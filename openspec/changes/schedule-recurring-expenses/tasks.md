## 1. Calendar Recurrence Planner

- [ ] 1.1 RED: add failing validation and due-identity cases in `src/features/expenses/recurring-expense.test.ts` for every N days, every N weeks on one weekday, monthly, twice monthly, inclusive start/end dates, leap years, month-end clamping, two slots on one clamped date, ordering, and explicit local `YYYY-MM-DD` inputs; run `pnpm test -- src/features/expenses/recurring-expense.test.ts`.
- [ ] 1.2 GREEN/REFACTOR: implement the discriminated recurrence model and pure `{ dueDate, slot }` planner in `src/features/expenses/recurring-expense.ts` without timers or UTC conversion; rerun `pnpm test -- src/features/expenses/recurring-expense.test.ts`.

## 2. Schedule and Occurrence Domain Rules

- [ ] 2.1 RED: extend `src/features/expenses/recurring-expense.test.ts` with failing Schedule command, active Client-or-Project target, positive source money, date-range, enabled-state, immutable occurrence snapshot, `Needs conversion`, and versioned-plan cases; run `pnpm test -- src/features/expenses/recurring-expense.test.ts`.
- [ ] 2.2 GREEN/REFACTOR: implement validated Schedule, occurrence snapshot, preview, overlap, reconciliation, and completion types in `src/features/expenses/recurring-expense.ts`, reusing `src/features/money/money.ts` and `src/features/expenses/expense.ts`; rerun the focused test.

## 3. Recurring Expense Store Contract

- [ ] 3.1 RED: define shared load, preview/apply, cancel, continuous reconciliation, retry idempotency, same-currency Expense creation, different-currency pending state, manual completion, edit-history independence, enable/disable, stale-plan, and failure expectations in `src/features/expenses/recurring-expense-store.contract.ts`; add failing cases in `src/features/expenses/in-memory-recurring-expense-store.test.ts`; run `pnpm test -- src/features/expenses/in-memory-recurring-expense-store.test.ts`.
- [ ] 3.2 GREEN/REFACTOR: add the small `RecurringExpenseStore` interface and typed errors in `src/features/expenses/recurring-expense-store.ts`, then implement atomic behavior in `src/features/expenses/in-memory-recurring-expense-store.ts`; rerun the focused test.

## 4. Migration 7 and Backup Compatibility

- [ ] 4.1 RED: extend `src-tauri/src/database.rs` tests for migration 7 Schedule configuration, discriminated recurrence fields, exactly one Client-or-Project target, enabled/reconciled state, immutable occurrence snapshots, nullable linked Expense, pending archive state, and unique Schedule/date/slot identity; run `cargo test --manifest-path src-tauri/Cargo.toml database`.
- [ ] 4.2 GREEN/REFACTOR: add migration 7 for `expense_schedules` and `scheduled_expense_occurrences` in `src-tauri/src/database.rs` without modifying migrations 1–6; rerun `cargo test --manifest-path src-tauri/Cargo.toml database`.
- [ ] 4.3 RED: extend `src-tauri/src/backup.rs` tests for valid migration-7 Schedule/occurrence schemas, malformed recurrence/identity/link schemas, and migration-1 through migration-6 compatibility; run `cargo test --manifest-path src-tauri/Cargo.toml backup`.
- [ ] 4.4 GREEN/REFACTOR: update migration-aware Schedule and occurrence schema validation in `src-tauri/src/backup.rs` without changing backup/restore interactions; rerun `cargo test --manifest-path src-tauri/Cargo.toml backup`.

## 5. Durable Recurring Expense Store

- [ ] 5.1 RED: run the shared contract plus focused SQLite cases in `src/features/expenses/sqlite-recurring-expense-store.test.ts` for bounded workspace loading, preview counts/ranges/overlaps, atomic apply, target/version rechecks, occurrence snapshots, same-currency Expense links, pending completion, continuous catch-up, duplicate triggers, restart progress, rollback, and malformed rows; run `pnpm test -- src/features/expenses/sqlite-recurring-expense-store.test.ts`.
- [ ] 5.2 GREEN/REFACTOR: implement bounded queries and transactional preview/apply/reconcile/complete operations in `src/features/expenses/sqlite-recurring-expense-store.ts` through `src/features/clients/database.ts`; rerun the focused test.

## 6. Catalog Lifecycle Integration

- [ ] 6.1 RED: extend `src/features/catalog-lifecycle/catalog-lifecycle.test.ts` with failing Project/Client archive-plan cases for enabled Schedule counts, pending-occurrence counts, targeted pending restore, required ancestors, preserved siblings, and restore-without-enable behavior; run `pnpm test -- src/features/catalog-lifecycle/catalog-lifecycle.test.ts`.
- [ ] 6.2 GREEN/REFACTOR: extend lifecycle targets, immutable plans, and impact summaries in `src/features/catalog-lifecycle/catalog-lifecycle.ts` for Schedule disabling and pending occurrences; rerun the focused planner test.
- [ ] 6.3 RED: extend `src/features/catalog-lifecycle/catalog-lifecycle.contract.ts`, `src/features/catalog-lifecycle/in-memory-catalog-lifecycle.test.ts`, and `src/features/catalog-lifecycle/sqlite-catalog-lifecycle.test.ts` with atomic Schedule disable, pending archive/restore, stale-plan, rollback, and no-auto-enable expectations; run `pnpm test -- src/features/catalog-lifecycle/in-memory-catalog-lifecycle.test.ts src/features/catalog-lifecycle/sqlite-catalog-lifecycle.test.ts`.
- [ ] 6.4 GREEN/REFACTOR: implement Schedule and pending-occurrence lifecycle state in `src/features/catalog-lifecycle/in-memory-catalog-lifecycle.ts` and transactional queries/writes in `src/features/catalog-lifecycle/sqlite-catalog-lifecycle.ts`; rerun the focused adapter tests.

## 7. Schedule Form and Confirmed Backfill

- [ ] 7.1 RED: add failing interaction and accessibility cases in `src/features/expenses/ExpenseScheduleForm.test.tsx` for active grouped targets, source money, each recurrence shape, start/end validation, create/edit draft retention, enabled state, exact backfill range/count/overlap preview, confirm, cancel, stale plan, and save failure; run `pnpm test -- src/features/expenses/ExpenseScheduleForm.test.tsx`.
- [ ] 7.2 GREEN/REFACTOR: implement `src/features/expenses/ExpenseScheduleForm.tsx` with existing Dialog, AlertDialog, Input, Label, Select, Button, focus, and inline-error patterns, applying a confirmed immutable store plan atomically; rerun the focused test.

## 8. Schedules Workspace

- [ ] 8.1 RED: add failing page cases in `src/features/expenses/ExpenseSchedulesView.test.tsx` for loading/error/empty states, compact Schedule rows, recurrence summary, active range, next due date, enabled state, create/edit, disable, enable with and without backfill, Retry, and no archive action; run `pnpm test -- src/features/expenses/ExpenseSchedulesView.test.tsx`.
- [ ] 8.2 GREEN/REFACTOR: implement `src/features/expenses/ExpenseSchedulesView.tsx` and integrate `Expenses`/`Schedules` switching in `src/features/expenses/ExpensesPage.tsx` without adding primary navigation; rerun `pnpm test -- src/features/expenses/ExpenseSchedulesView.test.tsx src/features/expenses/ExpensesPage.test.tsx`.

## 9. Pending Occurrence Completion

- [ ] 9.1 RED: extend `src/features/expenses/ExpensesPage.test.tsx` with failing active/archived `Needs conversion` rows, manual rate/final-billing linked inputs, exact preview, optional explicit ECB suggestion, one-Expense completion, retry idempotency, read-only archived state, targeted restore, retained draft, and recoverable failure cases; run `pnpm test -- src/features/expenses/ExpensesPage.test.tsx`.
- [ ] 9.2 GREEN/REFACTOR: extend `src/features/expenses/ExpensesPage.tsx` and `src/features/expenses/ExpenseForm.tsx` to display and complete pending occurrences through `RecurringExpenseStore`, reusing existing conversion and `CatalogLifecycle` seams; rerun the focused page test.

## 10. Application-Level Reconciliation

- [ ] 10.1 RED: add failing controller cases in `src/features/expenses/ExpenseScheduleReconciler.test.tsx` for initialization, focus, visibility, next local midnight, clock/timezone recomputation, serialized duplicate triggers, catch-up failure, and cleanup; extend `src/app/AppShell.test.tsx` with failing always-mounted injection cases; run `pnpm test -- src/features/expenses/ExpenseScheduleReconciler.test.tsx src/app/AppShell.test.tsx`.
- [ ] 10.2 GREEN/REFACTOR: implement `src/features/expenses/ExpenseScheduleReconciler.tsx`, mount it once from `src/app/AppShell.tsx`, inject `SqliteRecurringExpenseStore` from `src/App.tsx`, and keep reconciliation independent from the active route; rerun the focused controller and shell tests.

## 11. Integrated Verification

- [ ] 11.1 Run `pnpm test`, `pnpm build`, `cargo test --manifest-path src-tauri/Cargo.toml`, `cargo check --manifest-path src-tauri/Cargo.toml`, `pnpm exec openspec validate schedule-recurring-expenses --strict`, and `git diff --check`; fix only failures caused by this change and record exact results plus the no-OS-background limitation in the governed implementer report.
