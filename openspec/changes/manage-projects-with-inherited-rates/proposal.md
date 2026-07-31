## Why

Client defaults cannot yet be assigned to concrete work because the application
has no durable projects. Projects must make rate inheritance visible and
intentional so an inherited value is never mistaken for an editable override.

## What Changes

- Add durable projects that belong to exactly one client.
- Let the user create, edit, list, and archive projects from a client workspace.
- Give every project an explicit billing-rate mode: inherit the client's default
  hourly rate or override it with a non-negative amount, including zero.
- Display the inherited client rate as read-only contextual information and
  identify its source; only an override is directly editable.
- Show the project's effective hourly rate and distinguish a client value, a
  project override, and no available rate.
- Keep the client's billing currency authoritative for all of its projects.
- Preserve projects and their billing configuration across application restarts.
- Defer tasks and task-level inheritance to the immediately following vertical
  slice; this change establishes the same inheritance semantics they will use.
- Defer weekly time entry, invoices, payments, expenses, and import/export.

## Capabilities

### New Capabilities

- `project-catalog`: Project maintenance under clients, explicit rate
  inheritance or override, effective-rate presentation, archival, and durable
  local storage.

### Modified Capabilities

- `client-catalog`: Active clients provide the entry point for viewing and
  maintaining their projects.

## Impact

- Extends the Clients workspace with client-specific project navigation and
  project management UI.
- Adds project domain rules, catalog interfaces, SQLite persistence, and a new
  database migration.
- Extends backup validation for the evolved database schema without changing
  the backup workflow.
- Reuses existing client currency parsing, rate formatting, dialog, table,
  validation, and catalog patterns; no new runtime dependency is expected.
