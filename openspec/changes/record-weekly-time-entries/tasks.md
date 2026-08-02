## 1. Local Week and Duration Domain

- [ ] 1.1 RED: add failing local Monday–Sunday, previous/current/next, month/year boundary, DST-adjacent, `H:MM`, minute-range, row-key, total, and daily-1440 cases in `src/features/time-entry/weekly-time-entry.test.ts`; run `pnpm test -- src/features/time-entry/weekly-time-entry.test.ts`.
- [ ] 1.2 GREEN/REFACTOR: implement validated local dates, week arithmetic, discriminated work references, duration parse/format, and pure total rules in `src/features/time-entry/weekly-time-entry.ts`; rerun the focused test.

## 2. Weekly Store Interface and In-Memory Adapter

- [ ] 2.1 RED: define shared load/select/upsert/delete/eligibility/uniqueness/daily-limit/failure expectations in `src/features/time-entry/weekly-time-entry-store.contract.ts` and add failing tests in `src/features/time-entry/in-memory-weekly-time-entry-store.test.ts`; run `pnpm test -- src/features/time-entry/in-memory-weekly-time-entry-store.test.ts`.
- [ ] 2.2 GREEN/REFACTOR: add the small `WeeklyTimeEntryStore` interface and errors in `src/features/time-entry/weekly-time-entry-store.ts`, then implement atomic in-memory behavior in `src/features/time-entry/in-memory-weekly-time-entry-store.ts`; rerun the focused test.

## 3. Migration 5 and Backup Compatibility

- [ ] 3.1 RED: extend `src-tauri/src/database.rs` tests for migration 5 with date-only entries, exactly one Project-or-Task foreign key, positive minutes through 1440, timestamps, and partial per-date uniqueness; run `cargo test --manifest-path src-tauri/Cargo.toml database`.
- [ ] 3.2 GREEN/REFACTOR: add migration 5 to `src-tauri/src/database.rs` without modifying migrations 1–4; rerun `cargo test --manifest-path src-tauri/Cargo.toml database`.
- [ ] 3.3 RED: extend `src-tauri/src/backup.rs` tests for valid migration-5 time-entry schemas and migration-1 through migration-4 compatibility; run `cargo test --manifest-path src-tauri/Cargo.toml backup`.
- [ ] 3.4 GREEN/REFACTOR: update migration-aware time-entry compatibility in `src-tauri/src/backup.rs` without changing backup/restore interactions; rerun `cargo test --manifest-path src-tauri/Cargo.toml backup`.

## 4. Durable Weekly Store

- [ ] 4.1 RED: add the shared store contract and focused SQLite cases in `src/features/time-entry/sqlite-weekly-time-entry-store.test.ts` for grouped active selection, archived historical rows, week bounds, upsert, delete, one-row identity, active-path recheck, atomic daily limit, ordering, and persistence errors; run `pnpm test -- src/features/time-entry/sqlite-weekly-time-entry-store.test.ts`.
- [ ] 4.2 GREEN/REFACTOR: implement bounded hierarchy and week queries plus transactional upsert/delete in `src/features/time-entry/sqlite-weekly-time-entry-store.ts` through `src/features/clients/database.ts`; rerun the focused test.

## 5. Time Entry Cell

- [ ] 5.1 RED: add failing keyboard and accessibility cases in `src/features/time-entry/TimeEntryCell.test.tsx` for blank display, valid draft, invalid format, Escape, Enter, blur, read-only state, failed association, and focus restoration; run `pnpm test -- src/features/time-entry/TimeEntryCell.test.tsx`.
- [ ] 5.2 GREEN/REFACTOR: implement the focused controlled cell in `src/features/time-entry/TimeEntryCell.tsx` using the existing Input tokens and visible focus/error patterns; rerun the focused test.

## 6. Hierarchical Work Selector

- [ ] 6.1 RED: add failing grouped Client → Project → Task interaction cases in `src/features/time-entry/WorkItemSelector.test.tsx` for direct Project choice, Task choice, active-only options, no General Task, selection reset, and repeated-row focus request; run `pnpm test -- src/features/time-entry/WorkItemSelector.test.tsx`.
- [ ] 6.2 GREEN/REFACTOR: implement `src/features/time-entry/WorkItemSelector.tsx` with the existing Select group, label, item, trigger, and focus patterns; rerun the focused test.

## 7. Weekly Grid, Rows, and Totals

- [ ] 7.1 RED: add failing page cases in `src/features/time-entry/WeeklyTimesheetPage.test.tsx` for current local week, seven dated columns, Project/Task labels, empty week, transient rows, duplicate focus, blank cells, row/day/grand totals, and horizontal grid containment; run `pnpm test -- src/features/time-entry/WeeklyTimesheetPage.test.tsx`.
- [ ] 7.2 GREEN/REFACTOR: implement the initial grid, selector integration, loading/error/empty states, and calculated footer in `src/features/time-entry/WeeklyTimesheetPage.tsx`, reusing existing table, button, typography, spacing, and error components; rerun the focused test.

## 8. Autosave, Status, and Deletion

- [ ] 8.1 RED: extend `src/features/time-entry/WeeklyTimesheetPage.test.tsx` with failing serialized Enter/blur save, status priority, aria-live, invalid draft, Escape, failed draft, Retry, valid-draft totals, and no-success-toast cases; run `pnpm test -- src/features/time-entry/WeeklyTimesheetPage.test.tsx`.
- [ ] 8.2 GREEN/REFACTOR: implement per-cell saved/draft state and the serialized save queue in `src/features/time-entry/use-weekly-autosave.ts` and integrate it with `src/features/time-entry/WeeklyTimesheetPage.tsx`; rerun the focused test.
- [ ] 8.3 RED: add failing blank/`0:00` confirm, cancel, unsaved-clear, successful-delete, failed-delete, total, and Retry cases in `src/features/time-entry/WeeklyTimesheetPage.test.tsx`; run `pnpm test -- src/features/time-entry/WeeklyTimesheetPage.test.tsx`.
- [ ] 8.4 GREEN/REFACTOR: add the existing alert-dialog deletion flow to `src/features/time-entry/WeeklyTimesheetPage.tsx` without a global Save control; rerun the focused test.

## 9. Week and Leave Navigation Guards

- [ ] 9.1 RED: add failing Previous/Current/Next, wait-for-save, failed/invalid focus retention, route Stay/Discard, empty-row non-dirty, and native-close guard-state cases in `src/features/time-entry/WeeklyTimesheetPage.test.tsx` and `src/features/time-entry/time-entry-navigation-guard.test.ts`; run `pnpm test -- src/features/time-entry/WeeklyTimesheetPage.test.tsx src/features/time-entry/time-entry-navigation-guard.test.ts`.
- [ ] 9.2 GREEN/REFACTOR: implement reusable guard state in `src/features/time-entry/time-entry-navigation-guard.ts` and wire week, router, and Tauri close coordination in `src/features/time-entry/WeeklyTimesheetPage.tsx`; rerun the focused tests.

## 10. Archived Rows and Restore to Edit

- [ ] 10.1 RED: extend `src/features/time-entry/WeeklyTimesheetPage.test.tsx` with failing archived Client/Project/Task row, No longer active, disabled-cell, exact Restore to edit preview, success refresh, unchanged unrelated hierarchy, failure, and Retry cases; run `pnpm test -- src/features/time-entry/WeeklyTimesheetPage.test.tsx`.
- [ ] 10.2 GREEN/REFACTOR: integrate the existing `CatalogLifecycle` preview/apply seam into `src/features/time-entry/WeeklyTimesheetPage.tsx` and reload the row plus selector after successful restore; rerun the focused test.

## 11. Timesheet Route and Application Wiring

- [ ] 11.1 RED: extend `src/app/AppShell.test.tsx` with failing lazy Timesheet route, compact density, injected weekly store/lifecycle, default-route, loading, and recoverable-load-error cases; run `pnpm test -- src/app/AppShell.test.tsx`.
- [ ] 11.2 GREEN/REFACTOR: replace the root `ProductPage` branch with lazy `WeeklyTimesheetPage` wiring in `src/app/AppShell.tsx`, inject `SqliteWeeklyTimeEntryStore` from `src/App.tsx`, reuse the existing `CatalogLifecycle` injection, and preserve `src/app/navigation.tsx` shell metadata; rerun the focused test.

## 12. Integrated Verification

- [ ] 12.1 Run `pnpm test`, `pnpm build`, `cargo test --manifest-path src-tauri/Cargo.toml`, `cargo check --manifest-path src-tauri/Cargo.toml`, `pnpm exec openspec validate record-weekly-time-entries --strict`, and `git diff --check`; fix only failures caused by this change and record the exact results plus any manual Tauri limitation in the governed implementer report.
