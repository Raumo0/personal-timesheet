## Why

The application reserves an Expenses destination but cannot yet retain costs
against the Client or Project that will eventually be billed. A first usable
slice should preserve both the original transaction value and the amount the
user accepts in the Client's billing currency without requiring a network
service.

## What Changes

- Replace the Expenses placeholder with a local Expense workspace that lists
  active Expenses by default and archived Expenses separately.
- Create and edit a positive Expense with a local date, description, original
  amount and currency, and exactly one billing target: a Client directly or a
  Project whose Client is derived from that Project.
- Default the original currency to the Client billing currency. For another
  currency, let the user enter either a positive applied rate or the final
  amount in Client billing currency and recalculate the other value.
- Save original and billing amounts as authoritative minor units, apply one
  half-up conversion rounding, and retain the Client billing currency used by
  the saved Expense.
- Archive and restore Expenses without deletion. Project or Client archival
  includes related Expenses; restoring one Expense activates only that Expense
  and any required Client or Project ancestors.
- Keep persistence failures recoverable and retain all successfully saved data
  across restarts and local backup/restore.
- Defer suggested exchange rates, recurring Schedules, receipts, taxes,
  categories, Task assignment, refunds, credits, invoicing, and payments.

## Capabilities

### New Capabilities

- `expense-recording`: Expense workspace, billing targets, positive amounts,
  manual currency conversion, lifecycle, and durable local persistence.

### Modified Capabilities

None. Expense-owned lifecycle behavior is specified by `expense-recording` so
this change does not overlap the active Client/Project lifecycle deltas.

## Impact

- Replaces `/expenses` placeholder routing with a focused Expense page, form,
  table, and active/archived views using the established desktop UI patterns.
- Adds Expense domain, store, in-memory adapter, SQLite adapter, additive
  migration, and backup-version compatibility.
- Extends the catalog lifecycle seam planned by
  `manage-catalog-archive-lifecycle` to preview and atomically apply Expense
  archive and targeted restore operations.
- Depends on `manage-tasks-with-inherited-rates`,
  `manage-catalog-archive-lifecycle`, and `record-weekly-time-entries` being
  implemented first. No network dependency is added in this slice.
