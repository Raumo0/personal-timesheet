## MODIFIED Requirements

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

## ADDED Requirements

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
