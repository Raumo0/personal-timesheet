use std::{
    env, fs,
    path::{Path, PathBuf},
    process::ExitCode,
    time::{SystemTime, UNIX_EPOCH},
};

use personal_timesheet_lib::data_import::{
    apply_manifest, inspect_target, parse_and_validate_manifest, resolve_target, ApplyError,
    HostPlatform, ManifestSummary, ResolvedTargetKind, TargetIssue, TargetPathEnvironment,
    TargetSelection,
};
use serde_json::json;

struct Arguments {
    manifest: PathBuf,
    target: TargetSelection,
    apply: bool,
    production_acknowledgement: Option<String>,
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err((code, message)) => {
            eprintln!("{message}");
            ExitCode::from(code)
        }
    }
}

fn run() -> Result<(), (u8, String)> {
    let arguments = parse_arguments(env::args().skip(1))?;
    let initial_source = read_manifest(&arguments.manifest)?;
    let initial_digest = manifest_digest(&initial_source);
    let manifest = parse_and_validate_manifest(&initial_source)
        .map_err(|errors| (3, serde_json::to_string(&errors_json(errors)).unwrap()))?;

    let home = env::var_os("HOME").map(PathBuf::from);
    let app_data = env::var_os("APPDATA").map(PathBuf::from);
    let xdg_config_home = env::var_os("XDG_CONFIG_HOME").map(PathBuf::from);
    let target = resolve_target(
        arguments.target,
        host_platform(),
        TargetPathEnvironment {
            home: home.as_deref(),
            app_data: app_data.as_deref(),
            xdg_config_home: xdg_config_home.as_deref(),
        },
    )
    .map_err(|error| (2, error))?;
    let inspection = tauri::async_runtime::block_on(inspect_target(target.path()));
    println!(
        "{}",
        serde_json::to_string(&preview_json(
            &initial_digest,
            &manifest.summary,
            &target,
            &inspection
        ))
        .unwrap()
    );

    if !arguments.apply {
        return Ok(());
    }
    if let Some(issue) = inspection.issue {
        return Err((4, issue_code(&issue).to_owned()));
    }

    let apply_source = read_manifest(&arguments.manifest)?;
    if manifest_digest(&apply_source) != initial_digest {
        return Err((4, "manifest-changed-after-preview".to_owned()));
    }
    let apply_manifest_value = parse_and_validate_manifest(&apply_source)
        .map_err(|errors| (3, serde_json::to_string(&errors_json(errors)).unwrap()))?;
    let applied_at = current_utc_timestamp()?;
    let receipt = tauri::async_runtime::block_on(apply_manifest(
        &target,
        arguments.production_acknowledgement.as_deref(),
        apply_manifest_value,
        &applied_at,
    ))
    .map_err(|error| (4, apply_error_code(&error)))?;
    println!(
        "{}",
        serde_json::to_string(&json!({
            "expenseTotalsByBillingCurrency": receipt.expense_totals_by_billing_currency,
            "operation": "apply",
            "recordCounts": receipt.record_counts,
            "totalMinutes": receipt.total_minutes,
        }))
        .unwrap()
    );
    Ok(())
}

fn parse_arguments(arguments: impl Iterator<Item = String>) -> Result<Arguments, (u8, String)> {
    let mut manifest = None;
    let mut target = None;
    let mut apply = false;
    let mut production_acknowledgement = None;
    let mut arguments = arguments.peekable();
    while let Some(argument) = arguments.next() {
        match argument.as_str() {
            "--manifest" => manifest = Some(required_value(&mut arguments, "--manifest")?.into()),
            "--database" => {
                set_target(
                    &mut target,
                    TargetSelection::Path(required_value(&mut arguments, "--database")?.into()),
                )?;
            }
            "--development" => set_target(&mut target, TargetSelection::Development)?,
            "--production" => set_target(&mut target, TargetSelection::Production)?,
            "--apply" => apply = true,
            "--acknowledge-production" => {
                production_acknowledgement =
                    Some(required_value(&mut arguments, "--acknowledge-production")?);
            }
            "--help" | "-h" => return Err((0, usage().to_owned())),
            unknown => return Err((2, format!("unknown argument: {unknown}\n{}", usage()))),
        }
    }
    Ok(Arguments {
        manifest: manifest.ok_or_else(|| (2, format!("--manifest is required\n{}", usage())))?,
        target: target.ok_or_else(|| {
            (
                2,
                format!(
                    "one of --development, --production, or --database is required\n{}",
                    usage()
                ),
            )
        })?,
        apply,
        production_acknowledgement,
    })
}

fn required_value(
    arguments: &mut impl Iterator<Item = String>,
    option: &str,
) -> Result<String, (u8, String)> {
    arguments
        .next()
        .ok_or_else(|| (2, format!("{option} requires a value")))
}

fn set_target(
    target: &mut Option<TargetSelection>,
    selection: TargetSelection,
) -> Result<(), (u8, String)> {
    if target.is_some() {
        return Err((2, "select exactly one target".to_owned()));
    }
    *target = Some(selection);
    Ok(())
}

fn usage() -> &'static str {
    "Usage: import-timesheet-data --manifest FILE (--development|--production|--database FILE) [--apply] [--acknowledge-production com.personal.timesheet]"
}

fn read_manifest(path: &Path) -> Result<String, (u8, String)> {
    fs::read_to_string(path).map_err(|error| {
        (
            3,
            format!("manifest-unavailable: {}: {error}", path.display()),
        )
    })
}

fn manifest_digest(source: &str) -> String {
    let checksum = sqlx::migrate::Migration::new(
        0,
        "import manifest".into(),
        sqlx::migrate::MigrationType::Simple,
        source.to_owned().into(),
        false,
    )
    .checksum;
    format!("sha384:{}", hex(checksum.as_ref()))
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn preview_json(
    digest: &str,
    summary: &ManifestSummary,
    target: &personal_timesheet_lib::data_import::ResolvedTarget,
    inspection: &personal_timesheet_lib::data_import::TargetInspection,
) -> serde_json::Value {
    json!({
        "counts": {
            "clients": summary.clients,
            "expenses": summary.expenses,
            "projects": summary.projects,
            "tasks": summary.tasks,
            "timeEntries": summary.time_entries,
        },
        "eligible": inspection.issue.is_none(),
        "expenseTotalsByBillingCurrency": summary.expense_totals_by_billing_currency,
        "manifestDigest": digest,
        "operation": "preview",
        "target": target.path().to_string_lossy(),
        "targetIssue": inspection.issue.as_ref().map(issue_code),
        "targetKind": match target.kind() {
            ResolvedTargetKind::Production => "production",
            ResolvedTargetKind::Development => "development",
            ResolvedTargetKind::Explicit => "explicit",
        },
        "totalMinutes": summary.total_minutes,
    })
}

fn errors_json(
    errors: Vec<personal_timesheet_lib::data_import::ManifestValidationError>,
) -> serde_json::Value {
    json!({
        "errors": errors.into_iter().map(|error| json!({
            "code": error.code,
            "path": error.path,
        })).collect::<Vec<_>>()
    })
}

fn issue_code(issue: &TargetIssue) -> &'static str {
    match issue {
        TargetIssue::Missing => "missing",
        TargetIssue::ActiveUse => "active-use",
        TargetIssue::IncompatibleSchema => "incompatible-schema",
        TargetIssue::NonEmpty => "non-empty",
        TargetIssue::ProductionAcknowledgementRequired => "production-acknowledgement-required",
    }
}

fn apply_error_code(error: &ApplyError) -> String {
    match error {
        ApplyError::Ineligible(issue) => issue_code(issue).to_owned(),
        ApplyError::InvalidTimestamp => "invalid-apply-timestamp".to_owned(),
        ApplyError::Persistence(reason) => format!("persistence: {reason}"),
        ApplyError::VerificationFailed => "post-write-verification-failed".to_owned(),
    }
}

fn host_platform() -> HostPlatform {
    #[cfg(target_os = "macos")]
    return HostPlatform::Macos;
    #[cfg(target_os = "windows")]
    return HostPlatform::Windows;
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    HostPlatform::Linux
}

fn current_utc_timestamp() -> Result<String, (u8, String)> {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| (4, format!("system-clock-unavailable: {error}")))?
        .as_secs();
    let days =
        i64::try_from(seconds / 86_400).map_err(|_| (4, "system-clock-out-of-range".to_owned()))?;
    let seconds_of_day = seconds % 86_400;
    let (year, month, day) = civil_date(days);
    Ok(format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        seconds_of_day / 3_600,
        (seconds_of_day % 3_600) / 60,
        seconds_of_day % 60
    ))
}

fn civil_date(days_since_epoch: i64) -> (i64, i64, i64) {
    let shifted = days_since_epoch + 719_468;
    let era = if shifted >= 0 {
        shifted
    } else {
        shifted - 146_096
    } / 146_097;
    let day_of_era = shifted - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let mut year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_piece = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_piece + 2) / 5 + 1;
    let month = month_piece + if month_piece < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    (year, month, day)
}
