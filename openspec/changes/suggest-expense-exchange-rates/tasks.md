Coverage-first checkbox rule: each checkbox includes its indented GREEN/REFACTOR continuation. A passing focused test is sufficient evidence; when behavior is absent, record the expected RED before implementation, then finish the same checkbox with the focused command passing.

## 1. Expense Rate Provider Interface

- [ ] 1.1 COVERAGE-FIRST: define shared exact-date, earlier-date, canonical-direction, unsupported, unavailable, invalid-data, and Retry expectations in `src/features/expenses/expense-rate-provider.contract.ts`; add focused cases in `src/features/expenses/in-memory-expense-rate-provider.test.ts`; run `pnpm test -- src/features/expenses/in-memory-expense-rate-provider.test.ts`.
  - GREEN/REFACTOR: add the small `ExpenseRateProvider` interface, command/result types, and stable errors in `src/features/expenses/expense-rate-provider.ts`, then implement `src/features/expenses/in-memory-expense-rate-provider.ts`; rerun the focused test.

## 2. ECB Observation Selection and Direction

- [ ] 2.1 COVERAGE-FIRST: add focused Rust cases in `src-tauri/src/exchange_rates.rs` for validated currency/date inputs, ECB EUR-base observations, exact and latest-shared dates, EUR→quote, quote→EUR, non-EUR cross-rates including HUF, reversed pairs, 12-decimal half-up rate output, missing series, and malformed data; run `cargo test --manifest-path src-tauri/Cargo.toml exchange_rates`.
  - GREEN/REFACTOR: implement pure ECB observation parsing, shared-date selection, exact scaled-decimal normalization, typed errors, and the canonical suggestion result in `src-tauri/src/exchange_rates.rs`; rerun `cargo test --manifest-path src-tauri/Cargo.toml exchange_rates`.

## 3. Native ECB Transport and Command

- [ ] 3.1 COVERAGE-FIRST: extend `src-tauri/src/exchange_rates.rs` with focused injected-transport cases for the exact ECB request, HTTPS/status/content validation, timeout, unsupported series, no observation, and malformed response without a live network dependency; run `cargo test --manifest-path src-tauri/Cargo.toml exchange_rates`.
  - GREEN/REFACTOR: add the minimum HTTPS client dependency in `src-tauri/Cargo.toml` and `src-tauri/Cargo.lock`, implement the bounded ECB transport in `src-tauri/src/exchange_rates.rs`, and keep endpoint knowledge inside that adapter; rerun the focused Rust test.
- [ ] 3.3 COVERAGE-FIRST: extend `src-tauri/src/lib.rs` tests for registered `suggest_expense_exchange_rate` command input/output and stable error serialization; run `cargo test --manifest-path src-tauri/Cargo.toml`.
  - GREEN/REFACTOR: register the narrow command and module in `src-tauri/src/lib.rs` without adding a general webview HTTP permission; rerun `cargo test --manifest-path src-tauri/Cargo.toml`.

## 4. Tauri Frontend Adapter

- [ ] 4.1 COVERAGE-FIRST: add focused invocation, result-boundary, and native-error translation cases in `src/features/expenses/tauri-expense-rate-provider.test.ts`; run `pnpm test -- src/features/expenses/tauri-expense-rate-provider.test.ts`.
  - GREEN/REFACTOR: implement `src/features/expenses/tauri-expense-rate-provider.ts` as the only frontend adapter for the native command; rerun the focused test.

## 5. Suggestion Provenance

- [ ] 5.1 COVERAGE-FIRST: extend `src/features/expenses/expense.test.ts`, `src/features/expenses/in-memory-expense-store.test.ts`, and `src/features/expenses/sqlite-expense-store.test.ts` with focused manual, ECB unchanged, ECB manually adjusted, observation-date, row-boundary, update, and reload cases; run `pnpm test -- src/features/expenses/expense.test.ts src/features/expenses/in-memory-expense-store.test.ts src/features/expenses/sqlite-expense-store.test.ts`.
  - GREEN/REFACTOR: extend the Expense domain and in-memory store, then persist reserved provenance through the base change's named native `apply_expense_mutation` boundary without a new migration or frontend write path; rerun the focused Expense tests.

## 6. Explicit Get Rate Interaction

- [ ] 6.1 COVERAGE-FIRST: extend `src/features/expenses/ExpenseForm.test.tsx` with focused no-automatic-request, same-currency hidden control, loading, exact pair/date request, successful suggestion, actual observation date, reference-rate copy, amount preview, pair reversal, rate edit, billing-amount edit, Retry, unsupported currency, malformed response, and preserved-draft cases; run `pnpm test -- src/features/expenses/ExpenseForm.test.tsx`.
  - GREEN/REFACTOR: integrate `ExpenseRateProvider` into `src/features/expenses/ExpenseForm.tsx` with one explicit `Get rate` state machine, existing money conversion, provenance transitions, accessible status/error copy, and manual fallback; rerun the focused form test.

## 7. Provider Wiring

- [ ] 7.1 COVERAGE-FIRST: extend `src/features/expenses/ExpensesPage.test.tsx` and `src/app/AppShell.test.tsx` with focused provider injection, saved provenance display, lazy-route availability, and no-request-on-open cases; run `pnpm test -- src/features/expenses/ExpensesPage.test.tsx src/app/AppShell.test.tsx`.
  - GREEN/REFACTOR: inject `TauriExpenseRateProvider` from `src/App.tsx` through `src/app/AppShell.tsx` and `src/features/expenses/ExpensesPage.tsx` to the form without exposing provider details to the page; rerun the focused tests.

## 8. Integrated Verification

- [ ] 8.1 Run `pnpm test`, `pnpm build`, `cargo test --manifest-path src-tauri/Cargo.toml`, `cargo check --manifest-path src-tauri/Cargo.toml`, `pnpm exec openspec validate suggest-expense-exchange-rates --strict`, and `git diff --check`; fix only failures caused by this change and record exact results plus the live-ECB/manual-Tauri limitations in the governed implementer report.
