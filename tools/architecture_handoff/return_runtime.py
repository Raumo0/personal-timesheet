from dataclasses import dataclass

from .github import GitHubReadAdapter
from .github_preflight import (
    return_correlation_plan,
    return_preflight_from_coverage,
)
from .github_write import GitHubWriteAdapter
from .models import CapabilityStatus, ResultCompleteness
from .preflight import (
    Candidate,
    PreflightResult,
    PreflightSourceKind,
    SnapshotCandidateSource,
    SourceApplicability,
    SourceDeclaration,
)
from .query_coordinator import QueryCoordinator
from .query_models import (
    AdvancedQuery,
    ContinuationPlan,
    ProviderCall,
    QueryPurpose,
)
from .registry import (
    RegistryConfig,
    StoreConfig,
    StoreRole,
    resolve_active_store,
)
from .return_items import ReturnIntent, return_to_write_intent
from .runtime_config import (
    QueryBudget,
    RuntimeConfig,
    resolve_query_budget,
)
from .write_coordinator import (
    CandidateDisposition,
    PreparedWrite,
    WriteAuthorization,
    WriteCoordinator,
    WriteReceipt,
    WriteTargetConfig,
)
from .write_models import (
    IntakeState,
    ReturnKind,
    TypedRelation,
    WriteIntent,
    WriteOperation,
)


@dataclass(frozen=True)
class ReturnRequest:
    store_key: str
    operation: WriteOperation
    title: str
    return_kind: ReturnKind
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
    disposition: CandidateDisposition
    disposition_reason: str | None = None
    provider_id: str | None = None
    expected_provider_state: str | None = None


@dataclass(frozen=True)
class ReturnPreparation:
    request: ReturnRequest
    store: StoreConfig
    budget: QueryBudget
    intent: WriteIntent
    fast_search: PreflightResult | None
    fallback: PreflightResult | None
    candidates: tuple[Candidate, ...]
    limitations: tuple[str, ...]
    prepared: PreparedWrite | None
    blocked_reason: str | None
    provider_write_calls: tuple[str, ...]
    coordinator: WriteCoordinator | None


def _return_intent(request: ReturnRequest) -> WriteIntent:
    if not isinstance(request, ReturnRequest):
        raise ValueError("request must be a ReturnRequest")
    if not isinstance(request.disposition, CandidateDisposition):
        raise ValueError(
            "disposition must be a CandidateDisposition"
        )
    if request.operation is WriteOperation.CREATE:
        intake_state = IntakeState.PENDING
        previous_intake_state = None
    elif request.operation is WriteOperation.UPDATE:
        intake_state = IntakeState.HANDLED
        previous_intake_state = IntakeState.PENDING
    else:
        raise ValueError("operation must be a WriteOperation")
    return return_to_write_intent(
        ReturnIntent(
            operation=request.operation,
            target_key=request.store_key,
            title=request.title,
            return_kind=request.return_kind,
            intake_state=intake_state,
            previous_intake_state=previous_intake_state,
            correlation_id=request.correlation_id,
            source_relation=request.source_relation,
            origin=request.origin,
            evidence_links=request.evidence_links,
            outcome=request.outcome,
            method=request.method,
            observations=request.observations,
            verification=request.verification,
            produced_artifacts=request.produced_artifacts,
            limitations=request.limitations,
            remaining_unknowns=request.remaining_unknowns,
            requested_return_route=request.requested_return_route,
            provider_id=request.provider_id,
            expected_provider_state=request.expected_provider_state,
        )
    )


def _candidate_from_hit(hit) -> Candidate:
    return Candidate(
        source_kind=PreflightSourceKind.RETURN_INTAKE,
        provider_qualified_id=hit.item.provider_qualified_id,
        title=hit.item.title,
        status=hit.item.status,
        updated=hit.item.updated,
        url=hit.item.url,
    )


def _fast_search(
    adapter: GitHubReadAdapter,
    intent: WriteIntent,
    budget: QueryBudget,
) -> PreflightResult:
    query = AdvancedQuery(
        purpose=QueryPurpose.CORRELATION,
        logical_target=intent.target_key,
        correlation_id=intent.correlation_id,
        limit=budget.page_size,
    )
    page = adapter.query_page(query)
    expected_labels = {
        f"return-kind:{intent.return_kind.value}",
        f"intake-state:{IntakeState.PENDING.value}",
    }
    candidates = tuple(
        _candidate_from_hit(hit)
        for hit in page.hits
        if (
            "correlation-id" in hit.matched_signals
            and expected_labels.issubset(hit.item.labels)
        )
    )
    plan = ContinuationPlan(
        query=query,
        max_pages=1,
        max_items=budget.page_size,
    )
    calls = (
        ProviderCall(
            purpose=page.purpose,
            cursor=None,
            searched_scopes=page.searched_scopes,
            provider_record_count=(
                len(page.hits)
                if page.provider_record_count is None
                else page.provider_record_count
            ),
        ),
    )
    return PreflightResult(
        source_kind=PreflightSourceKind.RETURN_INTAKE,
        capability=page.capability,
        completeness=page.completeness,
        searched_scopes=page.searched_scopes,
        candidates=candidates,
        next_cursor=page.next_cursor,
        limitations=page.limitations,
        plan=plan,
        calls=calls,
    )


def _blocked(
    *,
    request: ReturnRequest,
    store: StoreConfig,
    budget: QueryBudget,
    intent: WriteIntent,
    fast_search: PreflightResult | None,
    fallback: PreflightResult | None,
    candidates: tuple[Candidate, ...],
    limitations: tuple[str, ...],
    reason: str,
) -> ReturnPreparation:
    return ReturnPreparation(
        request=request,
        store=store,
        budget=budget,
        intent=intent,
        fast_search=fast_search,
        fallback=fallback,
        candidates=candidates,
        limitations=limitations,
        prepared=None,
        blocked_reason=reason,
        provider_write_calls=(),
        coordinator=None,
    )


def _candidate_requires_stop(
    request: ReturnRequest,
    candidates: tuple[Candidate, ...],
) -> bool:
    return bool(candidates) and not (
        request.disposition is CandidateDisposition.CREATE_DISTINCT
        and isinstance(request.disposition_reason, str)
        and bool(request.disposition_reason.strip())
    )


def prepare_return(
    *,
    request: ReturnRequest,
    registry: RegistryConfig,
    runtime: RuntimeConfig,
    transport,
    page_size: int | None = None,
    max_pages: int | None = None,
    max_items: int | None = None,
) -> ReturnPreparation:
    if not isinstance(registry, RegistryConfig):
        raise ValueError("registry must be a RegistryConfig")
    if not isinstance(runtime, RuntimeConfig):
        raise ValueError("runtime must be a RuntimeConfig")
    store = resolve_active_store(
        registry.stores,
        request.store_key,
        StoreRole.DOCUMENTATION_INTAKE,
    )
    if store.provider != "github":
        raise ValueError(
            f"provider is not enabled for Return writes: {store.provider}"
        )
    budget = resolve_query_budget(
        runtime,
        "return_correlation_fallback",
        page_size=page_size,
        max_pages=max_pages,
        max_items=max_items,
    )
    intent = _return_intent(request)
    read_adapter = GitHubReadAdapter(
        store.repository,
        transport,
        logical_target=store.key,
    )
    write_adapter = GitHubWriteAdapter(store, transport)

    fast_search = None
    fallback = None
    candidates: tuple[Candidate, ...] = ()
    limitations: tuple[str, ...] = ()
    declarations: tuple[SourceDeclaration, ...] = ()
    sources = ()

    if request.operation is WriteOperation.CREATE:
        fast_search = _fast_search(read_adapter, intent, budget)
        candidates = fast_search.candidates
        limitations = fast_search.limitations
        if _candidate_requires_stop(request, candidates):
            return _blocked(
                request=request,
                store=store,
                budget=budget,
                intent=intent,
                fast_search=fast_search,
                fallback=None,
                candidates=candidates,
                limitations=limitations,
                reason="verified correlation candidate requires disposition",
            )

        coverage = QueryCoordinator(read_adapter).execute(
            return_correlation_plan(intent, budget)
        )
        fallback = return_preflight_from_coverage(coverage)
        candidates = fallback.candidates
        limitations = tuple(
            dict.fromkeys(
                fast_search.limitations + fallback.limitations
            )
        )
        if (
            fallback.capability is not CapabilityStatus.SUPPORTED
            or fallback.completeness
            is not ResultCompleteness.COMPLETE
        ):
            return _blocked(
                request=request,
                store=store,
                budget=budget,
                intent=intent,
                fast_search=fast_search,
                fallback=fallback,
                candidates=candidates,
                limitations=limitations,
                reason="Return correlation fallback coverage is partial",
            )
        if _candidate_requires_stop(request, candidates):
            return _blocked(
                request=request,
                store=store,
                budget=budget,
                intent=intent,
                fast_search=fast_search,
                fallback=fallback,
                candidates=candidates,
                limitations=limitations,
                reason="verified correlation candidate requires disposition",
            )
        declarations = (
            SourceDeclaration(
                kind=PreflightSourceKind.RETURN_INTAKE,
                applicability=SourceApplicability.ENABLED,
            ),
        )
        sources = (
            SnapshotCandidateSource(
                target=store,
                result=fallback,
            ),
        )

    coordinator = WriteCoordinator(
        WriteTargetConfig(
            target=store,
            declarations=declarations,
        ),
        write_adapter,
        sources,
        preflight_budget=budget,
    )
    prepared = coordinator.prepare(
        intent,
        request.disposition,
        request.disposition_reason,
    )
    return ReturnPreparation(
        request=request,
        store=store,
        budget=budget,
        intent=intent,
        fast_search=fast_search,
        fallback=fallback,
        candidates=candidates,
        limitations=limitations,
        prepared=prepared,
        blocked_reason=None,
        provider_write_calls=(),
        coordinator=coordinator,
    )


def execute_return(
    *,
    request: ReturnRequest,
    expected_fingerprint: str,
    approval_reference: str,
    registry: RegistryConfig,
    runtime: RuntimeConfig,
    transport,
    page_size: int | None = None,
    max_pages: int | None = None,
    max_items: int | None = None,
) -> WriteReceipt:
    preparation = prepare_return(
        request=request,
        registry=registry,
        runtime=runtime,
        transport=transport,
        page_size=page_size,
        max_pages=max_pages,
        max_items=max_items,
    )
    if preparation.prepared is None or preparation.coordinator is None:
        raise ValueError("Return preparation is blocked")
    if preparation.prepared.fingerprint != expected_fingerprint:
        raise ValueError("prepared fingerprint changed")
    return preparation.coordinator.execute(
        preparation.prepared,
        WriteAuthorization(
            fingerprint=expected_fingerprint,
            approval_reference=approval_reference,
        ),
    )
