## 1. Project Domain Rules

- [ ] 1.1 RED: add failing inheritance, override, explicit-zero, validation,
  normalization, and exact currency-rescaling cases in
  `src/features/projects/project.test.ts`; run
  `pnpm test -- src/features/projects/project.test.ts`.
- [ ] 1.2 GREEN/REFACTOR: implement the smallest project schemas, domain types,
  effective-rate resolver, and exact rescaling helpers in
  `src/features/projects/project.ts`, reusing billing currency helpers from
  `src/features/clients/client.ts`; rerun
  `pnpm test -- src/features/projects/project.test.ts`.

## 2. Catalog Interfaces and In-Memory Behavior

- [ ] 2.1 RED: define shared create/edit/list/archive expectations in
  `src/features/projects/project-catalog.contract.ts` and failing focused tests
  in `src/features/projects/in-memory-project-catalog.test.ts`; run
  `pnpm test -- src/features/projects/in-memory-project-catalog.test.ts`.
- [ ] 2.2 GREEN/REFACTOR: add the small `ProjectCatalog` interface and errors in
  `src/features/projects/project-catalog.ts`, then implement
  `src/features/projects/in-memory-project-catalog.ts` with client-scoped active
  name uniqueness and archival; rerun the focused test.

## 3. SQLite Schema and Persistence

- [ ] 3.1 RED: extend `src-tauri/src/database.rs` tests for migration 2 with the
  project foreign key, nullable non-negative override, timestamps, and partial
  active-name uniqueness per client; run `cargo test database` from
  `src-tauri`.
- [ ] 3.2 GREEN/REFACTOR: add migration 2 to `src-tauri/src/database.rs` without
  editing migration 1; rerun `cargo test database` from `src-tauri`.
- [ ] 3.3 RED: add project catalog contract and persistence failure cases in
  `src/features/projects/sqlite-project-catalog.test.ts`, including inherited
  `NULL`, explicit zero, client scoping, and archival; run
  `pnpm test -- src/features/projects/sqlite-project-catalog.test.ts`.
- [ ] 3.4 GREEN/REFACTOR: implement
  `src/features/projects/sqlite-project-catalog.ts` through the existing
  `src/features/clients/database.ts` connection seam; rerun the focused test.
- [ ] 3.5 RED: add currency-change cases to
  `src/features/clients/sqlite-client-catalog.test.ts` for exact transactional
  project rescaling and rejection without partial updates; run
  `pnpm test -- src/features/clients/sqlite-client-catalog.test.ts`.
- [ ] 3.6 GREEN/REFACTOR: extend `src/features/clients/sqlite-client-catalog.ts`
  and its catalog error mapping to rescale project overrides atomically when
  currency precision changes; rerun the focused test.

## 4. Project Workspace UI

- [ ] 4.1 RED: add failing form interaction tests in
  `src/features/projects/ProjectForm.test.tsx` for explicit “Inherit client
  rate” and “Override rate” choices, read-only inherited context, unset client
  rate, validation, and zero override; run
  `pnpm test -- src/features/projects/ProjectForm.test.tsx`.
- [ ] 4.2 GREEN/REFACTOR: implement
  `src/features/projects/ProjectForm.tsx` with existing dialog, input, label,
  selection, and rate-formatting components; rerun the focused test.
- [ ] 4.3 RED: add failing workspace tests in
  `src/features/projects/ProjectsPage.test.tsx` for active/archived lists,
  effective-rate sources, empty/error states, create/edit/archive flows, and an
  archived client's read-only state; run
  `pnpm test -- src/features/projects/ProjectsPage.test.tsx`.
- [ ] 4.4 GREEN/REFACTOR: implement
  `src/features/projects/ProjectsPage.tsx`, preserving the established Clients
  page spacing, table density, confirmations, and accessible error handling;
  rerun the focused test.
- [ ] 4.5 RED: extend `src/features/clients/ClientsPage.test.tsx` and
  `src/app/AppShell.test.tsx` for project navigation and deep-link retention;
  run `pnpm test -- src/features/clients/ClientsPage.test.tsx src/app/AppShell.test.tsx`.
- [ ] 4.6 GREEN/REFACTOR: update `src/features/clients/ClientsPage.tsx`,
  `src/app/AppShell.tsx`, and `src/App.tsx` to link and route
  `/clients/:clientId/projects` with injected project catalog seams; rerun the
  focused tests.

## 5. Backup Compatibility and Verification

- [ ] 5.1 RED: extend `src-tauri/src/backup.rs` tests for valid migration-2
  project schemas, migration-1 backup compatibility, and malformed project
  schema rejection; run `cargo test backup` from `src-tauri`.
- [ ] 5.2 GREEN/REFACTOR: update schema validation and preview handling in
  `src-tauri/src/backup.rs` without changing the backup/restore interaction;
  rerun `cargo test backup` from `src-tauri`.
- [ ] 5.3 Run `pnpm test`, `pnpm build`, `cargo test` from `src-tauri`,
  `pnpm spec validate manage-projects-with-inherited-rates --strict`, and
  `git diff --check`; record any manual Tauri verification still required.
