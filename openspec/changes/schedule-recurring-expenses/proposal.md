## Why

Repeated project costs should not require the user to recreate the same Expense
every week or month. A local recurrence rule can materialize only due records,
catch up safely after the application was closed, and still keep every created
Expense independently reviewable.

## What Changes

- Add a Schedules view inside Expenses for creating and editing enabled or
  disabled recurring Expense rules against one Client or Project target.
- Support every N days, every N weeks on a chosen weekday, monthly on a chosen
  day, and twice monthly on two chosen days, with start date and optional end
  date.
- Clamp monthly days 29–31 to the last day of shorter months without changing
  the selected day for later months.
- Materialize occurrences only when due: at the relevant local date while the
  application is open and through deterministic catch-up on the next launch or
  resume after a gap.
- Create ready Expenses when the original currency matches Client billing
  currency. Create `Needs conversion` occurrences for another currency so the
  user can explicitly get or enter that occurrence's rate or final billing
  amount.
- Preview and confirm any past backfill with its date range, occurrence count,
  and overlaps. Add new schedule occurrences without editing existing Expenses,
  while preventing retries from duplicating the same Schedule/date/slot.
- Keep generated Expenses independent from later Schedule edits. Disabling a
  Schedule stops new materialization without deleting its rule or history.
- Disable related Schedules when their Client or Project is archived; restoring
  the catalog path does not re-enable them or silently backfill past dates.
- Defer report/invoice blocking for `Needs conversion`, refunds, credits,
  receipts, taxes, categories, Task targets, and background execution while the
  application is closed.

## Capabilities

### New Capabilities

- `recurring-expense-scheduling`: Schedule configuration, calendar recurrence,
  due materialization, catch-up, confirmed backfill, enable/disable state, and
  catalog lifecycle effects.

### Modified Capabilities

- `expense-recording`: Adds schedule provenance and the `Needs conversion`
  occurrence state to independently editable generated Expenses.

## Impact

- Extends the global Expenses workspace with a Schedules view and due-conversion
  status without adding another primary navigation destination.
- Adds a Schedule domain/store, a due-occurrence planner, additive migration 7,
  and backup compatibility after `record-project-expenses` migration 6.
- Adds `RecurringExpenseStore` for atomic occurrence materialization and
  completion while reusing the existing Expense lifecycle and manual/ECB
  conversion flows.
- Depends on `record-project-expenses`; `suggest-expense-exchange-rates` is
  optional at runtime because every `Needs conversion` occurrence retains manual
  completion.
