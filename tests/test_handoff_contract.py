import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class ArchitectureHandoffContractTests(unittest.TestCase):
    def test_package_and_generic_runtime_are_present(self):
        self.assertTrue((ROOT / "tools/architecture_handoff").is_dir())
        runtime = json.loads(read("architecture-handoff.runtime.json"))
        self.assertIn("query_budgets", runtime)
        self.assertIn("github", runtime["providers"])

    def test_root_registry_is_an_inert_example(self):
        registry = json.loads(read("architecture-handoff.registry.json"))
        endpoints = registry["targets"] + registry["stores"]
        self.assertTrue(endpoints)
        self.assertTrue(all(item["routing_status"] == "suspended" for item in endpoints))
        serialized = json.dumps(registry)
        self.assertIn("example-org", serialized)
        self.assertNotIn("Raumo0", serialized)

    def test_vendor_configuration_is_an_obvious_template(self):
        vendor = json.loads(read("architecture-handoff.vendor.json"))
        self.assertEqual(
            vendor,
            {
                "source_repository": "EXAMPLE_SOURCE_REPOSITORY",
                "source_revision": "EXAMPLE_SOURCE_REVISION",
                "package_sha256": "EXAMPLE_PACKAGE_SHA256",
            },
        )

    def test_issue_templates_are_route_specific_and_target_neutral(self):
        expected = {
            "architecture-slice-brief.md": "architecture-slice-handoff",
            "implementation-conformance-referral.md": "implementation-conformance-referral",
            "spike-evidence.md": "spike-evidence",
        }
        for filename, route in expected.items():
            template = read(f".github/ISSUE_TEMPLATE/{filename}")
            self.assertIn(route, template)
            self.assertIn("<logical-target>", template)
            self.assertNotIn("example-implementation", template)

    def test_package_uses_neutral_runtime_identity(self):
        github_adapter = read("tools/architecture_handoff/github.py")
        provisioning = read("tools/architecture_handoff/provisioning_attempts.py")
        self.assertIn('"User-Agent": "architecture-handoff"', github_adapter)
        self.assertIn('state_root / "architecture-handoff"', provisioning)

    def test_package_docs_mark_example_configuration_as_inactive(self):
        readme = read("tools/architecture_handoff/README.md")
        self.assertIn("inactive example configuration", readme)
        self.assertIn("replace every example value", readme)
        self.assertNotIn("GitHub pilot", readme)
        self.assertNotIn("canonical workflow and authority rules live in", readme.lower())

    def test_repository_contains_no_previous_project_identity(self):
        roots = (
            ROOT / "architecture-handoff.registry.json",
            ROOT / "architecture-handoff.vendor.json",
            ROOT / ".github/ISSUE_TEMPLATE",
            ROOT / "tools/architecture_handoff",
        )
        forbidden = ("raumo0", "lotos", "pilot-implementation")
        for root in roots:
            paths = [root] if root.is_file() else root.rglob("*")
            for path in paths:
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                try:
                    content = path.read_text(encoding="utf-8").lower()
                except UnicodeDecodeError:
                    continue
                for term in forbidden:
                    self.assertNotIn(term, content, f"{term} remains in {path}")


if __name__ == "__main__":
    unittest.main()
