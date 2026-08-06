use std::path::Path;

use serde::{Deserialize, Serialize};
use sqlx::{sqlite::SqliteConnectOptions, Connection, SqliteConnection};

#[derive(Clone, Deserialize, Eq, PartialEq)]
#[serde(
    tag = "kind",
    rename_all = "camelCase",
    rename_all_fields = "camelCase"
)]
pub enum ExpenseTarget {
    Client { client_id: String },
    Project { project_id: String },
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExpenseCommand {
    target: ExpenseTarget,
    expense_date: String,
    description: String,
    original_currency_code: String,
    original_amount_minor: i64,
    billing_currency_code: String,
    billing_amount_minor: i64,
    applied_rate: String,
    rate_source: String,
    rate_observed_on: Option<String>,
    rate_manually_adjusted: bool,
}

#[derive(Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct ExpectedTarget {
    client_id: String,
    client_currency_code: String,
    client_updated_at: String,
    client_archived_at: Option<String>,
    project_id: Option<String>,
    project_updated_at: Option<String>,
    project_archived_at: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExpenseMutationPlan {
    operation: Operation,
    expense_id: String,
    applied_at: String,
    command: ExpenseCommand,
    expected_target: ExpectedTarget,
    expected_expense_updated_at: Option<String>,
    expected_expense_archived_at: Option<String>,
    expected_expense_target: Option<ExpenseTarget>,
    expected_original_currency_code: Option<String>,
    expected_billing_currency_code: Option<String>,
}

#[derive(Deserialize)]
#[serde(rename_all = "lowercase")]
enum Operation {
    Create,
    Update,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExpenseRecord {
    id: String,
    target: ExpenseTargetRecord,
    expense_date: String,
    description: String,
    original_currency_code: String,
    original_amount_minor: i64,
    billing_currency_code: String,
    billing_amount_minor: i64,
    applied_rate: String,
    rate_source: String,
    rate_observed_on: Option<String>,
    rate_manually_adjusted: bool,
    created_at: String,
    updated_at: String,
    archived_at: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(
    tag = "kind",
    rename_all = "camelCase",
    rename_all_fields = "camelCase"
)]
enum ExpenseTargetRecord {
    Client { client_id: String },
    Project { project_id: String },
}

type TargetState = (
    String,
    String,
    String,
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
);
type ExpenseState = (
    Option<String>,
    Option<String>,
    String,
    String,
    Option<String>,
    String,
    String,
);

pub async fn apply_at_path(
    database_path: &Path,
    plan: ExpenseMutationPlan,
) -> Result<ExpenseRecord, String> {
    validate_command(&plan.command)?;
    let options = SqliteConnectOptions::new()
        .filename(database_path)
        .create_if_missing(false);
    let mut connection = SqliteConnection::connect_with(&options)
        .await
        .map_err(persistence)?;
    sqlx::query("PRAGMA foreign_keys = ON")
        .execute(&mut connection)
        .await
        .map_err(persistence)?;
    let mut transaction = connection.begin().await.map_err(persistence)?;

    let target = target_state(&mut transaction, &plan.command.target).await?;
    let current_target = ExpectedTarget {
        client_id: target.0,
        client_currency_code: target.1,
        client_updated_at: target.2,
        client_archived_at: target.3,
        project_id: target.4,
        project_updated_at: target.5,
        project_archived_at: target.6,
    };
    if current_target != plan.expected_target {
        return Err("stale-plan: expense target changed".into());
    }
    if current_target.client_archived_at.is_some() || current_target.project_archived_at.is_some() {
        return Err("inactive-target: expense target is archived".into());
    }

    let (created_at, archived_at) = match plan.operation {
        Operation::Create => {
            let exists: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM expenses WHERE id = ?")
                .bind(&plan.expense_id)
                .fetch_one(&mut *transaction)
                .await
                .map_err(persistence)?;
            if exists != 0 {
                return Err("stale-plan: expense identity already exists".into());
            }
            if plan.command.billing_currency_code != current_target.client_currency_code {
                return Err("currency-changed: target currency changed".into());
            }
            insert(&mut transaction, &plan).await?;
            (plan.applied_at.clone(), None)
        }
        Operation::Update => {
            let state = expense_state(&mut transaction, &plan.expense_id)
                .await?
                .ok_or_else(|| "stale-plan: expense disappeared".to_owned())?;
            let current_expense_target = if let Some(client_id) = state.0.clone() {
                ExpenseTarget::Client { client_id }
            } else {
                ExpenseTarget::Project {
                    project_id: state.1.clone().expect("database XOR constraint"),
                }
            };
            if state.4.is_some() {
                return Err("archived-expense: archived expense is read-only".into());
            }
            if plan.expected_expense_updated_at.as_ref() != Some(&state.2)
                || plan.expected_expense_archived_at != state.4
                || plan.expected_expense_target.as_ref() != Some(&current_expense_target)
                || plan.expected_original_currency_code.as_ref() != Some(&state.3)
                || plan.expected_billing_currency_code.as_ref() != Some(&state.5)
            {
                return Err("stale-plan: expense changed".into());
            }
            let context_changed = current_expense_target != plan.command.target
                || state.3 != plan.command.original_currency_code;
            let expected_currency = if context_changed {
                &current_target.client_currency_code
            } else {
                &state.5
            };
            if &plan.command.billing_currency_code != expected_currency {
                return Err("currency-changed: conversion context changed".into());
            }
            update(&mut transaction, &plan).await?;
            (state.6, state.4)
        }
    };

    transaction.commit().await.map_err(persistence)?;
    Ok(record(plan, created_at, archived_at))
}

fn validate_command(command: &ExpenseCommand) -> Result<(), String> {
    if command.original_currency_code == command.billing_currency_code
        && (command.original_amount_minor != command.billing_amount_minor
            || command.applied_rate != "1")
    {
        return Err(
            "invalid-expense: matching currencies require equal amounts and applied rate 1".into(),
        );
    }
    Ok(())
}

async fn target_state(
    transaction: &mut sqlx::Transaction<'_, sqlx::Sqlite>,
    target: &ExpenseTarget,
) -> Result<TargetState, String> {
    let row = match target {
        ExpenseTarget::Client { client_id } => sqlx::query_as(
            "SELECT id, currency_code, updated_at, archived_at, NULL, NULL, NULL FROM clients WHERE id = ?",
        )
        .bind(client_id)
        .fetch_optional(&mut **transaction)
        .await,
        ExpenseTarget::Project { project_id } => sqlx::query_as(
            "SELECT clients.id, clients.currency_code, clients.updated_at, clients.archived_at, projects.id, projects.updated_at, projects.archived_at FROM projects JOIN clients ON clients.id = projects.client_id WHERE projects.id = ?",
        )
        .bind(project_id)
        .fetch_optional(&mut **transaction)
        .await,
    }
    .map_err(persistence)?;
    row.ok_or_else(|| "inactive-target: expense target disappeared".into())
}

async fn expense_state(
    transaction: &mut sqlx::Transaction<'_, sqlx::Sqlite>,
    id: &str,
) -> Result<Option<ExpenseState>, String> {
    sqlx::query_as("SELECT client_id, project_id, updated_at, original_currency_code, archived_at, billing_currency_code, created_at FROM expenses WHERE id = ?")
        .bind(id)
        .fetch_optional(&mut **transaction)
        .await
        .map_err(persistence)
}

async fn insert(
    transaction: &mut sqlx::Transaction<'_, sqlx::Sqlite>,
    plan: &ExpenseMutationPlan,
) -> Result<(), String> {
    let (client_id, project_id) = target_ids(&plan.command.target);
    sqlx::query("INSERT INTO expenses (id, client_id, project_id, expense_date, description, original_currency_code, original_amount_minor, billing_currency_code, billing_amount_minor, applied_rate, rate_source, rate_observed_on, rate_manually_adjusted, created_at, updated_at, archived_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)")
        .bind(&plan.expense_id).bind(client_id).bind(project_id)
        .bind(&plan.command.expense_date).bind(&plan.command.description)
        .bind(&plan.command.original_currency_code).bind(plan.command.original_amount_minor)
        .bind(&plan.command.billing_currency_code).bind(plan.command.billing_amount_minor)
        .bind(&plan.command.applied_rate).bind(&plan.command.rate_source)
        .bind(&plan.command.rate_observed_on).bind(plan.command.rate_manually_adjusted)
        .bind(&plan.applied_at).bind(&plan.applied_at)
        .execute(&mut **transaction).await.map_err(persistence)?;
    Ok(())
}

async fn update(
    transaction: &mut sqlx::Transaction<'_, sqlx::Sqlite>,
    plan: &ExpenseMutationPlan,
) -> Result<(), String> {
    let (client_id, project_id) = target_ids(&plan.command.target);
    let result = sqlx::query("UPDATE expenses SET client_id=?, project_id=?, expense_date=?, description=?, original_currency_code=?, original_amount_minor=?, billing_currency_code=?, billing_amount_minor=?, applied_rate=?, rate_source=?, rate_observed_on=?, rate_manually_adjusted=?, updated_at=? WHERE id=? AND updated_at=? AND archived_at IS NULL")
        .bind(client_id).bind(project_id).bind(&plan.command.expense_date)
        .bind(&plan.command.description).bind(&plan.command.original_currency_code)
        .bind(plan.command.original_amount_minor).bind(&plan.command.billing_currency_code)
        .bind(plan.command.billing_amount_minor).bind(&plan.command.applied_rate)
        .bind(&plan.command.rate_source).bind(&plan.command.rate_observed_on)
        .bind(plan.command.rate_manually_adjusted).bind(&plan.applied_at)
        .bind(&plan.expense_id).bind(&plan.expected_expense_updated_at)
        .execute(&mut **transaction).await.map_err(persistence)?;
    if result.rows_affected() != 1 {
        return Err("stale-plan: expense changed during update".into());
    }
    Ok(())
}

fn target_ids(target: &ExpenseTarget) -> (Option<&str>, Option<&str>) {
    match target {
        ExpenseTarget::Client { client_id } => (Some(client_id), None),
        ExpenseTarget::Project { project_id } => (None, Some(project_id)),
    }
}

fn record(
    plan: ExpenseMutationPlan,
    created_at: String,
    archived_at: Option<String>,
) -> ExpenseRecord {
    let target = match plan.command.target {
        ExpenseTarget::Client { client_id } => ExpenseTargetRecord::Client { client_id },
        ExpenseTarget::Project { project_id } => ExpenseTargetRecord::Project { project_id },
    };
    ExpenseRecord {
        id: plan.expense_id,
        target,
        expense_date: plan.command.expense_date,
        description: plan.command.description,
        original_currency_code: plan.command.original_currency_code,
        original_amount_minor: plan.command.original_amount_minor,
        billing_currency_code: plan.command.billing_currency_code,
        billing_amount_minor: plan.command.billing_amount_minor,
        applied_rate: plan.command.applied_rate,
        rate_source: plan.command.rate_source,
        rate_observed_on: plan.command.rate_observed_on,
        rate_manually_adjusted: plan.command.rate_manually_adjusted,
        created_at,
        updated_at: plan.applied_at,
        archived_at,
    }
}

fn persistence(error: sqlx::Error) -> String {
    format!("persistence: expense mutation failed: {error}")
}

#[cfg(test)]
mod tests {
    use sqlx::{Connection, SqliteConnection};

    use super::{apply_at_path, ExpenseMutationPlan};

    async fn fixture() -> (tempfile::TempDir, std::path::PathBuf) {
        let directory = tempfile::tempdir().expect("temporary directory should exist");
        let path = directory.path().join("expenses.db");
        let mut connection =
            SqliteConnection::connect(&format!("sqlite:{}?mode=rwc", path.display()))
                .await
                .expect("database should open");
        for migration in crate::database::client_migrations() {
            sqlx::raw_sql(migration.sql)
                .execute(&mut connection)
                .await
                .expect("migration should apply");
        }
        sqlx::raw_sql("INSERT INTO clients VALUES ('client-1','Acme','acme','EUR',NULL,'created','client-v1',NULL); INSERT INTO projects VALUES ('project-1','client-1','Site','site',NULL,'created','project-v1',NULL);")
            .execute(&mut connection).await.expect("catalog should seed");
        connection.close().await.expect("fixture should close");
        (directory, path)
    }

    fn plan(value: serde_json::Value) -> ExpenseMutationPlan {
        serde_json::from_value(value).expect("plan should deserialize")
    }

    fn create_plan() -> ExpenseMutationPlan {
        plan(serde_json::json!({
          "operation":"create", "expenseId":"expense-1", "appliedAt":"2026-08-06T10:00:00Z",
          "command":{"target":{"kind":"project","projectId":"project-1"},"expenseDate":"2026-08-06","description":"Train","originalCurrencyCode":"HUF","originalAmountMinor":9007199254740991_i64,"billingCurrencyCode":"EUR","billingAmountMinor":2251799813685248_i64,"appliedRate":"0.250000000000","rateSource":"manual","rateObservedOn":null,"rateManuallyAdjusted":false},
          "expectedTarget":{"clientId":"client-1","clientCurrencyCode":"EUR","clientUpdatedAt":"client-v1","clientArchivedAt":null,"projectId":"project-1","projectUpdatedAt":"project-v1","projectArchivedAt":null},
          "expectedExpenseUpdatedAt":null,"expectedExpenseArchivedAt":null,"expectedExpenseTarget":null,"expectedOriginalCurrencyCode":null,"expectedBillingCurrencyCode":null
        }))
    }

    #[test]
    fn expense_mutation_commits_exact_create_and_update() {
        tauri::async_runtime::block_on(async {
            let (_directory, path) = fixture().await;
            apply_at_path(&path, create_plan())
                .await
                .expect("create should commit");
            let update = plan(serde_json::json!({
              "operation":"update", "expenseId":"expense-1", "appliedAt":"2026-08-06T11:00:00Z",
              "command":{"target":{"kind":"project","projectId":"project-1"},"expenseDate":"2026-08-06","description":"Updated","originalCurrencyCode":"HUF","originalAmountMinor":9007199254740991_i64,"billingCurrencyCode":"EUR","billingAmountMinor":2251799813685249_i64,"appliedRate":"0.250000000001","rateSource":"manual","rateObservedOn":null,"rateManuallyAdjusted":false},
              "expectedTarget":{"clientId":"client-1","clientCurrencyCode":"EUR","clientUpdatedAt":"client-v1","clientArchivedAt":null,"projectId":"project-1","projectUpdatedAt":"project-v1","projectArchivedAt":null},
              "expectedExpenseUpdatedAt":"2026-08-06T10:00:00Z","expectedExpenseArchivedAt":null,"expectedExpenseTarget":{"kind":"project","projectId":"project-1"},"expectedOriginalCurrencyCode":"HUF","expectedBillingCurrencyCode":"EUR"
            }));
            apply_at_path(&path, update)
                .await
                .expect("update should commit");
            let mut db = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .unwrap();
            let row: (i64, i64, String, String) = sqlx::query_as("SELECT original_amount_minor,billing_amount_minor,applied_rate,description FROM expenses WHERE id='expense-1'").fetch_one(&mut db).await.unwrap();
            assert_eq!(
                row,
                (
                    9_007_199_254_740_991,
                    2_251_799_813_685_249,
                    "0.250000000001".into(),
                    "Updated".into()
                )
            );
        });
    }

    #[test]
    fn expense_mutation_rechecks_stale_target_and_rolls_back() {
        tauri::async_runtime::block_on(async {
            let (_directory, path) = fixture().await;
            let mut db = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .unwrap();
            sqlx::query("UPDATE clients SET currency_code='USD', updated_at='client-v2'")
                .execute(&mut db)
                .await
                .unwrap();
            db.close().await.unwrap();
            let error = apply_at_path(&path, create_plan())
                .await
                .expect_err("stale target should reject");
            assert!(error.starts_with("stale-plan:"), "{error}");
            let mut db = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .unwrap();
            let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM expenses")
                .fetch_one(&mut db)
                .await
                .unwrap();
            assert_eq!(count, 0);
        });
    }

    #[test]
    fn expense_mutation_rolls_back_constraint_failure() {
        tauri::async_runtime::block_on(async {
            let (_directory, path) = fixture().await;
            let mut invalid = create_plan();
            invalid.command.original_amount_minor = 0;
            let error = apply_at_path(&path, invalid)
                .await
                .expect_err("constraint should reject");
            assert!(error.starts_with("persistence:"), "{error}");
            let mut db = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .unwrap();
            let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM expenses")
                .fetch_one(&mut db)
                .await
                .unwrap();
            assert_eq!(count, 0);
        });
    }

    #[test]
    fn expense_mutation_rejects_same_currency_invariant_bypass_before_write() {
        tauri::async_runtime::block_on(async {
            let (_directory, path) = fixture().await;
            let mut invalid_create = create_plan();
            invalid_create.command.original_currency_code = "EUR".into();
            invalid_create.command.original_amount_minor = 100;
            invalid_create.command.billing_amount_minor = 101;
            invalid_create.command.applied_rate = "2".into();
            let error = apply_at_path(&path, invalid_create)
                .await
                .expect_err("malformed same-currency create should reject");
            assert!(error.starts_with("invalid-expense:"), "{error}");
            let mut db = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .unwrap();
            let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM expenses")
                .fetch_one(&mut db)
                .await
                .unwrap();
            assert_eq!(count, 0, "invalid create must write nothing");
            db.close().await.unwrap();

            apply_at_path(&path, create_plan())
                .await
                .expect("baseline create should commit");
            let invalid_update = plan(serde_json::json!({
              "operation":"update", "expenseId":"expense-1", "appliedAt":"2026-08-06T11:00:00Z",
              "command":{"target":{"kind":"project","projectId":"project-1"},"expenseDate":"2026-08-06","description":"Must not persist","originalCurrencyCode":"EUR","originalAmountMinor":100,"billingCurrencyCode":"EUR","billingAmountMinor":101,"appliedRate":"2","rateSource":"manual","rateObservedOn":null,"rateManuallyAdjusted":false},
              "expectedTarget":{"clientId":"client-1","clientCurrencyCode":"EUR","clientUpdatedAt":"client-v1","clientArchivedAt":null,"projectId":"project-1","projectUpdatedAt":"project-v1","projectArchivedAt":null},
              "expectedExpenseUpdatedAt":"2026-08-06T10:00:00Z","expectedExpenseArchivedAt":null,"expectedExpenseTarget":{"kind":"project","projectId":"project-1"},"expectedOriginalCurrencyCode":"HUF","expectedBillingCurrencyCode":"EUR"
            }));
            let error = apply_at_path(&path, invalid_update)
                .await
                .expect_err("malformed same-currency update should reject");
            assert!(error.starts_with("invalid-expense:"), "{error}");
            let mut db = SqliteConnection::connect(&format!("sqlite:{}", path.display()))
                .await
                .unwrap();
            let row: (String, String, i64, i64, String) = sqlx::query_as(
                "SELECT description, original_currency_code, original_amount_minor, billing_amount_minor, applied_rate FROM expenses WHERE id='expense-1'",
            )
            .fetch_one(&mut db)
            .await
            .unwrap();
            assert_eq!(
                row,
                (
                    "Train".into(),
                    "HUF".into(),
                    9_007_199_254_740_991,
                    2_251_799_813_685_248,
                    "0.250000000000".into(),
                )
            );
        });
    }
}
