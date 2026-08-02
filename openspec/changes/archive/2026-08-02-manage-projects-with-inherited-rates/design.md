## Context

The client catalog already establishes Zod-validated domain values, a small
catalog interface with in-memory and SQLite implementations, migration-driven
schema initialization, and reusable rate parsing and formatting. Routing
currently exposes one Clients page, while database backup validation recognizes
the current client-only schema. See `proposal.md` for motivation and the delta
specs for observable behavior.

## Goals / Non-Goals

**Goals:**

- Extend the existing catalog pattern without introducing a generic repository
  framework before a third catalog proves the abstraction.
- Keep rate-mode resolution in one pure, testable domain module.
- Preserve the selected client in the route so refreshes and deep links retain
  project context.
- Evolve the SQLite and backup schema checks safely.

**Non-Goals:**

- Store tasks or resolve task-level rates in this change.
- Restore archived projects or clients.
- Snapshot rates for future time entries or invoices.
- Add currency overrides below the client.

## Decisions

### Represent inheritance with a nullable override, never a copied rate

A project row stores `hourly_rate_override_minor`, where `NULL` means inherit
and any non-negative integer, including zero, means override. The effective rate
is computed from the project and its client rather than persisted. This keeps
inheritance live when the client default changes and preserves a zero override.
A separate copied effective value was rejected because it can become stale and
cannot reliably distinguish inheritance from an equal override.

### Resolve rate and source together

The project domain module exposes one pure resolution function returning both
the effective minor-unit amount and its source (`project`, `client`, or `unset`).
UI labels and later task resolution consume that result instead of repeating
nullable-value rules. The following task slice can apply the same pattern by
checking task, then project, then client.

### Keep currency owned by the client

Projects reference their client and store no currency. Forms and tables format
both inherited and overridden values using the current client currency. Per-
project currency was rejected because it would complicate aggregation,
invoicing, and the meaning of client billing defaults without supporting the
current use case.

### Add a focused project catalog beside the client catalog

Create a project feature module with a small catalog interface scoped by
`clientId`, plus in-memory and SQLite implementations following the tested
client pattern. Reuse the existing database connection seam and shared currency
rate helpers instead of creating another database loader or a premature generic
catalog. The client lookup remains explicit so project reads can return the
client currency and current inherited rate needed by the page.

### Use a client-detail route for durable UI context

Add `/clients/:clientId/projects` beneath the existing Clients navigation
destination. Client rows link to this route; the detail page contains a compact
header, active/archived filter, project table, and shared create/edit dialog.
The form uses an explicit two-option control labelled “Inherit client rate” and
“Override rate”. Inherited mode shows a disabled/read-only contextual value;
override mode shows the editable amount input.

### Preserve child records when a client or project is archived

Archiving changes only the selected record's `archived_at`. An archived client
makes its project workspace read-only but does not rewrite project archival
state. This preserves historical distinctions and avoids a destructive cascade;
future time-entry choices will exclude work beneath archived ancestors.

### Evolve the schema with an additive migration

Migration 2 creates `projects` with a client foreign key, timestamps, nullable
override, archive marker, and a partial unique index on normalized active names
per client. Backup validation accepts the new supported migration version and
verifies the project schema while retaining compatibility with valid older
backups that can be migrated after restoration.

### Preserve numeric overrides when client currency changes

When a client's currency changes, rescale every project override by the exact
power-of-ten difference between the old and new currency precisions in the same
transaction as the client update. This preserves `100.00 EUR` as `100 USD`
without implying foreign-exchange conversion. If reducing precision would drop
non-zero digits, reject the complete update and ask the user to adjust the
affected overrides first. Silent reinterpretation and rounding were rejected
because both alter billing intent.

## Risks / Trade-offs

- **A lower-precision currency cannot represent every existing override** →
  Rescale exactly in one transaction and reject the complete currency change
  when any override would lose precision.
- **A client can be archived while its projects remain active internally** →
  Treat ancestor availability as part of later selection queries and expose the
  archived client workspace as read-only.
- **Project and client catalogs may initially repeat persistence mechanics** →
  Keep their interfaces consistent and extract shared machinery only after task
  implementation reveals a stable third use case.

## Migration Plan

1. Add migration 2 without modifying migration 1 so existing databases upgrade
   in place and fresh databases replay both versions.
2. Extend backup schema validation to recognize projects only when the recorded
   data version includes migration 2; older valid backups remain restorable.
3. Roll back application code by leaving the additive project table unused;
   never downgrade or delete user data.
