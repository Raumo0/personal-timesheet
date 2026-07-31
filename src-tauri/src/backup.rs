use std::{
    error::Error,
    fmt, fs,
    path::{Path, PathBuf},
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

#[derive(Debug, Eq, PartialEq)]
pub struct BackupReceipt {
    pub path: PathBuf,
}

#[derive(Debug, Eq, PartialEq)]
pub enum BackupError {
    ProtectedDestination { path: PathBuf },
    DestinationUnavailable { path: PathBuf, reason: String },
    DestinationExists { path: PathBuf },
    SnapshotFailed { reason: String },
    FinalizeFailed { path: PathBuf, reason: String },
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
        }
    }
}

impl Error for BackupError {}

pub struct BackupService {
    paths: BackupPaths,
}

impl BackupService {
    pub fn new(paths: BackupPaths) -> Self {
        Self { paths }
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

fn remove_stale_partial(partial: &Path) -> Result<(), BackupError> {
    if !partial.exists() {
        return Ok(());
    }

    fs::remove_file(partial).map_err(|error| BackupError::DestinationUnavailable {
        path: partial.to_path_buf(),
        reason: error.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use std::{fs, path::Path};

    use sqlx::{sqlite::SqliteConnectOptions, Connection, SqliteConnection};
    use tempfile::TempDir;

    use super::{BackupError, BackupPaths, BackupService};

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
}
