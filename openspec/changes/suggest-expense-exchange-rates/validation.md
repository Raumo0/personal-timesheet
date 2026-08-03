## Validation plan

### Deterministic evidence

- For each selected task, run the exact focused command named in `tasks.md`.
  RED tasks must record the expected failure before implementation;
  GREEN/REFACTOR tasks must record the same focused command passing afterward.
- Native provider tests must use injected HTTP fixtures and prove exact request
  parameters, shared observation dates, EUR direct/inverse/cross direction,
  HUF coverage, 12-decimal output, error translation, and bounded timeouts
  without depending on live ECB availability.
- Task 8.1 must record passing results for `pnpm test`, `pnpm build`,
  `cargo test --manifest-path src-tauri/Cargo.toml`,
  `cargo check --manifest-path src-tauri/Cargo.toml`,
  `pnpm exec openspec validate suggest-expense-exchange-rates --strict`, and
  `git diff --check` against the integrated change.
- After the selected task's final diff and implementer report are ready, run
  `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json`.
  Evidence is acceptable only when fresh for the same worktree and diff,
  reporting `overall_status: pass`, matching the current Validation Contract,
  and containing every applicable mandatory gate in declared order.
- Canonical execution state, implementer reports, and validator evidence remain
  under `.agentic-workflow/`; this artifact does not duplicate their results.

### Manual limitations

- Fixture tests cannot prove live ECB uptime, TLS routing, current series
  availability, or response compatibility. Task 8.1 records whether an optional
  native smoke check retrieved one exact-date EUR/HUF or EUR/USD rate and one
  non-EUR cross-rate; skipping it remains an explicit limitation and cannot fail
  deterministic validation.
- Vitest cannot prove native webview presentation. The same optional smoke check
  may cover explicit request, observation-date copy, manual adjustment, and
  failure fallback without sending Client, Project, description, or amount.
- No test should depend on today's rate value or make an unapproved provider
  request during normal automated validation.
