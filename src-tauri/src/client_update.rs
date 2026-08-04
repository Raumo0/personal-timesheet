use std::{collections::HashSet, fmt, path::Path};

use serde::{Deserialize, Serialize};
use sqlx::{sqlite::SqliteConnectOptions, Connection, Sqlite, SqliteConnection, Transaction};

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ClientUpdatePlan {
    client_id: String,
    expected_client: ClientRecord,
    client: ClientRecord,
    overrides: Vec<OverrideUpdate>,
    updated_at: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct ClientRecord {
    id: String,
    name: String,
    normalized_name: String,
    currency_code: String,
    hourly_rate_minor: Option<i64>,
    created_at: String,
    updated_at: String,
    archived_at: Option<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
struct OverrideUpdate {
    kind: OverrideKind,
    id: String,
    expected_hourly_rate_override_minor: i64,
    expected_updated_at: String,
    hourly_rate_override_minor: i64,
}

#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(rename_all = "lowercase")]
enum OverrideKind {
    Project,
    Task,
}

#[derive(Debug)]
enum ClientUpdateError {
    Duplicate(String),
    Missing,
    Stale,
    Invalid(String),
    Persistence(String),
    Rollback { primary: String, rollback: String },
}

impl fmt::Display for ClientUpdateError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Duplicate(reason) => write!(formatter, "duplicate: {reason}"),
            Self::Missing => write!(formatter, "missing: Client does not exist"),
            Self::Stale => write!(formatter, "stale-plan: Client or descendants changed"),
            Self::Invalid(reason) => write!(formatter, "invalid-data: {reason}"),
            Self::Persistence(reason) => write!(formatter, "persistence: {reason}"),
            Self::Rollback { primary, rollback } => write!(
                formatter,
                "{primary}. Transaction rollback also failed: {rollback}"
            ),
        }
    }
}

pub async fn apply_at_path(path: &Path, plan: ClientUpdatePlan) -> Result<ClientRecord, String> {
    validate_plan(&plan).map_err(|error| error.to_string())?;
    let mut connection = SqliteConnection::connect_with(
        &SqliteConnectOptions::new()
            .filename(path)
            .create_if_missing(false),
    )
    .await
    .map_err(|error| ClientUpdateError::Persistence(error.to_string()).to_string())?;
    let mut transaction = connection
        .begin()
        .await
        .map_err(|error| ClientUpdateError::Persistence(error.to_string()).to_string())?;

    match apply_in_transaction(&mut transaction, &plan).await {
        Ok(saved) => transaction
            .commit()
            .await
            .map(|()| saved)
            .map_err(|error| ClientUpdateError::Persistence(error.to_string()).to_string()),
        Err(primary) => match transaction.rollback().await {
            Ok(()) => Err(primary.to_string()),
            Err(rollback) => Err(ClientUpdateError::Rollback {
                primary: primary.to_string(),
                rollback: rollback.to_string(),
            }
            .to_string()),
        },
    }
}

fn validate_plan(plan: &ClientUpdatePlan) -> Result<(), ClientUpdateError> {
    if plan.client_id.is_empty()
        || plan.client_id != plan.expected_client.id
        || plan.client_id != plan.client.id
        || plan.updated_at.is_empty()
        || plan.updated_at != plan.client.updated_at
        || plan.expected_client.created_at != plan.client.created_at
        || plan.expected_client.archived_at != plan.client.archived_at
    {
        return Err(ClientUpdateError::Invalid(
            "inconsistent Client plan".into(),
        ));
    }
    let mut keys = HashSet::new();
    for override_update in &plan.overrides {
        if override_update.id.is_empty()
            || override_update.expected_hourly_rate_override_minor < 0
            || override_update.hourly_rate_override_minor < 0
            || override_update.expected_updated_at.is_empty()
            || !keys.insert((
                override_update.kind.clone() as u8,
                override_update.id.clone(),
            ))
        {
            return Err(ClientUpdateError::Invalid(
                "invalid or duplicate descendant override".into(),
            ));
        }
    }
    Ok(())
}

async fn apply_in_transaction(
    transaction: &mut Transaction<'_, Sqlite>,
    plan: &ClientUpdatePlan,
) -> Result<ClientRecord, ClientUpdateError> {
    let actual_client = load_client(transaction, &plan.client_id).await?;
    if actual_client != plan.expected_client {
        return Err(ClientUpdateError::Stale);
    }
    let actual_overrides = load_overrides(transaction, &plan.client_id).await?;
    let expected_overrides = plan
        .overrides
        .iter()
        .map(|row| {
            (
                row.kind.clone(),
                row.id.clone(),
                row.expected_hourly_rate_override_minor,
                row.expected_updated_at.clone(),
            )
        })
        .collect::<Vec<_>>();
    if actual_overrides != expected_overrides {
        return Err(ClientUpdateError::Stale);
    }

    let result = sqlx::query(
        "UPDATE clients SET name = ?, normalized_name = ?, currency_code = ?, hourly_rate_minor = ?, updated_at = ? WHERE id = ?",
    )
    .bind(&plan.client.name)
    .bind(&plan.client.normalized_name)
    .bind(&plan.client.currency_code)
    .bind(plan.client.hourly_rate_minor)
    .bind(&plan.updated_at)
    .bind(&plan.client_id)
    .execute(&mut **transaction)
    .await
    .map_err(classify_sql_error)?;
    require_one_row(result.rows_affected())?;

    for row in &plan.overrides {
        let table = match row.kind {
            OverrideKind::Project => "projects",
            OverrideKind::Task => "tasks",
        };
        let result = sqlx::query(&format!(
            "UPDATE {table} SET hourly_rate_override_minor = ?, updated_at = ? WHERE id = ?"
        ))
        .bind(row.hourly_rate_override_minor)
        .bind(&plan.updated_at)
        .bind(&row.id)
        .execute(&mut **transaction)
        .await
        .map_err(classify_sql_error)?;
        require_one_row(result.rows_affected())?;
    }
    Ok(plan.client.clone())
}

fn require_one_row(rows: u64) -> Result<(), ClientUpdateError> {
    if rows == 1 {
        Ok(())
    } else {
        Err(ClientUpdateError::Stale)
    }
}

fn classify_sql_error(error: sqlx::Error) -> ClientUpdateError {
    if let sqlx::Error::Database(database) = &error {
        if database.is_unique_violation() {
            return ClientUpdateError::Duplicate(database.message().into());
        }
    }
    ClientUpdateError::Persistence(error.to_string())
}

async fn load_client(
    transaction: &mut Transaction<'_, Sqlite>,
    id: &str,
) -> Result<ClientRecord, ClientUpdateError> {
    sqlx::query_as::<_, (String, String, String, String, Option<i64>, String, String, Option<String>)>(
        "SELECT id, name, normalized_name, currency_code, hourly_rate_minor, created_at, updated_at, archived_at FROM clients WHERE id = ?",
    )
    .bind(id)
    .fetch_optional(&mut **transaction)
    .await
    .map_err(classify_sql_error)?
    .map(|row| ClientRecord {
        id: row.0, name: row.1, normalized_name: row.2, currency_code: row.3,
        hourly_rate_minor: row.4, created_at: row.5, updated_at: row.6, archived_at: row.7,
    })
    .ok_or(ClientUpdateError::Missing)
}

async fn load_overrides(
    transaction: &mut Transaction<'_, Sqlite>,
    client_id: &str,
) -> Result<Vec<(OverrideKind, String, i64, String)>, ClientUpdateError> {
    let projects: Vec<(String, i64, String)> = sqlx::query_as(
        "SELECT id, hourly_rate_override_minor, updated_at FROM projects WHERE client_id = ? AND archived_at IS NULL AND hourly_rate_override_minor IS NOT NULL ORDER BY id",
    )
    .bind(client_id)
    .fetch_all(&mut **transaction)
    .await
    .map_err(classify_sql_error)?;
    let tasks: Vec<(String, i64, String)> = sqlx::query_as(
        "SELECT tasks.id, tasks.hourly_rate_override_minor, tasks.updated_at FROM tasks JOIN projects ON projects.id = tasks.project_id WHERE projects.client_id = ? AND projects.archived_at IS NULL AND tasks.archived_at IS NULL AND tasks.hourly_rate_override_minor IS NOT NULL ORDER BY tasks.id",
    )
    .bind(client_id)
    .fetch_all(&mut **transaction)
    .await
    .map_err(classify_sql_error)?;
    Ok(projects
        .into_iter()
        .map(|(id, rate, updated_at)| (OverrideKind::Project, id, rate, updated_at))
        .chain(
            tasks
                .into_iter()
                .map(|(id, rate, updated_at)| (OverrideKind::Task, id, rate, updated_at)),
        )
        .collect())
}
