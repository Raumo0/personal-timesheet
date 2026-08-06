use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use serde::{Deserialize, Serialize};
use sqlx::{sqlite::SqliteConnectOptions, Connection, SqliteConnection};

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InvoiceRequest {
    pub client_id: String,
    pub sender_name: String,
    pub issue_date: String,
    pub invoice_number: Option<String>,
    pub period_start: String,
    pub period_end: String,
    /// `None` means every eligible Expense; `Some` is an explicit draft selection.
    pub included_expense_ids: Option<Vec<String>>,
    pub draft_rate_overrides_minor: BTreeMap<String, i64>,
    #[serde(default)]
    pub payment_note_enabled: bool,
    #[serde(default)]
    pub payment_note: String,
    #[serde(default)]
    pub include_daily_activity: bool,
    #[serde(default)]
    pub include_work_category_breakdown: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ClientSource {
    pub id: String,
    pub name: String,
    pub currency_code: String,
    pub hourly_rate_minor: Option<i64>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectSource {
    pub id: String,
    pub client_id: String,
    pub name: String,
    pub hourly_rate_override_minor: Option<i64>,
    pub archived: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TaskSource {
    pub id: String,
    pub project_id: String,
    pub name: String,
    pub hourly_rate_override_minor: Option<i64>,
    pub archived: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TimeEntrySource {
    pub date: String,
    pub minutes: i64,
    pub project_id: String,
    pub task_id: Option<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExpenseSource {
    pub id: String,
    pub client_id: Option<String>,
    pub project_id: Option<String>,
    pub date: String,
    pub description: String,
    pub billing_currency_code: String,
    pub billing_amount_minor: i64,
    pub archived: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InvoiceSourceSnapshot {
    pub client: ClientSource,
    pub projects: Vec<ProjectSource>,
    pub tasks: Vec<TaskSource>,
    pub time_entries: Vec<TimeEntrySource>,
    pub expenses: Vec<ExpenseSource>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ValidationIssue {
    pub code: String,
    pub field: Option<String>,
    pub line_key: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkLine {
    pub key: String,
    pub label: String,
    pub task_id: Option<String>,
    pub minutes: i64,
    pub rate_minor: Option<i64>,
    pub amount_minor: Option<i64>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InvoiceProject {
    pub id: String,
    pub name: String,
    pub work_lines: Vec<WorkLine>,
    pub subtotal_minor: i64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InvoiceExpense {
    pub id: String,
    pub project_id: Option<String>,
    pub project_name: Option<String>,
    pub date: String,
    pub description: String,
    pub billing_amount_minor: i64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DailyActivityPoint {
    pub date: String,
    pub minutes: i64,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DailyActivityAxis {
    pub upper_bound_hours: f64,
    pub ticks: Vec<f64>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkCategoryShare {
    pub project_id: String,
    pub project_name: String,
    pub line_key: String,
    pub label: String,
    pub minutes: i64,
    pub share: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct InvoiceDocument {
    pub sender_name: String,
    pub recipient_name: String,
    pub issue_date: String,
    pub invoice_number: Option<String>,
    pub payment_note: Option<String>,
    pub include_daily_activity: bool,
    pub include_work_category_breakdown: bool,
    pub period_start: String,
    pub period_end: String,
    pub currency_code: String,
    pub projects: Vec<InvoiceProject>,
    pub expenses: Vec<InvoiceExpense>,
    pub work_subtotal_minor: i64,
    pub expense_subtotal_minor: i64,
    pub total_due_minor: i64,
    pub total_minutes: i64,
    pub active_days: usize,
    pub daily_activity: Vec<DailyActivityPoint>,
    pub daily_activity_axis: DailyActivityAxis,
    pub work_category_shares: Vec<WorkCategoryShare>,
    pub validation_issues: Vec<ValidationIssue>,
    pub exportable: bool,
}

pub async fn prepare_invoice_at_path(
    path: &Path,
    request: InvoiceRequest,
) -> Result<InvoiceDocument, String> {
    let source = load_invoice_source_at_path(path, &request).await?;
    Ok(compose_invoice(&request, &source))
}

async fn load_invoice_source_at_path(
    path: &Path,
    request: &InvoiceRequest,
) -> Result<InvoiceSourceSnapshot, String> {
    let mut connection = SqliteConnection::connect_with(
        &SqliteConnectOptions::new()
            .filename(path)
            .create_if_missing(false)
            .read_only(true),
    )
    .await
    .map_err(persistence_error)?;
    let mut transaction = connection.begin().await.map_err(persistence_error)?;

    let loaded = async {
        let client: Option<(String, String, String, Option<i64>)> = sqlx::query_as(
            "SELECT id, name, currency_code, hourly_rate_minor FROM clients WHERE id = ? AND archived_at IS NULL",
        )
        .bind(&request.client_id)
        .fetch_optional(&mut *transaction)
        .await
        .map_err(persistence_error)?;
        let Some((id, name, currency_code, hourly_rate_minor)) = client else {
            return Err("not-found: active Client does not exist".to_owned());
        };
        let client = ClientSource { id, name, currency_code, hourly_rate_minor };

        let project_rows: Vec<(String, String, String, Option<i64>, Option<String>)> = sqlx::query_as(
            "SELECT id, client_id, name, hourly_rate_override_minor, archived_at FROM projects WHERE client_id = ?",
        )
        .bind(&client.id)
        .fetch_all(&mut *transaction)
        .await
        .map_err(persistence_error)?;
        let projects = project_rows
            .into_iter()
            .map(|(id, client_id, name, hourly_rate_override_minor, archived_at)| ProjectSource {
                id, client_id, name, hourly_rate_override_minor, archived: archived_at.is_some(),
            })
            .collect();

        let task_rows: Vec<(String, String, String, Option<i64>, Option<String>)> = sqlx::query_as(
            "SELECT tasks.id, tasks.project_id, tasks.name, tasks.hourly_rate_override_minor, tasks.archived_at FROM tasks JOIN projects ON projects.id = tasks.project_id WHERE projects.client_id = ?",
        )
        .bind(&client.id)
        .fetch_all(&mut *transaction)
        .await
        .map_err(persistence_error)?;
        let tasks = task_rows
            .into_iter()
            .map(|(id, project_id, name, hourly_rate_override_minor, archived_at)| TaskSource {
                id, project_id, name, hourly_rate_override_minor, archived: archived_at.is_some(),
            })
            .collect();

        let entry_rows: Vec<(String, i64, String, Option<String>)> = sqlx::query_as(
            "SELECT time_entries.entry_date, time_entries.duration_minutes, COALESCE(time_entries.project_id, tasks.project_id), time_entries.task_id \
             FROM time_entries \
             LEFT JOIN tasks ON tasks.id = time_entries.task_id \
             JOIN projects ON projects.id = COALESCE(time_entries.project_id, tasks.project_id) \
             WHERE projects.client_id = ? AND time_entries.entry_date BETWEEN ? AND ?",
        )
        .bind(&client.id)
        .bind(&request.period_start)
        .bind(&request.period_end)
        .fetch_all(&mut *transaction)
        .await
        .map_err(persistence_error)?;
        let time_entries = entry_rows
            .into_iter()
            .map(|(date, minutes, project_id, task_id)| TimeEntrySource { date, minutes, project_id, task_id })
            .collect();

        let expense_rows: Vec<(String, Option<String>, Option<String>, String, String, String, i64)> = sqlx::query_as(
            "SELECT expenses.id, expenses.client_id, expenses.project_id, expenses.expense_date, expenses.description, expenses.billing_currency_code, expenses.billing_amount_minor \
             FROM expenses \
             LEFT JOIN projects ON projects.id = expenses.project_id \
             WHERE expenses.archived_at IS NULL \
               AND expenses.expense_date BETWEEN ? AND ? \
               AND expenses.billing_currency_code = ? \
               AND ((expenses.client_id = ? AND expenses.project_id IS NULL) \
                    OR (expenses.client_id IS NULL AND projects.client_id = ?))",
        )
        .bind(&request.period_start)
        .bind(&request.period_end)
        .bind(&client.currency_code)
        .bind(&client.id)
        .bind(&client.id)
        .fetch_all(&mut *transaction)
        .await
        .map_err(persistence_error)?;
        let expenses = expense_rows
            .into_iter()
            .map(|(id, client_id, project_id, date, description, billing_currency_code, billing_amount_minor)| ExpenseSource {
                id, client_id, project_id, date, description, billing_currency_code, billing_amount_minor, archived: false,
            })
            .collect();

        Ok(InvoiceSourceSnapshot { client, projects, tasks, time_entries, expenses })
    }
    .await;

    let rollback = transaction.rollback().await;
    match (loaded, rollback) {
        (Ok(source), Ok(())) => Ok(source),
        (Err(primary), Ok(())) => Err(primary),
        (Ok(_), Err(rollback)) => Err(persistence_error(rollback)),
        (Err(primary), Err(rollback)) => Err(format!(
            "{primary}. Transaction rollback also failed: {rollback}"
        )),
    }
}

fn persistence_error(error: sqlx::Error) -> String {
    format!("persistence: invoice source read failed: {error}")
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct LocalDate {
    year: i32,
    month: u32,
    day: u32,
}

impl LocalDate {
    fn parse(value: &str) -> Option<Self> {
        let bytes = value.as_bytes();
        if bytes.len() != 10
            || bytes.get(4) != Some(&b'-')
            || bytes.get(7) != Some(&b'-')
            || !bytes[..4].iter().all(u8::is_ascii_digit)
            || !bytes[5..7].iter().all(u8::is_ascii_digit)
            || !bytes[8..].iter().all(u8::is_ascii_digit)
        {
            return None;
        }
        let year = value[0..4].parse().ok()?;
        let month = value[5..7].parse().ok()?;
        let day = value[8..10].parse().ok()?;
        let date = Self { year, month, day };
        (year >= 1 && month > 0 && month <= 12 && day > 0 && day <= days_in_month(year, month))
            .then_some(date)
    }

    fn next(self) -> Self {
        if self.day < days_in_month(self.year, self.month) {
            Self {
                day: self.day + 1,
                ..self
            }
        } else if self.month < 12 {
            Self {
                year: self.year,
                month: self.month + 1,
                day: 1,
            }
        } else {
            Self {
                year: self.year + 1,
                month: 1,
                day: 1,
            }
        }
    }

    fn iso(self) -> String {
        format!("{:04}-{:02}-{:02}", self.year, self.month, self.day)
    }
}

fn days_in_month(year: i32, month: u32) -> u32 {
    match month {
        4 | 6 | 9 | 11 => 30,
        2 if year % 400 == 0 || (year % 4 == 0 && year % 100 != 0) => 29,
        2 => 28,
        _ => 31,
    }
}

fn issue(code: &str, field: Option<&str>, line_key: Option<&str>) -> ValidationIssue {
    ValidationIssue {
        code: code.into(),
        field: field.map(str::to_owned),
        line_key: line_key.map(str::to_owned),
    }
}

fn rounded_line_amount(minutes: i64, rate_minor: i64) -> Option<i64> {
    if minutes < 0 || rate_minor < 0 {
        return None;
    }
    let numerator = i128::from(minutes).checked_mul(i128::from(rate_minor))?;
    i64::try_from((numerator + 30) / 60).ok()
}

pub fn nice_hour_ticks(max_minutes: i64) -> Vec<f64> {
    let max_hours = (max_minutes.max(0) as f64) / 60.0;
    let target_max = if max_hours == 0.0 { 1.0 } else { max_hours };
    let raw_step = target_max / 6.0;
    let exponent = raw_step.log10().floor() as i32;
    let mut candidates = Vec::new();
    for candidate_exponent in (exponent - 1)..=(exponent + 1) {
        let magnitude = 10_f64.powi(candidate_exponent);
        for nice in [1.0, 2.0, 2.5, 5.0, 10.0] {
            let step = nice * magnitude;
            let intervals = (target_max / step).ceil() as usize;
            if (5..=8).contains(&intervals) {
                candidates.push((intervals.abs_diff(6), step));
            }
        }
    }
    candidates.sort_by(|left, right| {
        left.0
            .cmp(&right.0)
            .then_with(|| left.1.total_cmp(&right.1))
    });
    let step = candidates
        .first()
        .map(|candidate| candidate.1)
        .unwrap_or(raw_step);
    let intervals = (target_max / step).ceil() as usize;
    (0..=intervals)
        .map(|index| ((index as f64 * step) * 1_000_000_000.0).round() / 1_000_000_000.0)
        .collect()
}

pub fn compose_invoice(
    request: &InvoiceRequest,
    source: &InvoiceSourceSnapshot,
) -> InvoiceDocument {
    let mut validation_issues = Vec::new();
    if request.client_id != source.client.id {
        validation_issues.push(issue("invalid-client", Some("clientId"), None));
    }
    if request.sender_name.trim().is_empty() {
        validation_issues.push(issue("required", Some("senderName"), None));
    }
    if LocalDate::parse(&request.issue_date).is_none() {
        validation_issues.push(issue("invalid-date", Some("issueDate"), None));
    }
    let start = LocalDate::parse(&request.period_start);
    let end = LocalDate::parse(&request.period_end);
    if start.is_none() {
        validation_issues.push(issue("invalid-date", Some("periodStart"), None));
    }
    if end.is_none() {
        validation_issues.push(issue("invalid-date", Some("periodEnd"), None));
    }
    if matches!((start, end), (Some(start), Some(end)) if start > end) {
        validation_issues.push(issue("invalid-period", Some("periodStart"), None));
    }

    let project_by_id: BTreeMap<_, _> = source
        .projects
        .iter()
        .filter(|project| project.client_id == source.client.id)
        .map(|project| (project.id.as_str(), project))
        .collect();
    let task_by_id: BTreeMap<_, _> = source
        .tasks
        .iter()
        .filter(|task| project_by_id.contains_key(task.project_id.as_str()))
        .map(|task| (task.id.as_str(), task))
        .collect();

    let in_period = |value: &str| -> bool {
        matches!((start, end, LocalDate::parse(value)), (Some(start), Some(end), Some(value)) if value >= start && value <= end)
    };
    let mut grouped_minutes: BTreeMap<(String, Option<String>), i64> = BTreeMap::new();
    let mut daily_minutes: BTreeMap<String, i64> = BTreeMap::new();
    for entry in source
        .time_entries
        .iter()
        .filter(|entry| entry.minutes > 0 && in_period(&entry.date))
    {
        let Some(project) = project_by_id.get(entry.project_id.as_str()) else {
            continue;
        };
        let task_id = match entry.task_id.as_ref() {
            Some(task_id)
                if task_by_id
                    .get(task_id.as_str())
                    .is_some_and(|task| task.project_id == project.id) =>
            {
                Some(task_id.clone())
            }
            Some(_) => continue,
            None => None,
        };
        let key = (project.id.clone(), task_id);
        if let Some(total) = grouped_minutes
            .get(&key)
            .copied()
            .and_then(|total| total.checked_add(entry.minutes))
        {
            grouped_minutes.insert(key, total);
        } else if !grouped_minutes.contains_key(&key) {
            grouped_minutes.insert(key, entry.minutes);
        } else {
            validation_issues.push(issue("amount-overflow", None, None));
        }
        let day_total = daily_minutes.entry(entry.date.clone()).or_default();
        if let Some(total) = day_total.checked_add(entry.minutes) {
            *day_total = total;
        } else {
            validation_issues.push(issue("amount-overflow", None, None));
        }
    }

    let mut projects = Vec::new();
    let mut work_subtotal_minor = 0_i64;
    for project in project_by_id.values() {
        let mut work_lines = Vec::new();
        for ((project_id, task_id), minutes) in grouped_minutes
            .iter()
            .filter(|((project_id, _), _)| project_id == &project.id)
        {
            let (key, label, inherited_rate) = if let Some(task_id) = task_id {
                let task = task_by_id[task_id.as_str()];
                (
                    format!("task:{task_id}"),
                    task.name.clone(),
                    task.hourly_rate_override_minor
                        .or(project.hourly_rate_override_minor)
                        .or(source.client.hourly_rate_minor),
                )
            } else {
                (
                    format!("project:{project_id}:general"),
                    "General project work".into(),
                    project
                        .hourly_rate_override_minor
                        .or(source.client.hourly_rate_minor),
                )
            };
            let rate = request
                .draft_rate_overrides_minor
                .get(&key)
                .copied()
                .or(inherited_rate);
            let amount = match rate {
                Some(rate) if rate < 0 => {
                    validation_issues.push(issue("invalid-rate", None, Some(&key)));
                    None
                }
                Some(rate) => match rounded_line_amount(*minutes, rate) {
                    Some(amount) => Some(amount),
                    None => {
                        validation_issues.push(issue("amount-overflow", None, Some(&key)));
                        None
                    }
                },
                None => {
                    validation_issues.push(issue("missing-rate", None, Some(&key)));
                    None
                }
            };
            if let Some(amount) = amount {
                match work_subtotal_minor.checked_add(amount) {
                    Some(total) => work_subtotal_minor = total,
                    None => validation_issues.push(issue("amount-overflow", None, Some(&key))),
                }
            }
            work_lines.push(WorkLine {
                key,
                label,
                task_id: task_id.clone(),
                minutes: *minutes,
                rate_minor: rate.filter(|rate| *rate >= 0),
                amount_minor: amount,
            });
        }
        work_lines.sort_by(|left, right| {
            left.task_id
                .is_some()
                .cmp(&right.task_id.is_some())
                .then_with(|| left.label.cmp(&right.label))
                .then_with(|| left.key.cmp(&right.key))
        });
        if !work_lines.is_empty() {
            let subtotal_minor = work_lines
                .iter()
                .filter_map(|line| line.amount_minor)
                .try_fold(0_i64, i64::checked_add)
                .unwrap_or(0);
            projects.push(InvoiceProject {
                id: project.id.clone(),
                name: project.name.clone(),
                work_lines,
                subtotal_minor,
            });
        }
    }
    projects.sort_by(|left, right| {
        left.name
            .cmp(&right.name)
            .then_with(|| left.id.cmp(&right.id))
    });

    let selected_expenses = request
        .included_expense_ids
        .as_ref()
        .map(|ids| ids.iter().map(String::as_str).collect::<BTreeSet<_>>());
    let mut expenses = Vec::new();
    for expense in source.expenses.iter().filter(|expense| {
        !expense.archived && expense.billing_amount_minor >= 0 && in_period(&expense.date)
    }) {
        if selected_expenses
            .as_ref()
            .is_some_and(|ids| !ids.contains(expense.id.as_str()))
        {
            continue;
        }
        let owned_directly = expense.client_id.as_deref() == Some(source.client.id.as_str())
            && expense.project_id.is_none();
        let owned_project = expense.client_id.is_none()
            && expense
                .project_id
                .as_ref()
                .and_then(|id| project_by_id.get(id.as_str()))
                .is_some();
        if (!owned_directly && !owned_project)
            || expense.billing_currency_code != source.client.currency_code
        {
            continue;
        }
        let project_name = expense
            .project_id
            .as_ref()
            .and_then(|id| project_by_id.get(id.as_str()))
            .map(|project| project.name.clone());
        expenses.push(InvoiceExpense {
            id: expense.id.clone(),
            project_id: expense.project_id.clone(),
            project_name,
            date: expense.date.clone(),
            description: expense.description.clone(),
            billing_amount_minor: expense.billing_amount_minor,
        });
    }
    expenses.sort_by(|left, right| {
        left.date
            .cmp(&right.date)
            .then_with(|| left.id.cmp(&right.id))
    });
    let expense_subtotal_minor = expenses
        .iter()
        .try_fold(0_i64, |total, expense| {
            total.checked_add(expense.billing_amount_minor)
        })
        .unwrap_or_else(|| {
            validation_issues.push(issue("amount-overflow", None, None));
            0
        });
    let total_due_minor = work_subtotal_minor
        .checked_add(expense_subtotal_minor)
        .unwrap_or_else(|| {
            validation_issues.push(issue("amount-overflow", None, None));
            0
        });

    let mut daily_activity = Vec::new();
    if let (Some(mut date), Some(end)) = (start, end) {
        while date <= end {
            let iso = date.iso();
            daily_activity.push(DailyActivityPoint {
                minutes: daily_minutes.get(&iso).copied().unwrap_or(0),
                date: iso,
            });
            date = date.next();
        }
    }
    let total_minutes = daily_minutes
        .values()
        .try_fold(0_i64, |total, minutes| total.checked_add(*minutes))
        .unwrap_or(0);
    let active_days = daily_activity.iter().filter(|day| day.minutes > 0).count();
    let max_minutes = daily_activity
        .iter()
        .map(|day| day.minutes)
        .max()
        .unwrap_or(0);
    let ticks = nice_hour_ticks(max_minutes);
    let upper_bound_hours = ticks.last().copied().unwrap_or(0.0);

    let mut work_category_shares = Vec::new();
    for project in &projects {
        for line in &project.work_lines {
            work_category_shares.push(WorkCategoryShare {
                project_id: project.id.clone(),
                project_name: project.name.clone(),
                line_key: line.key.clone(),
                label: line.label.clone(),
                minutes: line.minutes,
                share: if total_minutes == 0 {
                    0.0
                } else {
                    line.minutes as f64 / total_minutes as f64
                },
            });
        }
    }
    if grouped_minutes.is_empty() && expenses.is_empty() {
        validation_issues.push(issue("empty-invoice", None, None));
    }
    let exportable = validation_issues.is_empty();

    InvoiceDocument {
        sender_name: request.sender_name.clone(),
        recipient_name: source.client.name.clone(),
        issue_date: request.issue_date.clone(),
        invoice_number: request
            .invoice_number
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_owned),
        payment_note: request
            .payment_note_enabled
            .then(|| request.payment_note.trim())
            .filter(|value| !value.is_empty())
            .map(str::to_owned),
        include_daily_activity: request.include_daily_activity,
        include_work_category_breakdown: request.include_work_category_breakdown,
        period_start: request.period_start.clone(),
        period_end: request.period_end.clone(),
        currency_code: source.client.currency_code.clone(),
        projects,
        expenses,
        work_subtotal_minor,
        expense_subtotal_minor,
        total_due_minor,
        total_minutes,
        active_days,
        daily_activity,
        daily_activity_axis: DailyActivityAxis {
            upper_bound_hours,
            ticks,
        },
        work_category_shares,
        validation_issues,
        exportable,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request() -> InvoiceRequest {
        InvoiceRequest {
            client_id: "client-1".into(),
            sender_name: "Acme Studio".into(),
            issue_date: "2026-03-01".into(),
            invoice_number: Some("  INV-2026-001  ".into()),
            period_start: "2026-02-01".into(),
            period_end: "2026-02-03".into(),
            included_expense_ids: None,
            draft_rate_overrides_minor: Default::default(),
            payment_note_enabled: true,
            payment_note: "  Payment due within 14 days.  ".into(),
            include_daily_activity: false,
            include_work_category_breakdown: false,
        }
    }

    fn snapshot() -> InvoiceSourceSnapshot {
        InvoiceSourceSnapshot {
            client: ClientSource {
                id: "client-1".into(),
                name: "Client One".into(),
                currency_code: "EUR".into(),
                hourly_rate_minor: Some(6_001),
            },
            projects: vec![
                ProjectSource {
                    id: "project-1".into(),
                    client_id: "client-1".into(),
                    name: "Current project".into(),
                    hourly_rate_override_minor: Some(7_001),
                    archived: false,
                },
                ProjectSource {
                    id: "project-2".into(),
                    client_id: "client-1".into(),
                    name: "Archived project".into(),
                    hourly_rate_override_minor: None,
                    archived: true,
                },
            ],
            tasks: vec![
                TaskSource {
                    id: "task-1".into(),
                    project_id: "project-1".into(),
                    name: "Design".into(),
                    hourly_rate_override_minor: Some(8_001),
                    archived: false,
                },
                TaskSource {
                    id: "task-2".into(),
                    project_id: "project-2".into(),
                    name: "Retained work".into(),
                    hourly_rate_override_minor: None,
                    archived: true,
                },
            ],
            time_entries: vec![
                TimeEntrySource {
                    date: "2026-01-31".into(),
                    minutes: 999,
                    project_id: "project-1".into(),
                    task_id: Some("task-1".into()),
                },
                TimeEntrySource {
                    date: "2026-02-01".into(),
                    minutes: 30,
                    project_id: "project-1".into(),
                    task_id: Some("task-1".into()),
                },
                TimeEntrySource {
                    date: "2026-02-01".into(),
                    minutes: 30,
                    project_id: "project-1".into(),
                    task_id: Some("task-1".into()),
                },
                TimeEntrySource {
                    date: "2026-02-02".into(),
                    minutes: 60,
                    project_id: "project-1".into(),
                    task_id: None,
                },
                TimeEntrySource {
                    date: "2026-02-03".into(),
                    minutes: 30,
                    project_id: "project-2".into(),
                    task_id: Some("task-2".into()),
                },
                TimeEntrySource {
                    date: "2026-02-04".into(),
                    minutes: 999,
                    project_id: "project-1".into(),
                    task_id: None,
                },
                TimeEntrySource {
                    date: "2026-02-02".into(),
                    minutes: 0,
                    project_id: "project-1".into(),
                    task_id: None,
                },
            ],
            expenses: vec![
                ExpenseSource {
                    id: "expense-1".into(),
                    client_id: Some("client-1".into()),
                    project_id: None,
                    date: "2026-02-01".into(),
                    description: "Train".into(),
                    billing_currency_code: "EUR".into(),
                    billing_amount_minor: 1_000,
                    archived: false,
                },
                ExpenseSource {
                    id: "expense-2".into(),
                    client_id: None,
                    project_id: Some("project-1".into()),
                    date: "2026-02-03".into(),
                    description: "Hotel".into(),
                    billing_currency_code: "EUR".into(),
                    billing_amount_minor: 2_000,
                    archived: false,
                },
                ExpenseSource {
                    id: "expense-archived".into(),
                    client_id: Some("client-1".into()),
                    project_id: None,
                    date: "2026-02-02".into(),
                    description: "Old".into(),
                    billing_currency_code: "EUR".into(),
                    billing_amount_minor: 9_999,
                    archived: true,
                },
            ],
        }
    }

    #[test]
    fn composes_inclusive_grouped_work_with_inherited_rates_and_exact_totals() {
        let document = compose_invoice(&request(), &snapshot());

        assert!(document.validation_issues.is_empty());
        assert_eq!(document.invoice_number.as_deref(), Some("INV-2026-001"));
        assert_eq!(
            document.payment_note.as_deref(),
            Some("Payment due within 14 days.")
        );
        assert!(!document.include_daily_activity);
        assert!(!document.include_work_category_breakdown);
        assert_eq!(document.projects.len(), 2);
        assert_eq!(document.projects[0].name, "Archived project");
        assert_eq!(document.projects[0].work_lines[0].label, "Retained work");
        assert_eq!(document.projects[0].work_lines[0].minutes, 30);
        assert_eq!(document.projects[0].work_lines[0].rate_minor, Some(6_001));
        assert_eq!(document.projects[0].work_lines[0].amount_minor, Some(3_001));
        assert_eq!(document.projects[0].subtotal_minor, 3_001);
        assert_eq!(
            document.projects[1].work_lines[0].label,
            "General project work"
        );
        assert_eq!(document.projects[1].work_lines[0].rate_minor, Some(7_001));
        assert_eq!(document.projects[1].work_lines[0].amount_minor, Some(7_001));
        assert_eq!(document.projects[1].work_lines[1].label, "Design");
        assert_eq!(document.projects[1].work_lines[1].minutes, 60);
        assert_eq!(document.projects[1].work_lines[1].rate_minor, Some(8_001));
        assert_eq!(document.projects[1].subtotal_minor, 15_002);
        assert_eq!(document.work_subtotal_minor, 18_003);
        assert_eq!(document.expense_subtotal_minor, 3_000);
        assert_eq!(document.total_due_minor, 21_003);
    }

    #[test]
    fn applies_draft_rates_without_mutating_sources_and_reports_missing_or_invalid_rates() {
        let mut source = snapshot();
        source.client.hourly_rate_minor = None;
        source.projects[0].hourly_rate_override_minor = None;
        source.tasks[0].hourly_rate_override_minor = None;
        let original = source.clone();
        let mut invoice_request = request();
        invoice_request
            .draft_rate_overrides_minor
            .insert("task:task-1".into(), 12_345);
        invoice_request
            .draft_rate_overrides_minor
            .insert("task:task-2".into(), -1);

        let document = compose_invoice(&invoice_request, &source);

        let design = document
            .projects
            .iter()
            .flat_map(|project| &project.work_lines)
            .find(|line| line.key == "task:task-1")
            .unwrap();
        assert_eq!(design.rate_minor, Some(12_345));
        assert_eq!(design.amount_minor, Some(12_345));
        assert!(document
            .validation_issues
            .iter()
            .any(|issue| issue.code == "invalid-rate"
                && issue.line_key.as_deref() == Some("task:task-2")));
        assert!(document
            .validation_issues
            .iter()
            .any(|issue| issue.code == "missing-rate"
                && issue.line_key.as_deref() == Some("project:project-1:general")));
        assert_eq!(source, original);
    }

    #[test]
    fn validates_all_request_fields_and_rejects_empty_documents() {
        let mut invalid = request();
        invalid.client_id = "other-client".into();
        invalid.sender_name = "   ".into();
        invalid.issue_date = "2026-02-30".into();
        invalid.period_start = "bad".into();
        invalid.period_end = "2026-01-01".into();
        let empty = InvoiceSourceSnapshot {
            time_entries: vec![],
            expenses: vec![],
            ..snapshot()
        };

        let document = compose_invoice(&invalid, &empty);

        let fields: Vec<_> = document
            .validation_issues
            .iter()
            .filter_map(|issue| issue.field.as_deref())
            .collect();
        assert!(fields.contains(&"clientId"));
        assert!(fields.contains(&"senderName"));
        assert!(fields.contains(&"issueDate"));
        assert!(fields.contains(&"periodStart"));
        assert!(document
            .validation_issues
            .iter()
            .any(|issue| issue.code == "empty-invoice"));

        let mut reversed = request();
        reversed.period_start = "2026-02-04".into();
        reversed.period_end = "2026-02-03".into();
        assert!(compose_invoice(&reversed, &snapshot())
            .validation_issues
            .iter()
            .any(|issue| issue.code == "invalid-period"));

        let mut non_canonical = request();
        non_canonical.issue_date = "+026-01-01".into();
        assert!(compose_invoice(&non_canonical, &snapshot())
            .validation_issues
            .iter()
            .any(|issue| issue.field.as_deref() == Some("issueDate")));
    }

    #[test]
    fn selects_eligible_expenses_by_default_and_respects_explicit_selection() {
        let all = compose_invoice(&request(), &snapshot());
        assert_eq!(
            all.expenses
                .iter()
                .map(|expense| expense.id.as_str())
                .collect::<Vec<_>>(),
            vec!["expense-1", "expense-2"]
        );

        let mut selected_request = request();
        selected_request.included_expense_ids = Some(vec!["expense-2".into()]);
        let selected = compose_invoice(&selected_request, &snapshot());
        assert_eq!(selected.expenses.len(), 1);
        assert_eq!(selected.expenses[0].id, "expense-2");
        assert_eq!(selected.expense_subtotal_minor, 2_000);
    }

    #[test]
    fn returns_every_daily_date_active_days_and_deterministic_nice_ticks() {
        let mut source = snapshot();
        source
            .time_entries
            .retain(|entry| entry.date != "2026-02-02");
        let document = compose_invoice(&request(), &source);

        assert_eq!(
            document
                .daily_activity
                .iter()
                .map(|day| (day.date.as_str(), day.minutes))
                .collect::<Vec<_>>(),
            vec![("2026-02-01", 60), ("2026-02-02", 0), ("2026-02-03", 30)]
        );
        assert_eq!(document.active_days, 2);
        assert_eq!(document.total_minutes, 90);
        assert_eq!(nice_hour_ticks(60), vec![0.0, 0.2, 0.4, 0.6, 0.8, 1.0]);
        assert_eq!(
            nice_hour_ticks(12 * 60),
            vec![0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
        );
        assert_eq!(
            nice_hour_ticks(8 * 60),
            vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        );
        assert!(
            document.daily_activity_axis.ticks.len() >= 6
                && document.daily_activity_axis.ticks.len() <= 9
        );
        assert!(document.daily_activity_axis.upper_bound_hours >= 1.0);
    }

    #[test]
    fn omits_blank_or_disabled_payment_notes_completely() {
        let mut invoice_request = request();
        invoice_request.payment_note = "   ".into();
        assert_eq!(
            compose_invoice(&invoice_request, &snapshot()).payment_note,
            None
        );

        invoice_request.payment_note = "Do not render".into();
        invoice_request.payment_note_enabled = false;
        assert_eq!(
            compose_invoice(&invoice_request, &snapshot()).payment_note,
            None
        );
    }
}
