## Purpose

Defines how a local user records, converts, reviews, archives, and restores
positive costs against the Client or Project that will eventually be billed.

## ADDED Requirements

### Requirement: Expense workspace overview
The application SHALL provide an Expenses workspace that displays active
Expenses by default and archived Expenses separately. Each row SHALL identify
its local expense date, billing target, description, original amount and
currency, and amount in the saved Client billing currency.

#### Scenario: Open an empty Expense workspace
- **WHEN** the user opens Expenses before saving any Expenses
- **THEN** the application displays an empty state with a clear action to create the first Expense

#### Scenario: View active Expenses
- **WHEN** the user opens Expenses with saved active records
- **THEN** the application displays the active Expenses without mixing in archived records

#### Scenario: View archived Expenses
- **WHEN** the user selects the archived view
- **THEN** the application displays archived Expenses as retained read-only records

### Requirement: Select exactly one Expense billing target
Every Expense SHALL belong either to one Client directly or to one Project. A
Project Expense SHALL derive its Client from the selected Project and SHALL NOT
store an independently selectable Client that can disagree with that Project.
Creation and target changes SHALL offer only fully active target paths.

#### Scenario: Select a direct Client target
- **WHEN** the user selects an active Client directly
- **THEN** the Expense is identified as a direct Client Expense without a Project

#### Scenario: Select a Project target
- **WHEN** the user selects an active Project beneath an active Client
- **THEN** the Expense is identified as a Project Expense and uses that Project's Client

#### Scenario: Reject a missing target
- **WHEN** the user attempts to save an Expense without a Client or Project target
- **THEN** the application does not save the Expense and identifies the missing target

#### Scenario: Exclude an inactive target path
- **WHEN** a Client or Project is archived
- **THEN** the target selector excludes that record and every Project whose Client is archived

### Requirement: Create a positive dated Expense
The application SHALL allow the user to create an active Expense with a valid
local date, non-empty description, supported original currency, and original
amount strictly greater than zero. The original currency SHALL default to the
selected Client's billing currency.

#### Scenario: Create an Expense in Client billing currency
- **WHEN** the user enters valid Expense details and keeps the default currency
- **THEN** the application saves the Expense with equal original and billing amounts and an applied rate of `1`

#### Scenario: Create an Expense in another currency
- **WHEN** the user enters valid Expense details in a supported currency different from the Client billing currency and completes manual conversion
- **THEN** the application saves both currency amounts and the applied conversion rate

#### Scenario: Reject zero or negative amount
- **WHEN** the user attempts to save an original amount that is zero or negative
- **THEN** the application preserves the entered values, does not save the Expense, and identifies that the amount must be positive

#### Scenario: Reject invalid date or description
- **WHEN** the user attempts to save an invalid local date or blank description
- **THEN** the application preserves the entered values and identifies every value that must be corrected

### Requirement: Convert an Expense manually
When original and Client billing currencies differ, the application SHALL let
the user edit either a positive applied exchange rate or the positive final
billing amount and SHALL recalculate the other value. The interface SHALL state
the direction as `1 original currency = X Client billing currency`. When the
currencies match, the applied rate SHALL be `1` and conversion controls SHALL
not be shown.

#### Scenario: Enter an applied rate
- **WHEN** the user enters a valid positive applied rate
- **THEN** the application previews the final amount in Client billing currency

#### Scenario: Enter a final billing amount
- **WHEN** the user enters a valid positive final amount in Client billing currency
- **THEN** the application recalculates and displays the applied rate in the canonical direction

#### Scenario: Switch back to Client billing currency
- **WHEN** the user changes the original currency to the Client billing currency
- **THEN** the application sets the rate to `1`, makes both amounts equal, and hides conversion controls

#### Scenario: Reject an incomplete manual conversion
- **WHEN** the currencies differ and neither a valid rate nor final billing amount is available
- **THEN** the application does not save the Expense and identifies the missing conversion value

### Requirement: Preserve exact saved monetary values
The application SHALL accept original and billing amounts only at the supported
precision of their currencies, retain them as authoritative minor-unit values,
and accept applied rates with at most 12 decimal places. A rate-derived billing
amount SHALL be rounded once, half-up, to the Client billing currency precision.
Saved amounts and currencies SHALL NOT be recomputed when the Expense is loaded
or when the Client later changes billing currency.

#### Scenario: Round a converted amount once
- **WHEN** a valid applied rate produces more fractional digits than the Client billing currency supports
- **THEN** the displayed and saved billing amount is rounded half-up to that currency's precision

#### Scenario: Preserve a manually rounded billing amount
- **WHEN** the user enters the final billing amount directly and saves the Expense
- **THEN** the application retains that exact amount and the corresponding displayed applied rate

#### Scenario: Reopen a saved Expense after a Client currency change
- **WHEN** the Client billing currency changes after an Expense was saved
- **THEN** the Expense retains its saved original currency, billing currency, amounts, and applied rate

### Requirement: Edit an active Expense
The application SHALL allow the user to edit an active Expense while its
complete Client or Project target path is active, subject to the same target,
date, description, amount, currency, and conversion rules as creation.

#### Scenario: Save valid Expense changes
- **WHEN** the user saves valid changes to an editable Expense
- **THEN** the Expenses workspace displays the updated saved values

#### Scenario: Keep an Expense read-only under an archived target
- **WHEN** an Expense or any required Client or Project in its target path is archived
- **THEN** the application displays the Expense as read-only and offers targeted restore instead of editing

#### Scenario: Expense changes cannot be saved
- **WHEN** local persistence rejects an Expense edit
- **THEN** the application preserves the user's current context and entered values and explains that the changes were not saved

### Requirement: Archive Expense hierarchies
The application SHALL archive without permanent deletion. Archiving one Expense
SHALL affect only that Expense. Confirmed Project archival SHALL include every
active Expense of that Project, and confirmed Client archival SHALL include its
direct active Expenses plus active Expenses of every Project beneath it. Each
hierarchy operation SHALL be atomic.

#### Scenario: Archive one Expense
- **WHEN** the user confirms archiving an active Expense
- **THEN** that Expense leaves the active view and appears in the archived view without changing its Client, Project, or sibling Expenses

#### Scenario: Archive a Project with Expenses
- **WHEN** the user confirms archiving a Project hierarchy
- **THEN** the Project and all of its active Expenses are archived together

#### Scenario: Archive a Client with Expenses
- **WHEN** the user confirms archiving a Client hierarchy
- **THEN** the Client, its direct active Expenses, and active Expenses of its Projects are archived together with the catalog descendants already included by that operation

#### Scenario: Expense cascade cannot be saved
- **WHEN** persistence fails during a Project or Client archive cascade
- **THEN** no included catalog record or Expense changes lifecycle state and the application displays a recoverable error with Retry

### Requirement: Restore an archived Expense with required ancestors
The application SHALL restore a selected archived Expense and only the archived
Client and Project required to make its target path active. Restoring a Client
or Project SHALL NOT restore descendant Expenses automatically, and unrelated
records SHALL retain their lifecycle states.

#### Scenario: Restore a direct Client Expense
- **WHEN** the user confirms restoring a direct Client Expense whose Client is archived
- **THEN** the Client and selected Expense become active atomically while other Expenses remain unchanged

#### Scenario: Restore a Project Expense
- **WHEN** the user confirms restoring a Project Expense whose Project or Client is archived
- **THEN** the required Client, Project, and selected Expense become active atomically while sibling Projects and Expenses remain unchanged

#### Scenario: Restore beneath an active target path
- **WHEN** the user confirms restoring an Expense whose required Client and Project are already active
- **THEN** only the selected Expense becomes active

#### Scenario: Expense restore cannot be saved
- **WHEN** persistence fails during targeted Expense restore
- **THEN** every affected record retains its prior lifecycle state and the application displays a recoverable error with Retry

### Requirement: Retain Expenses locally
The application SHALL retain successfully saved Expense data across application
restarts, include it in complete local backup and restore, and SHALL NOT transmit
Expense data to an external service in this slice.

#### Scenario: Reopen the application
- **WHEN** the user closes and later reopens the application after saving Expense changes
- **THEN** the same Expenses, targets, monetary values, and lifecycle states are displayed

#### Scenario: Expense data cannot be loaded
- **WHEN** local Expense data cannot be initialized or read
- **THEN** the Expenses workspace displays a recoverable error with Retry instead of an empty ledger

#### Scenario: Backup and restore Expenses
- **WHEN** the user restores a compatible complete local backup containing Expenses
- **THEN** the restored application displays the backed-up Expenses with their saved relationships and monetary values
