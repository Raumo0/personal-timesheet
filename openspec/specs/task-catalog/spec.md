# Task Catalog Specification

## Purpose

Defines how tasks are maintained beneath projects and how their visible,
effective hourly rates inherit from the nearest project or client value.

## Requirements

### Requirement: Project task screen
The application SHALL provide a task screen for each project that displays
active tasks by default and archived tasks separately. Every task SHALL belong
to exactly one project and use that project's client billing currency.

#### Scenario: Open an empty task screen
- **WHEN** the user opens an active project that has no tasks
- **THEN** the application displays an empty task state with an action to create the first task

#### Scenario: View active tasks
- **WHEN** the user opens a project with saved active tasks
- **THEN** the application displays each task's name, rate mode, effective hourly rate, and rate source

#### Scenario: View archived tasks
- **WHEN** the user selects the archived task view
- **THEN** the application displays that project's archived tasks without mixing them into the active list

#### Scenario: Inspect tasks beneath an archived ancestor
- **WHEN** the user opens tasks for an archived project or a project beneath an archived client
- **THEN** the application displays retained tasks as read-only historical records and does not offer creation, editing, or archival

### Requirement: Create a task
The application SHALL allow the user to create an active task under an active
project of an active client with a unique non-empty name and an explicit choice
to inherit or override the project's effective hourly rate. Task-name
uniqueness SHALL ignore surrounding whitespace and letter case among active
tasks of the same project.

#### Scenario: Create an inheriting task
- **WHEN** the user enters a valid task name, selects inheritance, and saves
- **THEN** the task appears under the project with its rate identified as inherited

#### Scenario: Reuse a task name under another project
- **WHEN** two projects each have an active task with the same normalized name
- **THEN** the application accepts both tasks because uniqueness is scoped to their projects

#### Scenario: Reject a duplicate active task name
- **WHEN** the user saves a task name matching an active task of the same project after whitespace and case normalization
- **THEN** the application does not save the task and identifies the conflicting name

### Requirement: Explicit task rate mode
The application SHALL present inheritance and override as explicit mutually
exclusive task rate modes. In inherited mode the applicable project or client
value SHALL be visible, read-only, and identified by its source. In override
mode the task value SHALL be editable in the client's billing currency.

#### Scenario: Display an inherited project override
- **WHEN** a task inherits and its project defines an hourly rate override
- **THEN** the task form displays that project rate as read-only and identifies the project as its source

#### Scenario: Display an inherited client default
- **WHEN** a task inherits, its project inherits, and its client defines a default hourly rate
- **THEN** the task form displays that client rate as read-only and identifies the client as its source

#### Scenario: Display inheritance without an available rate
- **WHEN** a task inherits and neither its project nor client defines an applicable rate
- **THEN** the task form states that no inherited rate is set without converting the task to override mode

#### Scenario: Enter a task override
- **WHEN** the user selects override mode
- **THEN** the task form enables an hourly-rate input in the client's billing currency

#### Scenario: Preserve task mode while editing
- **WHEN** the user reopens a saved task for editing
- **THEN** the form restores its saved inheritance or override selection rather than inferring the mode from equal numeric values

### Requirement: Effective task rate
The application SHALL resolve a task's effective hourly rate from its explicit
override when present, otherwise from its project's explicit override, and
otherwise from its client's default hourly rate. The effective rate SHALL
remain unset when no level defines one, and an explicit zero at any applicable
level SHALL remain a valid zero rate.

#### Scenario: Resolve a task override
- **WHEN** a task defines an override
- **THEN** its effective rate is the task override regardless of project or client values and its source is identified as the task

#### Scenario: Resolve a project override
- **WHEN** a task inherits and its project defines an override
- **THEN** the task effective rate is the project override and its source is identified as the project

#### Scenario: Resolve a client default
- **WHEN** a task and project inherit and the client defines a default hourly rate
- **THEN** the task effective rate is the client default and its source is identified as the client

#### Scenario: Update an inherited task rate
- **WHEN** an applicable project override or client default changes for an inheriting task
- **THEN** the task displays the new effective rate and source without changing its inherited mode

#### Scenario: Keep a task override after ancestor changes
- **WHEN** a project override or client default changes for a task with an override
- **THEN** the task retains its override and effective rate

#### Scenario: Resolve no available task rate
- **WHEN** a task inherits and neither its project nor client defines a rate
- **THEN** the task effective rate is identified as not set

#### Scenario: Resolve an explicit zero
- **WHEN** the nearest applicable task, project, or client value is an explicit zero
- **THEN** the task effective rate is zero and its source identifies the level that defines zero

### Requirement: Edit and archive a task
The application SHALL allow the user to edit or archive an active task beneath
an active project and client without permanently deleting its record.

#### Scenario: Save task changes
- **WHEN** the user saves a valid name or rate-mode change
- **THEN** the task screen displays the updated task and effective rate

#### Scenario: Reject an invalid task override
- **WHEN** the user attempts to save a negative, missing, or invalid-precision task override
- **THEN** the application preserves the entered values and identifies the invalid rate

#### Scenario: Confirm task archival
- **WHEN** the user confirms archiving an active task
- **THEN** the task leaves the active list and appears in the archived task view

#### Scenario: Cancel task archival
- **WHEN** the user cancels the archival confirmation
- **THEN** the task remains active and unchanged

### Requirement: Durable local task data
The application SHALL retain successfully saved tasks and their explicit rate
modes across application restarts and SHALL not transmit task data to an
external service.

#### Scenario: Reopen the application
- **WHEN** the user closes and later reopens the application after saving task changes
- **THEN** the application displays the same task records, rate modes, and overrides

#### Scenario: Task data cannot be loaded
- **WHEN** local task data cannot be initialized or read
- **THEN** the task screen displays a recoverable error state instead of an empty catalog

#### Scenario: Task changes cannot be saved
- **WHEN** a local persistence error prevents a create, edit, or archive operation
- **THEN** the task screen preserves the user's current context and explains that the change was not saved
