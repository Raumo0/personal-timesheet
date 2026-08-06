use std::path::{Path, PathBuf};

use personal_timesheet_lib::invoice::{prepare_invoice_at_path, InvoiceRequest};
use sqlx::{sqlite::SqliteConnectOptions, Connection, SqliteConnection};

struct InvoiceFixture {
    _directory: tempfile::TempDir,
    path: PathBuf,
}

impl InvoiceFixture {
    async fn new() -> Self {
        let directory = tempfile::tempdir().expect("temporary directory should exist");
        let path = directory.path().join("invoice.db");
        let mut database = connect(&path, true).await;
        sqlx::raw_sql(
            r#"
            PRAGMA foreign_keys = ON;
            CREATE TABLE clients (id TEXT PRIMARY KEY, name TEXT NOT NULL, currency_code TEXT NOT NULL, hourly_rate_minor INTEGER, archived_at TEXT);
            CREATE TABLE projects (id TEXT PRIMARY KEY, client_id TEXT NOT NULL REFERENCES clients(id), name TEXT NOT NULL, hourly_rate_override_minor INTEGER, archived_at TEXT);
            CREATE TABLE tasks (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), name TEXT NOT NULL, hourly_rate_override_minor INTEGER, archived_at TEXT);
            CREATE TABLE time_entries (id TEXT PRIMARY KEY, entry_date TEXT NOT NULL, duration_minutes INTEGER NOT NULL, project_id TEXT REFERENCES projects(id), task_id TEXT REFERENCES tasks(id));
            CREATE TABLE expenses (id TEXT PRIMARY KEY, client_id TEXT REFERENCES clients(id), project_id TEXT REFERENCES projects(id), expense_date TEXT NOT NULL, description TEXT NOT NULL, billing_currency_code TEXT NOT NULL, billing_amount_minor INTEGER NOT NULL, archived_at TEXT);

            INSERT INTO clients VALUES
              ('client-1', 'Acme', 'EUR', 6000, NULL),
              ('client-2', 'Other', 'USD', 9000, NULL),
              ('client-archived', 'Old client', 'EUR', 5000, '2026-02-01T00:00:00Z');
            INSERT INTO projects VALUES
              ('project-archived', 'client-1', 'Retained project', 7000, '2026-02-10T00:00:00Z'),
              ('project-active', 'client-1', 'Active project', NULL, NULL),
              ('project-other', 'client-2', 'Other project', NULL, NULL);
            INSERT INTO tasks VALUES
              ('task-archived', 'project-archived', 'Retained category', 8000, '2026-02-10T00:00:00Z'),
              ('task-other', 'project-other', 'Other category', NULL, NULL);
            INSERT INTO time_entries VALUES
              ('time-start', '2026-02-01', 30, NULL, 'task-archived'),
              ('time-end', '2026-02-03', 60, 'project-active', NULL),
              ('time-before', '2026-01-31', 999, 'project-active', NULL),
              ('time-after', '2026-02-04', 999, 'project-active', NULL),
              ('time-other', '2026-02-02', 999, NULL, 'task-other');
            INSERT INTO expenses VALUES
              ('expense-direct', 'client-1', NULL, '2026-02-01', 'Train', 'EUR', 1000, NULL),
              ('expense-project', NULL, 'project-active', '2026-02-03', 'Hotel', 'EUR', 2000, NULL),
              ('expense-archived', 'client-1', NULL, '2026-02-02', 'Archived', 'EUR', 3000, '2026-02-10T00:00:00Z'),
              ('expense-before', 'client-1', NULL, '2026-01-31', 'Before', 'EUR', 4000, NULL),
              ('expense-after', NULL, 'project-active', '2026-02-04', 'After', 'EUR', 5000, NULL),
              ('expense-other', NULL, 'project-other', '2026-02-02', 'Other', 'USD', 6000, NULL),
              ('expense-wrong-currency', 'client-1', NULL, '2026-02-02', 'Wrong currency', 'USD', 7000, NULL);
            "#,
        )
        .execute(&mut database)
        .await
        .expect("invoice fixture should be created");
        database.close().await.expect("fixture should close");
        Self {
            _directory: directory,
            path,
        }
    }

    async fn logical_state(&self) -> Vec<(String, i64)> {
        let mut database = connect(&self.path, false).await;
        let mut state = Vec::new();
        for table in ["clients", "projects", "tasks", "time_entries", "expenses"] {
            let count: i64 = sqlx::query_scalar(&format!("SELECT COUNT(*) FROM {table}"))
                .fetch_one(&mut database)
                .await
                .expect("table count should be readable");
            state.push((table.into(), count));
        }
        state
    }

    async fn deny_source_writes(&self) {
        let mut database = connect(&self.path, false).await;
        for table in ["clients", "projects", "tasks", "time_entries", "expenses"] {
            for operation in ["INSERT", "UPDATE", "DELETE"] {
                let trigger = format!(
                    "CREATE TRIGGER deny_{table}_{} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'invoice source write attempted'); END",
                    operation.to_ascii_lowercase()
                );
                sqlx::query(&trigger)
                    .execute(&mut database)
                    .await
                    .expect("write-denial trigger should install");
            }
        }
    }
}

fn request(client_id: &str) -> InvoiceRequest {
    serde_json::from_value(serde_json::json!({
        "clientId": client_id,
        "senderName": "Studio",
        "issueDate": "2026-02-04",
        "invoiceNumber": null,
        "periodStart": "2026-02-01",
        "periodEnd": "2026-02-03",
        "includedExpenseIds": null,
        "draftRateOverridesMinor": {},
        "paymentNoteEnabled": false,
        "paymentNote": "",
        "includeDailyActivity": false,
        "includeWorkCategoryBreakdown": false
    }))
    .expect("request should deserialize")
}

#[test]
fn loads_inclusive_selected_client_time_with_retained_archived_identities() {
    tauri::async_runtime::block_on(async {
        let fixture = InvoiceFixture::new().await;

        let document = prepare_invoice_at_path(&fixture.path, request("client-1"))
            .await
            .expect("invoice should load");

        assert_eq!(document.total_minutes, 90);
        assert_eq!(document.projects.len(), 2);
        let retained = document
            .projects
            .iter()
            .find(|project| project.id == "project-archived")
            .unwrap();
        assert_eq!(retained.name, "Retained project");
        assert_eq!(retained.work_lines[0].label, "Retained category");
        assert_eq!(retained.work_lines[0].rate_minor, Some(8000));
        assert!(!document
            .projects
            .iter()
            .any(|project| project.id == "project-other"));
    });
}

#[test]
fn loads_only_active_owned_in_period_expenses_in_client_billing_currency() {
    tauri::async_runtime::block_on(async {
        let fixture = InvoiceFixture::new().await;

        let document = prepare_invoice_at_path(&fixture.path, request("client-1"))
            .await
            .expect("invoice should load");

        assert_eq!(
            document
                .expenses
                .iter()
                .map(|expense| expense.id.as_str())
                .collect::<Vec<_>>(),
            vec!["expense-direct", "expense-project"]
        );
        assert_eq!(document.expense_subtotal_minor, 3000);
        assert_eq!(
            document.expenses[1].project_name.as_deref(),
            Some("Active project")
        );
    });
}

#[test]
fn rejects_inactive_or_unknown_clients_and_never_changes_source_rows() {
    tauri::async_runtime::block_on(async {
        let fixture = InvoiceFixture::new().await;
        let before = fixture.logical_state().await;
        fixture.deny_source_writes().await;

        let archived = prepare_invoice_at_path(&fixture.path, request("client-archived")).await;
        let missing = prepare_invoice_at_path(&fixture.path, request("missing")).await;
        prepare_invoice_at_path(&fixture.path, request("client-1"))
            .await
            .expect("valid invoice should load");

        assert!(archived.unwrap_err().starts_with("not-found:"));
        assert!(missing.unwrap_err().starts_with("not-found:"));
        assert_eq!(fixture.logical_state().await, before);
    });
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
