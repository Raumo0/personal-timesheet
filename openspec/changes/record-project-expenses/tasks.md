Coverage-first checkbox rule: each checkbox includes its indented GREEN/REFACTOR continuation. A passing focused test is sufficient evidence; when behavior is absent, record the expected RED before implementation, then finish the same checkbox with the focused command passing.

## 1. Exact Money Domain

- [ ] 1.1 COVERAGE-FIRST: add focused money and compatibility cases; accept an already-passing focused test or record the expected RED, implement exact integer/BigInt money behavior and compatibility wrappers, then run `pnpm test -- src/features/money/money.test.ts src/features/clients/client.test.ts src/features/projects/project.test.ts` to GREEN and refactor only while it stays green.

## 2. Expense Domain Rules

- [ ] 2.1 COVERAGE-FIRST: add focused Expense domain cases; accept an already-passing focused test or record the expected RED, implement the smallest Expense schemas, discriminated target, commands, saved model, row mapping, and validation, then run `pnpm test -- src/features/expenses/expense.test.ts` to GREEN.

## 3. Expense Store Interface and In-Memory Adapter

- [ ] 3.1 COVERAGE-FIRST: define shared workspace-load, active/archived ordering, active-target tree, create, update, target recheck, retained billing snapshot, and failure expectations in `src/features/expenses/expense-store.contract.ts`; add focused cases in `src/features/expenses/in-memory-expense-store.test.ts`; run `pnpm test -- src/features/expenses/in-memory-expense-store.test.ts`.
  - GREEN/REFACTOR: add the small `ExpenseStore` interface and typed errors in `src/features/expenses/expense-store.ts`, then implement atomic in-memory behavior in `src/features/expenses/in-memory-expense-store.ts`; rerun `pnpm test -- src/features/expenses/in-memory-expense-store.test.ts`.

## 4. Migration 6 and Backup Compatibility

- [ ] 4.1 COVERAGE-FIRST: extend `src-tauri/src/database.rs` tests for migration 6 with exactly one Client-or-Project foreign key, local date, positive original/billing minor amounts, currency codes, decimal-rate text, rate-source, nullable observation-date, manual-adjustment provenance, timestamps, and archive state; run `cargo test --manifest-path src-tauri/Cargo.toml database`.
  - GREEN/REFACTOR: add migration 6 to `src-tauri/src/database.rs` without modifying migrations 1–5; rerun `cargo test --manifest-path src-tauri/Cargo.toml database`.
- [ ] 4.3 COVERAGE-FIRST: extend `src-tauri/src/backup.rs` tests for valid migration-6 Expense schemas, malformed target/money schemas, and migration-1 through migration-5 compatibility; run `cargo test --manifest-path src-tauri/Cargo.toml backup`.
  - GREEN/REFACTOR: update migration-aware Expense schema validation in `src-tauri/src/backup.rs` without changing backup/restore interactions; rerun `cargo test --manifest-path src-tauri/Cargo.toml backup`.

## 5. Durable Expense Store

- [ ] 5.1 COVERAGE-FIRST: run the shared contract plus focused SQLite/native cases for bounded reads, immutable create/update plans, exact money, target/version rechecks, commit, rollback, stale plans, malformed rows, and errors; accept a passing focused test or record the expected RED, then implement queries through `SqlReadDatabase`, the frontend adapter, and named Rust `apply_expense_mutation` transaction command; run the focused TypeScript and Rust command tests to GREEN.

## 6. Expense Lifecycle Integration

- [ ] 6.1 COVERAGE-FIRST: extend `src/features/catalog-lifecycle/catalog-lifecycle.test.ts` with focused Expense-only archive, Project/Client Expense cascade, direct-Client and Project-Expense ancestor restore, preserved siblings, impact summary, and stale-plan cases; run `pnpm test -- src/features/catalog-lifecycle/catalog-lifecycle.test.ts`.
  - GREEN/REFACTOR: extend Expense targets and nodes in `src/features/catalog-lifecycle/catalog-lifecycle.ts` without adding lifecycle writes to `ExpenseStore`; rerun `pnpm test -- src/features/catalog-lifecycle/catalog-lifecycle.test.ts`.
- [ ] 6.3 COVERAGE-FIRST: extend `src/features/catalog-lifecycle/catalog-lifecycle.contract.ts`, `src/features/catalog-lifecycle/in-memory-catalog-lifecycle.test.ts`, and `src/features/catalog-lifecycle/sqlite-catalog-lifecycle.test.ts` with atomic Expense cascade/restore, timestamp preservation, rollback, and stale-plan expectations; run `pnpm test -- src/features/catalog-lifecycle/in-memory-catalog-lifecycle.test.ts src/features/catalog-lifecycle/sqlite-catalog-lifecycle.test.ts`.
  - GREEN/REFACTOR: implement Expense lifecycle planning state in the in-memory adapter and extend the existing native `apply_catalog_lifecycle` plan, Rust command, and SQLite adapter for atomic Expense queries/writes; rerun the focused lifecycle adapter and native transaction tests.

## 7. Expense Form

- [ ] 7.1 COVERAGE-FIRST: add focused interaction and accessibility cases in `src/features/expenses/ExpenseForm.test.tsx` for direct Client and grouped Project targets, active-only options, local date/description, positive amounts, currency default, same-currency simplification, linked rate/billing inputs, half-up preview, validation, draft retention, and edit restoration; run `pnpm test -- src/features/expenses/ExpenseForm.test.tsx`.
  - GREEN/REFACTOR: implement `src/features/expenses/ExpenseForm.tsx` with existing Dialog, Input, Label, Select, Button, focus, and inline-error patterns plus the pure money module; rerun `pnpm test -- src/features/expenses/ExpenseForm.test.tsx`.

## 8. Expense Workspace and Lifecycle Actions

- [ ] 8.1 COVERAGE-FIRST: add focused page cases in `src/features/expenses/ExpensesPage.test.tsx` for loading/error/empty states, active/archived views, descending date order, displayed targets and both amounts, create/edit refresh, read-only archived rows, and recoverable CRUD failure; run `pnpm test -- src/features/expenses/ExpensesPage.test.tsx`.
  - GREEN/REFACTOR: implement `src/features/expenses/ExpensesPage.tsx` with the compact ledger, established typography/table density, form integration, persistent error region, and accessible status handling; rerun the focused page test.
- [ ] 8.3 COVERAGE-FIRST: extend `src/features/expenses/ExpensesPage.test.tsx` with focused archive confirmation, exact cascade preview, targeted restore preview, cancel, success refresh, unchanged siblings, stale plan, failure, focus, and Retry cases; run `pnpm test -- src/features/expenses/ExpensesPage.test.tsx`.
  - GREEN/REFACTOR: integrate the existing `CatalogLifecycle` preview/apply interface into `src/features/expenses/ExpensesPage.tsx` and reload workspace targets after successful lifecycle changes; rerun the focused page test.

## 9. Expenses Route and Application Wiring

- [ ] 9.1 COVERAGE-FIRST: extend `src/app/AppShell.test.tsx` with focused lazy `/expenses` route, comfortable density, injected Expense store/lifecycle, loading, active navigation, and recoverable-load-error cases; run `pnpm test -- src/app/AppShell.test.tsx`.
  - GREEN/REFACTOR: replace the Expenses `ProductPage` branch with lazy `ExpensesPage` wiring in `src/app/AppShell.tsx`, inject `SqliteExpenseStore` from `src/App.tsx`, reuse the existing `CatalogLifecycle` injection, and preserve `src/app/navigation.tsx` metadata; rerun `pnpm test -- src/app/AppShell.test.tsx`.

## 10. Integrated Verification

- [ ] 10.1 Run `pnpm test`, `pnpm build`, `cargo test --manifest-path src-tauri/Cargo.toml`, `cargo check --manifest-path src-tauri/Cargo.toml`, `pnpm exec openspec validate record-project-expenses --strict`, and `git diff --check`; fix only failures caused by this change and record exact results plus any manual Tauri limitation in the governed implementer report.
