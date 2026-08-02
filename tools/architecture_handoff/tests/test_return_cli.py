import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.return_cli import (  # noqa: E402
    load_return_request,
    run,
)
from tools.architecture_handoff.tests.test_return_runtime import (  # noqa: E402
    FakeGitHubTransport,
)


def request_payload(**overrides):
    payload = {
        "store_key": "documentation-intake",
        "operation": "create",
        "title": "Return provider evidence",
        "return_kind": "evidence-result",
        "correlation_id": "corr-12",
        "source_relation": {
            "kind": "return",
            "target": "github:owner/implementation#12",
        },
        "origin": "github:owner/implementation",
        "evidence_links": [
            "https://github.com/owner/implementation/actions/runs/1"
        ],
        "outcome": "The provider operation succeeded.",
        "method": "Executed one bounded integration check.",
        "observations": "The identifier was stable.",
        "verification": "The test passed.",
        "produced_artifacts": [
            "github:owner/implementation@abc123:test/provider.py"
        ],
        "limitations": [],
        "remaining_unknowns": [],
        "requested_return_route": "Resume Research Plan RP-0001.",
        "disposition": "create-distinct",
    }
    payload.update(overrides)
    return payload


class ReturnCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.registry_path = root / "registry.json"
        self.registry_path.write_text(
            json.dumps(
                {
                    "targets": [],
                    "stores": [
                        {
                            "key": "documentation-intake",
                            "role": "documentation-intake",
                            "provider": "github",
                            "repository": "owner/docs",
                            "routing_status": "active",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.runtime_path = root / "runtime.json"
        self.runtime_path.write_text(
            json.dumps(
                {
                    "query_budgets": {
                        "default": {
                            "page_size": 50,
                            "max_pages": 1,
                            "max_items": 100,
                        },
                        "return_correlation_fallback": {
                            "page_size": 100,
                            "max_pages": 1,
                            "max_items": 100,
                        },
                        "ceiling": {
                            "max_pages": 20,
                            "max_items": 2000,
                        },
                    },
                    "providers": {
                        "github": {
                            "request_timeout_seconds": 15,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.input_path = root / "return.json"
        self.input_path.write_text(
            json.dumps(request_payload()),
            encoding="utf-8",
        )
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_input_parser_rejects_unknown_provider_coordinates(self):
        payload = request_payload(repository="owner/docs")
        self.input_path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(
            ValueError,
            "unknown Return input fields: repository",
        ):
            load_return_request(self.input_path)

    def test_prepare_command_is_read_only_and_emits_fingerprint(self):
        transport = FakeGitHubTransport()

        code = run(
            [
                "prepare",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--input",
                str(self.input_path),
            ],
            transport_factory=lambda _token, _github: transport,
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
        )
        payload = json.loads(self.stdout.getvalue())

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(payload["store"]["key"], "documentation-intake")
        self.assertEqual(payload["budget"]["max_items"], 100)
        self.assertEqual(len(payload["fingerprint"]), 64)
        self.assertIn("provider_payload", payload)
        self.assertTrue(payload["provider_calls"])
        self.assertTrue(
            all(
                "provider_record_count" in call
                for call in payload["provider_calls"]
            )
        )
        self.assertNotIn("token", json.dumps(payload).lower())
        self.assertNotIn("POST", [call[0] for call in transport.calls])

    def test_prepare_limit_overrides_fallback_page_size(self):
        code = run(
            [
                "prepare",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--input",
                str(self.input_path),
                "--limit",
                "75",
            ],
            transport_factory=(
                lambda _token, _github: FakeGitHubTransport()
            ),
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
        )
        payload = json.loads(self.stdout.getvalue())

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(payload["budget"]["page_size"], 75)

    def test_execute_requires_environment_token_before_provider_calls(self):
        transport = FakeGitHubTransport()

        code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--input",
                str(self.input_path),
                "--expected-fingerprint",
                "0" * 64,
                "--approval-reference",
                "human-gate-2026-07-31",
            ],
            transport_factory=lambda _token, _github: transport,
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("GITHUB_TOKEN is required", self.stderr.getvalue())
        self.assertEqual(transport.calls, [])

    def test_invalid_json_error_contains_no_environment_secret(self):
        self.input_path.write_text("{", encoding="utf-8")

        code = run(
            [
                "prepare",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--input",
                str(self.input_path),
            ],
            transport_factory=lambda _token, _github: FakeGitHubTransport(),
            environ={"GITHUB_TOKEN": "do-not-print-this-token"},
            stdout=self.stdout,
            stderr=self.stderr,
        )

        self.assertEqual(code, 2)
        self.assertNotIn(
            "do-not-print-this-token",
            self.stderr.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
