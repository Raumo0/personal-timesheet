use std::{
    error::Error,
    fmt, fs,
    path::{Path, PathBuf},
    sync::Arc,
};

use sqlx::{sqlite::SqliteConnectOptions, Connection, SqliteConnection};

const DATABASE_FILENAME: &str = "personal-timesheet.db";
const PENDING_RESTORE_FILENAME: &str = "personal-timesheet.restore-pending";
const RECOVERY_DATABASE_FILENAME: &str = "personal-timesheet.recovery.db";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BackupPaths {
    pub live_database: PathBuf,
    pub pending_restore: PathBuf,
    pub recovery_database: PathBuf,
}

impl BackupPaths {
    pub fn from_config_dir(config_dir: &Path) -> Self {
        Self {
            live_database: config_dir.join(DATABASE_FILENAME),
            pending_restore: config_dir.join(PENDING_RESTORE_FILENAME),
            recovery_database: config_dir.join(RECOVERY_DATABASE_FILENAME),
        }
    }

    fn protected_paths(&self) -> [&Path; 3] {
        [
            &self.live_database,
            &self.pending_restore,
            &self.recovery_database,
        ]
    }
}

#[derive(Debug, Eq, PartialEq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BackupReceipt {
    pub path: PathBuf,
}

#[derive(Debug, Eq, PartialEq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BackupPreview {
    pub filename: String,
    pub data_version: i64,
    pub client_count: i64,
}

#[derive(Debug, Eq, PartialEq)]
pub enum BackupError {
    ProtectedDestination {
        path: PathBuf,
    },
    DestinationUnavailable {
        path: PathBuf,
        reason: String,
    },
    DestinationExists {
        path: PathBuf,
    },
    SnapshotFailed {
        reason: String,
    },
    FinalizeFailed {
        path: PathBuf,
        reason: String,
    },
    StageFailed {
        path: PathBuf,
        reason: String,
    },
    IntegrityCheckFailed {
        reason: String,
    },
    MissingApplicationSchema,
    UnsupportedNewerVersion {
        backup_version: i64,
        supported_version: i64,
    },
    CommitFailed {
        reason: String,
    },
    RollbackFailed {
        reason: String,
    },
}

impl fmt::Display for BackupError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ProtectedDestination { path } => write!(
                formatter,
                "backup destination is reserved by Personal Timesheet: {}",
                path.display()
            ),
            Self::DestinationUnavailable { path, reason } => write!(
                formatter,
                "backup destination is unavailable ({}): {reason}",
                path.display()
            ),
            Self::DestinationExists { path } => {
                write!(
                    formatter,
                    "backup destination already exists: {}",
                    path.display()
                )
            }
            Self::SnapshotFailed { reason } => {
                write!(
                    formatter,
                    "database snapshot could not be created: {reason}"
                )
            }
            Self::FinalizeFailed { path, reason } => write!(
                formatter,
                "completed snapshot could not be finalized ({}): {reason}",
                path.display()
            ),
            Self::StageFailed { path, reason } => write!(
                formatter,
                "backup could not be staged ({}): {reason}",
                path.display()
            ),
            Self::IntegrityCheckFailed { reason } => {
                write!(formatter, "backup integrity check failed: {reason}")
            }
            Self::MissingApplicationSchema => {
                write!(formatter, "file is not a Personal Timesheet backup")
            }
            Self::UnsupportedNewerVersion {
                backup_version,
                supported_version,
            } => write!(
                formatter,
                "backup data version {backup_version} is newer than supported version {supported_version}"
            ),
            Self::CommitFailed { reason } => {
                write!(formatter, "restore could not be committed: {reason}")
            }
            Self::RollbackFailed { reason } => write!(
                formatter,
                "restore failed and the recovery database could not be reinstated: {reason}"
            ),
        }
    }
}

impl Error for BackupError {}

trait FileOperations: Send + Sync {
    fn rename(&self, from: &Path, to: &Path) -> std::io::Result<()>;
    fn remove_file(&self, path: &Path) -> std::io::Result<()>;
}

struct StandardFileOperations;

impl FileOperations for StandardFileOperations {
    fn rename(&self, from: &Path, to: &Path) -> std::io::Result<()> {
        fs::rename(from, to)
    }

    fn remove_file(&self, path: &Path) -> std::io::Result<()> {
        fs::remove_file(path)
    }
}

pub struct BackupService {
    paths: BackupPaths,
    file_operations: Arc<dyn FileOperations>,
}

impl BackupService {
    pub fn new(paths: BackupPaths) -> Self {
        Self::with_file_operations(paths, Arc::new(StandardFileOperations))
    }

    fn with_file_operations(paths: BackupPaths, file_operations: Arc<dyn FileOperations>) -> Self {
        Self {
            paths,
            file_operations,
        }
    }

    pub async fn create_backup(&self, destination: &Path) -> Result<BackupReceipt, BackupError> {
        let requested_destination = destination.to_path_buf();
        let destination = normalized_destination(destination)?;

        if self.paths.protected_paths().iter().any(|protected| {
            normalized_existing_or_candidate(protected).ok().as_ref() == Some(&destination)
        }) {
            return Err(BackupError::ProtectedDestination { path: destination });
        }

        if destination.exists() {
            return Err(BackupError::DestinationExists { path: destination });
        }

        let partial = partial_path(&destination);
        remove_stale_partial(&partial)?;

        let snapshot_result = self.create_snapshot(&partial).await;
        if let Err(error) = snapshot_result {
            let _ = fs::remove_file(&partial);
            return Err(error);
        }

        if let Err(error) = fs::rename(&partial, &destination) {
            let _ = fs::remove_file(&partial);
            return Err(BackupError::FinalizeFailed {
                path: destination,
                reason: error.to_string(),
            });
        }

        Ok(BackupReceipt {
            path: requested_destination,
        })
    }

    pub async fn stage_and_validate(&self, selected: &Path) -> Result<BackupPreview, BackupError> {
        let filename = selected
            .file_name()
            .map(|name| name.to_string_lossy().into_owned())
            .ok_or_else(|| BackupError::StageFailed {
                path: selected.to_path_buf(),
                reason: "selected path has no filename".to_owned(),
            })?;
        let selected_path = selected
            .canonicalize()
            .map_err(|error| BackupError::StageFailed {
                path: selected.to_path_buf(),
                reason: error.to_string(),
            })?;
        let pending_path =
            normalized_existing_or_candidate(&self.paths.pending_restore).map_err(|error| {
                BackupError::StageFailed {
                    path: self.paths.pending_restore.clone(),
                    reason: error.to_string(),
                }
            })?;

        if selected_path == pending_path {
            return Err(BackupError::StageFailed {
                path: selected.to_path_buf(),
                reason: "selected file is the app-owned pending restore".to_owned(),
            });
        }

        let partial = partial_path(&self.paths.pending_restore);
        remove_staged_file(&partial)?;
        remove_staged_file(&self.paths.pending_restore)?;

        if let Err(error) = fs::copy(&selected_path, &partial) {
            let _ = fs::remove_file(&partial);
            return Err(BackupError::StageFailed {
                path: selected.to_path_buf(),
                reason: error.to_string(),
            });
        }

        if let Err(error) = fs::rename(&partial, &self.paths.pending_restore) {
            let _ = fs::remove_file(&partial);
            return Err(BackupError::StageFailed {
                path: self.paths.pending_restore.clone(),
                reason: error.to_string(),
            });
        }

        match self.validate_staged(filename).await {
            Ok(preview) => Ok(preview),
            Err(error) => {
                let _ = fs::remove_file(&self.paths.pending_restore);
                Err(error)
            }
        }
    }

    pub fn commit_restore(&self) -> Result<(), BackupError> {
        if !self.paths.live_database.is_file() {
            return Err(BackupError::CommitFailed {
                reason: "current database is missing".to_owned(),
            });
        }
        if !self.paths.pending_restore.is_file() {
            return Err(BackupError::CommitFailed {
                reason: "validated pending restore is missing".to_owned(),
            });
        }

        self.remove_if_exists(&self.paths.recovery_database)
            .map_err(|error| BackupError::CommitFailed {
                reason: format!("previous recovery copy could not be removed: {error}"),
            })?;
        self.file_operations
            .rename(&self.paths.live_database, &self.paths.recovery_database)
            .map_err(|error| BackupError::CommitFailed {
                reason: format!("current database could not be preserved: {error}"),
            })?;

        if let Err(error) = self
            .file_operations
            .rename(&self.paths.pending_restore, &self.paths.live_database)
        {
            return self.rollback_before_replacement(format!(
                "validated backup could not replace the current database: {error}"
            ));
        }

        if let Err(error) = self.remove_live_sidecars() {
            return self.rollback_after_replacement(format!(
                "obsolete SQLite sidecars could not be removed: {error}"
            ));
        }

        Ok(())
    }

    pub fn cancel_staged_restore(&self) -> Result<(), BackupError> {
        remove_staged_file(&partial_path(&self.paths.pending_restore))?;
        remove_staged_file(&self.paths.pending_restore)
    }

    async fn create_snapshot(&self, partial: &Path) -> Result<(), BackupError> {
        let options = SqliteConnectOptions::new()
            .filename(&self.paths.live_database)
            .create_if_missing(false);
        let mut connection = SqliteConnection::connect_with(&options)
            .await
            .map_err(|error| BackupError::SnapshotFailed {
                reason: error.to_string(),
            })?;

        sqlx::query("VACUUM INTO ?")
            .bind(partial.to_string_lossy().as_ref())
            .execute(&mut connection)
            .await
            .map_err(|error| BackupError::SnapshotFailed {
                reason: error.to_string(),
            })?;

        connection
            .close()
            .await
            .map_err(|error| BackupError::SnapshotFailed {
                reason: error.to_string(),
            })
    }

    async fn validate_staged(&self, filename: String) -> Result<BackupPreview, BackupError> {
        let options = SqliteConnectOptions::new()
            .filename(&self.paths.pending_restore)
            .read_only(true)
            .create_if_missing(false);
        let mut connection = SqliteConnection::connect_with(&options)
            .await
            .map_err(|error| BackupError::IntegrityCheckFailed {
                reason: error.to_string(),
            })?;

        let integrity_results = sqlx::query_scalar::<_, String>("PRAGMA quick_check")
            .fetch_all(&mut connection)
            .await
            .map_err(|error| BackupError::IntegrityCheckFailed {
                reason: error.to_string(),
            })?;
        if integrity_results.as_slice() != ["ok"] {
            return Err(BackupError::IntegrityCheckFailed {
                reason: integrity_results.join("; "),
            });
        }

        sqlx::query(
            "SELECT version, description, installed_on, success, checksum, execution_time \
             FROM _sqlx_migrations LIMIT 0",
        )
        .fetch_optional(&mut connection)
        .await
        .map_err(|_| BackupError::MissingApplicationSchema)?;

        let data_version = sqlx::query_scalar::<_, Option<i64>>(
            "SELECT MAX(version) FROM _sqlx_migrations WHERE success = TRUE",
        )
        .fetch_one(&mut connection)
        .await
        .map_err(|_| BackupError::MissingApplicationSchema)?
        .ok_or(BackupError::MissingApplicationSchema)?;
        let supported_version = crate::database::client_migrations()
            .iter()
            .map(|migration| migration.version)
            .max()
            .unwrap_or(0);

        if data_version > supported_version {
            return Err(BackupError::UnsupportedNewerVersion {
                backup_version: data_version,
                supported_version,
            });
        }

        sqlx::query(
            "SELECT id, name, normalized_name, currency_code, hourly_rate_minor, \
             created_at, updated_at, archived_at FROM clients LIMIT 0",
        )
        .fetch_optional(&mut connection)
        .await
        .map_err(|_| BackupError::MissingApplicationSchema)?;
        let client_count = sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM clients")
            .fetch_one(&mut connection)
            .await
            .map_err(|_| BackupError::MissingApplicationSchema)?;

        connection
            .close()
            .await
            .map_err(|error| BackupError::IntegrityCheckFailed {
                reason: error.to_string(),
            })?;

        Ok(BackupPreview {
            filename,
            data_version,
            client_count,
        })
    }

    fn remove_if_exists(&self, path: &Path) -> std::io::Result<()> {
        if path.exists() {
            self.file_operations.remove_file(path)
        } else {
            Ok(())
        }
    }

    fn remove_live_sidecars(&self) -> std::io::Result<()> {
        self.remove_if_exists(&sqlite_sidecar(&self.paths.live_database, "-wal"))?;
        self.remove_if_exists(&sqlite_sidecar(&self.paths.live_database, "-shm"))
    }

    fn rollback_before_replacement(&self, reason: String) -> Result<(), BackupError> {
        self.file_operations
            .rename(&self.paths.recovery_database, &self.paths.live_database)
            .map_err(|rollback_error| BackupError::RollbackFailed {
                reason: format!("{reason}; rollback failed: {rollback_error}"),
            })?;

        Err(BackupError::CommitFailed { reason })
    }

    fn rollback_after_replacement(&self, reason: String) -> Result<(), BackupError> {
        self.file_operations
            .rename(&self.paths.live_database, &self.paths.pending_restore)
            .and_then(|_| {
                self.file_operations
                    .rename(&self.paths.recovery_database, &self.paths.live_database)
            })
            .map_err(|rollback_error| BackupError::RollbackFailed {
                reason: format!("{reason}; rollback failed: {rollback_error}"),
            })?;

        Err(BackupError::CommitFailed { reason })
    }
}

fn normalized_destination(path: &Path) -> Result<PathBuf, BackupError> {
    normalized_existing_or_candidate(path).map_err(|error| BackupError::DestinationUnavailable {
        path: path.to_path_buf(),
        reason: error.to_string(),
    })
}

fn normalized_existing_or_candidate(path: &Path) -> std::io::Result<PathBuf> {
    if path.exists() {
        return path.canonicalize();
    }

    let parent = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let filename = path.file_name().ok_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "destination has no filename",
        )
    })?;

    Ok(parent.canonicalize()?.join(filename))
}

fn partial_path(destination: &Path) -> PathBuf {
    let mut filename = destination.file_name().unwrap_or_default().to_os_string();
    filename.push(".partial");
    destination.with_file_name(filename)
}

fn sqlite_sidecar(database: &Path, suffix: &str) -> PathBuf {
    let mut path = database.as_os_str().to_os_string();
    path.push(suffix);
    PathBuf::from(path)
}

fn remove_stale_partial(partial: &Path) -> Result<(), BackupError> {
    if !partial.exists() {
        return Ok(());
    }

    fs::remove_file(partial).map_err(|error| BackupError::DestinationUnavailable {
        path: partial.to_path_buf(),
        reason: error.to_string(),
    })
}

fn remove_staged_file(path: &Path) -> Result<(), BackupError> {
    if !path.exists() {
        return Ok(());
    }

    fs::remove_file(path).map_err(|error| BackupError::StageFailed {
        path: path.to_path_buf(),
        reason: error.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use std::{fs, io, path::Path, sync::Arc};

    use sqlx::{sqlite::SqliteConnectOptions, Connection, SqliteConnection};
    use tempfile::TempDir;

    use super::{BackupError, BackupPaths, BackupPreview, BackupService, FileOperations};

    async fn connect(path: &Path, create: bool) -> SqliteConnection {
        let options = SqliteConnectOptions::new()
            .filename(path)
            .create_if_missing(create);

        SqliteConnection::connect_with(&options)
            .await
            .expect("temporary SQLite database should open")
    }

    fn assert_no_partial_files(directory: &Path) {
        let partials = fs::read_dir(directory)
            .expect("temporary directory should be readable")
            .filter_map(Result::ok)
            .filter(|entry| entry.file_name().to_string_lossy().contains("partial"))
            .collect::<Vec<_>>();

        assert!(partials.is_empty(), "partial backup files remain");
    }

    async fn create_migrations_table(connection: &mut SqliteConnection, version: i64) {
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
        .execute(&mut *connection)
        .await
        .expect("migration table should be created");
        sqlx::query(
            "INSERT INTO _sqlx_migrations \
             (version, description, success, checksum, execution_time) \
             VALUES (?, 'test migration', TRUE, X'00', 1)",
        )
        .bind(version)
        .execute(&mut *connection)
        .await
        .expect("migration row should be inserted");
    }

    async fn create_valid_backup(path: &Path, version: i64, client_names: &[&str]) {
        let mut connection = connect(path, true).await;
        create_migrations_table(&mut connection, version).await;
        sqlx::query(
            r#"
            CREATE TABLE clients (
                id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                currency_code TEXT NOT NULL,
                hourly_rate_minor INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                archived_at TEXT
            )
            "#,
        )
        .execute(&mut connection)
        .await
        .expect("clients table should be created");

        for (index, name) in client_names.iter().enumerate() {
            sqlx::query(
                r#"
                INSERT INTO clients (
                    id, name, normalized_name, currency_code,
                    hourly_rate_minor, created_at, updated_at, archived_at
                ) VALUES (?, ?, ?, 'EUR', NULL, '2026-01-01', '2026-01-01', NULL)
                "#,
            )
            .bind(format!("client-{index}"))
            .bind(name)
            .bind(name.to_lowercase())
            .execute(&mut connection)
            .await
            .expect("client should be inserted");
        }

        connection.close().await.expect("backup should close");
    }

    #[test]
    fn create_produces_a_complete_consistent_snapshot() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should be created");
            let paths = BackupPaths::from_config_dir(directory.path());
            let mut source = connect(&paths.live_database, true).await;
            sqlx::query("PRAGMA journal_mode = WAL")
                .execute(&mut source)
                .await
                .expect("WAL mode should be enabled");
            sqlx::query("CREATE TABLE clients (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
                .execute(&mut source)
                .await
                .expect("clients table should be created");
            sqlx::query("INSERT INTO clients (id, name) VALUES ('client-1', 'Acme')")
                .execute(&mut source)
                .await
                .expect("client should be inserted");

            let destination = directory.path().join("weekly.ptimesheet-backup");
            let receipt = BackupService::new(paths)
                .create_backup(&destination)
                .await
                .expect("backup should succeed");

            assert_eq!(receipt.path, destination);
            let mut snapshot = connect(&destination, false).await;
            let client_name: String =
                sqlx::query_scalar("SELECT name FROM clients WHERE id = 'client-1'")
                    .fetch_one(&mut snapshot)
                    .await
                    .expect("snapshot should contain the committed client");
            let integrity: String = sqlx::query_scalar("PRAGMA quick_check")
                .fetch_one(&mut snapshot)
                .await
                .expect("snapshot integrity should be readable");

            assert_eq!(client_name, "Acme");
            assert_eq!(integrity, "ok");
            assert_no_partial_files(directory.path());
        });
    }

    #[test]
    fn create_rejects_every_protected_application_path() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should be created");
            let paths = BackupPaths::from_config_dir(directory.path());
            let mut source = connect(&paths.live_database, true).await;
            sqlx::query("CREATE TABLE clients (id TEXT PRIMARY KEY)")
                .execute(&mut source)
                .await
                .expect("clients table should be created");
            source.close().await.expect("source should close");
            let service = BackupService::new(paths.clone());

            for protected in [
                paths.live_database,
                paths.pending_restore,
                paths.recovery_database,
            ] {
                let result = service.create_backup(&protected).await;
                assert!(
                    matches!(result, Err(BackupError::ProtectedDestination { .. })),
                    "protected path should be rejected: {}",
                    protected.display()
                );
            }

            assert_no_partial_files(directory.path());
        });
    }

    #[test]
    fn create_reports_an_unavailable_destination_without_touching_source() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should be created");
            let paths = BackupPaths::from_config_dir(directory.path());
            let mut source = connect(&paths.live_database, true).await;
            sqlx::query("CREATE TABLE marker (value TEXT NOT NULL)")
                .execute(&mut source)
                .await
                .expect("marker table should be created");
            sqlx::query("INSERT INTO marker (value) VALUES ('current-data')")
                .execute(&mut source)
                .await
                .expect("marker should be inserted");
            source.close().await.expect("source should close");

            let destination = directory
                .path()
                .join("missing-parent")
                .join("backup.ptimesheet-backup");
            let result = BackupService::new(paths.clone())
                .create_backup(&destination)
                .await;

            assert!(matches!(
                result,
                Err(BackupError::DestinationUnavailable { .. })
            ));
            let mut unchanged = connect(&paths.live_database, false).await;
            let marker: String = sqlx::query_scalar("SELECT value FROM marker")
                .fetch_one(&mut unchanged)
                .await
                .expect("source data should remain readable");
            assert_eq!(marker, "current-data");
            assert_no_partial_files(directory.path());
        });
    }

    #[test]
    fn create_cleans_up_partial_output_when_snapshot_fails() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should be created");
            let paths = BackupPaths::from_config_dir(directory.path());
            fs::write(&paths.live_database, b"not a sqlite database")
                .expect("invalid source should be written");
            let destination = directory.path().join("broken.ptimesheet-backup");

            let result = BackupService::new(paths).create_backup(&destination).await;

            assert!(matches!(result, Err(BackupError::SnapshotFailed { .. })));
            assert!(!destination.exists());
            assert_no_partial_files(directory.path());
        });
    }

    #[test]
    fn validate_stages_an_intact_backup_and_returns_safe_preview_metadata() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should be created");
            let paths = BackupPaths::from_config_dir(directory.path());
            let selected = directory.path().join("restorable.ptimesheet-backup");
            create_valid_backup(&selected, 1, &["Acme", "Globex"]).await;

            let preview = BackupService::new(paths.clone())
                .stage_and_validate(&selected)
                .await
                .expect("compatible backup should be staged");

            assert_eq!(
                preview,
                BackupPreview {
                    filename: "restorable.ptimesheet-backup".to_owned(),
                    data_version: 1,
                    client_count: 2,
                }
            );
            assert!(paths.pending_restore.exists());

            fs::remove_file(&selected).expect("selected source should be removable after staging");
            let mut staged = connect(&paths.pending_restore, false).await;
            let staged_clients: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM clients")
                .fetch_one(&mut staged)
                .await
                .expect("staged copy should remain independently readable");
            assert_eq!(staged_clients, 2);
        });
    }

    #[test]
    fn validate_rejects_damaged_sqlite_and_removes_the_staged_file() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should be created");
            let paths = BackupPaths::from_config_dir(directory.path());
            let selected = directory.path().join("damaged.ptimesheet-backup");
            fs::write(&selected, b"this is not sqlite").expect("damaged backup should be written");

            let result = BackupService::new(paths.clone())
                .stage_and_validate(&selected)
                .await;

            assert!(matches!(
                result,
                Err(BackupError::IntegrityCheckFailed { .. })
            ));
            assert!(!paths.pending_restore.exists());
        });
    }

    #[test]
    fn validate_rejects_a_database_without_personal_timesheet_schema() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should be created");
            let paths = BackupPaths::from_config_dir(directory.path());
            let selected = directory.path().join("unrelated.ptimesheet-backup");
            let mut unrelated = connect(&selected, true).await;
            create_migrations_table(&mut unrelated, 1).await;
            sqlx::query("CREATE TABLE unrelated_records (id TEXT PRIMARY KEY)")
                .execute(&mut unrelated)
                .await
                .expect("unrelated table should be created");
            unrelated.close().await.expect("database should close");

            let result = BackupService::new(paths.clone())
                .stage_and_validate(&selected)
                .await;

            assert!(matches!(result, Err(BackupError::MissingApplicationSchema)));
            assert!(!paths.pending_restore.exists());
        });
    }

    #[test]
    fn validate_rejects_a_backup_from_a_newer_application_version() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should be created");
            let paths = BackupPaths::from_config_dir(directory.path());
            let selected = directory.path().join("future.ptimesheet-backup");
            create_valid_backup(&selected, 2, &["Future client"]).await;

            let result = BackupService::new(paths.clone())
                .stage_and_validate(&selected)
                .await;

            assert!(matches!(
                result,
                Err(BackupError::UnsupportedNewerVersion {
                    backup_version: 2,
                    supported_version: 1,
                })
            ));
            assert!(!paths.pending_restore.exists());
        });
    }

    #[test]
    fn commit_replaces_the_live_database_and_preserves_a_recovery_copy() {
        tauri::async_runtime::block_on(async {
            let directory = TempDir::new().expect("temporary directory should be created");
            let paths = BackupPaths::from_config_dir(directory.path());
            let mut live = connect(&paths.live_database, true).await;
            sqlx::query("CREATE TABLE marker (value TEXT NOT NULL)")
                .execute(&mut live)
                .await
                .expect("live marker table should be created");
            sqlx::query("INSERT INTO marker (value) VALUES ('current workspace')")
                .execute(&mut live)
                .await
                .expect("live marker should be inserted");
            live.close().await.expect("live database should close");
            create_valid_backup(&paths.pending_restore, 1, &["Restored client"]).await;

            BackupService::new(paths.clone())
                .commit_restore()
                .expect("restore should commit");

            let mut restored = connect(&paths.live_database, false).await;
            let restored_name: String = sqlx::query_scalar("SELECT name FROM clients")
                .fetch_one(&mut restored)
                .await
                .expect("restored client should be readable");
            let mut recovery = connect(&paths.recovery_database, false).await;
            let recovery_marker: String = sqlx::query_scalar("SELECT value FROM marker")
                .fetch_one(&mut recovery)
                .await
                .expect("recovery should contain previous workspace");

            assert_eq!(restored_name, "Restored client");
            assert_eq!(recovery_marker, "current workspace");
            assert!(!paths.pending_restore.exists());
        });
    }

    #[test]
    fn commit_removes_obsolete_live_database_sidecars() {
        let directory = TempDir::new().expect("temporary directory should be created");
        let paths = BackupPaths::from_config_dir(directory.path());
        fs::write(&paths.live_database, b"current").expect("live database should be written");
        fs::write(&paths.pending_restore, b"restored").expect("pending database should be written");
        let wal = directory.path().join("personal-timesheet.db-wal");
        let shared_memory = directory.path().join("personal-timesheet.db-shm");
        fs::write(&wal, b"obsolete wal").expect("WAL sidecar should be written");
        fs::write(&shared_memory, b"obsolete shm").expect("SHM sidecar should be written");

        BackupService::new(paths.clone())
            .commit_restore()
            .expect("restore should commit");

        assert_eq!(
            fs::read(&paths.live_database).expect("restored database should be readable"),
            b"restored"
        );
        assert!(!wal.exists());
        assert!(!shared_memory.exists());
    }

    struct FailPendingReplacement {
        pending: std::path::PathBuf,
        live: std::path::PathBuf,
    }

    impl FileOperations for FailPendingReplacement {
        fn rename(&self, from: &Path, to: &Path) -> io::Result<()> {
            if from == self.pending && to == self.live {
                return Err(io::Error::new(
                    io::ErrorKind::PermissionDenied,
                    "simulated replacement failure",
                ));
            }

            fs::rename(from, to)
        }

        fn remove_file(&self, path: &Path) -> io::Result<()> {
            fs::remove_file(path)
        }
    }

    #[test]
    fn commit_rolls_back_to_current_data_when_replacement_fails() {
        let directory = TempDir::new().expect("temporary directory should be created");
        let paths = BackupPaths::from_config_dir(directory.path());
        fs::write(&paths.live_database, b"current workspace")
            .expect("live database should be written");
        fs::write(&paths.pending_restore, b"staged restore")
            .expect("pending database should be written");
        let operations = Arc::new(FailPendingReplacement {
            pending: paths.pending_restore.clone(),
            live: paths.live_database.clone(),
        });

        let result =
            BackupService::with_file_operations(paths.clone(), operations).commit_restore();

        assert!(matches!(result, Err(BackupError::CommitFailed { .. })));
        assert_eq!(
            fs::read(&paths.live_database).expect("current database should be restored"),
            b"current workspace"
        );
        assert_eq!(
            fs::read(&paths.pending_restore).expect("staged restore should remain retryable"),
            b"staged restore"
        );
        assert!(!paths.recovery_database.exists());
    }

    #[test]
    fn command_preview_serializes_with_the_frontend_contract() {
        let preview = BackupPreview {
            filename: "july.ptimesheet-backup".to_owned(),
            data_version: 1,
            client_count: 7,
        };

        let value = serde_json::to_value(preview).expect("preview should serialize");

        assert_eq!(
            value,
            serde_json::json!({
                "filename": "july.ptimesheet-backup",
                "dataVersion": 1,
                "clientCount": 7
            })
        );
    }

    #[test]
    fn command_cancel_removes_only_the_pending_restore() {
        let directory = TempDir::new().expect("temporary directory should be created");
        let paths = BackupPaths::from_config_dir(directory.path());
        fs::write(&paths.live_database, b"current").expect("live database should be written");
        fs::write(&paths.pending_restore, b"pending").expect("pending restore should be written");

        BackupService::new(paths.clone())
            .cancel_staged_restore()
            .expect("cancel should succeed");

        assert!(paths.live_database.exists());
        assert!(!paths.pending_restore.exists());
    }
}
