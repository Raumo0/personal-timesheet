## Context

`/expenses` currently renders the generic placeholder. Client and Project data
already use durable IDs, billing currencies, additive SQLite migrations, and
active/archived tables. The active catalog-lifecycle change establishes one
preview/apply seam for atomic hierarchy changes, while the weekly-time change
occupies migration 5. See `proposal.md` and `specs/expense-recording/spec.md`
for the approved behavior.

## Goals / Non-Goals

**Goals:**

- Keep target validation, decimal conversion, rounding, and row mapping in
  pure testable domain modules.
- Give workspace loading and Expense CRUD one small persistence interface while
  retaining CatalogLifecycle as the only archive/restore write authority.
- Preserve exact saved money and target history without duplicating Client or
  Project ownership.
- Extend the established Expenses route, table, form, dialogs, focus, and
  recoverable error language rather than introduce another UI system.

**Non-Goals:**

- Build a generic accounting ledger, currency-rate provider, recurrence engine,
  or invoice model.
- Generalize Client, Project, Task, Time Entry, and Expense persistence behind
  one repository.
- Add a new decimal, form, state-management, or table dependency.

## Decisions

### Store a discriminated Client-or-Project target

Migration 6 adds `expenses` after the planned migration 5. Each row has exactly
one nullable foreign key: `client_id` for a direct Client Expense or
`project_id` for a Project Expense. A database check requires exactly one. The
Client for a Project Expense is resolved through the Project relationship; it
is not duplicated on the row.

The remaining columns are local `expense_date`, trimmed `description`, original
currency and positive minor amount, saved billing currency and positive minor
amount, applied-rate decimal text, `rate_source`, nullable `rate_observed_on`,
`rate_manually_adjusted`, timestamps, and `archived_at`. Manual conversion
records `rate_source` as `manual`; the nullable observation date and adjustment
flag reserve provenance for the approved follow-up provider slice. Decimal text
preserves the user's canonical rate without binary floating-point conversion.

Storing both Client and Project IDs was rejected because they can disagree.
Making Project mandatory was rejected because some costs belong to the Client
without a specific Project.

### Deepen money behavior behind pure functions

Extract generic currency precision, money parsing, formatting, fixed-scale rate
parsing, conversion, and half-up rounding into `src/features/money/money.ts`.
Keep the existing Client rate helpers as compatibility wrappers so current
Client, Project, and planned Task callers do not learn a second behavior. Use
integer/BigInt intermediate arithmetic and reject results outside safe stored
minor-unit bounds.

An Expense command carries both authoritative minor amounts and the applied
rate. Pure validation proves their currencies and precision are supported. A
rate edit derives and rounds the billing amount; a billing-amount edit derives
the displayed rate without changing either saved amount later.

Using JavaScript floating-point multiplication was rejected because cross-rate
precision and half-unit rounding become input-dependent. Adding a decimal
package was rejected because fixed-scale positive conversion is bounded here.

### Give Expense persistence one deep store interface

Add `ExpenseStore` with operations to load one active or archived workspace
snapshot, create an Expense, and update an Expense. A snapshot contains rows,
current hierarchy states, and one sorted active Client → Project target tree so
the page does not compose N+1 catalog calls. In-memory and SQLite adapters share
one behavioral contract for validation, ordering, stale target state, and
persistence failures.

Archive and restore methods do not belong to this interface. Extend the planned
`CatalogLifecycle` target and immutable plan records with Expense nodes. Its
archive planner includes Expense descendants for Client and Project targets;
its restore planner includes a selected Expense and only required ancestors.
This keeps one hierarchy write authority and one atomic transaction.

Adding lifecycle methods to both ExpenseStore and CatalogLifecycle was rejected
because callers could bypass cascade and stale-plan validation.

### Preserve the billing snapshot on each Expense

The saved billing currency and billing amount remain authoritative even if the
Client later changes currency. Editing that Expense keeps its saved billing
currency unless the user deliberately reselects the target or original
currency and completes a new conversion under the current Client currency.
Loading never silently recomputes history.

Resolving billing currency dynamically from Client was rejected because a later
catalog edit could relabel a historical amount without an explicit conversion.

### Build a compact global Expense ledger

Replace the `/expenses` placeholder with lazy `ExpensesPage`. Its header keeps
the existing description and one `Add expense` action. An Active/Archived
segmented control owns a table ordered by expense date descending and then
creation order. Columns show Date, Client / Project, Description, Original,
Billing amount, and row actions. Archived rows are visibly read-only and offer
`Restore`.

`ExpenseForm` uses existing Dialog, Input, Label, Select, and Button primitives.
The target selector groups Projects beneath Clients and includes one direct
Client choice per active Client. Currency starts at Client billing currency;
choosing another reveals two explicitly labelled linked inputs: applied rate
with its direction and final billing amount. Inline validation preserves draft
values after errors.

This extends the established Geist typography, neutral table/card tokens,
sentence-case copy, focus rings, alert confirmations, and persistent error
region. A project-scoped-only screen was rejected because direct Client
Expenses need the same ledger and the shell already owns a global destination.

### Extend backup compatibility for migration 6

Backup validation recognizes the Expense table only for migration-6 data and
keeps valid migration-1 through migration-5 backups restorable and migratable.
The existing complete SQLite snapshot includes Expense rows without a new
backup action.

## Risks / Trade-offs

- **A target archives between form load and save** → Recheck the complete target
  path during the write and return a recoverable stale-target error.
- **A Client currency changes while an edit dialog is open** → Recheck current
  target currency before update and preserve the draft for reconversion.
- **Conversion arithmetic overflows safe minor-unit storage** → Use exact
  intermediates, reject the command, and identify the amount as too large.
- **Lifecycle plans created before an Expense mutation become stale** → Include
  Expense IDs and lifecycle states in the immutable plan recheck.
- **The global list grows large** → Keep the first interface bounded by one
  active/archived query and stable ordering; defer pagination until measured.

## Migration Plan

1. Deepen the money module behind compatibility wrappers before adding Expense
   callers.
2. Add migration 6 and backup validation without modifying migrations 1–5.
3. Implement and contract-test ExpenseStore, then extend CatalogLifecycle plans
   and adapters with Expense nodes.
4. Replace the Expenses placeholder and wire the SQLite store plus lifecycle
   seam through the existing application composition root.
5. Roll back application code by leaving the additive table and retained data
   intact; never downgrade or delete local Expense records.
