## Purpose

Provides a safe local path for reviewing and importing a large structured Personal Timesheet dataset without manual re-entry.

## ADDED Requirements

### Requirement: Accept one versioned import manifest
The importer SHALL accept a local JSON manifest with a supported schema version and explicit Clients, Projects, Tasks, time entries, and Expenses. Identifiers SHALL be stable within the manifest, hierarchy references SHALL resolve, dates and currencies SHALL use application-supported formats, monetary values SHALL use exact integer minor units, and each time entry or Expense SHALL have exactly one valid target.

#### Scenario: Validate a complete hierarchy
- **WHEN** a manifest contains uniquely identified Clients, their Projects, their Tasks, and records referencing those identifiers
- **THEN** validation accepts the hierarchy and reports deterministic entity counts

#### Scenario: Reject an unsupported or malformed manifest
- **WHEN** the schema version is unsupported, a required value is malformed, an identifier is duplicated, or a reference does not resolve
- **THEN** the importer reports every deterministically discoverable validation error and writes nothing

#### Scenario: Preserve inherited rates
- **WHEN** a Client rate or a Project or Task override is omitted with `null`
- **THEN** the imported catalog preserves that null value so normal application inheritance remains effective

### Requirement: Preview without writing by default
Running the importer without an apply option SHALL validate the whole manifest, inspect the selected target, and print a deterministic preview containing the target environment or path, entity counts, total time, Expense totals grouped by billing currency, and whether the target is eligible. Preview SHALL NOT create or modify a database.

#### Scenario: Preview a valid import
- **WHEN** a valid manifest and an eligible existing database are selected without apply
- **THEN** the command exits successfully after printing the preview and the database remains byte-for-byte unchanged

#### Scenario: Preview an ineligible target
- **WHEN** the selected database is missing, incompatible, contains application records, or appears to be in active use
- **THEN** the preview identifies why apply is unavailable and writes nothing

### Requirement: Import atomically into an empty application database
Apply SHALL require a valid manifest and an existing compatible Personal Timesheet database with no Client, Project, Task, time-entry, or Expense records. It SHALL insert the complete dataset in one transaction using the same stored hierarchy, normalization, timestamps, currency, duration, rate, and Expense invariants as the application. Any failure SHALL roll back all imported records.

#### Scenario: Apply a valid manifest
- **WHEN** the user explicitly applies a valid manifest to an eligible development or explicit-path database
- **THEN** all manifest records become available to the application and the command reports the committed counts and totals

#### Scenario: Reject a non-empty database
- **WHEN** any application record already exists in the target database
- **THEN** apply refuses to merge, replace, or delete existing data

#### Scenario: Roll back a failed write
- **WHEN** a constraint or write failure occurs after the transaction begins
- **THEN** none of the manifest records remain in the target database

### Requirement: Protect production imports
The importer SHALL distinguish development, production, and explicit file targets. Applying to the production identity SHALL require both the normal apply option and a separate exact production acknowledgement. Preview SHALL remain available without that acknowledgement.

#### Scenario: Omit production acknowledgement
- **WHEN** apply targets production without the exact additional acknowledgement
- **THEN** the importer refuses before beginning a write transaction

#### Scenario: Acknowledge production explicitly
- **WHEN** a valid eligible production import includes both required apply controls
- **THEN** the importer may commit the same validated manifest that was previewed

### Requirement: Operate locally without a service
Import SHALL read a local manifest and SQLite database directly on the same device. It SHALL NOT open a listening port, send data over a network, expose a remote API, or modify the running application's process.

#### Scenario: Import without network access
- **WHEN** the device is offline and the application is closed
- **THEN** preview and eligible apply operations remain available from local files
