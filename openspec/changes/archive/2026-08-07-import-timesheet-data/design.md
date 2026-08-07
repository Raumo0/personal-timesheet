## Context

Personal Timesheet already has one SQLite schema, migrations, and strict constraints, but no bulk-ingestion surface. The normal UI and Tauri commands are designed for interactive edits, while test fixtures and in-memory stores are not production import mechanisms. The importer must be useful to a local operator and AI-assisted transcription without becoming a second application API.

## Goals / Non-Goals

**Goals:**

- Make a manifest readable, diffable, deterministic, and safe to preview.
- Keep validation and insertion testable below the CLI boundary.
- Fail closed around non-empty, incompatible, production, or active databases.

**Non-Goals:**

- Merge, update, or replace existing application records.
- Infer ambiguous currency conversions or billing rates.
- Parse screenshots directly; transcription produces the manifest before this tool runs.

## Decisions

### Add a Rust binary beside the native domain

Add `src-tauri/src/bin/import-timesheet-data.rs` as a thin argument and output boundary over a reusable `data_import` library module. This keeps SQLite behavior in the same crate and uses existing `serde`, `serde_json`, and `sqlx` dependencies.

Alternative considered: a Python script writing SQLite directly. Rejected because it would duplicate domain validation and make Rust schema compatibility harder to test.

### Require an already initialized empty database

The application must be launched once to create and migrate the target. The importer verifies the migration metadata and required schema, then requires all five application tables to be empty. It never creates schema, runs a parallel migration engine, or replaces data.

Alternative considered: create a database from migrations inside the importer. Rejected because Tauri's migration bookkeeping would be duplicated and could drift.

### Use exact storage-oriented JSON with friendly preview

Schema version 1 uses explicit string identifiers, ISO local dates, integer minutes, uppercase currency codes, integer minor units, nullable hourly-rate minor units, and decimal-string applied Expense rates. Creation timestamps are assigned consistently by the importer; archived records are outside this initial-population slice. A checked-in JSON Schema and example make AI-generated manifests reviewable.

Alternative considered: accept formatted money and `H:MM`. Rejected because locale and currency precision would add ambiguity before the first import path is proven.

### Separate pure validation, target inspection, and transaction apply

Manifest validation collects independent errors before opening a write transaction. Target inspection is read-only and produces the same summary used by preview and apply. Apply revalidates the target, begins one transaction, inserts in dependency order, verifies committed counts, and rolls back on any error.

### Make production acknowledgement explicit

Environment aliases resolve to identifier-derived platform paths: production is `com.personal.timesheet`, development is `com.personal.timesheet.dev`. `--apply` is sufficient for development or an explicit file path; production additionally requires `--acknowledge-production com.personal.timesheet`. An explicit path that resolves to the production database receives the same protection.

## Risks / Trade-offs

- [The application is open during import] → Refuse when SQLite sidecars or an immediate exclusive-lock probe indicate active use.
- [A handcrafted manifest bypasses UI conveniences] → Validate domain invariants and rely on database constraints as a second boundary.
- [Environment path rules vary by platform] → Isolate path resolution and test macOS, Windows, and Linux cases with injected environment values.
- [Two separately prepared previews differ] → Print a manifest digest and require apply to re-read and validate the current file.

## Migration Plan

The tool adds no database migration. It operates only against the current compatible schema. Removing the binary, library module, schema, and documentation fully rolls back the feature without changing application data.
