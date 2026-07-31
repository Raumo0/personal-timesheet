## Why

Personal Timesheet needs a first real, durable workspace entity before projects,
tasks, or time entries can be useful. A local client catalog validates the
application's persistence approach while giving the user an immediately useful
place to maintain billing defaults.

## What Changes

- Add a primary Clients destination that is easy to find from anywhere in the
  application.
- Let the user create, view, edit, and archive clients.
- Record each client's name, billing currency, and optional default hourly
  rate; an explicit zero rate remains valid.
- Persist clients in the application's local SQLite database and restore them
  after application restarts.
- Validate form input and persisted rows before they enter the application.
- Show purposeful loading, empty, validation-error, and persistence-error
  states.
- Keep projects, tasks, rate inheritance, backup/restore, synchronization, and
  permanent deletion outside this change.

## Capabilities

### New Capabilities

- `client-catalog`: Manage locally persisted clients and their billing
  defaults, including explicit zero rates and archival.

### Modified Capabilities

- `application-shell`: Add Clients to persistent primary product navigation.

## Impact

- Adds the Tauri SQL plugin, SQLite initialization, and the first versioned
  database migration.
- Adds Zod as the validation dependency at UI and persistence seams.
- Adds a focused client catalog module and Clients product surface in the React
  application.
- Extends Tauri capabilities and Rust plugin initialization for the local
  database.
