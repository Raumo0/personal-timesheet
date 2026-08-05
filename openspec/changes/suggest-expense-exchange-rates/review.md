## Independent review plan

### Scope and inputs

- Review one selected `tasks.md` checkbox at a time against its exact files,
  focused coverage-first command, its passing result, `proposal.md`, the Expense delta spec, and relevant
  `design.md` decisions.
- Inspect the task-bound diff for explicit-only network access, minimal request
  data, ECB series validation, one shared historical observation date, exact
  EUR direct/inverse/cross direction including HUF, bounded rate precision,
  stable errors, unchanged manual drafts, provenance transitions, accessible
  form state, and absence of a general webview HTTP permission where applicable.
- Require the receipt-bound implementer report, execution state for
  `suggest-expense-exchange-rates`, and fresh
  `.agentic-workflow/validation-evidence.json` produced for the same worktree
  and diff. Evidence must report `overall_status: pass`, match the current
  Validation Contract and gate registry, and contain no failed or skipped
  applicable mandatory gate.
- For task 8.1, review integrated coverage across every added expense-recording
  requirement and the frontend, Rust, OpenSpec, and diff checks. Treat live ECB
  and native presentation only as limitations recorded in `validation.md`,
  never as deterministic passed evidence.
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
