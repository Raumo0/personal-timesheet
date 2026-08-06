use std::path::Path;

use serde::Deserialize;
use sqlx::{sqlite::SqliteConnectOptions, Connection, Sqlite, SqliteConnection, Transaction};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WeeklyTimeEntryMutationPlan {
    operation: Operation,
    entry_id: String,
    date: String,
    reference: WorkReference,
    minutes: Option<i64>,
    applied_at: String,
    expected: ExpectedState,
}

#[derive(Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
enum Operation {
    Upsert,
    Delete,
}

#[derive(Deserialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
enum WorkReference {
    Project {
        #[serde(rename = "projectId")]
        project_id: String,
    },
    Task {
        #[serde(rename = "taskId")]
        task_id: String,
    },
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct ExpectedState {
    client_archived_at: Option<String>,
    project_archived_at: Option<String>,
    task_archived_at: Option<String>,
    #[serde(default)]
    existing_entry_id: Option<String>,
    existing_minutes: Option<i64>,
    existing_updated_at: Option<String>,
    daily_total: i64,
}

pub async fn apply_at_path(path: &Path, plan: WeeklyTimeEntryMutationPlan) -> Result<(), String> {
    let options = SqliteConnectOptions::new()
        .filename(path)
        .create_if_missing(false);
    let mut connection = SqliteConnection::connect_with(&options)
        .await
        .map_err(|error| format!("persistence: weekly time was not saved: {error}"))?;
    let mut transaction = connection
        .begin()
        .await
        .map_err(|error| format!("persistence: weekly time was not saved: {error}"))?;

    let result = apply_in_transaction(&mut transaction, &plan).await;
    match result {
        Ok(()) => transaction
            .commit()
            .await
            .map_err(|error| format!("persistence: weekly time was not saved: {error}")),
        Err(primary) => match transaction.rollback().await {
            Ok(()) => Err(primary),
            Err(rollback) => Err(format!(
                "{primary}. Transaction rollback also failed: {rollback}"
            )),
        },
    }
}

async fn apply_in_transaction(
    transaction: &mut Transaction<'_, Sqlite>,
    plan: &WeeklyTimeEntryMutationPlan,
) -> Result<(), String> {
    let (client_archived_at, project_archived_at, task_archived_at) =
        hierarchy_state(transaction, &plan.reference).await?;
    if client_archived_at != plan.expected.client_archived_at
        || project_archived_at != plan.expected.project_archived_at
        || task_archived_at != plan.expected.task_archived_at
    {
        return Err("stale-plan: weekly hierarchy changed".into());
    }

    let existing = existing_entry(transaction, &plan.date, &plan.reference).await?;
    let actual_existing_entry_id = existing.as_ref().map(|(id, _, _)| id.clone());
    let actual_existing_minutes = existing.as_ref().map(|(_, minutes, _)| *minutes);
    let actual_existing_updated_at = existing
        .as_ref()
        .map(|(_, _, updated_at)| updated_at.clone());
    if actual_existing_entry_id != plan.expected.existing_entry_id
        || actual_existing_minutes != plan.expected.existing_minutes
        || actual_existing_updated_at != plan.expected.existing_updated_at
    {
        return Err("stale-plan: weekly entry changed".into());
    }

    let daily_total: i64 = sqlx::query_scalar(
        "SELECT COALESCE(SUM(duration_minutes), 0) FROM time_entries WHERE entry_date = ?",
    )
    .bind(&plan.date)
    .fetch_one(&mut **transaction)
    .await
    .map_err(persistence)?;
    if daily_total != plan.expected.daily_total {
        return Err("stale-plan: weekly daily total changed".into());
    }

    match plan.operation {
        Operation::Upsert => {
            if client_archived_at.is_some()
                || project_archived_at.is_some()
                || task_archived_at.is_some()
            {
                return Err("inactive-work: selected work is archived".into());
            }
            let minutes = plan
                .minutes
                .filter(|minutes| *minutes > 0 && *minutes <= 1440)
                .ok_or_else(|| "persistence: invalid duration".to_owned())?;
            let prior = actual_existing_minutes.unwrap_or(0);
            if daily_total - prior + minutes > 1440 {
                return Err("daily-limit: daily total cannot exceed 24:00".into());
            }
            if let Some((entry_id, _, _)) = existing {
                let result = sqlx::query(
                    "UPDATE time_entries SET duration_minutes = ?, updated_at = ? WHERE id = ?",
                )
                .bind(minutes)
                .bind(&plan.applied_at)
                .bind(entry_id)
                .execute(&mut **transaction)
                .await
                .map_err(persistence)?;
                if result.rows_affected() != 1 {
                    return Err("stale-plan: weekly entry changed".into());
                }
            } else {
                let (project_id, task_id): (Option<&str>, Option<&str>) = match &plan.reference {
                    WorkReference::Project { project_id } => (Some(project_id), None),
                    WorkReference::Task { task_id } => (None, Some(task_id)),
                };
                sqlx::query(
                    "INSERT INTO time_entries (id, entry_date, duration_minutes, project_id, task_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                )
                .bind(&plan.entry_id)
                .bind(&plan.date)
                .bind(minutes)
                .bind(project_id)
                .bind(task_id)
                .bind(&plan.applied_at)
                .bind(&plan.applied_at)
                .execute(&mut **transaction)
                .await
                .map_err(persistence)?;
            }
        }
        Operation::Delete => {
            let (entry_id, _, _) =
                existing.ok_or_else(|| "entry-not-found: time entry disappeared".to_owned())?;
            let result = sqlx::query("DELETE FROM time_entries WHERE id = ?")
                .bind(entry_id)
                .execute(&mut **transaction)
                .await
                .map_err(persistence)?;
            if result.rows_affected() != 1 {
                return Err("stale-plan: weekly entry changed".into());
            }
        }
    }
    Ok(())
}

async fn hierarchy_state(
    transaction: &mut Transaction<'_, Sqlite>,
    reference: &WorkReference,
) -> Result<(Option<String>, Option<String>, Option<String>), String> {
    let row = match reference {
        WorkReference::Project { project_id } => sqlx::query_as(
            "SELECT clients.archived_at, projects.archived_at, NULL FROM projects JOIN clients ON clients.id = projects.client_id WHERE projects.id = ?",
        )
        .bind(project_id)
        .fetch_optional(&mut **transaction)
        .await,
        WorkReference::Task { task_id } => sqlx::query_as(
            "SELECT clients.archived_at, projects.archived_at, tasks.archived_at FROM tasks JOIN projects ON projects.id = tasks.project_id JOIN clients ON clients.id = projects.client_id WHERE tasks.id = ?",
        )
        .bind(task_id)
        .fetch_optional(&mut **transaction)
        .await,
    }
    .map_err(persistence)?;
    row.ok_or_else(|| "stale-plan: weekly hierarchy changed".into())
}

async fn existing_entry(
    transaction: &mut Transaction<'_, Sqlite>,
    date: &str,
    reference: &WorkReference,
) -> Result<Option<(String, i64, String)>, String> {
    match reference {
        WorkReference::Project { project_id } => sqlx::query_as(
            "SELECT id, duration_minutes, updated_at FROM time_entries WHERE entry_date = ? AND project_id = ?",
        )
        .bind(date)
        .bind(project_id)
        .fetch_optional(&mut **transaction)
        .await,
        WorkReference::Task { task_id } => sqlx::query_as(
            "SELECT id, duration_minutes, updated_at FROM time_entries WHERE entry_date = ? AND task_id = ?",
        )
        .bind(date)
        .bind(task_id)
        .fetch_optional(&mut **transaction)
        .await,
    }
    .map_err(persistence)
}

fn persistence(error: sqlx::Error) -> String {
    format!("persistence: weekly time was not saved: {error}")
}

#[cfg(test)]
mod tests {
    use sqlx::{sqlite::SqliteConnectOptions, Connection, SqliteConnection};

    use super::{apply_at_path, WeeklyTimeEntryMutationPlan};

    async fn fixture() -> (tempfile::TempDir, std::path::PathBuf) {
        let directory = tempfile::tempdir().expect("temporary directory should exist");
        let path = directory.path().join("weekly.db");
        let options = SqliteConnectOptions::new()
            .filename(&path)
            .create_if_missing(true);
        let mut connection = SqliteConnection::connect_with(&options)
            .await
            .expect("database should open");
        sqlx::raw_sql(
            r#"
            PRAGMA foreign_keys = ON;
            CREATE TABLE clients (id TEXT PRIMARY KEY, archived_at TEXT);
            CREATE TABLE projects (id TEXT PRIMARY KEY, client_id TEXT NOT NULL, archived_at TEXT);
            CREATE TABLE tasks (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, archived_at TEXT);
            CREATE TABLE time_entries (
              id TEXT PRIMARY KEY, entry_date TEXT NOT NULL, duration_minutes INTEGER NOT NULL,
              project_id TEXT, task_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX time_entries_project_date_unique ON time_entries(project_id, entry_date) WHERE project_id IS NOT NULL;
            CREATE UNIQUE INDEX time_entries_task_date_unique ON time_entries(task_id, entry_date) WHERE task_id IS NOT NULL;
            INSERT INTO clients VALUES ('client-1', NULL);
            INSERT INTO projects VALUES ('project-1', 'client-1', NULL);
            INSERT INTO tasks VALUES ('task-1', 'project-1', NULL);
            "#,
        )
        .execute(&mut connection)
        .await
        .expect("fixture should apply");
        connection.close().await.expect("fixture should close");
        (directory, path)
    }

    fn plan(value: serde_json::Value) -> WeeklyTimeEntryMutationPlan {
        serde_json::from_value(value).expect("plan should deserialize")
    }

    #[test]
    fn weekly_time_entry_commits_one_project_row_and_deletes_it() {
        tauri::async_runtime::block_on(async {
            let (_directory, path) = fixture().await;
            let upsert = plan(serde_json::json!({
              "operation":"upsert", "entryId":"entry-1", "date":"2026-08-03",
              "reference":{"kind":"project","projectId":"project-1"}, "minutes":30,
              "appliedAt":"2026-08-05T10:00:00.000Z",
              "expected":{"clientArchivedAt":null,"projectArchivedAt":null,"taskArchivedAt":null,"existingMinutes":null,"existingUpdatedAt":null,"dailyTotal":0}
            }));
            apply_at_path(&path, upsert)
                .await
                .expect("upsert should commit");

            let mut connection = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .expect("database should reopen");
            let row: (String, i64, Option<String>, Option<String>) = sqlx::query_as(
                "SELECT id, duration_minutes, project_id, task_id FROM time_entries",
            )
            .fetch_one(&mut connection)
            .await
            .expect("entry should exist");
            assert_eq!(row, ("entry-1".into(), 30, Some("project-1".into()), None));
            connection.close().await.expect("database should close");

            let update = plan(serde_json::json!({
              "operation":"upsert", "entryId":"must-not-replace-identity", "date":"2026-08-03",
              "reference":{"kind":"project","projectId":"project-1"}, "minutes":45,
              "appliedAt":"2026-08-05T10:01:00.000Z",
              "expected":{"clientArchivedAt":null,"projectArchivedAt":null,"taskArchivedAt":null,"existingEntryId":"entry-1","existingMinutes":30,"existingUpdatedAt":"2026-08-05T10:00:00.000Z","dailyTotal":30}
            }));
            apply_at_path(&path, update)
                .await
                .expect("existing identity should update");
            let mut connection = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .expect("database should reopen");
            let rows: Vec<(String, i64)> =
                sqlx::query_as("SELECT id, duration_minutes FROM time_entries")
                    .fetch_all(&mut connection)
                    .await
                    .expect("entry should load");
            assert_eq!(rows, vec![("entry-1".into(), 45)]);
            connection.close().await.expect("database should close");

            let delete = plan(serde_json::json!({
              "operation":"delete", "entryId":"unused", "date":"2026-08-03",
              "reference":{"kind":"project","projectId":"project-1"}, "minutes":null,
              "appliedAt":"2026-08-05T10:02:00.000Z",
              "expected":{"clientArchivedAt":null,"projectArchivedAt":null,"taskArchivedAt":null,"existingEntryId":"entry-1","existingMinutes":45,"existingUpdatedAt":"2026-08-05T10:01:00.000Z","dailyTotal":45}
            }));
            apply_at_path(&path, delete)
                .await
                .expect("delete should commit");
            let mut connection = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .expect("database should reopen");
            let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM time_entries")
                .fetch_one(&mut connection)
                .await
                .expect("count should load");
            assert_eq!(count, 0);
        });
    }

    #[test]
    fn weekly_time_entry_rechecks_active_path_daily_total_and_rolls_back_failures() {
        tauri::async_runtime::block_on(async {
            let (_directory, path) = fixture().await;
            let mut connection = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .expect("database should reopen");
            sqlx::query("UPDATE clients SET archived_at = 'archived' WHERE id = 'client-1'")
                .execute(&mut connection)
                .await
                .expect("client should archive");
            connection.close().await.expect("database should close");
            let stale = plan(serde_json::json!({
              "operation":"upsert", "entryId":"entry-stale", "date":"2026-08-03",
              "reference":{"kind":"task","taskId":"task-1"}, "minutes":30,
              "appliedAt":"now", "expected":{"clientArchivedAt":null,"projectArchivedAt":null,"taskArchivedAt":null,"existingMinutes":null,"existingUpdatedAt":null,"dailyTotal":0}
            }));
            let error = apply_at_path(&path, stale)
                .await
                .expect_err("archival race should reject");
            assert!(error.starts_with("stale-plan:"), "{error}");

            let (_directory2, path2) = fixture().await;
            let mut connection = SqliteConnection::connect(&format!("sqlite:{}", path2.display()))
                .await
                .expect("database should reopen");
            sqlx::query("INSERT INTO time_entries VALUES ('other', '2026-08-03', 1400, NULL, 'task-1', 'created', 'old')").execute(&mut connection).await.expect("competing entry should insert");
            connection.close().await.expect("database should close");
            let daily_stale = plan(serde_json::json!({
              "operation":"upsert", "entryId":"entry-new", "date":"2026-08-03",
              "reference":{"kind":"project","projectId":"project-1"}, "minutes":60,
              "appliedAt":"now", "expected":{"clientArchivedAt":null,"projectArchivedAt":null,"taskArchivedAt":null,"existingMinutes":null,"existingUpdatedAt":null,"dailyTotal":0}
            }));
            let error = apply_at_path(&path2, daily_stale)
                .await
                .expect_err("daily race should reject");
            assert!(error.starts_with("stale-plan:"), "{error}");
            let over_limit = plan(serde_json::json!({
              "operation":"upsert", "entryId":"entry-new", "date":"2026-08-03",
              "reference":{"kind":"project","projectId":"project-1"}, "minutes":60,
              "appliedAt":"now", "expected":{"clientArchivedAt":null,"projectArchivedAt":null,"taskArchivedAt":null,"existingMinutes":null,"existingUpdatedAt":null,"dailyTotal":1400}
            }));
            let error = apply_at_path(&path2, over_limit)
                .await
                .expect_err("daily limit should reject");
            assert!(error.starts_with("daily-limit:"), "{error}");
            let mut connection = SqliteConnection::connect(&format!("sqlite:{}", path2.display()))
                .await
                .expect("database should reopen");
            let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM time_entries")
                .fetch_one(&mut connection)
                .await
                .expect("count should load");
            assert_eq!(count, 1, "rejected mutation must write nothing");
        });
    }

    #[test]
    fn weekly_time_entry_rolls_back_when_the_write_fails() {
        tauri::async_runtime::block_on(async {
            let (_directory, path) = fixture().await;
            let mut connection = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .expect("database should reopen");
            sqlx::query(
                "CREATE TRIGGER fail_weekly_insert BEFORE INSERT ON time_entries BEGIN SELECT RAISE(ABORT, 'weekly insert failed'); END",
            )
            .execute(&mut connection)
            .await
            .expect("failure trigger should install");
            connection.close().await.expect("database should close");
            let mutation = plan(serde_json::json!({
              "operation":"upsert", "entryId":"entry-failed", "date":"2026-08-03",
              "reference":{"kind":"project","projectId":"project-1"}, "minutes":30,
              "appliedAt":"now", "expected":{"clientArchivedAt":null,"projectArchivedAt":null,"taskArchivedAt":null,"existingMinutes":null,"existingUpdatedAt":null,"dailyTotal":0}
            }));

            let error = apply_at_path(&path, mutation)
                .await
                .expect_err("trigger should abort the transaction");
            assert!(error.contains("weekly insert failed"), "{error}");
            let mut connection = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .expect("database should reopen");
            let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM time_entries")
                .fetch_one(&mut connection)
                .await
                .expect("count should load");
            assert_eq!(count, 0);
        });
    }

    #[test]
    fn weekly_time_entry_rejects_an_aba_entry_identity_race() {
        tauri::async_runtime::block_on(async {
            let (_directory, path) = fixture().await;
            let mut connection = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .expect("database should reopen");
            sqlx::query("INSERT INTO time_entries VALUES ('entry-original', '2026-08-03', 30, 'project-1', NULL, 'created', 'same-update')")
                .execute(&mut connection)
                .await
                .expect("original entry should insert");
            sqlx::query("DELETE FROM time_entries WHERE id = 'entry-original'")
                .execute(&mut connection)
                .await
                .expect("original entry should delete");
            sqlx::query("INSERT INTO time_entries VALUES ('entry-recreated', '2026-08-03', 30, 'project-1', NULL, 'created', 'same-update')")
                .execute(&mut connection)
                .await
                .expect("replacement entry should insert");
            connection.close().await.expect("database should close");
            let mutation = plan(serde_json::json!({
              "operation":"upsert", "entryId":"unused", "date":"2026-08-03",
              "reference":{"kind":"project","projectId":"project-1"}, "minutes":45,
              "appliedAt":"now", "expected":{"clientArchivedAt":null,"projectArchivedAt":null,"taskArchivedAt":null,"existingEntryId":"entry-original","existingMinutes":30,"existingUpdatedAt":"same-update","dailyTotal":30}
            }));

            let error = apply_at_path(&path, mutation)
                .await
                .expect_err("recreated identity should make the plan stale");
            assert!(error.starts_with("stale-plan:"), "{error}");
        });
    }
}
