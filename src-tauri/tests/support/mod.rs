use std::path::{Path, PathBuf};

use sqlx::{sqlite::SqliteConnectOptions, Connection, SqliteConnection};

pub struct CatalogFixture {
    _directory: tempfile::TempDir,
    pub path: PathBuf,
}

#[derive(Debug, PartialEq)]
pub struct CatalogState {
    pub client: (String, String, i64, String),
    pub projects: Vec<(String, Option<i64>, String)>,
    pub tasks: Vec<(String, Option<i64>, String)>,
}

#[derive(Debug, PartialEq)]
pub struct LifecycleState {
    pub clients: Vec<(String, Option<String>, String)>,
    pub projects: Vec<(String, Option<String>, String)>,
    pub tasks: Vec<(String, Option<String>, String)>,
    pub expenses: Vec<(String, Option<String>, String)>,
}

impl CatalogFixture {
    pub async fn new() -> Self {
        let directory = tempfile::tempdir().expect("temporary directory should exist");
        let path = directory.path().join("catalog.db");
        let mut connection = connect(&path, true).await;
        sqlx::raw_sql(
            r#"
            PRAGMA foreign_keys = ON;
            CREATE TABLE clients (
                id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                currency_code TEXT NOT NULL,
                hourly_rate_minor INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT
            );
            CREATE TABLE projects (
                id TEXT PRIMARY KEY NOT NULL,
                client_id TEXT NOT NULL REFERENCES clients(id),
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                hourly_rate_override_minor INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT
            );
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY NOT NULL,
                project_id TEXT NOT NULL REFERENCES projects(id),
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                hourly_rate_override_minor INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT
            );
            CREATE TABLE expenses (
                id TEXT PRIMARY KEY NOT NULL,
                client_id TEXT REFERENCES clients(id),
                project_id TEXT REFERENCES projects(id),
                description TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT,
                CHECK ((client_id IS NOT NULL) != (project_id IS NOT NULL))
            );
            INSERT INTO clients VALUES
              ('client-1', 'Acme', 'acme', 'EUR', 12500, '2026-07-30T08:00:00.000Z', '2026-07-31T09:00:00.000Z', NULL);
            INSERT INTO projects VALUES
              ('project-1', 'client-1', 'Website', 'website', 12500, 'created', 'old', NULL),
              ('project-null', 'client-1', 'Internal', 'internal', NULL, 'created', 'old', NULL);
            INSERT INTO tasks VALUES
              ('task-1', 'project-1', 'Research', 'research', 7500, 'created', 'old', NULL),
              ('task-null', 'project-1', 'Coordination', 'coordination', NULL, 'created', 'old', NULL);
            "#,
        )
        .execute(&mut connection)
        .await
        .expect("catalog fixture should be created");
        connection.close().await.expect("fixture should close");
        Self {
            _directory: directory,
            path,
        }
    }

    pub async fn execute(&self, sql: &str) {
        let mut connection = connect(&self.path, false).await;
        sqlx::raw_sql(sql)
            .execute(&mut connection)
            .await
            .expect("fixture mutation should succeed");
    }

    pub async fn state(&self) -> CatalogState {
        let mut connection = connect(&self.path, false).await;
        let client = sqlx::query_as(
            "SELECT name, currency_code, hourly_rate_minor, updated_at FROM clients WHERE id = 'client-1'",
        )
        .fetch_one(&mut connection)
        .await
        .expect("client state should be readable");
        let projects = sqlx::query_as(
            "SELECT id, hourly_rate_override_minor, updated_at FROM projects ORDER BY id",
        )
        .fetch_all(&mut connection)
        .await
        .expect("project state should be readable");
        let tasks = sqlx::query_as(
            "SELECT id, hourly_rate_override_minor, updated_at FROM tasks ORDER BY id",
        )
        .fetch_all(&mut connection)
        .await
        .expect("task state should be readable");
        CatalogState {
            client,
            projects,
            tasks,
        }
    }

    pub async fn lifecycle_state(&self) -> LifecycleState {
        let mut connection = connect(&self.path, false).await;
        let clients = sqlx::query_as("SELECT id, archived_at, updated_at FROM clients ORDER BY id")
            .fetch_all(&mut connection)
            .await
            .expect("Client lifecycle state should be readable");
        let projects =
            sqlx::query_as("SELECT id, archived_at, updated_at FROM projects ORDER BY id")
                .fetch_all(&mut connection)
                .await
                .expect("Project lifecycle state should be readable");
        let tasks = sqlx::query_as("SELECT id, archived_at, updated_at FROM tasks ORDER BY id")
            .fetch_all(&mut connection)
            .await
            .expect("Task lifecycle state should be readable");
        let expenses =
            sqlx::query_as("SELECT id, archived_at, updated_at FROM expenses ORDER BY id")
                .fetch_all(&mut connection)
                .await
                .expect("Expense lifecycle state should be readable");
        LifecycleState {
            clients,
            projects,
            tasks,
            expenses,
        }
    }
}

async fn connect(path: &Path, create_if_missing: bool) -> SqliteConnection {
    SqliteConnection::connect_with(
        &SqliteConnectOptions::new()
            .filename(path)
            .create_if_missing(create_if_missing),
    )
    .await
    .expect("temporary SQLite database should open")
}
