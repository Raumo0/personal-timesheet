## Validation plan

### Deterministic evidence

- For each selected task, run the exact focused command named in `tasks.md`.
  A passing result is sufficient evidence that the selected behavior already
  exists. If a new behavior is not yet present, record only its expected
  failures before implementation; unexpected failures remain invalid evidence.
- Task 9.1 must record passing results for `pnpm test`, `pnpm build`,
  `cargo test --manifest-path src-tauri/Cargo.toml`,
  `cargo check --manifest-path src-tauri/Cargo.toml`,
  `pnpm exec openspec validate manage-catalog-archive-lifecycle --strict`, and
  `git diff --check` against the integrated change.
- Tasks 10.1 and 10.2 run the focused SQLite lifecycle and AppShell command.
  Task 10.1 accepts either a passing command or exactly the two intended
  behavior failures; task 10.2 records the same command passing afterward.
- After the selected task's final diff and implementer report are ready, the
  implementation controller must run `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json`.
  Evidence is acceptable
  only when it is fresh for the same worktree and diff, reports
  `overall_status: pass`, matches the current Validation Contract, and contains
  every applicable mandatory gate in declared order.
- Canonical execution state, implementer reports, and validator evidence remain
  under `.agentic-workflow/`; this artifact does not duplicate their results.

### Manual limitations

- Vitest verifies confirmation copy, affected hierarchy, keyboard actions,
  focus, persistent errors, and Retry, but it cannot prove native Tauri
  rendering. Task 9.1 records whether a native smoke check covered Client,
  Project, and Task archive/restore in light and dark appearance; an unperformed
  check remains an explicit limitation.
- Migration and backup tests use controlled SQLite fixtures. They do not replace
  manually upgrading or restoring valuable user data, and this change requires
  no destructive manual data operation.
