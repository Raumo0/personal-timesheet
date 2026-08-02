from typing import Mapping, Protocol
from urllib.parse import urlparse

from .github import AdapterError, validate_repository_name
from .protocol_metadata import (
    ALL_PROTOCOL_LABELS,
    MetadataState,
    PROTOCOL_MARKER,
    PROTOCOL_SCHEMA_VERSION,
    ProtocolMetadata,
    parse_protocol_block,
    render_protocol_block,
    validate_protocol_labels,
)
from .registry import (
    ProviderEndpointConfig,
    StoreConfig,
    TargetConfig,
)
from .write_coordinator import NormalizedReadback, canonical_json
from .write_models import (
    ProtocolItemKind,
    WriteIntent,
    WriteOperation,
    validate_intent,
)


PROTOCOL_LABEL_PREFIXES = tuple(
    dict.fromkeys(
        f"{label.partition(':')[0]}:"
        for label in ALL_PROTOCOL_LABELS
    )
)


class GitHubWriteTransport(Protocol):
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

    def patch(
        self,
        path: str,
        payload: Mapping[str, object],
    ) -> tuple[object, str | None]:
        ...


def _provider_id(value: object) -> str:
    provider_id = str(value)
    if (
        isinstance(value, bool)
        or not provider_id.isdigit()
        or int(provider_id) < 1
    ):
        raise AdapterError("GitHub Issue number must be positive")
    return provider_id


def _label_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AdapterError("GitHub Issue labels must be a list")
    labels = []
    for label in value:
        if isinstance(label, str) and label:
            labels.append(label)
        elif (
            isinstance(label, dict)
            and isinstance(label.get("name"), str)
            and label["name"]
        ):
            labels.append(label["name"])
        else:
            raise AdapterError("GitHub Issue label is invalid")
    return tuple(labels)


def _validate_labels(
    labels: tuple[str, ...],
    *,
    item_kind: ProtocolItemKind | None = None,
) -> None:
    try:
        validate_protocol_labels(labels, item_kind=item_kind)
    except ValueError as error:
        raise AdapterError(str(error)) from error


def _protocol_label_value(
    labels: tuple[str, ...],
    prefix: str,
) -> str | None:
    for label in labels:
        if label.startswith(prefix):
            return label.removeprefix(prefix)
    return None


def _render_protocol_body(intent: WriteIntent) -> str:
    body = intent.body.rstrip()
    marker_index = body.rfind(PROTOCOL_MARKER)
    if marker_index >= 0 and body[marker_index:].rstrip().endswith("\n-->"):
        body = body[:marker_index].rstrip()
    metadata = ProtocolMetadata(
        schema_version=PROTOCOL_SCHEMA_VERSION,
        logical_target=intent.target_key,
        relations=intent.relations,
        correlation_id=intent.correlation_id,
        capability=intent.capability,
        expected_outcome=intent.expected_outcome,
    )
    return "\n".join((body, "", render_protocol_block(metadata)))


def _validate_selected_issue(
    payload: Mapping[str, object],
    repository: str,
    provider_id: str,
) -> None:
    if "pull_request" in payload:
        raise AdapterError(
            "selected GitHub item is a pull request, not an Issue"
        )
    try:
        observed_id = _provider_id(payload["number"])
    except KeyError as error:
        raise AdapterError("GitHub Issue is missing number") from error
    if observed_id != provider_id:
        raise AdapterError(
            "GitHub Issue identity does not match selected provider_id"
        )
    expected_url = (
        f"https://github.com/{repository}/issues/{provider_id}"
    )
    if payload.get("html_url") != expected_url:
        raise AdapterError(
            "GitHub Issue URL does not match bound repository and number"
        )


def _expected_pending_return_body(intent: WriteIntent) -> str:
    rendered = _render_protocol_body(intent)
    lines = rendered.splitlines()
    handled = "intake-state: handled"
    if len(lines) < 2 or lines[1] != handled:
        raise AdapterError(
            "Return update body must contain the canonical handled "
            "intake state"
        )
    lines[1] = "intake-state: pending"
    return "\n".join(lines)


class GitHubWriteAdapter:
    def __init__(
        self,
        target: ProviderEndpointConfig,
        transport: GitHubWriteTransport,
    ):
        if not isinstance(target, (TargetConfig, StoreConfig)):
            raise AdapterError(
                "GitHub write adapter requires a provider endpoint"
            )
        if target.provider != "github":
            raise AdapterError(
                "GitHub write adapter requires provider github"
            )
        if target.routing_status != "active":
            raise AdapterError(
                "GitHub write adapter requires an active target"
            )
        self.target = target
        self._repository = validate_repository_name(target.repository)
        self._transport = transport

    def render_payload(
        self,
        intent: WriteIntent,
    ) -> Mapping[str, object]:
        validate_intent(intent)
        labels = set()
        if intent.operation is WriteOperation.UPDATE:
            current = self.get_item(intent.provider_id)
            if current.get("updated_at") != intent.expected_provider_state:
                raise AdapterError(
                    "provider state changed after preview"
                )
            current_labels = _label_names(current.get("labels"))
            _validate_labels(current_labels, item_kind=intent.item_kind)
            if intent.item_kind is ProtocolItemKind.WORK_ITEM:
                current_route = _protocol_label_value(
                    current_labels,
                    "work-route:",
                )
                if current_route != intent.route.value:
                    raise AdapterError(
                        "current work-route does not match update intent"
                    )
                if intent.previous_lifecycle_state is not None:
                    current_state = _protocol_label_value(
                        current_labels,
                        "status:",
                    )
                    if current_state != intent.previous_lifecycle_state:
                        raise AdapterError(
                            "current status does not match declared "
                            "previous lifecycle state"
                        )
            else:
                current_return_kind = _protocol_label_value(
                    current_labels,
                    "return-kind:",
                )
                if current_return_kind != intent.return_kind.value:
                    raise AdapterError(
                        "current return-kind does not match update intent"
                    )
                current_intake_state = _protocol_label_value(
                    current_labels,
                    "intake-state:",
                )
                if (
                    current_intake_state
                    != intent.previous_intake_state.value
                ):
                    raise AdapterError(
                        "current intake-state does not match declared "
                        "previous intake state"
                    )
                if (
                    current.get("title") != intent.title
                    or current.get("body")
                    != _expected_pending_return_body(intent)
                ):
                    raise AdapterError(
                        "current immutable Return identity does not match "
                        "update intent"
                    )
            labels.update(
                label
                for label in current_labels
                if not label.startswith(PROTOCOL_LABEL_PREFIXES)
            )
        if intent.item_kind is ProtocolItemKind.WORK_ITEM:
            labels.add(f"work-route:{intent.route.value}")
            if intent.lifecycle_state is not None:
                labels.add(f"status:{intent.lifecycle_state}")
        else:
            labels.add(f"return-kind:{intent.return_kind.value}")
            labels.add(f"intake-state:{intent.intake_state.value}")
        _validate_labels(tuple(labels), item_kind=intent.item_kind)
        return {
            "body": _render_protocol_body(intent),
            "labels": sorted(labels),
            "title": intent.title,
        }

    def create_item(
        self,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        response, _ = self._transport.post(
            f"repos/{self._repository}/issues",
            payload,
        )
        if not isinstance(response, dict):
            raise AdapterError(
                "GitHub create response must be an object"
            )
        return response

    def update_item(
        self,
        provider_id: str,
        payload: Mapping[str, object],
        expected_state: str,
    ) -> Mapping[str, object]:
        provider_id = _provider_id(provider_id)
        if not isinstance(expected_state, str) or not expected_state:
            raise AdapterError(
                "expected provider state must be a non-empty string"
            )
        current = self.get_item(provider_id)
        if current.get("updated_at") != expected_state:
            raise AdapterError("provider state changed after preview")
        response, _ = self._transport.patch(
            f"repos/{self._repository}/issues/{provider_id}",
            payload,
        )
        if not isinstance(response, dict):
            raise AdapterError(
                "GitHub update response must be an object"
            )
        return response

    def get_item(self, provider_id: str) -> Mapping[str, object]:
        provider_id = _provider_id(provider_id)
        response, _ = self._transport.get(
            f"repos/{self._repository}/issues/{provider_id}",
            {},
        )
        if not isinstance(response, dict):
            raise AdapterError("GitHub Issue response must be an object")
        _validate_selected_issue(
            response,
            self._repository,
            provider_id,
        )
        return response

    def normalize_readback(
        self,
        payload: Mapping[str, object],
    ) -> NormalizedReadback:
        if not isinstance(payload, Mapping):
            raise AdapterError("GitHub Issue response must be an object")
        try:
            provider_id = _provider_id(payload["number"])
            title = payload["title"]
            body = payload["body"]
            updated = payload["updated_at"]
            url = payload["html_url"]
        except KeyError as error:
            raise AdapterError(
                f"GitHub Issue is missing {error.args[0]}"
            ) from error
        for value, field in (
            (title, "title"),
            (body, "body"),
            (updated, "updated_at"),
            (url, "html_url"),
        ):
            if not isinstance(value, str) or not value:
                raise AdapterError(
                    f"GitHub Issue {field} must be a non-empty string"
                )
        parsed_url = urlparse(url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise AdapterError("GitHub Issue URL must use https")
        expected_url = (
            f"https://github.com/{self._repository}/issues/{provider_id}"
        )
        if url != expected_url:
            raise AdapterError(
                "GitHub Issue URL does not match repository and Issue"
            )
        labels = _label_names(payload.get("labels"))
        item_kind = None
        if any(label.startswith("work-route:") for label in labels):
            item_kind = ProtocolItemKind.WORK_ITEM
        elif any(
            label.startswith(("return-kind:", "intake-state:"))
            for label in labels
        ):
            item_kind = ProtocolItemKind.RETURN_ITEM
        _validate_labels(labels, item_kind=item_kind)
        parsed_metadata = parse_protocol_block(body)
        if parsed_metadata.state is MetadataState.MALFORMED:
            raise AdapterError(
                "GitHub Issue has malformed protocol metadata: "
                f"{parsed_metadata.limitation}"
            )
        if (
            parsed_metadata.state is MetadataState.VERIFIED
            and parsed_metadata.metadata.logical_target != self.target.key
        ):
            raise AdapterError(
                "GitHub Issue protocol metadata logical target mismatch"
            )
        comparable = {
            "body": body,
            "labels": sorted(labels),
            "title": title,
        }
        return NormalizedReadback(
            provider="github",
            provider_id=provider_id,
            provider_qualified_id=(
                f"github:{self._repository}#{provider_id}"
            ),
            url=url,
            provider_state=updated,
            comparable_payload_json=canonical_json(comparable),
        )
