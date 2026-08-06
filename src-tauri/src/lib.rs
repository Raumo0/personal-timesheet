// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
pub mod backup;
pub mod catalog_lifecycle;
pub mod client_update;
mod database;
pub mod weekly_time_entry;

use std::path::Path;

use tauri::{AppHandle, Manager};

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

fn backup_service(app: &AppHandle) -> Result<backup::BackupService, String> {
    let config_dir = app
        .path()
        .app_config_dir()
        .map_err(|error| format!("application data directory is unavailable: {error}"))?;

    Ok(backup::BackupService::new(
        backup::BackupPaths::from_config_dir(&config_dir),
    ))
}

#[tauri::command]
async fn create_data_backup(
    app: AppHandle,
    destination: String,
) -> Result<backup::BackupReceipt, String> {
    backup_service(&app)?
        .create_backup(Path::new(&destination))
        .await
        .map_err(|error| error.to_string())
}

#[tauri::command]
async fn stage_restore_backup(
    app: AppHandle,
    source: String,
) -> Result<backup::BackupPreview, String> {
    backup_service(&app)?
        .stage_and_validate(Path::new(&source))
        .await
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn cancel_staged_restore(app: AppHandle) -> Result<(), String> {
    backup_service(&app)?
        .cancel_staged_restore()
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn commit_staged_restore(app: AppHandle) -> Result<(), String> {
    backup_service(&app)?
        .commit_restore()
        .map_err(|error| error.to_string())?;
    app.request_restart();
    Ok(())
}

#[tauri::command]
async fn apply_catalog_lifecycle(
    app: AppHandle,
    plan: catalog_lifecycle::LifecyclePlan,
) -> Result<(), String> {
    let config_dir = app
        .path()
        .app_config_dir()
        .map_err(|error| format!("application data directory is unavailable: {error}"))?;
    catalog_lifecycle::apply_at_path(
        &backup::BackupPaths::from_config_dir(&config_dir).live_database,
        plan,
    )
    .await
}

#[tauri::command]
async fn apply_client_update(
    app: AppHandle,
    plan: client_update::ClientUpdatePlan,
) -> Result<client_update::ClientRecord, String> {
    let config_dir = app
        .path()
        .app_config_dir()
        .map_err(|error| format!("application data directory is unavailable: {error}"))?;
    client_update::apply_at_path(
        &backup::BackupPaths::from_config_dir(&config_dir).live_database,
        plan,
    )
    .await
}

#[tauri::command]
async fn apply_weekly_time_entry_mutation(
    app: AppHandle,
    plan: weekly_time_entry::WeeklyTimeEntryMutationPlan,
) -> Result<(), String> {
    let config_dir = app
        .path()
        .app_config_dir()
        .map_err(|error| format!("application data directory is unavailable: {error}"))?;
    weekly_time_entry::apply_at_path(
        &backup::BackupPaths::from_config_dir(&config_dir).live_database,
        plan,
    )
    .await
}

fn application_context() -> tauri::Context<tauri::Wry> {
    tauri::generate_context!()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_sql::Builder::default()
                .add_migrations(database::DATABASE_URL, database::client_migrations())
                .build(),
        )
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            greet,
            create_data_backup,
            stage_restore_backup,
            cancel_staged_restore,
            commit_staged_restore,
            apply_catalog_lifecycle,
            apply_client_update,
            apply_weekly_time_entry_mutation
        ])
        .on_page_load(|webview, payload| {
            let window = webview.window();
            let visibility_result = match payload.event() {
                tauri::webview::PageLoadEvent::Started => window.hide(),
                tauri::webview::PageLoadEvent::Finished => window.show(),
            };

            if let Err(error) = visibility_result {
                eprintln!("failed to update startup window visibility: {error}");
            }
        })
        .run(application_context())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    #[test]
    fn main_window_starts_hidden_until_its_page_finishes_loading() {
        let context = super::application_context();
        let main_window = context
            .config()
            .app
            .windows
            .iter()
            .find(|window| window.label == "main")
            .expect("main window configuration should exist");

        assert!(!main_window.visible);
    }
}
