use tauri_plugin_sql::{Migration, MigrationKind};

pub const DATABASE_URL: &str = "sqlite:personal-timesheet.db";

pub fn client_migrations() -> Vec<Migration> {
    vec![
        Migration {
            version: 1,
            description: "create client catalog",
            sql: r#"
            CREATE TABLE clients (
                id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                currency_code TEXT NOT NULL CHECK (
                    length(currency_code) = 3
                    AND currency_code = upper(currency_code)
                ),
                hourly_rate_minor INTEGER CHECK (
                    hourly_rate_minor IS NULL OR hourly_rate_minor >= 0
                ),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT
            );

            CREATE UNIQUE INDEX clients_active_name_unique
                ON clients(normalized_name)
                WHERE archived_at IS NULL;
        "#,
            kind: MigrationKind::Up,
        },
        Migration {
            version: 2,
            description: "create project catalog",
            sql: r#"
            CREATE TABLE projects (
                id TEXT PRIMARY KEY NOT NULL,
                client_id TEXT NOT NULL REFERENCES clients(id),
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                hourly_rate_override_minor INTEGER CHECK (
                    hourly_rate_override_minor IS NULL OR hourly_rate_override_minor >= 0
                ),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT
            );

            CREATE UNIQUE INDEX projects_active_client_name_unique
                ON projects(client_id, normalized_name)
                WHERE archived_at IS NULL;
        "#,
            kind: MigrationKind::Up,
        },
        Migration {
            version: 3,
            description: "create task catalog",
            sql: r#"
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY NOT NULL,
                project_id TEXT NOT NULL REFERENCES projects(id),
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                hourly_rate_override_minor INTEGER CHECK (
                    hourly_rate_override_minor IS NULL OR hourly_rate_override_minor >= 0
                ),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT
            );

            CREATE UNIQUE INDEX tasks_active_project_name_unique
                ON tasks(project_id, normalized_name)
                WHERE archived_at IS NULL;
        "#,
            kind: MigrationKind::Up,
        },
        Migration {
            version: 4,
            description: "normalize catalog lifecycle hierarchy",
            sql: r#"
            UPDATE projects
            SET archived_at = (
                SELECT clients.archived_at
                FROM clients
                WHERE clients.id = projects.client_id
            )
            WHERE archived_at IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM clients
                  WHERE clients.id = projects.client_id
                    AND clients.archived_at IS NOT NULL
              );

            UPDATE tasks
            SET archived_at = (
                SELECT COALESCE(projects.archived_at, clients.archived_at)
                FROM projects
                JOIN clients ON clients.id = projects.client_id
                WHERE projects.id = tasks.project_id
            )
            WHERE archived_at IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM projects
                  JOIN clients ON clients.id = projects.client_id
                  WHERE projects.id = tasks.project_id
                    AND (
                        projects.archived_at IS NOT NULL
                        OR clients.archived_at IS NOT NULL
                    )
              );
        "#,
            kind: MigrationKind::Up,
        },
        Migration {
            version: 5,
            description: "create weekly time entries",
            sql: r#"
            CREATE TABLE time_entries (
                id TEXT PRIMARY KEY NOT NULL,
                entry_date TEXT NOT NULL CHECK (
                    length(entry_date) = 10
                    AND entry_date = date(entry_date, '+0 days')
                ),
                duration_minutes INTEGER NOT NULL CHECK (
                    typeof(duration_minutes) = 'integer'
                    AND duration_minutes > 0
                    AND duration_minutes <= 1440
                ),
                project_id TEXT REFERENCES projects(id),
                task_id TEXT REFERENCES tasks(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK ((project_id IS NOT NULL) != (task_id IS NOT NULL))
            );

            CREATE UNIQUE INDEX time_entries_project_date_unique
                ON time_entries(project_id, entry_date)
                WHERE project_id IS NOT NULL;

            CREATE UNIQUE INDEX time_entries_task_date_unique
                ON time_entries(task_id, entry_date)
                WHERE task_id IS NOT NULL;
        "#,
            kind: MigrationKind::Up,
        },
    ]
}

#[cfg(test)]
mod tests {
    use sqlx::{Connection, Executor, SqliteConnection};

    use super::client_migrations;

    async fn apply_migration(connection: &mut SqliteConnection, sql: &str) {
        sqlx::raw_sql(sql)
            .execute(connection)
            .await
            .expect("migration should apply as one SQL unit");
    }

    async fn migration_five_database() -> SqliteConnection {
        let mut connection = SqliteConnection::connect("sqlite::memory:")
            .await
            .expect("temporary SQLite database should open");
        connection
            .execute("PRAGMA foreign_keys = ON")
            .await
            .expect("foreign keys should be enabled");
        for migration in client_migrations() {
            apply_migration(&mut connection, migration.sql).await;
        }
        sqlx::raw_sql(
            r#"
            INSERT INTO clients VALUES
              ('client-1', 'Client', 'client', 'EUR', NULL, 'created', 'updated', NULL);
            INSERT INTO projects VALUES
              ('project-1', 'client-1', 'Project', 'project', NULL, 'created', 'updated', NULL);
            INSERT INTO tasks VALUES
              ('task-1', 'project-1', 'Task', 'task', NULL, 'created', 'updated', NULL);
            "#,
        )
        .execute(&mut connection)
        .await
        .expect("catalog fixture should insert");
        connection
    }

    #[test]
    fn initial_migration_defines_clients_and_active_name_uniqueness() {
        let migrations = client_migrations();

        assert_eq!(migrations[0].version, 1);
        assert!(migrations[0].sql.contains("CREATE TABLE clients"));
        assert!(migrations[0].sql.contains("hourly_rate_minor INTEGER"));
        assert!(migrations[0].sql.contains("WHERE archived_at IS NULL"));
    }

    #[test]
    fn second_migration_defines_projects_and_client_scoped_active_name_uniqueness() {
        let migrations = client_migrations();

        assert_eq!(migrations[1].version, 2);
        assert!(migrations[1].sql.contains("CREATE TABLE projects"));
        assert!(migrations[1]
            .sql
            .contains("client_id TEXT NOT NULL REFERENCES clients(id)"));
        assert!(migrations[1]
            .sql
            .contains("hourly_rate_override_minor IS NULL OR hourly_rate_override_minor >= 0"));
        assert!(migrations[1].sql.contains("created_at TEXT NOT NULL"));
        assert!(migrations[1].sql.contains("updated_at TEXT NOT NULL"));
        assert!(migrations[1]
            .sql
            .contains("ON projects(client_id, normalized_name)"));
        assert!(migrations[1].sql.contains("WHERE archived_at IS NULL"));
    }

    #[test]
    fn third_migration_defines_tasks_and_project_scoped_active_name_uniqueness() {
        let migrations = client_migrations();

        assert_eq!(migrations[2].version, 3);
        let normalized_sql = migrations[2]
            .sql
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ");
        assert!(migrations[2].sql.contains("CREATE TABLE tasks"));
        assert!(migrations[2]
            .sql
            .contains("project_id TEXT NOT NULL REFERENCES projects(id)"));
        assert!(normalized_sql.contains(
            "hourly_rate_override_minor INTEGER CHECK ( hourly_rate_override_minor IS NULL OR hourly_rate_override_minor >= 0 )"
        ));
        assert!(migrations[2].sql.contains("created_at TEXT NOT NULL"));
        assert!(migrations[2].sql.contains("updated_at TEXT NOT NULL"));
        assert!(migrations[2]
            .sql
            .contains("ON tasks(project_id, normalized_name)"));
        assert!(migrations[2].sql.contains("WHERE archived_at IS NULL"));
    }

    #[test]
    fn first_three_migrations_still_replay_without_migration_four() {
        tauri::async_runtime::block_on(async {
            let migrations = client_migrations();
            let mut connection = SqliteConnection::connect("sqlite::memory:")
                .await
                .expect("temporary SQLite database should open");

            for migration in migrations.iter().take(3) {
                apply_migration(&mut connection, migration.sql).await;
            }

            for table in ["clients", "projects", "tasks"] {
                let exists: i64 = sqlx::query_scalar(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
                )
                .bind(table)
                .fetch_one(&mut connection)
                .await
                .expect("replayed schema should be readable");
                assert_eq!(exists, 1, "{table} should exist after migrations 1-3");
            }
        });
    }

    #[test]
    fn fourth_migration_atomically_normalizes_archived_ancestor_invariants() {
        tauri::async_runtime::block_on(async {
            let migrations = client_migrations();
            let migration = migrations
                .get(3)
                .expect("migration 4 should normalize catalog lifecycle state");
            assert_eq!(migration.version, 4);

            let mut connection = SqliteConnection::connect("sqlite::memory:")
                .await
                .expect("temporary SQLite database should open");
            for prerequisite in migrations.iter().take(3) {
                apply_migration(&mut connection, prerequisite.sql).await;
            }

            sqlx::raw_sql(
                r#"
                INSERT INTO clients VALUES
                  ('client-1', 'Archived client', 'archived client', 'EUR', NULL, 'created', 'updated', '2026-08-01T09:00:00Z'),
                  ('client-2', 'Active client', 'active client', 'EUR', NULL, 'created', 'updated', NULL),
                  ('client-3', 'Other archived', 'other archived', 'EUR', NULL, 'created', 'updated', '2026-08-03T11:00:00Z');

                INSERT INTO projects VALUES
                  ('project-1', 'client-1', 'Active under archived', 'active under archived', NULL, 'created', 'updated', NULL),
                  ('project-2', 'client-1', 'Previously archived', 'previously archived', NULL, 'created', 'updated', '2026-07-20T07:00:00Z'),
                  ('project-3', 'client-2', 'Unaffected active', 'unaffected active', NULL, 'created', 'updated', NULL),
                  ('project-4', 'client-3', 'Archived project', 'archived project', NULL, 'created', 'updated', '2026-08-02T10:00:00Z'),
                  ('project-5', 'client-3', 'Second active descendant', 'second active descendant', NULL, 'created', 'updated', NULL);

                INSERT INTO tasks VALUES
                  ('task-1', 'project-1', 'Client normalized', 'client normalized', NULL, 'created', 'updated', NULL),
                  ('task-2', 'project-2', 'Nearest project', 'nearest project', NULL, 'created', 'updated', NULL),
                  ('task-3', 'project-2', 'Already archived', 'already archived', NULL, 'created', 'updated', '2026-07-10T06:00:00Z'),
                  ('task-4', 'project-3', 'Unaffected task', 'unaffected task', NULL, 'created', 'updated', NULL),
                  ('task-5', 'project-4', 'Project normalized', 'project normalized', NULL, 'created', 'updated', NULL),
                  ('task-6', 'project-5', 'Other client normalized', 'other client normalized', NULL, 'created', 'updated', NULL);
                "#,
            )
            .execute(&mut connection)
            .await
            .expect("legacy hierarchy fixture should be inserted");

            apply_migration(&mut connection, migration.sql).await;

            let projects: Vec<(String, Option<String>)> =
                sqlx::query_as("SELECT id, archived_at FROM projects ORDER BY id")
                    .fetch_all(&mut connection)
                    .await
                    .expect("normalized projects should be readable");
            assert_eq!(
                projects,
                vec![
                    ("project-1".into(), Some("2026-08-01T09:00:00Z".into())),
                    ("project-2".into(), Some("2026-07-20T07:00:00Z".into())),
                    ("project-3".into(), None),
                    ("project-4".into(), Some("2026-08-02T10:00:00Z".into())),
                    ("project-5".into(), Some("2026-08-03T11:00:00Z".into())),
                ],
            );

            let tasks: Vec<(String, Option<String>)> =
                sqlx::query_as("SELECT id, archived_at FROM tasks ORDER BY id")
                    .fetch_all(&mut connection)
                    .await
                    .expect("normalized tasks should be readable");
            assert_eq!(
                tasks,
                vec![
                    ("task-1".into(), Some("2026-08-01T09:00:00Z".into())),
                    ("task-2".into(), Some("2026-07-20T07:00:00Z".into())),
                    ("task-3".into(), Some("2026-07-10T06:00:00Z".into())),
                    ("task-4".into(), None),
                    ("task-5".into(), Some("2026-08-02T10:00:00Z".into())),
                    ("task-6".into(), Some("2026-08-03T11:00:00Z".into())),
                ],
            );
        });
    }

    #[test]
    fn fifth_migration_stores_project_or_task_minutes_and_timestamps() {
        tauri::async_runtime::block_on(async {
            let migrations = client_migrations();
            assert_eq!(migrations[4].version, 5);

            let mut connection = migration_five_database().await;
            sqlx::query(
                r#"INSERT INTO time_entries
                   (id, entry_date, duration_minutes, project_id, task_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)"#,
            )
            .bind("entry-project")
            .bind("2026-08-03")
            .bind(1440_i64)
            .bind("project-1")
            .bind(Option::<String>::None)
            .bind("2026-08-03T09:00:00.000Z")
            .bind("2026-08-03T09:30:00.000Z")
            .execute(&mut connection)
            .await
            .expect("valid direct project entry should insert");

            let stored: (String, i64, Option<String>, Option<String>, String, String) =
                sqlx::query_as(
                    "SELECT entry_date, duration_minutes, project_id, task_id, created_at, updated_at FROM time_entries",
                )
                .fetch_one(&mut connection)
                .await
                .expect("stored entry should be readable");
            assert_eq!(
                stored,
                (
                    "2026-08-03".into(),
                    1440,
                    Some("project-1".into()),
                    None,
                    "2026-08-03T09:00:00.000Z".into(),
                    "2026-08-03T09:30:00.000Z".into(),
                )
            );
        });
    }

    #[test]
    fn fifth_migration_rejects_invalid_dates_minutes_references_and_work_shape() {
        tauri::async_runtime::block_on(async {
            let mut connection = migration_five_database().await;

            for (id, date, minutes, project_id, task_id) in [
                ("zero", "2026-08-03", 0_i64, Some("project-1"), None),
                ("too-large", "2026-08-03", 1441, Some("project-1"), None),
                ("bad-date", "2026-02-30", 30, Some("project-1"), None),
                ("neither", "2026-08-03", 30, None, None),
                ("both", "2026-08-03", 30, Some("project-1"), Some("task-1")),
                ("missing-project", "2026-08-03", 30, Some("missing"), None),
                ("missing-task", "2026-08-03", 30, None, Some("missing")),
            ] {
                let result = sqlx::query(
                    r#"INSERT INTO time_entries
                       (id, entry_date, duration_minutes, project_id, task_id, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 'created', 'updated')"#,
                )
                .bind(id)
                .bind(date)
                .bind(minutes)
                .bind(project_id)
                .bind(task_id)
                .execute(&mut connection)
                .await;
                assert!(result.is_err(), "{id} should violate migration constraints");
            }

            let fractional_minutes = sqlx::query(
                r#"INSERT INTO time_entries
                   (id, entry_date, duration_minutes, project_id, task_id, created_at, updated_at)
                   VALUES ('fractional', '2026-08-03', ?, 'project-1', NULL, 'created', 'updated')"#,
            )
            .bind(1.5_f64)
            .execute(&mut connection)
            .await;
            assert!(
                fractional_minutes.is_err(),
                "fractional minutes should violate migration constraints"
            );

            let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM time_entries")
                .fetch_one(&mut connection)
                .await
                .expect("entry count should be readable");
            assert_eq!(count, 0, "failed inserts must leave no rows");
        });
    }

    #[test]
    fn fifth_migration_enforces_partial_uniqueness_and_restricts_parent_deletion() {
        tauri::async_runtime::block_on(async {
            let mut connection = migration_five_database().await;

            for statement in [
                "INSERT INTO time_entries VALUES ('project-entry', '2026-08-03', 30, 'project-1', NULL, 'created', 'updated')",
                "INSERT INTO time_entries VALUES ('task-entry', '2026-08-03', 60, NULL, 'task-1', 'created', 'updated')",
            ] {
                sqlx::query(statement)
                    .execute(&mut connection)
                    .await
                    .expect("one Project and one Task entry may share a date");
            }

            for duplicate in [
                "INSERT INTO time_entries VALUES ('project-duplicate', '2026-08-03', 45, 'project-1', NULL, 'created', 'updated')",
                "INSERT INTO time_entries VALUES ('task-duplicate', '2026-08-03', 45, NULL, 'task-1', 'created', 'updated')",
            ] {
                assert!(sqlx::query(duplicate)
                    .execute(&mut connection)
                    .await
                    .is_err());
            }

            assert!(sqlx::query("DELETE FROM projects WHERE id = 'project-1'")
                .execute(&mut connection)
                .await
                .is_err());
            assert!(sqlx::query("DELETE FROM tasks WHERE id = 'task-1'")
                .execute(&mut connection)
                .await
                .is_err());
        });
    }
}
