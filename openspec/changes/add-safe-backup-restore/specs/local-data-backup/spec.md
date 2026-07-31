## Purpose

Defines how the user protects and recovers the complete local workspace with a
manually stored backup file before more valuable work data accumulates.

## ADDED Requirements

### Requirement: Create a complete local backup
The application SHALL allow the user to save a consistent backup of all local
application data to a file location they choose.

#### Scenario: Save a backup
- **WHEN** the user chooses a destination and starts a backup
- **THEN** the application creates one `.ptimesheet-backup` file containing a consistent snapshot of all current local application data
- **THEN** the application confirms the completed file location

#### Scenario: Cancel backup destination selection
- **WHEN** the user cancels destination selection
- **THEN** the application creates no backup and leaves local data unchanged

#### Scenario: Backup cannot be completed
- **WHEN** the destination cannot be written or the snapshot cannot be completed
- **THEN** the application reports that no usable backup was created
- **THEN** the application leaves local data unchanged and does not leave a partial file presented as a valid backup

### Requirement: Validate before restoration
The application SHALL validate a selected backup's integrity and compatibility
before offering to replace current data.

#### Scenario: Select a compatible backup
- **WHEN** the user selects an intact backup supported by the installed application version
- **THEN** the application identifies it as ready to restore
- **THEN** the application warns that restoration replaces all current local data

#### Scenario: Select a damaged or unrelated file
- **WHEN** the user selects a file that is damaged or is not a Personal Timesheet backup
- **THEN** the application rejects the file and explains that current data was not changed

#### Scenario: Select a backup from an unsupported newer version
- **WHEN** the user selects a backup whose data version is newer than the installed application supports
- **THEN** the application rejects the file and explains that a newer application version is required

#### Scenario: Cancel restoration
- **WHEN** the user cancels file selection or the replacement confirmation
- **THEN** the application leaves current data unchanged

### Requirement: Restore all local data safely
The application SHALL restore a validated backup as one complete replacement
and SHALL preserve a recovery copy of the database being replaced.

#### Scenario: Confirm restoration
- **WHEN** the user confirms restoration of a validated backup
- **THEN** the application creates a recovery copy of the current database
- **THEN** the application replaces all local data with the selected backup and restarts
- **THEN** the restarted application displays the restored records

#### Scenario: Restoration cannot be prepared
- **WHEN** validation, staging, or recovery-copy creation fails
- **THEN** the application does not replace the current database
- **THEN** the application explains that restoration was not completed

#### Scenario: Replacement fails after preparation
- **WHEN** the prepared backup cannot safely replace the current database
- **THEN** the application rolls back to the recovery copy
- **THEN** the application reports that current data was preserved

### Requirement: Keep backup handling local and explicit
The application SHALL perform backup and restoration locally and SHALL make
the privacy characteristics of the backup file clear to the user.

#### Scenario: Create or inspect a backup
- **WHEN** the application creates or validates a backup
- **THEN** it does not transmit the backup or workspace data to an external service

#### Scenario: Present backup controls
- **WHEN** the user opens the Data section in Settings
- **THEN** the application explains that backup files are not encrypted and must be stored securely
