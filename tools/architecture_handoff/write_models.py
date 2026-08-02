from dataclasses import dataclass
from enum import Enum

from .lifecycle import validate_brief_transition
from .models import WorkRoute


class WriteOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"


class ProtocolItemKind(str, Enum):
    WORK_ITEM = "work-item"
    RETURN_ITEM = "return-item"


class ReturnKind(str, Enum):
    EVIDENCE_RESULT = "evidence-result"
    PRODUCT_GAP = "product-gap"
    ARCHITECTURE_GAP = "architecture-gap"


class IntakeState(str, Enum):
    PENDING = "pending"
    HANDLED = "handled"


class RelationKind(str, Enum):
    REFINEMENT = "refinement"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    SUPERSESSION = "supersession"
    CORRELATION = "correlation"
    RETURN = "return"


@dataclass(frozen=True)
class TypedRelation:
    kind: RelationKind
    target: str
    revision: str | None = None


@dataclass(frozen=True)
class WriteIntent:
    operation: WriteOperation
    target_key: str
    item_kind: ProtocolItemKind
    title: str
    body: str
    route: WorkRoute | None = None
    lifecycle_state: str | None = None
    previous_lifecycle_state: str | None = None
    intake_state: IntakeState | None = None
    previous_intake_state: IntakeState | None = None
    return_kind: ReturnKind | None = None
    relations: tuple[TypedRelation, ...] = ()
    correlation_id: str | None = None
    capability: str | None = None
    expected_outcome: str | None = None
    related_items: tuple[str, ...] = ()
    provider_id: str | None = None
    expected_provider_state: str | None = None


def _require_non_empty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def validate_intent(intent: WriteIntent) -> None:
    if not isinstance(intent, WriteIntent):
        raise ValueError("intent must be a WriteIntent")
    if not isinstance(intent.operation, WriteOperation):
        raise ValueError("operation must be a WriteOperation")
    if not isinstance(intent.item_kind, ProtocolItemKind):
        raise ValueError("item_kind must be a ProtocolItemKind")
    _require_non_empty(intent.target_key, "target_key")
    _require_non_empty(intent.title, "title")
    _require_non_empty(intent.body, "body")

    if intent.operation is WriteOperation.CREATE:
        if (
            intent.provider_id is not None
            or intent.expected_provider_state is not None
        ):
            raise ValueError("create intent must not carry provider state")
        if intent.previous_lifecycle_state is not None:
            raise ValueError(
                "create intent must not carry previous_lifecycle_state"
            )
    else:
        if (
            intent.provider_id is None
            or intent.expected_provider_state is None
        ):
            raise ValueError(
                "update requires provider_id and expected_provider_state"
            )
        _require_non_empty(intent.provider_id, "provider_id")
        _require_non_empty(
            intent.expected_provider_state,
            "expected_provider_state",
        )

    if intent.item_kind is ProtocolItemKind.WORK_ITEM:
        if not isinstance(intent.route, WorkRoute):
            raise ValueError("work item route must be a WorkRoute")
        if intent.route is WorkRoute.TARGET_NATIVE_INTERNAL:
            raise ValueError(
                "documentation-side writes reject target-native internal work"
            )
        if not intent.relations:
            raise ValueError(
                f"{intent.route.value} requires a direct typed relation"
            )
        if (
            intent.intake_state is not None
            or intent.previous_intake_state is not None
            or intent.return_kind is not None
        ):
            raise ValueError(
                "work item must not carry Return Item lifecycle"
            )
    else:
        if intent.route is not None:
            raise ValueError("Return Item must not carry work-route")
        if (
            intent.lifecycle_state is not None
            or intent.previous_lifecycle_state is not None
        ):
            raise ValueError(
                "Return Item must not carry Brief lifecycle"
            )
        if not isinstance(intent.return_kind, ReturnKind):
            raise ValueError("return_kind must be a ReturnKind")
        if not isinstance(intent.intake_state, IntakeState):
            raise ValueError("intake_state must be an IntakeState")
        _require_non_empty(intent.correlation_id, "correlation_id")
        if (
            len(intent.relations) != 1
            or intent.relations[0].kind is not RelationKind.RETURN
        ):
            raise ValueError(
                "Return Item requires one direct return relation"
            )
        if intent.operation is WriteOperation.CREATE:
            if intent.intake_state is not IntakeState.PENDING:
                raise ValueError(
                    "Return creation requires intake-state pending"
                )
            if intent.previous_intake_state is not None:
                raise ValueError(
                    "Return creation must not carry "
                    "previous_intake_state"
                )
        elif not (
            intent.previous_intake_state is IntakeState.PENDING
            and intent.intake_state is IntakeState.HANDLED
        ):
            raise ValueError(
                "Return update must transition pending to handled"
            )

    for relation in intent.relations:
        if not isinstance(relation, TypedRelation):
            raise ValueError("relations must contain TypedRelation values")
        if not isinstance(relation.kind, RelationKind):
            raise ValueError("relation kind must be a RelationKind")
        _require_non_empty(relation.target, "relation target")
        if relation.revision is not None:
            _require_non_empty(relation.revision, "relation revision")

    if intent.correlation_id is not None:
        _require_non_empty(intent.correlation_id, "correlation_id")
    if intent.capability is not None:
        _require_non_empty(intent.capability, "capability")
    if intent.expected_outcome is not None:
        _require_non_empty(intent.expected_outcome, "expected_outcome")
    for related_item in intent.related_items:
        _require_non_empty(related_item, "related item")

    if intent.route is WorkRoute.ARCHITECTURE_SLICE_HANDOFF:
        if intent.operation is WriteOperation.CREATE:
            if intent.lifecycle_state != "draft":
                raise ValueError(
                    "Architecture Slice Brief must start as draft"
                )
        else:
            _require_non_empty(
                intent.previous_lifecycle_state,
                "previous_lifecycle_state",
            )
            _require_non_empty(
                intent.lifecycle_state,
                "lifecycle_state",
            )
            validate_brief_transition(
                intent.previous_lifecycle_state,
                intent.lifecycle_state,
            )
