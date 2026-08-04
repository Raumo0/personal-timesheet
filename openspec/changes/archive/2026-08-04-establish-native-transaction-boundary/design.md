## Context

`src/features/clients/database.ts` currently exports one `SqlDatabase` with
both `select` and `execute`. Client, Project, Task, and catalog-lifecycle
adapters receive that interface. The Client adapter uses it for a conditional
multi-step currency update and its Vitest harness simulates connection-local
`BEGIN` and `ROLLBACK`; the real plugin routes each invocation to an SQLx pool.

The catalog lifecycle already uses the safer shape: frontend preview reads use
`plugin-sql`, while `apply_catalog_lifecycle` opens the live database in Rust,
begins one `sqlx::Transaction`, rechecks the plan, and applies every update
through that transaction. The active weekly-time, Expense, and recurring-
Expense changes plan additional atomic stores but have not implemented them.
See `proposal.md` and the Client catalog delta for the approved scope.

## Goals / Non-Goals

**Goals:**

- Make raw frontend access read-only by default and make every remaining
  independent write dependency explicit.
- Give one Client update operation a typed native apply boundary without moving
  rate-rescaling business rules out of their existing TypeScript domain module.
- Prove commit, rollback, and stale-plan behavior against real temporary SQLite
  databases rather than a mock that assumes one frontend connection.
- Make unsafe frontend transaction control fail a deterministic repository
  check before review.

**Non-Goals:**

- Create a generic native repository, SQL batch RPC, transaction token, or
  frontend connection-pinning protocol.
- Move independent single-statement Client, Project, or Task create/update
  operations to Rust solely for architectural uniformity.
- Change forms, catalog navigation, error regions, migrations, backup format,
  or the existing lifecycle policy.
- Implement or edit the independently governed weekly-time, Expense, recurring-
  Expense, or exchange-rate changes.

## Decisions

### Split raw reads from explicitly independent statements

Relocate the existing plugin wrapper to
`src/infrastructure/sqlite/plugin-sql-adapter.ts` rather than adding a second
database owner. Export a `SqlReadDatabase` whose only query capability is
`select`, plus the existing checkpoint-and-close operation. Export independent
writes through a separate injected `IndependentSqlStatementExecutor`, not
through the read database object.

The executor accepts one statement and bind values. It rejects empty input,
more than one statement, and transaction-control verbs including `BEGIN`,
`COMMIT`, `ROLLBACK`, `SAVEPOINT`, `RELEASE`, and transactional `END`. Existing
single-statement catalog creates and non-atomic updates may use it. Multi-call
correctness must not depend on that executor.

Keeping `execute` on the general facade was rejected because every feature
would retain the unsafe capability. Removing all plugin writes was rejected
because independent statements already have atomic SQLite semantics and do not
need a larger native interface.

### Apply Client edits through one immutable native plan

Keep command parsing, normalization, currency precision, and
`rescaleRateOverride` in the existing TypeScript domain modules. The SQLite
Client adapter loads the active Client and every non-null Project and Task
override, validates all rows, and builds an immutable `ClientUpdatePlan` with:

- the target ID and expected Client lifecycle/version and billing state;
- the complete ordered expected override snapshot;
- the validated Client values and exact rescaled override values to save; and
- one update timestamp shared by every affected record.

The adapter immediately invokes `apply_client_update` and translates native
duplicate, missing, stale-plan, invalid-data, and persistence failures to the
existing `ClientCatalogError` contract. The command returns the saved Client
shape so the adapter does not need a post-commit read to report success.

Sending unconstrained SQL or a list of arbitrary mutations was rejected because
it would move the same unsafe transaction composition across IPC. Reimplementing
currency metadata and rescaling in Rust was rejected because it would duplicate
an existing tested business rule in another language.

### Recheck and apply on one Rust connection and transaction

Add `src-tauri/src/client_update.rs` with a path-based application function used
by the Tauri command and integration tests. It opens one `SqliteConnection`,
begins one transaction, loads the actual Client and complete ordered override
snapshot through `&mut Transaction<Sqlite>`, and compares them with the plan
before the first update. Any missing, added, archived, or changed record makes
the plan stale and performs no write.

After the recheck, update the Client and every planned override through the same
transaction. Commit only after all row-count checks succeed. On error, attempt
rollback and retain both the primary and rollback errors when both fail, matching
the lifecycle behavior. Register only the named `apply_client_update` command;
do not expose the path-based function or transaction as an IPC primitive.

A generic shared transaction command was rejected because it cannot enforce
domain invariants or safe plan shape. Reusing the plugin pool was rejected
because its individual invocations do not preserve connection identity.

### Enforce the boundary with an AST-aware repository check

Add `tools/check_native_transaction_boundary.mjs` using the already installed
TypeScript compiler API. It scans production TypeScript imports and call sites,
allows `@tauri-apps/plugin-sql` only in the approved adapter, rejects frontend
transaction-control SQL, and limits imports of the independent executor to an
explicit reviewed allowlist. Add `lint:native-transactions` to `package.json`.

Add `tests/test_native_transaction_boundary.py` with fixture cases for allowed
reads and single statements plus forbidden imports, transaction verbs, dynamic
or multi-statement writes, and the repository itself. Because unittest
discovery is already the always-applicable `target-contracts` validation gate,
the boundary remains enforced without changing the Validation Contract.

A regex-only source scan was rejected because comments, imports, templates, and
ordinary UI text create avoidable false results. Adding ESLint solely for this
rule was rejected because the existing TypeScript parser can provide the needed
syntax awareness without another dependency.

### Treat the boundary as a prerequisite for planned atomic stores

This change does not edit artifacts owned by other active changes. Before
implementing `record-weekly-time-entries`, `record-project-expenses`, or
`schedule-recurring-expenses`, run `$openspec-update-change` for each relevant
change so its SQLite tasks use named Rust commands for multi-step writes and the
read-only facade for queries. `suggest-expense-exchange-rates` inherits the
Expense-store boundary through its base change.

Editing those changes here was rejected because each has its own approved scope
and Human Gates. Allowing their current frontend transaction wording to proceed
was rejected because it would immediately recreate the defect.

## Risks / Trade-offs

- **A Client plan becomes stale between frontend reads and native apply** →
  Compare the complete expected snapshot before the first update and return a
  typed stale-plan failure without changing any row.
- **The independent executor is used for a logically multi-step operation** →
  Keep it separate from reads, restrict its import allowlist, reject transaction
  control and multiple statements, and require review of each allowlist change.
- **The source checker misclassifies TypeScript syntax** → Use the TypeScript
  AST and fixture tests instead of text-only matching.
- **A native transaction contends with the plugin pool** → Keep transactions
  bounded, open the established live database path, and surface lock failures
  through existing recoverable persistence handling.
- **The frontend plan contains malformed or incomplete persistence data** →
  Validate selected rows before invocation and have Rust reject incomplete,
  duplicate, unexpected, or row-count-mismatched plans before commit.

## Migration Plan

1. Add the boundary checker and focused fixtures so the current frontend
   transaction is captured as the intended failure.
2. Split and relocate the database adapter, migrate existing read consumers,
   and route approved independent statements through the restricted executor.
3. Add the Client update plan and adapter command seam while preserving the
   in-memory catalog and existing UI contract.
4. Add the Rust Client command and real-database integration coverage, then
   replace the frontend `BEGIN`/`COMMIT` path and its simulated transaction
   tests.
5. Run integrated validation and independent review. After this change is
   approved, reconcile the three dependent active changes before selecting any
   of their SQLite write tasks.

Rollback requires no database downgrade. Revert the adapter and command wiring
together while leaving data and migrations unchanged; do not retain the source
checker with an allowlist that contradicts the reverted architecture.
