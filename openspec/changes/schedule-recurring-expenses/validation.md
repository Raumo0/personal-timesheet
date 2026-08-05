## Validation plan

### Deterministic evidence

- For each selected coverage-first task, run the exact focused command named in
  `tasks.md`. A passing focused test is sufficient when the behavior already
  exists. Otherwise record the expected behavior-specific RED, complete the
  indented GREEN/REFACTOR continuation within the same checkbox, and record the
  focused command passing before canonical validation.
- Pure recurrence tests must cover leap years, local date boundaries, inclusive
  ranges, month-end clamping, and distinct twice-monthly slots without reading
  the operating-system clock or using UTC date conversion.
- The shared store contract and SQLite tests must prove immutable snapshots,
  confirmed-plan atomicity, Schedule/date/slot idempotency, same-currency ready
  Expenses, different-currency pending occurrences, one-Expense completion,
  continuous catch-up, stale-state rejection, and rollback.
- Controller tests must use fake timers and explicit local dates to prove one
  serialized reconciliation path for initialization, focus, visibility, and
  local midnight without waiting for real time.
- Task 11.1 must record passing results for `pnpm test`, `pnpm build`,
  `cargo test --manifest-path src-tauri/Cargo.toml`,
  `cargo check --manifest-path src-tauri/Cargo.toml`,
  `pnpm exec openspec validate schedule-recurring-expenses --strict`, and
  `git diff --check` against the integrated change.
- After the selected task's final diff and implementer report are ready, run
  `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json`.
  Evidence is acceptable only when fresh for the same worktree and diff,
  reporting `overall_status: pass`, matching the current Validation Contract,
  and containing every applicable mandatory gate in declared order.
- Canonical execution state, implementer reports, and validator evidence remain
  under `.agentic-workflow/`; this artifact does not duplicate their results.

### Manual limitations

- Automated validation cannot prove generation while the application process is
  closed because this change deliberately adds no operating-system background
  service. Task 11.1 records this limitation and may manually confirm catch-up
  after closing the app across a due date or advancing a safe test clock.
- Vitest cannot prove native webview rendering or actual sleep/resume delivery.
  Task 11.1 records whether a native smoke check covered Schedule creation,
  confirmed backfill, disable/enable, `Needs conversion`, and route-independent
  reconciliation; an unperformed check remains explicit.
- Fixture tests can prove optional ECB-provider integration without live
  network access. No deterministic Schedule test depends on ECB availability or
  today's exchange-rate value.
- Migration and backup tests use controlled SQLite fixtures and do not replace a
  manual restore of valuable user data; no destructive manual restore is needed.
