import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.models import WorkRoute  # noqa: E402
from tools.architecture_handoff.query_models import (  # noqa: E402
    AdvancedQuery,
    ContinuationPlan,
    LaneRequirement,
    QueryPurpose,
    SimilarityMode,
)
from tools.architecture_handoff.write_models import (  # noqa: E402
    IntakeState,
    ReturnKind,
)


class QueryModelTests(unittest.TestCase):
    def test_return_query_requires_pending_or_handled_state(self):
        query = AdvancedQuery(
            purpose=QueryPurpose.RETURN_INTAKE,
            logical_target="example-implementation",
            intake_state=IntakeState.PENDING,
            return_kind=ReturnKind.EVIDENCE_RESULT,
        )

        self.assertEqual(query.limit, 50)

    def test_return_query_rejects_missing_or_invalid_intake_state(self):
        with self.assertRaisesRegex(
            ValueError,
            "return-intake requires intake_state",
        ):
            AdvancedQuery(
                purpose=QueryPurpose.RETURN_INTAKE,
                logical_target="example-implementation",
            )
        with self.assertRaisesRegex(
            ValueError,
            "intake_state must be a IntakeState",
        ):
            AdvancedQuery(
                purpose=QueryPurpose.RETURN_INTAKE,
                logical_target="example-implementation",
                intake_state="pending",
            )

    def test_stale_query_requires_source_and_current_revision(self):
        with self.assertRaisesRegex(
            ValueError,
            "stale-revision requires source_reference and current_revision",
        ):
            AdvancedQuery(
                purpose=QueryPurpose.STALE_REVISION,
                logical_target="example-implementation",
                source_reference="ADR-0003",
            )

    def test_required_purpose_predicates_are_enforced(self):
        cases = (
            (QueryPurpose.SOURCE_TRACEABILITY, {}, "source-traceability"),
            (QueryPurpose.CORRELATION, {}, "correlation requires correlation_id"),
            (QueryPurpose.SIMILARITY, {}, "similarity requires capability"),
        )
        for purpose, fields, message in cases:
            with self.subTest(purpose=purpose):
                with self.assertRaisesRegex(ValueError, message):
                    AdvancedQuery(
                        purpose=purpose,
                        logical_target="example-implementation",
                        **fields,
                    )

    def test_similarity_requires_text_and_defaults_to_advisory_hybrid(self):
        query = AdvancedQuery.similarity(
            logical_target="example-implementation",
            capability="account-address-prediction",
            expected_outcome="Return one deterministic address",
        )

        self.assertIs(query.requirement, LaneRequirement.ADVISORY)
        self.assertIs(query.similarity_mode, SimilarityMode.HYBRID)

    def test_direct_similarity_keeps_required_default(self):
        query = AdvancedQuery(
            purpose=QueryPurpose.SIMILARITY,
            logical_target="example-implementation",
            capability="account-address-prediction",
        )

        self.assertIs(query.requirement, LaneRequirement.REQUIRED)

    def test_provider_syntax_and_conflicting_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "provider syntax"):
            AdvancedQuery(
                purpose=QueryPurpose.SOURCE_TRACEABILITY,
                logical_target="repo:owner/name",
                source_reference="ADR-0003",
            )
        with self.assertRaisesRegex(ValueError, "not valid for inventory"):
            AdvancedQuery(
                purpose=QueryPurpose.INVENTORY,
                logical_target="example-implementation",
                correlation_id="corr-12",
            )

    def test_purpose_allow_list_rejects_unrelated_predicates(self):
        cases = (
            (
                QueryPurpose.SOURCE_TRACEABILITY,
                {"correlation_id": "corr-12"},
                "not valid for source-traceability",
            ),
            (
                QueryPurpose.CORRELATION,
                {"source_reference": "ADR-0003"},
                "not valid for correlation",
            ),
            (
                QueryPurpose.RETURN_INTAKE,
                {
                    "intake_state": IntakeState.PENDING,
                    "routes": (WorkRoute.SPIKE_EVIDENCE,),
                },
                "not valid for return-intake",
            ),
            (
                QueryPurpose.SIMILARITY,
                {
                    "capability": "account-address-prediction",
                    "current_revision": "abc123",
                },
                "not valid for similarity",
            ),
        )
        for purpose, fields, message in cases:
            with self.subTest(purpose=purpose, fields=fields):
                with self.assertRaisesRegex(ValueError, message):
                    AdvancedQuery(
                        purpose=purpose,
                        logical_target="example-implementation",
                        **fields,
                    )

    def test_query_rejects_invalid_limit_cursor_and_enums(self):
        for fields, message in (
            ({"limit": 0}, "limit must be between 1 and 100"),
            ({"limit": 101}, "limit must be between 1 and 100"),
            ({"cursor": "0"}, "cursor must be a positive integer string"),
            ({"cursor": "next"}, "cursor must be a positive integer string"),
            ({"requirement": "advisory"}, "requirement must be a LaneRequirement"),
            ({"routes": ("spike-evidence",)}, "routes must contain WorkRoute"),
        ):
            with self.subTest(fields=fields):
                with self.assertRaisesRegex(ValueError, message):
                    AdvancedQuery(
                        purpose=QueryPurpose.INVENTORY,
                        logical_target="example-implementation",
                        **fields,
                    )

    def test_return_correlation_requires_exact_intake_predicates(self):
        query = AdvancedQuery(
            purpose=QueryPurpose.RETURN_CORRELATION,
            logical_target="documentation-intake",
            correlation_id="corr-12",
            intake_state=IntakeState.PENDING,
            return_kind=ReturnKind.EVIDENCE_RESULT,
            limit=100,
        )

        self.assertEqual(query.correlation_id, "corr-12")
        self.assertIs(query.intake_state, IntakeState.PENDING)
        self.assertIs(query.return_kind, ReturnKind.EVIDENCE_RESULT)

        for omitted, message in (
            ("correlation_id", "correlation_id and intake_state"),
            ("intake_state", "correlation_id and intake_state"),
        ):
            fields = {
                "correlation_id": "corr-12",
                "intake_state": IntakeState.PENDING,
            }
            fields.pop(omitted)
            with self.subTest(omitted=omitted):
                with self.assertRaisesRegex(ValueError, message):
                    AdvancedQuery(
                        purpose=QueryPurpose.RETURN_CORRELATION,
                        logical_target="documentation-intake",
                        **fields,
                    )

    def test_query_and_continuation_bounds_reject_non_integers(self):
        with self.assertRaisesRegex(ValueError, "limit must be between 1 and 100"):
            AdvancedQuery(
                purpose=QueryPurpose.INVENTORY,
                logical_target="example-implementation",
                limit="50",
            )
        query = AdvancedQuery(
            purpose=QueryPurpose.INVENTORY,
            logical_target="example-implementation",
        )
        with self.assertRaisesRegex(ValueError, "max_pages"):
            ContinuationPlan(query=query, max_pages="3", max_items=200)
        with self.assertRaisesRegex(ValueError, "max_items"):
            ContinuationPlan(query=query, max_pages=3, max_items="200")

    def test_continuation_plan_is_bounded_and_immutable(self):
        query = AdvancedQuery(
            purpose=QueryPurpose.INVENTORY,
            logical_target="example-implementation",
            routes=(WorkRoute.ARCHITECTURE_SLICE_HANDOFF,),
        )
        plan = ContinuationPlan(query=query, max_pages=3, max_items=200)
        with self.assertRaises(FrozenInstanceError):
            plan.max_pages = 4
        with self.assertRaisesRegex(ValueError, "max_pages"):
            ContinuationPlan(query=query, max_pages=0, max_items=200)
        with self.assertRaisesRegex(ValueError, "max_items"):
            ContinuationPlan(query=query, max_pages=3, max_items=0)

    def test_runtime_policy_not_model_sets_continuation_ceiling(self):
        query = AdvancedQuery(
            purpose=QueryPurpose.INVENTORY,
            logical_target="example-implementation",
        )

        plan = ContinuationPlan(
            query=query,
            max_pages=21,
            max_items=2001,
        )

        self.assertEqual(plan.max_pages, 21)
        self.assertEqual(plan.max_items, 2001)

    def test_continuation_plan_cannot_start_from_a_cursor(self):
        query = AdvancedQuery(
            purpose=QueryPurpose.INVENTORY,
            logical_target="example-implementation",
            cursor="1",
        )

        with self.assertRaisesRegex(
            ValueError,
            "continuation plan query must start without cursor",
        ):
            ContinuationPlan(query=query, max_pages=3, max_items=200)


if __name__ == "__main__":
    unittest.main()
