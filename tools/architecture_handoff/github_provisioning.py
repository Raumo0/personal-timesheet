"""GitHub resource mapping for protocol endpoint provisioning."""

import json
import re
from typing import Mapping, Protocol
from urllib.parse import quote

from .github import (
    AdapterError,
    GitHubNotFoundError,
    validate_repository_name,
)
from .protocol_metadata import ALL_PROTOCOL_LABELS
from .provisioning import (
    ProvisioningAdapterCallError,
    ProvisioningError,
)
from .provisioning_models import (
    ProvisioningAction,
    ProvisioningActionReceipt,
    ProvisioningCall,
    ProvisioningObservation,
    ProvisioningRequirement,
    ProvisioningResourceSpec,
    ProvisioningResourceState,
)
from .registry import ProviderEndpointConfig
from .write_coordinator import canonical_json


GITHUB_PROTOCOL_LABEL_MANIFEST = {
    "work-route:architecture-slice-handoff": {
        "color": "1D76DB",
        "description": "Implements one bounded architecture slice",
    },
    "work-route:implementation-conformance-referral": {
        "color": "D93F0B",
        "description": "Corrects implementation against accepted sources",
    },
    "work-route:spike-evidence": {
        "color": "5319E7",
        "description": "Returns bounded evidence before dependent work",
    },
    "status:draft": {
        "color": "C5DEF5",
        "description": "Created but not ready for execution",
    },
    "status:backlog": {
        "color": "D4C5F9",
        "description": "Deferred and retained for later selection",
    },
    "status:ready": {
        "color": "0E8A16",
        "description": "Authorized and ready for execution",
    },
    "status:in-progress": {
        "color": "FBCA04",
        "description": "Execution is in progress",
    },
    "status:in-review": {
        "color": "0052CC",
        "description": "Awaiting required review",
    },
    "status:done": {
        "color": "006B75",
        "description": "Required work and verification completed",
    },
    "status:cancelled": {
        "color": "B60205",
        "description": "Work was cancelled without completion",
    },
    "return-kind:evidence-result": {
        "color": "1D76DB",
        "description": "Returned evidence for validation and routing",
    },
    "return-kind:product-gap": {
        "color": "D93F0B",
        "description": "Product clarification or decision required",
    },
    "return-kind:architecture-gap": {
        "color": "5319E7",
        "description": "Architecture clarification or decision required",
    },
    "intake-state:pending": {
        "color": "FBCA04",
        "description": "Awaiting documentation-side handling",
    },
    "intake-state:handled": {
        "color": "0E8A16",
        "description": "Documentation-side follow-up completed or linked",
    },
}

if set(GITHUB_PROTOCOL_LABEL_MANIFEST) != set(ALL_PROTOCOL_LABELS):
    raise RuntimeError("GitHub label manifest must cover protocol labels")


class GitHubProvisioningTransport(Protocol):
    def get(
        self,
        path: str,
        params: Mapping[str, str],
    ) -> tuple[object, str | None]:
        ...

    def post(
        self,
        path: str,
        payload: Mapping[str, object],
    ) -> tuple[object, str | None]:
        ...


def _resource_for(
    requirement: ProvisioningRequirement,
) -> ProvisioningResourceSpec:
    if not isinstance(requirement, ProvisioningRequirement):
        raise AdapterError(
            "requirement must be a ProvisioningRequirement"
        )
    presentation = GITHUB_PROTOCOL_LABEL_MANIFEST.get(requirement.name)
    if presentation is None:
        raise AdapterError("unsupported GitHub provisioning requirement")
    return ProvisioningResourceSpec(
        resource_type="label",
        stable_id=requirement.name,
        create_payload_json=canonical_json(
            {
                "name": requirement.name,
                "color": presentation["color"],
                "description": presentation["description"],
            }
        ),
        presentation_json=canonical_json(presentation),
    )


def _observed_label_metadata(
    payload: object,
    expected_name: str,
) -> tuple[str | None, str | None, str | None]:
    if not isinstance(payload, dict):
        return None, None, "GitHub label response was malformed"
    name = payload.get("name")
    color = payload.get("color")
    description = payload.get("description")
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 256
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in name
        )
        or not isinstance(color, str)
        or re.fullmatch(r"[0-9A-Fa-f]{6}", color) is None
        or "description" not in payload
        or (
            description is not None
            and (
                not isinstance(description, str)
                or len(description) > 512
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in description
                )
            )
        )
    ):
        return None, None, "GitHub label response was malformed"
    presentation = canonical_json(
        {
            "color": color.upper(),
            "description": description,
        }
    )
    if name != expected_name or name != name.lower():
        return (
            name,
            presentation,
            "GitHub label identity conflicts with requirement",
        )
    return name, presentation, None


class GitHubProvisioningAdapter:
    def __init__(
        self,
        endpoint: ProviderEndpointConfig,
        transport: GitHubProvisioningTransport,
        *,
        create_enabled: bool,
    ) -> None:
        if getattr(endpoint, "provider", None) != "github":
            raise AdapterError("GitHub provisioning requires a GitHub endpoint")
        if getattr(endpoint, "routing_status", None) != "active":
            raise AdapterError("GitHub provisioning requires an active endpoint")
        if type(create_enabled) is not bool:
            raise AdapterError("create_enabled must be a boolean")
        self.endpoint = endpoint
        self._repository = validate_repository_name(endpoint.repository)
        self._transport = transport
        self._create_enabled = create_enabled

    def ensure_create_available(
        self,
        actions: tuple[ProvisioningAction, ...],
    ) -> None:
        if not isinstance(actions, tuple) or any(
            not isinstance(action, ProvisioningAction)
            for action in actions
        ):
            raise ProvisioningError(
                "actions must contain ProvisioningAction values"
            )
        if actions and not self._create_enabled:
            raise ProvisioningError(
                "GITHUB_TOKEN is required for endpoint "
                "provisioning execution"
            )

    @staticmethod
    def _call(operation: str, stable_id: str) -> ProvisioningCall:
        return ProvisioningCall(
            operation=operation,
            resource_type="label",
            stable_id=stable_id,
        )

    def inspect(
        self,
        requirement: ProvisioningRequirement,
    ) -> tuple[ProvisioningObservation, tuple[ProvisioningCall, ...]]:
        resource = _resource_for(requirement)
        call = self._call("inspect", requirement.name)
        path = (
            f"repos/{self._repository}/labels/"
            f"{quote(requirement.name, safe='')}"
        )
        try:
            payload, _ = self._transport.get(path, {})
        except GitHubNotFoundError:
            return (
                ProvisioningObservation(
                    requirement=requirement,
                    resource=resource,
                    state=ProvisioningResourceState.MISSING,
                ),
                (call,),
            )
        except Exception as error:
            raise ProvisioningAdapterCallError(
                f"GitHub label inspection failed: {error}",
                provider_calls=(call,),
            ) from error

        observed_identity, observed_presentation, limitation = (
            _observed_label_metadata(payload, requirement.name)
        )
        if limitation is not None:
            return (
                ProvisioningObservation(
                    requirement=requirement,
                    resource=resource,
                    state=ProvisioningResourceState.CONFLICTING,
                    observed_identity=observed_identity,
                    observed_presentation_json=observed_presentation,
                    limitation=limitation,
                ),
                (call,),
            )
        if observed_presentation == resource.presentation_json:
            state = ProvisioningResourceState.SATISFIED
        else:
            state = ProvisioningResourceState.STYLE_DRIFT
        return (
            ProvisioningObservation(
                requirement=requirement,
                resource=resource,
                state=state,
                observed_identity=observed_identity,
                observed_presentation_json=observed_presentation,
            ),
            (call,),
        )

    def create(
        self,
        action: ProvisioningAction,
    ) -> tuple[ProvisioningActionReceipt, tuple[ProvisioningCall, ...]]:
        if not isinstance(action, ProvisioningAction):
            raise AdapterError("action must be a ProvisioningAction")
        self.ensure_create_available((action,))
        expected_resource = _resource_for(action.requirement)
        if action.resource != expected_resource:
            raise AdapterError(
                "provisioning action does not match the GitHub label manifest"
            )
        create_payload = json.loads(expected_resource.create_payload_json)
        call = self._call("create", action.stable_id)
        try:
            payload, _ = self._transport.post(
                f"repos/{self._repository}/labels",
                create_payload,
            )
        except Exception as error:
            raise ProvisioningAdapterCallError(
                f"GitHub label creation failed: {error}",
                provider_calls=(call,),
            ) from error
        observed_identity, observed_presentation, limitation = (
            _observed_label_metadata(payload, action.stable_id)
        )
        if (
            limitation is not None
            or observed_identity != action.stable_id
            or observed_presentation != expected_resource.presentation_json
        ):
            raise ProvisioningAdapterCallError(
                "GitHub label creation response did not match the action",
                provider_calls=(call,),
            )
        return (
            ProvisioningActionReceipt(action=action, calls=(call,)),
            (call,),
        )
