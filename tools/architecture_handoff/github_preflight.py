from typing import Callable, Mapping, Protocol
from urllib.parse import quote

from .adapter import AdapterBinding
from .github import (
    AdapterError,
    GitHubRateLimitError,
    validate_repository_name,
)
from .models import CapabilityStatus, ResultCompleteness
from .preflight import (
    Candidate,
    CandidateLane,
    PreflightResult,
    PreflightSourceKind,
)
from .query_coordinator import QueryCoordinator
from .query_models import (
    AdvancedQuery,
    ContinuationPlan,
    LaneRequirement,
    QueryCoverage,
    QueryPurpose,
    SearchHit,
)
from .registry import (
    ProviderEndpointConfig,
    StoreConfig,
    StoreRole,
    TargetConfig,
)
from .runtime_config import QueryBudget
from .write_models import ProtocolItemKind, WriteIntent, validate_intent


class GitHubPreflightTransport(Protocol):
    def get(
        self,
        path: str,
        params: Mapping[str, str],
    ) -> tuple[object, str | None]:
        ...


def _validate_github_endpoint(
    endpoint: ProviderEndpointConfig,
) -> ProviderEndpointConfig:
    if not isinstance(endpoint, (TargetConfig, StoreConfig)):
        raise AdapterError(
            "GitHub source requires a provider endpoint"
        )
    if endpoint.provider != "github":
        raise AdapterError("GitHub source requires provider github")
    if endpoint.routing_status != "active":
        raise AdapterError("GitHub source requires an active target")
    validate_repository_name(endpoint.repository)
    return endpoint


def _validate_github_target(target: TargetConfig) -> TargetConfig:
    if not isinstance(target, TargetConfig):
        raise AdapterError("GitHub source requires a TargetConfig")
    _validate_github_endpoint(target)
    return target


def _validate_github_intake_store(store: StoreConfig) -> StoreConfig:
    if (
        not isinstance(store, StoreConfig)
        or store.role is not StoreRole.DOCUMENTATION_INTAKE
    ):
        raise AdapterError(
            "GitHub return source requires a documentation-intake store"
        )
    _validate_github_endpoint(store)
    return store


def _require_records(payload: object, scope: str) -> list[object]:
    if not isinstance(payload, list):
        raise AdapterError(f"GitHub {scope} response must be a list")
    return payload


def _require_record(record: object, scope: str) -> dict[str, object]:
    if not isinstance(record, dict):
        raise AdapterError(f"GitHub {scope} item must be an object")
    return record


def _require_string(
    record: Mapping[str, object],
    field: str,
    scope: str,
) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise AdapterError(
            f"GitHub {scope} item requires string field {field}"
        )
    return value


def _require_positive_integer(
    record: Mapping[str, object],
    field: str,
    scope: str,
) -> int:
    value = record.get(field)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        raise AdapterError(
            f"GitHub {scope} item requires positive integer field {field}"
        )
    return value


def _issue_candidate(
    repository: str,
    record: object,
    source_kind: PreflightSourceKind,
) -> Candidate:
    item = _require_record(record, "issue")
    number = _require_positive_integer(item, "number", "issue")
    return Candidate(
        source_kind=source_kind,
        provider_qualified_id=f"github:{repository}#{number}",
        title=_require_string(item, "title", "issue"),
        status=_require_string(item, "state", "issue"),
        updated=_require_string(item, "updated_at", "issue"),
        url=_require_string(item, "html_url", "issue"),
    )


def _validate_limit(limit: int) -> None:
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= 100
    ):
        raise ValueError("limit must be between 1 and 100")


def native_work_plan(
    intent: WriteIntent,
    limit: int,
) -> ContinuationPlan:
    validate_intent(intent)
    _validate_limit(limit)
    if intent.item_kind is not ProtocolItemKind.WORK_ITEM:
        raise ValueError("native-work plan requires a work item")
    if len(intent.relations) != 1:
        raise ValueError(
            "native-work plan requires one accepted source"
        )
    return ContinuationPlan(
        query=AdvancedQuery(
            purpose=QueryPurpose.SOURCE_TRACEABILITY,
            logical_target=intent.target_key,
            active_only=False,
            routes=(intent.route,),
            source_reference=intent.relations[0].target,
            limit=limit,
        ),
        max_pages=1,
        max_items=limit,
    )


def native_work_plans(
    intent: WriteIntent,
    limit: int,
) -> tuple[ContinuationPlan, ...]:
    validate_intent(intent)
    _validate_limit(limit)
    if intent.item_kind is not ProtocolItemKind.WORK_ITEM:
        raise ValueError("native-work plans require a work item")
    return tuple(
        _native_work_plan_for_source(
            intent,
            limit,
            relation.target,
        )
        for relation in intent.relations
    )


def _native_work_plan_for_source(
    intent: WriteIntent,
    limit: int,
    source_reference: str,
) -> ContinuationPlan:
    validate_intent(intent)
    _validate_limit(limit)
    if intent.item_kind is not ProtocolItemKind.WORK_ITEM:
        raise ValueError("native-work plan requires a work item")
    if source_reference not in {
        relation.target for relation in intent.relations
    }:
        raise ValueError(
            "native-work plan source is not present in the write intent"
        )
    return ContinuationPlan(
        query=AdvancedQuery(
            purpose=QueryPurpose.SOURCE_TRACEABILITY,
            logical_target=intent.target_key,
            active_only=False,
            routes=(intent.route,),
            source_reference=source_reference,
            limit=limit,
        ),
        max_pages=1,
        max_items=limit,
    )


def return_intake_plan(
    intent: WriteIntent,
    limit: int,
) -> ContinuationPlan:
    validate_intent(intent)
    _validate_limit(limit)
    if intent.item_kind is not ProtocolItemKind.RETURN_ITEM:
        raise ValueError("return-intake plan requires a Return Item")
    return ContinuationPlan(
        query=AdvancedQuery(
            purpose=QueryPurpose.CORRELATION,
            logical_target=intent.target_key,
            active_only=False,
            correlation_id=intent.correlation_id,
            limit=limit,
        ),
        max_pages=1,
        max_items=limit,
    )


def return_correlation_plan(
    intent: WriteIntent,
    budget: QueryBudget,
) -> ContinuationPlan:
    validate_intent(intent)
    if not isinstance(budget, QueryBudget):
        raise ValueError("budget must be a QueryBudget")
    if intent.item_kind is not ProtocolItemKind.RETURN_ITEM:
        raise ValueError(
            "return-correlation plan requires a Return Item"
        )
    return ContinuationPlan(
        query=AdvancedQuery(
            purpose=QueryPurpose.RETURN_CORRELATION,
            logical_target=intent.target_key,
            correlation_id=intent.correlation_id,
            intake_state=intent.intake_state,
            return_kind=intent.return_kind,
            limit=budget.page_size,
        ),
        max_pages=budget.max_pages,
        max_items=budget.max_items,
    )


def return_preflight_from_coverage(
    coverage: QueryCoverage,
) -> PreflightResult:
    if not isinstance(coverage, QueryCoverage):
        raise ValueError("coverage must be QueryCoverage")
    if (
        coverage.plan.query.purpose
        is not QueryPurpose.RETURN_CORRELATION
    ):
        raise ValueError(
            "Return preflight requires return-correlation coverage"
        )
    candidates = tuple(
        Candidate(
            source_kind=PreflightSourceKind.RETURN_INTAKE,
            provider_qualified_id=hit.item.provider_qualified_id,
            title=hit.item.title,
            status=hit.item.status,
            updated=hit.item.updated,
            url=hit.item.url,
        )
        for hit in coverage.hits
        if "correlation-id" in hit.matched_signals
    )
    return PreflightResult(
        source_kind=PreflightSourceKind.RETURN_INTAKE,
        capability=coverage.capability,
        completeness=coverage.completeness,
        searched_scopes=tuple(
            scope
            for call in coverage.calls
            for scope in call.searched_scopes
        ),
        candidates=candidates,
        next_cursor=coverage.next_cursor,
        limitations=coverage.limitations,
        plan=coverage.plan,
        calls=coverage.calls,
    )


def advisory_similarity_plan(
    intent: WriteIntent,
    limit: int,
) -> ContinuationPlan:
    validate_intent(intent)
    _validate_limit(limit)
    if intent.item_kind is not ProtocolItemKind.WORK_ITEM:
        raise ValueError("similarity plan requires a work item")
    return ContinuationPlan(
        query=AdvancedQuery.similarity(
            logical_target=intent.target_key,
            capability=intent.capability,
            expected_outcome=intent.expected_outcome,
            limit=limit,
        ),
        max_pages=1,
        max_items=limit,
    )


class GitHubQueryCandidateSource:
    def __init__(
        self,
        target: ProviderEndpointConfig,
        coordinator: QueryCoordinator,
        plan_factory: Callable[[WriteIntent, int], ContinuationPlan],
        source_kind: PreflightSourceKind,
    ):
        self.target = _validate_github_endpoint(target)
        self._repository = validate_repository_name(target.repository)
        if not callable(plan_factory):
            raise ValueError("plan_factory must be callable")
        if not isinstance(source_kind, PreflightSourceKind):
            raise ValueError("source_kind must be a PreflightSourceKind")
        self.kind = source_kind
        expected_binding = AdapterBinding(
            provider="github",
            provider_scope=self._repository,
            logical_target=self.target.key,
        )
        if getattr(coordinator, "binding", None) != expected_binding:
            raise ValueError(
                "query coordinator binding does not match GitHub target"
            )
        self._coordinator = coordinator
        self._plan_factory = plan_factory

    def query(self, intent: WriteIntent, limit: int) -> PreflightResult:
        validate_intent(intent)
        _validate_limit(limit)
        if (
            self.kind is PreflightSourceKind.SIMILARITY
            and intent.capability is None
            and intent.expected_outcome is None
        ):
            return PreflightResult(
                source_kind=self.kind,
                capability=CapabilityStatus.UNSUPPORTED,
                completeness=ResultCompleteness.UNSUPPORTED,
                searched_scopes=(),
                limitations=(
                    "similarity candidate lane has no capability or "
                    "expected outcome; no advisory query was run",
                ),
            )
        plan = self._plan_factory(intent, limit)
        if not isinstance(plan, ContinuationPlan):
            raise ValueError("plan_factory must return a ContinuationPlan")
        if plan.query.logical_target != self.target.key:
            raise ValueError(
                "query plan logical target does not match source target"
            )
        expected_purpose = {
            PreflightSourceKind.NATIVE_WORK: (
                QueryPurpose.SOURCE_TRACEABILITY
            ),
            PreflightSourceKind.RETURN_INTAKE: (
                QueryPurpose.RETURN_CORRELATION
            ),
            PreflightSourceKind.SIMILARITY: QueryPurpose.SIMILARITY,
        }.get(self.kind)
        if plan.query.purpose is not expected_purpose:
            raise ValueError(
                "source kind does not match query purpose"
            )
        if (
            self.kind is not PreflightSourceKind.SIMILARITY
            and plan.query.requirement is not LaneRequirement.REQUIRED
        ):
            raise ValueError(
                "exact query plan must be required"
            )
        try:
            coverage = self._coordinator.execute(plan)
        except GitHubRateLimitError as error:
            retry = (
                f"; retry after {error.retry_after}"
                if error.retry_after is not None
                else ""
            )
            return PreflightResult(
                source_kind=self.kind,
                capability=CapabilityStatus.PARTIAL,
                completeness=ResultCompleteness.PARTIAL,
                searched_scopes=(
                    f"github:{self._repository}:"
                    f"{plan.query.purpose.value}:rate-limited",
                ),
                limitations=(
                    f"GitHub query was rate limited{retry}",
                ),
                plan=plan,
            )
        if not isinstance(coverage, QueryCoverage):
            raise ValueError(
                "query coordinator returned invalid coverage"
            )
        if coverage.plan != plan:
            raise ValueError(
                "query coverage plan does not match requested plan"
            )
        if any(
            call.purpose is not plan.query.purpose
            for call in coverage.calls
        ):
            raise ValueError(
                "provider call purpose does not match query plan"
            )
        repository_scope = f"github:{self._repository}:"
        for call in coverage.calls:
            if any(
                not scope.startswith(repository_scope)
                for scope in call.searched_scopes
            ):
                raise ValueError(
                    "query coverage scope is outside bound GitHub "
                    "repository"
                )
        candidates = []
        identity_prefix = f"github:{self._repository}#"
        for hit in coverage.hits:
            if not isinstance(hit, SearchHit):
                raise ValueError("query coverage hit is invalid")
            item = hit.item
            if not item.provider_qualified_id.startswith(identity_prefix):
                raise ValueError(
                    "candidate identity is outside bound GitHub repository"
                )
            candidates.append(
                Candidate(
                    source_kind=self.kind,
                    provider_qualified_id=item.provider_qualified_id,
                    title=item.title,
                    status=item.status,
                    updated=item.updated,
                    url=item.url,
                )
            )
        searched_scopes = tuple(
            scope
            for call in coverage.calls
            for scope in call.searched_scopes
        )
        if any(
            not scope.startswith(repository_scope)
            for scope in searched_scopes
        ):
            raise ValueError(
                "query result scope is outside bound GitHub repository"
            )
        return PreflightResult(
            source_kind=self.kind,
            capability=coverage.capability,
            completeness=coverage.completeness,
            searched_scopes=searched_scopes,
            candidates=tuple(candidates),
            next_cursor=coverage.next_cursor,
            limitations=coverage.limitations,
            plan=coverage.plan,
            calls=coverage.calls,
        )


def exact_source_candidate_lanes(
    target: TargetConfig,
    coordinator: QueryCoordinator,
    intent: WriteIntent,
) -> tuple[CandidateLane, ...]:
    validate_intent(intent)
    if intent.item_kind is not ProtocolItemKind.WORK_ITEM:
        raise ValueError("exact source lanes require a work item")

    lanes = []
    for index, relation in enumerate(intent.relations, start=1):
        source_reference = relation.target

        def plan_factory(
            candidate_intent: WriteIntent,
            limit: int,
            *,
            _source_reference: str = source_reference,
        ) -> ContinuationPlan:
            return _native_work_plan_for_source(
                candidate_intent,
                limit,
                _source_reference,
            )

        lanes.append(
            CandidateLane(
                name=f"exact-source-{index:02d}",
                requirement=LaneRequirement.REQUIRED,
                source=GitHubQueryCandidateSource(
                    target,
                    coordinator,
                    plan_factory,
                    PreflightSourceKind.NATIVE_WORK,
                ),
            )
        )
    return tuple(lanes)


class GitHubNativeCandidateSource:
    kind = PreflightSourceKind.NATIVE_WORK

    def __init__(
        self,
        target: TargetConfig,
        transport: GitHubPreflightTransport,
    ):
        self.target = _validate_github_target(target)
        self._repository = validate_repository_name(target.repository)
        self._transport = transport

    def query(self, intent: WriteIntent, limit: int) -> PreflightResult:
        validate_intent(intent)
        _validate_limit(limit)
        if intent.item_kind is not ProtocolItemKind.WORK_ITEM:
            raise ValueError("native-work source requires a work item")
        payload, next_cursor = self._transport.get(
            f"repos/{self._repository}/issues",
            {
                "state": "all",
                "per_page": str(limit),
                "page": "1",
            },
        )
        records = _require_records(payload, "issues")
        candidates = tuple(
            _issue_candidate(self._repository, record, self.kind)
            for record in records
            if "pull_request" not in _require_record(record, "issue")
        )
        limitations = (
            ("additional GitHub issue page remains",)
            if next_cursor
            else ()
        )
        return PreflightResult(
            source_kind=self.kind,
            capability=CapabilityStatus.SUPPORTED,
            completeness=(
                ResultCompleteness.PARTIAL
                if next_cursor
                else ResultCompleteness.COMPLETE
            ),
            searched_scopes=(
                f"github:{self._repository}:all-issues",
            ),
            candidates=candidates,
            next_cursor=next_cursor,
            limitations=limitations,
        )


class GitHubDeliveryCandidateSource:
    kind = PreflightSourceKind.DELIVERY

    def __init__(
        self,
        target: TargetConfig,
        transport: GitHubPreflightTransport,
    ):
        self.target = _validate_github_target(target)
        self._repository = validate_repository_name(target.repository)
        self._transport = transport

    def query(self, intent: WriteIntent, limit: int) -> PreflightResult:
        validate_intent(intent)
        _validate_limit(limit)
        if intent.item_kind is not ProtocolItemKind.WORK_ITEM:
            raise ValueError("delivery source requires a work item")

        pulls, pull_cursor = self._transport.get(
            f"repos/{self._repository}/pulls",
            {
                "state": "all",
                "per_page": str(limit),
                "page": "1",
            },
        )
        branches, branch_cursor = self._transport.get(
            f"repos/{self._repository}/branches",
            {
                "per_page": str(limit),
                "page": "1",
            },
        )
        releases, release_cursor = self._transport.get(
            f"repos/{self._repository}/releases",
            {
                "per_page": str(limit),
                "page": "1",
            },
        )

        candidates = [
            self._pull_candidate(record)
            for record in _require_records(pulls, "pulls")
        ]
        candidates.extend(
            self._branch_candidate(record)
            for record in _require_records(branches, "branches")
        )
        candidates.extend(
            self._release_candidate(record)
            for record in _require_records(releases, "releases")
        )

        cursors = tuple(
            cursor
            for cursor in (
                pull_cursor,
                branch_cursor,
                release_cursor,
            )
            if cursor
        )
        limitations = []
        if cursors:
            limitations.append(
                "additional GitHub delivery page remains"
            )
        if len(candidates) > limit:
            limitations.append(
                "delivery candidate item budget exceeded"
            )
        partial = bool(cursors) or len(candidates) > limit
        return PreflightResult(
            source_kind=self.kind,
            capability=CapabilityStatus.SUPPORTED,
            completeness=(
                ResultCompleteness.PARTIAL
                if partial
                else ResultCompleteness.COMPLETE
            ),
            searched_scopes=(
                f"github:{self._repository}:pulls",
                f"github:{self._repository}:branches",
                f"github:{self._repository}:releases",
            ),
            candidates=tuple(candidates[:limit]),
            next_cursor=cursors[0] if cursors else None,
            limitations=tuple(limitations),
        )

    def _pull_candidate(self, record: object) -> Candidate:
        item = _require_record(record, "pull request")
        number = _require_positive_integer(
            item,
            "number",
            "pull request",
        )
        return Candidate(
            source_kind=self.kind,
            provider_qualified_id=(
                f"github:{self._repository}#pull-{number}"
            ),
            title=_require_string(item, "title", "pull request"),
            status=_require_string(item, "state", "pull request"),
            updated=_require_string(
                item,
                "updated_at",
                "pull request",
            ),
            url=_require_string(item, "html_url", "pull request"),
        )

    def _branch_candidate(self, record: object) -> Candidate:
        item = _require_record(record, "branch")
        name = _require_string(item, "name", "branch")
        commit = _require_record(item.get("commit"), "branch commit")
        sha = _require_string(commit, "sha", "branch commit")
        protected = item.get("protected")
        if not isinstance(protected, bool):
            raise AdapterError(
                "GitHub branch item requires boolean field protected"
            )
        encoded_name = quote(name, safe="/")
        return Candidate(
            source_kind=self.kind,
            provider_qualified_id=(
                f"github:{self._repository}#branch-{name}"
            ),
            title=name,
            status="protected" if protected else "active",
            updated=sha,
            url=(
                f"https://github.com/{self._repository}/tree/"
                f"{encoded_name}"
            ),
        )

    def _release_candidate(self, record: object) -> Candidate:
        item = _require_record(record, "release")
        release_id = _require_positive_integer(
            item,
            "id",
            "release",
        )
        tag = _require_string(item, "tag_name", "release")
        name = item.get("name")
        if name is not None and not isinstance(name, str):
            raise AdapterError(
                "GitHub release item field name must be a string"
            )
        published_at = item.get("published_at")
        if not isinstance(published_at, str) or not published_at:
            published_at = _require_string(
                item,
                "created_at",
                "release",
            )
        draft = item.get("draft")
        if not isinstance(draft, bool):
            raise AdapterError(
                "GitHub release item requires boolean field draft"
            )
        return Candidate(
            source_kind=self.kind,
            provider_qualified_id=(
                f"github:{self._repository}#release-{release_id}"
            ),
            title=name or tag,
            status="draft" if draft else "published",
            updated=published_at,
            url=_require_string(item, "html_url", "release"),
        )


class GitHubReturnIntakeCandidateSource:
    kind = PreflightSourceKind.RETURN_INTAKE

    def __init__(
        self,
        target: StoreConfig,
        transport: GitHubPreflightTransport,
    ):
        self.target = _validate_github_intake_store(target)
        self._repository = validate_repository_name(target.repository)
        self._transport = transport

    def query(self, intent: WriteIntent, limit: int) -> PreflightResult:
        validate_intent(intent)
        _validate_limit(limit)
        if intent.item_kind is not ProtocolItemKind.RETURN_ITEM:
            raise ValueError("return-intake source requires a Return Item")
        expected = f"correlation-id: {intent.correlation_id}"
        escaped = expected.replace("\\", "\\\\").replace('"', '\\"')
        payload, next_cursor = self._transport.get(
            "search/issues",
            {
                "q": " ".join(
                    (
                        f"repo:{self._repository}",
                        "is:issue",
                        "in:body",
                        f'"{escaped}"',
                        f'label:"return-kind:{intent.return_kind.value}"',
                        f'label:"intake-state:{intent.intake_state.value}"',
                    )
                ),
                "per_page": str(limit),
                "page": "1",
            },
        )
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("items"), list)
            or not isinstance(payload.get("incomplete_results"), bool)
        ):
            raise AdapterError(
                "GitHub return search response must contain items and "
                "incomplete_results"
            )
        candidates = tuple(
            _issue_candidate(
                self._repository,
                record,
                self.kind,
            )
            for record in payload["items"]
            if "pull_request" not in _require_record(record, "issue")
        )
        limitations = [
            "GitHub correlation lookup is approximate provider candidate "
            "retrieval"
        ]
        if payload["incomplete_results"]:
            limitations.append(
                "GitHub reported incomplete return search results"
            )
        if next_cursor:
            limitations.append("additional GitHub return search page remains")
        return PreflightResult(
            source_kind=self.kind,
            capability=CapabilityStatus.PARTIAL,
            completeness=ResultCompleteness.PARTIAL,
            searched_scopes=(
                f"github:{self._repository}:return-intake-search",
            ),
            candidates=candidates,
            next_cursor=next_cursor,
            limitations=tuple(limitations),
        )
