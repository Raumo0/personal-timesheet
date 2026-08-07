import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "src-tauri" / "Cargo.toml"
BINARY = ROOT / "src-tauri" / "target" / "debug" / (
    "import-timesheet-data.exe" if os.name == "nt" else "import-timesheet-data"
)
EXAMPLE = ROOT / "tools" / "data-import" / "example-v1.json"
SCHEMA = ROOT / "tools" / "data-import" / "schema-v1.json"
DOCS = ROOT / "docs" / "data-import.md"
AJV_2020 = next(
    ROOT.glob("node_modules/.pnpm/ajv@*/node_modules/ajv/dist/2020.js"), None
)


def validate_against_schema(document: dict) -> subprocess.CompletedProcess[str]:
    if AJV_2020 is None:
        raise AssertionError("pnpm-installed Ajv 2020 validator was not found")
    payload = json.dumps(
        {
            "schema": json.loads(SCHEMA.read_text(encoding="utf-8")),
            "document": document,
        }
    )
    script = """
const fs = require("fs");
const Ajv2020 = require(process.argv[1]);
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const validate = new Ajv2020({ allErrors: true, strict: false, validateFormats: false }).compile(input.schema);
if (!validate(input.document)) {
  process.stderr.write(JSON.stringify(validate.errors));
  process.exit(1);
}
"""
    return subprocess.run(
        ["node", "-e", script, str(AJV_2020)],
        cwd=ROOT,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )


def initialize_current_database(path: Path) -> None:
    source = (ROOT / "src-tauri" / "src" / "database.rs").read_text(encoding="utf-8")
    migrations = re.findall(
        r"version:\s*(\d+),\s*description:\s*\"([^\"]+)\",\s*sql:\s*r#\"(.*?)\"#",
        source,
        re.DOTALL,
    )
    if len(migrations) != 6:
        raise AssertionError(f"expected six application migrations, found {len(migrations)}")
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE _sqlx_migrations (
          version BIGINT PRIMARY KEY,
          description TEXT NOT NULL,
          installed_on TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          success BOOLEAN NOT NULL,
          checksum BLOB NOT NULL,
          execution_time BIGINT NOT NULL
        )
        """
    )
    for version, description, sql in migrations:
        connection.executescript(sql)
        connection.execute(
            "INSERT INTO _sqlx_migrations "
            "(version, description, success, checksum, execution_time) "
            "VALUES (?, ?, TRUE, ?, 1)",
            (int(version), description, hashlib.sha384(sql.encode()).digest()),
        )
    connection.commit()
    connection.close()


class TimesheetDataImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            ["cargo", "build", "--manifest-path", str(MANIFEST), "--bin", "import-timesheet-data"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stdout + completed.stderr)

    def run_cli(self, *arguments: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(BINARY), *arguments],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_schema_example_and_operator_documentation_are_versioned_and_coherent(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        documentation = DOCS.read_text(encoding="utf-8")

        self.assertEqual(schema["$id"], "https://personal-timesheet.local/schema/import-v1.json")
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], 1)
        self.assertEqual(example["schemaVersion"], 1)
        self.assertIn("--development", documentation)
        self.assertIn("--production", documentation)
        self.assertIn("--database", documentation)
        self.assertIn("--acknowledge-production com.personal.timesheet", documentation)

    def test_executable_schema_accepts_example_and_rejects_malformed_or_blank_fields(self):
        example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        valid = validate_against_schema(example)
        self.assertEqual(valid.returncode, 0, valid.stderr)

        malformed = json.loads(json.dumps(example))
        del malformed["schemaVersion"]
        cases = [("missing schemaVersion", malformed)]
        for label, collection, field, value in (
            ("blank client name", "clients", "name", "   "),
            ("blank project name", "projects", "name", "\t"),
            ("blank task name", "tasks", "name", "\n"),
            ("blank expense description", "expenses", "description", "  \t"),
        ):
            candidate = json.loads(json.dumps(example))
            candidate[collection][0][field] = value
            cases.append((label, candidate))

        for label, candidate in cases:
            with self.subTest(label=label):
                invalid = validate_against_schema(candidate)
                self.assertNotEqual(invalid.returncode, 0, label)

    def test_preview_is_deterministic_and_leaves_an_eligible_database_byte_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "empty.db"
            initialize_current_database(database)
            before = database.read_bytes()
            command = ("--manifest", str(EXAMPLE), "--database", str(database))

            first = self.run_cli(*command)
            second = self.run_cli(*command)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            preview = json.loads(first.stdout)
            self.assertEqual(preview["operation"], "preview")
            self.assertTrue(preview["eligible"])
            self.assertEqual(preview["counts"]["clients"], 1)
            self.assertEqual(database.read_bytes(), before)

    def test_preview_reports_a_missing_target_without_creating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "missing.db"

            completed = self.run_cli(
                "--manifest", str(EXAMPLE), "--database", str(database)
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            preview = json.loads(completed.stdout)
            self.assertFalse(preview["eligible"])
            self.assertEqual(preview["targetIssue"], "missing")
            self.assertFalse(database.exists())

    def test_preview_reports_a_non_empty_target_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "non-empty.db"
            initialize_current_database(database)
            connection = sqlite3.connect(database)
            connection.execute(
                "INSERT INTO clients VALUES "
                "('existing','Existing','existing','EUR',NULL,'now','now',NULL)"
            )
            connection.commit()
            connection.close()
            before = database.read_bytes()

            completed = self.run_cli(
                "--manifest", str(EXAMPLE), "--database", str(database)
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            preview = json.loads(completed.stdout)
            self.assertFalse(preview["eligible"])
            self.assertEqual(preview["targetIssue"], "non-empty")
            self.assertEqual(database.read_bytes(), before)

    def test_explicit_apply_commits_the_example_to_a_temporary_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "apply.db"
            initialize_current_database(database)

            completed = self.run_cli(
                "--manifest", str(EXAMPLE), "--database", str(database), "--apply"
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            lines = [json.loads(line) for line in completed.stdout.splitlines()]
            self.assertEqual(lines[0]["operation"], "preview")
            self.assertEqual(lines[1]["operation"], "apply")
            connection = sqlite3.connect(database)
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("clients", "projects", "tasks", "time_entries", "expenses")
            }
            connection.close()
            self.assertEqual(counts, {name: 1 for name in counts})

    def test_production_apply_without_exact_acknowledgement_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            environment = dict(os.environ)
            environment["HOME"] = str(home)
            if sys.platform == "darwin":
                database = home / "Library" / "Application Support" / "com.personal.timesheet" / "personal-timesheet.db"
            elif os.name == "nt":
                app_data = Path(directory) / "app-data"
                environment["APPDATA"] = str(app_data)
                database = app_data / "com.personal.timesheet" / "personal-timesheet.db"
            else:
                xdg = Path(directory) / "xdg"
                environment["XDG_CONFIG_HOME"] = str(xdg)
                database = xdg / "com.personal.timesheet" / "personal-timesheet.db"
            database.parent.mkdir(parents=True)
            initialize_current_database(database)

            completed = self.run_cli(
                "--manifest", str(EXAMPLE), "--production", "--apply", env=environment
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("production-acknowledgement-required", completed.stderr)
            connection = sqlite3.connect(database)
            count = connection.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
            connection.close()
            self.assertEqual(count, 0)

    def test_atomic_rollback_contract_remains_executable_from_the_operator_suite(self):
        completed = subprocess.run(
            [
                "cargo",
                "test",
                "--manifest-path",
                str(MANIFEST),
                "data_import::apply_tests::apply_rolls_back_all_prior_inserts_when_a_late_constraint_fails",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("1 passed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
