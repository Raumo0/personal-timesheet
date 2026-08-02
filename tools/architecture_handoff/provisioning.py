"""Approval-gated, provider-neutral endpoint provisioning."""

import hashlib
import secrets
from threading import Lock
from typing import Callable, Protocol

from .provisioning_attempts import (
    InMemoryProvisioningAttemptStore,
    ProvisioningAttemptStore,
    ProvisioningAttemptStoreError,
)

from .provisioning_models import (
    PreparedProvisioning,
    ProvisioningAction,
    ProvisioningActionReceipt,
    ProvisioningAuthorization,
    ProvisioningCall,
    ProvisioningCheck,
    ProvisioningObservation,
    ProvisioningReceipt,
    ProvisioningRequirement,
    ProvisioningResourceState,
    requirements_for_endpoint,
)
from .registry import ProviderEndpointConfig
from .write_coordinator import canonical_json


class ProvisioningError(ValueError):
    """Provisioning cannot proceed safely."""

    def __init__(
        self,
        message: str,
        *,
        provider_calls: tuple[ProvisioningCall, ...] = (),
        failed_stable_id: str | None = None,
    ) -> None:
        super().__init__(message)
        if not isinstance(provider_calls, tuple) or any(
            not isinstance(call, ProvisioningCall)
            for call in provider_calls
        ):
            raise ValueError(
                "provider_calls must contain ProvisioningCall values"
            )
        self.provider_calls = provider_calls
        if failed_stable_id is not None and (
            not isinstance(failed_stable_id, str)
            or not failed_stable_id.strip()
            or failed_stable_id != failed_stable_id.strip()
        ):
            raise ValueError(
                "failed_stable_id must be a non-empty trimmed string"
            )
        self.failed_stable_id = failed_stable_id


class ProvisioningAdapterCallError(ProvisioningError):
    """A provider adapter failed after attempting declared calls."""


class ProvisioningExecutionError(ProvisioningError):
    """Provisioning stopped after an approved action failed."""

    def __init__(
        self,
        message: str,
        *,
        successful_stable_ids: tuple[str, ...] = (),
        failed_stable_id: str | None = None,
        provider_calls: tuple[ProvisioningCall, ...] = (),
    ) -> None:
        super().__init__(
            message,
            provider_calls=provider_calls,
            failed_stable_id=failed_stable_id,
        )
        self.successful_stable_ids = successful_stable_ids


class ProvisioningAdapter(Protocol):
    endpoint: ProviderEndpointConfig

    def ensure_create_available(
        self,
        actions: tuple[ProvisioningAction, ...],
    ) -> None:
        ...

    def inspect(
        self,
        requirement: ProvisioningRequirement,
    ) -> tuple[ProvisioningObservation, tuple[ProvisioningCall, ...]]:
        ...

    def create(
        self,
        action: ProvisioningAction,
    ) -> tuple[ProvisioningActionReceipt, tuple[ProvisioningCall, ...]]:
        ...


class _EndpointProvisioningGuard:
    def __init__(self) -> None:
        self.lock = Lock()


_endpoint_guards: dict[str, _EndpointProvisioningGuard] = {}
_endpoint_guards_lock = Lock()


def _guard_for(
    endpoint: ProviderEndpointConfig,
) -> _EndpointProvisioningGuard:
    endpoint_key = canonical_json(endpoint)
    with _endpoint_guards_lock:
        guard = _endpoint_guards.get(endpoint_key)
        if guard is None:
            guard = _EndpointProvisioningGuard()
            _endpoint_guards[endpoint_key] = guard
        return guard


def _style_drift_limitation(observation: ProvisioningObservation) -> str:
    return (
        "style-drift is advisory for existing resource: "
        f"{observation.requirement.name}"
    )


def _fingerprint(
    endpoint: ProviderEndpointConfig,
    requirements: tuple[ProvisioningRequirement, ...],
    check: ProvisioningCheck,
    actions: tuple[ProvisioningAction, ...],
) -> str:
    material = canonical_json(
        {
            "endpoint": endpoint,
            "requirements": requirements,
            "check": check,
            "actions": actions,
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _require_approval_reference(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProvisioningError(
            "approval_reference must be a non-empty string"
        )
    if value != value.strip():
        raise ProvisioningError(
            "approval_reference must not have leading or trailing whitespace"
        )
    return value


def _new_preparation_id() -> str:
    return "prep_" + secrets.token_urlsafe(32)


_default_attempt_store = InMemoryProvisioningAttemptStore()


class ProvisioningCoordinator:
    def __init__(
        self,
        endpoint: ProviderEndpointConfig,
        adapter: ProvisioningAdapter,
        *,
        attempt_store: ProvisioningAttemptStore | None = None,
        preparation_id_factory: Callable[[], str] = _new_preparation_id,
    ) -> None:
        try:
            requirements = requirements_for_endpoint(endpoint)
        except ValueError as error:
            raise ProvisioningError(str(error)) from error
        if getattr(adapter, "endpoint", None) != endpoint:
            raise ProvisioningError(
                "adapter endpoint does not match provisioning endpoint"
            )
        if not callable(
            getattr(adapter, "ensure_create_available", None)
        ):
            raise ProvisioningError(
                "adapter must implement create availability checks"
            )
        self._endpoint = endpoint
        self._adapter = adapter
        self._requirements = requirements
        self._guard = _guard_for(endpoint)
        self._attempt_store = attempt_store or _default_attempt_store
        if (
            not callable(getattr(self._attempt_store, "issue", None))
            or not callable(getattr(self._attempt_store, "consume", None))
        ):
            raise ProvisioningError(
                "attempt_store must implement atomic issue and consume"
            )
        if not callable(preparation_id_factory):
            raise ProvisioningError(
                "preparation_id_factory must be callable"
            )
        self._preparation_id_factory = preparation_id_factory

    def check(self) -> ProvisioningCheck:
        with self._guard.lock:
            return self._check()

    def _check(self) -> ProvisioningCheck:
        observations = []
        calls = []
        limitations = []
        for requirement in self._requirements:
            try:
                result = self._adapter.inspect(requirement)
            except Exception as error:
                raise ProvisioningError(
                    "incomplete provisioning inspection for "
                    f"{requirement.name}: {error}",
                    provider_calls=(
                        tuple(calls)
                        + tuple(
                            getattr(error, "provider_calls", ())
                        )
                    ),
                    failed_stable_id=requirement.name,
                ) from error
            if not isinstance(result, tuple) or len(result) != 2:
                raise ProvisioningError(
                    "incomplete provisioning inspection for "
                    f"{requirement.name}",
                    failed_stable_id=requirement.name,
                )
            observation, inspection_calls = result
            if (
                not isinstance(observation, ProvisioningObservation)
                or observation.requirement != requirement
            ):
                raise ProvisioningError(
                    "incomplete provisioning inspection for "
                    f"{requirement.name}",
                    failed_stable_id=requirement.name,
                )
            if not isinstance(inspection_calls, tuple) or any(
                not isinstance(call, ProvisioningCall)
                for call in inspection_calls
            ):
                raise ProvisioningError(
                    "invalid inspection calls for "
                    f"{requirement.name}",
                    failed_stable_id=requirement.name,
                )
            observations.append(observation)
            calls.extend(inspection_calls)
            if observation.state is ProvisioningResourceState.STYLE_DRIFT:
                limitations.append(_style_drift_limitation(observation))
            elif (
                observation.state
                is ProvisioningResourceState.CONFLICTING
            ):
                limitations.append(observation.limitation)

        return ProvisioningCheck(
            endpoint=self._endpoint,
            requirements=self._requirements,
            observations=tuple(observations),
            calls=tuple(calls),
            limitations=tuple(limitations),
        )

    def prepare(self) -> PreparedProvisioning:
        with self._guard.lock:
            prepared = self._prepare()
            try:
                issued = self._attempt_store.issue(
                    prepared.preparation_id,
                    prepared.fingerprint,
                )
            except ProvisioningAttemptStoreError as error:
                raise ProvisioningError(
                    f"provisioning attempt ledger failed: {error}",
                    provider_calls=prepared.check.calls,
                ) from error
            if not issued:
                raise ProvisioningError(
                    "provisioning preparation identity was already issued",
                    provider_calls=prepared.check.calls,
                )
            return prepared

    def _prepare(
        self,
        preparation_id: str | None = None,
    ) -> PreparedProvisioning:
        check = self._check()
        conflicting = tuple(
            observation.requirement.name
            for observation in check.observations
            if observation.state is ProvisioningResourceState.CONFLICTING
        )
        if conflicting:
            raise ProvisioningError(
                "conflicting provisioning resources block preparation: "
                + ", ".join(conflicting),
                provider_calls=check.calls,
            )
        if len(check.observations) != len(check.requirements):
            raise ProvisioningError(
                "incomplete provisioning inspection blocks preparation",
                provider_calls=check.calls,
            )
        actions = tuple(
            ProvisioningAction(
                requirement=observation.requirement,
                resource=observation.resource,
            )
            for observation in check.observations
            if observation.state is ProvisioningResourceState.MISSING
        )
        return PreparedProvisioning(
            check=check,
            actions=actions,
            fingerprint=_fingerprint(
                self._endpoint,
                self._requirements,
                check,
                actions,
            ),
            preparation_id=(
                preparation_id
                if preparation_id is not None
                else self._preparation_id_factory()
            ),
        )

    def execute(
        self,
        authorization: ProvisioningAuthorization,
        *,
        preflight_calls: tuple[ProvisioningCall, ...] = (),
    ) -> ProvisioningReceipt:
        if not isinstance(authorization, ProvisioningAuthorization):
            raise ProvisioningError(
                "authorization must be a ProvisioningAuthorization"
            )
        _require_approval_reference(authorization.approval_reference)
        if not isinstance(preflight_calls, tuple) or any(
            not isinstance(call, ProvisioningCall)
            for call in preflight_calls
        ):
            raise ProvisioningError(
                "preflight_calls must contain ProvisioningCall values"
            )

        with self._guard.lock:
            provider_calls = list(preflight_calls)
            try:
                prepared = self._prepare(
                    preparation_id=authorization.preparation_id
                )
            except ProvisioningError as error:
                raise ProvisioningError(
                    str(error),
                    provider_calls=(
                        tuple(provider_calls) + error.provider_calls
                    ),
                    failed_stable_id=error.failed_stable_id,
                ) from error
            provider_calls.extend(prepared.check.calls)
            if authorization.fingerprint != prepared.fingerprint:
                raise ProvisioningError(
                    "provisioning fingerprint changed",
                    provider_calls=tuple(provider_calls),
                )
            try:
                self._adapter.ensure_create_available(prepared.actions)
            except ProvisioningError as error:
                raise ProvisioningError(
                    str(error),
                    provider_calls=(
                        tuple(provider_calls) + error.provider_calls
                    ),
                    failed_stable_id=error.failed_stable_id,
                ) from error
            except Exception as error:
                raise ProvisioningError(
                    "provisioning action availability check failed",
                    provider_calls=tuple(provider_calls),
                ) from error
            try:
                consumed = self._attempt_store.consume(
                    authorization.preparation_id,
                    authorization.fingerprint,
                )
            except ProvisioningAttemptStoreError as error:
                raise ProvisioningError(
                    f"provisioning attempt ledger failed: {error}",
                    provider_calls=tuple(provider_calls),
                ) from error
            if not consumed:
                raise ProvisioningError(
                    "provisioning preparation identity was not issued with "
                    "this fingerprint or was already attempted",
                    provider_calls=tuple(provider_calls),
                )

            action_receipts = []
            for action in prepared.actions:
                try:
                    result = self._adapter.create(action)
                    receipt, create_calls = self._validate_create_result(
                        action,
                        result,
                    )
                except Exception as error:
                    if isinstance(error, ProvisioningExecutionError):
                        raise
                    provider_calls.extend(
                        getattr(error, "provider_calls", ())
                    )
                    raise ProvisioningExecutionError(
                        "provisioning failed for "
                        f"{action.stable_id}: {error}",
                        successful_stable_ids=tuple(
                            item.stable_id for item in action_receipts
                        ),
                        failed_stable_id=action.stable_id,
                        provider_calls=tuple(provider_calls),
                    ) from error
                action_receipts.append(receipt)
                provider_calls.extend(create_calls)

            successful_stable_ids = tuple(
                receipt.stable_id for receipt in action_receipts
            )
            try:
                readback = self._check()
            except Exception as error:
                provider_calls.extend(
                    getattr(error, "provider_calls", ())
                )
                raise ProvisioningExecutionError(
                    f"provisioning readback failed: {error}",
                    successful_stable_ids=successful_stable_ids,
                    failed_stable_id=getattr(
                        error,
                        "failed_stable_id",
                        None,
                    ),
                    provider_calls=tuple(provider_calls),
                ) from error
            provider_calls.extend(readback.calls)

            readback_requirements = tuple(
                observation.requirement
                for observation in readback.observations
            )
            invalid = tuple(
                observation.requirement.name
                for observation in readback.observations
                if observation.state
                in {
                    ProvisioningResourceState.MISSING,
                    ProvisioningResourceState.CONFLICTING,
                }
            )
            if (
                readback.requirements != self._requirements
                or readback_requirements != self._requirements
                or invalid
            ):
                failed_stable_id = (
                    invalid[0]
                    if invalid
                    else next(
                        (
                            requirement.name
                            for requirement in self._requirements
                            if requirement not in readback_requirements
                        ),
                        None,
                    )
                )
                raise ProvisioningExecutionError(
                    "provisioning readback was incomplete, missing, "
                    "or conflicting"
                    + (
                        f" for resource: {failed_stable_id}"
                        if failed_stable_id is not None
                        else ""
                    ),
                    successful_stable_ids=successful_stable_ids,
                    failed_stable_id=failed_stable_id,
                    provider_calls=tuple(provider_calls),
                )

            return ProvisioningReceipt(
                prepared=prepared,
                authorization=authorization,
                action_receipts=tuple(action_receipts),
                readback=readback,
                preflight_calls=preflight_calls,
            )

    @staticmethod
    def _validate_create_result(
        action: ProvisioningAction,
        result: object,
    ) -> tuple[
        ProvisioningActionReceipt,
        tuple[ProvisioningCall, ...],
    ]:
        if not isinstance(result, tuple) or len(result) != 2:
            raise ProvisioningError(
                "adapter returned an invalid provisioning result"
            )
        receipt, calls = result
        if not isinstance(calls, tuple) or any(
            not isinstance(call, ProvisioningCall) for call in calls
        ):
            raise ProvisioningError(
                "adapter returned invalid provisioning calls"
            )
        if (
            not isinstance(receipt, ProvisioningActionReceipt)
            or receipt.action != action
        ):
            raise ProvisioningError(
                "adapter returned an invalid provisioning receipt",
                provider_calls=calls,
            )
        if receipt.calls != calls:
            raise ProvisioningError(
                "adapter receipt calls do not match provisioning calls",
                provider_calls=calls,
            )
        return receipt, calls
