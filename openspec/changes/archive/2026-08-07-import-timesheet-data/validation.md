## Validation plan

### Deterministic evidence

- Focused `cargo test --manifest-path src-tauri/Cargo.toml data_import::manifest`, `data_import::target`, and `data_import::apply` commands prove validation, target safety, and atomic insertion.
- `python3 -m unittest tests/test_timesheet_data_import.py -v` exercises the built CLI against temporary initialized SQLite databases, including byte-stable preview, production refusal, and rollback.
- `/Users/admin/projects/personal-timesheet2/node_modules/.bin/openspec validate import-timesheet-data --strict --no-interactive` validates planning artifacts.
- `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json` records canonical per-task evidence.
- `pnpm build` and `cargo check --manifest-path src-tauri/Cargo.toml` prove repository integration.
- Canonical evidence and reviewer reports remain under `.agentic-workflow/`.

### Manual limitations

- Automated tests use synthetic manifests and temporary databases; they cannot verify the correctness of facts transcribed from a user's screenshots.
- Before a real production apply, the user must review the generated JSON and CLI preview. That external production-data write remains a separate Human Gate and is not performed by this change.
