import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.github import (  # noqa: E402
    AdapterError,
    GitHubNotFoundError,
)
from tools.architecture_handoff.provisioning_attempts import (  # noqa: E402
    FileProvisioningAttemptStore,
    InMemoryProvisioningAttemptStore,
)
from tools.architecture_handoff.github_provisioning import (  # noqa: E402
    GITHUB_PROTOCOL_LABEL_MANIFEST,
)
from tools.architecture_handoff.setup_cli import run  # noqa: E402


PREPARATION_ID = "prep_" + "a" * 43


class FakeProvisioningTransport:
    def __init__(self, labels=None):
        self.labels = dict(labels or {})
        self.get_calls = []
        self.post_calls = []
        self.fail_get_at = None
        self.fail_post_at = None

    def get(self, path, params):
        self.get_calls.append((path, params))
        if len(self.get_calls) == self.fail_get_at:
            raise AdapterError("provider read failed safely")
        name = path.rsplit("/", 1)[-1].replace("%3A", ":")
        if name not in self.labels:
            raise GitHubNotFoundError()
        return self.labels[name], None

    def post(self, path, payload):
        self.post_calls.append((path, payload))
        if len(self.post_calls) == self.fail_post_at:
            raise AdapterError("provider create failed safely")
        self.labels[payload["name"]] = dict(payload)
        return self.labels[payload["name"]], None


class ReprepareMissingTransport(FakeProvisioningTransport):
    def get(self, path, params):
        if len(self.get_calls) == len(self.labels):
            self.labels.clear()
        return super().get(path, params)


def required_labels():
    return {
        name: {"name": name, **presentation}
        for name, presentation in GITHUB_PROTOCOL_LABEL_MANIFEST.items()
        if name.startswith(("return-kind:", "intake-state:"))
    }


class SetupCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.registry_path = root / "registry.json"
        self.registry_path.write_text(
            json.dumps(
                {
                    "targets": [
                        {
                            "key": "pilot-backend",
                            "provider": "github",
                            "repository": "owner/target",
                            "routing_status": "active",
                            "owns": ["backend"],
                            "excludes": [],
                        },
                        {
                            "key": "unsupported-target",
                            "provider": "gitlab",
                            "repository": "owner/target",
                            "routing_status": "active",
                            "owns": ["unsupported"],
                            "excludes": [],
                        },
                    ],
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
                        "ceiling": {"max_pages": 20, "max_items": 2000},
                    },
                    "providers": {"github": {"request_timeout_seconds": 7}},
                }
            ),
            encoding="utf-8",
        )
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.attempt_store = InMemoryProvisioningAttemptStore()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _run(self, command, transport, *, environ=None):
        return run(
            [
                command,
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                *(
                    [
                        "--expected-fingerprint",
                        "0" * 64,
                        "--preparation-id",
                        PREPARATION_ID,
                        "--approval-reference",
                        "human-gate-1",
                    ]
                    if command == "execute"
                    else []
                ),
            ],
            transport_factory=lambda _token, _github: transport,
            environ=environ or {},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )

    def _payload(self):
        return json.loads(self.stdout.getvalue())

    def _error_payload(self):
        return json.loads(self.stderr.getvalue())

    def test_exactly_one_endpoint_selector_is_required(self):
        code = run(
            [
                "prepare",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
            ],
            stdout=self.stdout,
            stderr=self.stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("one of the arguments --target --store is required", self.stderr.getvalue())

    def test_endpoint_selectors_are_mutually_exclusive(self):
        code = run(
            [
                "prepare",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--target",
                "pilot-backend",
                "--store",
                "documentation-intake",
            ],
            stdout=self.stdout,
            stderr=self.stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("not allowed with argument", self.stderr.getvalue())

    def test_prepare_store_reports_five_exact_label_checks_without_writes(self):
        transport = FakeProvisioningTransport()

        code = self._run("prepare", transport)
        payload = self._payload()

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(payload["endpoint"]["key"], "documentation-intake")
        self.assertEqual(payload["endpoint"]["role"], "documentation-intake")
        self.assertEqual(len(payload["requirements"]), 5)
        self.assertEqual(len(payload["provider_calls"]), 5)
        self.assertEqual(len(payload["actions"]), 5)
        self.assertEqual(transport.post_calls, [])

    def test_prepare_target_resolves_active_endpoint(self):
        transport = FakeProvisioningTransport()

        code = run(
            [
                "prepare",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--target",
                "pilot-backend",
            ],
            transport_factory=lambda _token, _github: transport,
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )
        payload = self._payload()

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(payload["endpoint"]["key"], "pilot-backend")
        self.assertNotIn("role", payload["endpoint"])
        self.assertEqual(len(payload["requirements"]), 10)

    def test_prepare_rejects_non_github_endpoint_before_provider_calls(self):
        transport = FakeProvisioningTransport()

        code = run(
            [
                "prepare",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--target",
                "unsupported-target",
            ],
            transport_factory=lambda _token, _github: transport,
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
        )

        self.assertEqual(code, 2)
        self.assertIn("GitHub", self.stderr.getvalue())
        self.assertEqual(transport.get_calls, [])

    def test_prepare_serializes_compact_provisioning_preview(self):
        transport = FakeProvisioningTransport(
            {
                "return-kind:evidence-result": {
                    "name": "return-kind:evidence-result",
                    "color": "FFFFFF",
                    "description": "Existing custom presentation",
                }
            }
        )

        code = self._run("prepare", transport)
        payload = self._payload()

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(
            set(payload),
            {
                "actions",
                "endpoint",
                "fingerprint",
                "limitations",
                "observations",
                "preparation_id",
                "provider_calls",
                "requirements",
                "style_drift",
            },
        )
        self.assertEqual(payload["style_drift"], ["return-kind:evidence-result"])
        self.assertTrue(payload["limitations"])
        self.assertEqual(len(payload["fingerprint"]), 64)
        self.assertRegex(
            payload["preparation_id"],
            r"\Aprep_[A-Za-z0-9_-]{43}\Z",
        )
        self.assertNotIn("token", json.dumps(payload).lower())

    def test_execute_requires_token_only_when_live_preparation_has_actions(self):
        self._run("prepare", FakeProvisioningTransport())
        prepared = self._payload()
        self.stdout.seek(0)
        self.stdout.truncate(0)
        transport = FakeProvisioningTransport()

        code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                "--expected-fingerprint",
                prepared["fingerprint"],
                "--preparation-id",
                prepared["preparation_id"],
                "--approval-reference",
                "human-gate-token",
            ],
            transport_factory=lambda _token, _github: transport,
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )
        error = self._error_payload()

        self.assertEqual(code, 2)
        self.assertIn("GITHUB_TOKEN is required", error["error"])
        self.assertEqual(
            [
                (call["operation"], call["stable_id"])
                for call in error["provider_calls"]
            ],
            [
                ("inspect", "return-kind:evidence-result"),
                ("inspect", "return-kind:product-gap"),
                ("inspect", "return-kind:architecture-gap"),
                ("inspect", "intake-state:pending"),
                ("inspect", "intake-state:handled"),
                ("inspect", "return-kind:evidence-result"),
                ("inspect", "return-kind:product-gap"),
                ("inspect", "return-kind:architecture-gap"),
                ("inspect", "intake-state:pending"),
                ("inspect", "intake-state:handled"),
            ],
        )
        self.assertEqual(transport.post_calls, [])

    def test_reprepare_action_flip_requires_token_without_consuming_identity(self):
        prepared_transport = FakeProvisioningTransport()
        self._run("prepare", prepared_transport)
        prepared = self._payload()
        self.stdout.seek(0)
        self.stdout.truncate(0)
        execution = ReprepareMissingTransport(required_labels())

        code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                "--expected-fingerprint",
                prepared["fingerprint"],
                "--preparation-id",
                prepared["preparation_id"],
                "--approval-reference",
                "human-gate-state-flip",
            ],
            transport_factory=lambda _token, _github: execution,
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )
        self.assertEqual(code, 2)
        error = self._error_payload()
        required_ids = [
            requirement["name"] for requirement in prepared["requirements"]
        ]

        self.assertIn("GITHUB_TOKEN is required", error["error"])
        self.assertEqual(execution.post_calls, [])
        self.assertEqual(
            [
                (call["operation"], call["stable_id"])
                for call in error["provider_calls"]
            ],
            [
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
            ],
        )

        self.stdout.seek(0)
        self.stdout.truncate(0)
        self.stderr.seek(0)
        self.stderr.truncate(0)
        retry = FakeProvisioningTransport()
        retry_code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                "--expected-fingerprint",
                prepared["fingerprint"],
                "--preparation-id",
                prepared["preparation_id"],
                "--approval-reference",
                "human-gate-state-flip",
            ],
            transport_factory=lambda _token, _github: retry,
            environ={"GITHUB_TOKEN": "token-not-for-output"},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )

        self.assertEqual(retry_code, 0, self.stderr.getvalue())
        self.assertEqual(len(retry.post_calls), len(required_ids))

    def test_file_ledger_oserror_is_structured_and_token_safe(self):
        ledger = Path(self.temp_dir.name) / "state" / "attempts.json"
        with patch(
            "tools.architecture_handoff.provisioning_attempts.os.fstat",
            side_effect=OSError("raw-secret-path"),
        ):
            code = run(
                [
                    "prepare",
                    "--registry",
                    str(self.registry_path),
                    "--runtime",
                    str(self.runtime_path),
                    "--store",
                    "documentation-intake",
                ],
                transport_factory=lambda _token, _github: (
                    FakeProvisioningTransport()
                ),
                environ={},
                stdout=self.stdout,
                stderr=self.stderr,
                attempt_store=FileProvisioningAttemptStore(ledger),
            )

        self.assertEqual(code, 2)
        error = self._error_payload()
        self.assertIn("attempt ledger", error["error"])
        self.assertNotIn("raw-secret-path", self.stderr.getvalue())
        self.assertNotIn("Traceback", self.stderr.getvalue())

    def test_execute_noop_uses_approved_fingerprint_without_post(self):
        labels = {
            "return-kind:evidence-result": {
                "name": "return-kind:evidence-result",
                "color": "1D76DB",
                "description": "Returned evidence for validation and routing",
            },
            "return-kind:product-gap": {
                "name": "return-kind:product-gap",
                "color": "D93F0B",
                "description": "Product clarification or decision required",
            },
            "return-kind:architecture-gap": {
                "name": "return-kind:architecture-gap",
                "color": "5319E7",
                "description": "Architecture clarification or decision required",
            },
            "intake-state:pending": {
                "name": "intake-state:pending",
                "color": "FBCA04",
                "description": "Awaiting documentation-side handling",
            },
            "intake-state:handled": {
                "name": "intake-state:handled",
                "color": "0E8A16",
                "description": "Documentation-side follow-up completed or linked",
            },
        }
        prepared_transport = FakeProvisioningTransport(labels)
        self._run("prepare", prepared_transport)
        prepared = self._payload()
        self.stdout.seek(0)
        self.stdout.truncate(0)
        transport = FakeProvisioningTransport(labels)

        code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                "--expected-fingerprint",
                prepared["fingerprint"],
                "--preparation-id",
                prepared["preparation_id"],
                "--approval-reference",
                "human-gate-noop",
            ],
            transport_factory=lambda _token, _github: transport,
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )
        payload = self._payload()

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(payload["actions"], [])
        self.assertEqual(payload["approval_reference"], "human-gate-noop")
        self.assertEqual(transport.post_calls, [])
        required_ids = [
            requirement["name"] for requirement in prepared["requirements"]
        ]
        self.assertEqual(
            [
                (call["operation"], call["stable_id"])
                for call in payload["provider_calls"]
            ],
            [
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
            ],
        )

    def test_execute_propagates_exact_fingerprint_and_approval(self):
        transport = FakeProvisioningTransport()
        self._run("prepare", transport)
        prepared = self._payload()
        self.stdout.seek(0)
        self.stdout.truncate(0)
        execution = FakeProvisioningTransport()

        code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                "--expected-fingerprint",
                prepared["fingerprint"],
                "--preparation-id",
                prepared["preparation_id"],
                "--approval-reference",
                "human-gate-exact",
            ],
            transport_factory=lambda _token, _github: execution,
            environ={"GITHUB_TOKEN": "token-not-for-output"},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )
        payload = self._payload()

        self.assertEqual(code, 0, self.stderr.getvalue())
        self.assertEqual(payload["fingerprint"], prepared["fingerprint"])
        self.assertEqual(
            payload["preparation_id"],
            prepared["preparation_id"],
        )
        self.assertEqual(payload["approval_reference"], "human-gate-exact")
        self.assertEqual(len(execution.post_calls), 5)
        required_ids = [
            requirement["name"] for requirement in prepared["requirements"]
        ]
        self.assertEqual(
            [
                (call["operation"], call["stable_id"])
                for call in payload["provider_calls"]
            ],
            [
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("create", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
            ],
        )
        self.assertNotIn("token-not-for-output", self.stdout.getvalue())

    def test_execute_rejects_changed_fingerprint_without_leaking_token(self):
        transport = FakeProvisioningTransport()

        code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                "--expected-fingerprint",
                "0" * 64,
                "--preparation-id",
                PREPARATION_ID,
                "--approval-reference",
                "human-gate-exact",
            ],
            transport_factory=lambda _token, _github: transport,
            environ={"GITHUB_TOKEN": "secret-not-for-errors"},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )

        self.assertEqual(code, 2)
        self.assertIn("fingerprint changed", self.stderr.getvalue())
        self.assertNotIn("secret-not-for-errors", self.stderr.getvalue())
        self.assertEqual(transport.post_calls, [])

    def test_execute_rejects_malformed_authorization_before_provider_calls(self):
        transport = FakeProvisioningTransport()

        code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                "--expected-fingerprint",
                "not-a-fingerprint",
                "--preparation-id",
                PREPARATION_ID,
                "--approval-reference",
                "human-gate-exact",
            ],
            transport_factory=lambda _token, _github: transport,
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )

        self.assertEqual(code, 2)
        self.assertIn("fingerprint", self.stderr.getvalue())
        self.assertEqual(transport.get_calls, [])
        self.assertEqual(transport.post_calls, [])

    def test_execute_rejects_blank_approval_reference_for_noop(self):
        labels = {
            "return-kind:evidence-result": {
                "name": "return-kind:evidence-result",
                "color": "1D76DB",
                "description": "Returned evidence for validation and routing",
            },
            "return-kind:product-gap": {
                "name": "return-kind:product-gap",
                "color": "D93F0B",
                "description": "Product clarification or decision required",
            },
            "return-kind:architecture-gap": {
                "name": "return-kind:architecture-gap",
                "color": "5319E7",
                "description": "Architecture clarification or decision required",
            },
            "intake-state:pending": {
                "name": "intake-state:pending",
                "color": "FBCA04",
                "description": "Awaiting documentation-side handling",
            },
            "intake-state:handled": {
                "name": "intake-state:handled",
                "color": "0E8A16",
                "description": "Documentation-side follow-up completed or linked",
            },
        }
        transport = FakeProvisioningTransport(labels)
        self._run("prepare", transport)
        prepared = self._payload()
        self.stdout.seek(0)
        self.stdout.truncate(0)

        code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                "--expected-fingerprint",
                prepared["fingerprint"],
                "--preparation-id",
                prepared["preparation_id"],
                "--approval-reference",
                " ",
            ],
            transport_factory=lambda _token, _github: transport,
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )

        self.assertEqual(code, 2)
        self.assertIn("approval_reference", self.stderr.getvalue())
        self.assertEqual(transport.post_calls, [])

    def test_runtime_timeout_is_bound_to_default_transport(self):
        with patch("tools.architecture_handoff.setup_cli.GitHubRestTransport") as factory:
            factory.return_value = FakeProvisioningTransport()

            code = run(
                [
                    "prepare",
                    "--registry",
                    str(self.registry_path),
                    "--runtime",
                    str(self.runtime_path),
                    "--store",
                    "documentation-intake",
                ],
                environ={},
                stdout=self.stdout,
                stderr=self.stderr,
                attempt_store=self.attempt_store,
            )

        self.assertEqual(code, 0, self.stderr.getvalue())
        factory.assert_called_once_with(token=None, timeout_seconds=7)

    def test_partial_failure_emits_structured_ordered_call_ledger(self):
        prepared_transport = FakeProvisioningTransport()
        self._run("prepare", prepared_transport)
        prepared = self._payload()
        self.stdout.seek(0)
        self.stdout.truncate(0)
        execution = FakeProvisioningTransport()
        execution.fail_post_at = 2

        code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                "--expected-fingerprint",
                prepared["fingerprint"],
                "--preparation-id",
                prepared["preparation_id"],
                "--approval-reference",
                "human-gate-partial",
            ],
            transport_factory=lambda _token, _github: execution,
            environ={"GITHUB_TOKEN": "secret-not-for-errors"},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )
        error = self._error_payload()
        required_ids = [
            requirement["name"] for requirement in prepared["requirements"]
        ]

        self.assertEqual(code, 2)
        self.assertEqual(
            error["successful_stable_ids"],
            [required_ids[0]],
        )
        self.assertEqual(error["failed_stable_id"], required_ids[1])
        self.assertEqual(
            [
                (call["operation"], call["stable_id"])
                for call in error["provider_calls"]
            ],
            [
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
                ("create", required_ids[0]),
                ("create", required_ids[1]),
            ],
        )
        self.assertNotIn("secret-not-for-errors", self.stderr.getvalue())

    def test_noop_readback_failure_emits_structured_ordered_call_ledger(self):
        labels = {
            name: {
                "name": name,
                "color": presentation["color"],
                "description": presentation["description"],
            }
            for name, presentation in (
                (
                    "return-kind:evidence-result",
                    {
                        "color": "1D76DB",
                        "description": (
                            "Returned evidence for validation and routing"
                        ),
                    },
                ),
                (
                    "return-kind:product-gap",
                    {
                        "color": "D93F0B",
                        "description": (
                            "Product clarification or decision required"
                        ),
                    },
                ),
                (
                    "return-kind:architecture-gap",
                    {
                        "color": "5319E7",
                        "description": (
                            "Architecture clarification or decision required"
                        ),
                    },
                ),
                (
                    "intake-state:pending",
                    {
                        "color": "FBCA04",
                        "description": (
                            "Awaiting documentation-side handling"
                        ),
                    },
                ),
                (
                    "intake-state:handled",
                    {
                        "color": "0E8A16",
                        "description": (
                            "Documentation-side follow-up completed or linked"
                        ),
                    },
                ),
            )
        }
        prepared_transport = FakeProvisioningTransport(labels)
        self._run("prepare", prepared_transport)
        prepared = self._payload()
        self.stdout.seek(0)
        self.stdout.truncate(0)
        execution = FakeProvisioningTransport(labels)
        execution.fail_get_at = 11

        code = run(
            [
                "execute",
                "--registry",
                str(self.registry_path),
                "--runtime",
                str(self.runtime_path),
                "--store",
                "documentation-intake",
                "--expected-fingerprint",
                prepared["fingerprint"],
                "--preparation-id",
                prepared["preparation_id"],
                "--approval-reference",
                "human-gate-readback",
            ],
            transport_factory=lambda _token, _github: execution,
            environ={},
            stdout=self.stdout,
            stderr=self.stderr,
            attempt_store=self.attempt_store,
        )
        error = self._error_payload()
        required_ids = [
            requirement["name"] for requirement in prepared["requirements"]
        ]

        self.assertEqual(code, 2)
        self.assertEqual(error["successful_stable_ids"], [])
        self.assertEqual(error["failed_stable_id"], required_ids[0])
        self.assertEqual(
            [
                (call["operation"], call["stable_id"])
                for call in error["provider_calls"]
            ],
            [
                *(("inspect", stable_id) for stable_id in required_ids),
                *(("inspect", stable_id) for stable_id in required_ids),
                ("inspect", required_ids[0]),
            ],
        )


if __name__ == "__main__":
    unittest.main()
