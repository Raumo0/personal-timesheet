## MODIFIED Requirements

### Requirement: Edit a client
The application SHALL allow the user to change an active client's name,
billing currency, and default hourly rate subject to the same validation rules
as client creation. When the billing currency changes, numeric project and task
override amounts SHALL be preserved in the new currency when all of them can be
represented at its supported precision; otherwise the change SHALL be rejected
without partially updating the client, its projects, or their tasks.

#### Scenario: Save client changes
- **WHEN** the user saves valid changes to an active client
- **THEN** the active client list displays the updated billing details

#### Scenario: Reject invalid client changes
- **WHEN** the user attempts to save invalid changes
- **THEN** the application preserves the entered values and identifies each value that must be corrected

#### Scenario: Preserve descendant override amounts across a currency change
- **WHEN** the user changes a client's currency and every project and task override can be represented at the new currency precision
- **THEN** the client, its projects, and their tasks use the new currency while retaining the same numeric hourly-rate amounts

#### Scenario: Reject a lossy descendant currency change
- **WHEN** changing a client's currency would discard precision from any project or task override
- **THEN** the application leaves the client, all of its projects, and all of their tasks unchanged and identifies why the currency cannot be changed
