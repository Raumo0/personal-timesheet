## MODIFIED Requirements

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

## ADDED Requirements

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
