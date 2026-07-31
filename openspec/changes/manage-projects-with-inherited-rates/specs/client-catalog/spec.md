## MODIFIED Requirements

### Requirement: Client catalog overview
The application SHALL provide a Clients workspace that displays active clients
by default, allows the user to inspect archived clients separately, and provides
access to each client's project workspace.

#### Scenario: Open an empty client catalog
- **WHEN** the user opens Clients before creating any clients
- **THEN** the application displays an empty state with a clear action to create the first client

#### Scenario: View active clients
- **WHEN** the user opens Clients with saved active clients
- **THEN** the application displays each active client's name, billing currency, and default hourly rate status

#### Scenario: View archived clients
- **WHEN** the user selects the archived view
- **THEN** the application displays archived clients without mixing them into the active list

#### Scenario: Open a client's projects
- **WHEN** the user chooses an active or archived client from the Clients workspace
- **THEN** the application opens that client's project workspace without losing the selected client context

### Requirement: Edit a client
The application SHALL allow the user to change an active client's name,
billing currency, and default hourly rate subject to the same validation rules
as client creation. When the billing currency changes, numeric project override
amounts SHALL be preserved in the new currency when they can be represented at
its supported precision; otherwise the change SHALL be rejected without
partially updating the client or its projects.

#### Scenario: Save client changes
- **WHEN** the user saves valid changes to an active client
- **THEN** the active client list displays the updated billing details

#### Scenario: Reject invalid client changes
- **WHEN** the user attempts to save invalid changes
- **THEN** the application preserves the entered values and identifies each value that must be corrected

#### Scenario: Preserve project override amounts across a currency change
- **WHEN** the user changes a client's currency and every project override can be represented at the new currency precision
- **THEN** the client and its projects use the new currency while retaining the same numeric hourly-rate amounts

#### Scenario: Reject a lossy currency change
- **WHEN** changing a client's currency would discard precision from any project override
- **THEN** the application leaves the client and all projects unchanged and explains why the currency cannot be changed
