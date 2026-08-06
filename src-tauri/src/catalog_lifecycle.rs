use std::path::Path;

use serde::Deserialize;
use sqlx::{sqlite::SqliteConnectOptions, Connection, Sqlite, SqliteConnection, Transaction};

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LifecyclePlan {
    operation: Operation,
    target: Target,
    records: Vec<Record>,
    impact_description: String,
}

#[derive(Clone, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
enum Operation {
    Archive,
    Restore,
}

#[derive(Clone, Deserialize)]
struct Target {
    kind: Kind,
    id: String,
}

#[derive(Clone, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
enum Kind {
    Client,
    Project,
    Task,
    Expense,
}

#[derive(Clone, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
struct Record {
    kind: Kind,
    id: String,
    name: String,
    archived_at: Option<String>,
}

pub async fn apply_at_path(path: &Path, plan: LifecyclePlan) -> Result<(), String> {
    let options = SqliteConnectOptions::new()
        .filename(path)
        .create_if_missing(false);
    let mut connection = SqliteConnection::connect_with(&options)
        .await
        .map_err(|error| format!("Lifecycle change was not saved: {error}"))?;
    let mut transaction = connection
        .begin()
        .await
        .map_err(|error| format!("Lifecycle change was not saved: {error}"))?;

    let result = apply_in_transaction(&mut transaction, &plan).await;
    match result {
        Ok(()) => transaction
            .commit()
            .await
            .map_err(|error| format!("Lifecycle change was not saved: {error}")),
        Err(primary) => match transaction.rollback().await {
            Ok(()) => Err(primary),
            Err(rollback) => Err(lifecycle_failure_with_rollback_failure(&primary, &rollback)),
        },
    }
}

fn lifecycle_failure_with_rollback_failure(
    primary: impl std::fmt::Display,
    rollback: impl std::fmt::Display,
) -> String {
    format!("{primary}. Transaction rollback also failed: {rollback}")
}

async fn apply_in_transaction(
    transaction: &mut Transaction<'_, Sqlite>,
    plan: &LifecyclePlan,
) -> Result<(), String> {
    let (actual, impact_description) =
        expected_records(transaction, &plan.operation, &plan.target).await?;
    if actual != plan.records || impact_description != plan.impact_description {
        return Err("stale-plan: lifecycle hierarchy changed".into());
    }
    let applied_at: String = sqlx::query_scalar("SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")
        .fetch_one(&mut **transaction)
        .await
        .map_err(|error| format!("Lifecycle change was not saved: {error}"))?;
    let archived_at: Option<&str> = if plan.operation == Operation::Archive {
        Some(&applied_at)
    } else {
        None
    };
    for record in &plan.records {
        let table = match record.kind {
            Kind::Client => "clients",
            Kind::Project => "projects",
            Kind::Task => "tasks",
            Kind::Expense => "expenses",
        };
        let result = sqlx::query(&format!(
            "UPDATE {table} SET archived_at = ?, updated_at = ? WHERE id = ?"
        ))
        .bind(archived_at)
        .bind(&applied_at)
        .bind(&record.id)
        .execute(&mut **transaction)
        .await
        .map_err(|error| format!("Lifecycle change was not saved: {error}"))?;
        if result.rows_affected() != 1 {
            return Err("stale-plan: lifecycle record changed".into());
        }
    }
    Ok(())
}

async fn expected_records(
    transaction: &mut Transaction<'_, Sqlite>,
    operation: &Operation,
    target: &Target,
) -> Result<(Vec<Record>, String), String> {
    let client = match target.kind {
        Kind::Client => row(transaction, "SELECT id, name, archived_at FROM clients WHERE id = ?", &target.id, Kind::Client).await?,
        Kind::Project => row(transaction, "SELECT clients.id, clients.name, clients.archived_at FROM clients JOIN projects ON projects.client_id = clients.id WHERE projects.id = ?", &target.id, Kind::Client).await?,
        Kind::Task => row(transaction, "SELECT clients.id, clients.name, clients.archived_at FROM clients JOIN projects ON projects.client_id = clients.id JOIN tasks ON tasks.project_id = projects.id WHERE tasks.id = ?", &target.id, Kind::Client).await?,
        Kind::Expense => row(transaction, "SELECT clients.id, clients.name, clients.archived_at FROM clients JOIN expenses ON expenses.client_id = clients.id WHERE expenses.id = ?1 UNION SELECT clients.id, clients.name, clients.archived_at FROM clients JOIN projects ON projects.client_id = clients.id JOIN expenses ON expenses.project_id = projects.id WHERE expenses.id = ?1", &target.id, Kind::Client).await?,
    };
    let mut records = Vec::new();
    let impact_description = match (&target.kind, operation) {
        (Kind::Client, Operation::Archive) => {
            require_active(&client)?;
            let name = client.name.clone();
            records.push(client);
            let projects = rows(
                transaction,
                "SELECT id, name, archived_at FROM projects WHERE client_id = ? ORDER BY id",
                &target.id,
                Kind::Project,
            )
            .await?;
            let tasks = rows(transaction, "SELECT tasks.id, tasks.name, tasks.archived_at FROM tasks JOIN projects ON projects.id = tasks.project_id WHERE projects.client_id = ? ORDER BY tasks.id", &target.id, Kind::Task).await?;
            let project_count = projects.len();
            let task_count = tasks.len();
            let expenses = rows(transaction, "SELECT expenses.id, expenses.description, expenses.archived_at FROM expenses LEFT JOIN projects ON projects.id = expenses.project_id WHERE (expenses.client_id = ?1 OR projects.client_id = ?1) AND expenses.archived_at IS NULL ORDER BY expenses.id", &target.id, Kind::Expense).await?;
            let expense_count = expenses.len();
            records.extend(projects.into_iter().filter(|row| row.archived_at.is_none()));
            records.extend(tasks.into_iter().filter(|row| row.archived_at.is_none()));
            records.extend(expenses);
            if expense_count > 0 {
                format!("Archive {} and every Project, Task, and Expense beneath it ({} {}, {} {}, {} {}).", name, project_count, plural(project_count, "Project"), task_count, plural(task_count, "Task"), expense_count, plural(expense_count, "Expense"))
            } else {
                format!(
                    "Archive {} and every Project and Task beneath it ({} {}, {} {}).",
                    name,
                    project_count,
                    plural(project_count, "Project"),
                    task_count,
                    plural(task_count, "Task")
                )
            }
        }
        (Kind::Client, Operation::Restore) => {
            require_archived(&client)?;
            let name = client.name.clone();
            records.push(client);
            format!("Restore {name} only. Archived Projects and Tasks remain archived.")
        }
        (Kind::Project, Operation::Archive) => {
            let project = row(
                transaction,
                "SELECT id, name, archived_at FROM projects WHERE id = ?",
                &target.id,
                Kind::Project,
            )
            .await?;
            require_active(&project)?;
            let name = project.name.clone();
            records.push(project);
            let tasks = rows(
                transaction,
                "SELECT id, name, archived_at FROM tasks WHERE project_id = ? ORDER BY id",
                &target.id,
                Kind::Task,
            )
            .await?;
            let task_count = tasks.len();
            let expenses = rows(transaction, "SELECT id, description, archived_at FROM expenses WHERE project_id = ? AND archived_at IS NULL ORDER BY id", &target.id, Kind::Expense).await?;
            let expense_count = expenses.len();
            records.extend(tasks.into_iter().filter(|row| row.archived_at.is_none()));
            records.extend(expenses);
            if expense_count > 0 {
                format!(
                    "Archive {name} and every Task and Expense beneath it ({} {}, {} {}).",
                    task_count,
                    plural(task_count, "Task"),
                    expense_count,
                    plural(expense_count, "Expense")
                )
            } else {
                format!(
                    "Archive {name} and every Task beneath it ({} {}).",
                    task_count,
                    plural(task_count, "Task")
                )
            }
        }
        (Kind::Project, Operation::Restore) => {
            let project = row(
                transaction,
                "SELECT id, name, archived_at FROM projects WHERE id = ?",
                &target.id,
                Kind::Project,
            )
            .await?;
            require_archived(&project)?;
            if client.archived_at.is_some() {
                records.push(client);
            }
            let name = project.name.clone();
            records.push(project);
            let names = records
                .iter()
                .map(|record| record.name.as_str())
                .collect::<Vec<_>>();
            format!(
                "Restore {}{}. Tasks beneath {name} remain archived.",
                join_names(&names),
                if names.len() == 1 { " only" } else { "" }
            )
        }
        (Kind::Task, Operation::Archive) => {
            let task = row(
                transaction,
                "SELECT id, name, archived_at FROM tasks WHERE id = ?",
                &target.id,
                Kind::Task,
            )
            .await?;
            require_active(&task)?;
            let name = task.name.clone();
            records.push(task);
            format!("Archive {name}.")
        }
        (Kind::Task, Operation::Restore) => {
            let project = row(transaction, "SELECT projects.id, projects.name, projects.archived_at FROM projects JOIN tasks ON tasks.project_id = projects.id WHERE tasks.id = ?", &target.id, Kind::Project).await?;
            let task = row(
                transaction,
                "SELECT id, name, archived_at FROM tasks WHERE id = ?",
                &target.id,
                Kind::Task,
            )
            .await?;
            require_archived(&task)?;
            if client.archived_at.is_some() {
                records.push(client);
            }
            if project.archived_at.is_some() {
                records.push(project);
            }
            records.push(task);
            let names = records
                .iter()
                .map(|record| record.name.as_str())
                .collect::<Vec<_>>();
            format!(
                "Restore {}{}. Sibling records remain unchanged.",
                join_names(&names),
                if names.len() == 1 { " only" } else { "" }
            )
        }
        (Kind::Expense, operation) => {
            let expense = row(
                transaction,
                "SELECT id, description, archived_at FROM expenses WHERE id = ?",
                &target.id,
                Kind::Expense,
            )
            .await?;
            if operation == &Operation::Archive {
                require_active(&expense)?;
                let name = expense.name.clone();
                records.push(expense);
                format!("Archive {name}.")
            } else {
                require_archived(&expense)?;
                let project = optional_row(transaction, "SELECT projects.id, projects.name, projects.archived_at FROM projects JOIN expenses ON expenses.project_id = projects.id WHERE expenses.id = ?", &target.id, Kind::Project).await?;
                if client.archived_at.is_some() {
                    records.push(client);
                }
                if let Some(project) = project {
                    if project.archived_at.is_some() {
                        records.push(project);
                    }
                }
                records.push(expense);
                let names = records
                    .iter()
                    .map(|record| record.name.as_str())
                    .collect::<Vec<_>>();
                format!(
                    "Restore {}{}. Sibling records remain unchanged.",
                    join_names(&names),
                    if names.len() == 1 { " only" } else { "" }
                )
            }
        }
    };
    Ok((records, impact_description))
}

fn plural(count: usize, singular: &str) -> String {
    if count == 1 {
        singular.into()
    } else {
        format!("{singular}s")
    }
}
fn join_names(names: &[&str]) -> String {
    match names {
        [] => String::new(),
        [name] => (*name).into(),
        [first, second] => format!("{first} and {second}"),
        _ => format!(
            "{}, and {}",
            names[..names.len() - 1].join(", "),
            names[names.len() - 1]
        ),
    }
}

async fn row(
    transaction: &mut Transaction<'_, Sqlite>,
    sql: &str,
    id: &str,
    kind: Kind,
) -> Result<Record, String> {
    let row = sqlx::query_as::<_, (String, String, Option<String>)>(sql)
        .bind(id)
        .fetch_optional(&mut **transaction)
        .await
        .map_err(|error| format!("Lifecycle change was not saved: {error}"))?;
    row.map(|(id, name, archived_at)| Record {
        kind,
        id,
        name,
        archived_at,
    })
    .ok_or_else(|| "stale-plan: lifecycle hierarchy changed".into())
}

async fn optional_row(
    transaction: &mut Transaction<'_, Sqlite>,
    sql: &str,
    id: &str,
    kind: Kind,
) -> Result<Option<Record>, String> {
    sqlx::query_as::<_, (String, String, Option<String>)>(sql)
        .bind(id)
        .fetch_optional(&mut **transaction)
        .await
        .map(|row| {
            row.map(|(id, name, archived_at)| Record {
                kind,
                id,
                name,
                archived_at,
            })
        })
        .map_err(|error| format!("Lifecycle change was not saved: {error}"))
}

async fn rows(
    transaction: &mut Transaction<'_, Sqlite>,
    sql: &str,
    id: &str,
    kind: Kind,
) -> Result<Vec<Record>, String> {
    let rows = sqlx::query_as::<_, (String, String, Option<String>)>(sql)
        .bind(id)
        .fetch_all(&mut **transaction)
        .await
        .map_err(|error| format!("Lifecycle change was not saved: {error}"))?
        .into_iter()
        .map(|(id, name, archived_at)| Record {
            kind: kind.clone(),
            id,
            name,
            archived_at,
        })
        .collect();
    Ok(rows)
}

fn require_active(record: &Record) -> Result<(), String> {
    if record.archived_at.is_none() {
        Ok(())
    } else {
        Err("stale-plan: lifecycle hierarchy changed".into())
    }
}
fn require_archived(record: &Record) -> Result<(), String> {
    if record.archived_at.is_some() {
        Ok(())
    } else {
        Err("stale-plan: lifecycle hierarchy changed".into())
    }
}

#[cfg(test)]
mod tests {
    use sqlx::{sqlite::SqliteConnectOptions, Connection, SqliteConnection};

    use super::{apply_at_path, Kind, LifecyclePlan, Operation, Record, Target};

    #[test]
    fn preserves_primary_and_rollback_failures() {
        tauri::async_runtime::block_on(async {
            let directory = tempfile::tempdir().expect("temporary directory should exist");
            let path = directory.path().join("catalog.db");
            let options = SqliteConnectOptions::new()
                .filename(&path)
                .create_if_missing(true);
            let mut connection = SqliteConnection::connect_with(&options)
                .await
                .expect("temporary database should open");
            sqlx::raw_sql(
                "CREATE TABLE clients (id TEXT PRIMARY KEY, name TEXT NOT NULL, archived_at TEXT, updated_at TEXT NOT NULL);\
                 CREATE TABLE projects (id TEXT PRIMARY KEY, client_id TEXT NOT NULL, name TEXT NOT NULL, archived_at TEXT, updated_at TEXT NOT NULL);\
                 CREATE TABLE tasks (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, archived_at TEXT, updated_at TEXT NOT NULL);\
                 CREATE TABLE expenses (id TEXT PRIMARY KEY, client_id TEXT, project_id TEXT, description TEXT NOT NULL, archived_at TEXT, updated_at TEXT NOT NULL);\
                 INSERT INTO clients VALUES ('client-1', 'Acme', NULL, 'old');",
            )
            .execute(&mut connection)
            .await
            .expect("fixture should be inserted");
            sqlx::query(
                "CREATE TRIGGER fail_client_archive BEFORE UPDATE OF archived_at ON clients \
                 BEGIN SELECT RAISE(ROLLBACK, 'primary apply failure'); END",
            )
            .execute(&mut connection)
            .await
            .expect("rollback trigger should be created");
            connection
                .close()
                .await
                .expect("fixture connection should close");

            let plan = LifecyclePlan {
                operation: Operation::Archive,
                target: Target {
                    kind: Kind::Client,
                    id: "client-1".into(),
                },
                records: vec![Record {
                    kind: Kind::Client,
                    id: "client-1".into(),
                    name: "Acme".into(),
                    archived_at: None,
                }],
                impact_description:
                    "Archive Acme and every Project and Task beneath it (0 Projects, 0 Tasks)."
                        .into(),
            };

            let error = apply_at_path(&path, plan)
                .await
                .expect_err("trigger should fail the update and rollback");

            assert!(error.contains("primary apply failure"));
            assert!(error.contains("Transaction rollback also failed"));
        });
    }

    #[test]
    fn rejects_a_plan_when_an_archived_descendant_disappears() {
        tauri::async_runtime::block_on(async {
            let directory = tempfile::tempdir().expect("temporary directory should exist");
            let path = directory.path().join("catalog.db");
            let options = SqliteConnectOptions::new()
                .filename(&path)
                .create_if_missing(true);
            let mut connection = SqliteConnection::connect_with(&options)
                .await
                .expect("temporary database should open");
            sqlx::raw_sql(
                "CREATE TABLE clients (id TEXT PRIMARY KEY, name TEXT NOT NULL, archived_at TEXT, updated_at TEXT NOT NULL);\
                 CREATE TABLE projects (id TEXT PRIMARY KEY, client_id TEXT NOT NULL, name TEXT NOT NULL, archived_at TEXT, updated_at TEXT NOT NULL);\
                 CREATE TABLE tasks (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, archived_at TEXT, updated_at TEXT NOT NULL);\
                 CREATE TABLE expenses (id TEXT PRIMARY KEY, client_id TEXT, project_id TEXT, description TEXT NOT NULL, archived_at TEXT, updated_at TEXT NOT NULL);\
                 INSERT INTO clients VALUES ('client-1', 'Acme', NULL, 'old');\
                 INSERT INTO projects VALUES ('project-1', 'client-1', 'Website', NULL, 'old');\
                 INSERT INTO tasks VALUES ('task-1', 'project-1', 'Research', NULL, 'old'), ('task-2', 'project-1', 'Retired review', '2026-08-04T09:00:00.000Z', 'old');",
            )
            .execute(&mut connection)
            .await
            .expect("fixture should be inserted");
            connection
                .close()
                .await
                .expect("fixture connection should close");

            let plan = LifecyclePlan {
                operation: Operation::Archive,
                target: Target {
                    kind: Kind::Client,
                    id: "client-1".into(),
                },
                records: vec![
                    Record {
                        kind: Kind::Client,
                        id: "client-1".into(),
                        name: "Acme".into(),
                        archived_at: None,
                    },
                    Record {
                        kind: Kind::Project,
                        id: "project-1".into(),
                        name: "Website".into(),
                        archived_at: None,
                    },
                    Record {
                        kind: Kind::Task,
                        id: "task-1".into(),
                        name: "Research".into(),
                        archived_at: None,
                    },
                ],
                impact_description:
                    "Archive Acme and every Project and Task beneath it (1 Project, 2 Tasks)."
                        .into(),
            };
            let options = SqliteConnectOptions::new()
                .filename(&path)
                .create_if_missing(false);
            let mut connection = SqliteConnection::connect_with(&options)
                .await
                .expect("fixture database should reopen");
            sqlx::query("DELETE FROM tasks WHERE id = 'task-2'")
                .execute(&mut connection)
                .await
                .expect("archived descendant should disappear");
            connection
                .close()
                .await
                .expect("fixture connection should close");

            let error = apply_at_path(&path, plan)
                .await
                .expect_err("scope change should be stale");
            assert!(error.starts_with("stale-plan:"));
        });
    }
}
