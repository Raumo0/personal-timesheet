# Validation Contract

This document is the sole repository registry for deterministic implementation
gates. Local orchestration and CI invoke `tools/agentic_workflow/validate.py`,
which reads the table below in declared order and emits JSON evidence.

Changing a gate, command, applicability rule, mandatory flag, order, or timeout
requires an exact preview and the Validation Contract Human Gate before
dependent work continues. Do not duplicate this registry in an agent profile,
skill, CI workflow, or separate Validation Manifest.

## Gate registry

| Order | Gate ID | Applicability | Mandatory | Timeout | Command |
|---:|---|---|---|---:|---|
| 10 | target-contracts | always | yes | 180 | `python3 -m unittest discover -s tests -v` |
| 20 | handoff-package | path:tools/architecture_handoff/tests | yes | 300 | `python3 -m unittest discover -s tools/architecture_handoff/tests -v` |
| 30 | openspec-strict | path:openspec | yes | 120 | `openspec validate --all --strict --no-interactive` |
| 40 | rust-backup | path:src-tauri | yes | 300 | `cargo test --manifest-path src-tauri/Cargo.toml backup` |

## Applicability

- `always` runs in every checkout.
- `path:<relative-path>` runs only when that repository path exists; otherwise
  evidence records `not-applicable`.
- An unavailable executable records `skipped`, never `not-applicable`.

## Evidence contract

Each run records repository identity, Git revision when available, contract
hash, generation time, overall status, and one ordered result per gate. Every
gate result includes applicability, mandatory status, command, result status,
duration, exit code when available, reason, and redacted material output.

Statuses are `pass`, `fail`, `skipped`, and `not-applicable`. A mandatory
`fail` or `skipped` result makes the run fail. Missing, stale, failed, or
unauthorized-skipped mandatory evidence cannot be waived.

## Usage

```bash
python3 tools/agentic_workflow/validate.py \
  --output .agentic-workflow/validation-evidence.json
```

The validator redacts common token, password, secret, and authorization values.
Evidence is still local implementation data: inspect it before sharing.
