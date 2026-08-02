import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.registry import (  # noqa: E402
    RegistryConfig,
    StoreConfig,
    StoreRole,
)
from tools.architecture_handoff.github import AdapterError  # noqa: E402
from tools.architecture_handoff.return_runtime import (  # noqa: E402
    ReturnRequest,
    execute_return,
    prepare_return,
)
from tools.architecture_handoff.runtime_config import (  # noqa: E402
    GitHubRuntimeConfig,
    QueryBudget,
    QueryBudgetCeiling,
    RuntimeConfig,
    RuntimeConfigError,
)
from tools.architecture_handoff.write_coordinator import (  # noqa: E402
    CandidateDisposition,
)
from tools.architecture_handoff.write_models import (  # noqa: E402
    RelationKind,
    ReturnKind,
    TypedRelation,
    WriteOperation,
)


def registry():
    return RegistryConfig(
        targets=(),
        stores=(
            StoreConfig(
                key="documentation-intake",
                role=StoreRole.DOCUMENTATION_INTAKE,
                provider="github",
                repository="owner/docs",
                routing_status="active",
                tracker_reference="github:owner/docs",
            ),
        ),
    )


def runtime_config():
    return RuntimeConfig(
        default_budget=QueryBudget(50, 1, 100),
        return_correlation_fallback_budget=QueryBudget(100, 1, 100),
        ceiling=QueryBudgetCeiling(20, 2000),
        github=GitHubRuntimeConfig(15),
    )


def create_request(**overrides):
    values = {
        "store_key": "documentation-intake",
        "operation": WriteOperation.CREATE,
        "title": "Return provider evidence",
        "return_kind": ReturnKind.EVIDENCE_RESULT,
        "correlation_id": "corr-12",
        "source_relation": TypedRelation(
            kind=RelationKind.RETURN,
            target="github:owner/implementation#12",
        ),
        "origin": "github:owner/implementation",
        "evidence_links": (
            "https://github.com/owner/implementation/actions/runs/1",
        ),
        "outcome": "The provider operation succeeded.",
        "method": "Executed one bounded integration check.",
        "observations": "The identifier was stable.",
        "verification": "The test passed.",
        "produced_artifacts": (
            "github:owner/implementation@abc123:test/provider.py",
        ),
        "limitations": (),
        "remaining_unknowns": (),
        "requested_return_route": "Resume Research Plan RP-0001.",
        "disposition": CandidateDisposition.CREATE_DISTINCT,
    }
    values.update(overrides)
    return ReturnRequest(**values)


def issue(
    number=31,
    correlation_id="corr-12",
    intake_state="pending",
    *,
    pull_request=False,
):
    body = "\n".join(
        (
            "return-kind: evidence-result",
            f"intake-state: {intake_state}",
            f"correlation-id: {correlation_id}",
            (
                "source-relation: return "
                "github:owner/implementation#12"
            ),
            "origin: github:owner/implementation",
            "",
            "## Evidence links",
            (
                "- https://github.com/owner/implementation/"
                "actions/runs/1"
            ),
            "",
            "outcome: The provider operation succeeded.",
            "method: Executed one bounded integration check.",
            "observations: The identifier was stable.",
            "verification: The test passed.",
            "",
            "## Produced artifacts",
            "- github:owner/implementation@abc123:test/provider.py",
            "",
            "## Limitations",
            "- None",
            "",
            "## Remaining unknowns",
            "- None",
            "",
            "requested-return-route: Resume Research Plan RP-0001.",
            "",
            "<!-- architecture-handoff-protocol",
            "schema-version: 2",
            "logical-target: documentation-intake",
            f"correlation-id: {correlation_id}",
            (
                "relation: "
                '{"kind":"return","revision":null,'
                '"target":"github:owner/implementation#12"}'
            ),
            "-->",
        )
    )
    result = {
        "number": number,
        "title": "Return provider evidence",
        "body": body,
        "state": "open",
        "updated_at": "2026-07-31T10:00:00Z",
        "html_url": f"https://github.com/owner/docs/issues/{number}",
        "labels": [
            {"name": "return-kind:evidence-result"},
            {"name": f"intake-state:{intake_state}"},
        ],
    }
    if pull_request:
        result["pull_request"] = {
            "url": "https://api.github.com/repos/owner/docs/pulls/31"
        }
    return result


class FakeGitHubTransport:
    def __init__(
        self,
        *,
        fast_items=(),
        fallback_items=(),
        fallback_cursor=None,
        current=None,
    ):
        self.fast_items = list(fast_items)
        self.fallback_items = list(fallback_items)
        self.fallback_cursor = fallback_cursor
        self.current = current
        self.calls = []

    def get(self, path, params):
        self.calls.append(("GET", path, dict(params)))
        if path == "search/issues":
            return {
                "incomplete_results": False,
                "items": list(self.fast_items),
            }, None
        if path == "repos/owner/docs/issues":
            return list(self.fallback_items), self.fallback_cursor
        if path.startswith("repos/owner/docs/issues/"):
            if self.current is None:
                raise AssertionError("current Issue is not configured")
            return dict(self.current), None
        raise AssertionError(f"unexpected GET: {path}")

    def post(self, path, payload):
        self.calls.append(("POST", path, dict(payload)))
        self.current = {
            "number": 41,
            "state": "open",
            "updated_at": "2026-07-31T11:00:00Z",
            "html_url": "https://github.com/owner/docs/issues/41",
            **dict(payload),
        }
        return dict(self.current), None

    def patch(self, path, payload):
        self.calls.append(("PATCH", path, dict(payload)))
        self.current = {
            **dict(self.current or {}),
            **dict(payload),
            "updated_at": "2026-07-31T11:30:00Z",
        }
        return dict(self.current), None


class ReturnRuntimeTests(unittest.TestCase):
    def test_prepare_is_read_only_and_returns_exact_preview(self):
        transport = FakeGitHubTransport()

        result = prepare_return(
            request=create_request(),
            registry=registry(),
            runtime=runtime_config(),
            transport=transport,
        )

        self.assertIsNotNone(result.prepared)
        self.assertEqual(result.provider_write_calls, ())
        self.assertEqual(result.budget, QueryBudget(100, 1, 100))
        self.assertEqual(
            result.prepared.intent.intake_state.value,
            "pending",
        )
        self.assertEqual(
            [call[0] for call in transport.calls],
            ["GET", "GET"],
        )

    def test_execute_rejects_changed_fingerprint_before_write(self):
        transport = FakeGitHubTransport()

        with self.assertRaisesRegex(
            ValueError,
            "prepared fingerprint changed",
        ):
            execute_return(
                request=create_request(),
                expected_fingerprint="0" * 64,
                approval_reference="human-gate-2026-07-31",
                registry=registry(),
                runtime=runtime_config(),
                transport=transport,
            )

        self.assertNotIn("POST", [call[0] for call in transport.calls])

    def test_fast_verified_candidate_blocks_without_fallback(self):
        transport = FakeGitHubTransport(
            fast_items=(issue(),),
        )

        result = prepare_return(
            request=create_request(),
            registry=registry(),
            runtime=runtime_config(),
            transport=transport,
        )

        self.assertIsNone(result.prepared)
        self.assertIn("verified correlation candidate", result.blocked_reason)
        self.assertEqual(
            [call[1] for call in transport.calls],
            ["search/issues"],
        )

    def test_fallback_cursor_blocks_incomplete_negative(self):
        transport = FakeGitHubTransport(fallback_cursor="2")

        result = prepare_return(
            request=create_request(),
            registry=registry(),
            runtime=runtime_config(),
            transport=transport,
        )

        self.assertIsNone(result.prepared)
        self.assertIn("fallback coverage is partial", result.blocked_reason)
        self.assertEqual(result.fallback.next_cursor, "2")

    def test_operation_override_must_stay_within_ceiling(self):
        result = prepare_return(
            request=create_request(),
            registry=registry(),
            runtime=runtime_config(),
            transport=FakeGitHubTransport(),
            max_pages=5,
            max_items=500,
        )

        self.assertEqual(result.budget, QueryBudget(100, 5, 500))
        with self.assertRaisesRegex(
            RuntimeConfigError,
            "max_items exceeds configured ceiling",
        ):
            prepare_return(
                request=create_request(),
                registry=registry(),
                runtime=runtime_config(),
                transport=FakeGitHubTransport(),
                max_items=2001,
            )

    def test_execute_create_returns_verified_readback(self):
        transport = FakeGitHubTransport()
        prepared = prepare_return(
            request=create_request(),
            registry=registry(),
            runtime=runtime_config(),
            transport=transport,
        )

        receipt = execute_return(
            request=create_request(),
            expected_fingerprint=prepared.prepared.fingerprint,
            approval_reference="human-gate-2026-07-31",
            registry=registry(),
            runtime=runtime_config(),
            transport=transport,
        )

        self.assertEqual(receipt.provider_qualified_id, "github:owner/docs#41")
        self.assertEqual(receipt.intake_state.value, "pending")
        self.assertEqual(
            [call[0] for call in transport.calls].count("POST"),
            1,
        )

    def test_execute_handled_update_uses_selected_pending_issue(self):
        current = issue()
        transport = FakeGitHubTransport(current=current)
        request = create_request(
            operation=WriteOperation.UPDATE,
            provider_id="31",
            expected_provider_state="2026-07-31T10:00:00Z",
        )
        prepared = prepare_return(
            request=request,
            registry=registry(),
            runtime=runtime_config(),
            transport=transport,
        )

        receipt = execute_return(
            request=request,
            expected_fingerprint=prepared.prepared.fingerprint,
            approval_reference="human-gate-2026-07-31",
            registry=registry(),
            runtime=runtime_config(),
            transport=transport,
        )

        self.assertEqual(receipt.provider_id, "31")
        self.assertEqual(receipt.intake_state.value, "handled")
        self.assertEqual(
            [call[0] for call in transport.calls].count("PATCH"),
            1,
        )

    def test_prepare_update_rejects_changed_return_identity(self):
        transport = FakeGitHubTransport(
            current=issue(correlation_id="corr-existing"),
        )
        request = create_request(
            operation=WriteOperation.UPDATE,
            provider_id="31",
            expected_provider_state="2026-07-31T10:00:00Z",
            correlation_id="corr-different",
        )

        with self.assertRaisesRegex(
            AdapterError,
            "immutable Return identity",
        ):
            prepare_return(
                request=request,
                registry=registry(),
                runtime=runtime_config(),
                transport=transport,
            )

        self.assertNotIn("PATCH", [call[0] for call in transport.calls])

    def test_prepare_update_rejects_pull_request_before_write(self):
        transport = FakeGitHubTransport(current=issue(pull_request=True))
        request = create_request(
            operation=WriteOperation.UPDATE,
            provider_id="31",
            expected_provider_state="2026-07-31T10:00:00Z",
        )

        with self.assertRaisesRegex(AdapterError, "pull request"):
            prepare_return(
                request=request,
                registry=registry(),
                runtime=runtime_config(),
                transport=transport,
            )

        self.assertNotIn("PATCH", [call[0] for call in transport.calls])


if __name__ == "__main__":
    unittest.main()
