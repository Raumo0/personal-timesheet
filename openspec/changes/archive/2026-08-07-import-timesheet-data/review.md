## Independent review plan

### Scope and inputs

- Review only the manifest contract, local CLI, target protection, transaction behavior, fixtures, and operator documentation required by this change.
- Inspect the task's current diff, focused RED/GREEN evidence where applicable, and fresh canonical `.agentic-workflow/validation-evidence.json` from the assigned worktree.
- Treat any path that can modify a non-empty or unacknowledged production database, any partial-write outcome, or any network/listening behavior as an Important or Critical finding.

### Verdict

- Record `APPROVED` only when the current validated diff satisfies the selected task with zero unresolved Important or Critical findings; otherwise record `NEEDS_FIXES` with concrete findings.
- Mark a task checkbox only after the independent reviewer returns `APPROVED` for that task's current validated diff.
- Keep canonical execution state and reviewer reports under `.agentic-workflow/`.
