## Independent review plan

### Scope and inputs

- Review one selected `tasks.md` checkbox at a time against its exact files,
  focused RED/GREEN command, `proposal.md`, all affected delta specs, and the
  relevant `design.md` decisions.
- Inspect the current task-bound diff for directional archive/restore rules,
  immutable plan scope, stale-plan handling, atomicity, unchanged unrelated
  records, timestamp preservation, migration normalization, hierarchy context,
  confirmation accuracy, accessible errors, Retry, and backup compatibility
  wherever applicable.
- Require the receipt-bound implementer report, execution state for
  `manage-catalog-archive-lifecycle`, and fresh
  `.agentic-workflow/validation-evidence.json` produced for the same worktree
  and diff. Evidence must report `overall_status: pass`, match the current
  Validation Contract and gate registry, and contain no failed or skipped
  applicable mandatory gate.
- For task 9.1, review integrated coverage across every delta requirement and
  confirm the broader frontend, Rust, OpenSpec, and diff checks. Treat an
  unperformed native Tauri smoke check only as the limitation recorded in
  `validation.md`, never as passed evidence.
- Keep canonical execution state and reviewer reports under
  `.agentic-workflow/`; this planning artifact does not hold verdict evidence.

### Verdict

- Record exactly `APPROVED` or `NEEDS_FIXES` in the receipt-bound independent
  reviewer report, together with the count of unresolved Important/Critical
  findings and actionable file/line findings when fixes are required.
- `APPROVED` requires the selected task's behavior, tests, design constraints,
  and validated diff to agree with no unresolved Important or Critical finding.
  Otherwise record `NEEDS_FIXES` and return the same task through a bounded fix
  and revalidation round.
- Keep the selected task checkbox unchecked until the implementation controller
  accepts an independent `APPROVED` verdict for that task's current validated
  diff. Approval for one task does not approve another task or the whole change.
