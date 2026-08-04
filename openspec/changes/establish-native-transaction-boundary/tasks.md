## 1. Immutable Client Update Plan

- [x] 1.1 RED: add focused cases in `src/features/clients/client-update-plan.test.ts` for unchanged currency, exact Project and Task rescaling, zero overrides, lossy precision rejection, malformed selected rows, deterministic ordering, and complete expected-state capture; run `pnpm test -- src/features/clients/client-update-plan.test.ts` and record only the expected missing-plan failures.
- [x] 1.2 GREEN/REFACTOR: add the typed immutable plan builder in `src/features/clients/client-update-plan.ts`, reusing `clientCommandSchema`, `normalizeClientName`, and `rescaleRateOverride` rather than duplicating currency rules; rerun `pnpm test -- src/features/clients/client-update-plan.test.ts src/features/projects/project.test.ts`.

## 2. Native Client Transaction

- [x] 2.1 RED: add real temporary-SQLite integration cases in `src-tauri/tests/native_transaction_boundary.rs` and shared fixtures in `src-tauri/tests/support/mod.rs` for Client update commit, intermediate Task-update rollback, stale Client or override snapshots with zero writes, missing or unexpected descendants, row-count mismatch, and preservation of primary plus rollback failures; run `cargo test --manifest-path src-tauri/Cargo.toml --test native_transaction_boundary` and record only the expected missing-native-boundary failures.
- [x] 2.2 GREEN/REFACTOR: implement typed plan deserialization, complete expected-state recheck, one-connection transaction apply, commit, rollback, and error classification in `src-tauri/src/client_update.rs`; expose its path-based application seam for integration tests and register only the named `apply_client_update` Tauri command in `src-tauri/src/lib.rs`; rerun `cargo test --manifest-path src-tauri/Cargo.toml --test native_transaction_boundary`.
- [x] 2.3 COVERAGE: extend `src-tauri/tests/native_transaction_boundary.rs` to exercise `src-tauri/src/catalog_lifecycle.rs` through the same real-database boundary for a stale lifecycle plan and an intermediate update failure, making the module test-accessible without exposing a generic transaction command; rerun `cargo test --manifest-path src-tauri/Cargo.toml --test native_transaction_boundary`.

## 3. Frontend Client Command Seam

- [x] 3.1 RED: replace simulated `BEGIN`/`COMMIT` expectations in `src/features/clients/sqlite-client-catalog.test.ts` with exact immutable-plan invocation, native success result, duplicate, missing, stale-plan, persistence, rollback-failure, and no-post-commit-read cases; run `pnpm test -- src/features/clients/sqlite-client-catalog.test.ts` and record only the expected command-seam failures.
- [x] 3.2 GREEN/REFACTOR: inject a typed invoke dependency into `src/features/clients/sqlite-client-catalog.ts`, build the validated plan through `src/features/clients/client-update-plan.ts`, call only `apply_client_update` for Client edits, translate native failures to the existing `ClientCatalogError` codes, and remove every frontend transaction-control call; rerun `pnpm test -- src/features/clients/sqlite-client-catalog.test.ts src/features/clients/in-memory-client-catalog.test.ts`.

## 4. Read-Only Facade and Independent Statements

- [x] 4.1 RED: add focused adapter cases in `src/infrastructure/sqlite/plugin-sql-adapter.test.ts` for a select-only `SqlReadDatabase`, database reuse and close, successful bound single statements, and rejection of empty, dynamic multi-statement, `BEGIN`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`, `RELEASE`, and transactional `END` input; run `pnpm test -- src/infrastructure/sqlite/plugin-sql-adapter.test.ts` and record only the expected missing-adapter failures.
- [x] 4.2 GREEN/REFACTOR: move the existing plugin owner from `src/features/clients/database.ts` to `src/infrastructure/sqlite/plugin-sql-adapter.ts`, export separate `SqlReadDatabase` and `IndependentSqlStatementExecutor` capabilities, preserve checkpoint-and-close behavior, and update imports plus injected test dependencies in `src/features/backup/tauri-backup-service.ts`, `src/features/clients/sqlite-client-catalog.ts`, `src/features/projects/sqlite-project-catalog.ts`, `src/features/tasks/sqlite-task-catalog.ts`, `src/features/catalog-lifecycle/sqlite-catalog-lifecycle.ts`, and their focused tests; rerun `pnpm test -- src/infrastructure/sqlite/plugin-sql-adapter.test.ts src/features/backup/tauri-backup-service.test.ts src/features/clients/sqlite-client-catalog.test.ts src/features/projects/sqlite-project-catalog.test.ts src/features/tasks/sqlite-task-catalog.test.ts src/features/catalog-lifecycle/sqlite-catalog-lifecycle.test.ts`.

## 5. Import and SQL Boundary Check

- [x] 5.1 RED: add fixture and repository cases in `tests/test_native_transaction_boundary.py` for the single approved `@tauri-apps/plugin-sql` import, read-only consumers, reviewed independent-executor imports, forbidden direct imports, transaction verbs, dynamic writes, multi-statements, and allowlist drift; run `python3 -m unittest tests.test_native_transaction_boundary -v` and record only the expected missing-checker failures.
- [x] 5.2 GREEN/REFACTOR: add the TypeScript-AST checker in `tools/check_native_transaction_boundary.mjs`, add `lint:native-transactions` to `package.json`, keep the executor-import allowlist limited to the migrated independent statement adapters, and make the repository fixture pass; run `python3 -m unittest tests.test_native_transaction_boundary -v` and `pnpm lint:native-transactions`.

## 6. Catalog Regression Coverage

- [x] 6.1 REGRESSION: run `pnpm test -- src/features/clients/ClientsPage.test.tsx src/features/projects/ProjectsPage.test.tsx src/features/tasks/TasksPage.test.tsx src/app/AppShell.test.tsx` and fix only regressions caused by dependency injection or native error translation while preserving the existing desktop interactions.
- [x] 6.2 REGRESSION: run `cargo test --manifest-path src-tauri/Cargo.toml catalog_lifecycle` and `cargo test --manifest-path src-tauri/Cargo.toml backup` to confirm the named Client command does not alter lifecycle or backup behavior.

## 7. Integrated Verification

- [x] 7.1 Run `python3 -m unittest discover -s tests -v`, `pnpm lint:native-transactions`, `pnpm test`, `pnpm build`, `cargo test --manifest-path src-tauri/Cargo.toml`, `cargo check --manifest-path src-tauri/Cargo.toml`, `pnpm exec openspec validate establish-native-transaction-boundary --strict`, and `git diff --check`; then run `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json` and record exact results plus native-smoke limitations in the governed implementer report before independent review.
