import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff import github_preflight as github_preflight_module  # noqa: E402
from tools.architecture_handoff.github_preflight import (  # noqa: E402
    GitHubDeliveryCandidateSource,
    GitHubNativeCandidateSource,
    GitHubQueryCandidateSource,
    GitHubReturnIntakeCandidateSource,
    advisory_similarity_plan,
    native_work_plan,
    return_correlation_plan,
    return_intake_plan,
    return_preflight_from_coverage,
)
from tools.architecture_handoff.github import (  # noqa: E402
    GitHubRateLimitError,
)
from tools.architecture_handoff.adapter import AdapterBinding  # noqa: E402
from tools.architecture_handoff.models import (  # noqa: E402
    CapabilityStatus,
    ResultCompleteness,
    WorkItemSummary,
    WorkRoute,
)
from tools.architecture_handoff.preflight import (  # noqa: E402
    PreflightSourceKind,
)
from tools.architecture_handoff.query_models import (  # noqa: E402
    AdvancedQuery,
    ContinuationPlan,
    LaneRequirement,
    ProviderCall,
    QueryCoverage,
    QueryPurpose,
    SearchHit,
)
from tools.architecture_handoff.registry import (  # noqa: E402
    StoreConfig,
    StoreRole,
    TargetConfig,
)
from tools.architecture_handoff.runtime_config import QueryBudget  # noqa: E402
from tools.architecture_handoff.write_models import (  # noqa: E402
    IntakeState,
    ProtocolItemKind,
    RelationKind,
    TypedRelation,
    ReturnKind,
    WriteIntent,
    WriteOperation,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "github_delivery_page.json"
)


def github_target():
    return TargetConfig(
        key="example-implementation",
        provider="github",
        repository="owner/repository",
        routing_status="active",
        owns=("pilot implementation",),
        excludes=(),
    )


def github_intake_store():
    return StoreConfig(
        key="documentation-intake",
        role=StoreRole.DOCUMENTATION_INTAKE,
        provider="github",
        repository="owner/docs",
        routing_status="active",
        tracker_reference="github:owner/docs",
    )


class FakeTransport:
    def __init__(self, payloads, cursors=None):
        self.payloads = payloads
        self.cursors = cursors or {}
        self.calls = []

    def get(self, path, params):
        self.calls.append((path, params))
        key = path.rsplit("/", 1)[-1]
        return self.payloads[key], self.cursors.get(key)


class FakeQueryCoordinator:
    def __init__(self, coverage=None, error=None, binding=None):
        self.coverage = coverage
        self.error = error
        self.binding = binding or AdapterBinding(
            provider="github",
            provider_scope="owner/repository",
            logical_target="example-implementation",
        )
        self.plans = []

    def execute(self, plan):
        self.plans.append(plan)
        if self.error is not None:
            raise self.error
        return replace(self.coverage, plan=plan)


def work_intent():
    return WriteIntent(
        operation=WriteOperation.CREATE,
        target_key="example-implementation",
        item_kind=ProtocolItemKind.WORK_ITEM,
        title="Verify deterministic lookup",
        body="One bounded result.",
        route=WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
        lifecycle_state="draft",
        relations=(
            TypedRelation(
                kind=RelationKind.REFINEMENT,
                target="git:owner/docs@abc123:ADR-0003",
                revision="abc123",
            ),
        ),
    )


def return_intent(correlation_id="corr-12"):
    return WriteIntent(
        operation=WriteOperation.CREATE,
        target_key="documentation-intake",
        item_kind=ProtocolItemKind.RETURN_ITEM,
        title="Return evidence",
        body="Evidence.",
        intake_state=IntakeState.PENDING,
        return_kind=ReturnKind.EVIDENCE_RESULT,
        relations=(
            TypedRelation(
                kind=RelationKind.RETURN,
                target="github:owner/implementation#12",
            ),
        ),
        correlation_id=correlation_id,
    )


def issue(number, state, *, body="", pull_request=False):
    record = {
        "number": number,
        "title": f"Issue {number}",
        "state": state,
        "updated_at": f"2026-07-{number:02d}T10:00:00Z",
        "html_url": (
            f"https://github.com/owner/repository/issues/{number}"
        ),
        "body": body,
        "labels": [],
    }
    if pull_request:
        record["pull_request"] = {"url": "https://api.github.com/pulls/1"}
    return record


def similarity_intent():
    return replace(
        work_intent(),
        capability="account-address-prediction",
        expected_outcome="Return one deterministic address",
    )


def multi_source_intent():
    return replace(
        similarity_intent(),
        relations=(
            TypedRelation(
                kind=RelationKind.REFINEMENT,
                target=(
                    "git:https://github.com/owner/docs:"
                    "product/requirements/PR-0004.md"
                ),
                revision="abc123",
            ),
            TypedRelation(
                kind=RelationKind.REFINEMENT,
                target=(
                    "git:https://github.com/owner/docs:"
                    "architecture/09-architecture-decisions.md#adr-0003"
                ),
                revision="abc123",
            ),
            TypedRelation(
                kind=RelationKind.REFINEMENT,
                target=(
                    "git:https://github.com/owner/docs:"
                    "architecture/06-runtime-view.md#account-deployment"
                ),
                revision="abc123",
            ),
        ),
    )


def query_coverage(*, completeness=ResultCompleteness.COMPLETE):
    plan = advisory_similarity_plan(similarity_intent(), 20)
    return QueryCoverage(
        plan=plan,
        capability=CapabilityStatus.SUPPORTED,
        completeness=completeness,
        hits=(
            SearchHit(
                item=WorkItemSummary(
                    provider_id="11",
                    provider_qualified_id="github:owner/repository#11",
                    title="Existing candidate",
                    status="open",
                    work_route=WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
                    updated="2026-07-30T10:00:00Z",
                    url=(
                        "https://github.com/owner/repository/issues/11"
                    ),
                )
            ),
        ),
        calls=(
            ProviderCall(
                purpose=QueryPurpose.SIMILARITY,
                cursor=None,
                searched_scopes=(
                    "github:owner/repository:issue-search",
                ),
            ),
        ),
        limitations=(
            ("provider search is partial",)
            if completeness is ResultCompleteness.PARTIAL
            else ()
        ),
    )


class GitHubPreflightTests(unittest.TestCase):
    def test_return_correlation_plan_uses_resolved_budget(self):
        plan = return_correlation_plan(
            return_intent(),
            QueryBudget(
                page_size=100,
                max_pages=5,
                max_items=500,
            ),
        )

        self.assertIs(
            plan.query.purpose,
            QueryPurpose.RETURN_CORRELATION,
        )
        self.assertEqual(plan.query.correlation_id, "corr-12")
        self.assertIs(plan.query.intake_state, IntakeState.PENDING)
        self.assertIs(
            plan.query.return_kind,
            ReturnKind.EVIDENCE_RESULT,
        )
        self.assertEqual(plan.query.limit, 100)
        self.assertEqual(plan.max_pages, 5)
        self.assertEqual(plan.max_items, 500)

    def test_return_preflight_projects_only_exact_correlation_hits(self):
        plan = return_correlation_plan(
            return_intent(),
            QueryBudget(
                page_size=100,
                max_pages=1,
                max_items=100,
            ),
        )
        matching = SearchHit(
            item=WorkItemSummary(
                provider_id="31",
                provider_qualified_id="github:owner/docs#31",
                title="Matching Return",
                status="pending",
                work_route=WorkRoute.TARGET_NATIVE_INTERNAL,
                updated="2026-07-31T10:00:00Z",
                url="https://github.com/owner/docs/issues/31",
            ),
            matched_signals=("correlation-id",),
        )
        other = replace(
            matching,
            item=replace(
                matching.item,
                provider_id="32",
                provider_qualified_id="github:owner/docs#32",
                title="Other Return",
                url="https://github.com/owner/docs/issues/32",
            ),
            matched_signals=(),
        )
        coverage = QueryCoverage(
            plan=plan,
            capability=CapabilityStatus.SUPPORTED,
            completeness=ResultCompleteness.COMPLETE,
            hits=(matching, other),
            calls=(
                ProviderCall(
                    purpose=QueryPurpose.RETURN_CORRELATION,
                    cursor=None,
                    searched_scopes=(
                        "github:owner/docs:repository-issues",
                    ),
                ),
            ),
            limitations=(),
        )

        result = return_preflight_from_coverage(coverage)

        self.assertEqual(
            [
                candidate.provider_qualified_id
                for candidate in result.candidates
            ],
            ["github:owner/docs#31"],
        )
        self.assertEqual(result.plan, plan)
        self.assertEqual(result.calls, coverage.calls)
        self.assertIs(
            result.completeness,
            ResultCompleteness.COMPLETE,
        )

    def test_multi_source_intent_produces_one_independent_exact_plan_per_source(
        self,
    ):
        factory = getattr(
            github_preflight_module,
            "native_work_plans",
            None,
        )
        self.assertTrue(
            callable(factory),
            "native_work_plans must compose explicit per-source plans",
        )

        plans = factory(multi_source_intent(), 20)

        self.assertEqual(len(plans), 3)
        self.assertEqual(
            [plan.query.source_reference for plan in plans],
            [relation.target for relation in multi_source_intent().relations],
        )
        self.assertEqual(
            [plan.query.purpose for plan in plans],
            [QueryPurpose.SOURCE_TRACEABILITY] * 3,
        )
        self.assertEqual(
            [plan.query.cursor for plan in plans],
            [None, None, None],
        )
        self.assertEqual(len({plan.query.source_reference for plan in plans}), 3)

    def test_multi_source_intent_generates_separately_named_candidate_lanes(
        self,
    ):
        factory = getattr(
            github_preflight_module,
            "exact_source_candidate_lanes",
            None,
        )
        self.assertTrue(
            callable(factory),
            "exact_source_candidate_lanes must exist",
        )
        coordinator = FakeQueryCoordinator(query_coverage())

        lanes = factory(
            github_target(),
            coordinator,
            multi_source_intent(),
        )

        self.assertEqual(len(lanes), 3)
        self.assertEqual(len({lane.name for lane in lanes}), 3)
        self.assertEqual(
            [lane.requirement for lane in lanes],
            [LaneRequirement.REQUIRED] * 3,
        )
        self.assertEqual(len({id(lane.source) for lane in lanes}), 3)

    def test_query_source_rejects_wrong_repository_binding(self):
        coordinator = FakeQueryCoordinator(
            query_coverage(),
            binding=AdapterBinding(
                provider="github",
                provider_scope="owner/other",
                logical_target="example-implementation",
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "query coordinator binding does not match GitHub target",
        ):
            GitHubQueryCandidateSource(
                github_target(),
                coordinator,
                advisory_similarity_plan,
                PreflightSourceKind.SIMILARITY,
            )

    def test_query_source_rejects_non_github_binding(self):
        coordinator = FakeQueryCoordinator(
            query_coverage(),
            binding=AdapterBinding(
                provider="gitlab",
                provider_scope="owner/repository",
                logical_target="example-implementation",
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "query coordinator binding does not match GitHub target",
        ):
            GitHubQueryCandidateSource(
                github_target(),
                coordinator,
                advisory_similarity_plan,
                PreflightSourceKind.SIMILARITY,
            )

    def test_query_source_rejects_wrong_logical_target_binding(self):
        coordinator = FakeQueryCoordinator(
            query_coverage(),
            binding=AdapterBinding(
                provider="github",
                provider_scope="owner/repository",
                logical_target="documentation-intake",
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "query coordinator binding does not match GitHub target",
        ):
            GitHubQueryCandidateSource(
                github_target(),
                coordinator,
                advisory_similarity_plan,
                PreflightSourceKind.SIMILARITY,
            )

    def test_query_source_rejects_scope_outside_bound_repository(self):
        coverage = replace(
            query_coverage(),
            calls=(
                ProviderCall(
                    purpose=QueryPurpose.SIMILARITY,
                    cursor=None,
                    searched_scopes=("github:owner/other:issue-search",),
                ),
            ),
        )
        source = GitHubQueryCandidateSource(
            github_target(),
            FakeQueryCoordinator(coverage),
            advisory_similarity_plan,
            PreflightSourceKind.SIMILARITY,
        )

        with self.assertRaisesRegex(
            ValueError,
            "query coverage scope is outside bound GitHub repository",
        ):
            source.query(similarity_intent(), 20)

    def test_query_source_rejects_identity_outside_bound_repository(self):
        foreign_hit = replace(
            query_coverage().hits[0],
            item=replace(
                query_coverage().hits[0].item,
                provider_qualified_id="github:owner/other#11",
            ),
        )
        coverage = replace(query_coverage(), hits=(foreign_hit,))
        source = GitHubQueryCandidateSource(
            github_target(),
            FakeQueryCoordinator(coverage),
            advisory_similarity_plan,
            PreflightSourceKind.SIMILARITY,
        )

        with self.assertRaisesRegex(
            ValueError,
            "candidate identity is outside bound GitHub repository",
        ):
            source.query(similarity_intent(), 20)

    def test_signal_free_similarity_returns_explicit_unsupported_result(self):
        coordinator = FakeQueryCoordinator(query_coverage())
        source = GitHubQueryCandidateSource(
            github_target(),
            coordinator,
            advisory_similarity_plan,
            PreflightSourceKind.SIMILARITY,
        )

        result = source.query(work_intent(), 20)

        self.assertIs(result.capability, CapabilityStatus.UNSUPPORTED)
        self.assertIs(result.completeness, ResultCompleteness.UNSUPPORTED)
        self.assertEqual(result.searched_scopes, ())
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.calls, ())
        self.assertIsNone(result.next_cursor)
        self.assertIsNone(result.plan)
        self.assertTrue(result.limitations[0])
        self.assertEqual(coordinator.plans, [])

    def test_exact_query_source_rejects_advisory_plan(self):
        plan = ContinuationPlan(
            query=AdvancedQuery(
                purpose=QueryPurpose.SOURCE_TRACEABILITY,
                logical_target="example-implementation",
                requirement=LaneRequirement.ADVISORY,
                source_reference="git:owner/docs@abc123:ADR-0003",
                limit=20,
            ),
            max_pages=1,
            max_items=20,
        )
        coordinator = FakeQueryCoordinator(query_coverage())
        source = GitHubQueryCandidateSource(
            github_target(),
            coordinator,
            lambda _intent, _limit: plan,
            PreflightSourceKind.NATIVE_WORK,
        )

        with self.assertRaisesRegex(
            ValueError,
            "exact query plan must be required",
        ):
            source.query(work_intent(), 20)

        self.assertEqual(coordinator.plans, [])

    def test_query_source_kind_must_match_query_purpose(self):
        coordinator = FakeQueryCoordinator(query_coverage())
        source = GitHubQueryCandidateSource(
            github_target(),
            coordinator,
            advisory_similarity_plan,
            PreflightSourceKind.NATIVE_WORK,
        )

        with self.assertRaisesRegex(
            ValueError,
            "source kind does not match query purpose",
        ):
            source.query(similarity_intent(), 20)

        self.assertEqual(coordinator.plans, [])

    def test_provider_call_purpose_must_match_query_plan(self):
        mismatched = replace(
            query_coverage(),
            calls=(
                ProviderCall(
                    purpose=QueryPurpose.CORRELATION,
                    cursor=None,
                    searched_scopes=(
                        "github:owner/repository:issue-search",
                    ),
                ),
            ),
        )
        source = GitHubQueryCandidateSource(
            github_target(),
            FakeQueryCoordinator(mismatched),
            advisory_similarity_plan,
            PreflightSourceKind.SIMILARITY,
        )

        with self.assertRaisesRegex(
            ValueError,
            "provider call purpose does not match query plan",
        ):
            source.query(similarity_intent(), 20)

    def test_native_plan_rejects_ambiguous_accepted_sources(self):
        ambiguous = replace(
            work_intent(),
            relations=work_intent().relations
            + (
                TypedRelation(
                    kind=RelationKind.IMPLEMENTATION,
                    target="git:owner/docs@def456:ADR-0004",
                    revision="def456",
                ),
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "native-work plan requires one accepted source",
        ):
            native_work_plan(ambiguous, 25)

    def test_query_candidate_source_uses_coordinator_coverage(self):
        coordinator = FakeQueryCoordinator(query_coverage())
        source = GitHubQueryCandidateSource(
            github_target(),
            coordinator,
            advisory_similarity_plan,
            PreflightSourceKind.SIMILARITY,
        )

        result = source.query(similarity_intent(), 20)

        self.assertEqual(coordinator.plans, [result.plan])
        self.assertEqual(result.calls, query_coverage().calls)
        self.assertEqual(
            result.searched_scopes,
            ("github:owner/repository:issue-search",),
        )
        self.assertEqual(
            result.candidates[0].provider_qualified_id,
            "github:owner/repository#11",
        )
        self.assertIs(
            result.candidates[0].source_kind,
            PreflightSourceKind.SIMILARITY,
        )

    def test_query_candidate_source_preserves_returned_cursor(self):
        coverage = replace(
            query_coverage(
                completeness=ResultCompleteness.PARTIAL,
            ),
            next_cursor="2",
        )
        source = GitHubQueryCandidateSource(
            github_target(),
            FakeQueryCoordinator(coverage),
            advisory_similarity_plan,
            PreflightSourceKind.SIMILARITY,
        )

        result = source.query(similarity_intent(), 20)

        self.assertEqual(result.next_cursor, "2")

    def test_query_plan_factories_bind_exact_intent_predicates(self):
        native = native_work_plan(work_intent(), 25)
        returned = return_intake_plan(return_intent(), 25)
        similarity = advisory_similarity_plan(similarity_intent(), 25)

        self.assertIs(
            native.query.purpose,
            QueryPurpose.SOURCE_TRACEABILITY,
        )
        self.assertEqual(native.query.logical_target, "example-implementation")
        self.assertEqual(
            native.query.routes,
            (WorkRoute.ARCHITECTURE_SLICE_HANDOFF,),
        )
        self.assertEqual(
            native.query.source_reference,
            "git:owner/docs@abc123:ADR-0003",
        )
        self.assertIs(returned.query.purpose, QueryPurpose.CORRELATION)
        self.assertEqual(returned.query.correlation_id, "corr-12")
        self.assertIs(similarity.query.purpose, QueryPurpose.SIMILARITY)
        self.assertEqual(
            similarity.query.capability,
            "account-address-prediction",
        )
        self.assertEqual(
            similarity.query.expected_outcome,
            "Return one deterministic address",
        )

    def test_query_candidate_source_preserves_rate_limit_evidence(self):
        coordinator = FakeQueryCoordinator(
            error=GitHubRateLimitError("30"),
        )
        source = GitHubQueryCandidateSource(
            github_target(),
            coordinator,
            advisory_similarity_plan,
            PreflightSourceKind.SIMILARITY,
        )

        result = source.query(similarity_intent(), 20)

        self.assertIs(result.completeness, ResultCompleteness.PARTIAL)
        self.assertIn("rate limited", result.limitations[0])
        self.assertIn("30", result.limitations[0])
        self.assertEqual(result.plan, coordinator.plans[0])
        self.assertEqual(result.calls, ())

    def test_native_source_includes_open_and_closed_issues(self):
        transport = FakeTransport(
            {"issues": [issue(11, "open"), issue(12, "closed")]}
        )
        source = GitHubNativeCandidateSource(
            github_target(),
            transport,
        )

        result = source.query(work_intent(), 50)

        self.assertEqual(
            [candidate.status for candidate in result.candidates],
            ["open", "closed"],
        )
        self.assertEqual(result.completeness, ResultCompleteness.COMPLETE)
        self.assertEqual(transport.calls[0][1]["state"], "all")

    def test_native_source_excludes_pull_requests(self):
        transport = FakeTransport(
            {
                "issues": [
                    issue(11, "open"),
                    issue(12, "open", pull_request=True),
                ]
            }
        )
        source = GitHubNativeCandidateSource(
            github_target(),
            transport,
        )

        result = source.query(work_intent(), 50)

        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].provider_qualified_id,
                         "github:owner/repository#11")

    def test_native_source_reports_partial_when_page_remains(self):
        transport = FakeTransport(
            {"issues": [issue(11, "open")]},
            {"issues": "2"},
        )
        source = GitHubNativeCandidateSource(
            github_target(),
            transport,
        )

        result = source.query(work_intent(), 1)

        self.assertEqual(result.completeness, ResultCompleteness.PARTIAL)
        self.assertEqual(result.next_cursor, "2")

    def test_delivery_source_combines_configured_scopes(self):
        payloads = json.loads(FIXTURE.read_text(encoding="utf-8"))
        transport = FakeTransport(payloads)
        source = GitHubDeliveryCandidateSource(
            github_target(),
            transport,
        )

        result = source.query(work_intent(), 20)

        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(
            {candidate.source_kind for candidate in result.candidates},
            {PreflightSourceKind.DELIVERY},
        )
        self.assertTrue(
            all(not hasattr(candidate, "body") for candidate in result.candidates)
        )

    def test_delivery_source_reports_each_searched_scope(self):
        payloads = json.loads(FIXTURE.read_text(encoding="utf-8"))
        source = GitHubDeliveryCandidateSource(
            github_target(),
            FakeTransport(payloads),
        )

        result = source.query(work_intent(), 20)

        self.assertEqual(
            result.searched_scopes,
            (
                "github:owner/repository:pulls",
                "github:owner/repository:branches",
                "github:owner/repository:releases",
            ),
        )

    def test_delivery_source_reports_partial_when_total_exceeds_limit(self):
        payloads = json.loads(FIXTURE.read_text(encoding="utf-8"))
        source = GitHubDeliveryCandidateSource(
            github_target(),
            FakeTransport(payloads),
        )

        result = source.query(work_intent(), 2)

        self.assertEqual(len(result.candidates), 2)
        self.assertEqual(result.completeness, ResultCompleteness.PARTIAL)
        self.assertIn("item budget", result.limitations[0])

    def test_return_source_uses_provider_query_without_local_filtering(self):
        transport = FakeTransport(
            {
                "issues": {
                    "incomplete_results": False,
                    "items": [
                        issue(11, "open", body="correlation-id: corr-1"),
                        issue(12, "open", body="correlation-id: corr-12"),
                        issue(
                            13,
                            "open",
                            body="prefix correlation-id: corr-12 suffix",
                        ),
                    ],
                }
            }
        )
        source = GitHubReturnIntakeCandidateSource(
            github_intake_store(),
            transport,
        )

        result = source.query(return_intent(), 50)

        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(
            result.capability,
            CapabilityStatus.PARTIAL,
        )
        self.assertEqual(
            result.completeness,
            ResultCompleteness.PARTIAL,
        )
        path, params = transport.calls[0]
        self.assertEqual(path, "search/issues")
        self.assertIn('"correlation-id: corr-12"', params["q"])
        self.assertIn(
            'label:"return-kind:evidence-result"',
            params["q"],
        )
        self.assertIn('label:"intake-state:pending"', params["q"])
        self.assertIn("approximate", result.limitations[0])

    def test_candidate_projection_omits_body(self):
        source = GitHubReturnIntakeCandidateSource(
            github_intake_store(),
            FakeTransport(
                {
                    "issues": {
                        "incomplete_results": False,
                        "items": [
                            issue(
                                12,
                                "open",
                                body="correlation-id: corr-12",
                            )
                        ],
                    }
                }
            ),
        )

        result = source.query(return_intent(), 50)

        self.assertFalse(hasattr(result.candidates[0], "body"))


if __name__ == "__main__":
    unittest.main()
