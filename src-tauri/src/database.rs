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
    ]
}

#[cfg(test)]
mod tests {
    use sqlx::{Connection, SqliteConnection};

    use super::client_migrations;

    async fn apply_migration(connection: &mut SqliteConnection, sql: &str) {
        sqlx::raw_sql(sql)
            .execute(connection)
            .await
            .expect("migration should apply as one SQL unit");
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
}
