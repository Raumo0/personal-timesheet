## MODIFIED Requirements

### Requirement: Primary product navigation
The application SHALL provide persistent primary navigation to Timesheet,
Clients, Reports, Expenses, and Settings.

#### Scenario: Navigate between product areas
- **WHEN** the user selects a primary navigation destination
- **THEN** the application displays that destination without a full application reload
- **THEN** the selected destination is visibly identified as active

#### Scenario: Open the application
- **WHEN** the application opens without a specific destination
- **THEN** the Timesheet destination is displayed
