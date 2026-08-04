## Validation plan

### Deterministic evidence

- For each selected task, run the exact focused command named in `tasks.md`.
  Tasks 1.1, 2.1, 3.1, 4.1, and 5.1 may record only failures caused by their
  explicitly missing planned module, command seam, adapter, or checker. A
  passing focused test is also sufficient when the covered behavior already
  exists. Unexpected failures are invalid evidence.
- Client planning must pass
  `pnpm test -- src/features/clients/client-update-plan.test.ts
  src/features/projects/project.test.ts`; evidence must cover complete expected
  state, exact rescaling, zero, lossy precision, malformed rows, and ordering.
- Native atomicity must pass
  `cargo test --manifest-path src-tauri/Cargo.toml --test
  native_transaction_boundary` against real temporary SQLite files. Evidence
  must cover successful commit, intermediate failure rollback, stale and
  changed scope before any write, row-count checks, lifecycle stale-plan
  behavior, and preservation of both failures when rollback also fails.
- The frontend command and persistence split must pass the focused Client,
  plugin adapter, Project, Task, lifecycle, and backup Vitest commands in tasks
  3 and 4. Evidence must show that Client edits invoke only
  `apply_client_update`, the read facade has no `execute`, independent writes
  use their separate dependency, and no success path requires a post-commit
  read.
- The architecture boundary must pass both
  `python3 -m unittest tests.test_native_transaction_boundary -v` and
  `pnpm lint:native-transactions`. Fixture evidence must reject unauthorized
  plugin imports, executor imports, dynamic or multi-statement writes, and all
  frontend transaction-control forms while accepting approved reads and one
  independent bound statement.
- Task 7.1 must record passing results for
  `python3 -m unittest discover -s tests -v`,
  `pnpm lint:native-transactions`, `pnpm test`, `pnpm build`,
  `cargo test --manifest-path src-tauri/Cargo.toml`,
  `cargo check --manifest-path src-tauri/Cargo.toml`,
  `pnpm exec openspec validate establish-native-transaction-boundary --strict`,
  and `git diff --check` against the integrated change.
- Before independent review of each task, run
  `python3 tools/agentic_workflow/validate.py --output
  .agentic-workflow/validation-evidence.json`. Evidence is acceptable only when
  it is fresh for the same worktree and diff, reports `overall_status: pass`,
  matches the current Validation Contract, and contains every applicable
  mandatory gate in declared order. This change adds no Validation Contract
  gate; its repository boundary test runs through the existing always-
  applicable `target-contracts` gate.
- Canonical task state, command output, implementer reports, reviewer reports,
  and validator evidence remain under `.agentic-workflow/`; this artifact does
  not duplicate their results.

### Manual limitations

- Vitest verifies command selection, plan shape, error translation, and retained
  page context but does not execute the Tauri IPC runtime. A native smoke check
  may verify a normal Client currency edit with Project and Task overrides;
  record whether it was performed and do not describe an unperformed check as
  passed.
- Rollback and stale-plan failures use controlled temporary SQLite fixtures.
  The application has no safe production failure-injection control, so manual
  testing cannot reproduce those paths without risking local data. Automated
  Rust integration evidence is authoritative for them.
- The source checker proves repository import and SQL-call policy, not a
  property of arbitrary runtime-generated code. Dynamic independent write SQL
  is therefore forbidden instead of treated as manually validated.
- No migration, backup restore, or destructive data operation is required for
  this change.
