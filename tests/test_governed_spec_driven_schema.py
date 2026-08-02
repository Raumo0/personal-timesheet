import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
OPENSPEC = REPOSITORY_ROOT / "node_modules/.bin/openspec"


class GovernedSpecDrivenSchemaTests(unittest.TestCase):
    def run_openspec(self, repository, *arguments):
        completed = subprocess.run(
            [str(OPENSPEC), *arguments, "--json"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode, 0, completed.stdout + completed.stderr
        )
        return json.loads(completed.stdout)

    def test_governed_schema_creates_governance_artifacts_and_apply_context(self):
        """Catches a governed schema that omits its validation/review lifecycle."""
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / "repository"
            shutil.copytree(REPOSITORY_ROOT / "openspec", repository / "openspec")

            created = self.run_openspec(
                repository,
                "new",
                "change",
                "schema-contract",
                "--schema",
                "governed-spec-driven",
            )
            self.assertEqual(created["change"]["id"], "schema-contract")

            status = self.run_openspec(
                repository, "status", "--change", "schema-contract"
            )
            artifacts = {artifact["id"]: artifact for artifact in status["artifacts"]}
            self.assertEqual(
                list(artifacts),
                ["proposal", "specs", "design", "tasks", "validation", "review"],
            )
            self.assertEqual(artifacts["validation"]["requires"], ["tasks"])
            self.assertEqual(artifacts["review"]["requires"], ["validation"])

            change = repository / "openspec/changes/schema-contract"
            (change / ".openspec.yaml").write_text(
                "schema: governed-spec-driven\nskip_specs: true\n", encoding="utf-8"
            )
            (change / "proposal.md").write_text("## Why\n\nTest.\n", encoding="utf-8")
            (change / "design.md").write_text("## Context\n\nTest.\n", encoding="utf-8")
            (change / "tasks.md").write_text("## Tasks\n\n- [ ] 1.1 Test.\n", encoding="utf-8")

            blocked_apply = self.run_openspec(
                repository, "instructions", "apply", "--change", "schema-contract"
            )
            self.assertEqual(blocked_apply["state"], "blocked")
            self.assertEqual(
                blocked_apply["missingArtifacts"], ["validation", "review"]
            )

            (change / "validation.md").write_text("## Evidence\n\nTest.\n", encoding="utf-8")
            (change / "review.md").write_text("## Review\n\nTest.\n", encoding="utf-8")

            apply = self.run_openspec(
                repository, "instructions", "apply", "--change", "schema-contract"
            )
            self.assertEqual(apply["state"], "ready")
            self.assertEqual(
                apply["contextFiles"],
                {
                    "proposal": [str((change / "proposal.md").resolve())],
                    "design": [str((change / "design.md").resolve())],
                    "tasks": [str((change / "tasks.md").resolve())],
                    "validation": [str((change / "validation.md").resolve())],
                    "review": [str((change / "review.md").resolve())],
                },
            )


if __name__ == "__main__":
    unittest.main()
