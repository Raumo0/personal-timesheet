# Development data isolation Specification

## Purpose

Keeps development activity visibly and physically separate from the installed application's real local data.

## Requirements

### Requirement: Preserve the production identity and data location
Production builds SHALL retain the application identifier `com.personal.timesheet`, the product name `Personal Timesheet`, and the corresponding platform application-data directory. Development configuration SHALL NOT alter or migrate that production data.

#### Scenario: Build the production application
- **WHEN** the production build command resolves the application configuration
- **THEN** it uses `com.personal.timesheet` and does not include a development identity override

#### Scenario: Upgrade an installed production build
- **WHEN** a newer production build starts on a device with an existing production database
- **THEN** it continues opening the database under the production application-data directory

### Requirement: Isolate the normal development launch
The repository's documented development launch SHALL use `com.personal.timesheet.dev`, a development-specific product and window name, and the platform application-data directory derived from that identifier. It SHALL NOT open, create, migrate, restore, or back up the production database.

#### Scenario: Start development with no prior development data
- **WHEN** the normal development command starts for the first time
- **THEN** it creates or opens `personal-timesheet.db` beneath the `com.personal.timesheet.dev` application-data directory

#### Scenario: Start development after production contains data
- **WHEN** production data exists and the normal development command starts
- **THEN** development opens only its independent database and production data is not visible

#### Scenario: Reopen development
- **WHEN** the development command runs again after development data was saved
- **THEN** it reuses the development database without copying data to or from production

### Requirement: Make the active environment recognizable
The normal development launch SHALL be visibly distinguishable from production, and repository documentation SHALL state the supported development and production commands plus their platform-derived data identities.

#### Scenario: Inspect a development window
- **WHEN** a developer opens the normal development application
- **THEN** its product or window name clearly identifies it as development

#### Scenario: Follow repository launch documentation
- **WHEN** a developer follows the documented development or production command
- **THEN** the command selects the corresponding identifier without requiring an undocumented environment variable
