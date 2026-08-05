## Independent review plan

### Scope and inputs

- Review one selected `tasks.md` checkbox at a time against its exact files,
  focused coverage-first command, its passing result, `proposal.md`, both delta specs, and relevant
  `design.md` decisions.
- Inspect the task-bound diff for explicit local dates, calendar recurrence,
  month-end slot identity, bounded materialization, confirmed configuration
  backfill, continuous catch-up, immutable snapshots, Schedule/date/slot
  idempotency, exact conversion, atomic lifecycle effects, and one
  application-level reconciler wherever applicable.
- Require the receipt-bound implementer report, execution state for
  `schedule-recurring-expenses`, and fresh
  `.agentic-workflow/validation-evidence.json` produced for the same worktree
  and diff. Evidence must report `overall_status: pass`, match the current
  Validation Contract and gate registry, and contain no failed or skipped
  applicable mandatory gate.
- For task 11.1, review integrated coverage across recurring scheduling and the
  modified expense-recording requirements plus the broader frontend, Rust,
  OpenSpec, and diff checks. Treat OS-background execution, native resume, and
  native presentation only as limitations recorded in `validation.md`, never
  as deterministic passed evidence.
- Reject any implementation that weakens ready Expense money invariants,
  silently backfills a changed/reenabled Schedule, pre-creates an unbounded
  future, auto-enables Schedules after catalog restore, or claims to run while
  the application process is closed.
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
