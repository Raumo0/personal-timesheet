## Independent review plan

### Scope and inputs

- Review one governed task at a time against its checkbox wording, the complete `invoice-pdf-generation` delta spec, relevant design decisions, and only the current validated diff attributed to that task.
- Inspect canonical task state, validation evidence, implementation reports, and prior reviewer reports under `.agentic-workflow/`. Evidence must identify the current repository revision or validated diff and must not be missing, stale, failed, or skipped for a mandatory applicable gate.
- Confirm that source Client, Project, Task, time-entry, and Expense records remain unmodified by preview and export paths.
- For native domain tasks, inspect inclusive dates, ownership boundaries, archived work retention, active Expense eligibility, rate inheritance and overrides, integer rounding, totals, chart scales, and stable error categories.
- For PDF tasks, inspect text measurement, wrapping, page breaks, embedded-font licensing, selectable text, optional-section omission, chart legibility, A4 bounds, and representative rendered pages.
- For frontend tasks, inspect keyboard access, accessible names and summaries, error recovery, option-state fidelity, present-and-blank Invoice no. behavior, native-dialog cancellation, preview/export parity, and preservation of existing Reports navigation and Timesheet guards.
- Treat quiet-fintech aesthetics as a required human visual check in addition to deterministic layout evidence; subjective approval never replaces failed structural evidence.

### Verdict

- Record exactly `APPROVED` or `NEEDS_FIXES` for the current task and validated diff.
- `NEEDS_FIXES` lists every unresolved Important or Critical finding with file and line context, affected requirement or design decision, and required correction. Minor observations do not block only when explicitly labelled non-blocking.
- After fixes, rerun the task's focused checks and canonical validation, then obtain a fresh independent verdict for the new diff.
- Mark a task checkbox only after an independent reviewer records `APPROVED` for that task's current validated diff. Canonical checkbox state and reviewer reports remain under `.agentic-workflow/`; this plan does not duplicate them.
