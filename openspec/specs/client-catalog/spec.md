# Client Catalog Specification

## Purpose

Defines how the user maintains durable client records and their default
billing details before assigning projects, tasks, time, or expenses.
## Requirements
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

### Requirement: Create a client
The application SHALL allow the user to create an active client with a unique
non-empty name, a billing currency, and an optional default hourly rate.
Client-name uniqueness SHALL ignore surrounding whitespace and letter case
among active clients.

#### Scenario: Create a client with a default hourly rate
- **WHEN** the user enters a valid name, currency, and non-negative hourly rate and saves the client
- **THEN** the client appears in the active client list with the saved billing details

#### Scenario: Create a client without a default hourly rate
- **WHEN** the user enters a valid name and currency, leaves the hourly rate unset, and saves the client
- **THEN** the client appears in the active client list with its default hourly rate identified as not set

#### Scenario: Reject a duplicate active client name
- **WHEN** the user saves a name that matches an active client after whitespace and case normalization
- **THEN** the application does not create the client and identifies the conflicting name

### Requirement: Default hourly rate semantics
The application SHALL treat an unset default hourly rate differently from an
explicit zero hourly rate and SHALL reject negative rates.

#### Scenario: Save an explicit zero rate
- **WHEN** the user saves a client with an hourly rate of zero
- **THEN** the application stores and displays zero as the client's explicit default hourly rate

#### Scenario: Reject a negative rate
- **WHEN** the user attempts to save a negative hourly rate
- **THEN** the application does not save the client and identifies the invalid rate

### Requirement: Edit a client
The application SHALL allow the user to change an active client's name,
billing currency, and default hourly rate subject to the same validation rules
as client creation. When the billing currency changes, numeric project and task
override amounts SHALL be preserved in the new currency when all of them can be
represented at its supported precision; otherwise the change SHALL be rejected
without partially updating the client, its projects, or their tasks. A local
persistence failure during the change SHALL also leave the Client and every
descendant override at their previously saved values.

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

#### Scenario: Roll back a failed currency update
- **WHEN** local persistence fails after a Client currency update starts changing the Client or descendant overrides
- **THEN** the Client, every Project, and every Task retain their previously saved currency and rate values, and the interface reports that the change was not saved

### Requirement: Archive a client
The application SHALL allow the user to archive an active client only after a
confirmation that states the Client and every Project and Task beneath it will
be archived. Confirmation SHALL archive the complete hierarchy atomically
without permanently deleting catalog records or their historical relationships.

#### Scenario: Confirm client archival
- **WHEN** the user confirms archiving an active client
- **THEN** the Client, all of its active Projects, and all active Tasks beneath those Projects become archived and leave their active views

#### Scenario: Describe the cascade before confirmation
- **WHEN** an active client has descendant Projects or Tasks and the user requests archival
- **THEN** the confirmation identifies the Client and states that every Project and Task beneath it is included

#### Scenario: Cancel client archival
- **WHEN** the user cancels the archival confirmation
- **THEN** the Client and every descendant remain unchanged

#### Scenario: Client cascade cannot be saved
- **WHEN** local persistence fails while archiving the Client hierarchy
- **THEN** no affected Client, Project, or Task changes lifecycle state and the interface displays a recoverable error with Retry

#### Scenario: Client cascade rollback also fails
- **WHEN** local persistence fails and the attempted transaction rollback also fails
- **THEN** the interface identifies both the original persistence failure and the rollback failure without claiming that the hierarchy state was restored

### Requirement: Durable local client data
The application SHALL retain successfully saved client changes across
application restarts and SHALL not transmit client data to an external service.

#### Scenario: Reopen the application
- **WHEN** the user closes and later reopens the application after saving client changes
- **THEN** the application displays the same client records and billing details

#### Scenario: Client data cannot be loaded
- **WHEN** local client data cannot be initialized or read
- **THEN** the Clients workspace displays a recoverable error state instead of presenting an empty catalog

#### Scenario: Client changes cannot be saved
- **WHEN** a local persistence error prevents a create, edit, or archive operation
- **THEN** the application preserves the user's current context and explains that the change was not saved

### Requirement: Restore an archived client
The application SHALL allow the user to restore an archived Client from the
archived view after confirming the exact target. Restoring a Client SHALL make
only that Client active and SHALL NOT restore its archived Projects or Tasks.

#### Scenario: Restore only the client
- **WHEN** the user confirms restoring an archived Client
- **THEN** the Client becomes active while every archived Project and Task beneath it remains archived

#### Scenario: Cancel client restore
- **WHEN** the user cancels the restore confirmation
- **THEN** the Client and every descendant remain unchanged

#### Scenario: Client restore cannot be saved
- **WHEN** local persistence fails while restoring the Client
- **THEN** the Client remains archived and the interface displays a recoverable error with Retry
