## 1. Local Database Foundation

- [x] 1.1 Add `@tauri-apps/plugin-sql` and `zod` to `package.json`/`pnpm-lock.yaml`, add SQLite-enabled `tauri-plugin-sql` to `src-tauri/Cargo.toml`/`Cargo.lock`, and grant the required SQL permissions in `src-tauri/capabilities/default.json`; verify with `pnpm build` and `cargo check --manifest-path src-tauri/Cargo.toml`.
- [x] 1.2 RED: add focused migration-definition tests in `src-tauri/src/database.rs`; run `cargo test --manifest-path src-tauri/Cargo.toml` and confirm they fail because the client schema is absent.
- [x] 1.3 GREEN: define the version-1 client migration in `src-tauri/src/database.rs`, register it from `src-tauri/src/lib.rs`, and add the development database artifacts to `.gitignore`; rerun `cargo test --manifest-path src-tauri/Cargo.toml` and `cargo check --manifest-path src-tauri/Cargo.toml`.

## 2. Client Domain and Persistence Seam

- [x] 2.1 RED: create `src/features/clients/client.test.ts` covering normalized names, ISO currency codes, nullable rates, explicit zero, negative-rate rejection, and zero-/two-/three-decimal currency parsing; run `pnpm test -- src/features/clients/client.test.ts` and confirm the expected failures.
- [x] 2.2 GREEN: implement the Client types, Zod command/row schemas, name normalization, and exact rate parsing/formatting in `src/features/clients/client.ts`; rerun `pnpm test -- src/features/clients/client.test.ts` and refactor only while green.
- [x] 2.3 RED: create shared catalog contract tests in `src/features/clients/client-catalog.contract.ts` and `src/features/clients/in-memory-client-catalog.test.ts` for create, edit, active-name uniqueness, list filters, archive, and persistence errors; confirm failure with `pnpm test -- src/features/clients/in-memory-client-catalog.test.ts`.
- [x] 2.4 GREEN: add the small `ClientCatalog` interface and test adapter in `src/features/clients/client-catalog.ts` and `src/features/clients/in-memory-client-catalog.ts`; rerun the focused contract tests and refactor only while green.
- [x] 2.5 RED: add `src/features/clients/sqlite-client-catalog.test.ts` with a controlled SQL database adapter to verify bound statements, row decoding, active/archived queries, uniqueness translation, and error translation; confirm expected failures with `pnpm test -- src/features/clients/sqlite-client-catalog.test.ts`.
- [x] 2.6 GREEN: implement the lazy database connection and SQLite catalog adapter in `src/features/clients/database.ts` and `src/features/clients/sqlite-client-catalog.ts`; rerun all `src/features/clients/*.test.ts` tests.

## 3. Client Workspace

- [x] 3.1 Add the required shadcn/ui source components under `src/components/ui/` for labeled inputs, currency selection, table layout, form dialog, and archival confirmation; verify the generated components with `pnpm build` before adapting them.
- [x] 3.2 RED: create `src/features/clients/ClientsPage.test.tsx` for loading, empty, active, archived, create-with-rate, create-without-rate, explicit-zero, and validation-error behavior; run the focused test and confirm it fails before `ClientsPage` exists.
- [x] 3.3 GREEN: implement the shared form and initial catalog surface in `src/features/clients/ClientForm.tsx` and `src/features/clients/ClientsPage.tsx`; make the focused tests pass, keeping rates tabular and all fields explicitly labeled.
- [x] 3.4 RED: extend `ClientsPage.test.tsx` with edit, archive confirmation/cancel, load failure, save failure, preserved input, and retry scenarios; run it and confirm the new scenarios fail for the intended missing behavior.
- [x] 3.5 GREEN: implement the edit, archive, recovery, and retry states in the existing client form/page modules; rerun `pnpm test -- src/features/clients/ClientsPage.test.tsx` and refactor only while green.

## 4. Application Integration

- [x] 4.1 RED: extend `src/app/AppShell.test.tsx` to require a persistent Clients destination, active-route state, keyboard access, and an injected in-memory catalog; confirm failure with `pnpm test -- src/app/AppShell.test.tsx`.
- [x] 4.2 GREEN: add Clients to `src/app/navigation.tsx`, route it through the existing shell in `src/app/AppShell.tsx`, and supply the production catalog from `src/App.tsx`; rerun `pnpm test -- src/app/AppShell.test.tsx` and the complete `pnpm test` suite.
- [x] 4.3 Audit `src/features/clients/*.tsx`, `src/app/AppShell.tsx`, and the added UI primitives against the installed `frontend-design`, `web-design-guidelines`, and applicable Tauri/Vite portions of `vercel-react-best-practices`; resolve relevant findings and rerun focused tests after every behavioral correction.

## 5. Verification and Handoff

- [x] 5.1 Run `pnpm test`, `pnpm build`, `cargo test --manifest-path src-tauri/Cargo.toml`, `cargo check --manifest-path src-tauri/Cargo.toml`, and `openspec validate manage-clients-locally --strict`; resolve every relevant failure.
- [ ] 5.2 Run the native application with `pnpm tauri dev`, verify fresh initialization plus create/edit/zero-rate/archive/restart behavior, inspect light and dark themes, then stop all development processes.
- [x] 5.3 Update `.workspace/WORKPLAN.md` with the completed slice and next backup/restore priority, inspect `git diff --check` and `git status --short`, and commit implementation changes in independently understandable Conventional Commits.
