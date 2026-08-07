## Validation plan

### Deterministic evidence

- `node --test tools/run-tauri.test.mjs` proves development argument injection and production command preservation.
- `python3 -m unittest tests/test_development_data_isolation.py -v` validates identities, visible names, supported commands, and documentation.
- `/Users/admin/projects/personal-timesheet2/node_modules/.bin/openspec validate separate-development-data --strict --no-interactive` validates all planning artifacts.
- `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json` records canonical per-task evidence.
- `pnpm build` and `cargo check --manifest-path src-tauri/Cargo.toml` prove the application still builds.
- Canonical evidence and reviewer reports remain under `.agentic-workflow/`.

### Manual limitations

- Static checks prove the resolved identifiers and visible configuration, but they do not launch a signed macOS bundle or inspect user application-data directories.
- A final human smoke test should launch the supported development command, create one disposable record, and confirm production remains empty; this is not required to make deterministic checks pass.
