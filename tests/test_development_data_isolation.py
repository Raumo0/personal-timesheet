import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


class DevelopmentDataIsolationTests(unittest.TestCase):
    def test_production_and_development_have_distinct_visible_identities(self):
        production = read_json("src-tauri/tauri.conf.json")
        development = read_json("src-tauri/tauri.dev.conf.json")

        self.assertEqual(production["identifier"], "com.personal.timesheet")
        self.assertEqual(production["productName"], "Personal Timesheet")
        self.assertEqual(
            production["app"]["windows"][0]["title"], "Personal Timesheet"
        )
        self.assertEqual(development["identifier"], "com.personal.timesheet.dev")
        self.assertEqual(development["productName"], "Personal Timesheet Dev")
        self.assertEqual(
            development["app"]["windows"][0]["title"], "Personal Timesheet Dev"
        )

    def test_supported_commands_route_to_the_expected_configuration(self):
        package = read_json("package.json")
        self.assertEqual(package["scripts"]["tauri"], "node tools/run-tauri.mjs")

        result = subprocess.run(
            [
                "node",
                "--input-type=module",
                "--eval",
                """
process.argv[1] = './tools/config-contract.mjs'
const { buildTauriArgs } = await import('./tools/run-tauri.mjs')
console.log(JSON.stringify({
  development: buildTauriArgs(['dev']),
  production: buildTauriArgs(['build']),
}))
""",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            json.loads(result.stdout),
            {
                "development": [
                    "dev",
                    "--config",
                    "src-tauri/tauri.dev.conf.json",
                ],
                "production": ["build"],
            },
        )

    def test_readme_documents_commands_and_identifier_derived_storage(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        normalized_readme = " ".join(readme.split())
        required_text = [
            "Development command: `pnpm tauri dev`",
            "Production build command: `pnpm tauri build`",
            "`~/Library/Application Support/com.personal.timesheet/personal-timesheet.db`",
            "`~/Library/Application Support/com.personal.timesheet.dev/personal-timesheet.db`",
            "platform-specific application configuration directory",
            "No data is automatically copied, migrated, or synchronized",
        ]

        for text in required_text:
            with self.subTest(text=text):
                self.assertIn(" ".join(text.split()), normalized_readme)


if __name__ == "__main__":
    unittest.main()
