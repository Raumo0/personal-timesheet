## 1. Native Backup Foundation

- [x] 1.1 Add `@tauri-apps/plugin-dialog`, SQLite-enabled direct `sqlx`, and Rust `tempfile` test support to `package.json`, `pnpm-lock.yaml`, `src-tauri/Cargo.toml`, and `src-tauri/Cargo.lock`; register the dialog plugin with only required open/save permissions in `src-tauri/capabilities/default.json`; verify with `pnpm build` and `cargo check --manifest-path src-tauri/Cargo.toml`.
- [x] 1.2 RED: add `src-tauri/src/backup.rs` tests using temporary directories and databases for a complete consistent snapshot, protected-path rejection, destination failure, and partial-file cleanup; run `cargo test --manifest-path src-tauri/Cargo.toml backup::tests::create` and confirm the expected failures.
- [x] 1.3 GREEN: implement the deep native backup service, canonical app database paths, `VACUUM INTO` snapshot creation, temporary-file finalization, and product error types in `src-tauri/src/backup.rs`; rerun the focused create tests and `cargo check --manifest-path src-tauri/Cargo.toml`.

## 2. Safe Restore Engine

- [x] 2.1 RED: extend `src-tauri/src/backup.rs` tests for staging an intact backup, SQLite integrity failure, missing Personal Timesheet schema, and a migration version newer than the application supports; confirm failure with `cargo test --manifest-path src-tauri/Cargo.toml backup::tests::validate`.
- [x] 2.2 GREEN: implement app-owned staging, read-only `PRAGMA quick_check`, schema/migration compatibility validation, safe preview metadata, and staged-file cleanup; rerun the focused validation tests.
- [x] 2.3 RED: add restore-commit tests for recovery-copy creation, complete replacement, obsolete WAL/SHM cleanup, simulated replacement failure, and rollback to the current database; confirm failure with `cargo test --manifest-path src-tauri/Cargo.toml backup::tests::commit`.
- [x] 2.4 GREEN: implement the rollback-safe staged swap and recovery copy in the existing native backup service; rerun all `backup::tests` and refactor only while green.
- [x] 2.5 Add narrow Tauri commands for create, stage/validate, cancel staged restore, and commit/relaunch in `src-tauri/src/lib.rs`; cover command input/output serialization where practical and verify with `cargo test --manifest-path src-tauri/Cargo.toml`.

## 3. Frontend Backup Service

- [ ] 3.1 RED: create `src/features/backup/tauri-backup-service.test.ts` for save/open dialog cancellation, native command arguments, backup success, staged preview, SQL checkpoint/close ordering, commit, and translated failures; run the focused test and confirm it fails before the adapter exists.
- [ ] 3.2 GREEN: add the small `BackupService` interface and domain result/error types in `src/features/backup/backup-service.ts`, plus the production dialog/native adapter in `src/features/backup/tauri-backup-service.ts`; extend `src/features/clients/database.ts` only with the database checkpoint/close seam required by confirmed restore; rerun the focused adapter tests.
- [ ] 3.3 Add `src/features/backup/in-memory-backup-service.ts` for Settings tests with controllable success, cancellation, preview, and failure behavior; keep it conformant with the production interface through shared contract tests.

## 4. Settings Data Workspace

- [ ] 4.1 RED: create `src/features/backup/SettingsDataPage.test.tsx` for the unencrypted-file notice, backup success/cancellation/failure, restore selection, compatible preview, incompatible-file failure, replacement warning, and confirmation cancellation; run the focused test and confirm the intended failures.
- [ ] 4.2 GREEN: implement the Settings Data panel in `src/features/backup/SettingsDataPage.tsx` using existing Button and AlertDialog primitives, with explicit pending/success/error states and no invented dashboard decoration; make the focused tests pass.
- [ ] 4.3 RED: extend the page test with restore commit failure, preserved current-data messaging, retry, and disabled duplicate actions while an operation is pending; confirm the new scenarios fail for the intended missing behavior.
- [ ] 4.4 GREEN: implement recovery and retry states in the existing Settings Data page and service seam; rerun the focused page tests and refactor only while green.

## 5. Application Integration and Audit

- [ ] 5.1 RED: extend `src/app/AppShell.test.tsx` to require the real Settings Data workspace and an injected in-memory backup service while preserving navigation and keyboard behavior; confirm failure with `pnpm test -- src/app/AppShell.test.tsx`.
- [ ] 5.2 GREEN: route Settings through the existing shell, inject the production backup service from `src/App.tsx`, and keep other placeholder routes unchanged; rerun `pnpm test -- src/app/AppShell.test.tsx` and the complete `pnpm test` suite.
- [ ] 5.3 Audit the new Settings and dialog flows against `frontend-design`, freshly fetched `web-design-guidelines`, and applicable Tauri/Vite portions of `vercel-react-best-practices`; resolve relevant accessibility, destructive-action, async-state, and bundle findings with focused tests after behavioral changes.

## 6. Verification and Handoff

- [ ] 6.1 Run `pnpm test`, `pnpm build`, `cargo test --manifest-path src-tauri/Cargo.toml`, `cargo check --manifest-path src-tauri/Cargo.toml`, and `openspec validate add-safe-backup-restore --strict`; resolve every relevant failure.
- [ ] 6.2 Run the native application with `pnpm tauri dev`; verify backup cancellation, successful backup, damaged/newer-file rejection, restore confirmation cancellation, successful round trip with client data, restart, and rollback behavior; inspect light and dark themes, then stop all development processes.
- [ ] 6.3 Update `.workspace/WORKPLAN.md`, inspect `git diff --check` and `git status --short`, and commit the independently understandable native engine, frontend service, Settings UI, and final verification slices with Conventional Commits.
