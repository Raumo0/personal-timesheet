import io
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff import cli as cli_module  # noqa: E402
from tools.architecture_handoff.cli import run  # noqa: E402
from tools.architecture_handoff.github import GitHubReadAdapter  # noqa: E402
from tools.architecture_handoff.models import (  # noqa: E402
    CapabilityStatus,
    QueryResult,
    ResultCompleteness,
    WorkItemSummary,
    WorkRoute,
)
from tools.architecture_handoff.protocol_metadata import (  # noqa: E402
    MetadataState,
    ProtocolMetadata,
)
from tools.architecture_handoff.query_models import (  # noqa: E402
    QueryPurpose,
    SearchHit,
    SearchPage,
    SimilarityMode,
)
from tools.architecture_handoff.registry import TargetConfig  # noqa: E402
from tools.architecture_handoff.runtime_config import (  # noqa: E402
    GitHubRuntimeConfig,
)
from tools.architecture_handoff.write_models import (  # noqa: E402
    RelationKind,
    TypedRelation,
)

CANONICAL_SOURCE = (
    "git:https://github.com/owner/documentation:"
    "architecture/09-architecture-decisions.md#adr-0003"
)


class FakeAdapter:
    def __init__(self):
        self.requests = []
        self.queries = []

    def capabilities(self):
        return {
            "task-discovery": CapabilityStatus.SUPPORTED,
            "source-lookup": CapabilityStatus.PARTIAL,
            "controlled-write": CapabilityStatus.UNSUPPORTED,
        }

    def list_items(self, request):
        self.requests.append(request)
        return QueryResult(
            items=(
                WorkItemSummary(
                    provider_id="11",
                    provider_qualified_id=(
                        "github:owner/repository#11"
                    ),
                    title="Implement deterministic address lookup",
                    status="ready",
                    work_route=WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
                    updated="2026-07-30T10:00:00Z",
                    url=(
                        "https://github.com/"
                        "owner/repository/issues/11"
                    ),
                    labels=("status:ready",),
                ),
                WorkItemSummary(
                    provider_id="14",
                    provider_qualified_id=(
                        "github:owner/repository#14"
                    ),
                    title="Update local dependency",
                    status="open",
                    work_route=WorkRoute.TARGET_NATIVE_INTERNAL,
                    updated="2026-07-30T07:00:00Z",
                    url=(
                        "https://github.com/"
                        "owner/repository/issues/14"
                    ),
                    labels=("maintenance",),
                ),
            ),
            completeness=ResultCompleteness.PARTIAL,
            searched_scopes=(
                "github:owner/repository:open-issues",
            ),
            next_cursor="2",
            limitations=("additional provider page is available",),
        )

    def get_item(self, provider_id):
        return {
            "number": int(provider_id),
            "title": "Implement deterministic address lookup",
            "body": "Full payload after explicit selection.",
        }

    def query_page(self, query):
        self.queries.append(query)
        metadata = ProtocolMetadata(
            schema_version=2,
            logical_target="pilot-backend",
            correlation_id="corr-12",
            capability="account-address-prediction",
            expected_outcome="Return one deterministic address",
            relations=(
                TypedRelation(
                    kind=RelationKind.IMPLEMENTATION,
                    target=CANONICAL_SOURCE,
                    revision="rev-old",
                ),
                TypedRelation(
                    kind=RelationKind.RETURN,
                    target="research:plan-12",
                ),
            ),
        )
        hit = SearchHit(
            item=WorkItemSummary(
                provider_id="11",
                provider_qualified_id=(
                    "github:owner/repository#11"
                ),
                title="Implement deterministic address lookup",
                status="ready",
                work_route=WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
                updated="2026-07-30T10:00:00Z",
                url=(
                    "https://github.com/"
                    "owner/repository/issues/11"
                ),
                labels=("status:ready",),
            ),
            matched_signals=("correlation-id",),
            provider_rank=1,
            metadata_state=MetadataState.VERIFIED,
            protocol_metadata=metadata,
        )
        return SearchPage(
            purpose=query.purpose,
            capability=(
                CapabilityStatus.UNSUPPORTED
                if (
                    query.purpose is QueryPurpose.SIMILARITY
                    and query.similarity_mode is SimilarityMode.SEMANTIC
                )
                else CapabilityStatus.SUPPORTED
            ),
            completeness=(
                ResultCompleteness.UNSUPPORTED
                if (
                    query.purpose is QueryPurpose.SIMILARITY
                    and query.similarity_mode is SimilarityMode.SEMANTIC
                )
                else ResultCompleteness.PARTIAL
            ),
            searched_scopes=(
                ()
                if (
                    query.purpose is QueryPurpose.SIMILARITY
                    and query.similarity_mode is SimilarityMode.SEMANTIC
                )
                else (
                    "github:owner/repository:issue-search",
                )
            ),
            hits=(
                ()
                if (
                    query.purpose is QueryPurpose.SIMILARITY
                    and query.similarity_mode is SimilarityMode.SEMANTIC
                )
                else (hit,)
            ),
            next_cursor=(
                None
                if query.cursor == "2"
                else "2"
            ),
            limitations=(
                (
                    "GitHub semantic and hybrid Issue search is not enabled",
                )
                if (
                    query.purpose is QueryPurpose.SIMILARITY
                    and query.similarity_mode is SimilarityMode.SEMANTIC
                )
                else ("additional provider page is available",)
            ),
        )


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp_dir.name) / "targets.json"
        self.registry_path.write_text(
            json.dumps(
                {
                    "targets": [
                        {
                            "key": "pilot-backend",
                            "provider": "github",
                            "repository": "owner/repository",
                            "routing_status": "active",
                            "owns": ["backend"],
                            "excludes": ["frontend"],
                        }
                    ],
                    "stores": [
                        {
                            "key": "example-documentation-intake",
                            "role": "documentation-intake",
                            "provider": "github",
                            "repository": "owner/docs",
                            "routing_status": "active",
                            "tracker_reference": "github:owner/docs",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.runtime_path = Path(self.temp_dir.name) / "runtime.json"
        self.runtime_path.write_text(
            json.dumps(
                {
                    "query_budgets": {
                        "default": {
                            "page_size": 40,
                            "max_pages": 1,
                            "max_items": 80,
                        },
                        "return_correlation_fallback": {
                            "page_size": 100,
                            "max_pages": 1,
                            "max_items": 100,
                        },
                        "ceiling": {
                            "max_pages": 4,
                            "max_items": 400,
                        },
                    },
                    "providers": {
                        "github": {
                            "request_timeout_seconds": 7,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.factory_calls = []

    def tearDown(self):
        self.temp_dir.cleanup()

    def _factory(self, target):
        self.factory_calls.append(target)
        self.adapter = FakeAdapter()
        return self.adapter

    def _run(self, *arguments):
        arguments = (
            arguments[:1]
            + ("--runtime", str(self.runtime_path))
            + arguments[1:]
        )
        return run(
            list(arguments),
            adapter_factory=self._factory,
            stdout=self.stdout,
            stderr=self.stderr,
        )

    def _run_payload(self, *arguments):
        exit_code = self._run(*arguments)
        payload = (
            json.loads(self.stdout.getvalue())
            if self.stdout.getvalue()
            else None
        )
        return exit_code, payload

    def _run_payload_with_adapter(self, adapter, *arguments):
        arguments = (
            arguments[:1]
            + ("--runtime", str(self.runtime_path))
            + arguments[1:]
        )
        exit_code = run(
            list(arguments),
            adapter_factory=lambda _target: adapter,
            stdout=self.stdout,
            stderr=self.stderr,
        )
        payload = (
            json.loads(self.stdout.getvalue())
            if self.stdout.getvalue()
            else None
        )
        return exit_code, payload

    def test_default_factory_binds_runtime_timeout_and_semantic_mode(self):
        target = TargetConfig(
            key="pilot-backend",
            provider="github",
            repository="owner/repository",
            routing_status="active",
            owns=("backend",),
            excludes=("frontend",),
        )
        with (
            patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}),
            patch.object(cli_module, "GitHubReadAdapter") as adapter_type,
            patch.object(
                cli_module,
                "GitHubRestTransport",
            ) as transport_type,
        ):
            cli_module._default_adapter_factory(
                target,
                GitHubRuntimeConfig(request_timeout_seconds=7),
            )

        _, kwargs = adapter_type.call_args
        self.assertEqual(kwargs["logical_target"], "pilot-backend")
        self.assertTrue(kwargs["semantic_search_enabled"])
        transport_type.assert_called_once_with(
            token="test-token",
            timeout_seconds=7,
        )

    def test_list_outputs_compact_inventory_capabilities_and_hints(self):
        exit_code = self._run(
            "list",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--limit",
            "25",
        )

        self.assertEqual(exit_code, 0, self.stderr.getvalue())
        payload = json.loads(self.stdout.getvalue())
        self.assertEqual(payload["target"], "pilot-backend")
        self.assertEqual(payload["completeness"], "partial")
        self.assertEqual(payload["next_cursor"], "2")
        self.assertEqual(
            payload["capabilities"]["controlled-write"],
            "unsupported",
        )
        categories = {
            category["work_route"]: category
            for category in payload["categories"]
        }
        self.assertEqual(
            categories["architecture-slice-handoff"]["count"],
            1,
        )
        self.assertIn(
            "accepted product or architecture sources",
            categories["architecture-slice-handoff"]["hint"],
        )
        self.assertEqual(
            categories["implementation-conformance-referral"]["count"],
            0,
        )
        self.assertEqual(
            categories["target-native-internal"]["count"],
            1,
        )
        self.assertEqual(len(payload["items"]), 2)
        self.assertNotIn("body", payload["items"][0])

    def test_get_outputs_full_payload_after_selection(self):
        exit_code = self._run(
            "get",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--id",
            "11",
        )

        self.assertEqual(exit_code, 0, self.stderr.getvalue())
        payload = json.loads(self.stdout.getvalue())
        self.assertEqual(payload["target"], "pilot-backend")
        self.assertEqual(payload["item"]["number"], 11)
        self.assertIn("body", payload["item"])

    def test_get_resolves_selected_return_from_documentation_store(self):
        exit_code = self._run(
            "get",
            "--registry",
            str(self.registry_path),
            "--store",
            "example-documentation-intake",
            "--id",
            "11",
        )

        self.assertEqual(exit_code, 0, self.stderr.getvalue())
        payload = json.loads(self.stdout.getvalue())
        self.assertEqual(payload["endpoint_kind"], "store")
        self.assertEqual(
            payload["store"],
            "example-documentation-intake",
        )
        self.assertEqual(
            self.factory_calls[0].repository,
            "owner/docs",
        )
        self.assertEqual(payload["item"]["number"], 11)

    def test_search_exposes_one_bounded_lookup_key(self):
        exit_code = self._run(
            "search",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--correlation-id",
            "corr-12",
            "--limit",
            "20",
        )

        self.assertEqual(exit_code, 0, self.stderr.getvalue())
        self.assertEqual(self.adapter.requests[0].correlation_id, "corr-12")
        self.assertIsNone(self.adapter.requests[0].source_reference)
        payload = json.loads(self.stdout.getvalue())
        self.assertEqual(payload["completeness"], "partial")

    def test_returns_maps_kind_and_state_to_advanced_query(self):
        code, payload = self._run_payload(
            "returns",
            "--registry",
            str(self.registry_path),
            "--store",
            "example-documentation-intake",
            "--return-kind",
            "evidence-result",
            "--intake-state",
            "pending",
        )

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(
            payload["store"],
            "example-documentation-intake",
        )
        self.assertEqual(payload["endpoint_kind"], "store")
        self.assertEqual(
            self.factory_calls[0].repository,
            "owner/docs",
        )
        self.assertEqual(payload["query"]["purpose"], "return-intake")
        self.assertEqual(
            payload["query"]["return_kind"],
            "evidence-result",
        )
        self.assertEqual(payload["requirement"], "required")
        self.assertNotIn("write", payload)

    def test_advanced_defaults_come_from_runtime_policy(self):
        code, payload = self._run_payload(
            "returns",
            "--registry",
            str(self.registry_path),
            "--store",
            "example-documentation-intake",
            "--intake-state",
            "pending",
        )

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(payload["query"]["limit"], 40)
        self.assertEqual(
            payload["plan"],
            {"max_items": 80, "max_pages": 1},
        )

    def test_runtime_override_above_ceiling_is_rejected(self):
        code, payload = self._run_payload(
            "returns",
            "--registry",
            str(self.registry_path),
            "--store",
            "example-documentation-intake",
            "--intake-state",
            "pending",
            "--max-items",
            "401",
        )

        self.assertEqual(code, 2)
        self.assertIsNone(payload)
        self.assertIn(
            "max_items exceeds configured ceiling",
            self.stderr.getvalue(),
        )

    def test_explicit_continuation_reports_bounds_calls_and_cursor_state(self):
        code, payload = self._run_payload(
            "returns",
            "--registry",
            str(self.registry_path),
            "--store",
            "example-documentation-intake",
            "--intake-state",
            "pending",
            "--limit",
            "10",
            "--max-pages",
            "2",
            "--max-items",
            "20",
        )

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(
            payload["plan"],
            {"max_items": 20, "max_pages": 2},
        )
        self.assertEqual(len(payload["provider_calls"]), 2)
        self.assertEqual(
            [call["cursor"] for call in payload["provider_calls"]],
            [None, "2"],
        )
        self.assertEqual(
            payload["cursor"],
            {"continuation_required": False, "next": None},
        )
        self.assertEqual(len(payload["hits"]), 1)

    def test_item_budget_caps_provider_page_without_losing_terminal_hits(self):
        adapter = FakeAdapter()
        query_page = adapter.query_page

        def terminal_page(query):
            return replace(
                query_page(query),
                next_cursor=None,
                limitations=(),
                completeness=ResultCompleteness.COMPLETE,
            )

        adapter.query_page = terminal_page
        exit_code = run(
            [
                "returns",
                "--runtime",
                str(self.runtime_path),
                "--registry",
                str(self.registry_path),
                "--store",
                "example-documentation-intake",
                "--intake-state",
                "pending",
                "--limit",
                "100",
                "--max-items",
                "1",
            ],
            adapter_factory=lambda _target: adapter,
            stdout=self.stdout,
            stderr=self.stderr,
        )
        payload = json.loads(self.stdout.getvalue())

        self.assertEqual(exit_code, 0, self.stderr.getvalue())
        self.assertEqual(adapter.queries[0].limit, 1)
        self.assertEqual(payload["query"]["limit"], 1)
        self.assertEqual(payload["completeness"], "complete")
        self.assertEqual(
            payload["cursor"],
            {"continuation_required": False, "next": None},
        )

    def test_returns_rejects_target_coordinates(self):
        code, payload = self._run_payload(
            "returns",
            "--registry",
            str(self.registry_path),
            "--store",
            "example-documentation-intake",
            "--target",
            "pilot-backend",
            "--intake-state",
            "pending",
        )

        self.assertEqual(code, 2)
        self.assertIsNone(payload)
        self.assertEqual(self.factory_calls, [])
        self.assertIn("unrecognized arguments: --target", self.stderr.getvalue())

    def test_trace_correlation_returns_agent_composed_view(self):
        code, payload = self._run_payload(
            "trace",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--correlation-id",
            "corr-12",
            "--max-pages",
            "2",
        )

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(payload["query"]["purpose"], "correlation")
        self.assertEqual(payload["report"]["correlation_id"], "corr-12")
        self.assertEqual(
            payload["report"]["nodes"][0]["relation_targets"],
            [CANONICAL_SOURCE, "research:plan-12"],
        )
        self.assertEqual(
            payload["report"]["unresolved_targets"],
            [CANONICAL_SOURCE, "research:plan-12"],
        )

    def test_trace_requires_exactly_one_lookup_key(self):
        code, payload = self._run_payload(
            "trace",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
        )

        self.assertEqual(code, 2)
        self.assertIsNone(payload)
        self.assertIn(
            "one of the arguments --source-reference --correlation-id",
            self.stderr.getvalue(),
        )

    def test_stale_requires_source_and_current_revision(self):
        code, payload = self._run_payload(
            "stale",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--source-reference",
            CANONICAL_SOURCE,
        )

        self.assertEqual(code, 2)
        self.assertIsNone(payload)
        self.assertIn("current-revision", self.stderr.getvalue())

    def test_stale_rejects_blank_current_revision_before_adapter_creation(self):
        code, payload = self._run_payload(
            "stale",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--source-reference",
            CANONICAL_SOURCE,
            "--current-revision",
            "   ",
        )

        self.assertEqual(code, 2)
        self.assertIsNone(payload)
        self.assertEqual(self.factory_calls, [])
        self.assertIn(
            "current_revision must be a non-empty string",
            self.stderr.getvalue(),
        )

    def test_stale_classifies_observed_revision_from_source_candidates(self):
        code, payload = self._run_payload(
            "stale",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--source-reference",
            CANONICAL_SOURCE,
            "--current-revision",
            "rev-current",
            "--max-pages",
            "2",
        )

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(
            payload["query"]["purpose"],
            "source-traceability",
        )
        self.assertEqual(
            payload["report"]["entries"][0],
            {
                "classification": "stale",
                "observed_revision": "rev-old",
                "provider_qualified_id": (
                    "github:owner/repository#11"
                ),
            },
        )

    def test_similarity_is_read_only_and_reports_advisory_coverage(self):
        code, payload = self._run_payload(
            "similarity",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--capability",
            "account-address-prediction",
            "--expected-outcome",
            "Return one deterministic address",
        )

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(payload["requirement"], "advisory")
        self.assertEqual(payload["query"]["similarity_mode"], "hybrid")
        self.assertNotIn("write", payload)

    def test_unsupported_semantic_similarity_reports_no_provider_write(self):
        code, payload = self._run_payload(
            "similarity",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--capability",
            "account-address-prediction",
            "--mode",
            "semantic",
        )

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(payload["capability"], "unsupported")
        self.assertEqual(payload["completeness"], "unsupported")
        self.assertIn(
            "GitHub semantic and hybrid Issue search is not enabled",
            payload["limitations"],
        )
        self.assertEqual(payload["provider_calls"], [])
        self.assertEqual(payload["provider_call_count"], 0)
        self.assertNotIn("write", payload)

    def test_preflight_requires_one_canonical_source_reference(self):
        code, payload = self._run_payload(
            "preflight",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
        )

        self.assertEqual(code, 2)
        self.assertIsNone(payload)
        self.assertIn("source-reference", self.stderr.getvalue())

    def test_preflight_composes_exact_and_advisory_read_only_lanes(self):
        code, payload = self._run_payload(
            "preflight",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--source-reference",
            CANONICAL_SOURCE,
            "--route",
            "architecture-slice-handoff",
            "--capability",
            "account-address-prediction",
            "--expected-outcome",
            "Return one deterministic address",
        )

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(
            [lane["query"]["purpose"] for lane in payload["lanes"]],
            ["source-traceability", "similarity"],
        )
        self.assertEqual(
            [lane["requirement"] for lane in payload["lanes"]],
            ["required", "advisory"],
        )
        self.assertEqual(
            payload["lanes"][0]["query"]["source_reference"],
            CANONICAL_SOURCE,
        )
        for lane in payload["lanes"]:
            self.assertIn("plan", lane)
            self.assertIn("provider_calls", lane)
            self.assertIn("cursor", lane)
            self.assertIn("candidates", lane)
            self.assertIn("capability", lane)
            self.assertIn("completeness", lane)
            self.assertIn("searched_scopes", lane)
            self.assertIn("limitations", lane)
        self.assertNotIn("write", payload)

    def test_preflight_calls_real_github_adapter_once_per_composed_lane(self):
        class RecordingTransport:
            def __init__(self):
                self.requests = []

            def get(self, path, params):
                self.requests.append((path, params))
                body = "\n".join(
                    (
                        "<!-- architecture-handoff-protocol",
                        "schema-version: 2",
                        "logical-target: pilot-backend",
                        (
                            "relation: "
                            '{"kind":"refinement","revision":"rev-old",'
                            f'"target":"{CANONICAL_SOURCE}"'
                            "}"
                        ),
                        "-->",
                    )
                )
                return {
                    "incomplete_results": False,
                    "items": [
                        {
                            "number": 21,
                            "title": "Existing candidate",
                            "state": "open",
                            "updated_at": "2026-07-30T10:00:00Z",
                            "html_url": (
                                "https://github.com/"
                                "owner/repository/issues/21"
                            ),
                            "body": body,
                            "labels": [
                                {
                                    "name": (
                                        "work-route:"
                                        "architecture-slice-handoff"
                                    )
                                },
                                {"name": "status:ready"},
                            ],
                        }
                    ],
                }, None

        transport = RecordingTransport()
        adapter = GitHubReadAdapter(
            "owner/repository",
            transport,
            logical_target="pilot-backend",
            semantic_search_enabled=True,
        )
        code, payload = self._run_payload_with_adapter(
            adapter,
            "preflight",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--source-reference",
            CANONICAL_SOURCE,
            "--capability",
            "account-address-prediction",
        )

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(
            [path for path, _params in transport.requests],
            ["search/issues", "search/issues"],
        )
        self.assertNotIn("advanced_search", transport.requests[0][1])
        self.assertEqual(
            transport.requests[1][1]["advanced_search"],
            "true",
        )
        self.assertEqual(
            [lane["query"]["purpose"] for lane in payload["lanes"]],
            ["source-traceability", "similarity"],
        )

    def test_preflight_does_not_count_unsupported_lane_as_provider_call(self):
        class RecordingTransport:
            def __init__(self):
                self.requests = []

            def get(self, path, params):
                self.requests.append((path, params))
                return {
                    "incomplete_results": False,
                    "items": [],
                }, None

        transport = RecordingTransport()
        adapter = GitHubReadAdapter(
            "owner/repository",
            transport,
            logical_target="pilot-backend",
            semantic_search_enabled=False,
        )
        code, payload = self._run_payload_with_adapter(
            adapter,
            "preflight",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
            "--source-reference",
            CANONICAL_SOURCE,
            "--capability",
            "account-address-prediction",
        )

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(len(transport.requests), 1)
        exact, similarity = payload["lanes"]
        self.assertEqual(exact["provider_call_count"], 1)
        self.assertEqual(similarity["provider_call_count"], 0)
        self.assertEqual(similarity["provider_calls"], [])
        self.assertEqual(similarity["searched_scopes"], [])
        self.assertEqual(similarity["capability"], "unsupported")
        self.assertTrue(similarity["limitations"])

    def test_legacy_commands_remain_available(self):
        for arguments in (
            ("list", "--limit", "25"),
            ("get", "--id", "11"),
            ("search", "--source-reference", "ADR-0003"),
        ):
            with self.subTest(command=arguments[0]):
                self.stdout = io.StringIO()
                self.stderr = io.StringIO()
                code, payload = self._run_payload(
                    arguments[0],
                    "--registry",
                    str(self.registry_path),
                    "--target",
                    "pilot-backend",
                    *arguments[1:],
                )
                self.assertEqual(code, 0, self.stderr.getvalue())
                self.assertIsNotNone(payload)

    def test_unknown_target_returns_nonzero_without_json_output(self):
        exit_code = self._run(
            "list",
            "--registry",
            str(self.registry_path),
            "--target",
            "unknown",
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertIn("target not found: unknown", self.stderr.getvalue())

    def test_unsupported_provider_returns_nonzero(self):
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        payload["targets"][0]["provider"] = "jira"
        self.registry_path.write_text(json.dumps(payload), encoding="utf-8")

        exit_code = self._run(
            "list",
            "--registry",
            str(self.registry_path),
            "--target",
            "pilot-backend",
        )

        self.assertEqual(exit_code, 2)
        self.assertIn(
            "provider is not enabled in P0: jira",
            self.stderr.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
