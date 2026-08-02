import sys
import unittest
from dataclasses import replace
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.models import (  # noqa: E402
    CapabilityStatus,
    ResultCompleteness,
    WorkItemSummary,
    WorkRoute,
)
from tools.architecture_handoff.adapter import AdapterBinding  # noqa: E402
from tools.architecture_handoff.protocol_metadata import (  # noqa: E402
    MetadataState,
    ProtocolMetadata,
)
from tools.architecture_handoff.query_coordinator import (  # noqa: E402
    QueryCoordinator,
    build_correlation_view,
    classify_stale_revisions,
)
from tools.architecture_handoff.query_models import (  # noqa: E402
    AdvancedQuery,
    ContinuationPlan,
    QueryPurpose,
    SearchHit,
    SearchPage,
)
from tools.architecture_handoff.write_models import (  # noqa: E402
    RelationKind,
    TypedRelation,
)


def inventory_query():
    return AdvancedQuery(
        purpose=QueryPurpose.INVENTORY,
        logical_target="example-implementation",
    )


def metadata(
    *,
    correlation_id=None,
    relations=(),
):
    return ProtocolMetadata(
        schema_version=2,
        logical_target="example-implementation",
        correlation_id=correlation_id,
        relations=relations,
    )


def hit(
    provider_id,
    *,
    metadata_state=MetadataState.MISSING,
    protocol_metadata=None,
    metadata_limitation=None,
    matched_signals=(),
    provider_rank=None,
):
    return SearchHit(
        item=WorkItemSummary(
            provider_id=provider_id,
            provider_qualified_id=(
                f"github:owner/repository#{provider_id}"
            ),
            title=f"Item {provider_id}",
            status="open",
            work_route=WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
            updated="2026-07-30T10:00:00Z",
            url=(
                "https://github.com/owner/repository/issues/"
                f"{provider_id}"
            ),
        ),
        metadata_state=metadata_state,
        protocol_metadata=protocol_metadata,
        metadata_limitation=metadata_limitation,
        matched_signals=matched_signals,
        provider_rank=provider_rank,
    )


def page(
    *,
    ids=(),
    hits=None,
    next_cursor=None,
    capability=CapabilityStatus.SUPPORTED,
    completeness=ResultCompleteness.COMPLETE,
    limitations=(),
    searched_scopes=("github:owner/repository",),
    provider_record_count=None,
):
    if hits is None:
        hits = tuple(hit(provider_id) for provider_id in ids)
    if provider_record_count is None:
        provider_record_count = len(hits)
    return SearchPage(
        purpose=QueryPurpose.INVENTORY,
        capability=capability,
        completeness=completeness,
        searched_scopes=searched_scopes,
        hits=tuple(hits),
        next_cursor=next_cursor,
        limitations=limitations,
        provider_record_count=provider_record_count,
    )


class FakeAdvancedAdapter:
    def __init__(self, *, pages):
        self.pages = pages
        self.queries = []
        self.get_item_calls = []

    def query_page(self, query):
        self.queries.append(query)
        return self.pages[len(self.queries) - 1]

    def get_item(self, provider_id):
        self.get_item_calls.append(provider_id)
        raise AssertionError("coordinator must not load full items")


class QueryCoordinatorTests(unittest.TestCase):
    def test_exposes_immutable_adapter_binding_when_present(self):
        binding = AdapterBinding(
            provider="github",
            provider_scope="owner/repository",
            logical_target="example-implementation",
        )
        adapter = FakeAdvancedAdapter(pages=())
        adapter.binding = binding

        coordinator = QueryCoordinator(adapter)

        self.assertEqual(coordinator.binding, binding)
        with self.assertRaises(AttributeError):
            binding.provider = "other"

    def test_preserves_fake_adapter_compatibility_without_binding(self):
        coordinator = QueryCoordinator(FakeAdvancedAdapter(pages=()))

        self.assertIsNone(coordinator.binding)

    def test_rejects_invalid_adapter_binding(self):
        adapter = FakeAdvancedAdapter(pages=())
        adapter.binding = {
            "provider": "github",
            "provider_scope": "owner/repository",
            "logical_target": "example-implementation",
        }

        with self.assertRaisesRegex(
            ValueError,
            "advanced adapter binding is invalid",
        ):
            QueryCoordinator(adapter)

    def test_explicit_plan_follows_cursor_and_records_every_call(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=("1",),
                    next_cursor="2",
                    searched_scopes=("scope:a",),
                ),
                page(ids=("2",), searched_scopes=("scope:b",)),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=10,
            )
        )

        self.assertEqual(
            [search_hit.item.provider_id for search_hit in coverage.hits],
            ["1", "2"],
        )
        self.assertEqual(
            [query.cursor for query in adapter.queries],
            [None, "2"],
        )
        self.assertEqual(
            [call.cursor for call in coverage.calls],
            [None, "2"],
        )
        self.assertEqual(
            [call.searched_scopes for call in coverage.calls],
            [("scope:a",), ("scope:b",)],
        )
        self.assertIs(coverage.completeness, ResultCompleteness.COMPLETE)
        self.assertEqual(adapter.get_item_calls, [])

    def test_each_page_is_capped_by_remaining_provider_record_budget(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=tuple(str(value) for value in range(1, 101)),
                    next_cursor="2",
                ),
                page(ids=tuple(str(value) for value in range(101, 151))),
            )
        )
        query = replace(inventory_query(), limit=100)
        plan = ContinuationPlan(
            query=query,
            max_pages=2,
            max_items=150,
        )

        coverage = QueryCoordinator(adapter).execute(plan)

        self.assertEqual(
            [page_query.limit for page_query in adapter.queries],
            [100, 50],
        )
        self.assertEqual(len(coverage.hits), 150)
        self.assertIs(coverage.completeness, ResultCompleteness.COMPLETE)
        self.assertIsNone(coverage.next_cursor)
        self.assertEqual(coverage.plan, plan)
        self.assertEqual(coverage.plan.query.limit, 100)

    def test_filtered_provider_records_consume_item_budget(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    hits=(),
                    provider_record_count=2,
                    next_cursor="2",
                ),
                page(
                    ids=("3",),
                    provider_record_count=1,
                    next_cursor="3",
                ),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=replace(inventory_query(), limit=2),
                max_pages=3,
                max_items=3,
            )
        )

        self.assertEqual(
            [page_query.limit for page_query in adapter.queries],
            [2, 1],
        )
        self.assertEqual(len(coverage.calls), 2)
        self.assertEqual(
            [search_hit.item.provider_id for search_hit in coverage.hits],
            ["3"],
        )
        self.assertIs(coverage.completeness, ResultCompleteness.PARTIAL)
        self.assertEqual(coverage.next_cursor, "3")
        self.assertIn(
            "continuation plan item bound reached",
            coverage.limitations,
        )

    def test_duplicate_provider_records_consume_item_budget(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(ids=("1", "2"), next_cursor="2"),
                page(ids=("2",), next_cursor="3"),
                page(ids=("3",)),
            )
        )
        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=replace(inventory_query(), limit=2),
                max_pages=3,
                max_items=3,
            )
        )

        self.assertEqual(
            [page_query.limit for page_query in adapter.queries],
            [2, 1],
        )
        self.assertEqual(
            [search_hit.item.provider_id for search_hit in coverage.hits],
            ["1", "2"],
        )
        self.assertIs(coverage.completeness, ResultCompleteness.PARTIAL)
        self.assertEqual(coverage.next_cursor, "3")

    def test_bound_reached_before_cursor_exhaustion_is_partial(self):
        adapter = FakeAdvancedAdapter(
            pages=(page(ids=("1",), next_cursor="2"),)
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=1,
                max_items=10,
            )
        )

        self.assertIs(coverage.completeness, ResultCompleteness.PARTIAL)
        self.assertEqual(coverage.next_cursor, "2")
        self.assertIn(
            "continuation plan page bound reached",
            coverage.limitations,
        )

    def test_duplicate_identity_is_deduplicated_without_rescoring(self):
        first_duplicate = hit(
            "2",
            matched_signals=("first-page",),
            provider_rank=2,
        )
        later_duplicate = hit(
            "2",
            matched_signals=("later-page",),
            provider_rank=1,
        )
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    hits=(hit("1"), first_duplicate),
                    next_cursor="2",
                ),
                page(hits=(later_duplicate, hit("3"))),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=10,
            )
        )

        self.assertEqual(
            [search_hit.item.provider_id for search_hit in coverage.hits],
            ["1", "2", "3"],
        )
        self.assertEqual(coverage.hits[1].provider_rank, 2)
        self.assertEqual(
            coverage.hits[1].matched_signals,
            ("first-page",),
        )

    def test_item_bound_keeps_first_seen_hits_and_is_partial(self):
        adapter = FakeAdvancedAdapter(
            pages=(page(ids=("3", "1", "2"), next_cursor="2"),)
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=2,
            )
        )

        self.assertEqual(
            [search_hit.item.provider_id for search_hit in coverage.hits],
            ["3", "1"],
        )
        self.assertIs(coverage.completeness, ResultCompleteness.PARTIAL)
        self.assertIn(
            "continuation plan item bound reached",
            coverage.limitations,
        )

    def test_provider_limitations_and_weakest_capability_are_preserved(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=("1",),
                    next_cursor="2",
                    capability=CapabilityStatus.PARTIAL,
                    limitations=("provider search is lexical",),
                ),
                page(ids=("2",)),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=10,
            )
        )

        self.assertIs(coverage.capability, CapabilityStatus.PARTIAL)
        self.assertIn("provider search is lexical", coverage.limitations)

    def test_terminal_provider_completeness_is_not_upgraded(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=("1",),
                    completeness=ResultCompleteness.PARTIAL,
                    limitations=("provider returned incomplete results",),
                ),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=10,
            )
        )

        self.assertIs(coverage.completeness, ResultCompleteness.PARTIAL)
        self.assertIn(
            "provider returned incomplete results",
            coverage.limitations,
        )

    def test_earlier_intrinsic_partial_survives_terminal_complete(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=("1",),
                    next_cursor="2",
                    completeness=ResultCompleteness.PARTIAL,
                    limitations=("provider returned incomplete results",),
                ),
                page(ids=("2",)),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=10,
            )
        )

        self.assertIs(coverage.completeness, ResultCompleteness.PARTIAL)
        self.assertIn(
            "provider returned incomplete results",
            coverage.limitations,
        )

    def test_earlier_unsupported_survives_terminal_complete(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=("1",),
                    next_cursor="2",
                    completeness=ResultCompleteness.UNSUPPORTED,
                    limitations=("provider result is unsupported",),
                ),
                page(ids=("2",)),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=10,
            )
        )

        self.assertIs(
            coverage.completeness,
            ResultCompleteness.UNSUPPORTED,
        )
        self.assertIn(
            "provider result is unsupported",
            coverage.limitations,
        )

    def test_page_bound_does_not_upgrade_unsupported(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=("1",),
                    next_cursor="2",
                    completeness=ResultCompleteness.UNSUPPORTED,
                    limitations=("provider result is unsupported",),
                ),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=1,
                max_items=10,
            )
        )

        self.assertIs(
            coverage.completeness,
            ResultCompleteness.UNSUPPORTED,
        )
        self.assertIn(
            "continuation plan page bound reached",
            coverage.limitations,
        )

    def test_item_bound_does_not_upgrade_unsupported(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=("1", "2"),
                    completeness=ResultCompleteness.UNSUPPORTED,
                    limitations=("provider result is unsupported",),
                ),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=1,
            )
        )

        self.assertIs(
            coverage.completeness,
            ResultCompleteness.UNSUPPORTED,
        )
        self.assertIn(
            "continuation plan item bound reached",
            coverage.limitations,
        )

    def test_cursor_limitation_with_another_limitation_stays_partial(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=("1",),
                    next_cursor="2",
                    completeness=ResultCompleteness.PARTIAL,
                    limitations=(
                        "additional provider page is available",
                        "provider returned incomplete results",
                    ),
                ),
                page(ids=("2",)),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=10,
            )
        )

        self.assertIs(coverage.completeness, ResultCompleteness.PARTIAL)
        self.assertIn(
            "additional provider page is available",
            coverage.limitations,
        )
        self.assertIn(
            "provider returned incomplete results",
            coverage.limitations,
        )

    def test_cursor_only_partial_stays_partial_for_terminal_limitation(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=("1",),
                    next_cursor="2",
                    completeness=ResultCompleteness.PARTIAL,
                    limitations=("additional provider page is available",),
                ),
                page(
                    ids=("2",),
                    limitations=("terminal provider limitation",),
                ),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=10,
            )
        )

        self.assertIs(coverage.completeness, ResultCompleteness.PARTIAL)
        self.assertIn(
            "terminal provider limitation",
            coverage.limitations,
        )
        self.assertNotIn(
            "additional provider page is available",
            coverage.limitations,
        )

    def test_cursor_only_partial_is_complete_after_exhaustion(self):
        adapter = FakeAdvancedAdapter(
            pages=(
                page(
                    ids=("1",),
                    next_cursor="2",
                    completeness=ResultCompleteness.PARTIAL,
                    limitations=("additional provider page is available",),
                ),
                page(ids=("2",)),
            )
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=2,
                max_items=10,
            )
        )

        self.assertIs(coverage.completeness, ResultCompleteness.COMPLETE)
        self.assertNotIn(
            "additional provider page is available",
            coverage.limitations,
        )


class CorrelationViewTests(unittest.TestCase):
    def test_uses_only_verified_metadata_for_requested_correlation(self):
        linked = hit(
            "1",
            metadata_state=MetadataState.VERIFIED,
            protocol_metadata=metadata(
                correlation_id="corr-12",
                relations=(
                    TypedRelation(
                        kind=RelationKind.IMPLEMENTATION,
                        target=(
                            "github:owner/repository#2"
                        ),
                    ),
                ),
            ),
        )
        resolved = hit(
            "2",
            metadata_state=MetadataState.VERIFIED,
            protocol_metadata=metadata(correlation_id="corr-12"),
        )
        different = hit(
            "3",
            metadata_state=MetadataState.VERIFIED,
            protocol_metadata=metadata(
                correlation_id="corr-other",
                relations=(
                    TypedRelation(
                        kind=RelationKind.CORRELATION,
                        target="github:owner/repository#1",
                    ),
                ),
            ),
        )
        coverage = QueryCoordinator(
            FakeAdvancedAdapter(
                pages=(page(hits=(linked, resolved, different)),)
            )
        ).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=1,
                max_items=10,
            )
        )

        view = build_correlation_view(coverage, "corr-12")

        self.assertEqual(
            [node.provider_qualified_id for node in view.nodes],
            [
                "github:owner/repository#1",
                "github:owner/repository#2",
            ],
        )
        self.assertEqual(
            view.nodes[0].relation_targets,
            ("github:owner/repository#2",),
        )
        self.assertEqual(view.unresolved_targets, ())
        self.assertIs(view.completeness, ResultCompleteness.COMPLETE)

    def test_unresolved_forward_targets_are_explicit_and_not_inferred(self):
        linked = hit(
            "1",
            metadata_state=MetadataState.VERIFIED,
            protocol_metadata=metadata(
                correlation_id="corr-12",
                relations=(
                    TypedRelation(
                        kind=RelationKind.IMPLEMENTATION,
                        target=(
                            "github:owner/repository#99"
                        ),
                    ),
                    TypedRelation(
                        kind=RelationKind.VALIDATION,
                        target=(
                            "github:owner/repository#99"
                        ),
                    ),
                ),
            ),
        )
        coverage = QueryCoordinator(
            FakeAdvancedAdapter(pages=(page(hits=(linked,)),))
        ).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=1,
                max_items=10,
            )
        )

        view = build_correlation_view(coverage, "corr-12")

        self.assertEqual(
            view.unresolved_targets,
            ("github:owner/repository#99",),
        )

    def test_missing_and_malformed_metadata_are_partial_evidence(self):
        coverage = QueryCoordinator(
            FakeAdvancedAdapter(
                pages=(
                    page(
                        hits=(
                            hit(
                                "1",
                                metadata_limitation=(
                                    "versioned protocol metadata is missing"
                                ),
                            ),
                            hit(
                                "2",
                                metadata_state=MetadataState.MALFORMED,
                                metadata_limitation=(
                                    "protocol marker block is incomplete"
                                ),
                            ),
                        )
                    ),
                )
            )
        ).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=1,
                max_items=10,
            )
        )

        view = build_correlation_view(coverage, "corr-12")

        self.assertIs(view.completeness, ResultCompleteness.PARTIAL)
        self.assertEqual(view.nodes, ())
        self.assertTrue(
            any(
                "github:owner/repository#1" in limitation
                and "missing" in limitation
                for limitation in view.limitations
            )
        )
        self.assertTrue(
            any(
                "github:owner/repository#2" in limitation
                and "incomplete" in limitation
                for limitation in view.limitations
            )
        )


class StaleRevisionTests(unittest.TestCase):
    def _coverage(self, *hits):
        return QueryCoordinator(
            FakeAdvancedAdapter(pages=(page(hits=hits),))
        ).execute(
            ContinuationPlan(
                query=inventory_query(),
                max_pages=1,
                max_items=20,
            )
        )

    def test_equal_revision_is_current(self):
        source_hit = hit(
            "1",
            metadata_state=MetadataState.VERIFIED,
            protocol_metadata=metadata(
                relations=(
                    TypedRelation(
                        kind=RelationKind.IMPLEMENTATION,
                        target="ADR-0003",
                        revision="abc123",
                    ),
                )
            ),
        )

        report = classify_stale_revisions(
            self._coverage(source_hit),
            "ADR-0003",
            "abc123",
        )

        self.assertEqual(report.entries[0].classification, "current")
        self.assertEqual(report.entries[0].observed_revision, "abc123")
        self.assertIs(report.completeness, ResultCompleteness.COMPLETE)

    def test_unequal_revision_is_stale(self):
        source_hit = hit(
            "1",
            metadata_state=MetadataState.VERIFIED,
            protocol_metadata=metadata(
                relations=(
                    TypedRelation(
                        kind=RelationKind.IMPLEMENTATION,
                        target="ADR-0003",
                        revision="old456",
                    ),
                )
            ),
        )

        report = classify_stale_revisions(
            self._coverage(source_hit),
            "ADR-0003",
            "abc123",
        )

        self.assertEqual(report.entries[0].classification, "stale")
        self.assertEqual(report.entries[0].observed_revision, "old456")
        self.assertIs(report.completeness, ResultCompleteness.COMPLETE)

    def test_missing_revision_is_explicit_and_partial(self):
        source_hit = hit(
            "1",
            metadata_state=MetadataState.VERIFIED,
            protocol_metadata=metadata(
                relations=(
                    TypedRelation(
                        kind=RelationKind.IMPLEMENTATION,
                        target="ADR-0003",
                    ),
                )
            ),
        )

        report = classify_stale_revisions(
            self._coverage(source_hit),
            "ADR-0003",
            "abc123",
        )

        self.assertEqual(
            report.entries[0].classification,
            "missing-revision",
        )
        self.assertIsNone(report.entries[0].observed_revision)
        self.assertIs(report.completeness, ResultCompleteness.PARTIAL)
        self.assertTrue(
            any("revision is missing" in item for item in report.limitations)
        )

    def test_malformed_metadata_is_explicit_and_partial(self):
        malformed_hit = hit(
            "1",
            metadata_state=MetadataState.MALFORMED,
            metadata_limitation="malformed relation JSON",
        )

        report = classify_stale_revisions(
            self._coverage(malformed_hit),
            "ADR-0003",
            "abc123",
        )

        self.assertEqual(
            report.entries[0].classification,
            "malformed-metadata",
        )
        self.assertIsNone(report.entries[0].observed_revision)
        self.assertIs(report.completeness, ResultCompleteness.PARTIAL)
        self.assertTrue(
            any(
                "malformed relation JSON" in item
                for item in report.limitations
            )
        )

    def test_missing_metadata_is_partial_without_inferred_relation(self):
        report = classify_stale_revisions(
            self._coverage(
                hit(
                    "1",
                    metadata_limitation=(
                        "versioned protocol metadata is missing"
                    ),
                )
            ),
            "ADR-0003",
            "abc123",
        )

        self.assertEqual(report.entries, ())
        self.assertIs(report.completeness, ResultCompleteness.PARTIAL)
        self.assertTrue(
            any("metadata is missing" in item for item in report.limitations)
        )

    def test_nonmatching_forward_relation_is_not_classified(self):
        source_hit = hit(
            "1",
            metadata_state=MetadataState.VERIFIED,
            protocol_metadata=metadata(
                relations=(
                    TypedRelation(
                        kind=RelationKind.IMPLEMENTATION,
                        target="ADR-00030",
                        revision="old456",
                    ),
                )
            ),
        )

        report = classify_stale_revisions(
            self._coverage(source_hit),
            "ADR-0003",
            "abc123",
        )

        self.assertEqual(report.entries, ())
        self.assertIs(report.completeness, ResultCompleteness.COMPLETE)


if __name__ == "__main__":
    unittest.main()
