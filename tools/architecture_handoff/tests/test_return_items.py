import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.models import (  # noqa: E402
    CapabilityStatus,
    ResultCompleteness,
    WorkRoute,
)
from tools.architecture_handoff.preflight import (  # noqa: E402
    Candidate,
    CandidateLane,
    PreflightResult,
    PreflightSourceKind,
    SourceApplicability,
    SourceDeclaration,
    SnapshotCandidateSource,
    run_preflight,
)
from tools.architecture_handoff.query_models import (  # noqa: E402
    AdvancedQuery,
    ContinuationPlan,
    LaneRequirement,
    QueryPurpose,
)
from tools.architecture_handoff.return_items import (  # noqa: E402
    IntakeState,
    ReturnIntent,
    ReturnKind,
    return_to_write_intent,
)
from tools.architecture_handoff.registry import (  # noqa: E402
    StoreConfig,
    StoreRole,
    TargetConfig,
)
from tools.architecture_handoff.runtime_config import QueryBudget  # noqa: E402
from tools.architecture_handoff.write_coordinator import (  # noqa: E402
    CandidateDisposition,
    WriteCoordinator,
    WriteTargetConfig,
)
from tools.architecture_handoff.write_models import (  # noqa: E402
    ProtocolItemKind,
    RelationKind,
    TypedRelation,
    WriteIntent,
    WriteOperation,
)


def return_intent(**overrides):
    values = {
        "operation": WriteOperation.CREATE,
        "target_key": "documentation-intake",
        "title": "Return feasibility evidence",
        "return_kind": ReturnKind.EVIDENCE_RESULT,
        "intake_state": IntakeState.PENDING,
        "correlation_id": "corr-spike-12",
        "source_relation": TypedRelation(
            kind=RelationKind.RETURN,
            target="github:owner/implementation#12",
        ),
        "origin": "github:owner/implementation",
        "evidence_links": (
            "https://github.com/owner/implementation/actions/runs/1",
        ),
        "outcome": "The provider supports the required operation.",
        "method": "Executed one bounded API prototype.",
        "observations": "The response preserved the expected identifier.",
        "verification": "The integration test passed.",
        "produced_artifacts": (
            "github:owner/implementation@abc123:test/provider.py",
        ),
        "limitations": ("Only one provider version was tested.",),
        "remaining_unknowns": ("Rate-limit behavior remains unknown.",),
        "requested_return_route": "Resume Research Plan RP-0001.",
    }
    values.update(overrides)
    return ReturnIntent(**values)


def intake_store():
    return StoreConfig(
        key="documentation-intake",
        role=StoreRole.DOCUMENTATION_INTAKE,
        provider="github",
        repository="owner/docs",
        routing_status="active",
        tracker_reference="github:owner/docs",
    )


class ReturnSource:
    kind = PreflightSourceKind.RETURN_INTAKE

    def __init__(self, target, candidates=()):
        self.target = target
        self.candidates = candidates
        self.calls = 0

    def query(self, _intent, _limit):
        self.calls += 1
        return PreflightResult(
            source_kind=self.kind,
            capability=CapabilityStatus.SUPPORTED,
            completeness=ResultCompleteness.COMPLETE,
            searched_scopes=("github:owner/docs:return-intake",),
            candidates=self.candidates,
        )


class AdvisoryReturnSource:
    kind = PreflightSourceKind.SIMILARITY

    def __init__(self, target):
        self.target = target

    def query(self, _intent, limit):
        return PreflightResult(
            source_kind=self.kind,
            capability=CapabilityStatus.PARTIAL,
            completeness=ResultCompleteness.PARTIAL,
            searched_scopes=("github:owner/docs:issue-search",),
            limitations=("advisory search was rate limited",),
            plan=ContinuationPlan(
                query=AdvancedQuery(
                    purpose=QueryPurpose.SIMILARITY,
                    logical_target="documentation-intake",
                    requirement=LaneRequirement.ADVISORY,
                    capability="related-return-evidence",
                    limit=limit,
                ),
                max_pages=1,
                max_items=limit,
            ),
        )


class RenderOnlyAdapter:
    def __init__(self, target):
        self.target = target
        self.render_calls = 0

    def render_payload(self, intent):
        self.render_calls += 1
        return {
            "title": intent.title,
            "body": intent.body,
            "labels": [
                f"return-kind:{return_intent().return_kind.value}",
                f"intake-state:{intent.intake_state.value}",
            ],
        }


def intake_declaration():
    return (
        SourceDeclaration(
            kind=PreflightSourceKind.RETURN_INTAKE,
            applicability=SourceApplicability.ENABLED,
        ),
    )


class ReturnItemTests(unittest.TestCase):
    def test_return_exact_source_stays_required_with_advisory_lane(self):
        target = intake_store()
        advisory = AdvisoryReturnSource(target)

        bundle = run_preflight(
            return_to_write_intent(return_intent()),
            intake_declaration(),
            (ReturnSource(target),),
            candidate_lanes=(
                CandidateLane(
                    name="related-return-candidates",
                    requirement=LaneRequirement.ADVISORY,
                    source=advisory,
                ),
            ),
        )

        self.assertEqual(
            [result.source_kind for result in bundle.results],
            [PreflightSourceKind.RETURN_INTAKE],
        )
        self.assertEqual(
            bundle.advisory_results[0].limitations,
            ("advisory search was rate limited",),
        )

    def test_return_create_requires_pending_and_correlation(self):
        with self.assertRaisesRegex(
            ValueError,
            "Return creation requires intake-state pending",
        ):
            return_to_write_intent(
                return_intent(intake_state=IntakeState.HANDLED)
            )

        with self.assertRaisesRegex(
            ValueError,
            "correlation_id",
        ):
            return_to_write_intent(return_intent(correlation_id=" "))

    def test_return_create_requires_one_typed_source_relation(self):
        with self.assertRaisesRegex(
            ValueError,
            "RelationKind.RETURN",
        ):
            return_to_write_intent(
                return_intent(
                    source_relation=TypedRelation(
                        kind=RelationKind.CORRELATION,
                        target="github:owner/implementation#12",
                    )
                )
            )

    def test_return_uses_return_intake_preflight_only(self):
        source = ReturnSource(intake_store())
        write_intent = return_to_write_intent(return_intent())

        bundle = run_preflight(
            write_intent,
            intake_declaration(),
            (source,),
        )

        self.assertEqual(
            write_intent.item_kind,
            ProtocolItemKind.RETURN_ITEM,
        )
        self.assertEqual(
            [result.source_kind for result in bundle.results],
            [PreflightSourceKind.RETURN_INTAKE],
        )
        self.assertEqual(source.calls, 1)

    def test_snapshot_candidate_source_returns_bound_coverage_without_calls(
        self,
    ):
        store = intake_store()
        result = PreflightResult(
            source_kind=PreflightSourceKind.RETURN_INTAKE,
            capability=CapabilityStatus.SUPPORTED,
            completeness=ResultCompleteness.COMPLETE,
            searched_scopes=("github:owner/docs:repository-issues",),
        )
        source = SnapshotCandidateSource(
            target=store,
            result=result,
        )

        returned = source.query(
            return_to_write_intent(return_intent()),
            100,
        )

        self.assertIs(returned, result)
        self.assertIs(source.kind, PreflightSourceKind.RETURN_INTAKE)

    def test_duplicate_correlation_candidate_requires_human_disposition(self):
        candidate = Candidate(
            source_kind=PreflightSourceKind.RETURN_INTAKE,
            provider_qualified_id="github:owner/docs#40",
            title="Existing evidence return",
            status="pending",
            updated="2026-07-30T11:00:00Z",
            url="https://github.com/owner/docs/issues/40",
        )
        target = intake_store()
        source = ReturnSource(target, (candidate,))
        coordinator = WriteCoordinator(
            WriteTargetConfig(
                target=target,
                declarations=intake_declaration(),
            ),
            RenderOnlyAdapter(target),
            (source,),
            preflight_budget=QueryBudget(
                page_size=100,
                max_pages=1,
                max_items=100,
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "create-distinct requires a reason",
        ):
            coordinator.prepare(
                return_to_write_intent(return_intent()),
                CandidateDisposition.CREATE_DISTINCT,
            )

    def test_return_requires_documentation_intake_store_before_render(self):
        target = TargetConfig(
            key="documentation-intake",
            provider="github",
            repository="owner/docs",
            routing_status="active",
            owns=("documentation intake",),
            excludes=(),
        )
        adapter = RenderOnlyAdapter(target)

        with self.assertRaisesRegex(
            ValueError,
            "Return Item requires a documentation-intake store",
        ):
            WriteCoordinator(
                WriteTargetConfig(
                    target=target,
                    declarations=intake_declaration(),
                ),
                adapter,
                (ReturnSource(target),),
                preflight_budget=QueryBudget(
                    page_size=100,
                    max_pages=1,
                    max_items=100,
                ),
            ).prepare(
                return_to_write_intent(return_intent()),
                CandidateDisposition.CREATE_DISTINCT,
            )

        self.assertEqual(adapter.render_calls, 0)

    def test_work_item_rejects_documentation_store_before_render(self):
        store = intake_store()
        adapter = RenderOnlyAdapter(store)
        work_intent = WriteIntent(
            operation=WriteOperation.CREATE,
            target_key=store.key,
            item_kind=ProtocolItemKind.WORK_ITEM,
            title="Implementation work",
            body="One result.",
            route=WorkRoute.IMPLEMENTATION_CONFORMANCE_REFERRAL,
            lifecycle_state="draft",
            relations=(
                TypedRelation(
                    kind=RelationKind.REFINEMENT,
                    target="git:owner/docs@abc123:ADR-0003",
                    revision="abc123",
                ),
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "Work Item requires an implementation target",
        ):
            WriteCoordinator(
                WriteTargetConfig(
                    target=store,
                    declarations=(),
                ),
                adapter,
                (),
                preflight_budget=QueryBudget(
                    page_size=100,
                    max_pages=1,
                    max_items=100,
                ),
            ).prepare(
                work_intent,
                CandidateDisposition.CREATE_DISTINCT,
            )

        self.assertEqual(adapter.render_calls, 0)

    def test_return_handled_update_requires_pending_protocol_state(self):
        valid = return_intent(
            operation=WriteOperation.UPDATE,
            intake_state=IntakeState.HANDLED,
            previous_intake_state=IntakeState.PENDING,
            provider_id="40",
            expected_provider_state="2026-07-30T11:00:00Z",
        )

        converted = return_to_write_intent(valid)

        self.assertEqual(converted.intake_state, IntakeState.HANDLED)
        self.assertEqual(
            converted.previous_intake_state,
            IntakeState.PENDING,
        )
        self.assertEqual(converted.provider_id, "40")

        with self.assertRaisesRegex(
            ValueError,
            "pending to handled",
        ):
            return_to_write_intent(
                return_intent(
                    operation=WriteOperation.UPDATE,
                    intake_state=IntakeState.HANDLED,
                    previous_intake_state=IntakeState.HANDLED,
                    provider_id="40",
                    expected_provider_state="2026-07-30T11:00:00Z",
                )
            )

    def test_return_handled_update_skips_duplicate_correlation_preflight(self):
        write_intent = return_to_write_intent(
            return_intent(
                operation=WriteOperation.UPDATE,
                intake_state=IntakeState.HANDLED,
                previous_intake_state=IntakeState.PENDING,
                provider_id="40",
                expected_provider_state="2026-07-30T11:00:00Z",
            )
        )

        bundle = run_preflight(write_intent, (), ())

        self.assertEqual(bundle.declarations, ())
        self.assertEqual(bundle.results, ())

    def test_return_body_is_deterministic_and_complete(self):
        converted = return_to_write_intent(return_intent())
        body = converted.body

        expected_fields = (
            "return-kind: evidence-result",
            "intake-state: pending",
            "correlation-id: corr-spike-12",
            "source-relation: return github:owner/implementation#12",
            "origin: github:owner/implementation",
            "outcome: The provider supports the required operation.",
            "method: Executed one bounded API prototype.",
            "verification: The integration test passed.",
            "requested-return-route: Resume Research Plan RP-0001.",
        )
        positions = [body.index(field) for field in expected_fields]
        self.assertEqual(positions, sorted(positions))

    def test_return_required_evidence_fields_reject_empty_values(self):
        for field in (
            "origin",
            "outcome",
            "method",
            "observations",
            "verification",
            "requested_return_route",
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    return_to_write_intent(
                        return_intent(**{field: " "})
                    )


if __name__ == "__main__":
    unittest.main()
