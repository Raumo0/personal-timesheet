import json
import subprocess
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]


def read(relative_path):
    path = REPOSITORY_ROOT / relative_path
    assert path.is_file(), f"required repository file is missing: {relative_path}"
    return path.read_text(encoding="utf-8")


class AgenticWorkflowContractTests(unittest.TestCase):
    def test_named_profiles_are_registered(self):
        config = read(".codex/config.toml")
        for profile_id, display_name in (
            ("implementer", "Task Implementer"),
            ("reviewer", "Independent Reviewer"),
        ):
            self.assertIn(f"[agents.{profile_id}]", config)
            profile = read(f".codex/agents/{profile_id}.toml")
            self.assertIn(f'name = "{display_name}"', profile)
            self.assertIn("developer_instructions", profile)

    def test_openspec_owns_active_discovery_and_planning(self):
        guidance = "\n".join((
            read("AGENTS.md"),
            read(".agents/skills/using-superpowers/SKILL.md"),
            read(".agents/skills/subagent-driven-development/SKILL.md"),
        ))
        for required in (
            "$openspec-explore",
            "$openspec-propose",
            "$openspec-update-change",
            "$openspec-apply-change",
            "parallel",
        ):
            self.assertIn(required, guidance)
        self.assertFalse((REPOSITORY_ROOT / "docs/superpowers").exists())

    def test_validation_contract_has_one_ci_entrypoint(self):
        self.assertIn("mandatory", read("docs/agentic-workflow/validation-contract.md").lower())
        self.assertTrue((REPOSITORY_ROOT / "tools/agentic_workflow/validate.py").is_file())
        workflow = read(".github/workflows/validation-contract.yml")
        command = (
            "python3 tools/agentic_workflow/validate.py --output "
            ".agentic-workflow/validation-evidence.json"
        )
        self.assertEqual(workflow.count(command), 1)
        self.assertNotIn("upload-artifact", workflow)

    def test_working_notes_support_is_complete(self):
        for relative_path in (
            ".agents/skills/capturing-working-agreements/SKILL.md",
            "processes/progressive-working-agreement-notes.md",
            "tools/working-notes/resolve_primary_checkout.py",
            "working-notes/README.md",
            "working-notes/TEMPLATE.md",
        ):
            self.assertTrue((REPOSITORY_ROOT / relative_path).is_file())
        ignore_rules = read(".gitignore")
        self.assertIn("working-notes/*", ignore_rules)
        self.assertIn("!/working-notes/README.md", ignore_rules)
        self.assertIn("!/working-notes/TEMPLATE.md", ignore_rules)

    def test_lock_inventory_matches_installed_upstream_skills(self):
        lock = json.loads(read("skills-lock.json"))
        custom_skills = {
            "capturing-working-agreements",
            "implementation-loop",
        }
        installed = {
            path.name
            for path in (REPOSITORY_ROOT / ".agents/skills").iterdir()
            if path.is_dir()
        }
        self.assertTrue(lock["skills"])
        self.assertEqual(installed, set(lock["skills"]) | custom_skills)
        for skill_name, entry in lock["skills"].items():
            self.assertTrue((REPOSITORY_ROOT / ".agents/skills" / skill_name).is_dir())
            self.assertRegex(entry["computedHash"], r"^[0-9a-f]{64}$")

        rules = read("AGENTS.md")
        self.assertIn("Upstream skills", rules)
        self.assertIn("Custom project skills", rules)

    def test_repository_rules_preserve_safety_controls(self):
        instructions = read("AGENTS.md").lower()
        for required in (
            "destructive git",
            "secrets",
            "fresh verification",
            "git status",
            "conventional commits",
            "openspec",
        ):
            self.assertIn(required, instructions)

    def test_readme_is_product_facing_not_agentic_contract(self):
        readme = read("README.md")
        self.assertIn("Personal Timesheet", readme)
        self.assertIn("$openspec-explore", readme)
        self.assertNotIn("establish-agentic-implementation-workflow", readme)

    def test_deferred_packaging_remains_absent(self):
        self.assertFalse((REPOSITORY_ROOT / ".codex-plugin").exists())
        self.assertFalse((REPOSITORY_ROOT / "validation-manifest.json").exists())
        self.assertFalse((REPOSITORY_ROOT / "validation-manifest.yaml").exists())


if __name__ == "__main__":
    unittest.main()
