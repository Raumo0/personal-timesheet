## Context

The approved Expense ledger stores only ready Expenses with authoritative
original and billing amounts. It also exposes active/archived lifecycle through
one CatalogLifecycle seam. The Expenses route can be extended without another
primary destination. Dates elsewhere use validated local `YYYY-MM-DD` values
and additive migrations; Expense data occupies migration 6. See `proposal.md`
and both delta specs for behavior.

## Goals / Non-Goals

**Goals:**

- Keep recurrence calculation deterministic, date-only, and independent from
  timers, React, SQLite, and the operating-system clock.
- Give Schedule configuration, preview, materialization, catch-up, and pending
  completion one deep store interface with atomic operations.
- Preserve immutable occurrence snapshots and ready Expense history when a
  Schedule changes.
- Reuse Expense conversion and CatalogLifecycle instead of introducing parallel
  money or archive behavior.

**Non-Goals:**

- Run while the application process is closed or register an operating-system
  background job.
- Turn Schedule into an archived catalog entity or permanently delete generated
  history.
- Implement report/invoice readiness enforcement before those output surfaces
  exist.
- Add a date, job-queue, state-management, or notification dependency.

## Decisions

### Represent recurrence as validated data, not cron text

Add a discriminated `Recurrence` in
`src/features/expenses/recurring-expense.ts`: every N days, every N weeks with a
weekday, monthly with one day, or twice monthly with two ordered day/slot
values. A pure planner receives the recurrence, inclusive start/end range, and
requested local date window and returns ordered `{ dueDate, slot }` identities.

Date arithmetic uses the existing local date-only approach rather than UTC.
Monthly planning clamps each selected day to the calendar month's last day but
retains its original value for later months. Two slots remain distinct even
when both clamp to the same date.

Cron strings were rejected because month-end clamping and two stable slots are
not visible or safely editable. Fixed day counts for months were rejected
because they drift across calendar boundaries.

### Store Schedule rules and immutable occurrence snapshots separately

Migration 7 adds `expense_schedules` with exactly one Client-or-Project target,
description, positive original amount/currency, discriminated recurrence
fields, start/end dates, enabled flag, `reconciled_through`, and timestamps.
Schedules have no `archived_at`.

It also adds `scheduled_expense_occurrences` with Schedule ID, due date, slot,
snapshotted target, description, original amount/currency, Client billing
currency, nullable linked Expense ID, pending `archived_at`, and timestamps. A
unique key on Schedule/date/slot provides retry idempotency. The snapshot makes
materialized work independent from later Schedule edits.

Same-currency materialization creates the snapshot and ready Expense atomically
and links them. Different-currency materialization stores the snapshot without
an Expense; this derived state is `Needs conversion`. Completing it creates one
ready Expense through the existing exact conversion rules and fills the link in
the same transaction.

Allowing nullable billing amounts in the ready Expense table was rejected
because it would weaken the base ledger invariant. Pre-creating future rows was
rejected because it produces unbounded presentation and migration work.

### Give recurrence persistence one deep store interface

Add `RecurringExpenseStore` with operations to load the Schedules workspace,
preview a create/edit/enable command through the current local date, atomically
apply the returned immutable plan, reconcile continuously enabled Schedules
through a date, and complete one pending occurrence. The preview contains the
new configuration, due identities, exact range/count, and same-target/date
overlap summaries.

The TypeScript adapter uses `SqlReadDatabase` to build an immutable typed plan.
A named Rust `apply_recurring_expense_operation` command evaluates and applies
that plan in one transaction, rechecking
Schedule version, target lifecycle/currency, existing occurrence identities,
and overlap state. The in-memory adapter and SQLite adapter share a behavioral
contract. Cancellation applies nothing.

Putting due generation in React was rejected because launch catch-up, preview,
Retry, and SQLite idempotency would diverge. Exposing separate create/edit,
backfill, and reconcile transactions in the frontend was rejected because partial state could
enable a Schedule without its confirmed past occurrences.

### Distinguish continuous catch-up from configuration backfill

An enabled Schedule records the last local date through which automatic
reconciliation completed. Launch/resume reconciliation advances continuously
enabled rules through today without confirmation; this is expected catch-up for
a rule the user already enabled.

Creating, editing, or re-enabling a rule first produces a plan. If the new
configuration contributes any earlier unmaterialized dates, the UI must confirm
the preview before the configuration and occurrences are applied atomically.
Disabling stops reconciliation and retains its marker. Re-enabling never
silently fills the disabled interval.

Treating all launch catch-up as user-confirmed backfill was rejected because a
long-closed application would require repeated approval for an already enabled
rule. Treating configuration changes as ordinary catch-up was rejected because
they can unexpectedly add historical costs.

### Run one application-level local-date reconciler

Add one `ExpenseScheduleReconciler` mounted from the application shell rather
than the Expenses page. It reconciles after Schedule storage initializes, when
the application regains visibility/focus, and at the next computed local
midnight while running. It always passes an explicit current local date to the
store and schedules the next boundary again after clock or timezone changes.

The controller serializes runs and retries only after a visible failure or the
next lifecycle trigger. Store idempotency is authoritative, so duplicate focus
or timer events are harmless. No timer claims to run while the process is
closed; the next launch performs catch-up.

A page-mounted timer was rejected because schedules would stop when the user
navigates away. An OS background service was rejected as a separate
cross-platform product capability.

### Extend CatalogLifecycle with Schedule and pending-occurrence effects

Client and Project archive plans include disabling active descendant Schedules
and archiving active pending occurrences, in the same transaction as catalog
records and ready Expenses. Restoring a Client or Project leaves Schedules
disabled. Restoring one pending occurrence includes only that occurrence and
required ancestors. A linked ready Expense continues to use ordinary Expense
lifecycle; its occurrence link is provenance, not another visible lifecycle.

This extends the existing native `apply_catalog_lifecycle` plan and command.
Recurring lifecycle writes are not added to the recurring store, and neither
frontend transaction control nor the independent-statement executor may be used
for multi-step Schedule operations.

Making Schedule archiveable was rejected because enable/disable already
expresses whether the recurrence runs. Re-enabling after catalog restore stays
explicit so any historical range receives the approved preview.

### Add Schedules and Needs conversion to the existing workspace

Extend `ExpensesPage` with `Expenses` and `Schedules` views. Schedules use a
compact table showing target, description/amount, recurrence summary, active
range, next due date, and enabled state. `ExpenseScheduleForm` reuses the
existing Expense target and money inputs, then reveals fields for the selected
recurrence. Save or Enable opens the existing alert dialog when a backfill plan
requires confirmation.

The Expenses view includes active pending occurrences in date order with a
`Needs conversion` badge and `Complete conversion` action. Its completion form
reuses manual conversion and, when installed, the explicit ECB provider. An
archived pending occurrence is read-only with targeted Restore.

A new top-level Scheduled navigation item was rejected because schedules are
configuration for the Expense ledger, not a separate product area.

### Extend backup compatibility for migration 7

Backup validation recognizes both Schedule and occurrence tables only for
migration-7 data and keeps valid migration-1 through migration-6 backups
restorable and migratable. The complete SQLite snapshot already copies all
rows.

## Risks / Trade-offs

- **The clock or timezone changes while the app runs** → Recompute current local
  date and the next boundary at every trigger; rely on occurrence identity for
  idempotency.
- **A large backfill creates many records** → Preview the exact count and apply
  one bounded transaction; do not hide or silently truncate the range.
- **A Schedule edit collides with a prior date/slot** → Treat that identity as
  already materialized and never rewrite it.
- **A target archives during preview** → Recheck the complete target path and
  immutable plan before applying; change nothing on stale state.
- **A pending occurrence never receives conversion** → Keep it visibly
  `Needs conversion`; future Reports/Invoices must enforce A-0014 in their own
  changes.

## Migration Plan

1. Implement and exhaustively test the pure date-only recurrence planner.
2. Add migration 7 and backup validation without modifying migrations 1–6.
3. Implement the store contract, atomic plan/apply/reconcile operations, and
   pending completion before adding timers or UI.
4. Extend CatalogLifecycle, then add the Schedules and Needs conversion views.
5. Mount the application-level reconciler only after store idempotency and
   failure behavior are validated.
6. Roll back application code by disabling the reconciler and leaving additive
   Schedule, occurrence, and Expense data intact.
