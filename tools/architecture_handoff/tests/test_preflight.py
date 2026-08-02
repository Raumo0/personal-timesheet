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
    run_preflight,
)
from tools.architecture_handoff.query_models import (  # noqa: E402
    AdvancedQuery,
    ContinuationPlan,
    LaneRequirement,
    ProviderCall,
    QueryPurpose,
)
from tools.architecture_handoff.write_models import (  # noqa: E402
    IntakeState,
    ProtocolItemKind,
    RelationKind,
    TypedRelation,
    ReturnKind,
    WriteIntent,
    WriteOperation,
)


class FakeCandidateSource:
    def __init__(self, kind, result):
        self.kind = kind
        self.result = result
        self.calls = []

    def query(self, intent, limit):
        self.calls.append((intent, limit))
        return self.result


def complete_result(kind, *, candidates=()):
    return PreflightResult(
        source_kind=kind,
        capability=CapabilityStatus.SUPPORTED,
        completeness=ResultCompleteness.COMPLETE,
        searched_scopes=(f"scope:{kind.value}",),
        candidates=candidates,
    )


def source(kind, *, completeness=ResultCompleteness.COMPLETE):
    capability = (
        CapabilityStatus.SUPPORTED
        if completeness is ResultCompleteness.COMPLETE
        else CapabilityStatus.PARTIAL
    )
    if completeness is ResultCompleteness.UNSUPPORTED:
        capability = CapabilityStatus.UNSUPPORTED
    return FakeCandidateSource(
        kind,
        PreflightResult(
            source_kind=kind,
            capability=capability,
            completeness=completeness,
            searched_scopes=(f"scope:{kind.value}",),
            limitations=(
                ()
                if completeness is ResultCompleteness.COMPLETE
                else ("provider limitation",)
            ),
        ),
    )


def declaration(kind, applicability=SourceApplicability.ENABLED, reason=None):
    return SourceDeclaration(
        kind=kind,
        applicability=applicability,
        reason=reason,
    )


def outbound_intent():
    return WriteIntent(
        operation=WriteOperation.CREATE,
        target_key="example-implementation",
        item_kind=ProtocolItemKind.WORK_ITEM,
        title="Check one bounded result",
        body="Candidate body",
        route=WorkRoute.IMPLEMENTATION_CONFORMANCE_REFERRAL,
        relations=(
            TypedRelation(
                kind=RelationKind.IMPLEMENTATION,
                target="git:owner/documentation@abc123:ADR-0003",
                revision="abc123",
            ),
        ),
    )


def return_intent():
    return WriteIntent(
        operation=WriteOperation.CREATE,
        target_key="documentation-intake",
        item_kind=ProtocolItemKind.RETURN_ITEM,
        title="Return evidence",
        body="Evidence result",
        intake_state=IntakeState.PENDING,
        return_kind=ReturnKind.EVIDENCE_RESULT,
        relations=(
            TypedRelation(
                kind=RelationKind.RETURN,
                target="github:owner/implementation#12",
            ),
        ),
        correlation_id="corr-12",
    )


def all_outbound_declarations():
    return tuple(
        declaration(kind)
        for kind in (
            PreflightSourceKind.NATIVE_WORK,
            PreflightSourceKind.OPENSPEC,
            PreflightSourceKind.DELIVERY,
        )
    )


def all_outbound_sources():
    return tuple(
        source(kind)
        for kind in (
            PreflightSourceKind.NATIVE_WORK,
            PreflightSourceKind.OPENSPEC,
            PreflightSourceKind.DELIVERY,
        )
    )


def candidate_lane(
    *,
    requirement,
    completeness,
    capability=None,
    limitations=(),
):
    if capability is None:
        capability = {
            ResultCompleteness.COMPLETE: CapabilityStatus.SUPPORTED,
            ResultCompleteness.PARTIAL: CapabilityStatus.PARTIAL,
            ResultCompleteness.UNSUPPORTED: CapabilityStatus.UNSUPPORTED,
        }[completeness]
    plan = None
    searched_scopes = ()
    if (
        capability is not CapabilityStatus.UNSUPPORTED
        or completeness is not ResultCompleteness.UNSUPPORTED
    ):
        plan = ContinuationPlan(
            query=AdvancedQuery(
                purpose=QueryPurpose.SIMILARITY,
                logical_target="example-implementation",
                requirement=requirement,
                capability="account-address-prediction",
            ),
            max_pages=1,
            max_items=25,
        )
        searched_scopes = ("scope:similarity",)
    result = PreflightResult(
        source_kind=PreflightSourceKind.SIMILARITY,
        capability=capability,
        completeness=completeness,
        searched_scopes=searched_scopes,
        limitations=limitations,
        plan=plan,
    )
    return CandidateLane(
        name="semantic-candidates",
        requirement=requirement,
        source=FakeCandidateSource(
            PreflightSourceKind.SIMILARITY,
            result,
        ),
    )


class PreflightTests(unittest.TestCase):
    def test_planned_zero_call_supported_complete_evidence_is_rejected(self):
        plan = ContinuationPlan(
            query=AdvancedQuery.similarity(
                logical_target="example-implementation",
                capability="account-address-prediction",
                expected_outcome=None,
            ),
            max_pages=1,
            max_items=25,
        )
        candidate = Candidate(
            source_kind=PreflightSourceKind.SIMILARITY,
            provider_qualified_id="github:owner/repository#11",
            title="Existing candidate",
            status="open",
            updated="2026-07-30T10:00:00Z",
            url="https://github.com/owner/repository/issues/11",
        )
        lane = CandidateLane(
            name="semantic-candidates",
            requirement=LaneRequirement.ADVISORY,
            source=FakeCandidateSource(
                PreflightSourceKind.SIMILARITY,
                PreflightResult(
                    source_kind=PreflightSourceKind.SIMILARITY,
                    capability=CapabilityStatus.SUPPORTED,
                    completeness=ResultCompleteness.COMPLETE,
                    searched_scopes=("scope:similarity",),
                    candidates=(candidate,),
                    plan=plan,
                ),
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "zero-call candidate lane must not report supported capability",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_planned_zero_call_complete_empty_result_is_rejected(self):
        plan = ContinuationPlan(
            query=AdvancedQuery.similarity(
                logical_target="example-implementation",
                capability="account-address-prediction",
                expected_outcome=None,
            ),
            max_pages=1,
            max_items=25,
        )
        lane = CandidateLane(
            name="semantic-candidates",
            requirement=LaneRequirement.ADVISORY,
            source=FakeCandidateSource(
                PreflightSourceKind.SIMILARITY,
                PreflightResult(
                    source_kind=PreflightSourceKind.SIMILARITY,
                    capability=CapabilityStatus.UNSUPPORTED,
                    completeness=ResultCompleteness.COMPLETE,
                    searched_scopes=(),
                    limitations=("query was interrupted before execution",),
                    plan=plan,
                ),
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "zero-call candidate lane must not report complete evidence",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_planned_zero_call_partial_candidate_is_rejected(self):
        plan = ContinuationPlan(
            query=AdvancedQuery.similarity(
                logical_target="example-implementation",
                capability="account-address-prediction",
                expected_outcome=None,
            ),
            max_pages=1,
            max_items=25,
        )
        candidate = Candidate(
            source_kind=PreflightSourceKind.SIMILARITY,
            provider_qualified_id="github:owner/repository#11",
            title="Unexecuted candidate",
            status="open",
            updated="2026-07-30T10:00:00Z",
            url="https://github.com/owner/repository/issues/11",
        )
        lane = CandidateLane(
            name="semantic-candidates",
            requirement=LaneRequirement.ADVISORY,
            source=FakeCandidateSource(
                PreflightSourceKind.SIMILARITY,
                PreflightResult(
                    source_kind=PreflightSourceKind.SIMILARITY,
                    capability=CapabilityStatus.PARTIAL,
                    completeness=ResultCompleteness.PARTIAL,
                    searched_scopes=("scope:similarity:interrupted",),
                    candidates=(candidate,),
                    limitations=("query was interrupted before execution",),
                    plan=plan,
                ),
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "zero-call candidate lane must not return candidates",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_planned_zero_call_interruption_requires_a_limitation(self):
        lane = candidate_lane(
            requirement=LaneRequirement.ADVISORY,
            capability=CapabilityStatus.PARTIAL,
            completeness=ResultCompleteness.PARTIAL,
        )

        with self.assertRaisesRegex(
            ValueError,
            "zero-call candidate lane requires a limitation",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_candidate_lane_evidence_requires_an_explicit_plan(self):
        candidate = Candidate(
            source_kind=PreflightSourceKind.SIMILARITY,
            provider_qualified_id="github:owner/repository#11",
            title="Existing candidate",
            status="open",
            updated="2026-07-30T10:00:00Z",
            url="https://github.com/owner/repository/issues/11",
        )
        evidence_results = (
            PreflightResult(
                source_kind=PreflightSourceKind.SIMILARITY,
                capability=CapabilityStatus.UNSUPPORTED,
                completeness=ResultCompleteness.UNSUPPORTED,
                searched_scopes=(),
                candidates=(candidate,),
                limitations=("provider search is unsupported",),
            ),
            PreflightResult(
                source_kind=PreflightSourceKind.SIMILARITY,
                capability=CapabilityStatus.UNSUPPORTED,
                completeness=ResultCompleteness.UNSUPPORTED,
                searched_scopes=(),
                limitations=("provider search is unsupported",),
                calls=(
                    ProviderCall(
                        purpose=QueryPurpose.SIMILARITY,
                        cursor=None,
                        searched_scopes=(),
                    ),
                ),
            ),
            PreflightResult(
                source_kind=PreflightSourceKind.SIMILARITY,
                capability=CapabilityStatus.PARTIAL,
                completeness=ResultCompleteness.UNSUPPORTED,
                searched_scopes=("scope:similarity",),
                limitations=("provider search is partial",),
            ),
            PreflightResult(
                source_kind=PreflightSourceKind.SIMILARITY,
                capability=CapabilityStatus.UNSUPPORTED,
                completeness=ResultCompleteness.PARTIAL,
                searched_scopes=(),
                limitations=("provider search is partial",),
            ),
        )

        for result in evidence_results:
            with self.subTest(result=result):
                lane = CandidateLane(
                    name="semantic-candidates",
                    requirement=LaneRequirement.ADVISORY,
                    source=FakeCandidateSource(
                        PreflightSourceKind.SIMILARITY,
                        result,
                    ),
                )
                with self.assertRaisesRegex(ValueError, "query plan"):
                    run_preflight(
                        outbound_intent(),
                        declarations=all_outbound_declarations(),
                        sources=all_outbound_sources(),
                        candidate_lanes=(lane,),
                    )

    def test_empty_unsupported_advisory_lane_may_omit_plan(self):
        lane = candidate_lane(
            requirement=LaneRequirement.ADVISORY,
            capability=CapabilityStatus.UNSUPPORTED,
            completeness=ResultCompleteness.UNSUPPORTED,
            limitations=("similarity signals were not supplied",),
        )

        bundle = run_preflight(
            outbound_intent(),
            declarations=all_outbound_declarations(),
            sources=all_outbound_sources(),
            candidate_lanes=(lane,),
        )

        result = bundle.advisory_results[0]
        self.assertIsNone(result.plan)
        self.assertEqual(result.searched_scopes, ())
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.calls, ())
        self.assertIsNone(result.next_cursor)

    def test_planless_unsupported_lane_requires_a_limitation(self):
        lane = candidate_lane(
            requirement=LaneRequirement.ADVISORY,
            capability=CapabilityStatus.UNSUPPORTED,
            completeness=ResultCompleteness.UNSUPPORTED,
        )

        with self.assertRaisesRegex(
            ValueError,
            "planless unsupported candidate lane requires a limitation",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_candidate_lane_source_kind_must_match_query_purpose(self):
        plan = ContinuationPlan(
            query=AdvancedQuery(
                purpose=QueryPurpose.CORRELATION,
                logical_target="example-implementation",
                requirement=LaneRequirement.ADVISORY,
                correlation_id="corr-12",
            ),
            max_pages=1,
            max_items=25,
        )
        lane = CandidateLane(
            name="semantic-candidates",
            requirement=LaneRequirement.ADVISORY,
            source=FakeCandidateSource(
                PreflightSourceKind.SIMILARITY,
                PreflightResult(
                    source_kind=PreflightSourceKind.SIMILARITY,
                    capability=CapabilityStatus.SUPPORTED,
                    completeness=ResultCompleteness.COMPLETE,
                    searched_scopes=("scope:similarity",),
                    plan=plan,
                ),
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "candidate lane source kind does not match query purpose",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_candidate_lane_call_purpose_must_match_plan(self):
        plan = ContinuationPlan(
            query=AdvancedQuery.similarity(
                logical_target="example-implementation",
                capability="account-address-prediction",
                expected_outcome=None,
            ),
            max_pages=1,
            max_items=25,
        )
        lane = CandidateLane(
            name="semantic-candidates",
            requirement=LaneRequirement.ADVISORY,
            source=FakeCandidateSource(
                PreflightSourceKind.SIMILARITY,
                PreflightResult(
                    source_kind=PreflightSourceKind.SIMILARITY,
                    capability=CapabilityStatus.SUPPORTED,
                    completeness=ResultCompleteness.COMPLETE,
                    searched_scopes=("scope:similarity",),
                    plan=plan,
                    calls=(
                        ProviderCall(
                            purpose=QueryPurpose.CORRELATION,
                            cursor=None,
                            searched_scopes=("scope:similarity",),
                        ),
                    ),
                ),
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "candidate lane provider call purpose does not match query plan",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_candidate_lane_cursor_requires_recorded_coverage_call(self):
        plan = ContinuationPlan(
            query=AdvancedQuery.similarity(
                logical_target="example-implementation",
                capability="account-address-prediction",
                expected_outcome=None,
            ),
            max_pages=1,
            max_items=25,
        )
        lane = CandidateLane(
            name="semantic-candidates",
            requirement=LaneRequirement.ADVISORY,
            source=FakeCandidateSource(
                PreflightSourceKind.SIMILARITY,
                PreflightResult(
                    source_kind=PreflightSourceKind.SIMILARITY,
                    capability=CapabilityStatus.PARTIAL,
                    completeness=ResultCompleteness.PARTIAL,
                    searched_scopes=("scope:similarity",),
                    next_cursor="2",
                    limitations=("additional page is available",),
                    plan=plan,
                ),
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "candidate lane next_cursor requires a provider call",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_candidate_lane_requirement_must_match_query_plan(self):
        plan = ContinuationPlan(
            query=AdvancedQuery.similarity(
                logical_target="example-implementation",
                capability="account-address-prediction",
                expected_outcome=None,
            ),
            max_pages=1,
            max_items=25,
        )
        result = PreflightResult(
            source_kind=PreflightSourceKind.SIMILARITY,
            capability=CapabilityStatus.SUPPORTED,
            completeness=ResultCompleteness.COMPLETE,
            searched_scopes=("scope:similarity",),
            plan=plan,
        )
        lane = CandidateLane(
            name="required-semantic-candidates",
            requirement=LaneRequirement.REQUIRED,
            source=FakeCandidateSource(
                PreflightSourceKind.SIMILARITY,
                result,
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "candidate lane requirement does not match query plan",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_partial_required_candidate_lane_blocks_write(self):
        lane = candidate_lane(
            requirement=LaneRequirement.REQUIRED,
            completeness=ResultCompleteness.PARTIAL,
            limitations=("query was interrupted before execution",),
        )

        with self.assertRaisesRegex(
            ValueError,
            "required candidate lane did not return complete",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_partial_advisory_similarity_is_preserved_without_blocking(self):
        lane = candidate_lane(
            requirement=LaneRequirement.ADVISORY,
            completeness=ResultCompleteness.PARTIAL,
            limitations=("provider search is rate limited",),
        )

        bundle = run_preflight(
            outbound_intent(),
            declarations=all_outbound_declarations(),
            sources=all_outbound_sources(),
            candidate_lanes=(lane,),
        )

        self.assertEqual(bundle.advisory_results, (lane.source.result,))
        self.assertEqual(
            bundle.advisory_results[0].limitations,
            ("provider search is rate limited",),
        )

    def test_required_unsupported_semantic_lane_blocks_write(self):
        lane = candidate_lane(
            requirement=LaneRequirement.REQUIRED,
            capability=CapabilityStatus.UNSUPPORTED,
            completeness=ResultCompleteness.UNSUPPORTED,
            limitations=("semantic search is unsupported",),
        )

        with self.assertRaisesRegex(
            ValueError,
            "required candidate lane did not return complete",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources(),
                candidate_lanes=(lane,),
            )

    def test_similarity_requires_an_explicit_candidate_lane(self):
        similarity = source(PreflightSourceKind.SIMILARITY)

        with self.assertRaisesRegex(
            ValueError,
            "similarity source requires an explicit candidate lane",
        ):
            run_preflight(
                outbound_intent(),
                declarations=all_outbound_declarations(),
                sources=all_outbound_sources() + (similarity,),
            )

    def test_not_applicable_requires_reason_and_skips_source(self):
        openspec_source = source(PreflightSourceKind.OPENSPEC)
        declarations = (
            declaration(PreflightSourceKind.NATIVE_WORK),
            declaration(
                PreflightSourceKind.OPENSPEC,
                SourceApplicability.NOT_APPLICABLE,
                "Target has no OpenSpec workspace.",
            ),
            declaration(PreflightSourceKind.DELIVERY),
        )
        sources = (
            source(PreflightSourceKind.NATIVE_WORK),
            openspec_source,
            source(PreflightSourceKind.DELIVERY),
        )

        bundle = run_preflight(
            outbound_intent(),
            declarations,
            sources,
        )

        self.assertEqual(len(bundle.results), 2)
        self.assertEqual(openspec_source.calls, [])

        invalid = list(declarations)
        invalid[1] = declaration(
            PreflightSourceKind.OPENSPEC,
            SourceApplicability.NOT_APPLICABLE,
        )
        with self.assertRaisesRegex(
            ValueError,
            "not-applicable source requires a reason",
        ):
            run_preflight(
                outbound_intent(),
                tuple(invalid),
                sources,
            )

    def test_enabled_source_requires_complete_result(self):
        bundle = run_preflight(
            outbound_intent(),
            all_outbound_declarations(),
            all_outbound_sources(),
            limit=25,
        )

        self.assertEqual(
            [result.source_kind for result in bundle.results],
            [
                PreflightSourceKind.NATIVE_WORK,
                PreflightSourceKind.OPENSPEC,
                PreflightSourceKind.DELIVERY,
            ],
        )
        self.assertTrue(
            all(
                result.completeness is ResultCompleteness.COMPLETE
                for result in bundle.results
            )
        )

    def test_partial_enabled_source_blocks_write(self):
        sources = list(all_outbound_sources())
        sources[1] = source(
            PreflightSourceKind.OPENSPEC,
            completeness=ResultCompleteness.PARTIAL,
        )

        with self.assertRaisesRegex(
            ValueError,
            "enabled source openspec did not return complete",
        ):
            run_preflight(
                outbound_intent(),
                all_outbound_declarations(),
                tuple(sources),
            )

    def test_unsupported_enabled_source_blocks_write(self):
        sources = list(all_outbound_sources())
        sources[2] = source(
            PreflightSourceKind.DELIVERY,
            completeness=ResultCompleteness.UNSUPPORTED,
        )

        with self.assertRaisesRegex(
            ValueError,
            "enabled source delivery did not return complete",
        ):
            run_preflight(
                outbound_intent(),
                all_outbound_declarations(),
                tuple(sources),
            )

    def test_outbound_work_requires_all_three_source_declarations(self):
        declarations = all_outbound_declarations()[:-1]

        with self.assertRaisesRegex(
            ValueError,
            "required source declarations",
        ):
            run_preflight(
                outbound_intent(),
                declarations,
                all_outbound_sources(),
            )

    def test_return_item_uses_only_return_intake_source(self):
        intake_source = source(PreflightSourceKind.RETURN_INTAKE)

        bundle = run_preflight(
            return_intent(),
            (declaration(PreflightSourceKind.RETURN_INTAKE),),
            (intake_source,),
        )

        self.assertEqual(len(bundle.results), 1)
        self.assertEqual(
            bundle.results[0].source_kind,
            PreflightSourceKind.RETURN_INTAKE,
        )

    def test_duplicate_source_declaration_is_rejected(self):
        declarations = all_outbound_declarations() + (
            declaration(PreflightSourceKind.NATIVE_WORK),
        )

        with self.assertRaisesRegex(
            ValueError,
            "duplicate source declaration",
        ):
            run_preflight(
                outbound_intent(),
                declarations,
                all_outbound_sources(),
            )

    def test_source_kind_mismatch_and_unbounded_limit_are_rejected(self):
        mismatched = FakeCandidateSource(
            PreflightSourceKind.NATIVE_WORK,
            complete_result(PreflightSourceKind.DELIVERY),
        )
        sources = (
            mismatched,
            source(PreflightSourceKind.OPENSPEC),
            source(PreflightSourceKind.DELIVERY),
        )

        with self.assertRaisesRegex(
            ValueError,
            "source kind mismatch",
        ):
            run_preflight(
                outbound_intent(),
                all_outbound_declarations(),
                sources,
            )

        with self.assertRaisesRegex(
            ValueError,
            "limit must be between 1 and 100",
        ):
            run_preflight(
                outbound_intent(),
                all_outbound_declarations(),
                all_outbound_sources(),
                limit=101,
            )

    def test_candidate_is_compact_and_immutable(self):
        candidate = Candidate(
            source_kind=PreflightSourceKind.NATIVE_WORK,
            provider_qualified_id="github:owner/repository#11",
            title="Existing work",
            status="open",
            updated="2026-07-30T10:00:00Z",
            url="https://github.com/owner/repository/issues/11",
        )

        self.assertFalse(hasattr(candidate, "body"))
        with self.assertRaisesRegex(
            AttributeError,
            "cannot assign to field",
        ):
            candidate.title = "Changed"

    def test_complete_source_rejects_malformed_candidate_metadata(self):
        malformed = Candidate(
            source_kind=PreflightSourceKind.NATIVE_WORK,
            provider_qualified_id="github:owner/repository#11",
            title="",
            status="open",
            updated="2026-07-30T10:00:00Z",
            url="https://github.com/owner/repository/issues/11",
        )
        sources = list(all_outbound_sources())
        sources[0] = FakeCandidateSource(
            PreflightSourceKind.NATIVE_WORK,
            complete_result(
                PreflightSourceKind.NATIVE_WORK,
                candidates=(malformed,),
            ),
        )

        with self.assertRaisesRegex(
            ValueError,
            "candidate title",
        ):
            run_preflight(
                outbound_intent(),
                all_outbound_declarations(),
                tuple(sources),
            )

    def test_complete_source_rejects_continuation_cursor(self):
        result = complete_result(PreflightSourceKind.NATIVE_WORK)
        invalid = PreflightResult(
            source_kind=result.source_kind,
            capability=result.capability,
            completeness=result.completeness,
            searched_scopes=result.searched_scopes,
            next_cursor="2",
        )
        sources = list(all_outbound_sources())
        sources[0] = FakeCandidateSource(
            PreflightSourceKind.NATIVE_WORK,
            invalid,
        )

        with self.assertRaisesRegex(
            ValueError,
            "complete source must not return next_cursor",
        ):
            run_preflight(
                outbound_intent(),
                all_outbound_declarations(),
                tuple(sources),
            )


if __name__ == "__main__":
    unittest.main()
