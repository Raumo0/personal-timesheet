## Why

The frontend currently attempts a multi-step Client currency update with
`BEGIN`, reads, descendant updates, and `COMMIT` through `plugin-sql`. Each
plugin call executes against a connection pool, so the sequence is not bound to
one SQLite connection and cannot guarantee the atomic behavior already required
by the Client catalog.

## What Changes

- Make the general frontend SQLite facade read-only and keep direct
  `@tauri-apps/plugin-sql` imports inside one approved infrastructure adapter.
- Keep `plugin-sql` available for simple reads, database maintenance, and
  independent single-statement writes through a separate restricted executor.
- Reject frontend transaction-control statements and multi-statement execution
  through an automated import and SQL boundary check.
- Move the multi-step Client update, including currency rescaling across Project
  and Task overrides, behind one named Rust command that owns one connection,
  one explicit SQL transaction, stale-state validation, commit, and rollback.
- Add real SQLite Rust integration coverage for successful commit, intermediate
  failure rollback, and stale-plan atomicity. Retain the existing native catalog
  lifecycle command as the established transaction-boundary precedent.
- Defer converting every independent Client, Project, or Task CRUD statement to
  Rust, removing `plugin-sql`, exposing a generic SQL batch command, database
  schema changes, and user-interface changes.
- Require planned weekly-time, Expense, and recurring-Expense multi-step writes
  to be reconciled with this boundary before those separate changes are
  implemented; do not implement those features in this change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `client-catalog`: A failed Client currency update leaves the Client and every
  descendant rate override at their previously saved values.

## Impact

- Replaces the write-capable frontend database facade with separate read and
  restricted single-statement capabilities.
- Changes the SQLite Client catalog adapter and its tests from simulated
  frontend transaction calls to a typed native-command seam.
- Adds one focused Rust Client-update module, registers one Tauri command, and
  adds temp-database integration tests without a migration or new runtime
  dependency.
- Adds a repository boundary checker and focused tests using the existing
  TypeScript and Python toolchains.
- Establishes an implementation dependency for `record-weekly-time-entries`,
  `record-project-expenses`, and `schedule-recurring-expenses`; their planning
  artifacts remain owned by their respective changes.
