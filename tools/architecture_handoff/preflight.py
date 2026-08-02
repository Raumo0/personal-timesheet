from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .models import CapabilityStatus, ResultCompleteness
from .query_models import (
    ContinuationPlan,
    LaneRequirement,
    ProviderCall,
    QueryPurpose,
)
from .registry import ProviderEndpointConfig
from .write_models import (
    ProtocolItemKind,
    WriteIntent,
    WriteOperation,
    validate_intent,
)


class PreflightSourceKind(str, Enum):
    NATIVE_WORK = "native-work"
    OPENSPEC = "openspec"
    DELIVERY = "delivery"
    RETURN_INTAKE = "return-intake"
    SIMILARITY = "similarity"


class SourceApplicability(str, Enum):
    ENABLED = "enabled"
    NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True)
class SourceDeclaration:
    kind: PreflightSourceKind
    applicability: SourceApplicability
    reason: str | None = None


@dataclass(frozen=True)
class Candidate:
    source_kind: PreflightSourceKind
    provider_qualified_id: str
    title: str
    status: str
    updated: str
    url: str


@dataclass(frozen=True)
class PreflightResult:
    source_kind: PreflightSourceKind
    capability: CapabilityStatus
    completeness: ResultCompleteness
    searched_scopes: tuple[str, ...]
    candidates: tuple[Candidate, ...] = ()
    next_cursor: str | None = None
    limitations: tuple[str, ...] = ()
    plan: ContinuationPlan | None = None
    calls: tuple[ProviderCall, ...] = ()


class CandidateSource(Protocol):
    kind: PreflightSourceKind
    target: ProviderEndpointConfig

    def query(
        self,
        intent: WriteIntent,
        limit: int,
    ) -> PreflightResult:
        ...


@dataclass(frozen=True)
class SnapshotCandidateSource:
    target: ProviderEndpointConfig
    result: PreflightResult

    @property
    def kind(self) -> PreflightSourceKind:
        return self.result.source_kind

    def query(
        self,
        intent: WriteIntent,
        limit: int,
    ) -> PreflightResult:
        validate_intent(intent)
        if intent.target_key != self.target.key:
            raise ValueError(
                "snapshot target does not match write intent"
            )
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 100
        ):
            raise ValueError("limit must be between 1 and 100")
        _validate_result(self.result, self.kind)
        return self.result


@dataclass(frozen=True)
class CandidateLane:
    name: str
    requirement: LaneRequirement
    source: CandidateSource


@dataclass(frozen=True)
class CandidateLaneResult:
    name: str
    requirement: LaneRequirement
    result: PreflightResult


@dataclass(frozen=True)
class PreflightBundle:
    declarations: tuple[SourceDeclaration, ...]
    results: tuple[PreflightResult, ...]
    candidate_lanes: tuple[CandidateLaneResult, ...] = ()

    @property
    def advisory_results(self) -> tuple[PreflightResult, ...]:
        return tuple(
            lane.result
            for lane in self.candidate_lanes
            if lane.requirement is LaneRequirement.ADVISORY
        )


OUTBOUND_SOURCE_ORDER = (
    PreflightSourceKind.NATIVE_WORK,
    PreflightSourceKind.OPENSPEC,
    PreflightSourceKind.DELIVERY,
)
RETURN_SOURCE_ORDER = (PreflightSourceKind.RETURN_INTAKE,)
_CANDIDATE_LANE_PURPOSES = {
    PreflightSourceKind.NATIVE_WORK: QueryPurpose.SOURCE_TRACEABILITY,
    PreflightSourceKind.RETURN_INTAKE: QueryPurpose.CORRELATION,
    PreflightSourceKind.SIMILARITY: QueryPurpose.SIMILARITY,
}


def _required_sources(intent: WriteIntent) -> tuple[PreflightSourceKind, ...]:
    if intent.item_kind is ProtocolItemKind.RETURN_ITEM:
        if intent.operation is WriteOperation.UPDATE:
            return ()
        return RETURN_SOURCE_ORDER
    return OUTBOUND_SOURCE_ORDER


def _declaration_map(
    declarations: tuple[SourceDeclaration, ...],
) -> dict[PreflightSourceKind, SourceDeclaration]:
    declared = {}
    for declaration in declarations:
        if not isinstance(declaration, SourceDeclaration):
            raise ValueError(
                "declarations must contain SourceDeclaration values"
            )
        if not isinstance(declaration.kind, PreflightSourceKind):
            raise ValueError("source declaration kind is invalid")
        if not isinstance(
            declaration.applicability,
            SourceApplicability,
        ):
            raise ValueError("source applicability is invalid")
        if declaration.kind in declared:
            raise ValueError(
                f"duplicate source declaration: {declaration.kind.value}"
            )
        if (
            declaration.applicability
            is SourceApplicability.NOT_APPLICABLE
            and (
                not isinstance(declaration.reason, str)
                or not declaration.reason.strip()
            )
        ):
            raise ValueError(
                "not-applicable source requires a reason: "
                f"{declaration.kind.value}"
            )
        declared[declaration.kind] = declaration
    return declared


def _source_map(
    sources: tuple[CandidateSource, ...],
) -> dict[PreflightSourceKind, CandidateSource]:
    mapped = {}
    for source in sources:
        kind = getattr(source, "kind", None)
        if not isinstance(kind, PreflightSourceKind):
            raise ValueError("candidate source kind is invalid")
        if kind in mapped:
            raise ValueError(f"duplicate candidate source: {kind.value}")
        mapped[kind] = source
    return mapped


def _require_non_empty(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _validate_result(
    result: PreflightResult,
    expected_kind: PreflightSourceKind,
) -> None:
    if not isinstance(result.capability, CapabilityStatus):
        raise ValueError("source capability is invalid")
    if not isinstance(result.completeness, ResultCompleteness):
        raise ValueError("source completeness is invalid")
    if not isinstance(result.searched_scopes, tuple):
        raise ValueError("searched_scopes must be a tuple")
    if (
        not result.searched_scopes
        and result.capability is not CapabilityStatus.UNSUPPORTED
    ):
        raise ValueError("searched_scopes must be a non-empty tuple")
    for scope in result.searched_scopes:
        _require_non_empty(scope, "searched scope")
    if not isinstance(result.candidates, tuple):
        raise ValueError("candidates must be a tuple")
    candidate_ids = set()
    for candidate in result.candidates:
        if not isinstance(candidate, Candidate):
            raise ValueError("candidate result is invalid")
        if candidate.source_kind is not expected_kind:
            raise ValueError("candidate source kind mismatch")
        for value, field in (
            (candidate.provider_qualified_id, "candidate identity"),
            (candidate.title, "candidate title"),
            (candidate.status, "candidate status"),
            (candidate.updated, "candidate updated state"),
            (candidate.url, "candidate URL"),
        ):
            _require_non_empty(value, field)
        if candidate.provider_qualified_id in candidate_ids:
            raise ValueError("candidate identity is duplicated")
        candidate_ids.add(candidate.provider_qualified_id)
    if not isinstance(result.limitations, tuple):
        raise ValueError("limitations must be a tuple")
    for limitation in result.limitations:
        _require_non_empty(limitation, "limitation")
    if result.next_cursor is not None:
        _require_non_empty(result.next_cursor, "next_cursor")
    if (
        result.completeness is ResultCompleteness.COMPLETE
        and result.next_cursor is not None
    ):
        raise ValueError("complete source must not return next_cursor")
    if result.plan is not None and not isinstance(
        result.plan,
        ContinuationPlan,
    ):
        raise ValueError("query plan is invalid")
    if not isinstance(result.calls, tuple) or any(
        not isinstance(call, ProviderCall) for call in result.calls
    ):
        raise ValueError("provider calls are invalid")
    if result.plan is None and result.calls:
        raise ValueError("provider calls require a query plan")


def _validate_candidate_lane_plan(
    intent: WriteIntent,
    lane: CandidateLane,
    result: PreflightResult,
) -> None:
    plan = result.plan
    if plan is None:
        is_empty_unsupported = (
            result.capability is CapabilityStatus.UNSUPPORTED
            and result.completeness is ResultCompleteness.UNSUPPORTED
            and not result.searched_scopes
            and not result.candidates
            and result.next_cursor is None
            and not result.calls
        )
        if not is_empty_unsupported:
            raise ValueError(
                "candidate lane evidence requires an explicit query plan"
            )
        if not result.limitations:
            raise ValueError(
                "planless unsupported candidate lane requires a limitation"
            )
        return

    query = plan.query
    if query.requirement is not lane.requirement:
        raise ValueError(
            "candidate lane requirement does not match query plan"
        )
    if query.logical_target != intent.target_key:
        raise ValueError(
            "candidate lane query target does not match write intent"
        )
    expected_purpose = _CANDIDATE_LANE_PURPOSES.get(result.source_kind)
    if query.purpose is not expected_purpose:
        raise ValueError(
            "candidate lane source kind does not match query purpose"
        )
    if not result.calls:
        if result.capability is CapabilityStatus.SUPPORTED:
            raise ValueError(
                "zero-call candidate lane must not report supported "
                "capability"
            )
        if result.completeness is ResultCompleteness.COMPLETE:
            raise ValueError(
                "zero-call candidate lane must not report complete evidence"
            )
        if result.candidates:
            raise ValueError(
                "zero-call candidate lane must not return candidates"
            )
        if result.next_cursor is not None:
            raise ValueError(
                "candidate lane next_cursor requires a provider call"
            )
        if not result.limitations:
            raise ValueError(
                "zero-call candidate lane requires a limitation"
            )
        return
    if any(call.purpose is not query.purpose for call in result.calls):
        raise ValueError(
            "candidate lane provider call purpose does not match query plan"
        )
    if len(result.calls) > plan.max_pages:
        raise ValueError(
            "candidate lane provider calls exceed query plan page bound"
        )
    if len(result.candidates) > plan.max_items:
        raise ValueError(
            "candidate lane candidates exceed query plan item bound"
        )
    if result.calls and result.calls[0].cursor is not None:
        raise ValueError(
            "candidate lane coverage must start without a cursor"
        )
    for index, call in enumerate(result.calls):
        if index > 0 and call.cursor is None:
            raise ValueError(
                "candidate lane continuation call requires a cursor"
            )
        if call.cursor is not None and (
            not call.cursor.isdigit() or int(call.cursor) < 1
        ):
            raise ValueError(
                "candidate lane provider call cursor is invalid"
            )
    if result.next_cursor is not None:
        if (
            not result.next_cursor.isdigit()
            or int(result.next_cursor) < 1
        ):
            raise ValueError("candidate lane next_cursor is invalid")
        if not result.calls:
            raise ValueError(
                "candidate lane next_cursor requires a provider call"
            )
        if result.completeness is not ResultCompleteness.PARTIAL:
            raise ValueError(
                "candidate lane next_cursor requires partial completeness"
            )
        if result.next_cursor in {
            call.cursor for call in result.calls if call.cursor is not None
        }:
            raise ValueError(
                "candidate lane next_cursor must identify unqueried coverage"
            )
    if result.calls:
        call_scopes = tuple(
            scope
            for call in result.calls
            for scope in call.searched_scopes
        )
        if result.searched_scopes != call_scopes:
            raise ValueError(
                "candidate lane searched scopes do not match provider calls"
            )


def _candidate_lane_results(
    intent: WriteIntent,
    candidate_lanes: tuple[CandidateLane, ...],
    limit: int,
) -> tuple[CandidateLaneResult, ...]:
    names = set()
    results = []
    incomplete_required = []
    for lane in candidate_lanes:
        if not isinstance(lane, CandidateLane):
            raise ValueError(
                "candidate_lanes must contain CandidateLane values"
            )
        _require_non_empty(lane.name, "candidate lane name")
        if lane.name in names:
            raise ValueError(f"duplicate candidate lane: {lane.name}")
        names.add(lane.name)
        if not isinstance(lane.requirement, LaneRequirement):
            raise ValueError("candidate lane requirement is invalid")
        kind = getattr(lane.source, "kind", None)
        if not isinstance(kind, PreflightSourceKind):
            raise ValueError("candidate lane source kind is invalid")
        result = lane.source.query(intent, limit)
        if not isinstance(result, PreflightResult):
            raise ValueError(
                f"candidate lane {lane.name} returned an invalid result"
            )
        if result.source_kind is not kind:
            raise ValueError(
                "candidate lane source kind mismatch: "
                f"expected {kind.value}, got {result.source_kind.value}"
            )
        _validate_result(result, kind)
        _validate_candidate_lane_plan(intent, lane, result)
        results.append(
            CandidateLaneResult(
                name=lane.name,
                requirement=lane.requirement,
                result=result,
            )
        )
        if (
            lane.requirement is LaneRequirement.REQUIRED
            and (
                result.capability is not CapabilityStatus.SUPPORTED
                or result.completeness
                is not ResultCompleteness.COMPLETE
            )
        ):
            incomplete_required.append(lane.name)
    if incomplete_required:
        raise ValueError(
            "required candidate lane did not return complete: "
            + ", ".join(incomplete_required)
        )
    return tuple(results)


def run_preflight(
    intent: WriteIntent,
    declarations: tuple[SourceDeclaration, ...],
    sources: tuple[CandidateSource, ...],
    *,
    limit: int = 100,
    candidate_lanes: tuple[CandidateLane, ...] = (),
) -> PreflightBundle:
    validate_intent(intent)
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 100
    ):
        raise ValueError("limit must be between 1 and 100")

    if not isinstance(candidate_lanes, tuple):
        raise ValueError("candidate_lanes must be a tuple")
    if any(
        getattr(source, "kind", None) is PreflightSourceKind.SIMILARITY
        for source in sources
    ):
        raise ValueError(
            "similarity source requires an explicit candidate lane"
        )

    required = _required_sources(intent)
    declared = _declaration_map(declarations)
    if set(declared) != set(required):
        expected = ", ".join(kind.value for kind in required)
        raise ValueError(f"required source declarations: {expected}")
    available = _source_map(sources)

    results = []
    for kind in required:
        declaration = declared[kind]
        if (
            declaration.applicability
            is SourceApplicability.NOT_APPLICABLE
        ):
            continue
        candidate_source = available.get(kind)
        if candidate_source is None:
            raise ValueError(f"enabled source is unavailable: {kind.value}")
        result = candidate_source.query(intent, limit)
        if not isinstance(result, PreflightResult):
            raise ValueError(
                f"source {kind.value} returned an invalid result"
            )
        if result.source_kind is not kind:
            raise ValueError(
                f"source kind mismatch: expected {kind.value}, "
                f"got {result.source_kind.value}"
            )
        _validate_result(result, kind)
        if (
            result.capability is not CapabilityStatus.SUPPORTED
            or result.completeness is not ResultCompleteness.COMPLETE
        ):
            raise ValueError(
                f"enabled source {kind.value} did not return complete"
            )
        results.append(result)

    lane_results = _candidate_lane_results(
        intent,
        candidate_lanes,
        limit,
    )
    return PreflightBundle(
        declarations=tuple(declared[kind] for kind in required),
        results=tuple(results),
        candidate_lanes=lane_results,
    )
