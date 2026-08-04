import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPOSITORY_ROOT / "tools" / "check_native_transaction_boundary.mjs"


class NativeTransactionBoundaryTests(unittest.TestCase):
    def run_fixture(self, files: dict[str, str], *, allowed: bool) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            fixture_root = Path(directory)
            for relative_path, source in files.items():
                target = fixture_root / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding="utf-8")

            completed = subprocess.run(
                ["node", str(CHECKER), "--root", str(fixture_root)],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assert_checker_exists(completed)
        if allowed:
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        else:
            self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return completed

    def assert_checker_exists(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.assertTrue(
            CHECKER.is_file(),
            "expected RED: tools/check_native_transaction_boundary.mjs is missing\n"
            + completed.stdout
            + completed.stderr,
        )

    def test_allows_the_single_plugin_sql_owner(self):
        self.run_fixture(
            {
                "src/infrastructure/sqlite/plugin-sql-adapter.ts": (
                    'import Database from "@tauri-apps/plugin-sql";\n'
                    'export const read = (database: Database) => database.select("SELECT 1");\n'
                )
            },
            allowed=True,
        )

    def test_allows_read_only_consumers(self):
        self.run_fixture(
            {
                "src/infrastructure/sqlite/plugin-sql-adapter.ts": (
                    'import Database from "@tauri-apps/plugin-sql";\n'
                    "export interface SqlReadDatabase { select(sql: string): Promise<unknown[]> }\n"
                ),
                "src/features/reports/sqlite-report.ts": (
                    'import type { SqlReadDatabase } from "@/infrastructure/sqlite/plugin-sql-adapter";\n'
                    "export const load = (database: SqlReadDatabase) => "
                    'database.select("SELECT * FROM clients");\n'
                ),
            },
            allowed=True,
        )

    def test_allows_only_the_reviewed_independent_executor_consumers(self):
        consumer = (
            'import { getIndependentSqlStatementExecutor } from '
            '"@/infrastructure/sqlite/plugin-sql-adapter";\n'
            "export const save = () => getIndependentSqlStatementExecutor().execute("
            '"UPDATE clients SET name = ? WHERE id = ?", ["Acme", "client-1"]);\n'
        )
        self.run_fixture(
            {
                "src/infrastructure/sqlite/plugin-sql-adapter.ts": (
                    'import Database from "@tauri-apps/plugin-sql";\n'
                    "export const getIndependentSqlStatementExecutor = () => "
                    "({ execute: (sql: string, values: unknown[]) => "
                    "Database.load(\"sqlite:test.db\").then(db => db.execute(sql, values)) });\n"
                ),
                "src/features/clients/sqlite-client-catalog.ts": consumer,
                "src/features/projects/sqlite-project-catalog.ts": consumer.replace(
                    "clients", "projects"
                ),
                "src/features/tasks/sqlite-task-catalog.ts": consumer.replace("clients", "tasks"),
            },
            allowed=True,
        )

    def test_rejects_plugin_sql_import_outside_the_approved_adapter(self):
        self.run_fixture(
            {
                "src/features/clients/unsafe-database.ts": (
                    'import Database from "@tauri-apps/plugin-sql";\n'
                    'export const database = Database.load("sqlite:test.db");\n'
                )
            },
            allowed=False,
        )

    def test_rejects_transaction_verbs_and_syntax_bypasses(self):
        statements = (
            'executor.execute("BEGIN IMMEDIATE")',
            'executor.execute("  -- acquire\\ncommit")',
            'executor.execute("/* nested call */ ROLLBACK")',
            'executor.execute(`SAVEPOINT ${"before_write"}`)',
            'const run = executor.execute.bind(executor); run("RELEASE before_write")',
            'const { execute: run } = executor; run("END TRANSACTION")',
        )
        for index, statement in enumerate(statements):
            with self.subTest(statement=statement):
                self.run_fixture(
                    {
                        "src/features/clients/sqlite-client-catalog.ts": (
                            'import { getIndependentSqlStatementExecutor } from '
                            '"@/infrastructure/sqlite/plugin-sql-adapter";\n'
                            "const executor = getIndependentSqlStatementExecutor();\n"
                            f"{statement};\n"
                        )
                    },
                    allowed=False,
                )

    def test_rejects_dynamic_writes_templates_and_aliases(self):
        statements = (
            'const sql = "UPDATE clients SET name = ?"; executor.execute(sql, ["Acme"])',
            'executor.execute(`UPDATE clients SET name = ${name}`)',
            'const run = executor.execute.bind(executor); run(statement)',
            'const { execute } = executor; execute("DELETE FROM clients WHERE id = ?", [id])',
        )
        for index, statement in enumerate(statements):
            with self.subTest(statement=statement):
                self.run_fixture(
                    {
                        "src/features/clients/sqlite-client-catalog.ts": (
                            'import { getIndependentSqlStatementExecutor } from '
                            '"@/infrastructure/sqlite/plugin-sql-adapter";\n'
                            "declare const name: string, statement: string, id: string;\n"
                            "const executor = getIndependentSqlStatementExecutor();\n"
                            f"{statement};\n"
                        )
                    },
                    allowed=False,
                )

    def test_rejects_multiple_statements(self):
        for statement in (
            'executor.execute("UPDATE clients SET name = ?; DELETE FROM tasks", ["Acme"])',
            'executor.execute(`UPDATE clients SET name = ?; ${suffix}`, ["Acme"])',
        ):
            with self.subTest(statement=statement):
                self.run_fixture(
                    {
                        "src/features/clients/sqlite-client-catalog.ts": (
                            'import { getIndependentSqlStatementExecutor } from '
                            '"@/infrastructure/sqlite/plugin-sql-adapter";\n'
                            "declare const suffix: string;\n"
                            "const executor = getIndependentSqlStatementExecutor();\n"
                            f"{statement};\n"
                        )
                    },
                    allowed=False,
                )

    def test_rejects_independent_executor_allowlist_drift(self):
        self.run_fixture(
            {
                "src/features/reports/sqlite-report.ts": (
                    'import { getIndependentSqlStatementExecutor } from '
                    '"@/infrastructure/sqlite/plugin-sql-adapter";\n'
                    "getIndependentSqlStatementExecutor().execute("
                    '"UPDATE reports SET generated_at = ?", [Date.now()]);\n'
                )
            },
            allowed=False,
        )

    def test_rejects_namespace_executor_access_outside_the_allowlist(self):
        self.run_fixture(
            {
                "src/features/reports/sqlite-report.ts": (
                    'import * as sqlite from "@/infrastructure/sqlite/plugin-sql-adapter";\n'
                    "sqlite.getIndependentSqlStatementExecutor().execute("
                    '"UPDATE reports SET generated_at = ?", [Date.now()]);\n'
                )
            },
            allowed=False,
        )

    def test_rejects_direct_and_element_access_execute_alias_flows(self):
        statements = (
            "const run = executor.execute; run(statement)",
            'executor["execute"]("BEGIN")',
            'const run = executor["execute"]; run("COMMIT")',
            'const first = executor.execute; const second = first; second("ROLLBACK")',
        )
        for statement in statements:
            with self.subTest(statement=statement):
                self.run_fixture(
                    {
                        "src/features/clients/sqlite-client-catalog.ts": (
                            'import { getIndependentSqlStatementExecutor } from '
                            '"@/infrastructure/sqlite/plugin-sql-adapter";\n'
                            "declare const statement: string;\n"
                            "const executor = getIndependentSqlStatementExecutor();\n"
                            f"{statement};\n"
                        )
                    },
                    allowed=False,
                )

    def test_allows_semicolons_inside_sql_literals_and_comments(self):
        for statement in (
            'executor.execute("UPDATE clients SET name = \'A;B\' WHERE id = ?", [id])',
            'executor.execute("UPDATE clients SET name = ? /* audit; marker */ WHERE id = ?", [name, id])',
            'executor.execute("-- audit; marker\\nUPDATE clients SET name = ? WHERE id = ?", [name, id])',
        ):
            with self.subTest(statement=statement):
                self.run_fixture(
                    {
                        "src/features/clients/sqlite-client-catalog.ts": (
                            'import { getIndependentSqlStatementExecutor } from '
                            '"@/infrastructure/sqlite/plugin-sql-adapter";\n'
                            "declare const id: string, name: string;\n"
                            "const executor = getIndependentSqlStatementExecutor();\n"
                            f"{statement};\n"
                        )
                    },
                    allowed=True,
                )

    def test_current_repository_satisfies_the_boundary(self):
        completed = subprocess.run(
            ["node", str(CHECKER), "--root", str(REPOSITORY_ROOT)],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assert_checker_exists(completed)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
