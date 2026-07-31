## Context

The application stores its first durable records in
`sqlite:personal-timesheet.db`, located by the Tauri SQL plugin under the app
configuration directory. Migrations are Rust-owned, while the React catalog
loads and mutates the database through the plugin. See `proposal.md` for the
motivation and `specs/local-data-backup/spec.md` for observable behavior.

Backup and restore cross the native file picker, filesystem, SQLite connection
lifecycle, application restart, and Settings UI. A database replacement must
not occur while the plugin still has live connections.

## Goals / Non-Goals

**Goals:**

- Produce one consistent SQLite snapshot that automatically contains every
  current application table.
- Validate and stage a restore before closing the active database.
- Make the final database replacement rollback-safe and restart into one
  coherent state.
- Keep native path access and destructive file operations behind a small Rust
  command surface that is testable with temporary directories.

**Non-Goals:**

- Treat the backup as a human-readable interchange or reporting format.
- Merge records, restore selected tables, or synchronize multiple devices.
- Encrypt backup files or manage encryption keys.
- Schedule or retain a history of automatic backups.

## Decisions

### Use a SQLite snapshot with a product-specific extension

The backup is a normal SQLite database saved as `.ptimesheet-backup`. Create it
with SQLite `VACUUM INTO` through a dedicated native database connection, first
at a temporary destination and only expose the final filename after completion.
This produces a consistent single-file snapshot while the application remains
usable and automatically includes future tables.

A logical JSON export was rejected for backup because every new table,
relationship, and exact data type would require parallel serialization and
restore logic. JSON/CSV remains appropriate for the separately planned data
export capability.

### Keep orchestration in a deep Rust backup service

Add one native module that owns live-database path resolution, protected paths,
snapshot creation, validation, staging, replacement, recovery, and error
translation. Tauri commands expose only coarse operations such as create,
validate/stage, and commit. React never receives the internal database path and
cannot issue arbitrary filesystem operations.

Use the official dialog plugin only for user-selected source and destination
paths. Do not grant broad frontend filesystem permissions; Rust commands act
only on paths returned for the current operation and explicitly reject the live
database, pending-restore, and recovery paths as user destinations.

### Validate integrity and migration compatibility before confirmation

Copy the chosen restore source into an app-owned pending file, open that copy
read-only, run SQLite `PRAGMA quick_check`, verify the expected migration table
and application schema, and compare its latest successful migration with the
latest migration embedded in the application. A backup with a newer migration
is rejected. An older compatible backup is allowed because the normal plugin
migrations will advance it after restart.

Validation always uses the staged copy rather than trusting a user-controlled
file that could change between preview and confirmation. The returned preview
contains safe summary information only, initially the backup filename, data
version, and client count.

### Close the plugin connection only after restore is fully staged

The Settings workflow first stages and validates the backup while the current
database remains open. After explicit confirmation it checkpoints SQLite,
closes the named frontend database connection through the existing SQL plugin,
and invokes the native commit command.

The commit command moves the live database to one app-owned recovery path,
atomically moves the pending database into the live path, removes obsolete WAL
and shared-memory sidecars, and requests an application relaunch. If the second
move fails, it restores the recovery file before returning an error. Keeping
one latest recovery copy is deliberate; a user-facing recovery-history manager
is outside this slice.

### Restart after successful replacement

Do not attempt to refresh individual React catalogs after replacing the whole
database. Relaunching creates a fresh SQL plugin pool, applies pending
migrations, and ensures every later feature reads the same restored state.

### Add a restrained Data section to Settings

Replace the Settings placeholder with a data-protection panel containing a
short status explanation and two explicit actions: “Back up data” and “Restore
backup.” Backup is the primary safe action. Restore uses a preview and a
destructive confirmation that names the selected file and states that all
current data will be replaced. Loading, success, cancellation, and recoverable
errors remain local to this page.

## Risks / Trade-offs

- **A destination disappears or fills during backup** → Write to a temporary
  file, finalize only after SQLite succeeds, and clean up partial artifacts.
- **A selected file changes after validation** → Restore only the app-owned
  staged copy created during validation.
- **The active database still has WAL state during replacement** → Checkpoint
  and close the SQL plugin connection before committing the swap.
- **The process stops between replacement and relaunch** → The new database is
  already at the canonical path and the previous database remains as the
  recovery copy.
- **A future migration cannot read an older backup** → Preserve the recovery
  copy and surface the migration failure; future migration changes must include
  restore compatibility tests.
- **The backup exposes private billing data** → State clearly that the file is
  local but unencrypted and let the user choose its storage location.

## Migration Plan

1. Add narrowly scoped dialog capability and native dependencies for SQLite
   snapshot/validation plus application relaunch.
2. Add the native backup service and commands without changing the existing
   database schema.
3. Add Settings UI and inject a test backup service for browser-level tests.
4. Verify backup and restore against temporary databases, then manually verify
   a native round trip and recovery rollback.

Rollback removes the UI and native commands. Existing `.ptimesheet-backup`
files remain ordinary SQLite snapshots and no live database migration needs to
be reverted.
