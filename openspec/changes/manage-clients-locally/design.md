## Context

The application currently has a React shell and placeholder product routes but
no persistence dependency, domain modules, or real product records. See
`proposal.md` for motivation and the capability specs for observable behavior.

This change crosses the React UI, the Tauri plugin boundary, local database
initialization, and validation. It establishes patterns that later projects,
tasks, time entries, and expenses will extend.

## Goals / Non-Goals

**Goals:**

- Establish one versioned local SQLite database owned by the application.
- Keep SQL, row decoding, normalization, and persistence errors behind a small
  client-catalog interface.
- Make the first real product surface visually consistent, accessible, and
  testable without a running native shell.
- Preserve exact billing-rate meaning, including unset and explicit zero.

**Non-Goals:**

- Generalize a repository framework before another catalog needs it.
- Implement projects, tasks, inherited rates, time entries, expenses, or data
  synchronization.
- Expose raw database files or implement backup and restore in this change.

## Decisions

### Use the official Tauri SQL plugin with Rust-owned migrations

Register the SQLite migration list in `src-tauri/src/lib.rs` and initialize the
plugin when the application starts. The frontend loads the same named database
through `@tauri-apps/plugin-sql`; Tauri applies pending migrations
transactionally before the catalog is used.

This keeps schema history in the native application and avoids custom Rust
commands that would only forward CRUD calls. A browser database or handwritten
Rust persistence layer would add a second storage model without product value.

### Put a deep client-catalog module at the persistence seam

Expose a small interface for listing, creating, updating, and archiving clients.
The production adapter owns SQL, identifiers, timestamps, normalization, row
decoding, and error translation. React screens receive domain-shaped results
and never issue SQL.

Use an in-memory adapter in UI tests. Production and test adapters make this a
real seam while keeping the interface identical for callers and tests. Do not
add a generic repository base class; later catalogs can extract shared behavior
only after repetition exists.

### Validate both commands and persisted rows with Zod

Creation and edit commands are parsed before persistence. Every SQLite row is
parsed before it becomes a Client. This treats UI values and local database
contents as separate untrusted inputs and prevents invalid values from leaking
into rendering or future billing calculations.

Persistence constraints remain the final integrity layer. Validation messages
use product language, while unexpected database failures become a small set of
catalog errors the UI can handle deliberately.

### Store rates as nullable integer minor units

Each client row contains a three-letter uppercase currency code and a nullable
integer hourly-rate amount in that currency's standard minor unit. `NULL`
means no default rate; `0` means an explicit zero rate. Formatting and parsing
use `Intl.NumberFormat` currency metadata rather than hardcoded separators or
decimal counts.

Floating-point storage was rejected because equality and later invoice totals
must be exact. Decimal strings were rejected because every calculation would
then require reparsing and a decimal arithmetic policy.

### Use stable text identifiers and explicit archival state

Generate UUID client identifiers in the application and store UTC timestamps
as ISO text. Client rows contain `created_at`, `updated_at`, and nullable
`archived_at` values. A partial case-insensitive uniqueness constraint protects
normalized active names while allowing a new active client to reuse an archived
client's name.

Archival is confirmed in the UI and never deletes the row. Restoring archived
clients is deliberately deferred because future project relationships affect
the correct restore behavior.

### Give Clients a restrained, data-first product surface

Add Clients to primary navigation between Timesheet and Reports. The page uses
the established Geist typography and application tokens: a consistent page
header, one primary “Add client” action, active/archived filters, and a compact
table with tabular numeric rates. Create and edit use one shared form surface;
archive uses an explicit confirmation.

The visual signature is a precise billing ledger rather than decorative art:
currency and rate information align consistently, empty and error states lead
to a next action, and no new font or graphic competes with dense future work
data.

### Keep asynchronous UI state local and explicit

The Clients route owns loading, loaded, empty, and failure states and refreshes
the catalog after successful mutations. It does not introduce SWR, global state,
or speculative caching for a single local database consumer. Independent reads
may run in parallel when useful, but correctness takes priority over premature
memoization.

## Risks / Trade-offs

- **A migration error can block the first real product screen** → Apply
  migrations transactionally and test initialization against a temporary
  database before wiring the UI.
- **Currency minor units vary by currency** → Derive accepted precision and
  display formatting from `Intl.NumberFormat`, and test zero-, two-, and
  three-decimal currencies.
- **Frontend SQL permissions increase the webview's local capability** → Grant
  only the SQL permissions required by the main window and keep all statements
  inside the catalog adapter.
- **The in-memory adapter can drift from SQLite behavior** → Share command and
  row schemas, and add focused SQLite integration tests for constraints and
  migrations.
- **Backup is not yet available once real data exists** → Keep this slice small,
  then prioritize the separately planned backup/restore change before extensive
  time-entry data accumulates.

## Migration Plan

1. Install and register the SQL plugin and its scoped capability permissions.
2. Add migration version 1 for the client table and active-name index.
3. Verify a fresh database and repeat startup against an already migrated
   database.
4. Ship the client catalog and Clients route only after persistence tests pass.

Rollback during development removes the unshipped local development database
and reverts the plugin registration. Once released, migrations are append-only;
the application must not silently downgrade an existing database.
