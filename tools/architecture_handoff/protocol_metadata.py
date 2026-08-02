from dataclasses import dataclass
from enum import Enum
import json

from .models import WorkRoute
from .write_models import (
    IntakeState,
    ProtocolItemKind,
    RelationKind,
    ReturnKind,
    TypedRelation,
)


PROTOCOL_MARKER = "<!-- architecture-handoff-protocol"
PROTOCOL_SCHEMA_VERSION = 2
_PROTOCOL_CLOSING_MARKER = "-->"

WORK_ROUTE_LABELS = tuple(
    f"work-route:{route.value}"
    for route in WorkRoute
    if route is not WorkRoute.TARGET_NATIVE_INTERNAL
)
STATUS_LABELS = tuple(
    f"status:{value}"
    for value in (
        "draft",
        "backlog",
        "ready",
        "in-progress",
        "in-review",
        "done",
        "cancelled",
    )
)
RETURN_KIND_LABELS = tuple(
    f"return-kind:{return_kind.value}"
    for return_kind in ReturnKind
)
INTAKE_STATE_LABELS = tuple(
    f"intake-state:{intake_state.value}"
    for intake_state in IntakeState
)
ALL_PROTOCOL_LABELS = (
    WORK_ROUTE_LABELS
    + STATUS_LABELS
    + RETURN_KIND_LABELS
    + INTAKE_STATE_LABELS
)

_LABEL_FAMILIES = (
    ("work-route:", WORK_ROUTE_LABELS),
    ("status:", STATUS_LABELS),
    ("return-kind:", RETURN_KIND_LABELS),
    ("intake-state:", INTAKE_STATE_LABELS),
)
_SCALAR_KEYS = (
    "schema-version",
    "logical-target",
    "correlation-id",
    "capability",
    "expected-outcome",
)


class MetadataState(str, Enum):
    VERIFIED = "verified"
    MISSING = "missing"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class ProtocolMetadata:
    schema_version: int
    logical_target: str
    relations: tuple[TypedRelation, ...] = ()
    correlation_id: str | None = None
    capability: str | None = None
    expected_outcome: str | None = None


@dataclass(frozen=True)
class ParsedProtocolMetadata:
    state: MetadataState
    metadata: ProtocolMetadata | None
    limitation: str | None = None


def _require_non_blank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"blank {field}")
    return value


def _validate_line_scalar(value: object, field: str) -> str:
    value = _require_non_blank(value, field)
    if "\r" in value or "\n" in value:
        raise ValueError(f"{field} must not contain CR or LF")
    if value != value.strip():
        raise ValueError(
            f"{field} must not contain leading or trailing whitespace"
        )
    if (
        PROTOCOL_MARKER in value
        or _PROTOCOL_CLOSING_MARKER in value
    ):
        raise ValueError(f"{field} must not contain protocol delimiters")
    return value


def _validate_metadata(metadata: ProtocolMetadata) -> None:
    if not isinstance(metadata, ProtocolMetadata):
        raise ValueError("metadata must be ProtocolMetadata")
    if metadata.schema_version != PROTOCOL_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema version: {metadata.schema_version}"
        )
    _validate_line_scalar(metadata.logical_target, "logical-target")
    for field in ("correlation_id", "capability", "expected_outcome"):
        value = getattr(metadata, field)
        if value is not None:
            _validate_line_scalar(value, field.replace("_", "-"))
    seen = set()
    for relation in metadata.relations:
        if not isinstance(relation, TypedRelation):
            raise ValueError("relations must contain TypedRelation values")
        if not isinstance(relation.kind, RelationKind):
            raise ValueError("relation kind must be a RelationKind")
        _require_non_blank(relation.target, "relation target")
        if relation.revision is not None:
            _require_non_blank(relation.revision, "relation revision")
        if relation in seen:
            raise ValueError("duplicate relation")
        seen.add(relation)


def _relation_json(relation: TypedRelation) -> str:
    return json.dumps(
        {
            "kind": relation.kind.value,
            "revision": relation.revision,
            "target": relation.target,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def render_protocol_block(metadata: ProtocolMetadata) -> str:
    _validate_metadata(metadata)
    lines = [
        PROTOCOL_MARKER,
        f"schema-version: {metadata.schema_version}",
        f"logical-target: {metadata.logical_target}",
    ]
    for key, value in (
        ("correlation-id", metadata.correlation_id),
        ("capability", metadata.capability),
        ("expected-outcome", metadata.expected_outcome),
    ):
        if value is not None:
            lines.append(f"{key}: {value}")
    lines.extend(
        f"relation: {_relation_json(relation)}"
        for relation in metadata.relations
    )
    lines.append(_PROTOCOL_CLOSING_MARKER)
    return "\n".join(lines)


def _parse_relation(value: str) -> TypedRelation:
    def reject_duplicate_keys(pairs):
        record = {}
        for key, item in pairs:
            if key in record:
                raise ValueError(f"duplicate relation JSON key: {key}")
            record[key] = item
        return record

    try:
        record = json.loads(value, object_pairs_hook=reject_duplicate_keys)
    except json.JSONDecodeError as error:
        raise ValueError("malformed relation JSON") from error
    if not isinstance(record, dict) or set(record) != {
        "kind",
        "revision",
        "target",
    }:
        raise ValueError("malformed relation JSON object")
    try:
        kind = RelationKind(record["kind"])
    except (TypeError, ValueError) as error:
        raise ValueError("unsupported relation kind") from error
    target = _require_non_blank(record["target"], "relation target")
    revision = record["revision"]
    if revision is not None:
        revision = _require_non_blank(revision, "relation revision")
    return TypedRelation(kind=kind, target=target, revision=revision)


def _parse_verified_block(block: str) -> ProtocolMetadata:
    lines = block.split("\n")
    if (
        not lines
        or lines[0] != PROTOCOL_MARKER
        or lines[-1] != _PROTOCOL_CLOSING_MARKER
    ):
        raise ValueError("protocol marker block is incomplete")
    scalars: dict[str, str] = {}
    relations = []
    for line in lines[1:-1]:
        if ":" not in line:
            raise ValueError("metadata line has no key separator")
        key, value = line.split(":", 1)
        if key == "relation":
            relation = _parse_relation(value.strip())
            if relation in relations:
                raise ValueError("duplicate relation")
            relations.append(relation)
            continue
        if key not in _SCALAR_KEYS:
            raise ValueError(f"unsupported metadata key: {key}")
        if key in scalars:
            raise ValueError(f"duplicate {key}")
        if not value.startswith(" "):
            raise ValueError(f"{key} must follow the canonical line format")
        scalars[key] = _validate_line_scalar(value[1:], key)
    for required in ("schema-version", "logical-target"):
        if required not in scalars:
            raise ValueError(f"missing {required}")
    try:
        schema_version = int(scalars["schema-version"])
    except ValueError as error:
        raise ValueError("schema-version must be an integer") from error
    metadata = ProtocolMetadata(
        schema_version=schema_version,
        logical_target=scalars["logical-target"],
        relations=tuple(relations),
        correlation_id=scalars.get("correlation-id"),
        capability=scalars.get("capability"),
        expected_outcome=scalars.get("expected-outcome"),
    )
    _validate_metadata(metadata)
    return metadata


def _block_keys(block: str) -> tuple[str, ...]:
    lines = block.split("\n")
    return tuple(
        line.split(":", 1)[0]
        for line in lines[1:-1]
        if ":" in line
    )


def _parse_legacy_block(block: str) -> None:
    lines = block.split("\n")
    if (
        not lines
        or lines[0] != PROTOCOL_MARKER
        or lines[-1] != _PROTOCOL_CLOSING_MARKER
    ):
        raise ValueError("protocol marker block is incomplete")
    correlation_id = None
    relations = []
    for line in lines[1:-1]:
        if ":" not in line:
            raise ValueError("metadata line has no key separator")
        key, value = line.split(":", 1)
        if key == "relation":
            if not value.startswith(" "):
                raise ValueError(
                    "relation must follow the canonical line format"
                )
            relation = _parse_relation(value[1:])
            if relation in relations:
                raise ValueError("duplicate relation")
            relations.append(relation)
            continue
        if key != "correlation-id":
            raise ValueError(f"unsupported legacy metadata key: {key}")
        if correlation_id is not None:
            raise ValueError("duplicate correlation-id")
        if not value.startswith(" "):
            raise ValueError(
                "correlation-id must follow the canonical line format"
            )
        correlation_id = _validate_line_scalar(
            value[1:],
            "correlation-id",
        )
    if correlation_id is None and not relations:
        raise ValueError("legacy metadata block is empty")


def parse_protocol_block(body: str) -> ParsedProtocolMetadata:
    if not isinstance(body, str):
        return ParsedProtocolMetadata(
            MetadataState.MALFORMED,
            None,
            "Issue body must be a string",
        )
    marker_index = body.rfind(PROTOCOL_MARKER)
    if marker_index < 0:
        return ParsedProtocolMetadata(
            MetadataState.MISSING,
            None,
            "versioned protocol metadata is missing",
        )
    closing_index = body.find("\n-->", marker_index)
    if closing_index < 0:
        return ParsedProtocolMetadata(
            MetadataState.MALFORMED,
            None,
            "protocol marker block is incomplete",
        )
    block = body[marker_index : closing_index + len("\n-->")]
    v2_keys = {
        "schema-version",
        "logical-target",
        "capability",
        "expected-outcome",
    }
    try:
        if v2_keys.intersection(_block_keys(block)):
            metadata = _parse_verified_block(block)
        else:
            _parse_legacy_block(block)
            return ParsedProtocolMetadata(
                MetadataState.MISSING,
                None,
                "legacy unversioned protocol metadata is unverified",
            )
    except ValueError as error:
        return ParsedProtocolMetadata(
            MetadataState.MALFORMED,
            None,
            str(error),
        )
    return ParsedProtocolMetadata(MetadataState.VERIFIED, metadata)


def validate_protocol_labels(
    labels: tuple[str, ...],
    *,
    item_kind: ProtocolItemKind | None = None,
) -> None:
    if not isinstance(labels, tuple) or any(
        not isinstance(label, str) or not label
        for label in labels
    ):
        raise ValueError("labels must contain non-empty strings")
    for prefix, vocabulary in _LABEL_FAMILIES:
        family_labels = tuple(
            label for label in labels if label.startswith(prefix)
        )
        family = prefix.removesuffix(":")
        if len(family_labels) > 1:
            raise ValueError(f"multiple {family} labels")
        if family_labels and family_labels[0] not in vocabulary:
            if family_labels[0] == "work-route:target-native-internal":
                raise ValueError(
                    "target-native internal work must omit work-route"
                )
            raise ValueError(
                f"unsupported {family} label: {family_labels[0]}"
            )
    if item_kind is ProtocolItemKind.WORK_ITEM and any(
        label.startswith(("return-kind:", "intake-state:"))
        for label in labels
    ):
        raise ValueError("work item must not carry return or intake labels")
    if item_kind is ProtocolItemKind.RETURN_ITEM and any(
        label.startswith("work-route:") for label in labels
    ):
        raise ValueError("Return Item must not carry work-route labels")
    if item_kind is ProtocolItemKind.RETURN_ITEM and any(
        label.startswith("status:") for label in labels
    ):
        raise ValueError("Return Item must not carry status labels")
