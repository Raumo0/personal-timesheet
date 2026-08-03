## ADDED Requirements

### Requirement: Represent generated Expense occurrences
A due Schedule occurrence whose original currency matches its snapshotted Client
billing currency SHALL create and link a ready Expense immediately. A due
occurrence whose currencies differ SHALL remain visible as `Needs conversion`
without creating a ready Expense until the user supplies a valid applied rate or
final billing amount.

#### Scenario: Materialize a same-currency occurrence
- **WHEN** a Schedule occurrence is due with matching original and Client billing currencies
- **THEN** the application creates a ready Expense with equal authoritative amounts and rate `1`

#### Scenario: Materialize a different-currency occurrence
- **WHEN** a Schedule occurrence is due with different original and Client billing currencies
- **THEN** the Expenses workspace shows its snapshotted details as `Needs conversion` without inventing a rate or billing amount

#### Scenario: Complete a pending occurrence manually
- **WHEN** the user supplies a valid manual rate or final billing amount for a `Needs conversion` occurrence
- **THEN** the application creates and links one ready Expense using the existing exact conversion rules

#### Scenario: Complete a pending occurrence from a suggestion
- **WHEN** an Expense rate provider is available and the user explicitly obtains and accepts or adjusts a valid suggestion
- **THEN** the application creates and links one ready Expense with the saved provider provenance

#### Scenario: Retry occurrence completion
- **WHEN** completion is retried after a persistence failure
- **THEN** the occurrence links to at most one ready Expense and no duplicate Expense is created

### Requirement: Keep generated Expenses independent
Once a Schedule occurrence links to a ready Expense, that Expense SHALL use the
ordinary Expense edit, archive, restore, and persistence rules. Later Schedule
edits, disabling, or removal of future dates SHALL NOT rewrite or remove it.

#### Scenario: Edit a generated Expense
- **WHEN** the user edits a ready Expense created from a Schedule
- **THEN** only that Expense changes and the Schedule configuration remains unchanged

#### Scenario: Disable a Schedule with generated Expenses
- **WHEN** the user disables a Schedule that already generated ready Expenses
- **THEN** those Expenses retain their values and lifecycle states

#### Scenario: Archive a generated Expense
- **WHEN** the user archives one generated Expense
- **THEN** the Expense follows ordinary archive behavior without disabling or changing its Schedule

### Requirement: Apply Expense lifecycle to pending occurrences
A `Needs conversion` occurrence SHALL follow the ordinary Expense lifecycle
rules for its snapshotted Client-or-Project target. Catalog archive cascades
SHALL include it, and targeted restore SHALL activate only that occurrence and
the required Client or Project ancestors.

#### Scenario: Archive a target with pending occurrences
- **WHEN** the user confirms archiving a Client or Project hierarchy containing `Needs conversion` occurrences
- **THEN** those occurrences become archived as part of the atomic hierarchy operation

#### Scenario: Restore one pending occurrence
- **WHEN** the user confirms restoring an archived `Needs conversion` occurrence
- **THEN** that occurrence and only its required archived Client or Project ancestors become active

#### Scenario: Keep an archived pending occurrence read-only
- **WHEN** a pending occurrence or any required target ancestor is archived
- **THEN** the application keeps it read-only and offers targeted restore instead of conversion
