## Context

The client and project features already provide Zod-validated domain values,
small catalog interfaces with in-memory and SQLite adapters, additive database
migrations, explicit nullable rate overrides, and reusable desktop table and
dialog patterns. Project routing currently resolves a client by listing both
catalog states, and backup validation recognizes migrations 1 and 2. See
`proposal.md` for motivation and the delta specs for required behavior.

## Goals / Non-Goals

**Goals:**

- Add a deep task domain module whose small interface owns validation,
  inheritance, source resolution, and persistence mapping.
- Extend existing catalog seams for durable deep-link lookup rather than
  introducing route-specific data access.
- Keep task management visually and behaviorally consistent with the existing
  client and project screens.
- Evolve SQLite, currency rescaling, and backup validation without rewriting
  existing migrations or partially updating descendant rates.

**Non-Goals:**

- Introduce a generic catalog framework merely because tasks are the third
  catalog-shaped feature.
- Create a new visual identity, navigation destination, runtime dependency, or
  reusable routing framework.
- Snapshot effective rates for future time entries or invoices.
- Enforce time-entry eligibility, because time entry remains a later change.

## Decisions

### Store a nullable task override and resolve the full source chain once

Migration 3 adds a `tasks` table with `project_id`, normalized name, nullable
`hourly_rate_override_minor`, timestamps, and an archive marker. `NULL` means
inherit; any non-negative integer, including zero, means override. The task
domain exposes one pure resolver that accepts task, project, and client values
and returns both the effective amount and source (`task`, `project`, `client`,
or `unset`). It may reuse project resolution internally, but callers do not
compose nullable-value rules themselves.

Copying an effective rate into a task row was rejected because it would become
stale after ancestor changes and could not distinguish inheritance from an
equal override. A generic cross-feature rate engine was rejected because four
nullable values and sources do not justify a wider interface.

### Add a focused TaskCatalog at the established persistence seam

Create `TaskCatalog` with `list(projectId, filter)`, `create`, `update`, and
`archive`, backed by in-memory and SQLite adapters and tested through one shared
contract. The interface remains project-scoped, so callers cannot accidentally
move a task between projects. SQL update and archive statements include both
task and project identifiers.

The repeated client/project catalog mechanics are not extracted into a generic
repository. Their domain validation, ownership scopes, and currency behavior
remain different, so a shared CRUD abstraction would expose shallow mechanics
instead of hiding useful complexity.

### Extend client and project catalogs for durable route lookup

Add ID lookup to the existing `ClientCatalog` and `ProjectCatalog` interfaces
and both adapters. Lookup returns active or archived records and preserves each
catalog's parsing and error mapping. The existing project route and the new task
route use these interfaces instead of listing two states and searching in the
router. This makes the catalogs the single seam for durable record lookup and
keeps refresh and deep-link behavior testable.

Passing client and project objects only through navigation state was rejected
because refresh and direct links would lose context. Duplicating list-and-find
logic in another route was rejected because record lookup already belongs to
the catalog interfaces.

### Use a nested task route without adding primary navigation

Add `/clients/:clientId/projects/:projectId/tasks`. A project name becomes the
task-screen link while edit and archive remain separate row actions. The task
screen uses a compact Client → Project → Tasks breadcrumb, the existing page
header, active/archived filter, table density, empty/error states, confirmation,
and `TaskForm` dialog. Invalid route context displays an unavailable state with
a return path instead of an endless loading state.

The visual design extends the established Geist typography, spacing, color
tokens, focus behavior, and sentence-case copy. The breadcrumb is structural:
it communicates hierarchy and provides the return action. An inline expandable
task table was rejected because it would crowd project rate/actions and would
not provide durable project context for later time-entry links.

### Preserve descendants while making archived ancestors read-only

Archiving a client, project, or task changes only that record's `archived_at`.
Opening tasks beneath an archived client or project remains possible, but the
task screen disables create/edit/archive actions. Active tasks are not silently
archived when an ancestor is archived. Later time-entry selection must exclude
records with any archived ancestor by joining the hierarchy.

Cascading archival was rejected because it destroys the distinction between a
task intentionally archived by the user and one merely hidden by an ancestor.

### Rescale every explicit descendant override in one transaction

Generalize the existing exact precision-rescaling helper so the client update
can validate project and task overrides with the same pure rule. On a client
currency change, load all explicit project overrides and all explicit task
overrides joined through that client's projects, compute every new minor-unit
amount first, and only then begin one transaction that updates the client and
all descendants. Any lossy or unsafe value rejects the complete operation.

Separate project and task transactions were rejected because one could commit
before the other fails. Rounding was rejected because it changes billing intent.

### Add migration-3 backup compatibility without changing backup UX

Extend the additive migration list with the task table and partial unique index
on `(project_id, normalized_name)` for active tasks. Backup validation checks the
task schema only when the recorded data version includes migration 3. Valid
migration-1 and migration-2 backups remain acceptable and migrate after restore.
The generic complete-backup behavior already covers task rows, so no
`local-data-backup` requirement changes.

## Risks / Trade-offs

- **A deep link refers to a missing or mismatched client/project pair** → Use
  catalog lookup through both identifiers and show a bounded unavailable state.
- **One task override cannot be represented in a lower-precision currency** →
  Validate every descendant before writing and reject the whole client update.
- **Active tasks remain stored beneath archived ancestors** → Make historical
  screens read-only and require future selectors to filter every ancestor.
- **A third catalog increases repeated persistence code** → Keep the focused
  interface now; extract only after a concrete shared deep interface appears.
- **Task UI can drift from the established product identity** → Reuse the
  project screen's components, tokens, density, interaction names, and error
  behavior; add only the hierarchy breadcrumb.

## Migration Plan

1. Add migration 3 without modifying migrations 1 or 2 so existing databases
   upgrade in place and fresh databases replay the full sequence.
2. Extend backup validation for task-aware migration-3 files while retaining
   compatibility with older valid backups.
3. Roll back application code by leaving the additive task table unused; never
   downgrade the database or delete retained task data.
