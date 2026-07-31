# Client Catalog Specification

## Purpose

Defines how the user maintains durable client records and their default
billing details before assigning projects, tasks, time, or expenses.

## Requirements

### Requirement: Client catalog overview
The application SHALL provide a Clients workspace that displays active clients
by default and allows the user to inspect archived clients separately.

#### Scenario: Open an empty client catalog
- **WHEN** the user opens Clients before creating any clients
- **THEN** the application displays an empty state with a clear action to create the first client

#### Scenario: View active clients
- **WHEN** the user opens Clients with saved active clients
- **THEN** the application displays each active client's name, billing currency, and default hourly rate status

#### Scenario: View archived clients
- **WHEN** the user selects the archived view
- **THEN** the application displays archived clients without mixing them into the active list

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
as client creation.

#### Scenario: Save client changes
- **WHEN** the user saves valid changes to an active client
- **THEN** the active client list displays the updated billing details

#### Scenario: Reject invalid client changes
- **WHEN** the user attempts to save invalid changes
- **THEN** the application preserves the entered values and identifies each value that must be corrected

### Requirement: Archive a client
The application SHALL allow the user to archive an active client without
permanently deleting its record.

#### Scenario: Confirm client archival
- **WHEN** the user confirms archiving an active client
- **THEN** the client is removed from the active list and appears in the archived view

#### Scenario: Cancel client archival
- **WHEN** the user cancels the archival confirmation
- **THEN** the client remains active and unchanged

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
