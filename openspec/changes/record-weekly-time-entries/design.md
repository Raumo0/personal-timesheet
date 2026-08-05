## Context

The shell already reserves `/` for a compact Timesheet surface but currently
renders a placeholder. Client, Project, and planned Task records use durable IDs
and `archived_at`; `manage-catalog-archive-lifecycle` establishes the active-path
and targeted-restore contract. Raw frontend SQLite access is read-only by
default; multi-step writes use named Rust commands that own one live connection
and transaction. Additive migrations remain the persistence model. See
`proposal.md` and
`specs/weekly-time-entry/spec.md` for the approved behavior.

## Goals / Non-Goals

**Goals:**

- Keep local calendar calculations, duration rules, row identity, and totals in
  pure testable domain functions.
- Give weekly loading, eligible-work lookup, atomic save/delete, and hierarchy
  status one small persistence interface.
- Make autosave state explicit at both cell and page level without a global Save
  button.
- Fit a keyboard-friendly data grid into the shell's established compact desktop
  workspace and visual identity.

**Non-Goals:**

- Snapshot billing rates or names into time entries.
- Build a generic spreadsheet engine, form framework, or remote sync layer.
- Add a new date, state-management, table, or notification dependency.
- Change the shell density, sidebar, catalog lifecycle policy, or backup UX.

## Decisions

### Model weeks and entry dates as local date-only values

Add pure local-date helpers that derive Monday from the user's local calendar
year, month, and day and move weeks in seven-day increments without converting
the date through UTC. The domain uses validated `YYYY-MM-DD` values for the
seven stored dates and receives `Date` only at the UI boundary for Current.

Using UTC timestamps for entry dates was rejected because midnight conversion
can move a local Sunday or Monday into another date. Adding a date library was
rejected because Monday derivation and date-only arithmetic are bounded here.

### Use a discriminated Project-or-Task work reference

Represent row identity as either `{ kind: "project", projectId }` or
`{ kind: "task", taskId }`; stable keys include the kind so a direct Project row
and one of its Task rows remain distinct. A weekly snapshot joins current Client,
Project, and optional Task names plus lifecycle states. It reconstructs rows only
from saved entries, while newly selected empty rows stay in page state.

A synthetic General Task was rejected because direct Project work is an explicit
domain choice. Persisting a separate weekly-row table was rejected because it
would retain empty presentation state as business data.

### Store only positive minute entries in migration 5

Migration 5 adds `time_entries` with an ID, local `entry_date`, positive
`duration_minutes` up to 1440, timestamps, and exactly one nullable foreign key:
`project_id` for direct Project work or `task_id` for Task work. Partial unique
indexes enforce one direct-Project or Task entry per date. Blank and `0:00`
delete the row, so zero is never persisted.

The TypeScript store builds an immutable mutation plan from read-only queries.
A named Rust command rechecks that the selected hierarchy is fully active and
calculates the complete date total in the same transaction as each upsert or
delete. A write that would
exceed 1440 minutes or race with archival changes nothing. Task hierarchy and
labels are resolved by joining the catalog rather than duplicating `project_id`,
Client IDs, names, or archive markers in `time_entries`.

Storing decimal hours was rejected because duration precision is minute-based.
Storing both Project and Task IDs was rejected because it permits mismatched
pairs and duplicates hierarchy already owned by Task.

### Give weekly persistence one deep store interface

Add `WeeklyTimeEntryStore` with operations to load one Monday–Sunday snapshot,
list selectable active work as a grouped hierarchy, upsert a positive duration,
and delete an entry. In-memory and SQLite adapters share one behavioral
contract. The snapshot returns saved entries even when their hierarchy is
archived, plus enough current state to render those rows read-only.

The SQLite adapter uses `SqlReadDatabase` for bounded queries and invokes only a
named `apply_weekly_time_entry_mutation` command for writes. The command accepts
a typed expected-state plan rather than SQL, rechecks it in Rust, and returns the
saved result or a stable stale-plan/persistence error. A frontend transaction or
the independent-statement executor is not an allowed implementation.

Composing every Client/Project/Task list in the page was rejected because it
would create route-level N+1 queries and duplicate eligibility joins. Folding
time entry into an existing catalog was rejected because dated duration
persistence is a separate responsibility.

### Serialize autosaves and derive one visible page status

Each cell tracks its saved minutes, draft text, validation result, and pending or
failed write. Valid Enter/blur commits are serialized so daily-limit checks and
later edits observe a deterministic order. A failed draft remains in its cell;
Retry replays that draft. Escape restores the saved value. When a valid draft is
visible, totals preview its parsed value; an invalid draft contributes the last
saved value.

The page status is derived with failure first, then Saving…, then Unsaved
changes, then Saved locally when the week contains confirmed entries, otherwise
No time saved. Save success updates the existing aria-live status and does not
emit per-cell toasts. Errors use a persistent alert and associate the failed
cell with its message.

Parallel writes were rejected because two cells on one date could each validate
against an obsolete total. A global Save button was rejected because the
approved interaction commits at the cell boundary.

### Treat deletion as a confirmed cell commit

Blank or `0:00` in a cell with a nonzero saved value opens the existing alert
dialog before enqueueing deletion. Cancel restores the saved display; confirmed
failure keeps the deletion draft and exposes Retry while the saved entry remains
authoritative. Clearing a cell that has never been saved simply removes its
draft.

Immediate deletion on blur was rejected because it makes an accidental clear
hard to detect or reverse.

### Coordinate week, route, and native-close navigation with draft state

Previous, Current, and Next first commit the active valid cell and await the
save queue. A failure or invalid draft retains the week and focuses that cell.
Route navigation and native close register one guard only while invalid, pending,
or failed drafts exist; Stay preserves them and Discard changes restores the
last saved snapshot before continuing. Empty transient rows alone are not dirty.

Unconditionally blocking close was rejected because saved local data and empty
row selections require no warning.

### Build one quiet, dense weekly ledger surface

Replace the placeholder with `WeeklyTimesheetPage`. Its header combines the
visible date range, Previous → Current → Next controls, and persistent save
status. `WorkItemSelector` uses the existing grouped Select primitives: Client
labels contain selectable Project rows and visibly indented Task rows. The table
keeps the work column and right Total column visually anchored around seven
narrow day columns, with a strong footer for daily and grand totals. On narrower
desktop windows the day grid scrolls horizontally instead of compressing inputs
beyond usable width.

`TimeEntryCell` owns accessible editing and failure association; the page owns
row selection, totals, navigation, and lifecycle refresh. Archived rows retain
their hierarchy labels, add a quiet `No longer active` badge, disable all seven
cells, and expose `Restore to edit` through the existing `CatalogLifecycle`
preview/apply flow.

This extends existing Geist typography, neutral card/table tokens, sentence-case
copy, focus rings, dialogs, and error regions. A colorful calendar dashboard was
rejected because the defining product object is a compact work ledger, not an
analytics surface.

### Extend backup compatibility for migration 5

Backup validation recognizes the time-entry table only for migration-5 data and
keeps valid migration-1 through migration-4 backups restorable and migratable.
The complete local backup already copies table data, so no new backup action is
required.

## Risks / Trade-offs

- **DST or timezone conversion shifts a displayed date** → Keep domain dates
  date-only and test local Sunday/Monday plus month/year boundaries.
- **Catalog state changes between load and save** → Recheck the complete active
  path inside the save transaction and reload the affected row on rejection.
- **Rapid blur events obscure the authoritative value** → Serialize writes and
  retain per-cell saved/draft state until each acknowledgement arrives.
- **A large catalog makes selection noisy** → Load one sorted hierarchy query,
  group by Client and Project, and never prepopulate Timesheet rows.
- **Native close interception differs from jsdom behavior** → Unit-test the
  guard state and record native smoke-check limitations explicitly.

## Migration Plan

1. Add migration 5 after catalog lifecycle migration 4 without modifying prior
   migrations; fresh databases replay the complete sequence.
2. Add the store, immutable mutation plan, and named Rust apply command before
   replacing the Timesheet placeholder.
3. Wire lifecycle restore and navigation guards only after core entry/save
   behavior is deterministic.
4. Roll back application code by leaving the additive table and saved entries
   intact; never downgrade or delete local time data.
