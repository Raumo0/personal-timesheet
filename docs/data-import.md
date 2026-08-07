# Import timesheet data

The importer is a local operator tool. It reads one versioned JSON manifest and an existing, current, empty Personal Timesheet SQLite database. Preview is the default and never creates or modifies a database.

Close Personal Timesheet before preview or apply. Launch each development or production app once first so it creates and migrates its database. Review the manifest and preview before applying.

## Prepare a manifest

Copy `tools/data-import/example-v1.json` and follow `tools/data-import/schema-v1.json`. Use stable IDs, ISO dates, integer minutes, integer minor currency units, uppercase currency codes, and decimal-string Expense rates. The tool validates hierarchy, uniqueness, targets, currencies, dates, money, and rates before inspecting the database.

## Preview

Development database:

```bash
cargo run --manifest-path src-tauri/Cargo.toml --bin import-timesheet-data -- \
  --manifest /absolute/path/timesheet.json --development
```

Production database (preview needs no acknowledgement):

```bash
cargo run --manifest-path src-tauri/Cargo.toml --bin import-timesheet-data -- \
  --manifest /absolute/path/timesheet.json --production
```

Explicit database path:

```bash
cargo run --manifest-path src-tauri/Cargo.toml --bin import-timesheet-data -- \
  --manifest /absolute/path/timesheet.json \
  --database /absolute/path/personal-timesheet.db
```

The one-line JSON preview reports the target, target kind, manifest SHA-384 digest, entity counts, total minutes, Expense totals by billing currency, and eligibility. Missing, incompatible, non-empty, sidecar-active, or locked targets remain read-only and are reported as ineligible.

## Apply

Apply to development or an explicit non-production path by adding `--apply`:

```bash
cargo run --manifest-path src-tauri/Cargo.toml --bin import-timesheet-data -- \
  --manifest /absolute/path/timesheet.json --development --apply
```

Explicit path apply:

```bash
cargo run --manifest-path src-tauri/Cargo.toml --bin import-timesheet-data -- \
  --manifest /absolute/path/timesheet.json \
  --database /absolute/path/personal-timesheet.db --apply
```

Production additionally requires the exact acknowledgement:

```bash
cargo run --manifest-path src-tauri/Cargo.toml --bin import-timesheet-data -- \
  --manifest /absolute/path/timesheet.json --production --apply \
  --acknowledge-production com.personal.timesheet
```

An explicit path or hard link resolving to production receives the same protection. Apply rereads the manifest, checks its digest, revalidates the target under an exclusive lock, inserts all records in one transaction, verifies counts and totals, and rolls back on failure. It never merges, updates, replaces, or deletes existing records.
