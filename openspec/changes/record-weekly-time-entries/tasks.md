Coverage-first checkbox rule: each checkbox includes its indented GREEN/REFACTOR continuation. A passing focused test is sufficient evidence; when behavior is absent, record the expected RED before implementation, then finish the same checkbox with the focused command passing.

## 1. Local Week and Duration Domain

- [ ] 1.1 COVERAGE-FIRST: add focused local Monday–Sunday, previous/current/next, month/year boundary, DST-adjacent, `H:MM`, minute-range, row-key, total, and daily-1440 cases in `src/features/time-entry/weekly-time-entry.test.ts`; a passing focused test is sufficient, otherwise record the expected RED, implement validated local dates, week arithmetic, discriminated work references, duration parse/format, and pure total rules in `src/features/time-entry/weekly-time-entry.ts`, then rerun `pnpm test -- src/features/time-entry/weekly-time-entry.test.ts` to GREEN and refactor only while it stays green.

## 2. Weekly Store Interface and In-Memory Adapter

- [ ] 2.1 COVERAGE-FIRST: define shared load/select/upsert/delete/eligibility/uniqueness/daily-limit/failure expectations and focused in-memory cases; accept an already-passing focused test or record the expected RED, then add the small `WeeklyTimeEntryStore` interface and errors and implement atomic in-memory behavior; run `pnpm test -- src/features/time-entry/in-memory-weekly-time-entry-store.test.ts` to GREEN and refactor only while it stays green.

## 3. Migration 5 and Backup Compatibility

- [ ] 3.1 COVERAGE-FIRST: extend `src-tauri/src/database.rs` tests for migration 5; accept a passing focused test or record the expected RED, add migration 5 without modifying migrations 1–4, then run `cargo test --manifest-path src-tauri/Cargo.toml database` to GREEN.
- [ ] 3.2 COVERAGE-FIRST: extend `src-tauri/src/backup.rs` tests for valid migration-5 time-entry schemas and migration-1 through migration-4 compatibility; accept a passing focused test or record the expected RED, update migration-aware compatibility without changing backup/restore interactions, then run `cargo test --manifest-path src-tauri/Cargo.toml backup` to GREEN.

## 4. Durable Weekly Store

- [ ] 4.1 COVERAGE-FIRST: add the shared store contract and focused SQLite/native cases for bounded reads, immutable upsert/delete plans, active-path and daily-total rechecks, commit, rollback, stale plans, ordering, and errors; accept a passing focused test or record the expected RED, then implement read queries through `SqlReadDatabase`, the frontend adapter, and named Rust `apply_weekly_time_entry_mutation` transaction command; run `pnpm test -- src/features/time-entry/sqlite-weekly-time-entry-store.test.ts` and the focused Rust command test to GREEN.

## 5. Time Entry Cell

- [ ] 5.1 COVERAGE-FIRST: add focused keyboard and accessibility cases in `src/features/time-entry/TimeEntryCell.test.tsx` for blank display, valid draft, invalid format, Escape, Enter, blur, read-only state, failed association, and focus restoration; run `pnpm test -- src/features/time-entry/TimeEntryCell.test.tsx`.
  - GREEN/REFACTOR: implement the focused controlled cell in `src/features/time-entry/TimeEntryCell.tsx` using the existing Input tokens and visible focus/error patterns; rerun the focused test.

## 6. Hierarchical Work Selector

- [ ] 6.1 COVERAGE-FIRST: add focused grouped Client → Project → Task interaction cases in `src/features/time-entry/WorkItemSelector.test.tsx` for direct Project choice, Task choice, active-only options, no General Task, selection reset, and repeated-row focus request; run `pnpm test -- src/features/time-entry/WorkItemSelector.test.tsx`.
  - GREEN/REFACTOR: implement `src/features/time-entry/WorkItemSelector.tsx` with the existing Select group, label, item, trigger, and focus patterns; rerun the focused test.

## 7. Weekly Grid, Rows, and Totals

- [ ] 7.1 COVERAGE-FIRST: add focused page cases in `src/features/time-entry/WeeklyTimesheetPage.test.tsx` for current local week, seven dated columns, Project/Task labels, empty week, transient rows, duplicate focus, blank cells, row/day/grand totals, and horizontal grid containment; run `pnpm test -- src/features/time-entry/WeeklyTimesheetPage.test.tsx`.
  - GREEN/REFACTOR: implement the initial grid, selector integration, loading/error/empty states, and calculated footer in `src/features/time-entry/WeeklyTimesheetPage.tsx`, reusing existing table, button, typography, spacing, and error components; rerun the focused test.

## 8. Autosave, Status, and Deletion

- [ ] 8.1 COVERAGE-FIRST: extend `src/features/time-entry/WeeklyTimesheetPage.test.tsx` with focused serialized Enter/blur save, status priority, aria-live, invalid draft, Escape, failed draft, Retry, valid-draft totals, and no-success-toast cases; run `pnpm test -- src/features/time-entry/WeeklyTimesheetPage.test.tsx`.
  - GREEN/REFACTOR: implement per-cell saved/draft state and the serialized save queue in `src/features/time-entry/use-weekly-autosave.ts` and integrate it with `src/features/time-entry/WeeklyTimesheetPage.tsx`; rerun the focused test.
- [ ] 8.3 COVERAGE-FIRST: add focused blank/`0:00` confirm, cancel, unsaved-clear, successful-delete, failed-delete, total, and Retry cases in `src/features/time-entry/WeeklyTimesheetPage.test.tsx`; run `pnpm test -- src/features/time-entry/WeeklyTimesheetPage.test.tsx`.
  - GREEN/REFACTOR: add the existing alert-dialog deletion flow to `src/features/time-entry/WeeklyTimesheetPage.tsx` without a global Save control; rerun the focused test.

## 9. Week and Leave Navigation Guards

- [ ] 9.1 COVERAGE-FIRST: add focused Previous/Current/Next, wait-for-save, failed/invalid focus retention, route Stay/Discard, empty-row non-dirty, and native-close guard-state cases in `src/features/time-entry/WeeklyTimesheetPage.test.tsx` and `src/features/time-entry/time-entry-navigation-guard.test.ts`; run `pnpm test -- src/features/time-entry/WeeklyTimesheetPage.test.tsx src/features/time-entry/time-entry-navigation-guard.test.ts`.
  - GREEN/REFACTOR: implement reusable guard state in `src/features/time-entry/time-entry-navigation-guard.ts` and wire week, router, and Tauri close coordination in `src/features/time-entry/WeeklyTimesheetPage.tsx`; rerun the focused tests.

## 10. Archived Rows and Restore to Edit

- [ ] 10.1 COVERAGE-FIRST: extend `src/features/time-entry/WeeklyTimesheetPage.test.tsx` with focused archived Client/Project/Task row, No longer active, disabled-cell, exact Restore to edit preview, success refresh, unchanged unrelated hierarchy, failure, and Retry cases; run `pnpm test -- src/features/time-entry/WeeklyTimesheetPage.test.tsx`.
  - GREEN/REFACTOR: integrate the existing `CatalogLifecycle` preview/apply seam into `src/features/time-entry/WeeklyTimesheetPage.tsx` and reload the row plus selector after successful restore; rerun the focused test.

## 11. Timesheet Route and Application Wiring

- [ ] 11.1 COVERAGE-FIRST: extend `src/app/AppShell.test.tsx` with focused lazy Timesheet route, compact density, injected weekly store/lifecycle, default-route, loading, and recoverable-load-error cases; run `pnpm test -- src/app/AppShell.test.tsx`.
  - GREEN/REFACTOR: replace the root `ProductPage` branch with lazy `WeeklyTimesheetPage` wiring in `src/app/AppShell.tsx`, inject `SqliteWeeklyTimeEntryStore` from `src/App.tsx`, reuse the existing `CatalogLifecycle` injection, and preserve `src/app/navigation.tsx` shell metadata; rerun the focused test.

## 12. Integrated Verification

- [ ] 12.1 Run `pnpm test`, `pnpm build`, `cargo test --manifest-path src-tauri/Cargo.toml`, `cargo check --manifest-path src-tauri/Cargo.toml`, `pnpm exec openspec validate record-weekly-time-entries --strict`, and `git diff --check`; fix only failures caused by this change and record the exact results plus any manual Tauri limitation in the governed implementer report.
