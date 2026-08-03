## 1. Lifecycle Planning Rules

- [x] 1.1 RED: add failing Client, Project, and Task archive/restore plan cases in `src/features/catalog-lifecycle/catalog-lifecycle.test.ts` for downward archive, target-plus-ancestor restore, unchanged siblings, preserved archived descendants, and exact impact descriptions; run `pnpm test -- src/features/catalog-lifecycle/catalog-lifecycle.test.ts`.
- [x] 1.2 GREEN/REFACTOR: implement discriminated targets, immutable plans, lifecycle errors, and the pure planner in `src/features/catalog-lifecycle/catalog-lifecycle.ts`; rerun `pnpm test -- src/features/catalog-lifecycle/catalog-lifecycle.test.ts`.

## 2. Lifecycle Interface and In-Memory Adapter

- [x] 2.1 RED: define shared preview/apply/stale/failure expectations in `src/features/catalog-lifecycle/catalog-lifecycle.contract.ts` and add failing focused tests in `src/features/catalog-lifecycle/in-memory-catalog-lifecycle.test.ts`; run `pnpm test -- src/features/catalog-lifecycle/in-memory-catalog-lifecycle.test.ts`.
- [x] 2.2 GREEN/REFACTOR: add the small `CatalogLifecycle` interface in `src/features/catalog-lifecycle/catalog-lifecycle.ts` and implement atomic snapshot replacement in `src/features/catalog-lifecycle/in-memory-catalog-lifecycle.ts`; rerun the focused test.

## 3. Migration 4 and Backup Compatibility

- [x] 3.1 RED: extend `src-tauri/src/database.rs` tests for migration 4 normalization of active Projects beneath archived Clients and active Tasks beneath archived Projects or Clients while preserving existing archive timestamps; run `cargo test --manifest-path src-tauri/Cargo.toml database`.
- [x] 3.2 GREEN/REFACTOR: add migration 4 to `src-tauri/src/database.rs` without modifying migrations 1–3; rerun `cargo test --manifest-path src-tauri/Cargo.toml database`.
- [x] 3.3 REGRESSION: extend `src-tauri/src/backup.rs` tests for valid migration-4 backups plus migration-1 through migration-3 compatibility.
- [x] 3.4 COMPATIBILITY/REFACTOR: update migration-aware compatibility and future-version expectations without changing backup/restore interactions; run `cargo test --manifest-path src-tauri/Cargo.toml backup`.

## 4. Atomic SQLite Lifecycle

- [x] 4.1 RED: add the shared lifecycle contract and focused SQLite cases in `src/features/catalog-lifecycle/sqlite-catalog-lifecycle.test.ts` for cascade archive, ancestor restore, preserved timestamps, stale plans, rollback, ordering, and persistence errors; run `pnpm test -- src/features/catalog-lifecycle/sqlite-catalog-lifecycle.test.ts`.
- [x] 4.2 GREEN/REFACTOR: implement bounded hierarchy loading and one-transaction plan application in `src/features/catalog-lifecycle/sqlite-catalog-lifecycle.ts` through `src/features/clients/database.ts`; rerun the focused test.

## 5. Client Archive and Restore Interaction

- [x] 5.1 RED: extend `src/features/clients/ClientsPage.test.tsx` with failing archive-scope, archived-row Restore, target-only restore, cancel, stale-plan, persistent error, focus, and Retry cases; run `pnpm test -- src/features/clients/ClientsPage.test.tsx`.
- [x] 5.2 GREEN/REFACTOR: route Client lifecycle actions through `CatalogLifecycle` in `src/features/clients/ClientsPage.tsx`, extending the existing Active/Archived table, alert dialog, and error region; rerun the focused test.

## 6. Project Archive and Restore Interaction

- [ ] 6.1 RED: extend `src/features/projects/ProjectsPage.test.tsx` with failing Task-cascade confirmation, restore-with-Client, archived-descendant preservation, cancel, persistent error, focus, and Retry cases; run `pnpm test -- src/features/projects/ProjectsPage.test.tsx`.
- [ ] 6.2 GREEN/REFACTOR: route Project lifecycle actions through `CatalogLifecycle` in `src/features/projects/ProjectsPage.tsx`, preserving visible Client context and the existing table/dialog patterns; rerun the focused test.

## 7. Task Archive and Restore Interaction

- [ ] 7.1 RED: extend `src/features/tasks/TasksPage.test.tsx` with failing Task-only archive, target-plus-ancestor restore confirmation, unchanged sibling, cancel, persistent error, focus, and Retry cases; run `pnpm test -- src/features/tasks/TasksPage.test.tsx`.
- [ ] 7.2 GREEN/REFACTOR: route Task lifecycle actions through `CatalogLifecycle` in `src/features/tasks/TasksPage.tsx`, preserving the Client → Project → Tasks breadcrumb and established table/dialog patterns; rerun the focused test.

## 8. Application Wiring and Single Write Authority

- [ ] 8.1 RED: extend `src/app/AppShell.test.tsx` with failing lifecycle injection and archived Client → Project → Task navigation/restore-context cases; run `pnpm test -- src/app/AppShell.test.tsx`.
- [ ] 8.2 GREEN/REFACTOR: inject `SqliteCatalogLifecycle` from `src/App.tsx` through `src/app/AppShell.tsx` to all three catalog screens, then remove direct `archive` methods and expectations from `src/features/clients/client-catalog.ts`, `src/features/clients/client-catalog.contract.ts`, `src/features/clients/in-memory-client-catalog.ts`, `src/features/clients/sqlite-client-catalog.ts`, `src/features/projects/project-catalog.ts`, `src/features/projects/project-catalog.contract.ts`, `src/features/projects/in-memory-project-catalog.ts`, `src/features/projects/sqlite-project-catalog.ts`, `src/features/tasks/task-catalog.ts`, `src/features/tasks/task-catalog.contract.ts`, `src/features/tasks/in-memory-task-catalog.ts`, and `src/features/tasks/sqlite-task-catalog.ts`; rerun `pnpm test -- src/app/AppShell.test.tsx src/features/clients/in-memory-client-catalog.test.ts src/features/clients/sqlite-client-catalog.test.ts src/features/projects/in-memory-project-catalog.test.ts src/features/projects/sqlite-project-catalog.test.ts src/features/tasks/in-memory-task-catalog.test.ts src/features/tasks/sqlite-task-catalog.test.ts`.

## 9. Integrated Verification

- [ ] 9.1 Run `pnpm test`, `pnpm build`, `cargo test --manifest-path src-tauri/Cargo.toml`, `cargo check --manifest-path src-tauri/Cargo.toml`, `pnpm exec openspec validate manage-catalog-archive-lifecycle --strict`, and `git diff --check`; fix only failures caused by this change and record the exact results plus any manual Tauri limitation in the governed implementer report.
