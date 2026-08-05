## Validation plan

### Deterministic evidence

- For each selected coverage-first task, run the exact focused command named in
  `tasks.md`. A passing focused test is sufficient when the behavior already
  exists. Otherwise record the expected behavior-specific RED, complete the
  indented GREEN/REFACTOR continuation within the same checkbox, and record the
  focused command passing before canonical validation.
- Task 10.1 must record passing results for `pnpm test`, `pnpm build`,
  `cargo test --manifest-path src-tauri/Cargo.toml`,
  `cargo check --manifest-path src-tauri/Cargo.toml`,
  `pnpm exec openspec validate record-project-expenses --strict`, and
  `git diff --check` against the integrated change.
- After the selected task's final diff and implementer report are ready, the
  implementation controller must run `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json`.
  Evidence is acceptable only when fresh for the same worktree and diff,
  reporting `overall_status: pass`, matching the current Validation Contract,
  and containing every applicable mandatory gate in declared order.
- Canonical execution state, implementer reports, and validator evidence remain
  under `.agentic-workflow/`; this artifact does not duplicate their results.

### Manual limitations

- Vitest verifies form behavior, exact conversion outputs, table states,
  dialogs, focus, lifecycle previews, errors, and Retry, but it cannot prove
  native Tauri rendering. Task 10.1 records whether a native smoke check covered
  direct Client and Project Expenses, manual conversion in both edit directions,
  archive/restore, comfortable-width containment, and light/dark appearance; an
  unperformed check remains an explicit limitation.
- Currency tests use the runtime's supported `Intl` data and representative
  zero-, two-, and three-decimal currencies; they cannot prove every operating
  system ships identical locale display names.
- Migration and backup tests use controlled SQLite fixtures and do not replace a
  manual restore of valuable user data; no destructive manual restore is needed.
