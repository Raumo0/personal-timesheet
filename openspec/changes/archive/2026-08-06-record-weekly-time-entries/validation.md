## Validation plan

### Deterministic evidence

- For each selected coverage-first task, run the exact focused command named in
  `tasks.md`. A passing focused test is sufficient when the behavior already
  exists. Otherwise record the expected behavior-specific RED, complete the
  indented GREEN/REFACTOR continuation within the same checkbox, and record the
  focused command passing before canonical validation.
- Tasks 12.1 and 15.1 must record passing results for `pnpm test`, `pnpm build`,
  `cargo test --manifest-path src-tauri/Cargo.toml`,
  `cargo check --manifest-path src-tauri/Cargo.toml`,
  `pnpm exec openspec validate record-weekly-time-entries --strict`, and
  `git diff --check` against the integrated change.
- After the selected task's final diff and implementer report are ready, the
  implementation controller must run `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json`.
  Evidence is acceptable only when it is fresh for the same worktree and diff,
  reports `overall_status: pass`, matches the current Validation Contract, and
  contains every applicable mandatory gate in declared order.
- Canonical execution state, implementer reports, and validator evidence remain
  under `.agentic-workflow/`; this artifact does not duplicate their results.

### Manual limitations

- Vitest verifies dates, grid structure, keyboard editing, selector grouping,
  autosave states, dialogs, focus, route guards, errors, and Retry, but it cannot
  prove native Tauri rendering or window-close interception. Task 12.1 records
  whether a native smoke check covered week navigation, entry/save/delete,
  Restore to edit, close guarding, horizontal containment, and light/dark
  appearance; an unperformed check remains an explicit limitation.
- Task 13.1 verifies the 1280px fit threshold, narrower overflow containment,
  stable row height during invalid input, emphasized totals, alternating rows,
  and the selector's accessible already-added state. Task 14.1 exercises the
  concrete native listener seam and proves Discard uses one terminal close
  operation without a recursive close-request; task 15.1 records whether the
  same behavior was also smoke-tested in a native Tauri window.
- Local-date tests exercise controlled time zones and boundaries but do not
  represent every operating-system locale rule.
- Migration and backup tests use controlled SQLite fixtures and do not replace a
  manual restore of valuable user data; no destructive manual restore is needed.
