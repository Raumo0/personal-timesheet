## ADDED Requirements

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
