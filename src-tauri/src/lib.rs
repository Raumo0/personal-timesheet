// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
pub mod backup;
mod database;

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
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
        .invoke_handler(tauri::generate_handler![greet])
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
