## Independent review plan

### Scope and inputs

- Review one selected `tasks.md` checkbox at a time against its exact files,
  focused coverage-first command, its passing result, `proposal.md`, the weekly delta spec, and the
  relevant `design.md` decisions.
- Inspect the current task-bound diff for local date-only arithmetic,
  Project-or-Task identity, positive-minute persistence, active-path checks,
  atomic daily limits, row reconstruction, transient-row handling, duration
  validation, serialized autosave, status truthfulness, deletion confirmation,
  navigation protection, archived-row behavior, accessibility, migration, and
  backup compatibility wherever applicable.
- Require the receipt-bound implementer report, execution state for
  `record-weekly-time-entries`, and fresh
  `.agentic-workflow/validation-evidence.json` produced for the same worktree
  and diff. Evidence must report `overall_status: pass`, match the current
  Validation Contract and gate registry, and contain no failed or skipped
  applicable mandatory gate.
- For task 12.1, review integrated coverage across every weekly-time-entry
  requirement and confirm the broader frontend, Rust, OpenSpec, and diff checks.
  Treat unperformed native Tauri, close-guard, and appearance checks only as the
  limitations recorded in `validation.md`, never as passed evidence.
- For task 13.1, inspect compact column sizing at the declared breakpoint,
  overflow below it, zebra-row and totals contrast in both themes, visible and
  non-color already-added selector state, unchanged repeated-row focus, and the
  absence of inline validation text or row-height movement.
- For task 14.1, trace the concrete Tauri close listener: unguarded requests must
  use the default close path, Stay must preserve state, and Discard must invoke
  exactly one terminal destruction operation without emitting a second guarded
  close request. For task 15.1, reconcile these refinements with the complete
  frontend, Rust, OpenSpec, transaction-boundary, and diff evidence.
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
