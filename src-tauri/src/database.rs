use tauri_plugin_sql::{Migration, MigrationKind};

pub const DATABASE_URL: &str = "sqlite:personal-timesheet.db";

pub fn client_migrations() -> Vec<Migration> {
    vec![Migration {
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
    }]
}

#[cfg(test)]
mod tests {
    use super::client_migrations;

    #[test]
    fn initial_migration_defines_clients_and_active_name_uniqueness() {
        let migrations = client_migrations();

        assert_eq!(migrations.len(), 1);
        assert_eq!(migrations[0].version, 1);
        assert!(migrations[0].sql.contains("CREATE TABLE clients"));
        assert!(migrations[0].sql.contains("hourly_rate_minor INTEGER"));
        assert!(migrations[0].sql.contains("WHERE archived_at IS NULL"));
    }
}
