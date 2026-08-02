from dataclasses import dataclass, replace

from .adapter import AdapterBinding, AdvancedReadAdapter
from .models import CapabilityStatus, ResultCompleteness
from .protocol_metadata import MetadataState
from .query_models import (
    ContinuationPlan,
    ProviderCall,
    QueryCoverage,
    SearchHit,
)


_CAPABILITY_ORDER = {
    CapabilityStatus.UNSUPPORTED: 0,
    CapabilityStatus.PARTIAL: 1,
    CapabilityStatus.SUPPORTED: 2,
}
_COMPLETENESS_ORDER = {
    ResultCompleteness.UNSUPPORTED: 0,
    ResultCompleteness.PARTIAL: 1,
    ResultCompleteness.COMPLETE: 2,
}
_CURSOR_CONTINUATION_LIMITATION = (
    "additional provider page is available"
)


def weakest_capability(
    first: CapabilityStatus,
    second: CapabilityStatus,
) -> CapabilityStatus:
    if _CAPABILITY_ORDER[first] <= _CAPABILITY_ORDER[second]:
        return first
    return second


def weakest_completeness(
    first: ResultCompleteness,
    second: ResultCompleteness,
) -> ResultCompleteness:
    if _COMPLETENESS_ORDER[first] <= _COMPLETENESS_ORDER[second]:
        return first
    return second


def partial_coverage(
    plan: ContinuationPlan,
    capability: CapabilityStatus,
    completeness: ResultCompleteness,
    hits_by_id: dict[str, SearchHit],
    calls: list[ProviderCall],
    limitations: list[str],
    next_cursor: str | None = None,
) -> QueryCoverage:
    return QueryCoverage(
        plan=plan,
        capability=capability,
        completeness=weakest_completeness(
            completeness,
            ResultCompleteness.PARTIAL,
        ),
        hits=tuple(hits_by_id.values()),
        calls=tuple(calls),
        limitations=tuple(limitations),
        next_cursor=next_cursor,
    )


def completed_or_partial_coverage(
    plan: ContinuationPlan,
    capability: CapabilityStatus,
    hits_by_id: dict[str, SearchHit],
    calls: list[ProviderCall],
    limitations: list[str],
    completeness: ResultCompleteness,
) -> QueryCoverage:
    return QueryCoverage(
        plan=plan,
        capability=capability,
        completeness=weakest_completeness(
            ResultCompleteness.COMPLETE,
            completeness,
        ),
        hits=tuple(hits_by_id.values()),
        calls=tuple(calls),
        limitations=tuple(limitations),
    )


class QueryCoordinator:
    def __init__(self, adapter: AdvancedReadAdapter):
        self._adapter = adapter
        binding = getattr(adapter, "binding", None)
        if binding is not None and not isinstance(binding, AdapterBinding):
            raise ValueError("advanced adapter binding is invalid")
        self._binding = binding

    @property
    def binding(self) -> AdapterBinding | None:
        return self._binding

    def execute(self, plan: ContinuationPlan) -> QueryCoverage:
        query = plan.query
        hits_by_id: dict[str, SearchHit] = {}
        calls: list[ProviderCall] = []
        limitations: list[str] = []
        capability = CapabilityStatus.SUPPORTED
        completeness = ResultCompleteness.COMPLETE
        cursor: str | None = None
        provider_records_seen = 0
        pending_cursor_only_partial = False
        cursor_only_partial_seen = False

        for _page_number in range(plan.max_pages):
            remaining = plan.max_items - provider_records_seen
            if remaining <= 0:
                limitations.append(
                    "continuation plan item bound reached"
                )
                return partial_coverage(
                    plan,
                    capability,
                    completeness,
                    hits_by_id,
                    calls,
                    limitations,
                    cursor,
                )
            page_query = replace(
                query,
                cursor=cursor,
                limit=min(query.limit, remaining),
            )
            page = self._adapter.query_page(page_query)
            provider_record_count = (
                len(page.hits)
                if page.provider_record_count is None
                else page.provider_record_count
            )
            if pending_cursor_only_partial:
                limitations.pop()
                pending_cursor_only_partial = False
            calls.append(
                ProviderCall(
                    purpose=page.purpose,
                    cursor=cursor,
                    searched_scopes=page.searched_scopes,
                    provider_record_count=provider_record_count,
                )
            )
            provider_records_seen += provider_record_count
            capability = weakest_capability(capability, page.capability)
            limitations.extend(page.limitations)
            cursor_only_partial = (
                page.completeness is ResultCompleteness.PARTIAL
                and page.next_cursor is not None
                and page.limitations
                == (_CURSOR_CONTINUATION_LIMITATION,)
            )
            if cursor_only_partial:
                pending_cursor_only_partial = True
                cursor_only_partial_seen = True
            else:
                completeness = weakest_completeness(
                    completeness,
                    page.completeness,
                )
            for hit in page.hits[:remaining]:
                identity = hit.item.provider_qualified_id
                if identity in hits_by_id:
                    continue
                hits_by_id[identity] = hit
            cursor = page.next_cursor
            if provider_record_count > remaining:
                limitations.append(
                    "continuation plan item bound reached"
                )
                return partial_coverage(
                    plan,
                    capability,
                    completeness,
                    hits_by_id,
                    calls,
                    limitations,
                    cursor,
                )
            if cursor is None:
                if cursor_only_partial_seen and limitations:
                    completeness = weakest_completeness(
                        completeness,
                        ResultCompleteness.PARTIAL,
                    )
                return completed_or_partial_coverage(
                    plan,
                    capability,
                    hits_by_id,
                    calls,
                    limitations,
                    completeness,
                )
            if provider_records_seen >= plan.max_items:
                limitations.append(
                    "continuation plan item bound reached"
                )
                return partial_coverage(
                    plan,
                    capability,
                    completeness,
                    hits_by_id,
                    calls,
                    limitations,
                    cursor,
                )

        limitations.append("continuation plan page bound reached")
        return partial_coverage(
            plan,
            capability,
            completeness,
            hits_by_id,
            calls,
            limitations,
            cursor,
        )


@dataclass(frozen=True)
class CorrelationNode:
    provider_qualified_id: str
    relation_targets: tuple[str, ...]


@dataclass(frozen=True)
class CorrelationView:
    correlation_id: str
    nodes: tuple[CorrelationNode, ...]
    unresolved_targets: tuple[str, ...]
    completeness: ResultCompleteness
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class StaleRevisionEntry:
    provider_qualified_id: str
    observed_revision: str | None
    classification: str


@dataclass(frozen=True)
class StaleRevisionReport:
    source_reference: str
    current_revision: str
    entries: tuple[StaleRevisionEntry, ...]
    completeness: ResultCompleteness
    limitations: tuple[str, ...]


def _metadata_limitation(hit: SearchHit) -> str:
    identity = hit.item.provider_qualified_id
    if hit.metadata_limitation is not None:
        return f"{identity}: {hit.metadata_limitation}"
    if hit.metadata_state is MetadataState.MISSING:
        return f"{identity}: versioned protocol metadata is missing"
    return f"{identity}: protocol metadata is malformed"


def _partial_evidence(
    completeness: ResultCompleteness,
) -> ResultCompleteness:
    return weakest_completeness(
        completeness,
        ResultCompleteness.PARTIAL,
    )


def build_correlation_view(
    coverage: QueryCoverage,
    correlation_id: str,
) -> CorrelationView:
    nodes = []
    limitations = list(coverage.limitations)
    completeness = coverage.completeness

    for hit in coverage.hits:
        if (
            hit.metadata_state is not MetadataState.VERIFIED
            or hit.protocol_metadata is None
        ):
            limitations.append(_metadata_limitation(hit))
            completeness = _partial_evidence(completeness)
            continue
        if hit.protocol_metadata.correlation_id != correlation_id:
            continue
        nodes.append(
            CorrelationNode(
                provider_qualified_id=hit.item.provider_qualified_id,
                relation_targets=tuple(
                    relation.target
                    for relation in hit.protocol_metadata.relations
                ),
            )
        )

    resolved_identities = {
        node.provider_qualified_id
        for node in nodes
    }
    unresolved_targets = []
    seen_targets = set()
    for node in nodes:
        for target in node.relation_targets:
            if (
                target in resolved_identities
                or target in seen_targets
            ):
                continue
            seen_targets.add(target)
            unresolved_targets.append(target)

    return CorrelationView(
        correlation_id=correlation_id,
        nodes=tuple(nodes),
        unresolved_targets=tuple(unresolved_targets),
        completeness=completeness,
        limitations=tuple(limitations),
    )


def classify_stale_revisions(
    coverage: QueryCoverage,
    source_reference: str,
    current_revision: str,
) -> StaleRevisionReport:
    entries = []
    limitations = list(coverage.limitations)
    completeness = coverage.completeness

    for hit in coverage.hits:
        identity = hit.item.provider_qualified_id
        if hit.metadata_state is MetadataState.MISSING:
            limitations.append(_metadata_limitation(hit))
            completeness = _partial_evidence(completeness)
            continue
        if (
            hit.metadata_state is MetadataState.MALFORMED
            or hit.protocol_metadata is None
        ):
            entries.append(
                StaleRevisionEntry(
                    provider_qualified_id=identity,
                    observed_revision=None,
                    classification="malformed-metadata",
                )
            )
            limitations.append(_metadata_limitation(hit))
            completeness = _partial_evidence(completeness)
            continue

        for relation in hit.protocol_metadata.relations:
            if relation.target != source_reference:
                continue
            if relation.revision is None:
                classification = "missing-revision"
                limitations.append(
                    f"{identity}: revision is missing for "
                    f"{source_reference}"
                )
                completeness = _partial_evidence(completeness)
            elif relation.revision == current_revision:
                classification = "current"
            else:
                classification = "stale"
            entries.append(
                StaleRevisionEntry(
                    provider_qualified_id=identity,
                    observed_revision=relation.revision,
                    classification=classification,
                )
            )

    return StaleRevisionReport(
        source_reference=source_reference,
        current_revision=current_revision,
        entries=tuple(entries),
        completeness=completeness,
        limitations=tuple(limitations),
    )
