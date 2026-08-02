import tomllib
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]


def read_toml(relative_path):
    path = REPOSITORY_ROOT / relative_path
    assert path.is_file(), f"required profile file is missing: {relative_path}"
    with path.open("rb") as stream:
        return tomllib.load(stream)


class AgentProfileTests(unittest.TestCase):
    def test_registers_only_the_two_approved_named_profiles(self):
        config = read_toml(".codex/config.toml")

        self.assertEqual(set(config), {"agents"})
        self.assertEqual(set(config["agents"]), {"implementer", "reviewer"})
        self.assertEqual(
            config["agents"]["implementer"],
            {
                "description": (
                    "Implements one authorized OpenSpec task in its assigned worktree"
                ),
                "config_file": "agents/implementer.toml",
                "nickname_candidates": ["Task Implementer"],
            },
        )
        self.assertEqual(
            config["agents"]["reviewer"],
            {
                "description": (
                    "Independently reviews one authorized implementation without "
                    "modifying it"
                ),
                "config_file": "agents/reviewer.toml",
                "nickname_candidates": ["Independent Reviewer"],
            },
        )

    def test_implementer_is_bounded_and_evidence_driven(self):
        profile = read_toml(".codex/agents/implementer.toml")
        instructions = " ".join(profile["developer_instructions"].split())

        self.assertEqual(profile["name"], "Task Implementer")
        self.assertEqual(profile["sandbox_mode"], "workspace-write")
        self.assertNotIn("model", profile)
        self.assertNotIn("model_reasoning_effort", profile)
        for required in (
            "bounded assignment",
            "assigned worktree",
            "OpenSpec task",
            "Red-Green-Refactor",
            "NEEDS_CONTEXT",
            "BLOCKED",
            "Issues",
            "pull requests",
            "agent profiles",
            "Validation Contract",
            "external systems",
            "unrelated files",
            "durable report path",
            "Self-review does not replace independent review",
        ):
            self.assertIn(required, instructions)

    def test_reviewer_is_contextual_read_only_and_cannot_waive_gates(self):
        profile = read_toml(".codex/agents/reviewer.toml")
        instructions = " ".join(profile["developer_instructions"].split())

        self.assertEqual(profile["name"], "Independent Reviewer")
        self.assertEqual(profile["sandbox_mode"], "read-only")
        self.assertNotIn("model", profile)
        self.assertNotIn("model_reasoning_effort", profile)
        for required in (
            "Remain read-only",
            "OpenSpec task",
            "implementation diff",
            "implementer report",
            "deterministic validator evidence",
            "cannot be waived",
            "OpenSpec compliance",
            "test integrity",
            "code quality",
            "security-relevant context",
            "coverage gap",
            "Human Gate",
            "APPROVED",
            "NEEDS_FIXES",
            "BLOCKED",
        ):
            self.assertIn(required, instructions)


if __name__ == "__main__":
    unittest.main()
