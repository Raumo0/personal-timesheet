import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.architecture_handoff.conformance import (
    PACKAGE_MANIFEST_FORMAT,
    PackageManifestError,
    audit_roots,
    main,
    package_tree_manifest,
    package_tree_sha256,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
DOCUMENTATION_GUIDANCE_AVAILABLE = all(
    (REPOSITORY_ROOT / relative_path).is_file()
    for relative_path in (
        "AGENTS.md",
        "handbook/architecture-to-openspec-handoff.md",
        "processes/architecture-to-openspec-handoff.md",
    )
)


class ConformanceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.documentation_root = root / "documentation"
        self.target_root = root / "target"
        self._write_valid_fixture()

    def _write(self, root, relative_path, text):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")

    def _commit_documentation(self, message):
        subprocess.run(
            ["git", "-C", str(self.documentation_root), "init"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(self.documentation_root), "add", "."],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.documentation_root),
                "-c",
                "user.name=Conformance Test",
                "-c",
                "user.email=conformance@example.invalid",
                "commit",
                "-m",
                message,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return subprocess.run(
            ["git", "-C", str(self.documentation_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _write_valid_fixture(self):
        self._write(
            self.documentation_root,
            "processes/architecture-to-openspec-handoff.md",
            """
            ## Work Routing

            architecture-slice-handoff
            implementation-conformance-referral
            spike-evidence
            target-native internal work

            ## Accepted Driving Sources

            Product Requirement recorded as not applicable with a reason

            ## Return Channel

            Return Item

            ## On-Demand Task Discovery

            Load the full payload and linked sources only after the user selects one record.
            required predicates
            advisory candidate enrichment
            one provider page
            continuation cursor
            no derived index
            GitHub semantic
            human semantic disposition

            ## Provider Endpoint Setup

            Setup is explicit and on demand.
            An Implementation target requires work-route:* and status:*.
            A Documentation intake store requires return-kind:* and intake-state:*.
            Prepare the exact provisioning preview with an opaque preparation_id
            and deterministic content fingerprint.
            Obtain the Endpoint Setup Human Gate.
            Execute once with --preparation-id, atomically consume it in the
            local replay ledger outside the repository, does not retry, and
            verify provider readback with an ordered provider call ledger.
            Existing style drift is advisory.
            """,
        )
        self._write(
            self.documentation_root,
            "AGENTS.md",
            """
            ## Architecture-to-OpenSpec Handoff Operations

            semantic on-demand trigger
            Do not poll at session start
            current session language
            English source guidance
            explicit continuation
            drill-down
            show pending evidence returns
            trace correlation corr-12
            find work still citing revision X for ADR-0003
            find similar work for capability Y
            Selection starts inspection, not implementation.
            Run local setup with setup_cli prepare.
            Show the exact preview, fingerprint, and preparation_id, then
            obtain the Endpoint Setup Human Gate.
            Run setup_cli execute once with --preparation-id and verify
            provider readback and the ordered provider call ledger.
            """,
        )
        self._write(
            self.target_root,
            "AGENTS.md",
            """
            ## Protocol Authority

            Product Requirement as not applicable with a reason

            ## On-Demand Work Discovery

            query the entire configured target task store
            Do not poll at session start
            Architecture Slice Handoff
            Implementation Conformance Referral
            Spike / Evidence
            Target-native internal tasks
            current session language
            Load the full payload and linked sources only after the user selects one record.

            ## Inspect and Process One Item

            Selection starts inspection, not implementation.
            Starting work requires separate human authorization.

            ## Target Adoption

            not a routine `work-route`
            status:draft
            status:ready
            all three `work-route:*` labels
            Run local setup with setup_cli prepare.
            Show the exact preview, fingerprint, and preparation_id, then
            obtain the Endpoint Setup Human Gate.
            Run setup_cli execute once with --preparation-id and verify
            provider readback and the ordered provider call ledger.

            ## Evidence and Returns

            Return Item

            ## Return Item Delivery

            Select example-documentation-intake.
            Run return_cli prepare and show the exact preview and fingerprint.
            Obtain the external-write Human Gate.
            Run return_cli execute and verify provider readback.
            """,
        )

        self._write(
            self.target_root,
            "README.md",
            """
            Target Adoption
            Architecture Slice Brief
            Implementation Conformance Referral
            Spike / Evidence
            target-native internal work
            On-Demand Discovery
            OpenSpec
            """,
        )
        self._write(
            self.target_root,
            ".github/ISSUE_TEMPLATE/architecture-slice-brief.md",
            """
            ---
            name: Architecture Slice Brief
            labels: "work-route:architecture-slice-handoff,status:draft"
            ---
            - Work route: `work-route: architecture-slice-handoff`
            - Product Requirement applicability: accepted | not-applicable
            - Profile: skeleton | behavior
            - Correlation ID:
            - Pinned documentation revision:
            """,
        )
        self._write(
            self.target_root,
            ".github/ISSUE_TEMPLATE/implementation-conformance-referral.md",
            """
            ---
            name: Implementation Conformance Referral
            labels: "work-route:implementation-conformance-referral"
            ---
            - Work route: `work-route: implementation-conformance-referral`
            - Observed contradiction:
            - Typed direct source relation:
            - Pinned source revision:
            - Correlation ID:
            - Return Item:
            """,
        )
        self._write(
            self.target_root,
            ".github/ISSUE_TEMPLATE/spike-evidence.md",
            """
            ---
            name: Spike / Evidence
            labels: "work-route:spike-evidence"
            ---
            - Work route: `work-route: spike-evidence`
            - Question:
            - Timebox or stop condition:
            - Required Evidence:
            - Correlation ID:
            - Typed source relation:
            - Pinned source revision or not-applicable reason:
            - Return Item:
            """,
        )
        self._write(
            self.target_root,
            "openspec/config.yaml",
            """
            schema: spec-driven

            rules:
              proposal:
                - Cite the initiating native work item.
                - For an Architecture Slice Handoff, cite the Brief, immutable profile.
                - Cite a Product Requirement when product behavior or acceptance applies; otherwise preserve the Brief's justified not-applicable result.
                - Cite pinned arc42 source references when architecture applies.
                - For an Implementation Conformance Referral, cite the observed contradiction and expected verification.
                - For target-native work, must not invent an upstream parent.
                - For Spike / Evidence, require a separately authorized native work item.
            """,
        )
        registry = {
            "targets": [
                {
                    "key": "example-implementation",
                    "provider": "github",
                    "repository": "owner/implementation",
                    "routing_status": "active",
                    "owns": ["backend"],
                    "excludes": [],
                }
            ],
            "stores": [
                {
                    "key": "example-documentation-intake",
                    "role": "documentation-intake",
                    "provider": "github",
                    "repository": "owner/documentation",
                    "tracker_reference": "github:owner/documentation",
                    "routing_status": "active",
                }
            ],
        }
        runtime = {
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
        for root in (self.documentation_root, self.target_root):
            self._write(
                root,
                "architecture-handoff.registry.json",
                json.dumps(registry, indent=2),
            )
            self._write(
                root,
                "architecture-handoff.runtime.json",
                json.dumps(runtime, indent=2),
            )
            self._write(
                root,
                "tools/architecture_handoff/__init__.py",
                '"""Architecture handoff package."""\n',
            )
            self._write(
                root,
                "tools/architecture_handoff/github_provisioning.py",
                """
                GITHUB_PROTOCOL_LABEL_MANIFEST = {
                    "work-route:architecture-slice-handoff": {},
                    "work-route:implementation-conformance-referral": {},
                    "work-route:spike-evidence": {},
                    "status:draft": {},
                    "status:backlog": {},
                    "status:ready": {},
                    "status:in-progress": {},
                    "status:in-review": {},
                    "status:done": {},
                    "status:cancelled": {},
                    "return-kind:evidence-result": {},
                    "return-kind:product-gap": {},
                    "return-kind:architecture-gap": {},
                    "intake-state:pending": {},
                    "intake-state:handled": {},
                }
                """,
            )
            self._write(
                root,
                "tools/architecture_handoff/README.md",
                """
                ## Provision a Provider Endpoint

                setup_cli prepare
                exact preview
                fingerprint
                preparation_id
                Endpoint Setup Human Gate
                setup_cli execute
                --preparation-id
                provider readback
                ordered provider call ledger
                """,
            )
            self._write(
                root,
                "tools/architecture_handoff/design/endpoint-provisioning.md",
                "# Provider Endpoint Provisioning\n",
            )
            self._write(
                root,
                "tools/architecture_handoff/design/github-adapter.md",
                """
                ## GitHub Label Provisioning

                GitHub-only rollout
                """,
            )
        self._write(
            self.target_root,
            "architecture-handoff.vendor.json",
            json.dumps(
                {
                    "source_repository": (
                        "https://github.com/owner/documentation"
                    ),
                    "source_revision": "a" * 40,
                    "package_sha256": package_tree_sha256(
                        self.documentation_root
                        / "tools/architecture_handoff"
                    ),
                },
                indent=2,
            ),
        )

    def test_package_digest_uses_versioned_canonical_file_manifest(
        self,
    ):
        package_root = Path(self.temporary_directory.name) / "package"
        self._write(package_root, "nested/a.bin", "alpha\n")
        self._write(package_root, "b.txt", "beta\n")
        self._write(package_root, "__pycache__/ignored.py", "ignored")
        self._write(package_root, "ignored.pyc", "ignored")
        manifest = {
            "format": PACKAGE_MANIFEST_FORMAT,
            "files": [
                {
                    "path": "b.txt",
                    "byte_length": 5,
                    "sha256": hashlib.sha256(b"beta\n").hexdigest(),
                },
                {
                    "path": "nested/a.bin",
                    "byte_length": 6,
                    "sha256": hashlib.sha256(b"alpha\n").hexdigest(),
                },
            ],
        }
        expected = hashlib.sha256(
            json.dumps(
                manifest,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        self.assertEqual(package_tree_manifest(package_root), manifest)
        self.assertEqual(package_tree_sha256(package_root), expected)

    def test_package_manifest_enforces_entry_and_total_byte_bounds(self):
        package_root = Path(self.temporary_directory.name) / "package"
        self._write(package_root, "a.txt", "alpha")
        self._write(package_root, "b.txt", "beta")

        with self.assertRaisesRegex(PackageManifestError, "entry limit"):
            package_tree_sha256(package_root, max_entries=1)
        with self.assertRaisesRegex(PackageManifestError, "total byte limit"):
            package_tree_sha256(package_root, max_total_bytes=8)

    def test_package_manifest_caps_all_visited_entries(self):
        package_root = Path(self.temporary_directory.name) / "package"
        for name in ("one", "two", "three"):
            (package_root / name).mkdir(parents=True)

        with self.assertRaisesRegex(
            PackageManifestError,
            r"traversal entry limit exceeded \(2\)",
        ):
            package_tree_manifest(
                package_root,
                max_visited_entries=2,
            )

    def test_package_manifest_prunes_ignored_generated_tree(self):
        package_root = Path(self.temporary_directory.name) / "package"
        self._write(package_root, "safe.py", "safe\n")
        for index in range(20):
            self._write(
                package_root,
                f"__pycache__/ignored-{index}.pyc",
                "ignored",
            )

        manifest = package_tree_manifest(
            package_root,
            max_visited_entries=2,
        )

        self.assertEqual(
            [entry["path"] for entry in manifest["files"]],
            ["safe.py"],
        )

    @unittest.skipUnless(
        hasattr(os, "mkfifo"),
        "FIFO creation is unavailable",
    )
    def test_package_manifest_rejects_non_regular_filesystem_nodes(self):
        package_root = Path(self.temporary_directory.name) / "package"
        package_root.mkdir()
        fifo = package_root / "blocked.pipe"
        os.mkfifo(fifo)

        with self.assertRaisesRegex(
            PackageManifestError,
            r"\Apackage entry must be a regular file or directory\Z",
        ) as raised:
            package_tree_manifest(package_root)

        self.assertEqual(raised.exception.relative_path, "blocked.pipe")

    def test_package_digest_mismatch_is_reported(self):
        self._write(
            self.target_root,
            "tools/architecture_handoff/__init__.py",
            '"""Changed target package."""\n',
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                finding.rule == "target.package-digest"
                for finding in result.findings
            )
        )

    def test_template_vendor_is_rejected_for_active_registry(self):
        vendor_path = self.target_root / "architecture-handoff.vendor.json"
        vendor_path.write_text(
            json.dumps(
                {
                    "source_repository": "EXAMPLE_SOURCE_REPOSITORY",
                    "source_revision": "EXAMPLE_SOURCE_REVISION",
                    "package_sha256": "EXAMPLE_PACKAGE_SHA256",
                }
            ),
            encoding="utf-8",
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(
            any(
                finding.rule == "target.package-provenance"
                and "suspended" in finding.message
                for finding in result.findings
            )
        )

    def test_non_string_vendor_value_is_reported_without_crashing(self):
        vendor_path = self.target_root / "architecture-handoff.vendor.json"
        vendor_path.write_text(
            json.dumps(
                {
                    "source_repository": ["invalid"],
                    "source_revision": "EXAMPLE_SOURCE_REVISION",
                    "package_sha256": "EXAMPLE_PACKAGE_SHA256",
                }
            ),
            encoding="utf-8",
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(
            any(
                finding.rule == "target.package-provenance"
                for finding in result.findings
            )
        )

    def test_later_non_package_commit_preserves_vendor_source_revision(self):
        source_revision = self._commit_documentation(
            "record package source",
        )
        vendor_path = (
            self.target_root / "architecture-handoff.vendor.json"
        )
        vendor = json.loads(vendor_path.read_text(encoding="utf-8"))
        vendor["source_revision"] = source_revision
        vendor_path.write_text(json.dumps(vendor), encoding="utf-8")
        self._write(
            self.documentation_root,
            "implementation-progress.md",
            "Task progress only.\n",
        )
        self._commit_documentation("record implementation progress")

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(result.ok, result.findings)

    def test_missing_documentation_intake_store_is_reported(self):
        registry_path = (
            self.target_root / "architecture-handoff.registry.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["stores"] = []
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                finding.rule == "target.documentation-intake-store"
                for finding in result.findings
            )
        )

    def test_changed_runtime_budget_is_reported(self):
        runtime_path = (
            self.target_root / "architecture-handoff.runtime.json"
        )
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["query_budgets"]["ceiling"]["max_items"] = 1999
        runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                finding.rule == "target.runtime-policy"
                for finding in result.findings
            )
        )

    def test_sensitive_config_key_is_reported_without_value(self):
        registry_path = (
            self.target_root / "architecture-handoff.registry.json"
        )
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["github_token"] = "do-not-report-this-value"
        registry_path.write_text(json.dumps(registry), encoding="utf-8")

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        finding = next(
            finding
            for finding in result.findings
            if finding.rule == "target.config-sensitive-key"
        )
        self.assertNotIn("do-not-report-this-value", finding.message)

    def test_absolute_local_path_in_config_is_reported(self):
        runtime_path = (
            self.target_root / "architecture-handoff.runtime.json"
        )
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime["cache_path"] = "/Users/example/private-cache"
        runtime_path.write_text(json.dumps(runtime), encoding="utf-8")

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(
            any(
                finding.rule == "target.config-local-path"
                for finding in result.findings
            )
        )

    def test_missing_return_runner_guidance_is_reported(self):
        agents_path = self.target_root / "AGENTS.md"
        agents_path.write_text(
            agents_path.read_text(encoding="utf-8").replace(
                "show the exact preview and fingerprint",
                "show the exact preview",
            ),
            encoding="utf-8",
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(
            any(
                finding.rule == "target.return-runner-guidance"
                for finding in result.findings
            )
        )

    def test_missing_target_setup_guidance_is_reported(self):
        agents_path = self.target_root / "AGENTS.md"
        agents_path.write_text(
            agents_path.read_text(encoding="utf-8").replace(
                "exact preview",
                "Show the setup summary.",
            ),
            encoding="utf-8",
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(
            any(
                finding.rule == "target.endpoint-setup-guidance"
                for finding in result.findings
            )
        )

    def test_missing_target_preparation_identity_guidance_is_reported(self):
        agents_path = self.target_root / "AGENTS.md"
        agents_path.write_text(
            agents_path.read_text(encoding="utf-8").replace(
                "preparation_id",
                "setup identifier",
            ),
            encoding="utf-8",
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(
            any(
                finding.rule == "target.endpoint-setup-guidance"
                for finding in result.findings
            )
        )

    def test_missing_documentation_setup_guidance_is_reported(self):
        agents_path = self.documentation_root / "AGENTS.md"
        agents_path.write_text(
            agents_path.read_text(encoding="utf-8").replace(
                "provider readback",
                "Finish setup.",
            ),
            encoding="utf-8",
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(
            any(
                finding.rule == "documentation.endpoint-setup-guidance"
                for finding in result.findings
            )
        )

    def test_missing_endpoint_provisioning_design_is_reported(self):
        (
            self.documentation_root
            / "tools/architecture_handoff/design/endpoint-provisioning.md"
        ).unlink()

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(
            any(
                finding.rule == "documentation.required-file"
                and finding.path
                == "tools/architecture_handoff/design/endpoint-provisioning.md"
                for finding in result.findings
            )
        )

    def test_github_manifest_must_exactly_cover_protocol_labels(self):
        for root in (self.documentation_root, self.target_root):
            manifest_path = (
                root
                / "tools/architecture_handoff/github_provisioning.py"
            )
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace(
                    '    "intake-state:handled": {},\n',
                    '    "provider-only:extra": {},\n',
                ),
                encoding="utf-8",
            )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(
            any(
                finding.rule == "documentation.github-label-manifest"
                for finding in result.findings
            )
        )

    def _write_reconciled_note(self):
        note = Path(self.temporary_directory.name) / "working-note.md"
        note.write_text(
            textwrap.dedent(
                """
                ### Agreement Ledger

                | Agreement | Action refs | State |
                |---|---|---|
                | A-0001 | ACT-0008 | verified |
                | A-0002 | ACT-0007 | mapped |
                | A-0003 | ACT-0011 | mapped |
                | A-0004 | ACT-0008 | verified |

                ### Action Register

                | Action | State |
                |---|---|
                | ACT-0007 | planned |
                | ACT-0008 | done |
                | ACT-0011 | planned |

                ### Coverage Matrix

                | Agreement | Action | State |
                |---|---|---|
                | A-0001 | ACT-0008 | verified |
                | A-0004 | ACT-0008 | verified |
                """
            ).lstrip(),
            encoding="utf-8",
        )
        return note

    def test_valid_roots_produce_machine_readable_pass_result(self):
        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertTrue(result.ok)
        payload = result.to_dict()
        self.assertEqual("pass", payload["status"])
        self.assertEqual("bounded-github-contract", payload["scope"])
        self.assertTrue(payload["limitations"])
        self.assertEqual(str(self.documentation_root.resolve()), payload["roots"]["documentation"])
        self.assertEqual(str(self.target_root.resolve()), payload["roots"]["target"])
        self.assertGreater(payload["checks"], 10)
        self.assertEqual([], payload["findings"])

    @unittest.skipUnless(
        DOCUMENTATION_GUIDANCE_AVAILABLE,
        "documentation repository guidance is not present",
    )
    def test_repository_guidance_preserves_advanced_read_boundaries(self):
        tracked_guidance = "\n".join(
            (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
            for relative_path in (
                "AGENTS.md",
                "handbook/architecture-to-openspec-handoff.md",
                "processes/architecture-to-openspec-handoff.md",
                "tools/architecture_handoff/README.md",
            )
        )

        for required_text in (
            "required predicates",
            "advisory candidate enrichment",
            "one provider page",
            "continuation cursor",
            "no derived index",
            "GitHub semantic",
            "human semantic disposition",
            "Do not poll at session start",
            "New GitLab, Jira, and Markdown adapters remain outside",
        ):
            self.assertIn(required_text, tracked_guidance)

    def test_reconciliation_audit_preserves_deferred_p2(self):
        note = self._write_reconciled_note()

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
            working_note=note,
        )

        self.assertTrue(result.ok)
        self.assertEqual(str(note.resolve()), result.to_dict()["working_note"]["path"])
        self.assertTrue(result.to_dict()["working_note"]["sha256"])

    def test_reconciliation_rejects_hidden_non_p2_mapping(self):
        note = self._write_reconciled_note()
        note.write_text(
            note.read_text(encoding="utf-8").replace(
                "| A-0001 | ACT-0008 | verified |",
                "| A-0001 | ACT-0008 | mapped |",
                1,
            ),
            encoding="utf-8",
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
            working_note=note,
        )

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                finding.rule == "reconciliation.hidden-incomplete"
                for finding in result.findings
            )
        )

    def test_reconciliation_requires_every_ledger_coverage_edge(self):
        note = self._write_reconciled_note()
        edge = "| A-0001 | ACT-0008 | verified |\n"
        before, separator, after = note.read_text(encoding="utf-8").rpartition(edge)
        self.assertEqual(edge, separator)
        note.write_text(before + after, encoding="utf-8")

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
            working_note=note,
        )

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                finding.rule == "reconciliation.p1-coverage"
                for finding in result.findings
            )
        )

    def test_unversioned_roots_fail_the_default_completion_mode(self):
        result = audit_roots(self.documentation_root, self.target_root)

        self.assertFalse(result.ok)
        self.assertTrue(
            any(finding.rule == "documentation.git-revision" for finding in result.findings)
        )
        self.assertTrue(any(finding.rule == "target.git-revision" for finding in result.findings))

    def test_missing_required_surface_fails_closed(self):
        (self.target_root / "openspec/config.yaml").unlink()

        result = audit_roots(self.documentation_root, self.target_root)

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                finding.rule == "target.required-file"
                and finding.path == "openspec/config.yaml"
                for finding in result.findings
            )
        )

    def test_protocol_surface_cannot_escape_declared_root(self):
        outside = Path(self.temporary_directory.name) / "outside.md"
        outside.write_text("Do not poll at session start", encoding="utf-8")
        target_agents = self.target_root / "AGENTS.md"
        target_agents.unlink()
        target_agents.symlink_to(outside)

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                finding.rule == "target.unsafe-path" and finding.path == "AGENTS.md"
                for finding in result.findings
            )
        )

    def test_non_utf8_surface_fails_closed(self):
        (self.target_root / "AGENTS.md").write_bytes(b"\xff\xfe")

        result = audit_roots(self.documentation_root, self.target_root)

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                finding.rule == "target.invalid-text"
                and finding.path == "AGENTS.md"
                for finding in result.findings
            )
        )

    def test_oversized_surface_fails_closed(self):
        (self.target_root / "AGENTS.md").write_bytes(b"x" * 1_048_577)

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                finding.rule == "target.oversized-file"
                and finding.path == "AGENTS.md"
                for finding in result.findings
            )
        )

    def test_missing_on_demand_boundary_is_reported(self):
        target_agents = self.target_root / "AGENTS.md"
        target_agents.write_text(
            target_agents.read_text(encoding="utf-8").replace(
                "Do not poll at session start",
                "Poll at session start\n<!-- Do not poll at session start -->",
            ),
            encoding="utf-8",
        )

        result = audit_roots(self.documentation_root, self.target_root)

        self.assertFalse(result.ok)
        self.assertTrue(
            any(finding.rule == "target.on-demand-no-polling" for finding in result.findings)
        )

    def test_frontmatter_requires_exact_protocol_labels(self):
        brief = self.target_root / ".github/ISSUE_TEMPLATE/architecture-slice-brief.md"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                'labels: "work-route:architecture-slice-handoff,status:draft"',
                'labels: "work-route:architecture-slice-handoff,status:draft,profile:skeleton"',
            ),
            encoding="utf-8",
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertFalse(result.ok)
        self.assertTrue(any(finding.rule == "target.brief-labels" for finding in result.findings))

    def test_spike_requires_source_revision_field(self):
        spike = self.target_root / ".github/ISSUE_TEMPLATE/spike-evidence.md"
        spike.write_text(
            spike.read_text(encoding="utf-8").replace(
                "- Pinned source revision or not-applicable reason:\n", ""
            ),
            encoding="utf-8",
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertFalse(result.ok)
        self.assertTrue(any(finding.rule == "target.spike-contract" for finding in result.findings))

    def test_openspec_requires_conditional_architecture_sources(self):
        config = self.target_root / "openspec/config.yaml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "    - Cite pinned arc42 source references when architecture applies.\n",
                "",
            ),
            encoding="utf-8",
        )

        result = audit_roots(
            self.documentation_root,
            self.target_root,
            require_clean_revisions=False,
        )

        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                finding.rule == "target.openspec-route-conditioning"
                for finding in result.findings
            )
        )

    def test_profiles_are_rejected_outside_brief(self):
        referral = (
            self.target_root
            / ".github/ISSUE_TEMPLATE/implementation-conformance-referral.md"
        )
        referral.write_text(
            referral.read_text(encoding="utf-8") + "\n- Profile: behavior\n",
            encoding="utf-8",
        )

        result = audit_roots(self.documentation_root, self.target_root)

        self.assertFalse(result.ok)
        self.assertTrue(
            any(finding.rule == "target.referral-no-profile" for finding in result.findings)
        )

    def test_cli_emits_json_and_nonzero_exit_on_failure(self):
        (self.target_root / "AGENTS.md").unlink()
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = main(
                [
                    "--documentation-root",
                    str(self.documentation_root),
                    "--target-root",
                    str(self.target_root),
                ]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", payload["status"])
        self.assertTrue(payload["findings"])


if __name__ == "__main__":
    unittest.main()
