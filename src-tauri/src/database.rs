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
    ]
}

#[cfg(test)]
mod tests {
    use super::client_migrations;

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
}
