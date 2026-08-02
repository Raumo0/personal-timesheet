import importlib.util
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
VALIDATOR_PATH = REPOSITORY_ROOT / "tools/agentic_workflow/validate.py"


def load_validator():
    assert VALIDATOR_PATH.is_file(), "validator entrypoint is missing"
    spec = importlib.util.spec_from_file_location("agentic_validator", VALIDATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_contract(root, rows):
    contract = root / "validation-contract.md"
    lines = [
        "## Gate registry",
        "",
        "| Order | Gate ID | Applicability | Mandatory | Timeout | Command |",
        "|---:|---|---|---|---:|---|",
    ]
    lines.extend(f"| {order} | {gate} | {app} | {mandatory} | {timeout} | `{command}` |" for order, gate, app, mandatory, timeout, command in rows)
    contract.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return contract


def initialize_git_repository(root):
    for arguments in (
        ["git", "init", "--quiet", str(root)],
        ["git", "-C", str(root), "config", "user.email", "validator@example.test"],
        ["git", "-C", str(root), "config", "user.name", "Validator Test"],
    ):
        subprocess.run(arguments, check=True, capture_output=True)


class AgenticValidatorTests(unittest.TestCase):
    def test_local_evidence_directory_is_ignored(self):
        ignore_rules = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/.agentic-workflow/", ignore_rules)

    def test_discovers_gates_and_runs_them_in_declared_order(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = write_contract(
                root,
                [
                    (20, "second", "always", "yes", 5, f'{sys.executable} -c "print(2)"'),
                    (10, "first", "always", "yes", 5, f'{sys.executable} -c "print(1)"'),
                ],
            )

            evidence = validator.run_validation(root, contract)

        self.assertEqual([gate["id"] for gate in evidence["gates"]], ["first", "second"])
        self.assertEqual([gate["status"] for gate in evidence["gates"]], ["pass", "pass"])
        self.assertEqual(evidence["overall_status"], "pass")

    def test_reports_fail_skipped_and_not_applicable_statuses(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = write_contract(
                root,
                [
                    (10, "failed", "always", "yes", 5, f'{sys.executable} -c "import sys; sys.exit(3)"'),
                    (20, "skipped", "always", "yes", 5, f'{sys.executable} -c "print(2)"'),
                    (30, "absent", "path:missing", "yes", 5, f'{sys.executable} -c "print(3)"'),
                ],
            )

            evidence = validator.run_validation(root, contract, skip_ids={"skipped"})

        self.assertEqual(
            {gate["id"]: gate["status"] for gate in evidence["gates"]},
            {"failed": "fail", "skipped": "skipped", "absent": "not-applicable"},
        )
        self.assertEqual(evidence["overall_status"], "fail")

    def test_timeout_and_unavailable_tool_are_blocking(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = write_contract(
                root,
                [
                    (10, "timeout", "always", "yes", 0.05, f'{sys.executable} -c "import time; print(\'before timeout\', flush=True); time.sleep(1)"'),
                    (20, "missing-tool", "always", "yes", 5, "definitely-missing-validator-tool --version"),
                ],
            )

            evidence = validator.run_validation(root, contract)

        gates = {gate["id"]: gate for gate in evidence["gates"]}
        self.assertEqual(gates["timeout"]["status"], "fail")
        self.assertIn("timed out", gates["timeout"]["reason"])
        self.assertIn("before timeout", gates["timeout"]["output"])
        self.assertEqual(gates["missing-tool"]["status"], "skipped")
        self.assertIn("unavailable", gates["missing-tool"]["reason"])
        self.assertEqual(evidence["overall_status"], "fail")

    def test_redacts_sensitive_output_and_writes_json_evidence(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = (
                f"{sys.executable} -c \"import sys; print('token=abc123 password: hunter2 "
                "authorization: Bearer bearer-secret ghp_abcdefghijklmnop "
                "GHU_UPPERCASE token value \\\"secret\\\": \\\"json-secret\\\" "
                "Authorization: Basic basic-secret'); sys.stderr.write('SECRET stderr-secret')\""
            )
            contract = write_contract(
                root, [(10, "redaction", "always", "yes", 5, command)]
            )
            output = root / "evidence.json"

            exit_code = validator.main(
                ["--repository", str(root), "--contract", str(contract), "--output", str(output)]
            )
            evidence = json.loads(output.read_text(encoding="utf-8"))

        serialized = json.dumps(evidence)
        self.assertEqual(exit_code, 0)
        self.assertNotIn("abc123", serialized)
        self.assertNotIn("hunter2", serialized)
        self.assertNotIn("bearer-secret", serialized)
        self.assertNotIn("ghp_abcdefghijklmnop", serialized)
        self.assertNotIn("UPPERCASE", serialized)
        self.assertNotIn("json-secret", serialized)
        self.assertNotIn("basic-secret", serialized)
        self.assertNotIn("stderr-secret", serialized)
        self.assertIn("[REDACTED]", serialized)

    def test_prints_the_same_redacted_evidence_after_writing_it(self):
        """Catches a successful validator run whose CI log omits structured diagnostics."""
        validator = load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = write_contract(
                root,
                [(10, "diagnostic", "always", "yes", 5, f'{sys.executable} -c "print(\'token=secret-value\')"')],
            )
            output = root / "evidence.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = validator.main(
                    ["--repository", str(root), "--contract", str(contract), "--output", str(output)]
                )

            emitted = stdout.getvalue()
            persisted = output.read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertEqual(emitted, persisted)
        self.assertIn("[REDACTED]", emitted)
        self.assertNotIn("secret-value", emitted)

    def test_binds_dirty_worktree_contents_and_excludes_local_evidence(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize_git_repository(root)
            tracked = root / "tracked.txt"
            tracked.write_text("original\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "--quiet", "-m", "initial"], check=True)
            tracked.write_text("first dirty value\n", encoding="utf-8")
            first = validator.repository_identity(root)
            tracked.write_text("second dirty value\n", encoding="utf-8")
            second = validator.repository_identity(root)
            (root / ".agentic-workflow").mkdir()
            (root / ".agentic-workflow" / "validation-evidence.json").write_text("local", encoding="utf-8")
            third = validator.repository_identity(root)

        self.assertEqual(first["worktree_state"], second["worktree_state"])
        self.assertNotEqual(first["worktree_digest"], second["worktree_digest"])
        self.assertEqual(second["worktree_digest"], third["worktree_digest"])
        self.assertIn(".agentic-workflow/", third["worktree_digest_exclusions"])

    def test_redacts_structured_and_space_separated_authorization_values(self):
        validator = load_validator()
        diagnostic = "\n".join(
            (
                '{"authorization": "Basic basic-secret"}',
                '{"Authorization": "Bearer bearer-secret"}',
                "AUTHORIZATION Basic space-secret",
            )
        )

        redacted = validator.redact(diagnostic)

        self.assertNotIn("basic-secret", redacted)
        self.assertNotIn("bearer-secret", redacted)
        self.assertNotIn("space-secret", redacted)
        self.assertIn("authorization", redacted.lower())

    def test_rejects_invalid_or_unrelated_contract_tables(self):
        validator = load_validator()
        invalid_rows = (
            ([(10, "gate", "always", "maybe", 5, "echo ok")], "mandatory"),
            ([(10, "gate", "always", "yes", 0, "echo ok")], "timeout"),
            ([(10, "gate", "always", "yes", 5, "")], "command"),
            ([(10, "duplicate", "always", "yes", 5, "echo one"), (20, "duplicate", "always", "yes", 5, "echo two")], "duplicate"),
            ([(10, "first", "always", "yes", 5, "echo one"), (10, "second", "always", "yes", 5, "echo two")], "duplicate"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for rows, reason in invalid_rows:
                with self.subTest(reason=reason, rows=rows):
                    with self.assertRaisesRegex(ValueError, reason):
                        validator.parse_contract(write_contract(root, rows))
            contract = root / "validation-contract.md"
            contract.write_text(
                "| unrelated | six | column | table | for | prose |\n"
                "|---|---|---|---|---|---|\n"
                "| one | two | three | four | five | six |\n"
                "\n## Gate registry\n\n"
                "| Order | Gate ID | Applicability | Mandatory | Timeout | Command |\n"
                "|---:|---|---|---|---:|---|\n"
                "| 10 | valid | always | no | 5 | `echo ok` |\n",
                encoding="utf-8",
            )
            self.assertEqual([gate["id"] for gate in validator.parse_contract(contract)], ["valid"])

    def test_optional_failures_do_not_fail_overall_and_relative_output_uses_repository(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as elsewhere:
            root = Path(directory)
            contract = write_contract(
                root,
                [
                    (10, "optional-fail", "always", "no", 5, f'{sys.executable} -c "import sys; sys.exit(2)"'),
                    (20, "optional-skip", "always", "no", 5, "missing-optional-tool --version"),
                ],
            )
            original_directory = Path.cwd()
            try:
                import os
                os.chdir(elsewhere)
                exit_code = validator.main(["--repository", str(root), "--contract", str(contract), "--output", "evidence.json"])
            finally:
                os.chdir(original_directory)

            evidence = json.loads((root / "evidence.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["gates"][0]["status"], "fail")
        self.assertEqual(evidence["gates"][1]["status"], "skipped")
        self.assertEqual(evidence["overall_status"], "pass")


if __name__ == "__main__":
    unittest.main()
