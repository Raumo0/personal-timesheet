## Independent review plan

### Scope and inputs

- Review only the development overlay, Tauri command wrapper, configuration contract, and documentation required by this change.
- Inspect the task's current diff, the exact task acceptance evidence, and fresh canonical `.agentic-workflow/validation-evidence.json` from the assigned worktree.
- Confirm production identity and build routing remain unchanged, normal development routing always adds the dev overlay, and no data migration or user-file mutation was introduced.

### Verdict

- Record `APPROVED` only when the current validated diff satisfies the selected task with zero unresolved Important or Critical findings; otherwise record `NEEDS_FIXES` with concrete findings.
- Mark a task checkbox only after the independent reviewer returns `APPROVED` for that task's current validated diff.
- Keep canonical execution state and reviewer reports under `.agentic-workflow/`.
