from dataclasses import dataclass

from .write_models import (
    IntakeState,
    ProtocolItemKind,
    RelationKind,
    ReturnKind,
    TypedRelation,
    WriteIntent,
    WriteOperation,
    validate_intent,
)


@dataclass(frozen=True)
class ReturnIntent:
    operation: WriteOperation
    target_key: str
    title: str
    return_kind: ReturnKind
    intake_state: IntakeState
    correlation_id: str
    source_relation: TypedRelation
    origin: str
    evidence_links: tuple[str, ...]
    outcome: str
    method: str
    observations: str
    verification: str
    produced_artifacts: tuple[str, ...]
    limitations: tuple[str, ...]
    remaining_unknowns: tuple[str, ...]
    requested_return_route: str
    provider_id: str | None = None
    expected_provider_state: str | None = None
    previous_intake_state: IntakeState | None = None


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _string_tuple(
    value: object,
    field: str,
    *,
    non_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(
        not isinstance(item, str) or not item.strip()
        for item in value
    ):
        raise ValueError(f"{field} must be a tuple of non-empty strings")
    if non_empty and not value:
        raise ValueError(f"{field} must contain at least one item")
    return tuple(item.strip() for item in value)


def _bullet_lines(values: tuple[str, ...]) -> list[str]:
    if not values:
        return ["- None"]
    return [f"- {value}" for value in values]


def _validate_return(intent: ReturnIntent) -> None:
    if not isinstance(intent, ReturnIntent):
        raise ValueError("intent must be a ReturnIntent")
    if not isinstance(intent.operation, WriteOperation):
        raise ValueError("operation must be a WriteOperation")
    if not isinstance(intent.return_kind, ReturnKind):
        raise ValueError("return_kind must be a ReturnKind")
    if not isinstance(intent.intake_state, IntakeState):
        raise ValueError("intake_state must be an IntakeState")
    _require_string(intent.target_key, "target_key")
    _require_string(intent.title, "title")
    _require_string(intent.correlation_id, "correlation_id")
    if (
        not isinstance(intent.source_relation, TypedRelation)
        or intent.source_relation.kind is not RelationKind.RETURN
    ):
        raise ValueError(
            "source_relation must use RelationKind.RETURN"
        )
    _require_string(
        intent.source_relation.target,
        "source_relation target",
    )
    if intent.source_relation.revision is not None:
        _require_string(
            intent.source_relation.revision,
            "source_relation revision",
        )
    for field in (
        "origin",
        "outcome",
        "method",
        "observations",
        "verification",
        "requested_return_route",
    ):
        _require_string(getattr(intent, field), field)
    _string_tuple(
        intent.evidence_links,
        "evidence_links",
        non_empty=True,
    )
    for field in (
        "produced_artifacts",
        "limitations",
        "remaining_unknowns",
    ):
        _string_tuple(getattr(intent, field), field)

    if intent.operation is WriteOperation.CREATE:
        if intent.intake_state is not IntakeState.PENDING:
            raise ValueError(
                "Return creation requires intake-state pending"
            )
        if intent.previous_intake_state is not None:
            raise ValueError(
                "Return creation must not carry previous_intake_state"
            )
    elif not (
        intent.previous_intake_state is IntakeState.PENDING
        and intent.intake_state is IntakeState.HANDLED
    ):
        raise ValueError(
            "Return update must transition pending to handled"
        )


def _render_body(intent: ReturnIntent) -> str:
    evidence_links = _string_tuple(
        intent.evidence_links,
        "evidence_links",
        non_empty=True,
    )
    produced_artifacts = _string_tuple(
        intent.produced_artifacts,
        "produced_artifacts",
    )
    limitations = _string_tuple(intent.limitations, "limitations")
    remaining_unknowns = _string_tuple(
        intent.remaining_unknowns,
        "remaining_unknowns",
    )
    relation = intent.source_relation
    lines = [
        f"return-kind: {intent.return_kind.value}",
        f"intake-state: {intent.intake_state.value}",
        f"correlation-id: {intent.correlation_id.strip()}",
        (
            f"source-relation: {relation.kind.value} "
            f"{relation.target.strip()}"
        ),
        f"origin: {intent.origin.strip()}",
        "",
        "## Evidence links",
        *_bullet_lines(evidence_links),
        "",
        f"outcome: {intent.outcome.strip()}",
        f"method: {intent.method.strip()}",
        f"observations: {intent.observations.strip()}",
        f"verification: {intent.verification.strip()}",
        "",
        "## Produced artifacts",
        *_bullet_lines(produced_artifacts),
        "",
        "## Limitations",
        *_bullet_lines(limitations),
        "",
        "## Remaining unknowns",
        *_bullet_lines(remaining_unknowns),
        "",
        (
            "requested-return-route: "
            f"{intent.requested_return_route.strip()}"
        ),
    ]
    return "\n".join(lines)


def return_to_write_intent(intent: ReturnIntent) -> WriteIntent:
    _validate_return(intent)
    converted = WriteIntent(
        operation=intent.operation,
        target_key=intent.target_key.strip(),
        item_kind=ProtocolItemKind.RETURN_ITEM,
        title=intent.title.strip(),
        body=_render_body(intent),
        intake_state=intent.intake_state,
        previous_intake_state=intent.previous_intake_state,
        return_kind=intent.return_kind,
        relations=(intent.source_relation,),
        correlation_id=intent.correlation_id.strip(),
        related_items=(intent.source_relation.target.strip(),),
        provider_id=intent.provider_id,
        expected_provider_state=intent.expected_provider_state,
    )
    validate_intent(converted)
    return converted
