## Independent review plan

### Scope and inputs

- Review one selected `tasks.md` checkbox at a time against its exact files,
  focused command and allowed passing or expected-failure result,
  `proposal.md`, the complete Client catalog delta, the relevant `design.md`
  decisions, and `validation.md`.
- For Client planning and adapter tasks, inspect complete expected-state
  capture, deterministic Project and Task ordering, reuse of existing currency
  rules, exact native plan serialization, no post-commit read, and translation
  to the existing catalog error contract. Require the delta scenario to retain
  every previously saved Client and descendant rate value after failure.
- For Rust tasks, inspect the code path from the named Tauri command to one
  path-based application function. Require one `SqliteConnection`, one
  `sqlx::Transaction`, all recheck reads and writes through that transaction,
  row-count validation, commit only after complete success, rollback on every
  primary failure, and retention of both errors when rollback also fails.
- Require real temporary-database integration evidence for Client commit,
  intermediate rollback, stale or changed plan scope with zero writes, and the
  catalog-lifecycle stale-plan precedent. Mock-only transaction evidence is not
  sufficient.
- For the frontend persistence boundary, require the raw database facade to
  expose no `execute`, direct `@tauri-apps/plugin-sql` import to exist only in
  the approved adapter, every retained write to be an allowlisted independent
  statement, and checkpoint-and-close behavior to remain intact.
- Inspect the AST checker and fixtures for bypasses through aliases, template
  expressions, dynamic statements, multiple statements, transaction-control
  variants, or an overbroad executor allowlist. Require no new ESLint or runtime
  dependency and no change to the Validation Contract registry.
- Reject any generic SQL batch command, frontend transaction handle, database
  migration, UI expansion, or implementation/edit of the separately governed
  weekly-time, Expense, recurring-Expense, or exchange-rate changes.
- Require the receipt-bound implementer report, execution state for
  `establish-native-transaction-boundary`, and fresh
  `.agentic-workflow/validation-evidence.json` for the same worktree and diff.
  Evidence must report `overall_status: pass`, match the current Validation
  Contract, contain no failed or skipped applicable mandatory gate, and state
  the native-smoke limitation accurately.
- For task 7.1, review integrated coverage across the delta requirement and all
  architectural decisions. Confirm the full frontend, Rust, OpenSpec, boundary,
  unittest, build, check, and diff commands passed. An unperformed Tauri smoke
  check remains a limitation, never passed evidence.
- Keep canonical execution state and reviewer reports under
  `.agentic-workflow/`; this planning artifact does not hold verdict evidence.

### Verdict

- Record exactly `APPROVED` or `NEEDS_FIXES` in the receipt-bound independent
  reviewer report, with the count of unresolved Important/Critical findings and
  actionable file/line findings when fixes are required.
- `APPROVED` requires the selected task's behavior, tests, design constraints,
  and validated diff to agree with no unresolved Important or Critical finding.
  Otherwise record `NEEDS_FIXES` and return the same task through a bounded fix
  and revalidation round.
- Keep the selected task checkbox unchecked until the implementation controller
  accepts an independent `APPROVED` verdict for that task's current validated
  diff. Approval for one task does not approve another task or the whole change.
