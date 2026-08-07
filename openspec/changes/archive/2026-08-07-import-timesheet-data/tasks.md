## 1. Manifest contract

- [x] 1.1 Add coverage-first tests and implement versioned manifest deserialization, complete deterministic validation, normalization, and preview summaries in `src-tauri/src/data_import.rs`; verify with `cargo test --manifest-path src-tauri/Cargo.toml data_import::manifest`.

## 2. Target safety and transaction

- [x] 2.1 Add coverage-first tests and implement cross-platform environment path resolution, compatible-empty database inspection, active-use detection, and production acknowledgement in `src-tauri/src/data_import.rs`; verify with `cargo test --manifest-path src-tauri/Cargo.toml data_import::target`.
- [x] 2.2 Add coverage-first integration tests and implement one-transaction insertion with rollback and post-write count verification in `src-tauri/src/data_import.rs`; verify with `cargo test --manifest-path src-tauri/Cargo.toml data_import::apply`.

## 3. Operator interface

- [x] 3.1 Add the thin `src-tauri/src/bin/import-timesheet-data.rs` CLI, `tools/data-import/schema-v1.json`, an example manifest, operator documentation, and `tests/test_timesheet_data_import.py`; verify with `python3 -m unittest tests/test_timesheet_data_import.py -v`.

## 4. Integrated verification

- [x] 4.1 Verify dry-run immutability, development apply, production refusal, rollback, and repository health with `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json`, `pnpm build`, and `cargo check --manifest-path src-tauri/Cargo.toml`.
