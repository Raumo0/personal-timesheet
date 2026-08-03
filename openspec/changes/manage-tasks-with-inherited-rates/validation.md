## Validation plan

### Deterministic evidence

- For each selected task, run the exact focused command named in `tasks.md`.
  RED/GREEN/REFACTOR tasks must record the expected failing behavior before
  implementation and the same focused command passing afterward.
- Task 9.1 must record passing results for `pnpm test`, `pnpm build`,
  `cargo test --manifest-path src-tauri/Cargo.toml`,
  `cargo check --manifest-path src-tauri/Cargo.toml`,
  `pnpm exec openspec validate manage-tasks-with-inherited-rates --strict`, and
  `git diff --check` against the integrated change.
- After the selected task's final diff and implementer report are ready, the
  implementation controller must run the canonical validator through
  `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json`.
  Evidence is acceptable only when it is fresh for the same worktree/diff,
  reports `overall_status: pass`, matches the current Validation Contract, and
  contains every applicable mandatory gate in declared order.
- Canonical execution state, implementer reports, and validator evidence remain
  under `.agentic-workflow/`; this artifact does not duplicate their results.

### Manual limitations

- Vitest can verify task interactions, accessible names, focus targets, route
  behavior, and read-only controls, but it cannot prove native Tauri rendering
  or platform dialog behavior. Task 9.1 records whether a native smoke check of
  Client → Project → Tasks navigation, form focus, archival confirmation, and
  light/dark appearance was performed; an unperformed check remains an explicit
  limitation and is not reported as passed.
- Backup compatibility tests use controlled SQLite fixtures. They do not replace
  a manual restore of valuable user data; no destructive restore is required
  for this change's implementation review.
