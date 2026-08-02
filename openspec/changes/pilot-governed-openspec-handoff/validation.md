## Validation plan

### Deterministic evidence

- `pnpm exec openspec instructions apply --change pilot-governed-openspec-handoff --json`
- `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json`

Canonical execution state and validator evidence remain under
`.agentic-workflow/`.

### Manual limitations

- A human reviews the pilot outcome before any default-schema change.
