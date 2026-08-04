# Project Catalog Specification

## Purpose

Defines how projects are maintained beneath clients and how their visible,
effective billing rates inherit or override client defaults.
## Requirements
### Requirement: Client project workspace
The application SHALL provide a project workspace for each client that displays
active projects by default and archived projects separately. Every project
SHALL belong to exactly one client and use that client's billing currency.

#### Scenario: Open an empty project workspace
- **WHEN** the user opens an active client that has no projects
- **THEN** the application displays an empty project state with an action to create the first project

#### Scenario: View active projects
- **WHEN** the user opens a client with saved active projects
- **THEN** the application displays each project's name, rate mode, effective hourly rate, and rate source

#### Scenario: View archived projects
- **WHEN** the user selects the archived project view
- **THEN** the application displays that client's archived projects without mixing them into the active list

#### Scenario: Inspect projects for an archived client
- **WHEN** the user opens the project workspace for an archived client
- **THEN** the application displays retained projects as read-only historical records and does not offer creation or editing

### Requirement: Create a project
The application SHALL allow the user to create an active project under an
active client with a unique non-empty name and an explicit choice to inherit or
override the client's default hourly rate. Project-name uniqueness SHALL ignore
surrounding whitespace and letter case among active projects of the same client.

#### Scenario: Create an inheriting project
- **WHEN** the user enters a valid project name, selects inheritance, and saves
- **THEN** the project appears under the client with its rate identified as inherited

#### Scenario: Reuse a project name under another client
- **WHEN** two active clients each have an active project with the same normalized name
- **THEN** the application accepts both projects because uniqueness is scoped to their clients

#### Scenario: Reject a duplicate active project name
- **WHEN** the user saves a project name matching an active project of the same client after whitespace and case normalization
- **THEN** the application does not save the project and identifies the conflicting name

### Requirement: Explicit project rate mode
The application SHALL present inheritance and override as explicit mutually
exclusive project rate modes. In inherited mode the applicable client value
SHALL be visible, read-only, and identified as coming from the client. In
override mode the project value SHALL be editable in the client's currency.

#### Scenario: Display an inherited client rate
- **WHEN** a project's rate mode is inherited and its client defines a default hourly rate
- **THEN** the project form displays the formatted client rate as read-only and identifies the client as its source

#### Scenario: Display inheritance without a client rate
- **WHEN** a project's rate mode is inherited and its client has no default hourly rate
- **THEN** the project form states that no client rate is set without converting the project to override mode

#### Scenario: Enter an override
- **WHEN** the user selects override mode
- **THEN** the project form enables an hourly-rate input in the client's billing currency

#### Scenario: Preserve mode while editing
- **WHEN** the user reopens a saved project for editing
- **THEN** the form restores its saved inheritance or override selection rather than inferring the mode from equal numeric values

### Requirement: Effective project rate
The application SHALL resolve a project's effective hourly rate from its
explicit override when present and otherwise from its client's default hourly
rate. An unset client rate SHALL yield an unset effective project rate, while an
explicit zero at either applicable level SHALL remain a valid zero rate.

#### Scenario: Resolve a project override
- **WHEN** a project defines an override
- **THEN** its effective rate is the project override regardless of the client's current default

#### Scenario: Resolve client inheritance
- **WHEN** a project inherits and its client defines a default hourly rate
- **THEN** its effective rate is the current client default and its source is identified as the client

#### Scenario: Update an inherited effective rate
- **WHEN** the client default hourly rate changes for an inheriting project
- **THEN** the project displays the new client value without changing its inherited mode

#### Scenario: Keep an override after a client change
- **WHEN** the client default hourly rate changes for a project with an override
- **THEN** the project retains its override and effective rate

#### Scenario: Resolve no available rate
- **WHEN** a project inherits and its client has no default hourly rate
- **THEN** the project effective rate is identified as not set

#### Scenario: Resolve an explicit zero override
- **WHEN** a project overrides its rate with zero
- **THEN** the effective rate is zero and is identified as a project override

### Requirement: Edit and archive a project
The application SHALL allow the user to edit or archive an active Project under
an active Client without permanently deleting its record or historical
relationships. Project archival SHALL require confirmation that identifies the
Project and every Task beneath it, then archive the complete Project hierarchy
atomically.

#### Scenario: Save project changes
- **WHEN** the user saves a valid name or rate-mode change
- **THEN** the project workspace displays the updated Project and effective rate

#### Scenario: Reject an invalid override
- **WHEN** the user attempts to save a negative, missing, or invalid-precision override
- **THEN** the application preserves the entered values and identifies the invalid rate

#### Scenario: Confirm project archival
- **WHEN** the user confirms archiving an active Project
- **THEN** the Project and all of its active Tasks become archived and leave their active views

#### Scenario: Describe the task cascade before confirmation
- **WHEN** an active Project has Tasks and the user requests archival
- **THEN** the confirmation identifies the Project and states that every Task beneath it is included

#### Scenario: Cancel project archival
- **WHEN** the user cancels the archival confirmation
- **THEN** the Project and every Task beneath it remain unchanged

#### Scenario: Project cascade cannot be saved
- **WHEN** local persistence fails while archiving the Project hierarchy
- **THEN** neither the Project nor any Task beneath it changes lifecycle state and the interface displays a recoverable error with Retry

### Requirement: Durable local project data
The application SHALL retain successfully saved projects and their explicit
rate modes across application restarts and SHALL not transmit project data to an
external service.

#### Scenario: Reopen the application
- **WHEN** the user closes and later reopens the application after saving project changes
- **THEN** the application displays the same projects, rate modes, and overrides

#### Scenario: Project data cannot be loaded
- **WHEN** local project data cannot be initialized or read
- **THEN** the project workspace displays a recoverable error state instead of an empty catalog

#### Scenario: Project changes cannot be saved
- **WHEN** a local persistence error prevents a create, edit, or archive operation
- **THEN** the project workspace preserves the user's current context and explains that the change was not saved

### Requirement: Project task navigation
The application SHALL provide access from each project to that project's task
screen while retaining the selected client and project context. The task screen
SHALL identify both ancestors and provide a direct return to the client's
project screen.

#### Scenario: Open tasks for an active project
- **WHEN** the user chooses an active project from the project screen
- **THEN** the application opens that project's task screen and identifies its client and project context

#### Scenario: Retain task context through a deep link
- **WHEN** the application opens or refreshes a task-screen route containing valid client and project identifiers
- **THEN** the application restores the same client and project context

#### Scenario: Open tasks for an archived ancestor
- **WHEN** the user chooses a project that is archived or belongs to an archived client
- **THEN** the application opens its task screen in read-only historical mode without losing the selected ancestors

#### Scenario: Return to the project screen
- **WHEN** the user follows the project ancestor from a task screen
- **THEN** the application returns to that client's project screen

### Requirement: Restore an archived project
The application SHALL allow the user to restore an archived Project from its
archived view. If its Client is archived, the confirmation SHALL identify both
records and the restore SHALL activate the Client and Project atomically.
Archived Tasks beneath the Project SHALL remain archived.

#### Scenario: Restore a project beneath an active client
- **WHEN** the user confirms restoring an archived Project whose Client is active
- **THEN** the Project becomes active and its archived Tasks remain archived

#### Scenario: Restore a project beneath an archived client
- **WHEN** the user confirms restoring an archived Project whose Client is archived
- **THEN** the confirmation identifies both records and the Client and Project become active atomically while archived Tasks remain archived

#### Scenario: Leave sibling records unchanged
- **WHEN** an archived Project is restored
- **THEN** sibling Projects and their Tasks retain their existing lifecycle states

#### Scenario: Project restore cannot be saved
- **WHEN** local persistence fails while restoring the Project and any required Client ancestor
- **THEN** every affected record retains its prior lifecycle state and the interface displays a recoverable error with Retry
