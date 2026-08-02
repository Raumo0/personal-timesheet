## 1. Task Domain Rules

- [ ] 1.1 RED: add failing normalization, row-boundary, validation,
  inheritance-chain, source, unset, and explicit-zero cases in
  `src/features/tasks/task.test.ts`; run
  `pnpm test -- src/features/tasks/task.test.ts`.
- [ ] 1.2 GREEN/REFACTOR: implement the smallest task schemas, domain types,
  row mapping, and one pure Task → Project → Client rate resolver in
  `src/features/tasks/task.ts`, reusing project/client rate behavior without a
  generic rate engine; rerun `pnpm test -- src/features/tasks/task.test.ts`.

## 2. Task Catalog Interface and In-Memory Adapter

- [ ] 2.1 RED: define shared create/edit/list/archive expectations in
  `src/features/tasks/task-catalog.contract.ts` and add failing focused tests in
  `src/features/tasks/in-memory-task-catalog.test.ts` for project-scoped active
  names, archived separation, zero overrides, and failures; run
  `pnpm test -- src/features/tasks/in-memory-task-catalog.test.ts`.
- [ ] 2.2 GREEN/REFACTOR: add the small `TaskCatalog` interface and errors in
  `src/features/tasks/task-catalog.ts`, then implement
  `src/features/tasks/in-memory-task-catalog.ts` without a generic catalog
  abstraction; rerun the focused test.

## 3. Durable Client and Project Lookup

- [ ] 3.1 RED: extend `src/features/clients/client-catalog.contract.ts`,
  `src/features/clients/in-memory-client-catalog.test.ts`,
  `src/features/clients/sqlite-client-catalog.test.ts`,
  `src/features/projects/project-catalog.contract.ts`,
  `src/features/projects/in-memory-project-catalog.test.ts`, and
  `src/features/projects/sqlite-project-catalog.test.ts` with failing ID lookup
  cases for active, archived, missing, and mismatched records; run
  `pnpm test -- src/features/clients/in-memory-client-catalog.test.ts src/features/clients/sqlite-client-catalog.test.ts src/features/projects/in-memory-project-catalog.test.ts src/features/projects/sqlite-project-catalog.test.ts`.
- [ ] 3.2 GREEN/REFACTOR: extend `ClientCatalog` and `ProjectCatalog` plus their
  in-memory and SQLite adapters with durable ID lookup in
  `src/features/clients/client-catalog.ts`,
  `src/features/clients/in-memory-client-catalog.ts`,
  `src/features/clients/sqlite-client-catalog.ts`,
  `src/features/projects/project-catalog.ts`,
  `src/features/projects/in-memory-project-catalog.ts`, and
  `src/features/projects/sqlite-project-catalog.ts`; rerun the focused tests.

## 4. SQLite Task Persistence

- [ ] 4.1 RED: extend `src-tauri/src/database.rs` tests for migration 3 with
  the task foreign key, nullable non-negative override, timestamps, and partial
  active-name uniqueness per project; run
  `cargo test --manifest-path src-tauri/Cargo.toml database`.
- [ ] 4.2 GREEN/REFACTOR: add migration 3 to `src-tauri/src/database.rs`
  without modifying migrations 1 or 2; rerun
  `cargo test --manifest-path src-tauri/Cargo.toml database`.
- [ ] 4.3 RED: add the shared task catalog contract and persistence-failure
  cases in `src/features/tasks/sqlite-task-catalog.test.ts`, including inherited
  `NULL`, explicit zero, project scoping, ordering, and archival; run
  `pnpm test -- src/features/tasks/sqlite-task-catalog.test.ts`.
- [ ] 4.4 GREEN/REFACTOR: implement
  `src/features/tasks/sqlite-task-catalog.ts` through the existing
  `src/features/clients/database.ts` connection seam with project-scoped update
  and archive statements; rerun the focused test.

## 5. Atomic Descendant Currency Rescaling

- [ ] 5.1 RED: extend `src/features/projects/project.test.ts` and
  `src/features/clients/sqlite-client-catalog.test.ts` with failing cases for a
  shared exact override-rescaling rule, simultaneous project/task conversion,
  explicit zero, overflow, lossy task precision, and rollback without partial
  updates; run
  `pnpm test -- src/features/projects/project.test.ts src/features/clients/sqlite-client-catalog.test.ts`.
- [ ] 5.2 GREEN/REFACTOR: generalize the existing pure rescaling helper in
  `src/features/projects/project.ts` and extend
  `src/features/clients/sqlite-client-catalog.ts` to validate and update every
  project and task override in one transaction; rerun the focused tests.

## 6. Task Form

- [ ] 6.1 RED: add failing form interaction tests in
  `src/features/tasks/TaskForm.test.tsx` for explicit inherit/override choices,
  project and client sources, unset inheritance, validation, mode restoration,
  and zero override; run
  `pnpm test -- src/features/tasks/TaskForm.test.tsx`.
- [ ] 6.2 GREEN/REFACTOR: implement
  `src/features/tasks/TaskForm.tsx` with the existing dialog, input, label,
  radio, currency parsing, and rate-formatting patterns; rerun the focused test.

## 7. Task Screen and Navigation

- [ ] 7.1 RED: add failing screen tests in
  `src/features/tasks/TasksPage.test.tsx` for active/archived lists, effective
  sources, empty/loading/error states, create/edit/archive flows, breadcrumb
  context, and read-only archived ancestors; run
  `pnpm test -- src/features/tasks/TasksPage.test.tsx`.
- [ ] 7.2 GREEN/REFACTOR: implement
  `src/features/tasks/TasksPage.tsx` using the established project screen
  typography, spacing, table density, confirmations, accessible errors, and a
  compact Client → Project → Tasks breadcrumb; rerun the focused test.
- [ ] 7.3 RED: extend `src/features/projects/ProjectsPage.test.tsx` and
  `src/app/AppShell.test.tsx` with failing project-link, task deep-link,
  refresh-context, missing-context, return-navigation, lazy-loading, and active
  Clients-navigation cases; run
  `pnpm test -- src/features/projects/ProjectsPage.test.tsx src/app/AppShell.test.tsx`.
- [ ] 7.4 GREEN/REFACTOR: link project names in
  `src/features/projects/ProjectsPage.tsx`, add the
  `/clients/:clientId/projects/:projectId/tasks` route and catalog lookups in
  `src/app/AppShell.tsx`, and inject `SqliteTaskCatalog` from `src/App.tsx`;
  preserve separate edit/archive actions and rerun the focused tests.

## 8. Backup Compatibility

- [ ] 8.1 RED: extend `src-tauri/src/backup.rs` tests for valid migration-3
  task schemas, migration-1 and migration-2 compatibility, and malformed task
  schema rejection; run `cargo test --manifest-path src-tauri/Cargo.toml backup`.
- [ ] 8.2 GREEN/REFACTOR: update migration-aware task schema validation in
  `src-tauri/src/backup.rs` without changing the backup/restore interaction;
  rerun `cargo test --manifest-path src-tauri/Cargo.toml backup`.

## 9. Integrated Verification

- [ ] 9.1 Run `pnpm test`, `pnpm build`,
  `cargo test --manifest-path src-tauri/Cargo.toml`,
  `cargo check --manifest-path src-tauri/Cargo.toml`,
  `pnpm exec openspec validate manage-tasks-with-inherited-rates --strict`, and
  `git diff --check`; fix only failures caused by this change and record the
  exact results plus any manual Tauri limitation in the governed implementer
  report.
