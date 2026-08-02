## Context

Client and Project catalogs currently own independent `archive` mutations and
their screens provide separate Active/Archived tables and confirmation dialogs.
`manage-tasks-with-inherited-rates` adds the same pattern for Tasks and retains
active descendants beneath archived ancestors as transitional behavior. All
three levels use `archived_at` and the same local SQLite connection. See
`proposal.md` and the three delta specs for the approved lifecycle behavior.

## Goals / Non-Goals

**Goals:**

- Give hierarchy lifecycle one small domain interface and one atomic SQLite
  transaction boundary.
- Make the exact affected path or subtree available before confirmation.
- Extend the established catalog screens and hierarchy context without a new
  management destination or visual language.
- Normalize previously stored ancestor/descendant lifecycle inconsistencies.

**Non-Goals:**

- Generalize Client, Project, and Task CRUD behind one repository.
- Add permanent deletion, bulk selection, scheduled archival, or lifecycle
  provenance.
- Add Timesheet behavior or expose lifecycle policy through a remote API.

## Decisions

### Move archive and restore writes behind one CatalogLifecycle seam

Add a focused `CatalogLifecycle` interface for archive/restore planning and
execution over a discriminated Client, Project, or Task target. A lifecycle plan
contains the operation, target hierarchy, current states, and records that would
change. Client, Project, and Task screens request a plan for confirmation and
then execute that plan. Existing catalog interfaces remain the read/create/edit
owners; their direct archive methods are removed when callers move to the new
seam so there is not a second lifecycle authority.

A pure planner owns the directional rules: archive includes the target subtree,
while restore includes the target and only archived ancestors. It leaves already
archived descendants and unrelated records unchanged. The in-memory adapter and
SQLite adapter share contract cases built from this planner.

Duplicating cascade logic across three catalogs was rejected because Client
archive and Task restore cross multiple ownership levels. A generic CRUD
repository was rejected because only lifecycle is cross-cutting.

### Validate and apply one immutable lifecycle plan atomically

The plan records IDs and expected lifecycle states. Execution rechecks that
state, rejects a stale plan, and performs every required update as one unit. The
SQLite adapter uses one transaction; the in-memory adapter computes the complete
replacement before committing it. A persistence or stale-plan error changes no
record and leaves the UI on the same hierarchy with Retry, which reloads a fresh
plan before asking for confirmation again.

Best-effort sequential updates were rejected because they can expose a restored
Task beneath an archived Project or leave only part of an archive cascade
applied.

### Preserve archived timestamps that are already set

Archive changes only active records in the target subtree. A descendant that
was already archived keeps its existing `archived_at`; the operation does not
need provenance to distinguish why it is archived because restore never expands
downward. Restoring clears `archived_at` only for the target and required
ancestors represented in the confirmed plan.

Overwriting every descendant timestamp was rejected because it would erase the
record's earlier lifecycle history without improving the restore rules.

### Normalize legacy hierarchy state in migration 4

After the Task table from migration 3 exists, migration 4 archives any active
Project beneath an archived Client and any active Task beneath an archived
Project or Client. Each normalized descendant receives the nearest archived
ancestor's timestamp, while already archived records keep their timestamp. This
establishes the invariant before the new lifecycle interface is used. Backup
validation accepts the migration-4 data version while retaining compatibility
with valid older backups that migrate after restore.

Leaving legacy active descendants untouched was rejected because catalog
filters and future Timesheet eligibility would otherwise observe different
hierarchy rules for old and new data.

### Extend existing archived views with hierarchy-specific restore actions

Keep the current Active/Archived segmented tables. Active rows expose Archive;
archived rows expose Restore. The Client page is the hierarchy root, the Project
page retains its Client context, and the Task page retains the planned
Client → Project → Tasks breadcrumb. Confirmations use sentence-case action
copy and display the target plus either the complete descendant scope for
archive or each concrete ancestor restored with the target.

Mutation errors remain in the existing persistent catalog error region with a
Retry action; dialogs do not close as though the operation succeeded. This
extends the product's current Geist typography, table density, focus behavior,
and accessible alert patterns. A new global hierarchy tree and checkbox-based
restore dialog were rejected because they add navigation and bulk semantics
outside this slice.

## Risks / Trade-offs

- **A plan becomes stale before confirmation** → Recheck expected states and
  reload a fresh plan instead of applying a different scope silently.
- **Migration 4 encounters malformed hierarchy data** → Let migration fail as a
  unit and leave the previous database version intact.
- **Removing direct catalog archive methods touches three features** → Migrate
  contracts and screen callers in bounded TDD tasks before deleting the old
  methods.
- **A large Client subtree is expensive to preview** → Query only IDs, names,
  kinds, and lifecycle state; confirmations may summarize the complete subtree
  with counts instead of rendering an unbounded list.

## Migration Plan

1. Implement and contract-test lifecycle planning independently of UI callers.
2. Add migration 4 and backup compatibility without modifying migrations 1–3.
3. Route Client, Project, and Task archive/restore interactions through the new
   lifecycle seam, then remove direct archive methods from the catalog APIs.
4. Roll back application code by leaving normalized archive states and the
   additive migration in place; never downgrade or delete retained records.
