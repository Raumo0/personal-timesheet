## Why

Entering a large real-world catalog, timesheet, and expense history through the UI is slow and error-prone. A local, reviewable import path is needed so structured data prepared from screenshots or source documents can be validated before it touches SQLite.

## What Changes

- Add a versioned JSON manifest for Clients, Projects, Tasks, time entries, and Expenses.
- Add a local CLI that validates the complete manifest and prints a deterministic preview without writing by default.
- Apply a valid manifest to an empty Personal Timesheet database in one transaction only after an explicit apply flag.
- Require an additional explicit acknowledgement when the selected target is production.
- Reuse the application schema and preserve its identifiers, hierarchy, currency, date, duration, rate, and Expense invariants.
- Provide an example manifest and exact commands suitable for data transcribed from screenshots.
- Do not add a network API, remote storage, UI import screen, merge/update semantics, or unattended production writes.

## Capabilities

### New Capabilities

- `timesheet-data-import`: Defines a local preview-first, transactional import of structured Personal Timesheet data.

### Modified Capabilities

None.

## Impact

- Adds a developer-operated Rust CLI, import manifest types, validation, fixtures, and documentation.
- Reuses the existing SQLite migrations and writes only to an explicitly selected development, production, or file-path target.
- Does not change normal application behavior or expose a listening service.
