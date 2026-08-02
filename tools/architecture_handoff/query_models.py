from dataclasses import dataclass
from enum import Enum

from .models import (
    CapabilityStatus,
    ResultCompleteness,
    WorkItemSummary,
    WorkRoute,
)
from .protocol_metadata import MetadataState, ProtocolMetadata
from .write_models import IntakeState, ReturnKind


class QueryPurpose(str, Enum):
    INVENTORY = "inventory"
    SOURCE_TRACEABILITY = "source-traceability"
    LOGICAL_TARGET = "logical-target"
    CORRELATION = "correlation"
    RETURN_INTAKE = "return-intake"
    RETURN_CORRELATION = "return-correlation"
    STALE_REVISION = "stale-revision"
    SIMILARITY = "similarity"
    DUPLICATE_PREFLIGHT = "duplicate-preflight"


class LaneRequirement(str, Enum):
    REQUIRED = "required"
    ADVISORY = "advisory"


class SimilarityMode(str, Enum):
    HYBRID = "hybrid"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class AdvancedQuery:
    purpose: QueryPurpose
    logical_target: str
    requirement: LaneRequirement = LaneRequirement.REQUIRED
    active_only: bool = True
    routes: tuple[WorkRoute, ...] = ()
    source_reference: str | None = None
    current_revision: str | None = None
    correlation_id: str | None = None
    intake_state: IntakeState | None = None
    return_kind: ReturnKind | None = None
    capability: str | None = None
    expected_outcome: str | None = None
    similarity_mode: SimilarityMode = SimilarityMode.HYBRID
    cursor: str | None = None
    limit: int = 50

    def __post_init__(self) -> None:
        validate_advanced_query(self)

    @classmethod
    def similarity(
        cls,
        *,
        logical_target: str,
        capability: str | None,
        expected_outcome: str | None,
        similarity_mode: SimilarityMode = SimilarityMode.HYBRID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> "AdvancedQuery":
        return cls(
            purpose=QueryPurpose.SIMILARITY,
            logical_target=logical_target,
            requirement=LaneRequirement.ADVISORY,
            capability=capability,
            expected_outcome=expected_outcome,
            similarity_mode=similarity_mode,
            cursor=cursor,
            limit=limit,
        )


@dataclass(frozen=True)
class SearchHit:
    item: WorkItemSummary
    matched_signals: tuple[str, ...] = ()
    provider_rank: int | None = None
    metadata_state: MetadataState = MetadataState.MISSING
    protocol_metadata: ProtocolMetadata | None = None
    metadata_limitation: str | None = None


@dataclass(frozen=True)
class SearchPage:
    purpose: QueryPurpose
    capability: CapabilityStatus
    completeness: ResultCompleteness
    searched_scopes: tuple[str, ...]
    hits: tuple[SearchHit, ...] = ()
    next_cursor: str | None = None
    limitations: tuple[str, ...] = ()
    provider_record_count: int | None = None

    def __post_init__(self) -> None:
        if self.provider_record_count is None:
            return
        if (
            not isinstance(self.provider_record_count, int)
            or isinstance(self.provider_record_count, bool)
            or self.provider_record_count < len(self.hits)
        ):
            raise ValueError(
                "provider_record_count must be an integer no smaller "
                "than the normalized hit count"
            )


@dataclass(frozen=True)
class ContinuationPlan:
    query: AdvancedQuery
    max_pages: int
    max_items: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_pages, int)
            or isinstance(self.max_pages, bool)
            or self.max_pages < 1
        ):
            raise ValueError("max_pages must be a positive integer")
        if (
            not isinstance(self.max_items, int)
            or isinstance(self.max_items, bool)
            or self.max_items < 1
        ):
            raise ValueError("max_items must be a positive integer")
        if self.query.cursor is not None:
            raise ValueError("continuation plan query must start without cursor")


@dataclass(frozen=True)
class ProviderCall:
    purpose: QueryPurpose
    cursor: str | None
    searched_scopes: tuple[str, ...]
    provider_record_count: int = 0


@dataclass(frozen=True)
class QueryCoverage:
    plan: ContinuationPlan
    capability: CapabilityStatus
    completeness: ResultCompleteness
    hits: tuple[SearchHit, ...]
    calls: tuple[ProviderCall, ...]
    limitations: tuple[str, ...]
    next_cursor: str | None = None


_PURPOSE_FIELDS = {
    QueryPurpose.INVENTORY: frozenset(),
    QueryPurpose.SOURCE_TRACEABILITY: frozenset({"source_reference"}),
    QueryPurpose.LOGICAL_TARGET: frozenset(),
    QueryPurpose.CORRELATION: frozenset({"correlation_id"}),
    QueryPurpose.RETURN_INTAKE: frozenset({"intake_state", "return_kind"}),
    QueryPurpose.RETURN_CORRELATION: frozenset(
        {"correlation_id", "intake_state", "return_kind"}
    ),
    QueryPurpose.STALE_REVISION: frozenset(
        {"source_reference", "current_revision"}
    ),
    QueryPurpose.SIMILARITY: frozenset(
        {"capability", "expected_outcome", "similarity_mode"}
    ),
    QueryPurpose.DUPLICATE_PREFLIGHT: frozenset(),
}

_PURPOSE_REQUIRED_FIELDS = {
    QueryPurpose.SOURCE_TRACEABILITY: ("source_reference",),
    QueryPurpose.CORRELATION: ("correlation_id",),
    QueryPurpose.RETURN_INTAKE: ("intake_state",),
    QueryPurpose.RETURN_CORRELATION: (
        "correlation_id",
        "intake_state",
    ),
    QueryPurpose.STALE_REVISION: ("source_reference", "current_revision"),
}


def _require_non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _validate_logical_target(value: object) -> None:
    target = _require_non_empty_string(value, "logical_target")
    if any(character.isspace() for character in target) or ":" in target:
        raise ValueError(
            "logical_target must not contain provider syntax or "
            "whitespace-delimited qualifiers"
        )


def _validate_enum(value: object, enum_type: type[Enum], field: str) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(f"{field} must be a {enum_type.__name__}")


def validate_advanced_query(query: AdvancedQuery) -> None:
    if not isinstance(query, AdvancedQuery):
        raise ValueError("query must be an AdvancedQuery")
    _validate_enum(query.purpose, QueryPurpose, "purpose")
    _validate_enum(query.requirement, LaneRequirement, "requirement")
    _validate_enum(query.similarity_mode, SimilarityMode, "similarity_mode")
    _validate_logical_target(query.logical_target)

    if not isinstance(query.active_only, bool):
        raise ValueError("active_only must be a bool")
    if not isinstance(query.routes, tuple) or any(
        not isinstance(route, WorkRoute) for route in query.routes
    ):
        raise ValueError("routes must contain WorkRoute values")
    if (
        not isinstance(query.limit, int)
        or isinstance(query.limit, bool)
        or not 1 <= query.limit <= 100
    ):
        raise ValueError("limit must be between 1 and 100")
    if query.cursor is not None and (
        not isinstance(query.cursor, str)
        or not query.cursor.isdigit()
        or int(query.cursor) < 1
    ):
        raise ValueError("cursor must be a positive integer string")

    for field in (
        "source_reference",
        "current_revision",
        "correlation_id",
        "capability",
        "expected_outcome",
    ):
        value = getattr(query, field)
        if value is not None:
            _require_non_empty_string(value, field)
    if query.intake_state is not None:
        _validate_enum(query.intake_state, IntakeState, "intake_state")
    if query.return_kind is not None:
        _validate_enum(query.return_kind, ReturnKind, "return_kind")

    if query.purpose in {
        QueryPurpose.RETURN_INTAKE,
        QueryPurpose.RETURN_CORRELATION,
    } and query.routes:
        raise ValueError("routes are not valid for return-intake")

    for field in (
        "source_reference",
        "current_revision",
        "correlation_id",
        "intake_state",
        "return_kind",
        "capability",
        "expected_outcome",
    ):
        if (
            getattr(query, field) is not None
            and field not in _PURPOSE_FIELDS[query.purpose]
        ):
            raise ValueError(
                f"{field} is not valid for {query.purpose.value}"
            )
    if (
        query.purpose is not QueryPurpose.SIMILARITY
        and query.similarity_mode is not SimilarityMode.HYBRID
    ):
        raise ValueError(
            f"similarity_mode is not valid for {query.purpose.value}"
        )

    required_fields = _PURPOSE_REQUIRED_FIELDS.get(query.purpose, ())
    if any(getattr(query, field) is None for field in required_fields):
        required = " and ".join(required_fields)
        raise ValueError(f"{query.purpose.value} requires {required}")
    if query.purpose is QueryPurpose.SIMILARITY and not (
        query.capability or query.expected_outcome
    ):
        raise ValueError("similarity requires capability or expected_outcome")
