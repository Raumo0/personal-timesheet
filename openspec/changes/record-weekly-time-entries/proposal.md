## Why

The application has a Timesheet destination but no way to record time. The
first usable time-tracking slice should let a local user complete the current or
past week without loading every catalog item or losing confidence in whether an
edit was saved.

## What Changes

- Show a Monday–Sunday weekly Timesheet based on the user's local date, with
  Previous, Current, and Next navigation.
- Let the user add one row per selected Project or Task from a Client → Project
  → Task selector that includes only fully active hierarchy paths.
- Accept daily durations in `H:MM`, store positive integer minutes locally, and
  render absent entries as blank cells.
- Autosave valid edits on Enter or blur, retain invalid or failed drafts, expose
  a persistent save state with Retry, and guard navigation or close while
  unsaved changes remain.
- Confirm before deleting an existing nonzero entry by replacing it with blank
  or `0:00`, and reject changes that would exceed `24:00` for one day.
- Calculate each row total, each day total, and the weekly grand total.
- Restore rows from saved entries rather than persisting empty row selections;
  repeated selection focuses the existing row.
- Keep rows linked to archived hierarchy visible as `No longer active` and
  read-only, with `Restore to edit` using the catalog lifecycle operation.
- Defer timer tracking, entry notes, week copying, billable values, reports,
  invoices, period locking, and automatically generated General Tasks.

## Capabilities

### New Capabilities

- `weekly-time-entry`: Local-week navigation, hierarchical work selection,
  duration entry, persistence, totals, save feedback, deletion, and archived
  hierarchy behavior.

### Modified Capabilities

None.

## Impact

- Replaces the Timesheet placeholder with a dense weekly table and focused
  domain, persistence, selector, cell, navigation, and save-state modules.
- Adds an additive SQLite time-entry migration and extends backup compatibility.
- Extends `src/App.tsx` and `src/app/AppShell.tsx` to inject the weekly store and
  existing catalog lifecycle seam; no new runtime dependency is expected.
- Depends on `manage-tasks-with-inherited-rates` and
  `manage-catalog-archive-lifecycle` being implemented first.
