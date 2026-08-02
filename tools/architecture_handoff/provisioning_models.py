"""Provider-neutral, immutable contracts for endpoint provisioning."""

import json
import re
from dataclasses import dataclass, field
from enum import Enum

from .protocol_metadata import (
    INTAKE_STATE_LABELS,
    RETURN_KIND_LABELS,
    STATUS_LABELS,
    WORK_ROUTE_LABELS,
)
from .registry import StoreConfig, StoreRole, TargetConfig


class ProvisioningResourceState(str, Enum):
    SATISFIED = "satisfied"
    MISSING = "missing"
    STYLE_DRIFT = "style-drift"
    CONFLICTING = "conflicting"


def _require_non_blank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{field} must not have leading or trailing whitespace")
    return value


def _canonical_json(value: object, field: str) -> str:
    _require_non_blank(value, field)
    try:
        parsed = json.loads(value)
        canonical = json.dumps(
            parsed,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"{field} must be canonical JSON") from error
    if not isinstance(parsed, dict) or canonical != value:
        raise ValueError(f"{field} must be canonical JSON")
    return value


def _validate_endpoint(endpoint: object) -> TargetConfig | StoreConfig:
    if not isinstance(endpoint, (TargetConfig, StoreConfig)):
        raise ValueError("endpoint must be a TargetConfig or StoreConfig")
    for field in ("key", "provider", "repository"):
        _require_non_blank(getattr(endpoint, field), f"endpoint {field}")
    if endpoint.routing_status != "active":
        raise ValueError("endpoint must be active")
    if isinstance(endpoint, StoreConfig) and not isinstance(
        endpoint.role, StoreRole
    ):
        raise ValueError("endpoint store role must be a StoreRole")
    return endpoint


@dataclass(frozen=True)
class ProvisioningRequirement:
    family: str
    name: str

    def __post_init__(self) -> None:
        family = _require_non_blank(self.family, "family")
        name = _require_non_blank(self.name, "name")
        if ":" in family or any(character.isspace() for character in family):
            raise ValueError("family must be a protocol classifier family")
        if not name.startswith(f"{family}:") or name == f"{family}:":
            raise ValueError("name must belong to family")


@dataclass(frozen=True)
class ProvisioningResourceSpec:
    resource_type: str
    stable_id: str
    create_payload_json: str
    presentation_json: str

    def __post_init__(self) -> None:
        _require_non_blank(self.resource_type, "resource_type")
        _require_non_blank(self.stable_id, "stable_id")
        _canonical_json(self.create_payload_json, "create_payload_json")
        _canonical_json(self.presentation_json, "presentation_json")


@dataclass(frozen=True)
class ProvisioningObservation:
    requirement: ProvisioningRequirement
    resource: ProvisioningResourceSpec
    state: ProvisioningResourceState
    observed_identity: str | None = None
    observed_presentation_json: str | None = None
    limitation: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, ProvisioningRequirement):
            raise ValueError("requirement must be a ProvisioningRequirement")
        if not isinstance(self.resource, ProvisioningResourceSpec):
            raise ValueError("resource must be a ProvisioningResourceSpec")
        if self.resource.stable_id != self.requirement.name:
            raise ValueError("resource stable_id must match requirement name")
        if not isinstance(self.state, ProvisioningResourceState):
            raise ValueError("state must be a ProvisioningResourceState")
        if self.observed_identity is not None:
            _require_non_blank(self.observed_identity, "observed_identity")
            if (
                len(self.observed_identity) > 256
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in self.observed_identity
                )
            ):
                raise ValueError(
                    "observed_identity must be safe presentation text"
                )
        if self.observed_presentation_json is not None:
            _canonical_json(
                self.observed_presentation_json,
                "observed_presentation_json",
            )
        if self.limitation is not None:
            _require_non_blank(self.limitation, "limitation")

        if self.state is ProvisioningResourceState.MISSING:
            if (
                self.observed_identity is not None
                or self.observed_presentation_json is not None
                or self.limitation is not None
            ):
                raise ValueError("missing observation must not include a resource")
        elif self.state is ProvisioningResourceState.STYLE_DRIFT:
            if self.observed_presentation_json is None:
                raise ValueError("style-drift observation requires presentation")
            if self.observed_presentation_json == self.resource.presentation_json:
                raise ValueError("style-drift observation must differ in presentation")
            if self.limitation is not None:
                raise ValueError("style-drift observation must not include a limitation")
            if (
                self.observed_identity is not None
                and self.observed_identity != self.requirement.name
            ):
                raise ValueError(
                    "style-drift observed_identity must match requirement"
                )
        elif self.state is ProvisioningResourceState.CONFLICTING:
            if self.limitation is None:
                raise ValueError("conflicting observation requires a limitation")
        elif self.limitation is not None:
            raise ValueError("satisfied observation must not include a limitation")
        elif (
            self.observed_presentation_json is not None
            and self.observed_presentation_json != self.resource.presentation_json
        ):
            raise ValueError("satisfied observation must match presentation")
        elif (
            self.observed_identity is not None
            and self.observed_identity != self.requirement.name
        ):
            raise ValueError(
                "satisfied observed_identity must match requirement"
            )


@dataclass(frozen=True)
class ProvisioningCall:
    operation: str
    resource_type: str
    stable_id: str

    def __post_init__(self) -> None:
        _require_non_blank(self.operation, "operation")
        _require_non_blank(self.resource_type, "resource_type")
        _require_non_blank(self.stable_id, "stable_id")


def _validate_requirements(
    requirements: tuple[ProvisioningRequirement, ...],
) -> None:
    if not isinstance(requirements, tuple) or any(
        not isinstance(requirement, ProvisioningRequirement)
        for requirement in requirements
    ):
        raise ValueError("requirements must contain ProvisioningRequirement values")
    if len(set(requirements)) != len(requirements):
        raise ValueError("duplicate requirement")


@dataclass(frozen=True)
class ProvisioningCheck:
    endpoint: TargetConfig | StoreConfig
    requirements: tuple[ProvisioningRequirement, ...]
    observations: tuple[ProvisioningObservation, ...]
    calls: tuple[ProvisioningCall, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_endpoint(self.endpoint)
        _validate_requirements(self.requirements)
        if not isinstance(self.observations, tuple) or any(
            not isinstance(observation, ProvisioningObservation)
            for observation in self.observations
        ):
            raise ValueError("observations must contain ProvisioningObservation values")
        observation_requirements = tuple(
            observation.requirement for observation in self.observations
        )
        if len(set(observation_requirements)) != len(observation_requirements):
            raise ValueError("duplicate observation requirement")
        if any(
            requirement not in self.requirements
            for requirement in observation_requirements
        ):
            raise ValueError("observation requirement is not required")
        if not isinstance(self.calls, tuple) or any(
            not isinstance(call, ProvisioningCall) for call in self.calls
        ):
            raise ValueError("calls must contain ProvisioningCall values")
        if not isinstance(self.limitations, tuple):
            raise ValueError("limitations must be a tuple")
        for limitation in self.limitations:
            _require_non_blank(limitation, "limitation")


@dataclass(frozen=True)
class ProvisioningAction:
    requirement: ProvisioningRequirement
    resource: ProvisioningResourceSpec

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, ProvisioningRequirement):
            raise ValueError("requirement must be a ProvisioningRequirement")
        if not isinstance(self.resource, ProvisioningResourceSpec):
            raise ValueError("resource must be a ProvisioningResourceSpec")
        if self.resource.stable_id != self.requirement.name:
            raise ValueError("resource stable_id must match requirement name")

    @property
    def stable_id(self) -> str:
        return self.resource.stable_id


def _require_fingerprint(value: object, field: str) -> str:
    value = _require_non_blank(value, field)
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field} must be a SHA-256 fingerprint")
    return value


def validate_preparation_id(value: object) -> str:
    value = _require_non_blank(value, "preparation_id")
    if re.fullmatch(r"prep_[A-Za-z0-9_-]{43}", value) is None:
        raise ValueError("preparation_id must be an opaque preparation identity")
    return value


@dataclass(frozen=True)
class PreparedProvisioning:
    check: ProvisioningCheck
    actions: tuple[ProvisioningAction, ...]
    fingerprint: str
    preparation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.check, ProvisioningCheck):
            raise ValueError("check must be a ProvisioningCheck")
        if not isinstance(self.actions, tuple) or any(
            not isinstance(action, ProvisioningAction) for action in self.actions
        ):
            raise ValueError("actions must contain ProvisioningAction values")
        stable_ids = tuple(action.stable_id for action in self.actions)
        if len(set(stable_ids)) != len(stable_ids):
            raise ValueError("duplicate provisioning action")
        if any(
            action.requirement not in self.check.requirements
            for action in self.actions
        ):
            raise ValueError("action requirement is not required")
        expected_actions = tuple(
            ProvisioningAction(
                requirement=observation.requirement,
                resource=observation.resource,
            )
            for observation in self.check.observations
            if observation.state is ProvisioningResourceState.MISSING
        )
        if self.actions != expected_actions:
            raise ValueError(
                "actions must exactly match ordered missing observations"
            )
        _require_fingerprint(self.fingerprint, "fingerprint")
        validate_preparation_id(self.preparation_id)


@dataclass(frozen=True)
class ProvisioningAuthorization:
    fingerprint: str
    preparation_id: str
    approval_reference: str

    def __post_init__(self) -> None:
        _require_fingerprint(self.fingerprint, "fingerprint")
        validate_preparation_id(self.preparation_id)
        _require_non_blank(self.approval_reference, "approval_reference")


@dataclass(frozen=True)
class ProvisioningActionReceipt:
    action: ProvisioningAction
    calls: tuple[ProvisioningCall, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.action, ProvisioningAction):
            raise ValueError("action must be a ProvisioningAction")
        if (
            not isinstance(self.calls, tuple)
            or not self.calls
            or any(
                not isinstance(call, ProvisioningCall)
                for call in self.calls
            )
        ):
            raise ValueError(
                "calls must contain attempted ProvisioningCall values"
            )

    @property
    def stable_id(self) -> str:
        return self.action.stable_id


@dataclass(frozen=True)
class ProvisioningReceipt:
    prepared: PreparedProvisioning
    authorization: ProvisioningAuthorization
    action_receipts: tuple[ProvisioningActionReceipt, ...]
    readback: ProvisioningCheck
    preflight_calls: tuple[ProvisioningCall, ...] = ()
    calls: tuple[ProvisioningCall, ...] = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.prepared, PreparedProvisioning):
            raise ValueError("prepared must be a PreparedProvisioning")
        if not isinstance(self.authorization, ProvisioningAuthorization):
            raise ValueError("authorization must be a ProvisioningAuthorization")
        if self.authorization.fingerprint != self.prepared.fingerprint:
            raise ValueError("authorization fingerprint must match prepared fingerprint")
        if (
            self.authorization.preparation_id
            != self.prepared.preparation_id
        ):
            raise ValueError(
                "authorization preparation identity must match prepared identity"
            )
        if not isinstance(self.action_receipts, tuple) or any(
            not isinstance(receipt, ProvisioningActionReceipt)
            for receipt in self.action_receipts
        ):
            raise ValueError("action_receipts must contain ProvisioningActionReceipt values")
        receipt_ids = tuple(receipt.stable_id for receipt in self.action_receipts)
        if len(set(receipt_ids)) != len(receipt_ids):
            raise ValueError("duplicate provisioning action receipt")
        if (
            tuple(receipt.action for receipt in self.action_receipts)
            != self.prepared.actions
        ):
            raise ValueError(
                "action receipts must exactly match prepared actions"
            )
        if not isinstance(self.readback, ProvisioningCheck):
            raise ValueError("readback must be a ProvisioningCheck")
        if self.readback.endpoint != self.prepared.check.endpoint:
            raise ValueError("readback endpoint must match prepared endpoint")
        readback_requirements = tuple(
            observation.requirement
            for observation in self.readback.observations
        )
        if (
            self.readback.requirements != self.prepared.check.requirements
            or readback_requirements != self.readback.requirements
            or any(
                observation.state
                in {
                    ProvisioningResourceState.MISSING,
                    ProvisioningResourceState.CONFLICTING,
                }
                for observation in self.readback.observations
            )
        ):
            raise ValueError(
                "successful readback must be complete and non-conflicting"
            )
        if not isinstance(self.preflight_calls, tuple) or any(
            not isinstance(call, ProvisioningCall)
            for call in self.preflight_calls
        ):
            raise ValueError(
                "preflight_calls must contain ProvisioningCall values"
            )
        object.__setattr__(
            self,
            "calls",
            (
                self.preflight_calls
                + self.prepared.check.calls
                + tuple(
                    call
                    for receipt in self.action_receipts
                    for call in receipt.calls
                )
                + self.readback.calls
            ),
        )


def requirements_for_endpoint(
    endpoint: TargetConfig | StoreConfig,
) -> tuple[ProvisioningRequirement, ...]:
    endpoint = _validate_endpoint(endpoint)
    if isinstance(endpoint, TargetConfig):
        labels = WORK_ROUTE_LABELS + STATUS_LABELS
    elif endpoint.role is StoreRole.DOCUMENTATION_INTAKE:
        labels = RETURN_KIND_LABELS + INTAKE_STATE_LABELS
    else:
        raise ValueError(f"unsupported store role: {endpoint.role}")
    return tuple(
        ProvisioningRequirement(
            family=name.split(":", 1)[0],
            name=name,
        )
        for name in labels
    )
