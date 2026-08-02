import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
SKILL_PATH = REPOSITORY_ROOT / ".agents/skills/using-superpowers/SKILL.md"
CODEX_REFERENCE_PATH = (
    REPOSITORY_ROOT
    / ".agents/skills/using-superpowers/references/codex-tools.md"
)


class UsingSuperpowersAdaptationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = SKILL_PATH.read_text(encoding="utf-8")
        cls.codex_reference = CODEX_REFERENCE_PATH.read_text(encoding="utf-8")

    def test_openspec_route_is_explicit_and_complete(self):
        for required in (
            "Repositories governed by OpenSpec",
            "$openspec-explore",
            "$openspec-propose",
            "$openspec-update-change",
            "$openspec-apply-change",
            "sole discovery, design, and planning authority",
            "Human Gate",
        ):
            self.assertIn(required, self.skill)

    def test_openspec_route_forbids_parallel_planning(self):
        _, marker, remainder = self.skill.partition(
            "**Repositories governed by OpenSpec:**"
        )
        self.assertTrue(marker, "OpenSpec routing section is missing")
        openspec_section, boundary, _ = remainder.partition("**Other repositories")
        self.assertTrue(boundary, "non-OpenSpec routing boundary is missing")
        for forbidden in (
            "`brainstorming`",
            "`writing-plans`",
            "`docs/superpowers`",
        ):
            self.assertIn(forbidden, openspec_section)
        self.assertIn("Do not invoke", openspec_section)

    def test_routes_only_to_installed_local_skills(self):
        for stale_reference in (
            "executing-plans",
            "systematic-debugging",
            "superpowers:",
        ):
            self.assertNotIn(stale_reference, self.skill)

    def test_codex_reference_uses_current_runtime_and_authority_rules(self):
        for stale_claim in (
            "close_agent",
            "[features]",
            "multi_agent = true",
            "commits all work",
            "stage files",
        ):
            self.assertNotIn(stale_claim, self.codex_reference)
        self.assertIn("explicit authority", self.codex_reference)

    def test_non_openspec_behavior_is_preserved(self):
        self.assertIn("Other repositories, before entering plan mode", self.skill)
        self.assertIn("brainstorming skill first", self.skill)


if __name__ == "__main__":
    unittest.main()
