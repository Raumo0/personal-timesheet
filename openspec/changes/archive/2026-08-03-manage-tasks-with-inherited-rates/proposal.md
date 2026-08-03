## Why

Projects can be selected as work, but they cannot yet be divided into durable
tasks. Adding tasks now completes the planned work hierarchy and extends the
existing rate model before weekly time entry depends on it.

## What Changes

- Add durable tasks that belong to exactly one project and, through it, one
  client.
- Let the user open a project's task screen and create, edit, list, and archive
  tasks while retaining client and project context in the route.
- Give every task an explicit billing-rate mode: inherit the project's
  effective hourly rate or override it with a non-negative amount, including
  zero.
- Display each task's effective rate and its task, project, client, or unset
  source.
- Keep the client's billing currency authoritative and rescale project and task
  overrides atomically when that currency changes without losing precision.
- Preserve task records and rate modes across application restarts and include
  the evolved schema in backup compatibility checks.
- Keep tasks beneath archived clients or projects available as read-only
  historical records in this slice; defer cascading archive and targeted
  restore to the follow-up catalog-lifecycle change.
- Defer time entry, nested tasks, manual task ordering, task descriptions,
  moving tasks between projects, and task-specific currencies.

## Capabilities

### New Capabilities

- `task-catalog`: Task maintenance beneath projects, explicit rate inheritance
  or override, effective-rate presentation, archival, navigation, and durable
  local storage.

### Modified Capabilities

- `project-catalog`: Projects provide access to their task screen while
  retaining client and project context, including read-only historical access.
- `client-catalog`: Client currency changes preserve both project and task
  override amounts atomically or reject the complete change.

## Impact

- Adds task domain rules, a small catalog interface with in-memory and SQLite
  adapters, a database migration, task forms, and a task screen.
- Extends project navigation, application routing, client currency updates, and
  backup schema validation.
- Reuses existing client/project rate parsing, formatting, catalog, dialog,
  table, error-state, and archival patterns; no new runtime dependency is
  expected.
