use std::{
    cell::RefCell,
    collections::{BTreeMap, HashMap, HashSet},
    fmt,
    path::{Component, Path, PathBuf},
    time::Duration,
};

use serde::{
    de::{DeserializeSeed, MapAccess, SeqAccess, Visitor},
    Deserialize,
};
use sqlx::{sqlite::SqliteConnectOptions, Connection, Executor, SqliteConnection};

const SUPPORTED_SCHEMA_VERSION: u32 = 1;
const MAX_EXACT_INTEGER: i64 = 9_007_199_254_740_991;
pub const PRODUCTION_IDENTIFIER: &str = "com.personal.timesheet";
pub const DEVELOPMENT_IDENTIFIER: &str = "com.personal.timesheet.dev";
const DATABASE_FILENAME: &str = "personal-timesheet.db";
// Kept in sync with the application's current `Intl.supportedValuesOf("currency")` boundary.
const SUPPORTED_CURRENCIES: &str = "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD XCG XDR XOF XPF XSU YER ZAR ZMW ZWG ZWL";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HostPlatform {
    Macos,
    Windows,
    Linux,
}

#[derive(Clone, Copy)]
pub struct TargetPathEnvironment<'a> {
    pub home: Option<&'a Path>,
    pub app_data: Option<&'a Path>,
    pub xdg_config_home: Option<&'a Path>,
}

#[derive(Debug)]
pub enum TargetSelection {
    Production,
    Development,
    Path(PathBuf),
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ResolvedTargetKind {
    Production,
    Development,
    Explicit,
}

#[derive(Debug, Eq, PartialEq)]
pub struct ResolvedTarget {
    path: PathBuf,
    kind: ResolvedTargetKind,
}

impl ResolvedTarget {
    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn kind(&self) -> ResolvedTargetKind {
        self.kind
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TargetIssue {
    Missing,
    ActiveUse,
    IncompatibleSchema,
    NonEmpty,
    ProductionAcknowledgementRequired,
}

#[derive(Debug, Eq, PartialEq)]
pub struct TargetInspection {
    pub issue: Option<TargetIssue>,
    pub migration_version: Option<i64>,
    pub record_counts: BTreeMap<String, i64>,
}

#[derive(Debug, Eq, PartialEq)]
pub enum ApplyError {
    Ineligible(TargetIssue),
    InvalidTimestamp,
    Persistence(String),
    VerificationFailed,
}

#[derive(Debug, Eq, PartialEq)]
pub struct ApplyReceipt {
    pub record_counts: BTreeMap<String, i64>,
    pub total_minutes: i64,
    pub expense_totals_by_billing_currency: BTreeMap<String, i128>,
}

pub async fn apply_manifest(
    target: &ResolvedTarget,
    production_acknowledgement: Option<&str>,
    manifest: ValidatedManifest,
    applied_at: &str,
) -> Result<ApplyReceipt, ApplyError> {
    authorize_target_apply(target, production_acknowledgement).map_err(ApplyError::Ineligible)?;
    apply_manifest_at_path(target.path(), manifest, applied_at).await
}

async fn apply_manifest_at_path(
    path: &Path,
    manifest: ValidatedManifest,
    applied_at: &str,
) -> Result<ApplyReceipt, ApplyError> {
    if let Some(issue) = inspect_target(path).await.issue {
        return Err(ApplyError::Ineligible(issue));
    }

    let options = SqliteConnectOptions::new()
        .filename(path)
        .create_if_missing(false)
        .busy_timeout(Duration::from_millis(1));
    let mut connection = SqliteConnection::connect_with(&options)
        .await
        .map_err(apply_persistence)?;
    if !valid_application_timestamp(applied_at) {
        return Err(ApplyError::InvalidTimestamp);
    }
    connection
        .execute("PRAGMA foreign_keys = ON")
        .await
        .map_err(apply_persistence)?;
    connection
        .execute("BEGIN EXCLUSIVE")
        .await
        .map_err(|error| ApplyError::Ineligible(classify_probe_error(error)))?;

    let result = apply_under_lock(&mut connection, manifest, applied_at).await;
    match result {
        Ok(receipt) => {
            if let Err(error) = connection.execute("COMMIT").await {
                let _ = connection.execute("ROLLBACK").await;
                return Err(apply_persistence(error));
            }
            Ok(receipt)
        }
        Err(error) => match connection.execute("ROLLBACK").await {
            Ok(_) => Err(error),
            Err(rollback_error) => Err(ApplyError::Persistence(format!(
                "{error:?}; rollback failed: {rollback_error}"
            ))),
        },
    }
}

async fn apply_under_lock(
    connection: &mut SqliteConnection,
    manifest: ValidatedManifest,
    applied_at: &str,
) -> Result<ApplyReceipt, ApplyError> {
    let inspection = inspect_connection(connection)
        .await
        .map_err(ApplyError::Ineligible)?;
    if let Some(issue) = inspection.issue {
        return Err(ApplyError::Ineligible(issue));
    }

    for client in &manifest.clients {
        sqlx::query("INSERT INTO clients (id, name, normalized_name, currency_code, hourly_rate_minor, created_at, updated_at, archived_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)")
            .bind(&client.id).bind(&client.name).bind(&client.normalized_name)
            .bind(&client.currency_code).bind(client.hourly_rate_minor)
            .bind(applied_at).bind(applied_at)
            .execute(&mut *connection).await.map_err(apply_persistence)?;
    }
    for project in &manifest.projects {
        sqlx::query("INSERT INTO projects (id, client_id, name, normalized_name, hourly_rate_override_minor, created_at, updated_at, archived_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)")
            .bind(&project.id).bind(&project.client_id).bind(&project.name)
            .bind(&project.normalized_name).bind(project.hourly_rate_override_minor)
            .bind(applied_at).bind(applied_at)
            .execute(&mut *connection).await.map_err(apply_persistence)?;
    }
    for task in &manifest.tasks {
        sqlx::query("INSERT INTO tasks (id, project_id, name, normalized_name, hourly_rate_override_minor, created_at, updated_at, archived_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)")
            .bind(&task.id).bind(&task.project_id).bind(&task.name)
            .bind(&task.normalized_name).bind(task.hourly_rate_override_minor)
            .bind(applied_at).bind(applied_at)
            .execute(&mut *connection).await.map_err(apply_persistence)?;
    }
    for entry in &manifest.time_entries {
        sqlx::query("INSERT INTO time_entries (id, entry_date, duration_minutes, project_id, task_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)")
            .bind(&entry.id).bind(&entry.entry_date).bind(entry.duration_minutes)
            .bind(&entry.project_id).bind(&entry.task_id).bind(applied_at).bind(applied_at)
            .execute(&mut *connection).await.map_err(apply_persistence)?;
    }
    for expense in &manifest.expenses {
        sqlx::query("INSERT INTO expenses (id, client_id, project_id, expense_date, description, original_currency_code, original_amount_minor, billing_currency_code, billing_amount_minor, applied_rate, rate_source, rate_observed_on, rate_manually_adjusted, created_at, updated_at, archived_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', NULL, 0, ?, ?, NULL)")
            .bind(&expense.id).bind(&expense.client_id).bind(&expense.project_id)
            .bind(&expense.expense_date).bind(&expense.description)
            .bind(&expense.original_currency_code).bind(expense.original_amount_minor)
            .bind(&expense.billing_currency_code).bind(expense.billing_amount_minor)
            .bind(&expense.applied_rate).bind(applied_at).bind(applied_at)
            .execute(&mut *connection).await.map_err(apply_persistence)?;
    }

    let record_counts = current_record_counts(connection).await?;
    let expected_counts = BTreeMap::from([
        ("clients".to_owned(), manifest.summary.clients as i64),
        ("expenses".to_owned(), manifest.summary.expenses as i64),
        ("projects".to_owned(), manifest.summary.projects as i64),
        ("tasks".to_owned(), manifest.summary.tasks as i64),
        (
            "time_entries".to_owned(),
            manifest.summary.time_entries as i64,
        ),
    ]);
    let total_minutes: i64 =
        sqlx::query_scalar("SELECT COALESCE(SUM(duration_minutes), 0) FROM time_entries")
            .fetch_one(&mut *connection)
            .await
            .map_err(apply_persistence)?;
    let expense_rows = sqlx::query_as::<_, (String, i64)>(
        "SELECT billing_currency_code, billing_amount_minor FROM expenses ORDER BY billing_currency_code, id",
    )
    .fetch_all(&mut *connection)
    .await
    .map_err(apply_persistence)?;
    let mut expense_totals_by_billing_currency = BTreeMap::new();
    for (currency, amount) in expense_rows {
        let total = expense_totals_by_billing_currency
            .entry(currency)
            .or_insert(0_i128);
        *total = total
            .checked_add(i128::from(amount))
            .ok_or(ApplyError::VerificationFailed)?;
    }
    if record_counts != expected_counts
        || total_minutes != manifest.summary.total_minutes
        || expense_totals_by_billing_currency != manifest.summary.expense_totals_by_billing_currency
    {
        return Err(ApplyError::VerificationFailed);
    }
    Ok(ApplyReceipt {
        record_counts,
        total_minutes,
        expense_totals_by_billing_currency,
    })
}

async fn current_record_counts(
    connection: &mut SqliteConnection,
) -> Result<BTreeMap<String, i64>, ApplyError> {
    let mut counts = BTreeMap::new();
    for table in ["clients", "expenses", "projects", "tasks", "time_entries"] {
        let count = sqlx::query_scalar::<_, i64>(&format!("SELECT COUNT(*) FROM {table}"))
            .fetch_one(&mut *connection)
            .await
            .map_err(apply_persistence)?;
        counts.insert(table.to_owned(), count);
    }
    Ok(counts)
}

fn apply_persistence(error: sqlx::Error) -> ApplyError {
    ApplyError::Persistence(format!("timesheet import failed: {error}"))
}

fn valid_application_timestamp(value: &str) -> bool {
    let Some(without_z) = value.strip_suffix('Z') else {
        return false;
    };
    if !without_z.is_ascii() {
        return false;
    }
    let (date_time, fraction) = match without_z.split_once('.') {
        Some((date_time, fraction)) => (date_time, Some(fraction)),
        None => (without_z, None),
    };
    if date_time.len() != 19
        || &date_time[10..11] != "T"
        || &date_time[13..14] != ":"
        || &date_time[16..17] != ":"
        || !valid_date(&date_time[..10])
        || fraction.is_some_and(|digits| {
            digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit())
        })
    {
        return false;
    }
    let hour = date_time[11..13].parse::<u32>().unwrap_or(24);
    let minute = date_time[14..16].parse::<u32>().unwrap_or(60);
    let second = date_time[17..19].parse::<u32>().unwrap_or(60);
    hour < 24 && minute < 60 && second < 60
}

pub fn resolve_target(
    selection: TargetSelection,
    platform: HostPlatform,
    environment: TargetPathEnvironment<'_>,
) -> Result<ResolvedTarget, String> {
    let production_path = environment_database_path(PRODUCTION_IDENTIFIER, platform, environment)?;
    match selection {
        TargetSelection::Production => Ok(ResolvedTarget {
            path: production_path,
            kind: ResolvedTargetKind::Production,
        }),
        TargetSelection::Development => Ok(ResolvedTarget {
            path: environment_database_path(DEVELOPMENT_IDENTIFIER, platform, environment)?,
            kind: ResolvedTargetKind::Development,
        }),
        TargetSelection::Path(path) => {
            let path = normalize_path(&path);
            let kind = if paths_equivalent(&path, &production_path) {
                ResolvedTargetKind::Production
            } else {
                ResolvedTargetKind::Explicit
            };
            Ok(ResolvedTarget { path, kind })
        }
    }
}

pub fn authorize_target_apply(
    target: &ResolvedTarget,
    acknowledgement: Option<&str>,
) -> Result<(), TargetIssue> {
    if target.kind == ResolvedTargetKind::Production
        && acknowledgement != Some(PRODUCTION_IDENTIFIER)
    {
        Err(TargetIssue::ProductionAcknowledgementRequired)
    } else {
        Ok(())
    }
}

fn environment_database_path(
    identifier: &str,
    platform: HostPlatform,
    environment: TargetPathEnvironment<'_>,
) -> Result<PathBuf, String> {
    let root = match platform {
        HostPlatform::Macos => environment
            .home
            .map(|home| home.join("Library/Application Support"))
            .ok_or_else(|| "home directory is unavailable".to_owned())?,
        HostPlatform::Windows => environment
            .app_data
            .map(Path::to_path_buf)
            .ok_or_else(|| "Windows application-data directory is unavailable".to_owned())?,
        HostPlatform::Linux => environment
            .xdg_config_home
            .map(Path::to_path_buf)
            .or_else(|| environment.home.map(|home| home.join(".config")))
            .ok_or_else(|| "Linux configuration directory is unavailable".to_owned())?,
    };
    Ok(normalize_path(
        &root.join(identifier).join(DATABASE_FILENAME),
    ))
}

fn paths_equivalent(left: &Path, right: &Path) -> bool {
    match (left.canonicalize(), right.canonicalize()) {
        (Ok(canonical_left), Ok(canonical_right)) => {
            canonical_left == canonical_right || same_existing_file(left, right)
        }
        _ => normalize_path(left) == normalize_path(right),
    }
}

#[cfg(unix)]
fn same_existing_file(left: &Path, right: &Path) -> bool {
    use std::os::unix::fs::MetadataExt;

    match (left.metadata(), right.metadata()) {
        (Ok(left), Ok(right)) => left.dev() == right.dev() && left.ino() == right.ino(),
        _ => false,
    }
}

#[cfg(windows)]
fn same_existing_file(left: &Path, right: &Path) -> bool {
    use std::os::windows::fs::MetadataExt;

    match (left.metadata(), right.metadata()) {
        (Ok(left), Ok(right)) => {
            left.volume_serial_number().is_some()
                && left.volume_serial_number() == right.volume_serial_number()
                && left.file_index().is_some()
                && left.file_index() == right.file_index()
        }
        _ => false,
    }
}

#[cfg(not(any(unix, windows)))]
fn same_existing_file(_left: &Path, _right: &Path) -> bool {
    false
}

fn normalize_path(path: &Path) -> PathBuf {
    if let Ok(canonical) = path.canonicalize() {
        return canonical;
    }
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => match normalized.components().next_back() {
                Some(Component::Normal(_)) => {
                    normalized.pop();
                }
                Some(Component::ParentDir) | None => normalized.push(".."),
                Some(Component::RootDir | Component::Prefix(_)) => {}
                Some(Component::CurDir) => unreachable!("current directories are not stored"),
            },
            other => normalized.push(other.as_os_str()),
        }
    }
    normalized
}

pub async fn inspect_target(path: &Path) -> TargetInspection {
    if !path.is_file() {
        return target_issue(TargetIssue::Missing);
    }
    if ["-wal", "-shm", "-journal"]
        .iter()
        .any(|suffix| sqlite_sidecar(path, suffix).exists())
    {
        return target_issue(TargetIssue::ActiveUse);
    }
    if let Err(issue) = exclusive_lock_probe(path).await {
        return target_issue(issue);
    }
    inspect_compatible_empty_schema(path)
        .await
        .unwrap_or_else(target_issue)
}

async fn exclusive_lock_probe(path: &Path) -> Result<(), TargetIssue> {
    let options = SqliteConnectOptions::new()
        .filename(path)
        .create_if_missing(false)
        .busy_timeout(Duration::from_millis(1));
    let mut connection = SqliteConnection::connect_with(&options)
        .await
        .map_err(classify_probe_error)?;
    connection
        .execute("BEGIN EXCLUSIVE")
        .await
        .map_err(classify_probe_error)?;
    connection
        .execute("ROLLBACK")
        .await
        .map_err(|_| TargetIssue::IncompatibleSchema)?;
    connection
        .close()
        .await
        .map_err(|_| TargetIssue::IncompatibleSchema)
}

fn classify_probe_error(error: sqlx::Error) -> TargetIssue {
    let locked = match &error {
        sqlx::Error::Database(database) => {
            matches!(database.code().as_deref(), Some("5" | "6"))
                || database.message().to_ascii_lowercase().contains("locked")
                || database.message().to_ascii_lowercase().contains("busy")
        }
        _ => false,
    };
    if locked {
        TargetIssue::ActiveUse
    } else {
        TargetIssue::IncompatibleSchema
    }
}

async fn inspect_compatible_empty_schema(path: &Path) -> Result<TargetInspection, TargetIssue> {
    let options = SqliteConnectOptions::new()
        .filename(path)
        .read_only(true)
        .create_if_missing(false);
    let mut connection = SqliteConnection::connect_with(&options)
        .await
        .map_err(|_| TargetIssue::IncompatibleSchema)?;

    let result = inspect_connection(&mut connection).await;
    let close_result = connection.close().await;
    if close_result.is_err() {
        return Err(TargetIssue::IncompatibleSchema);
    }
    result
}

async fn inspect_connection(
    connection: &mut SqliteConnection,
) -> Result<TargetInspection, TargetIssue> {
    let integrity = sqlx::query_scalar::<_, String>("PRAGMA quick_check")
        .fetch_all(&mut *connection)
        .await
        .map_err(|_| TargetIssue::IncompatibleSchema)?;
    if integrity.as_slice() != ["ok"] {
        return Err(TargetIssue::IncompatibleSchema);
    }
    sqlx::query("SELECT version, description, installed_on, success, checksum, execution_time FROM _sqlx_migrations LIMIT 0")
        .fetch_optional(&mut *connection)
        .await
        .map_err(|_| TargetIssue::IncompatibleSchema)?;
    let migration_rows = sqlx::query_as::<_, (i64, String, bool, Vec<u8>)>(
        "SELECT version, description, success, checksum FROM _sqlx_migrations ORDER BY version",
    )
    .fetch_all(&mut *connection)
    .await
    .map_err(|_| TargetIssue::IncompatibleSchema)?;
    let expected_migrations = crate::database::client_migrations()
        .into_iter()
        .map(|migration| {
            let checksum = sqlx::migrate::Migration::new(
                migration.version,
                migration.description.into(),
                sqlx::migrate::MigrationType::ReversibleUp,
                migration.sql.into(),
                false,
            )
            .checksum
            .into_owned();
            (
                migration.version,
                migration.description.to_owned(),
                checksum,
            )
        })
        .collect::<Vec<_>>();
    if migration_rows.len() != expected_migrations.len()
        || migration_rows.iter().zip(&expected_migrations).any(
            |(
                (version, description, success, checksum),
                (expected_version, expected_description, expected_checksum),
            )| {
                !success
                    || version != expected_version
                    || description != expected_description
                    || checksum != expected_checksum
            },
        )
    {
        return Err(TargetIssue::IncompatibleSchema);
    }

    let required_queries = [
        "SELECT id, name, normalized_name, currency_code, hourly_rate_minor, created_at, updated_at, archived_at FROM clients LIMIT 0",
        "SELECT id, client_id, name, normalized_name, hourly_rate_override_minor, created_at, updated_at, archived_at FROM projects LIMIT 0",
        "SELECT id, project_id, name, normalized_name, hourly_rate_override_minor, created_at, updated_at, archived_at FROM tasks LIMIT 0",
        "SELECT id, entry_date, duration_minutes, project_id, task_id, created_at, updated_at FROM time_entries LIMIT 0",
        "SELECT id, client_id, project_id, expense_date, description, original_currency_code, original_amount_minor, billing_currency_code, billing_amount_minor, applied_rate, rate_source, rate_observed_on, rate_manually_adjusted, created_at, updated_at, archived_at FROM expenses LIMIT 0",
    ];
    for query in required_queries {
        sqlx::query(query)
            .fetch_optional(&mut *connection)
            .await
            .map_err(|_| TargetIssue::IncompatibleSchema)?;
    }
    if schema_signature(connection).await? != trusted_schema_signature().await? {
        return Err(TargetIssue::IncompatibleSchema);
    }

    let mut record_counts = BTreeMap::new();
    for table in ["clients", "projects", "tasks", "time_entries", "expenses"] {
        let count = sqlx::query_scalar::<_, i64>(&format!("SELECT COUNT(*) FROM {table}"))
            .fetch_one(&mut *connection)
            .await
            .map_err(|_| TargetIssue::IncompatibleSchema)?;
        record_counts.insert(table.to_owned(), count);
    }
    let migration_version = expected_migrations.last().map(|migration| migration.0);
    if record_counts.values().any(|count| *count != 0) {
        return Ok(TargetInspection {
            issue: Some(TargetIssue::NonEmpty),
            migration_version,
            record_counts,
        });
    }
    Ok(TargetInspection {
        issue: None,
        migration_version,
        record_counts,
    })
}

type SchemaObject = (String, String, String, String);

async fn schema_signature(
    connection: &mut SqliteConnection,
) -> Result<Vec<SchemaObject>, TargetIssue> {
    let rows = sqlx::query_as::<_, (String, String, String, Option<String>)>(
        "SELECT type, name, tbl_name, sql FROM sqlite_master \
         WHERE name NOT LIKE 'sqlite_%' AND name <> '_sqlx_migrations' \
         ORDER BY type, name",
    )
    .fetch_all(connection)
    .await
    .map_err(|_| TargetIssue::IncompatibleSchema)?;
    Ok(rows
        .into_iter()
        .map(|(kind, name, table, sql)| {
            (
                kind,
                name,
                table,
                normalize_schema_sql(sql.as_deref().unwrap_or_default()),
            )
        })
        .collect())
}

async fn trusted_schema_signature() -> Result<Vec<SchemaObject>, TargetIssue> {
    let mut connection = SqliteConnection::connect("sqlite::memory:")
        .await
        .map_err(|_| TargetIssue::IncompatibleSchema)?;
    for migration in crate::database::client_migrations() {
        sqlx::raw_sql(migration.sql)
            .execute(&mut connection)
            .await
            .map_err(|_| TargetIssue::IncompatibleSchema)?;
    }
    let signature = schema_signature(&mut connection).await;
    connection
        .close()
        .await
        .map_err(|_| TargetIssue::IncompatibleSchema)?;
    signature
}

fn normalize_schema_sql(sql: &str) -> String {
    sql.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn target_issue(issue: TargetIssue) -> TargetInspection {
    TargetInspection {
        issue: Some(issue),
        migration_version: None,
        record_counts: BTreeMap::new(),
    }
}

fn sqlite_sidecar(database: &Path, suffix: &str) -> PathBuf {
    let mut path = database.as_os_str().to_os_string();
    path.push(suffix);
    PathBuf::from(path)
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ImportManifest {
    pub schema_version: u32,
    pub clients: Vec<ImportClient>,
    pub projects: Vec<ImportProject>,
    pub tasks: Vec<ImportTask>,
    pub time_entries: Vec<ImportTimeEntry>,
    pub expenses: Vec<ImportExpense>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ImportClient {
    pub id: String,
    pub name: String,
    #[serde(skip)]
    pub normalized_name: String,
    pub currency_code: String,
    pub hourly_rate_minor: Option<i64>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ImportProject {
    pub id: String,
    pub client_id: String,
    pub name: String,
    #[serde(skip)]
    pub normalized_name: String,
    pub hourly_rate_override_minor: Option<i64>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ImportTask {
    pub id: String,
    pub project_id: String,
    pub name: String,
    #[serde(skip)]
    pub normalized_name: String,
    pub hourly_rate_override_minor: Option<i64>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ImportTimeEntry {
    pub id: String,
    pub entry_date: String,
    pub duration_minutes: i64,
    pub project_id: Option<String>,
    pub task_id: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ImportExpense {
    pub id: String,
    pub client_id: Option<String>,
    pub project_id: Option<String>,
    pub expense_date: String,
    pub description: String,
    pub original_currency_code: String,
    pub original_amount_minor: i64,
    pub billing_currency_code: String,
    pub billing_amount_minor: i64,
    pub applied_rate: String,
}

#[derive(Debug, Eq, PartialEq)]
pub struct ManifestValidationError {
    pub path: String,
    pub code: String,
}

#[derive(Debug, Eq, PartialEq)]
pub struct ManifestSummary {
    pub clients: usize,
    pub projects: usize,
    pub tasks: usize,
    pub time_entries: usize,
    pub expenses: usize,
    pub total_minutes: i64,
    pub expense_totals_by_billing_currency: BTreeMap<String, i128>,
}

#[derive(Debug)]
pub struct ValidatedManifest {
    pub clients: Vec<ImportClient>,
    pub projects: Vec<ImportProject>,
    pub tasks: Vec<ImportTask>,
    pub time_entries: Vec<ImportTimeEntry>,
    pub expenses: Vec<ImportExpense>,
    pub summary: ManifestSummary,
}

pub fn parse_and_validate_manifest(
    input: &str,
) -> Result<ValidatedManifest, Vec<ManifestValidationError>> {
    let duplicate_errors = RefCell::new(Vec::new());
    let mut deserializer = serde_json::Deserializer::from_str(input);
    let document = DuplicateAwareSeed {
        path: "$".to_owned(),
        errors: &duplicate_errors,
    }
    .deserialize(&mut deserializer)
    .and_then(|document| {
        deserializer.end()?;
        Ok(document)
    })
    .map_err(|_| invalid_json_error())?;
    let mut errors = duplicate_errors.into_inner();
    errors.extend(structural_errors(&document));
    if !errors.is_empty() {
        return Err(errors);
    }
    let manifest = serde_json::from_value(document).map_err(|_| {
        vec![ManifestValidationError {
            path: "$".to_owned(),
            code: "invalid-manifest".to_owned(),
        }]
    })?;
    validate_manifest(manifest)
}

fn invalid_json_error() -> Vec<ManifestValidationError> {
    vec![ManifestValidationError {
        path: "$".to_owned(),
        code: "invalid-json".to_owned(),
    }]
}

struct DuplicateAwareSeed<'a> {
    path: String,
    errors: &'a RefCell<Vec<ManifestValidationError>>,
}

impl<'de> DeserializeSeed<'de> for DuplicateAwareSeed<'_> {
    type Value = serde_json::Value;

    fn deserialize<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        deserializer.deserialize_any(DuplicateAwareVisitor {
            path: self.path,
            errors: self.errors,
        })
    }
}

struct DuplicateAwareVisitor<'a> {
    path: String,
    errors: &'a RefCell<Vec<ManifestValidationError>>,
}

impl<'de> Visitor<'de> for DuplicateAwareVisitor<'_> {
    type Value = serde_json::Value;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value")
    }

    fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
        Ok(value.into())
    }

    fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
        Ok(value.into())
    }

    fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
        Ok(value.into())
    }

    fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
    where
        E: serde::de::Error,
    {
        serde_json::Number::from_f64(value)
            .map(serde_json::Value::Number)
            .ok_or_else(|| E::custom("JSON number must be finite"))
    }

    fn visit_str<E>(self, value: &str) -> Result<Self::Value, E> {
        Ok(value.into())
    }

    fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
        Ok(value.into())
    }

    fn visit_none<E>(self) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Null)
    }

    fn visit_unit<E>(self) -> Result<Self::Value, E> {
        Ok(serde_json::Value::Null)
    }

    fn visit_some<D>(self, deserializer: D) -> Result<Self::Value, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        DuplicateAwareSeed {
            path: self.path,
            errors: self.errors,
        }
        .deserialize(deserializer)
    }

    fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
    where
        A: SeqAccess<'de>,
    {
        let mut values = Vec::new();
        let mut index = 0;
        while let Some(value) = sequence.next_element_seed(DuplicateAwareSeed {
            path: format!("{}[{index}]", self.path),
            errors: self.errors,
        })? {
            values.push(value);
            index += 1;
        }
        Ok(serde_json::Value::Array(values))
    }

    fn visit_map<A>(self, mut map: A) -> Result<Self::Value, A::Error>
    where
        A: MapAccess<'de>,
    {
        let mut object = serde_json::Map::new();
        let mut keys = HashSet::new();
        while let Some(key) = map.next_key::<String>()? {
            let path = if self.path == "$" {
                key.clone()
            } else {
                format!("{}.{}", self.path, key)
            };
            if !keys.insert(key.clone()) {
                push_error(&mut self.errors.borrow_mut(), &path, "duplicate-field");
            }
            let value = map.next_value_seed(DuplicateAwareSeed {
                path,
                errors: self.errors,
            })?;
            object.insert(key, value);
        }
        Ok(serde_json::Value::Object(object))
    }
}

#[derive(Clone, Copy)]
enum JsonFieldType {
    String,
    Integer,
    Version,
    NullableString,
    NullableInteger,
}

const CLIENT_FIELDS: &[(&str, JsonFieldType)] = &[
    ("id", JsonFieldType::String),
    ("name", JsonFieldType::String),
    ("currencyCode", JsonFieldType::String),
    ("hourlyRateMinor", JsonFieldType::NullableInteger),
];
const PROJECT_FIELDS: &[(&str, JsonFieldType)] = &[
    ("id", JsonFieldType::String),
    ("clientId", JsonFieldType::String),
    ("name", JsonFieldType::String),
    ("hourlyRateOverrideMinor", JsonFieldType::NullableInteger),
];
const TASK_FIELDS: &[(&str, JsonFieldType)] = &[
    ("id", JsonFieldType::String),
    ("projectId", JsonFieldType::String),
    ("name", JsonFieldType::String),
    ("hourlyRateOverrideMinor", JsonFieldType::NullableInteger),
];
const TIME_ENTRY_FIELDS: &[(&str, JsonFieldType)] = &[
    ("id", JsonFieldType::String),
    ("entryDate", JsonFieldType::String),
    ("durationMinutes", JsonFieldType::Integer),
    ("projectId", JsonFieldType::NullableString),
    ("taskId", JsonFieldType::NullableString),
];
const EXPENSE_FIELDS: &[(&str, JsonFieldType)] = &[
    ("id", JsonFieldType::String),
    ("clientId", JsonFieldType::NullableString),
    ("projectId", JsonFieldType::NullableString),
    ("expenseDate", JsonFieldType::String),
    ("description", JsonFieldType::String),
    ("originalCurrencyCode", JsonFieldType::String),
    ("originalAmountMinor", JsonFieldType::Integer),
    ("billingCurrencyCode", JsonFieldType::String),
    ("billingAmountMinor", JsonFieldType::Integer),
    ("appliedRate", JsonFieldType::String),
];

fn structural_errors(document: &serde_json::Value) -> Vec<ManifestValidationError> {
    let mut errors = Vec::new();
    let Some(object) = document.as_object() else {
        push_error(&mut errors, "$", "invalid-type");
        return errors;
    };

    validate_json_field(
        object.get("schemaVersion"),
        "schemaVersion",
        JsonFieldType::Version,
        &mut errors,
    );
    validate_json_collection(object, "clients", CLIENT_FIELDS, &mut errors);
    validate_json_collection(object, "projects", PROJECT_FIELDS, &mut errors);
    validate_json_collection(object, "tasks", TASK_FIELDS, &mut errors);
    validate_json_collection(object, "timeEntries", TIME_ENTRY_FIELDS, &mut errors);
    validate_json_collection(object, "expenses", EXPENSE_FIELDS, &mut errors);
    collect_unknown_fields(
        object,
        "$",
        &[
            "schemaVersion",
            "clients",
            "projects",
            "tasks",
            "timeEntries",
            "expenses",
        ],
        &mut errors,
    );
    errors
}

fn validate_json_collection(
    object: &serde_json::Map<String, serde_json::Value>,
    name: &str,
    fields: &[(&str, JsonFieldType)],
    errors: &mut Vec<ManifestValidationError>,
) {
    let Some(value) = object.get(name) else {
        push_error(errors, name, "missing-field");
        return;
    };
    let Some(items) = value.as_array() else {
        push_error(errors, name, "invalid-type");
        return;
    };
    for (index, item) in items.iter().enumerate() {
        let item_path = format!("{name}[{index}]");
        let Some(item_object) = item.as_object() else {
            push_error(errors, item_path, "invalid-type");
            continue;
        };
        for (field, field_type) in fields {
            validate_json_field(
                item_object.get(*field),
                &format!("{item_path}.{field}"),
                *field_type,
                errors,
            );
        }
        let expected = fields.iter().map(|(field, _)| *field).collect::<Vec<_>>();
        collect_unknown_fields(item_object, &item_path, &expected, errors);
    }
}

fn validate_json_field(
    value: Option<&serde_json::Value>,
    path: &str,
    expected: JsonFieldType,
    errors: &mut Vec<ManifestValidationError>,
) {
    let Some(value) = value else {
        push_error(errors, path, "missing-field");
        return;
    };
    let valid = match expected {
        JsonFieldType::String => value.is_string(),
        JsonFieldType::Integer => value.as_i64().is_some(),
        JsonFieldType::Version => value
            .as_u64()
            .is_some_and(|version| u32::try_from(version).is_ok()),
        JsonFieldType::NullableString => value.is_null() || value.is_string(),
        JsonFieldType::NullableInteger => value.is_null() || value.as_i64().is_some(),
    };
    if !valid {
        push_error(errors, path, "invalid-type");
    }
}

fn collect_unknown_fields(
    object: &serde_json::Map<String, serde_json::Value>,
    path: &str,
    expected: &[&str],
    errors: &mut Vec<ManifestValidationError>,
) {
    let mut unknown = object
        .keys()
        .filter(|field| !expected.contains(&field.as_str()))
        .collect::<Vec<_>>();
    unknown.sort();
    for field in unknown {
        let field_path = if path == "$" {
            field.clone()
        } else {
            format!("{path}.{field}")
        };
        push_error(errors, field_path, "unknown-field");
    }
}

pub fn validate_manifest(
    mut manifest: ImportManifest,
) -> Result<ValidatedManifest, Vec<ManifestValidationError>> {
    let mut errors = Vec::new();
    if manifest.schema_version != SUPPORTED_SCHEMA_VERSION {
        push_error(&mut errors, "schemaVersion", "unsupported-version");
    }

    let client_ids = validate_clients(&mut manifest.clients, &mut errors);
    let (project_ids, project_clients) =
        validate_projects(&mut manifest.projects, &client_ids, &mut errors);
    let task_ids = validate_tasks(&mut manifest.tasks, &project_ids, &mut errors);
    validate_time_entries(&manifest.time_entries, &project_ids, &task_ids, &mut errors);
    validate_expenses(
        &mut manifest.expenses,
        &manifest.clients,
        &client_ids,
        &project_ids,
        &project_clients,
        &mut errors,
    );

    if !errors.is_empty() {
        return Err(errors);
    }

    let total_minutes = manifest
        .time_entries
        .iter()
        .map(|entry| entry.duration_minutes)
        .sum();
    let mut expense_totals_by_billing_currency = BTreeMap::new();
    for expense in &manifest.expenses {
        *expense_totals_by_billing_currency
            .entry(expense.billing_currency_code.clone())
            .or_insert(0) += i128::from(expense.billing_amount_minor);
    }
    let summary = ManifestSummary {
        clients: manifest.clients.len(),
        projects: manifest.projects.len(),
        tasks: manifest.tasks.len(),
        time_entries: manifest.time_entries.len(),
        expenses: manifest.expenses.len(),
        total_minutes,
        expense_totals_by_billing_currency,
    };

    Ok(ValidatedManifest {
        clients: manifest.clients,
        projects: manifest.projects,
        tasks: manifest.tasks,
        time_entries: manifest.time_entries,
        expenses: manifest.expenses,
        summary,
    })
}

fn validate_clients(
    clients: &mut [ImportClient],
    errors: &mut Vec<ManifestValidationError>,
) -> HashSet<String> {
    let mut ids = HashSet::new();
    let mut names = HashSet::new();
    for (index, client) in clients.iter_mut().enumerate() {
        normalize_name(&mut client.name, &mut client.normalized_name);
        validate_id(
            &client.id,
            &format!("clients[{index}].id"),
            &mut ids,
            errors,
        );
        if client.name.is_empty() {
            push_error(errors, format!("clients[{index}].name"), "empty-name");
        }
        if !valid_currency(&client.currency_code) {
            push_error(
                errors,
                format!("clients[{index}].currencyCode"),
                "invalid-currency",
            );
        }
        if !valid_optional_catalog_money(client.hourly_rate_minor) {
            push_error(
                errors,
                format!("clients[{index}].hourlyRateMinor"),
                "invalid-money",
            );
        }
        if !client.normalized_name.is_empty() && !names.insert(client.normalized_name.clone()) {
            push_error(errors, format!("clients[{index}].name"), "duplicate-name");
        }
    }
    ids
}

fn validate_projects(
    projects: &mut [ImportProject],
    client_ids: &HashSet<String>,
    errors: &mut Vec<ManifestValidationError>,
) -> (HashSet<String>, HashMap<String, String>) {
    let mut ids = HashSet::new();
    let mut names = HashSet::new();
    let mut project_clients = HashMap::new();
    for (index, project) in projects.iter_mut().enumerate() {
        normalize_name(&mut project.name, &mut project.normalized_name);
        validate_id(
            &project.id,
            &format!("projects[{index}].id"),
            &mut ids,
            errors,
        );
        if !client_ids.contains(&project.client_id) {
            push_error(
                errors,
                format!("projects[{index}].clientId"),
                "missing-client",
            );
        }
        if project.name.is_empty() {
            push_error(errors, format!("projects[{index}].name"), "empty-name");
        }
        if !valid_optional_catalog_money(project.hourly_rate_override_minor) {
            push_error(
                errors,
                format!("projects[{index}].hourlyRateOverrideMinor"),
                "invalid-money",
            );
        }
        let scoped_name = (project.client_id.clone(), project.normalized_name.clone());
        if !project.normalized_name.is_empty() && !names.insert(scoped_name) {
            push_error(errors, format!("projects[{index}].name"), "duplicate-name");
        }
        project_clients
            .entry(project.id.clone())
            .or_insert_with(|| project.client_id.clone());
    }
    (ids, project_clients)
}

fn validate_tasks(
    tasks: &mut [ImportTask],
    project_ids: &HashSet<String>,
    errors: &mut Vec<ManifestValidationError>,
) -> HashSet<String> {
    let mut ids = HashSet::new();
    let mut names = HashSet::new();
    for (index, task) in tasks.iter_mut().enumerate() {
        normalize_name(&mut task.name, &mut task.normalized_name);
        validate_id(&task.id, &format!("tasks[{index}].id"), &mut ids, errors);
        if !project_ids.contains(&task.project_id) {
            push_error(
                errors,
                format!("tasks[{index}].projectId"),
                "missing-project",
            );
        }
        if task.name.is_empty() {
            push_error(errors, format!("tasks[{index}].name"), "empty-name");
        }
        if !valid_optional_catalog_money(task.hourly_rate_override_minor) {
            push_error(
                errors,
                format!("tasks[{index}].hourlyRateOverrideMinor"),
                "invalid-money",
            );
        }
        let scoped_name = (task.project_id.clone(), task.normalized_name.clone());
        if !task.normalized_name.is_empty() && !names.insert(scoped_name) {
            push_error(errors, format!("tasks[{index}].name"), "duplicate-name");
        }
    }
    ids
}

fn validate_time_entries(
    entries: &[ImportTimeEntry],
    project_ids: &HashSet<String>,
    task_ids: &HashSet<String>,
    errors: &mut Vec<ManifestValidationError>,
) {
    let mut ids = HashSet::new();
    let mut dated_targets = HashSet::new();
    for (index, entry) in entries.iter().enumerate() {
        validate_id(
            &entry.id,
            &format!("timeEntries[{index}].id"),
            &mut ids,
            errors,
        );
        if !valid_date(&entry.entry_date) {
            push_error(
                errors,
                format!("timeEntries[{index}].entryDate"),
                "invalid-date",
            );
        }
        if !(1..=1440).contains(&entry.duration_minutes) {
            push_error(
                errors,
                format!("timeEntries[{index}].durationMinutes"),
                "invalid-duration",
            );
        }
        if entry.project_id.is_some() == entry.task_id.is_some() {
            push_error(errors, format!("timeEntries[{index}]"), "invalid-target");
        }
        if let Some(project_id) = &entry.project_id {
            if !project_ids.contains(project_id) {
                push_error(
                    errors,
                    format!("timeEntries[{index}].projectId"),
                    "missing-project",
                );
            }
            if !dated_targets.insert(("project", project_id, entry.entry_date.as_str())) {
                push_error(errors, format!("timeEntries[{index}]"), "duplicate-entry");
            }
        }
        if let Some(task_id) = &entry.task_id {
            if !task_ids.contains(task_id) {
                push_error(
                    errors,
                    format!("timeEntries[{index}].taskId"),
                    "missing-task",
                );
            }
            if !dated_targets.insert(("task", task_id, entry.entry_date.as_str())) {
                push_error(errors, format!("timeEntries[{index}]"), "duplicate-entry");
            }
        }
    }
}

fn validate_expenses(
    expenses: &mut [ImportExpense],
    clients: &[ImportClient],
    client_ids: &HashSet<String>,
    project_ids: &HashSet<String>,
    project_clients: &HashMap<String, String>,
    errors: &mut Vec<ManifestValidationError>,
) {
    let mut ids = HashSet::new();
    let client_currencies = clients
        .iter()
        .map(|client| (client.id.as_str(), client.currency_code.as_str()))
        .collect::<HashMap<_, _>>();
    for (index, expense) in expenses.iter_mut().enumerate() {
        expense.description = expense.description.trim().to_owned();
        validate_id(
            &expense.id,
            &format!("expenses[{index}].id"),
            &mut ids,
            errors,
        );
        if !valid_date(&expense.expense_date) {
            push_error(
                errors,
                format!("expenses[{index}].expenseDate"),
                "invalid-date",
            );
        }
        if expense.description.is_empty() {
            push_error(
                errors,
                format!("expenses[{index}].description"),
                "empty-description",
            );
        }
        validate_currency_and_money(
            &expense.original_currency_code,
            expense.original_amount_minor,
            &format!("expenses[{index}].originalCurrencyCode"),
            &format!("expenses[{index}].originalAmountMinor"),
            errors,
        );
        validate_currency_and_money(
            &expense.billing_currency_code,
            expense.billing_amount_minor,
            &format!("expenses[{index}].billingCurrencyCode"),
            &format!("expenses[{index}].billingAmountMinor"),
            errors,
        );
        if !valid_rate(&expense.applied_rate) {
            push_error(
                errors,
                format!("expenses[{index}].appliedRate"),
                "invalid-rate",
            );
        }
        if expense.client_id.is_some() == expense.project_id.is_some() {
            push_error(errors, format!("expenses[{index}]"), "invalid-target");
        }

        let target_client = if let Some(client_id) = &expense.client_id {
            if !client_ids.contains(client_id) {
                push_error(
                    errors,
                    format!("expenses[{index}].clientId"),
                    "missing-client",
                );
                None
            } else {
                Some(client_id.as_str())
            }
        } else if let Some(project_id) = &expense.project_id {
            if !project_ids.contains(project_id) {
                push_error(
                    errors,
                    format!("expenses[{index}].projectId"),
                    "missing-project",
                );
                None
            } else {
                project_clients.get(project_id).map(String::as_str)
            }
        } else {
            None
        };
        if let Some(target_currency) = target_client.and_then(|id| client_currencies.get(id)) {
            if expense.billing_currency_code != *target_currency {
                push_error(
                    errors,
                    format!("expenses[{index}].billingCurrencyCode"),
                    "target-currency-mismatch",
                );
            }
        }
        if expense.original_currency_code == expense.billing_currency_code
            && (expense.original_amount_minor != expense.billing_amount_minor
                || expense.applied_rate != "1")
        {
            push_error(
                errors,
                format!("expenses[{index}]"),
                "inconsistent-conversion",
            );
        }
    }
}

fn validate_currency_and_money(
    currency: &str,
    amount: i64,
    currency_path: &str,
    amount_path: &str,
    errors: &mut Vec<ManifestValidationError>,
) {
    if !valid_currency(currency) {
        push_error(errors, currency_path, "invalid-currency");
    }
    if !(1..=MAX_EXACT_INTEGER).contains(&amount) {
        push_error(errors, amount_path, "invalid-money");
    }
}

fn valid_optional_catalog_money(value: Option<i64>) -> bool {
    value.is_none_or(|amount| (0..=MAX_EXACT_INTEGER).contains(&amount))
}

fn validate_id(
    id: &str,
    path: &str,
    ids: &mut HashSet<String>,
    errors: &mut Vec<ManifestValidationError>,
) {
    if id.trim().is_empty() || id != id.trim() {
        push_error(errors, path, "invalid-id");
    } else if !ids.insert(id.to_owned()) {
        push_error(errors, path, "duplicate-id");
    }
}

fn normalize_name(name: &mut String, normalized_name: &mut String) {
    *name = name.trim().to_owned();
    *normalized_name = name.to_lowercase();
}

fn valid_currency(value: &str) -> bool {
    value.len() == 3
        && value.bytes().all(|byte| byte.is_ascii_uppercase())
        && SUPPORTED_CURRENCIES
            .split_ascii_whitespace()
            .any(|currency| currency == value)
}

fn valid_rate(value: &str) -> bool {
    let mut parts = value.split('.');
    let whole = parts.next().unwrap_or_default();
    let fraction = parts.next();
    if parts.next().is_some()
        || whole.is_empty()
        || !whole.bytes().all(|byte| byte.is_ascii_digit())
        || fraction.is_some_and(|digits| {
            digits.is_empty()
                || digits.len() > 12
                || !digits.bytes().all(|byte| byte.is_ascii_digit())
        })
    {
        return false;
    }
    whole
        .bytes()
        .chain(fraction.unwrap_or("").bytes())
        .any(|byte| byte != b'0')
}

fn valid_date(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 10
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes
            .iter()
            .enumerate()
            .any(|(index, byte)| index != 4 && index != 7 && !byte.is_ascii_digit())
    {
        return false;
    }
    let year = value[0..4].parse::<u32>().unwrap_or(0);
    let month = value[5..7].parse::<u32>().unwrap_or(0);
    let day = value[8..10].parse::<u32>().unwrap_or(0);
    let leap_year =
        year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400));
    let days = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if leap_year => 29,
        2 => 28,
        _ => return false,
    };
    year != 0 && (1..=days).contains(&day)
}

fn push_error(
    errors: &mut Vec<ManifestValidationError>,
    path: impl Into<String>,
    code: impl Into<String>,
) {
    errors.push(ManifestValidationError {
        path: path.into(),
        code: code.into(),
    });
}

#[cfg(test)]
mod manifest_tests {
    use std::collections::BTreeMap;

    use super::{parse_and_validate_manifest, validate_manifest, ImportManifest};

    fn valid_manifest_json() -> &'static str {
        r#"{
          "schemaVersion": 1,
          "clients": [
            {"id":"client-1","name":"  Acme Consulting  ","currencyCode":"EUR","hourlyRateMinor":12500}
          ],
          "projects": [
            {"id":"project-1","clientId":"client-1","name":" Website ","hourlyRateOverrideMinor":null}
          ],
          "tasks": [
            {"id":"task-1","projectId":"project-1","name":" Discovery ","hourlyRateOverrideMinor":15000}
          ],
          "timeEntries": [
            {"id":"time-2","entryDate":"2026-02-02","durationMinutes":75,"projectId":null,"taskId":"task-1"},
            {"id":"time-1","entryDate":"2026-02-01","durationMinutes":45,"projectId":"project-1","taskId":null}
          ],
          "expenses": [
            {"id":"expense-2","clientId":null,"projectId":"project-1","expenseDate":"2026-02-02","description":" Hosting ","originalCurrencyCode":"USD","originalAmountMinor":1000,"billingCurrencyCode":"EUR","billingAmountMinor":920,"appliedRate":"0.92"},
            {"id":"expense-1","clientId":"client-1","projectId":null,"expenseDate":"2026-02-01","description":" Train ","originalCurrencyCode":"EUR","originalAmountMinor":2500,"billingCurrencyCode":"EUR","billingAmountMinor":2500,"appliedRate":"1"}
          ]
        }"#
    }

    #[test]
    fn manifest_deserializes_the_supported_version_and_preserves_nullable_rates() {
        let manifest: ImportManifest =
            serde_json::from_str(valid_manifest_json()).expect("version 1 should deserialize");

        assert_eq!(manifest.schema_version, 1);
        assert_eq!(manifest.projects[0].hourly_rate_override_minor, None);
        assert_eq!(manifest.tasks[0].hourly_rate_override_minor, Some(15_000));
    }

    #[test]
    fn manifest_validation_rejects_catalog_money_outside_the_safe_integer_range() {
        let mut document: serde_json::Value =
            serde_json::from_str(valid_manifest_json()).expect("fixture should be JSON");
        document["clients"][0]["hourlyRateMinor"] = 9_007_199_254_740_992_i64.into();
        let manifest: ImportManifest =
            serde_json::from_value(document).expect("large integer remains structurally valid");

        let errors = validate_manifest(manifest).expect_err("unsafe money must be rejected");

        assert_eq!(
            errors,
            vec![super::ManifestValidationError {
                path: "clients[0].hourlyRateMinor".to_owned(),
                code: "invalid-money".to_owned(),
            }]
        );
    }

    #[test]
    fn manifest_validation_rejects_well_formed_but_unsupported_currency_codes() {
        let mut document: serde_json::Value =
            serde_json::from_str(valid_manifest_json()).expect("fixture should be JSON");
        document["clients"][0]["currencyCode"] = "ZZZ".into();
        let manifest: ImportManifest =
            serde_json::from_value(document).expect("currency remains structurally valid");

        let errors = validate_manifest(manifest).expect_err("unsupported currency must fail");

        assert!(errors.iter().any(|error| {
            error.path == "clients[0].currencyCode" && error.code == "invalid-currency"
        }));
    }

    #[test]
    fn manifest_parsing_collects_all_independent_structural_errors_in_stable_order() {
        let errors = parse_and_validate_manifest(
            r#"{
              "schemaVersion":"one",
              "clients":[{"name":7,"hourlyRateMinor":"free"}],
              "projects":{},
              "tasks":[false],
              "expenses":[{"id":"expense-1","clientId":null,"projectId":null,"expenseDate":"2026-02-01","description":"Train","originalCurrencyCode":"EUR","originalAmountMinor":2500,"billingCurrencyCode":"EUR","appliedRate":4}]
            }"#,
        )
        .expect_err("all structural errors should be returned together");
        let actual = errors
            .iter()
            .map(|error| (error.path.as_str(), error.code.as_str()))
            .collect::<Vec<_>>();

        assert_eq!(
            actual,
            vec![
                ("schemaVersion", "invalid-type"),
                ("clients[0].id", "missing-field"),
                ("clients[0].name", "invalid-type"),
                ("clients[0].currencyCode", "missing-field"),
                ("clients[0].hourlyRateMinor", "invalid-type"),
                ("projects", "invalid-type"),
                ("tasks[0]", "invalid-type"),
                ("timeEntries", "missing-field"),
                ("expenses[0].billingAmountMinor", "missing-field"),
                ("expenses[0].appliedRate", "invalid-type"),
            ]
        );
    }

    #[test]
    fn manifest_parsing_rejects_duplicate_object_members_at_deterministic_paths() {
        let errors = parse_and_validate_manifest(
            r#"{
              "schemaVersion":1,
              "schemaVersion":1,
              "clients":[{"id":"client-1","id":"client-shadow","name":"Acme","currencyCode":"EUR","hourlyRateMinor":null}],
              "projects":[],
              "tasks":[],
              "timeEntries":[]
            }"#,
        )
        .expect_err("duplicate object members must be rejected before collapsing");

        assert_eq!(
            errors,
            vec![
                super::ManifestValidationError {
                    path: "schemaVersion".to_owned(),
                    code: "duplicate-field".to_owned(),
                },
                super::ManifestValidationError {
                    path: "clients[0].id".to_owned(),
                    code: "duplicate-field".to_owned(),
                },
                super::ManifestValidationError {
                    path: "expenses".to_owned(),
                    code: "missing-field".to_owned(),
                },
            ]
        );
    }

    #[test]
    fn manifest_validation_collects_hierarchy_and_domain_errors_in_stable_order() {
        let manifest: ImportManifest = serde_json::from_str(
            r#"{
              "schemaVersion": 9,
              "clients": [
                {"id":"client-1","name":"Acme","currencyCode":"eur","hourlyRateMinor":-1},
                {"id":"client-1","name":" acme ","currencyCode":"USD","hourlyRateMinor":null}
              ],
              "projects": [
                {"id":"project-1","clientId":"missing-client","name":"","hourlyRateOverrideMinor":null}
              ],
              "tasks": [
                {"id":"task-1","projectId":"missing-project","name":"Task","hourlyRateOverrideMinor":-2}
              ],
              "timeEntries": [
                {"id":"time-1","entryDate":"2026-02-30","durationMinutes":0,"projectId":"missing-project","taskId":"missing-task"}
              ],
              "expenses": [
                {"id":"expense-1","clientId":null,"projectId":null,"expenseDate":"bad-date","description":" ","originalCurrencyCode":"EU","originalAmountMinor":0,"billingCurrencyCode":"eur","billingAmountMinor":-1,"appliedRate":"0"}
              ]
            }"#,
        )
        .expect("domain-invalid data should remain structurally readable");

        let errors = validate_manifest(manifest).expect_err("manifest must be rejected");
        let actual = errors
            .iter()
            .map(|error| (error.path.as_str(), error.code.as_str()))
            .collect::<Vec<_>>();

        assert_eq!(
            actual,
            vec![
                ("schemaVersion", "unsupported-version"),
                ("clients[0].currencyCode", "invalid-currency"),
                ("clients[0].hourlyRateMinor", "invalid-money"),
                ("clients[1].id", "duplicate-id"),
                ("clients[1].name", "duplicate-name"),
                ("projects[0].clientId", "missing-client"),
                ("projects[0].name", "empty-name"),
                ("tasks[0].projectId", "missing-project"),
                ("tasks[0].hourlyRateOverrideMinor", "invalid-money"),
                ("timeEntries[0].entryDate", "invalid-date"),
                ("timeEntries[0].durationMinutes", "invalid-duration"),
                ("timeEntries[0]", "invalid-target"),
                ("timeEntries[0].projectId", "missing-project"),
                ("timeEntries[0].taskId", "missing-task"),
                ("expenses[0].expenseDate", "invalid-date"),
                ("expenses[0].description", "empty-description"),
                ("expenses[0].originalCurrencyCode", "invalid-currency"),
                ("expenses[0].originalAmountMinor", "invalid-money"),
                ("expenses[0].billingCurrencyCode", "invalid-currency"),
                ("expenses[0].billingAmountMinor", "invalid-money"),
                ("expenses[0].appliedRate", "invalid-rate"),
                ("expenses[0]", "invalid-target"),
            ]
        );
    }

    #[test]
    fn manifest_validation_normalizes_names_and_builds_deterministic_preview_totals() {
        let validated =
            parse_and_validate_manifest(valid_manifest_json()).expect("fixture should validate");

        assert_eq!(validated.clients[0].name, "Acme Consulting");
        assert_eq!(validated.clients[0].normalized_name, "acme consulting");
        assert_eq!(validated.projects[0].normalized_name, "website");
        assert_eq!(validated.tasks[0].normalized_name, "discovery");
        assert_eq!(validated.expenses[0].description, "Hosting");
        assert_eq!(validated.summary.clients, 1);
        assert_eq!(validated.summary.projects, 1);
        assert_eq!(validated.summary.tasks, 1);
        assert_eq!(validated.summary.time_entries, 2);
        assert_eq!(validated.summary.expenses, 2);
        assert_eq!(validated.summary.total_minutes, 120);
        assert_eq!(
            validated.summary.expense_totals_by_billing_currency,
            BTreeMap::from([("EUR".to_owned(), 3_420)])
        );
    }
}

#[cfg(test)]
mod target_tests {
    use std::{fs, path::PathBuf};

    use sqlx::{sqlite::SqliteConnectOptions, Connection, Executor, SqliteConnection};
    use tempfile::TempDir;

    use super::{
        authorize_target_apply, inspect_target, resolve_target, HostPlatform, ResolvedTargetKind,
        TargetIssue, TargetPathEnvironment, TargetSelection, DATABASE_FILENAME,
        DEVELOPMENT_IDENTIFIER, PRODUCTION_IDENTIFIER,
    };

    async fn create_current_database(path: &std::path::Path) {
        let options = SqliteConnectOptions::new()
            .filename(path)
            .create_if_missing(true);
        let mut connection = SqliteConnection::connect_with(&options)
            .await
            .expect("temporary SQLite database should open");
        sqlx::query(
            r#"
            CREATE TABLE _sqlx_migrations (
                version BIGINT PRIMARY KEY,
                description TEXT NOT NULL,
                installed_on TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN NOT NULL,
                checksum BLOB NOT NULL,
                execution_time BIGINT NOT NULL
            )
            "#,
        )
        .execute(&mut connection)
        .await
        .expect("migration metadata should be created");
        for migration in crate::database::client_migrations() {
            sqlx::raw_sql(migration.sql)
                .execute(&mut connection)
                .await
                .expect("application migration should apply");
            let checksum = sqlx::migrate::Migration::new(
                migration.version,
                migration.description.into(),
                sqlx::migrate::MigrationType::ReversibleUp,
                migration.sql.into(),
                false,
            )
            .checksum
            .into_owned();
            sqlx::query("INSERT INTO _sqlx_migrations (version, description, success, checksum, execution_time) VALUES (?, ?, TRUE, ?, 1)")
                .bind(migration.version)
                .bind(migration.description)
                .bind(checksum)
                .execute(&mut connection)
                .await
                .expect("migration metadata should be recorded");
        }
        connection
            .close()
            .await
            .expect("temporary database should close");
    }

    fn environments<'a>(
        home: &'a std::path::Path,
        app_data: &'a std::path::Path,
        xdg: Option<&'a std::path::Path>,
    ) -> TargetPathEnvironment<'a> {
        TargetPathEnvironment {
            home: Some(home),
            app_data: Some(app_data),
            xdg_config_home: xdg,
        }
    }

    #[test]
    fn development_tauri_identity_resolves_to_the_importer_development_target() {
        let overlay: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.dev.conf.json"))
                .expect("development Tauri overlay should be valid JSON");
        let configured_identifier = overlay["identifier"]
            .as_str()
            .expect("development Tauri overlay should define an identifier");
        assert_eq!(configured_identifier, DEVELOPMENT_IDENTIFIER);

        let home = PathBuf::from("/Users/operator");
        let app_data = PathBuf::from("C:\\Users\\operator\\AppData\\Roaming");
        let target = resolve_target(
            TargetSelection::Development,
            HostPlatform::Macos,
            environments(&home, &app_data, None),
        )
        .expect("configured development target should resolve");
        assert_eq!(
            target.path,
            home.join("Library/Application Support")
                .join(configured_identifier)
                .join(DATABASE_FILENAME)
        );
        assert_eq!(target.kind, ResolvedTargetKind::Development);
    }

    #[test]
    fn target_paths_resolve_for_each_platform_and_equivalent_explicit_production_is_protected() {
        let home = PathBuf::from("/Users/operator");
        let app_data = PathBuf::from("C:\\Users\\operator\\AppData\\Roaming");
        let xdg = PathBuf::from("/var/operator-config");
        let environment = environments(&home, &app_data, Some(&xdg));

        let mac_production = resolve_target(
            TargetSelection::Production,
            HostPlatform::Macos,
            environment,
        )
        .expect("macOS production should resolve");
        assert_eq!(
            mac_production.path,
            home.join("Library/Application Support/com.personal.timesheet/personal-timesheet.db")
        );
        assert_eq!(mac_production.kind, ResolvedTargetKind::Production);

        let windows_development = resolve_target(
            TargetSelection::Development,
            HostPlatform::Windows,
            environment,
        )
        .expect("Windows development should resolve");
        assert_eq!(
            windows_development.path,
            app_data.join("com.personal.timesheet.dev/personal-timesheet.db")
        );
        assert_eq!(windows_development.kind, ResolvedTargetKind::Development);

        let linux_production = resolve_target(
            TargetSelection::Production,
            HostPlatform::Linux,
            environment,
        )
        .expect("Linux production should resolve");
        assert_eq!(
            linux_production.path,
            xdg.join("com.personal.timesheet/personal-timesheet.db")
        );

        let equivalent = home.join(
            "Library/Application Support/com.personal.timesheet/../com.personal.timesheet/personal-timesheet.db",
        );
        let explicit = resolve_target(
            TargetSelection::Path(equivalent),
            HostPlatform::Macos,
            environment,
        )
        .expect("equivalent explicit path should resolve");
        assert_eq!(explicit.kind, ResolvedTargetKind::Production);

        let relative = resolve_target(
            TargetSelection::Path(PathBuf::from("../scratch.db")),
            HostPlatform::Macos,
            environment,
        )
        .expect("relative explicit path should resolve without changing meaning");
        assert_eq!(relative.path, PathBuf::from("../scratch.db"));
    }

    #[test]
    fn target_apply_requires_the_exact_acknowledgement_only_for_production() {
        let production = super::ResolvedTarget {
            path: PathBuf::from("production.db"),
            kind: ResolvedTargetKind::Production,
        };
        let development = super::ResolvedTarget {
            path: PathBuf::from("development.db"),
            kind: ResolvedTargetKind::Development,
        };

        assert_eq!(
            authorize_target_apply(&production, None),
            Err(TargetIssue::ProductionAcknowledgementRequired)
        );
        assert_eq!(
            authorize_target_apply(&production, Some("com.personal.timesheet.dev")),
            Err(TargetIssue::ProductionAcknowledgementRequired)
        );
        assert_eq!(
            authorize_target_apply(&production, Some(PRODUCTION_IDENTIFIER)),
            Ok(())
        );
        assert_eq!(authorize_target_apply(&development, None), Ok(()));
    }

    #[test]
    fn target_paths_protect_an_existing_hard_link_to_production() {
        let directory = TempDir::new().expect("temporary directory should exist");
        let home = directory.path().join("home");
        let app_data = directory.path().join("app-data");
        let production =
            home.join("Library/Application Support/com.personal.timesheet/personal-timesheet.db");
        fs::create_dir_all(
            production
                .parent()
                .expect("production should have a parent"),
        )
        .expect("production directory should be created");
        fs::write(&production, b"database identity").expect("production fixture should be written");
        let alias = directory.path().join("production-alias.db");
        fs::hard_link(&production, &alias).expect("hard-link fixture should be supported");

        let resolved = resolve_target(
            TargetSelection::Path(alias),
            HostPlatform::Macos,
            environments(&home, &app_data, None),
        )
        .expect("hard-link alias should resolve");

        assert_eq!(resolved.kind, ResolvedTargetKind::Production);
        assert_eq!(
            authorize_target_apply(&resolved, None),
            Err(TargetIssue::ProductionAcknowledgementRequired)
        );
    }

    #[test]
    fn target_inspection_accepts_only_current_empty_schema_without_changing_bytes() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("eligible.db");
            create_current_database(&database).await;
            let before = fs::read(&database).expect("database bytes should be readable");

            let inspection = inspect_target(&database).await;

            assert_eq!(inspection.issue, None);
            assert_eq!(inspection.migration_version, Some(6));
            assert_eq!(inspection.record_counts.values().sum::<i64>(), 0);
            assert_eq!(
                fs::read(&database).expect("database bytes should remain readable"),
                before
            );
        });
    }

    #[test]
    fn target_inspection_rejects_missing_incompatible_and_non_empty_databases() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            assert_eq!(
                inspect_target(&directory.path().join("missing.db"))
                    .await
                    .issue,
                Some(TargetIssue::Missing)
            );

            let incompatible = directory.path().join("incompatible.db");
            SqliteConnection::connect_with(
                &SqliteConnectOptions::new()
                    .filename(&incompatible)
                    .create_if_missing(true),
            )
            .await
            .expect("incompatible database should be created")
            .close()
            .await
            .expect("incompatible database should close");
            assert_eq!(
                inspect_target(&incompatible).await.issue,
                Some(TargetIssue::IncompatibleSchema)
            );

            let failed_migration = directory.path().join("failed-migration.db");
            create_current_database(&failed_migration).await;
            let mut connection = SqliteConnection::connect_with(
                &SqliteConnectOptions::new()
                    .filename(&failed_migration)
                    .create_if_missing(false),
            )
            .await
            .expect("current database should reopen");
            sqlx::query("INSERT INTO _sqlx_migrations (version, description, success, checksum, execution_time) VALUES (7, 'failed future migration', FALSE, X'00', 1)")
                .execute(&mut connection)
                .await
                .expect("failed migration metadata should insert");
            connection.close().await.expect("database should close");
            assert_eq!(
                inspect_target(&failed_migration).await.issue,
                Some(TargetIssue::IncompatibleSchema)
            );

            let non_empty = directory.path().join("non-empty.db");
            create_current_database(&non_empty).await;
            let mut connection = SqliteConnection::connect_with(
                &SqliteConnectOptions::new()
                    .filename(&non_empty)
                    .create_if_missing(false),
            )
            .await
            .expect("current database should reopen");
            sqlx::query(
                "INSERT INTO clients VALUES ('client-1','Acme','acme','EUR',NULL,'now','now',NULL)",
            )
            .execute(&mut connection)
            .await
            .expect("record should insert");
            connection.close().await.expect("database should close");
            assert_eq!(
                inspect_target(&non_empty).await.issue,
                Some(TargetIssue::NonEmpty)
            );
        });
    }

    #[test]
    fn target_inspection_rejects_forged_metadata_when_a_required_unique_index_is_missing() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("forged-schema.db");
            create_current_database(&database).await;
            let mut connection = SqliteConnection::connect_with(
                &SqliteConnectOptions::new()
                    .filename(&database)
                    .create_if_missing(false),
            )
            .await
            .expect("current database should reopen");
            connection
                .execute("DROP INDEX clients_active_name_unique")
                .await
                .expect("required index should be removed for the fixture");
            connection.close().await.expect("database should close");

            assert_eq!(
                inspect_target(&database).await.issue,
                Some(TargetIssue::IncompatibleSchema)
            );
        });
    }

    #[test]
    fn target_inspection_rejects_a_forged_migration_checksum() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("forged-checksum.db");
            create_current_database(&database).await;
            let mut connection = SqliteConnection::connect_with(
                &SqliteConnectOptions::new()
                    .filename(&database)
                    .create_if_missing(false),
            )
            .await
            .expect("current database should reopen");
            connection
                .execute("UPDATE _sqlx_migrations SET checksum = X'00' WHERE version = 6")
                .await
                .expect("checksum should be forged for the fixture");
            connection.close().await.expect("database should close");

            assert_eq!(
                inspect_target(&database).await.issue,
                Some(TargetIssue::IncompatibleSchema)
            );
        });
    }

    #[test]
    fn target_inspection_refuses_sidecars_and_an_exclusive_lock() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("active.db");
            create_current_database(&database).await;
            fs::write(format!("{}-wal", database.display()), b"active")
                .expect("sidecar fixture should be written");
            assert_eq!(
                inspect_target(&database).await.issue,
                Some(TargetIssue::ActiveUse)
            );
            fs::remove_file(format!("{}-wal", database.display()))
                .expect("sidecar fixture should be removed");

            let mut holder = SqliteConnection::connect_with(
                &SqliteConnectOptions::new()
                    .filename(&database)
                    .create_if_missing(false),
            )
            .await
            .expect("lock holder should connect");
            holder
                .execute("BEGIN EXCLUSIVE")
                .await
                .expect("exclusive lock should start");
            assert_eq!(
                inspect_target(&database).await.issue,
                Some(TargetIssue::ActiveUse)
            );
            holder
                .execute("ROLLBACK")
                .await
                .expect("lock should release");
        });
    }
}

#[cfg(test)]
mod apply_tests {
    use std::collections::BTreeMap;

    use sqlx::{sqlite::SqliteConnectOptions, Connection, Executor, SqliteConnection};
    use tempfile::TempDir;

    use super::{
        apply_manifest, apply_manifest_at_path, parse_and_validate_manifest, ApplyError,
        ImportExpense, ResolvedTarget, ResolvedTargetKind, TargetIssue,
    };

    fn manifest_json() -> &'static str {
        r#"{
          "schemaVersion":1,
          "clients":[{"id":"client-1","name":"Acme","currencyCode":"EUR","hourlyRateMinor":12500}],
          "projects":[{"id":"project-1","clientId":"client-1","name":"Website","hourlyRateOverrideMinor":null}],
          "tasks":[{"id":"task-1","projectId":"project-1","name":"Discovery","hourlyRateOverrideMinor":15000}],
          "timeEntries":[{"id":"time-1","entryDate":"2026-08-07","durationMinutes":90,"projectId":null,"taskId":"task-1"}],
          "expenses":[{"id":"expense-1","clientId":null,"projectId":"project-1","expenseDate":"2026-08-07","description":"Train","originalCurrencyCode":"EUR","originalAmountMinor":2500,"billingCurrencyCode":"EUR","billingAmountMinor":2500,"appliedRate":"1"}]
        }"#
    }

    async fn create_current_database(path: &std::path::Path) {
        let mut connection = SqliteConnection::connect_with(
            &SqliteConnectOptions::new()
                .filename(path)
                .create_if_missing(true),
        )
        .await
        .expect("temporary SQLite database should open");
        sqlx::query(
            r#"
            CREATE TABLE _sqlx_migrations (
                version BIGINT PRIMARY KEY,
                description TEXT NOT NULL,
                installed_on TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                success BOOLEAN NOT NULL,
                checksum BLOB NOT NULL,
                execution_time BIGINT NOT NULL
            )
            "#,
        )
        .execute(&mut connection)
        .await
        .expect("migration metadata should be created");
        for migration in crate::database::client_migrations() {
            sqlx::raw_sql(migration.sql)
                .execute(&mut connection)
                .await
                .expect("application migration should apply");
            let checksum = sqlx::migrate::Migration::new(
                migration.version,
                migration.description.into(),
                sqlx::migrate::MigrationType::ReversibleUp,
                migration.sql.into(),
                false,
            )
            .checksum
            .into_owned();
            sqlx::query("INSERT INTO _sqlx_migrations (version, description, success, checksum, execution_time) VALUES (?, ?, TRUE, ?, 1)")
                .bind(migration.version)
                .bind(migration.description)
                .bind(checksum)
                .execute(&mut connection)
                .await
                .expect("migration metadata should be recorded");
        }
        connection.close().await.expect("database should close");
    }

    #[test]
    fn apply_public_boundary_requires_exact_acknowledgement_for_production() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("production.db");
            create_current_database(&database).await;
            let target = ResolvedTarget {
                path: database,
                kind: ResolvedTargetKind::Production,
            };
            let manifest =
                parse_and_validate_manifest(manifest_json()).expect("manifest should validate");

            assert_eq!(
                apply_manifest(&target, None, manifest, "2026-08-07T12:34:56Z").await,
                Err(ApplyError::Ineligible(
                    TargetIssue::ProductionAcknowledgementRequired
                ))
            );
        });
    }

    #[test]
    fn apply_rejects_sqlite_dates_that_are_not_application_rfc3339_timestamps() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("invalid-timestamp.db");
            create_current_database(&database).await;
            let target = ResolvedTarget {
                path: database,
                kind: ResolvedTargetKind::Explicit,
            };
            let manifest =
                parse_and_validate_manifest(manifest_json()).expect("manifest should validate");

            assert_eq!(
                apply_manifest(&target, None, manifest, "2026-08-07").await,
                Err(ApplyError::InvalidTimestamp)
            );
        });
    }

    #[test]
    fn apply_verifies_expense_totals_larger_than_sqlite_i64_without_overflow() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("large-expense-total.db");
            create_current_database(&database).await;
            let target = ResolvedTarget {
                path: database,
                kind: ResolvedTargetKind::Explicit,
            };
            let mut manifest =
                parse_and_validate_manifest(manifest_json()).expect("manifest should validate");
            let amount = 9_007_199_254_740_991_i64;
            manifest.expenses = (0..1_025)
                .map(|index| ImportExpense {
                    id: format!("expense-{index}"),
                    client_id: None,
                    project_id: Some("project-1".to_owned()),
                    expense_date: "2026-08-07".to_owned(),
                    description: format!("Expense {index}"),
                    original_currency_code: "EUR".to_owned(),
                    original_amount_minor: amount,
                    billing_currency_code: "EUR".to_owned(),
                    billing_amount_minor: amount,
                    applied_rate: "1".to_owned(),
                })
                .collect();
            manifest.summary.expenses = manifest.expenses.len();
            let expected_total = i128::from(amount) * 1_025;
            manifest.summary.expense_totals_by_billing_currency =
                BTreeMap::from([("EUR".to_owned(), expected_total)]);

            let receipt = apply_manifest(&target, None, manifest, "2026-08-07T12:34:56.000Z")
                .await
                .expect("valid i128 aggregate should commit");

            assert_eq!(
                receipt.expense_totals_by_billing_currency,
                BTreeMap::from([("EUR".to_owned(), expected_total)])
            );
            assert_eq!(receipt.record_counts["expenses"], 1_025);
        });
    }

    #[test]
    fn apply_inserts_every_entity_once_with_consistent_timestamps_and_totals() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("apply-success.db");
            create_current_database(&database).await;
            let manifest =
                parse_and_validate_manifest(manifest_json()).expect("manifest should validate");

            let receipt = apply_manifest_at_path(&database, manifest, "2026-08-07T12:34:56Z")
                .await
                .expect("eligible import should commit");

            assert_eq!(
                receipt.record_counts,
                BTreeMap::from([
                    ("clients".to_owned(), 1),
                    ("expenses".to_owned(), 1),
                    ("projects".to_owned(), 1),
                    ("tasks".to_owned(), 1),
                    ("time_entries".to_owned(), 1),
                ])
            );
            assert_eq!(receipt.total_minutes, 90);
            assert_eq!(
                receipt.expense_totals_by_billing_currency,
                BTreeMap::from([("EUR".to_owned(), 2_500)])
            );

            let mut connection = SqliteConnection::connect_with(
                &SqliteConnectOptions::new()
                    .filename(&database)
                    .read_only(true),
            )
            .await
            .expect("imported database should open");
            let null_override: Option<i64> = sqlx::query_scalar(
                "SELECT hourly_rate_override_minor FROM projects WHERE id='project-1'",
            )
            .fetch_one(&mut connection)
            .await
            .expect("project should exist");
            assert_eq!(null_override, None);
            let timestamp_mismatches: i64 = sqlx::query_scalar(
                "SELECT (SELECT COUNT(*) FROM clients WHERE created_at <> '2026-08-07T12:34:56Z' OR updated_at <> created_at) + (SELECT COUNT(*) FROM projects WHERE created_at <> '2026-08-07T12:34:56Z' OR updated_at <> created_at) + (SELECT COUNT(*) FROM tasks WHERE created_at <> '2026-08-07T12:34:56Z' OR updated_at <> created_at) + (SELECT COUNT(*) FROM time_entries WHERE created_at <> '2026-08-07T12:34:56Z' OR updated_at <> created_at) + (SELECT COUNT(*) FROM expenses WHERE created_at <> '2026-08-07T12:34:56Z' OR updated_at <> created_at)",
            )
            .fetch_one(&mut connection)
            .await
            .expect("timestamps should be queryable");
            assert_eq!(timestamp_mismatches, 0);
        });
    }

    #[test]
    fn apply_rolls_back_all_prior_inserts_when_a_late_constraint_fails() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("apply-rollback.db");
            create_current_database(&database).await;
            let mut manifest =
                parse_and_validate_manifest(manifest_json()).expect("manifest should validate");
            manifest.expenses[0].applied_rate = "0".to_owned();

            assert!(matches!(
                apply_manifest_at_path(&database, manifest, "2026-08-07T12:34:56Z").await,
                Err(ApplyError::Persistence(_))
            ));

            let mut connection = SqliteConnection::connect_with(
                &SqliteConnectOptions::new()
                    .filename(&database)
                    .read_only(true),
            )
            .await
            .expect("database should reopen");
            for table in ["clients", "projects", "tasks", "time_entries", "expenses"] {
                let count: i64 = sqlx::query_scalar(&format!("SELECT COUNT(*) FROM {table}"))
                    .fetch_one(&mut connection)
                    .await
                    .expect("count should be readable");
                assert_eq!(count, 0, "{table} should roll back");
            }
        });
    }

    #[test]
    fn apply_reinspects_and_refuses_a_database_that_is_no_longer_empty() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("apply-ineligible.db");
            create_current_database(&database).await;
            let mut connection = SqliteConnection::connect_with(
                &SqliteConnectOptions::new()
                    .filename(&database)
                    .create_if_missing(false),
            )
            .await
            .expect("database should reopen");
            connection
                .execute("INSERT INTO clients VALUES ('existing','Existing','existing','EUR',NULL,'now','now',NULL)")
                .await
                .expect("existing record should insert");
            connection.close().await.expect("database should close");
            let manifest =
                parse_and_validate_manifest(manifest_json()).expect("manifest should validate");

            assert_eq!(
                apply_manifest_at_path(&database, manifest, "2026-08-07T12:34:56Z").await,
                Err(ApplyError::Ineligible(TargetIssue::NonEmpty))
            );
        });
    }

    #[test]
    fn apply_rolls_back_when_post_write_counts_do_not_match_the_preview() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should exist");
            let database = directory.path().join("apply-count-mismatch.db");
            create_current_database(&database).await;
            let mut manifest =
                parse_and_validate_manifest(manifest_json()).expect("manifest should validate");
            manifest.summary.clients = 0;

            assert_eq!(
                apply_manifest_at_path(&database, manifest, "2026-08-07T12:34:56Z").await,
                Err(ApplyError::VerificationFailed)
            );

            let mut connection = SqliteConnection::connect_with(
                &SqliteConnectOptions::new()
                    .filename(&database)
                    .read_only(true),
            )
            .await
            .expect("database should reopen");
            let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM clients")
                .fetch_one(&mut connection)
                .await
                .expect("count should be readable");
            assert_eq!(count, 0);
        });
    }
}
