## 1. Environment selection

- [x] 1.1 Add coverage-first argument-routing tests, `src-tauri/tauri.dev.conf.json`, and the environment-aware `tools/run-tauri.mjs` wrapper wired through `package.json`; verify with `node --test tools/run-tauri.test.mjs`.
- [x] 1.2 Add the deterministic `tests/test_development_data_isolation.py` configuration contract and document supported commands and identifier-derived storage in `README.md`; verify with `python3 -m unittest tests/test_development_data_isolation.py -v`.

## 2. Integrated verification

- [x] 2.1 Verify resolved development and production configurations plus repository health with `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json`, `pnpm build`, and `cargo check --manifest-path src-tauri/Cargo.toml`.
