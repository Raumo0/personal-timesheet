import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.adapter import (  # noqa: E402
    AdvancedReadAdapter,
    QueryRequest,
    ReadAdapter,
)
from tools.architecture_handoff.core import build_inventory  # noqa: E402
from tools.architecture_handoff.models import (  # noqa: E402
    QueryResult,
    ResultCompleteness,
    WorkItemSummary,
    WorkRoute,
)


def item(provider_id, route):
    return WorkItemSummary(
        provider_id=str(provider_id),
        provider_qualified_id=(
            f"github:owner/repository#{provider_id}"
        ),
        title=f"Task {provider_id}",
        status="ready",
        work_route=route,
        updated="2026-07-30T10:00:00Z",
        url=(
            "https://github.com/owner/repository/issues/"
            f"{provider_id}"
        ),
    )


class CoreTests(unittest.TestCase):
    def test_advanced_read_adapter_extends_existing_read_contract(self):
        self.assertIn(ReadAdapter, AdvancedReadAdapter.__bases__)
        self.assertTrue(hasattr(AdvancedReadAdapter, "query_page"))

    def test_inventory_counts_every_category_in_stable_order(self):
        result = QueryResult(
            items=(
                item(1, WorkRoute.ARCHITECTURE_SLICE_HANDOFF),
                item(2, WorkRoute.ARCHITECTURE_SLICE_HANDOFF),
                item(3, WorkRoute.IMPLEMENTATION_CONFORMANCE_REFERRAL),
                item(4, WorkRoute.SPIKE_EVIDENCE),
                item(5, WorkRoute.TARGET_NATIVE_INTERNAL),
            ),
            completeness=ResultCompleteness.COMPLETE,
            searched_scopes=("github:owner/repository:open-issues",),
        )

        inventory = build_inventory(result)

        self.assertEqual(
            list(inventory.counts.items()),
            [
                (WorkRoute.ARCHITECTURE_SLICE_HANDOFF, 2),
                (WorkRoute.IMPLEMENTATION_CONFORMANCE_REFERRAL, 1),
                (WorkRoute.SPIKE_EVIDENCE, 1),
                (WorkRoute.TARGET_NATIVE_INTERNAL, 1),
            ],
        )

    def test_inventory_keeps_zero_count_categories(self):
        result = QueryResult(
            items=(item(1, WorkRoute.TARGET_NATIVE_INTERNAL),),
            completeness=ResultCompleteness.COMPLETE,
            searched_scopes=("github:owner/repository:open-issues",),
        )

        inventory = build_inventory(result)

        self.assertEqual(
            inventory.counts[WorkRoute.ARCHITECTURE_SLICE_HANDOFF],
            0,
        )
        self.assertEqual(inventory.counts[WorkRoute.TARGET_NATIVE_INTERNAL], 1)

    def test_inventory_preserves_partial_result_metadata(self):
        result = QueryResult(
            items=(),
            completeness=ResultCompleteness.PARTIAL,
            searched_scopes=("github:owner/repository:open-issues",),
            next_cursor="2",
            limitations=("additional provider page is available",),
        )

        inventory = build_inventory(result)

        self.assertEqual(inventory.completeness, ResultCompleteness.PARTIAL)
        self.assertEqual(inventory.next_cursor, "2")
        self.assertEqual(
            inventory.limitations,
            ("additional provider page is available",),
        )

    def test_query_request_rejects_unbounded_limit(self):
        for value in (0, 101):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError, "limit must be between 1 and 100"
                ):
                    QueryRequest(limit=value)

    def test_query_request_rejects_two_lookup_keys(self):
        with self.assertRaisesRegex(
            ValueError,
            "source_reference and correlation_id are mutually exclusive",
        ):
            QueryRequest(
                source_reference="ADR-0003",
                correlation_id="corr-123",
            )

    def test_query_request_rejects_empty_lookup_keys(self):
        for field in ("source_reference", "correlation_id"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    ValueError,
                    f"{field} must be a non-empty string",
                ):
                    QueryRequest(**{field: ""})

    def test_query_request_rejects_invalid_cursor(self):
        for cursor in ("0", "next", "-1"):
            with self.subTest(cursor=cursor):
                with self.assertRaisesRegex(
                    ValueError,
                    "cursor must be a positive integer string",
                ):
                    QueryRequest(cursor=cursor)


if __name__ == "__main__":
    unittest.main()
