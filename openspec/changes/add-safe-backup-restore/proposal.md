## Why

Personal Timesheet now stores real client data locally, but the user has no
safe way to protect or recover that data. Backup and restore should exist
before projects, time entries, and expenses make the database costly to lose.

## What Changes

- Add a Data section in Settings with explicit “Back up data” and “Restore
  backup” actions.
- Save a transactionally consistent snapshot of the complete local database as
  one user-selected `.ptimesheet-backup` file.
- Validate a selected backup before changing current data and reject damaged or
  incompatible files.
- Restore by replacing all local application data, not merging records.
- Create a recovery copy of the current database before replacement and leave
  current data untouched when preparation or validation fails.
- Restart the application after a successful restore so every catalog reloads
  from one coherent database state.
- Keep automatic schedules, cloud storage, synchronization, encryption,
  selective restore, merge restore, and human-readable data export outside this
  change.

## Capabilities

### New Capabilities

- `local-data-backup`: Manually create, validate, and restore complete local
  database backups without risking the current workspace.

### Modified Capabilities

None.

## Impact

- Adds native file-selection and local file-operation support with narrowly
  scoped Tauri permissions.
- Adds Rust-owned backup creation, validation, staged restoration, and recovery
  behavior around the existing SQLite database.
- Adds the first functional Data controls to the existing Settings workspace.
- Establishes a versioned backup contract that future database migrations must
  remain able to restore or explicitly reject.
