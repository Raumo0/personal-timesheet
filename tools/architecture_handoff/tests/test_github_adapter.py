import io
import json
import sys
import traceback
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.adapter import (  # noqa: E402
    AdapterBinding,
    QueryRequest,
)
from tools.architecture_handoff import github as github_module  # noqa: E402
from tools.architecture_handoff.github import (  # noqa: E402
    AdapterError,
    GitHubReadAdapter,
    GitHubRestTransport,
    SameOriginRedirectHandler,
    next_page_cursor,
)
from tools.architecture_handoff.models import (  # noqa: E402
    CapabilityStatus,
    ResultCompleteness,
    WorkRoute,
)
from tools.architecture_handoff.protocol_metadata import (  # noqa: E402
    MetadataState,
)
from tools.architecture_handoff.query_models import (  # noqa: E402
    AdvancedQuery,
    ContinuationPlan,
    QueryPurpose,
    SimilarityMode,
)
from tools.architecture_handoff.query_coordinator import (  # noqa: E402
    QueryCoordinator,
)
from tools.architecture_handoff.write_models import (  # noqa: E402
    IntakeState,
    ReturnKind,
)


FIXTURE = (
    Path(__file__).parent / "fixtures" / "github_issues_page.json"
)
ADVANCED_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "github_advanced_search_page.json"
)


class FakeTransport:
    def __init__(self, payload, next_cursor=None):
        self.payload = payload
        self.next_cursor = next_cursor
        self.responses = []
        self.requests = []
        self.calls = self.requests

    def get(self, path, params):
        self.requests.append((path, params))
        if self.responses:
            return self.responses.pop(0)
        if path.startswith("search/"):
            return {"items": self.payload}, self.next_cursor
        if path.endswith("/issues/11"):
            return self.payload[0], None
        return self.payload, self.next_cursor


class FakeResponse:
    def __init__(self, payload, link=None):
        self._payload = payload
        self.headers = {"Link": link} if link else {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def return_issue(
    number,
    correlation_id,
    *,
    malformed=False,
    pull_request=False,
):
    body = (
        "<!-- architecture-handoff-protocol\n"
        "schema-version: 2\n"
        "logical-target: documentation-intake\n"
        f"correlation-id: {correlation_id}\n"
        "relation: "
        '{"kind":"return","revision":null,'
        '"target":"github:owner/implementation#12"}'
        "\n-->"
    )
    if malformed:
        body = body.removesuffix("-->")
    record = {
        "number": number,
        "title": f"Return {number}",
        "state": "open",
        "updated_at": "2026-07-31T10:00:00Z",
        "html_url": (
            f"https://github.com/owner/repository/issues/{number}"
        ),
        "body": body,
        "labels": [
            {"name": "return-kind:evidence-result"},
            {"name": "intake-state:pending"},
        ],
    }
    if pull_request:
        record["pull_request"] = {
            "url": "https://api.github.com/repos/owner/repository/pulls/1"
        }
    return record


class RawResponse(FakeResponse):
    def read(self):
        return self._payload


class TrackedErrorBody(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


class GitHubReadAdapterTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.advanced_payload = json.loads(
            ADVANCED_FIXTURE.read_text(encoding="utf-8")
        )
        self.transport = FakeTransport(self.payload)
        self.adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
        )

    def test_exposes_exact_provider_binding_when_logical_target_is_bound(self):
        adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
            logical_target="example-implementation",
        )

        self.assertEqual(
            adapter.binding,
            AdapterBinding(
                provider="github",
                provider_scope="owner/repository",
                logical_target="example-implementation",
            ),
        )

    def test_legacy_unbound_adapter_has_no_physical_binding(self):
        self.assertIsNone(self.adapter.binding)

    def test_advanced_normalization_rejects_invalid_issue_identity_and_url(self):
        base = dict(self.advanced_payload["items"][0])
        cases = (
            (
                {**base, "number": 0},
                "positive integer",
            ),
            (
                {**base, "number": "21"},
                "positive integer",
            ),
            (
                {**base, "number": True},
                "positive integer",
            ),
            (
                {
                    **base,
                    "html_url": (
                        "https://github.com/owner/other/issues/21"
                    ),
                },
                "URL does not match",
            ),
            (
                {
                    **base,
                    "html_url": (
                        "https://github.com/"
                        "owner/repository/issues/22"
                    ),
                },
                "URL does not match",
            ),
        )
        for record, expected in cases:
            with self.subTest(expected=expected, record=record):
                self.transport.responses.append(([record], None))
                with self.assertRaisesRegex(AdapterError, expected):
                    self.adapter.query_page(
                        AdvancedQuery(
                            purpose=QueryPurpose.INVENTORY,
                            logical_target="example-implementation",
                        )
                    )

    def test_advanced_normalization_uses_shared_protocol_label_validation(self):
        base = dict(self.advanced_payload["items"][0])
        cases = (
            (("status:invented",), "unsupported status"),
            (("return-kind:invented",), "unsupported return-kind"),
            (("intake-state:invented",), "unsupported intake-state"),
            (
                ("status:draft", "status:ready"),
                "multiple status",
            ),
            (
                (
                    "work-route:architecture-slice-handoff",
                    "return-kind:evidence-result",
                    "intake-state:pending",
                ),
                "work item must not carry return or intake",
            ),
            (
                (
                    "return-kind:evidence-result",
                    "intake-state:pending",
                    "status:ready",
                ),
                "Return Item must not carry status",
            ),
        )
        for labels, expected in cases:
            with self.subTest(labels=labels):
                record = {
                    **base,
                    "labels": [{"name": label} for label in labels],
                }
                self.transport.responses.append(([record], None))
                with self.assertRaisesRegex(AdapterError, expected):
                    self.adapter.query_page(
                        AdvancedQuery(
                            purpose=QueryPurpose.INVENTORY,
                            logical_target="example-implementation",
                        )
                    )

    def test_advanced_normalization_preserves_native_and_return_labels(self):
        base = dict(self.advanced_payload["items"][0])
        records = (
            {
                **base,
                "labels": [{"name": "team:platform"}],
            },
            {
                **base,
                "number": 22,
                "html_url": (
                    "https://github.com/"
                    "owner/repository/issues/22"
                ),
                "labels": [
                    {"name": "return-kind:evidence-result"},
                    {"name": "intake-state:pending"},
                    {"name": "team:research"},
                ],
            },
        )
        self.transport.responses.append((list(records), None))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.INVENTORY,
                logical_target="example-implementation",
            )
        )

        self.assertEqual(
            [hit.item.work_route for hit in page.hits],
            [
                WorkRoute.TARGET_NATIVE_INTERNAL,
                WorkRoute.TARGET_NATIVE_INTERNAL,
            ],
        )
        self.assertEqual(page.hits[0].item.labels, ("team:platform",))
        self.assertIn("team:research", page.hits[1].item.labels)

    def test_return_query_uses_two_exact_labels(self):
        self.transport.responses.append(([], None))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.RETURN_INTAKE,
                logical_target="example-implementation",
                intake_state=IntakeState.PENDING,
                return_kind=ReturnKind.EVIDENCE_RESULT,
            )
        )

        path, params = self.transport.requests[0]
        self.assertEqual(
            path,
            "repos/owner/repository/issues",
        )
        self.assertEqual(
            params["labels"],
            "return-kind:evidence-result,intake-state:pending",
        )
        self.assertIs(page.capability, CapabilityStatus.SUPPORTED)
        self.assertEqual(len(self.transport.requests), 1)

    def test_return_correlation_uses_label_page_then_exact_metadata(self):
        self.transport.responses.append(
            (
                [
                    return_issue(31, "corr-12"),
                    return_issue(32, "corr-other"),
                ],
                None,
            )
        )
        adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
            logical_target="documentation-intake",
        )

        page = adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.RETURN_CORRELATION,
                logical_target="documentation-intake",
                correlation_id="corr-12",
                intake_state=IntakeState.PENDING,
                return_kind=ReturnKind.EVIDENCE_RESULT,
                limit=100,
            )
        )

        path, params = self.transport.requests[0]
        self.assertEqual(path, "repos/owner/repository/issues")
        self.assertEqual(
            params["labels"],
            "return-kind:evidence-result,intake-state:pending",
        )
        self.assertEqual(
            [hit.matched_signals for hit in page.hits],
            [("correlation-id",), ()],
        )
        self.assertIs(page.completeness, ResultCompleteness.COMPLETE)

    def test_return_correlation_complete_negative_has_no_signal(self):
        self.transport.responses.append(
            ([return_issue(31, "corr-other")], None)
        )
        adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
            logical_target="documentation-intake",
        )

        page = adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.RETURN_CORRELATION,
                logical_target="documentation-intake",
                correlation_id="corr-12",
                intake_state=IntakeState.PENDING,
            )
        )

        self.assertIs(page.completeness, ResultCompleteness.COMPLETE)
        self.assertEqual(page.hits[0].matched_signals, ())

    def test_return_correlation_cursor_or_malformed_metadata_is_partial(self):
        adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
            logical_target="documentation-intake",
        )
        cases = (
            ([return_issue(31, "corr-other")], "2"),
            ([return_issue(32, "corr-12", malformed=True)], None),
        )
        for records, cursor in cases:
            with self.subTest(cursor=cursor):
                self.transport.responses.append((records, cursor))
                page = adapter.query_page(
                    AdvancedQuery(
                        purpose=QueryPurpose.RETURN_CORRELATION,
                        logical_target="documentation-intake",
                        correlation_id="corr-12",
                        intake_state=IntakeState.PENDING,
                    )
                )
                self.assertIs(
                    page.completeness,
                    ResultCompleteness.PARTIAL,
                )

    def test_return_correlation_excludes_pull_requests(self):
        self.transport.responses.append(
            (
                [
                    return_issue(31, "corr-12", pull_request=True),
                    return_issue(32, "corr-12"),
                ],
                None,
            )
        )
        adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
            logical_target="documentation-intake",
        )

        page = adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.RETURN_CORRELATION,
                logical_target="documentation-intake",
                correlation_id="corr-12",
                intake_state=IntakeState.PENDING,
            )
        )

        self.assertEqual(
            [hit.item.provider_id for hit in page.hits],
            ["32"],
        )

    def test_return_correlation_plan_can_enumerate_five_pages(self):
        for page_number in range(5):
            start = page_number * 100 + 1
            records = [
                return_issue(number, f"corr-other-{number}")
                for number in range(start, start + 100)
            ]
            self.transport.responses.append(
                (records, str(page_number + 2) if page_number < 4 else None)
            )
        adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
            logical_target="documentation-intake",
        )
        query = AdvancedQuery(
            purpose=QueryPurpose.RETURN_CORRELATION,
            logical_target="documentation-intake",
            correlation_id="corr-12",
            intake_state=IntakeState.PENDING,
            limit=100,
        )

        coverage = QueryCoordinator(adapter).execute(
            ContinuationPlan(
                query=query,
                max_pages=5,
                max_items=500,
            )
        )

        self.assertEqual(len(coverage.calls), 5)
        self.assertEqual(len(coverage.hits), 500)
        self.assertIs(
            coverage.completeness,
            ResultCompleteness.COMPLETE,
        )

    def test_inventory_maps_state_route_limit_and_cursor(self):
        self.transport.responses.append(([], "3"))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.INVENTORY,
                logical_target="example-implementation",
                active_only=False,
                routes=(WorkRoute.SPIKE_EVIDENCE,),
                cursor="2",
                limit=25,
            )
        )

        path, params = self.transport.requests[0]
        self.assertEqual(
            path,
            "repos/owner/repository/issues",
        )
        self.assertEqual(
            params,
            {
                "state": "all",
                "labels": "work-route:spike-evidence",
                "per_page": "25",
                "page": "2",
            },
        )
        self.assertEqual(page.next_cursor, "3")
        self.assertIs(page.completeness, ResultCompleteness.PARTIAL)

    def test_source_query_quotes_body_term_and_verifies_exact_relation(self):
        self.transport.responses.append((self.advanced_payload, None))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.SOURCE_TRACEABILITY,
                logical_target="example-implementation",
                source_reference='ADR-0003 "quoted"',
                routes=(WorkRoute.ARCHITECTURE_SLICE_HANDOFF,),
            )
        )

        path, params = self.transport.requests[0]
        self.assertEqual(path, "search/issues")
        self.assertIn("repo:owner/repository", params["q"])
        self.assertIn("is:issue", params["q"])
        self.assertIn("is:open", params["q"])
        self.assertIn(
            'label:"work-route:architecture-slice-handoff"',
            params["q"],
        )
        self.assertIn(r'in:body "ADR-0003 \"quoted\""', params["q"])
        self.assertNotIn("advanced_search", params)
        self.assertNotIn("search_type", params)
        self.assertEqual(page.hits[0].matched_signals, ())
        self.assertIs(page.capability, CapabilityStatus.PARTIAL)
        self.assertIs(page.completeness, ResultCompleteness.PARTIAL)
        self.assertEqual(len(self.transport.requests), 1)

    def test_source_query_marks_exact_signal_only_after_metadata_match(self):
        self.transport.responses.append((self.advanced_payload, None))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.SOURCE_TRACEABILITY,
                logical_target="example-implementation",
                source_reference="ADR-0003",
            )
        )

        self.assertEqual(page.hits[0].matched_signals, ("source-reference",))
        self.assertEqual(page.hits[1].matched_signals, ())
        self.assertEqual(page.hits[2].matched_signals, ())

    def test_logical_target_query_quotes_body_term_and_verifies_metadata(self):
        self.transport.responses.append((self.advanced_payload, None))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.LOGICAL_TARGET,
                logical_target="example-implementation",
            )
        )

        _, params = self.transport.requests[0]
        self.assertIn(
            'in:body "example-implementation"',
            params["q"],
        )
        self.assertEqual(page.hits[0].matched_signals, ("logical-target",))
        self.assertEqual(page.hits[1].matched_signals, ())

    def test_correlation_query_quotes_body_term_and_verifies_metadata(self):
        self.transport.responses.append((self.advanced_payload, None))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.CORRELATION,
                logical_target="example-implementation",
                correlation_id="corr-12",
            )
        )

        _, params = self.transport.requests[0]
        self.assertIn('in:body "corr-12"', params["q"])
        self.assertEqual(page.hits[0].matched_signals, ("correlation-id",))
        self.assertEqual(page.hits[1].matched_signals, ())

    def test_similarity_uses_native_hybrid_search(self):
        adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
            logical_target="example-implementation",
            semantic_search_enabled=True,
        )
        self.transport.responses.append(
            ({"incomplete_results": False, "items": []}, None)
        )

        adapter.query_page(
            AdvancedQuery.similarity(
                logical_target="example-implementation",
                capability="account-address-prediction",
                expected_outcome="Return one deterministic address",
            )
        )

        path, params = self.transport.requests[0]
        self.assertEqual(path, "search/issues")
        self.assertEqual(params["advanced_search"], "true")
        self.assertEqual(params["search_type"], "hybrid")
        self.assertIn("repo:owner/repository", params["q"])
        self.assertIn("is:issue", params["q"])

    def test_similarity_maps_explicit_semantic_mode(self):
        adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
            semantic_search_enabled=True,
        )
        self.transport.responses.append(
            ({"incomplete_results": False, "items": []}, None)
        )

        adapter.query_page(
            AdvancedQuery.similarity(
                logical_target="example-implementation",
                capability="account-address-prediction",
                expected_outcome=None,
                similarity_mode=SimilarityMode.SEMANTIC,
            )
        )

        _, params = self.transport.requests[0]
        self.assertEqual(params["search_type"], "semantic")

    def test_similarity_without_enabled_native_support_is_unsupported(self):
        page = self.adapter.query_page(
            AdvancedQuery.similarity(
                logical_target="example-implementation",
                capability="account-address-prediction",
                expected_outcome=None,
            )
        )

        self.assertIs(page.capability, CapabilityStatus.UNSUPPORTED)
        self.assertIs(page.completeness, ResultCompleteness.UNSUPPORTED)
        self.assertEqual(self.transport.requests, [])

    def test_search_maps_incomplete_results_and_next_cursor(self):
        payload = {
            "incomplete_results": True,
            "items": [self.advanced_payload["items"][0]],
        }
        self.transport.responses.append((payload, "2"))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.CORRELATION,
                logical_target="example-implementation",
                correlation_id="corr-12",
            )
        )

        self.assertEqual(page.next_cursor, "2")
        self.assertIs(page.completeness, ResultCompleteness.PARTIAL)
        self.assertTrue(
            any("incomplete" in limitation for limitation in page.limitations)
        )
        self.assertTrue(
            any(
                "additional provider page" in limitation
                for limitation in page.limitations
            )
        )
        self.assertEqual(len(self.transport.requests), 1)

    def test_similarity_preserves_provider_order_and_excludes_pull_requests(self):
        adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
            semantic_search_enabled=True,
        )
        payload = {
            "incomplete_results": False,
            "items": [
                self.advanced_payload["items"][0],
                self.advanced_payload["items"][3],
                self.advanced_payload["items"][1],
                self.advanced_payload["items"][2],
            ],
        }
        self.transport.responses.append((payload, None))

        page = adapter.query_page(
            AdvancedQuery.similarity(
                logical_target="example-implementation",
                capability="account-address-prediction",
                expected_outcome=None,
            )
        )

        self.assertEqual(
            [hit.item.provider_id for hit in page.hits],
            ["21", "22", "23"],
        )
        self.assertEqual(
            [hit.provider_rank for hit in page.hits],
            [1, 3, 4],
        )

    def test_inventory_preserves_provider_positions_when_skipping_pull_request(
        self,
    ):
        records = [
            self.payload[0],
            self.payload[4],
            self.payload[1],
        ]
        self.transport.responses.append((records, None))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.INVENTORY,
                logical_target="example-implementation",
            )
        )

        self.assertEqual(
            [hit.item.provider_id for hit in page.hits],
            ["11", "12"],
        )
        self.assertEqual(
            [hit.provider_rank for hit in page.hits],
            [1, 3],
        )

    def test_lexical_search_preserves_positions_when_skipping_pull_request(
        self,
    ):
        payload = {
            "incomplete_results": False,
            "items": [
                self.advanced_payload["items"][0],
                self.advanced_payload["items"][3],
                self.advanced_payload["items"][1],
            ],
        }
        self.transport.responses.append((payload, None))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.LOGICAL_TARGET,
                logical_target="example-implementation",
            )
        )

        self.assertEqual(
            [hit.item.provider_id for hit in page.hits],
            ["21", "22"],
        )
        self.assertEqual(
            [hit.provider_rank for hit in page.hits],
            [1, 3],
        )

    def test_search_exposes_verified_missing_and_malformed_metadata(self):
        self.transport.responses.append((self.advanced_payload, None))

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.LOGICAL_TARGET,
                logical_target="example-implementation",
            )
        )

        self.assertEqual(
            [hit.metadata_state for hit in page.hits],
            [
                MetadataState.VERIFIED,
                MetadataState.MISSING,
                MetadataState.MALFORMED,
            ],
        )
        self.assertIsNotNone(page.hits[0].protocol_metadata)
        self.assertIn(
            "versioned protocol metadata is missing",
            page.hits[1].metadata_limitation,
        )
        self.assertIn(
            "incomplete",
            page.hits[2].metadata_limitation,
        )
        self.assertTrue(
            any(
                "versioned protocol metadata is missing" in limitation
                for limitation in page.limitations
            )
        )

    def test_search_treats_valid_unversioned_protocol_block_as_legacy_missing(self):
        record = dict(self.advanced_payload["items"][0])
        record["body"] = "\n".join(
            (
                "<!-- architecture-handoff-protocol",
                "correlation-id: corr-12",
                (
                    "relation: "
                    '{"kind":"refinement","revision":"abc123",'
                    '"target":"git:https://github.com/owner/docs:'
                    'architecture/09-architecture-decisions.md#adr-0003"}'
                ),
                "-->",
            )
        )
        self.transport.responses.append(
            (
                {"incomplete_results": False, "items": [record]},
                None,
            )
        )

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.CORRELATION,
                logical_target="example-implementation",
                correlation_id="corr-12",
            )
        )

        self.assertIs(page.hits[0].metadata_state, MetadataState.MISSING)
        self.assertIsNone(page.hits[0].protocol_metadata)
        self.assertIn(
            "legacy unversioned",
            page.hits[0].metadata_limitation,
        )
        self.assertEqual(page.hits[0].matched_signals, ())

    def test_bound_logical_target_rejects_mismatch_without_provider_call(self):
        adapter = GitHubReadAdapter(
            "owner/repository",
            self.transport,
            logical_target="example-implementation",
        )
        with self.assertRaisesRegex(
            AdapterError,
            "logical target does not match",
        ):
            adapter.query_page(
                AdvancedQuery(
                    purpose=QueryPurpose.INVENTORY,
                    logical_target="other-target",
                )
            )

        self.assertEqual(self.transport.requests, [])

    def test_stale_revision_is_unsupported_without_provider_call(self):
        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.STALE_REVISION,
                logical_target="example-implementation",
                source_reference="ADR-0003",
                current_revision="abc123",
            )
        )

        self.assertIs(page.capability, CapabilityStatus.UNSUPPORTED)
        self.assertIs(page.completeness, ResultCompleteness.UNSUPPORTED)
        self.assertEqual(self.transport.requests, [])

    def test_duplicate_preflight_is_unsupported_without_provider_call(self):
        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.DUPLICATE_PREFLIGHT,
                logical_target="example-implementation",
            )
        )

        self.assertIs(page.capability, CapabilityStatus.UNSUPPORTED)
        self.assertIs(page.completeness, ResultCompleteness.UNSUPPORTED)
        self.assertEqual(self.transport.requests, [])

    def test_multiple_route_alternatives_are_unsupported_without_scan(self):
        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.INVENTORY,
                logical_target="example-implementation",
                routes=(
                    WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
                    WorkRoute.SPIKE_EVIDENCE,
                ),
            )
        )

        self.assertIs(page.capability, CapabilityStatus.UNSUPPORTED)
        self.assertIs(page.completeness, ResultCompleteness.UNSUPPORTED)
        self.assertEqual(self.transport.requests, [])

    def test_search_maps_multiple_routes_to_one_native_or_qualifier(self):
        self.transport.responses.append(
            ({"incomplete_results": False, "items": []}, None)
        )

        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.SOURCE_TRACEABILITY,
                logical_target="example-implementation",
                routes=(
                    WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
                    WorkRoute.SPIKE_EVIDENCE,
                ),
                source_reference="ADR-0003",
            )
        )

        path, params = self.transport.requests[0]
        self.assertEqual(path, "search/issues")
        self.assertIn(
            'label:"work-route:architecture-slice-handoff",'
            '"work-route:spike-evidence"',
            params["q"],
        )
        self.assertIs(page.capability, CapabilityStatus.PARTIAL)
        self.assertEqual(len(self.transport.requests), 1)

    def test_internal_route_filter_is_unsupported_without_scan(self):
        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.INVENTORY,
                logical_target="example-implementation",
                routes=(WorkRoute.TARGET_NATIVE_INTERNAL,),
            )
        )

        self.assertIs(page.capability, CapabilityStatus.UNSUPPORTED)
        self.assertIs(page.completeness, ResultCompleteness.UNSUPPORTED)
        self.assertEqual(self.transport.requests, [])

    def test_internal_route_is_unsupported_in_any_route_position(self):
        page = self.adapter.query_page(
            AdvancedQuery(
                purpose=QueryPurpose.SOURCE_TRACEABILITY,
                logical_target="example-implementation",
                routes=(
                    WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
                    WorkRoute.TARGET_NATIVE_INTERNAL,
                ),
                source_reference="ADR-0003",
            )
        )

        self.assertIs(page.capability, CapabilityStatus.UNSUPPORTED)
        self.assertIs(page.completeness, ResultCompleteness.UNSUPPORTED)
        self.assertEqual(self.transport.requests, [])

    def test_declares_supported_partial_and_unsupported_capabilities(self):
        capabilities = self.adapter.capabilities()

        self.assertEqual(
            capabilities["task-discovery"],
            CapabilityStatus.SUPPORTED,
        )
        self.assertEqual(
            capabilities["source-lookup"],
            CapabilityStatus.PARTIAL,
        )
        self.assertEqual(
            capabilities["controlled-write"],
            CapabilityStatus.UNSUPPORTED,
        )
        self.assertEqual(
            capabilities["duplicate-preflight"],
            CapabilityStatus.UNSUPPORTED,
        )
        self.assertEqual(
            capabilities["return-round-trip"],
            CapabilityStatus.UNSUPPORTED,
        )

    def test_normalizes_routes_status_priority_and_internal_work(self):
        result = self.adapter.list_items(QueryRequest())

        self.assertEqual(result.completeness, ResultCompleteness.COMPLETE)
        self.assertEqual(len(result.items), 4)
        self.assertEqual(
            [item.work_route for item in result.items],
            [
                WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
                WorkRoute.IMPLEMENTATION_CONFORMANCE_REFERRAL,
                WorkRoute.SPIKE_EVIDENCE,
                WorkRoute.TARGET_NATIVE_INTERNAL,
            ],
        )
        self.assertEqual(result.items[0].status, "ready")
        self.assertEqual(result.items[0].priority, "high")
        self.assertEqual(
            result.items[0].provider_qualified_id,
            "github:owner/repository#11",
        )
        self.assertFalse(hasattr(result.items[0], "body"))

    def test_uses_bounded_issue_query_and_keeps_continuation(self):
        transport = FakeTransport(self.payload, next_cursor="2")
        adapter = GitHubReadAdapter(
            "owner/repository",
            transport,
        )

        result = adapter.list_items(QueryRequest(limit=25, cursor="1"))

        self.assertEqual(
            transport.calls,
            [
                (
                    "repos/owner/repository/issues",
                    {"state": "open", "per_page": "25", "page": "1"},
                )
            ],
        )
        self.assertEqual(result.completeness, ResultCompleteness.PARTIAL)
        self.assertEqual(result.next_cursor, "2")
        self.assertIn("additional provider page", result.limitations[0])

    def test_route_filter_maps_to_github_label(self):
        transport = FakeTransport([self.payload[2]])
        adapter = GitHubReadAdapter(
            "owner/repository",
            transport,
        )

        adapter.list_items(
            QueryRequest(route=WorkRoute.SPIKE_EVIDENCE)
        )

        _, params = transport.calls[0]
        self.assertEqual(params["labels"], "work-route:spike-evidence")

    def test_legacy_internal_route_is_unsupported_without_provider_call(self):
        result = self.adapter.list_items(
            QueryRequest(route=WorkRoute.TARGET_NATIVE_INTERNAL)
        )

        self.assertIs(
            result.completeness,
            ResultCompleteness.UNSUPPORTED,
        )
        self.assertEqual(result.items, ())
        self.assertEqual(result.searched_scopes, ())
        self.assertEqual(self.transport.calls, [])
        self.assertIn("absence of a work-route", result.limitations[0])

    def test_lookup_route_uses_provider_qualifier(self):
        transport = FakeTransport([self.payload[0]])
        adapter = GitHubReadAdapter(
            "owner/repository",
            transport,
        )

        result = adapter.list_items(
            QueryRequest(
                route=WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
                source_reference="ADR-0003",
            )
        )

        path, params = transport.calls[0]
        self.assertEqual(path, "search/issues")
        self.assertIn(
            'label:"work-route:architecture-slice-handoff"',
            params["q"],
        )
        self.assertEqual(len(result.items), 1)

    def test_native_route_query_rejects_mismatched_provider_record(self):
        transport = FakeTransport([self.payload[3]])
        adapter = GitHubReadAdapter(
            "owner/repository",
            transport,
        )

        with self.assertRaisesRegex(
            AdapterError,
            "does not match native route predicate",
        ):
            adapter.list_items(
                QueryRequest(route=WorkRoute.SPIKE_EVIDENCE)
            )

    def test_source_lookup_uses_search_and_reports_partial_semantics(self):
        result = self.adapter.list_items(
            QueryRequest(source_reference="ADR-0003", limit=20)
        )

        path, params = self.transport.calls[0]
        self.assertEqual(path, "search/issues")
        self.assertEqual(params["per_page"], "20")
        self.assertIn("repo:owner/repository", params["q"])
        self.assertIn("is:open", params["q"])
        self.assertIn('"ADR-0003"', params["q"])
        self.assertEqual(result.completeness, ResultCompleteness.PARTIAL)
        self.assertIn("full-text", result.limitations[0])

    def test_source_lookup_can_include_closed_items_when_requested(self):
        self.adapter.list_items(
            QueryRequest(
                active_only=False,
                source_reference="ADR-0003",
            )
        )

        _, params = self.transport.calls[0]
        self.assertNotIn("is:open", params["q"])

    def test_source_lookup_escapes_github_search_quotes(self):
        self.adapter.list_items(
            QueryRequest(source_reference='ADR-"quoted"')
        )

        _, params = self.transport.calls[0]
        self.assertIn(r'"ADR-\"quoted\""', params["q"])

    def test_get_item_returns_full_provider_payload_after_selection(self):
        item = self.adapter.get_item("11")

        self.assertEqual(item["number"], 11)
        self.assertIn("body", item)
        self.assertEqual(
            self.transport.calls[0][0],
            "repos/owner/repository/issues/11",
        )

    def test_get_item_rejects_path_like_provider_id(self):
        with self.assertRaisesRegex(
            AdapterError,
            "provider_id must be a positive integer string",
        ):
            self.adapter.get_item("../labels")

    def test_get_item_rejects_pull_request_after_selection(self):
        self.payload[0]["pull_request"] = {
            "url": (
                "https://api.github.com/repos/"
                "owner/repository/pulls/11"
            )
        }

        with self.assertRaisesRegex(AdapterError, "pull request"):
            self.adapter.get_item("11")

    def test_rejects_repository_with_path_or_query_syntax(self):
        for repository in (
            "owner/repository/extra",
            "owner/repository?state=all",
            "../user",
            "owner/..",
            "./repository",
        ):
            with self.subTest(repository=repository):
                with self.assertRaisesRegex(
                    AdapterError,
                    "GitHub repository must use owner/name",
                ):
                    GitHubReadAdapter(repository, self.transport)

    def test_rejects_malformed_provider_record_instead_of_claiming_complete(self):
        transport = FakeTransport([self.payload[0], "malformed"])
        adapter = GitHubReadAdapter(
            "owner/repository",
            transport,
        )

        with self.assertRaisesRegex(
            AdapterError,
            "GitHub Issue record must be an object",
        ):
            adapter.list_items(QueryRequest())

    def test_rejects_explicit_internal_route_label(self):
        self.payload[3]["labels"].append(
            {"name": "work-route:target-native-internal"}
        )

        with self.assertRaisesRegex(
            AdapterError,
            "target-native internal work must omit work-route",
        ):
            self.adapter.list_items(QueryRequest())

    def test_rest_transport_rejects_non_https_api_url(self):
        with self.assertRaisesRegex(
            AdapterError,
            "GitHub API URL must use https",
        ):
            GitHubRestTransport(
                token="secret-that-must-not-cross-plaintext",
                api_url="http://api.github.example",
            )

    def test_rest_transport_rejects_unsafe_token_without_exposing_it(self):
        unsafe_token = "secret\nleak"

        with self.assertRaisesRegex(
            AdapterError,
            "GitHub token contains unsupported characters",
        ) as context:
            GitHubRestTransport(token=unsafe_token)

        self.assertNotIn(unsafe_token, str(context.exception))
        self.assertNotIn("secret", str(context.exception))

    def test_rest_transport_rejects_invalid_api_version(self):
        for api_version in ("2026-3-10", "2026-02-30", "latest"):
            with self.subTest(api_version=api_version):
                with self.assertRaisesRegex(
                    AdapterError,
                    "GitHub API version must use YYYY-MM-DD",
                ):
                    GitHubRestTransport(api_version=api_version)

    def test_rest_transport_bounds_call_and_preserves_pagination(self):
        observed = {}

        def opener(request, *, timeout):
            observed["url"] = request.full_url
            observed["authorization"] = request.get_header("Authorization")
            observed["api_version"] = request.get_header(
                "X-github-api-version"
            )
            observed["timeout"] = timeout
            return FakeResponse(
                [],
                (
                    "<https://api.github.com/repos/owner/repository/"
                    'issues?page=2>; rel="next"'
                ),
            )

        transport = GitHubRestTransport(token="secret", opener=opener)

        payload, cursor = transport.get(
            "repos/owner/repository/issues",
            {"state": "open", "page": "1"},
        )

        self.assertEqual(payload, [])
        self.assertEqual(cursor, "2")
        self.assertEqual(observed["timeout"], 15)
        self.assertEqual(observed["authorization"], "Bearer secret")
        self.assertEqual(observed["api_version"], "2026-03-10")
        self.assertIn("state=open", observed["url"])

    def test_rest_transport_uses_configured_positive_timeout(self):
        observed = {}

        def opener(_request, *, timeout):
            observed["timeout"] = timeout
            return FakeResponse([])

        transport = GitHubRestTransport(
            opener=opener,
            timeout_seconds=7,
        )

        transport.get("repos/owner/repository/issues", {})

        self.assertEqual(observed["timeout"], 7)
        with self.assertRaisesRegex(
            AdapterError,
            "timeout_seconds must be a positive integer",
        ):
            GitHubRestTransport(timeout_seconds=True)

    def test_rest_transport_maps_rate_limits_without_exposing_token(self):
        error_type = getattr(
            github_module,
            "GitHubRateLimitError",
            None,
        )
        if error_type is None:
            self.fail("GitHubRateLimitError does not exist")
        secret = "secret-rate-limit-token"
        cases = (
            (429, {"Retry-After": "9"}),
            (
                403,
                {
                    "Retry-After": "11",
                    "X-RateLimit-Remaining": "0",
                },
            ),
        )
        for status, headers in cases:
            with self.subTest(status=status):
                def opener(request, *, timeout):
                    raise HTTPError(
                        request.full_url,
                        status,
                        "rate limited",
                        headers,
                        None,
                    )

                transport = GitHubRestTransport(
                    token=secret,
                    opener=opener,
                )

                with self.assertRaises(error_type) as context:
                    transport.get(
                        "repos/owner/repository/issues",
                        {},
                    )

                self.assertEqual(
                    context.exception.retry_after,
                    headers["Retry-After"],
                )
                self.assertNotIn(secret, str(context.exception))

    def test_rest_transport_rate_limit_without_retry_after_is_typed(self):
        error_type = getattr(
            github_module,
            "GitHubRateLimitError",
            None,
        )
        if error_type is None:
            self.fail("GitHubRateLimitError does not exist")

        def opener(request, *, timeout):
            raise HTTPError(
                request.full_url,
                403,
                "rate limited",
                {"X-RateLimit-Remaining": "0"},
                None,
            )

        transport = GitHubRestTransport(
            token="secret",
            opener=opener,
        )

        with self.assertRaises(error_type) as context:
            transport.get("repos/owner/repository/issues", {})

        self.assertIsNone(context.exception.retry_after)

    def test_rest_transport_recognizes_secondary_403_body_without_header(self):
        error_type = github_module.GitHubRateLimitError
        secret = "secret-secondary-token"
        messages = (
            f"You have exceeded a secondary rate limit. {secret}",
            f"You have triggered an abuse detection mechanism. {secret}",
        )
        for message in messages:
            with self.subTest(message=message):
                body = TrackedErrorBody(
                    json.dumps({"message": message}).encode("utf-8")
                )

                def opener(request, *, timeout):
                    raise HTTPError(
                        request.full_url,
                        403,
                        "Forbidden",
                        {"X-RateLimit-Remaining": "42"},
                        body,
                    )

                transport = GitHubRestTransport(
                    token=secret,
                    opener=opener,
                )

                with self.assertRaises(error_type) as context:
                    transport.get(
                        "repos/owner/repository/issues",
                        {},
                    )

                self.assertIsNone(context.exception.retry_after)
                self.assertNotIn(secret, str(context.exception))
                self.assertEqual(len(body.read_sizes), 1)
                self.assertGreater(body.read_sizes[0], 0)
                self.assertLessEqual(body.read_sizes[0], 4097)

    def test_rest_transport_keeps_permission_403_as_adapter_error(self):
        secret = "secret-permission-token"
        body = TrackedErrorBody(
            json.dumps(
                {
                    "message": (
                        f"Resource not accessible by integration {secret}"
                    )
                }
            ).encode("utf-8")
        )

        def opener(request, *, timeout):
            raise HTTPError(
                request.full_url,
                403,
                "Forbidden",
                {"X-RateLimit-Remaining": "42"},
                body,
            )

        transport = GitHubRestTransport(
            token=secret,
            opener=opener,
        )

        with self.assertRaises(AdapterError) as context:
            transport.get("repos/owner/repository/issues", {})

        self.assertNotIsInstance(
            context.exception,
            github_module.GitHubRateLimitError,
        )
        self.assertNotIn(secret, str(context.exception))

    def test_rest_transport_maps_404_to_fixed_token_safe_error(self):
        error_type = getattr(
            github_module,
            "GitHubNotFoundError",
            None,
        )
        self.assertIsNotNone(
            error_type,
            "GitHubNotFoundError does not exist",
        )
        secret = "secret-not-found-token"
        body = TrackedErrorBody(
            json.dumps(
                {"message": f"provider resource missing {secret}"}
            ).encode("utf-8")
        )

        def opener(request, *, timeout):
            raise HTTPError(
                request.full_url,
                404,
                f"Not Found {secret}",
                {},
                body,
            )

        transport = GitHubRestTransport(
            token=secret,
            opener=opener,
        )

        with self.assertRaises(error_type) as context:
            transport.get(
                "repos/owner/repository/labels/status%3Aready",
                {},
            )

        self.assertEqual(
            str(context.exception),
            "GitHub resource was not found",
        )
        self.assertNotIn(secret, str(context.exception))
        self.assertEqual(body.read_sizes, [])
        self.assertTrue(body.closed)
        formatted = "".join(
            traceback.TracebackException.from_exception(
                context.exception,
            ).format(chain=True)
        )
        self.assertNotIn(secret, formatted)

    def test_rest_transport_rejects_untrusted_403_bodies_with_bounded_read(self):
        secret = "secret-error-body-token"
        cases = (
            b"{not-json",
            json.dumps(["secondary rate limit", secret]).encode("utf-8"),
            json.dumps(
                {
                    "message": (
                        "secondary rate limit "
                        + secret
                        + ("x" * 5000)
                    )
                }
            ).encode("utf-8"),
        )
        for payload in cases:
            with self.subTest(payload_size=len(payload)):
                body = TrackedErrorBody(payload)

                def opener(request, *, timeout):
                    raise HTTPError(
                        request.full_url,
                        403,
                        "Forbidden",
                        {"X-RateLimit-Remaining": "42"},
                        body,
                    )

                transport = GitHubRestTransport(
                    token=secret,
                    opener=opener,
                )

                with self.assertRaises(AdapterError) as context:
                    transport.get(
                        "repos/owner/repository/issues",
                        {},
                    )

                self.assertNotIsInstance(
                    context.exception,
                    github_module.GitHubRateLimitError,
                )
                self.assertNotIn(secret, str(context.exception))
                self.assertEqual(len(body.read_sizes), 1)
                self.assertGreater(body.read_sizes[0], 0)
                self.assertLessEqual(body.read_sizes[0], 4097)

    def test_rest_transport_wraps_timeout_without_exposing_token(self):
        def opener(_request, *, timeout):
            raise TimeoutError(f"provider timed out after {timeout}")

        transport = GitHubRestTransport(token="secret", opener=opener)

        with self.assertRaisesRegex(
            AdapterError,
            "GitHub request failed: provider timed out after 15",
        ) as context:
            transport.get("repos/owner/repository/issues", {})

        self.assertNotIn("secret", str(context.exception))

    def test_rest_transport_rejects_cross_origin_redirect(self):
        handler = SameOriginRedirectHandler()
        request = Request(
            "https://api.github.com/repos/owner/repository/issues",
            headers={"Authorization": "Bearer secret"},
        )

        with self.assertRaisesRegex(
            HTTPError,
            "cross-origin redirect rejected",
        ) as context:
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://attacker.example/collect",
            )
        context.exception.close()

    def test_rest_transport_wraps_invalid_utf8(self):
        def opener(_request, *, timeout):
            return RawResponse(b"\xff")

        transport = GitHubRestTransport(opener=opener)

        with self.assertRaisesRegex(
            AdapterError,
            "GitHub response was not valid UTF-8 JSON",
        ):
            transport.get("repos/owner/repository/issues", {})

    def test_rejects_ambiguous_route_labels(self):
        self.payload[0]["labels"].append(
            {"name": "work-route:spike-evidence"}
        )

        with self.assertRaisesRegex(AdapterError, "multiple work-route labels"):
            self.adapter.list_items(QueryRequest())

    def test_parses_next_page_from_github_link_header(self):
        link = (
            '<https://api.github.com/repositories/1/issues?page=2>; rel="next", '
            '<https://api.github.com/repositories/1/issues?page=4>; rel="last"'
        )

        self.assertEqual(next_page_cursor(link), "2")
        self.assertIsNone(next_page_cursor(None))


if __name__ == "__main__":
    unittest.main()
