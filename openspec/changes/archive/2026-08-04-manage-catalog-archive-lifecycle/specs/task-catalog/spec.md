## MODIFIED Requirements

### Requirement: Edit and archive a task
The application SHALL allow the user to edit or archive an active Task beneath
an active Project and Client without permanently deleting its record or
historical relationships.

#### Scenario: Save task changes
- **WHEN** the user saves a valid name or rate-mode change
- **THEN** the task screen displays the updated Task and effective rate

#### Scenario: Reject an invalid task override
- **WHEN** the user attempts to save a negative, missing, or invalid-precision task override
- **THEN** the application preserves the entered values and identifies the invalid rate

#### Scenario: Confirm task archival
- **WHEN** the user confirms archiving an active Task
- **THEN** the Task leaves the active list and appears in the archived Task view without changing its Client, Project, or sibling Tasks

#### Scenario: Cancel task archival
- **WHEN** the user cancels the archival confirmation
- **THEN** the Task and its hierarchy remain unchanged

#### Scenario: Task archival cannot be saved
- **WHEN** local persistence fails while archiving the Task
- **THEN** the Task remains active and the interface displays a recoverable error with Retry

## ADDED Requirements

### Requirement: Restore an archived task
The application SHALL allow the user to restore an archived Task from its
archived view. The confirmation SHALL identify the Task and each archived
Project or Client on its ancestor path, and the restore SHALL activate exactly
those records atomically without restoring siblings or other descendants.

#### Scenario: Restore a task beneath active ancestors
- **WHEN** the user confirms restoring an archived Task whose Project and Client are active
- **THEN** only the Task becomes active

#### Scenario: Restore a task with archived ancestors
- **WHEN** the user confirms restoring an archived Task whose Project or Client is archived
- **THEN** the confirmation identifies the Task and archived ancestors and exactly that path becomes active atomically

#### Scenario: Leave unrelated records unchanged
- **WHEN** an archived Task is restored
- **THEN** sibling Tasks, sibling Projects, and other descendants retain their existing lifecycle states

#### Scenario: Task restore cannot be saved
- **WHEN** local persistence fails while restoring the Task and required ancestors
- **THEN** every affected record retains its prior lifecycle state and the interface displays a recoverable error with Retry
