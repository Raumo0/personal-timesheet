## Purpose

Defines how recurring Client or Project costs become independent local Expense
occurrences on calendar due dates without pre-creating an unbounded future.

## ADDED Requirements

### Requirement: Maintain recurring Expense Schedules
The application SHALL provide a Schedules view inside Expenses. A Schedule
SHALL retain one active Client-or-Project billing target, non-empty description,
positive original amount, original currency, recurrence, start date, optional
end date, and enabled or disabled state. A Schedule SHALL NOT be archived.

#### Scenario: Create an enabled Schedule
- **WHEN** the user saves a valid Schedule against a fully active Client or Project path
- **THEN** the Schedule appears as enabled in the Schedules view

#### Scenario: Create a disabled Schedule
- **WHEN** the user saves a valid Schedule without enabling it
- **THEN** the Schedule retains its configuration without materializing occurrences

#### Scenario: Reject an inactive billing target
- **WHEN** the user attempts to create or retarget a Schedule to an archived Client or Project path
- **THEN** the application does not save the change and identifies that the target must be active

#### Scenario: Schedule data cannot be saved
- **WHEN** local persistence rejects a Schedule create or edit
- **THEN** the application preserves the entered configuration and explains that it was not saved

### Requirement: Support calendar recurrence patterns
The application SHALL support `every N days`, `every N weeks` on one selected
weekday, `monthly` on one selected day of month, and `twice monthly` on two
selected days of month. Every pattern SHALL use a start date and optional end
date and SHALL produce no due date outside that inclusive range.

#### Scenario: Repeat every N days
- **WHEN** an enabled Schedule uses `every N days`
- **THEN** its due dates advance by exactly N local calendar dates from the start date

#### Scenario: Repeat every N weeks
- **WHEN** an enabled Schedule uses `every N weeks` and a selected weekday
- **THEN** its first due date is the first selected weekday on or after the start date and later due dates use that weekday every N weeks

#### Scenario: Repeat monthly
- **WHEN** an enabled Schedule uses `monthly` with one selected day
- **THEN** it has one recurrence slot in every included calendar month

#### Scenario: Repeat twice monthly
- **WHEN** an enabled Schedule uses `twice monthly` with two selected days
- **THEN** it has two distinct recurrence slots in every included calendar month

#### Scenario: Clamp a short month
- **WHEN** a monthly recurrence selects day 29, 30, or 31 and an included month is shorter
- **THEN** that slot is due on the month's last local date and a later month again uses the originally selected day

#### Scenario: Two slots clamp to one date
- **WHEN** both twice-monthly slots clamp to the same last date of a short month
- **THEN** the application retains two distinct occurrences on that date by their recurrence slots

### Requirement: Materialize only due Schedule occurrences
The application SHALL NOT create all future occurrences. While running, it
SHALL materialize an enabled Schedule when a due local date arrives. On launch
or resume after a gap, it SHALL catch up every due date through the user's
current local date for each Schedule that remained enabled, without requiring a
background process while the application was closed.

#### Scenario: Keep future dates unmaterialized
- **WHEN** an enabled Schedule has recurrence dates after the current local date
- **THEN** no occurrence exists for those future dates

#### Scenario: Reach a due date while running
- **WHEN** the local calendar reaches an enabled Schedule's due date while the application remains open
- **THEN** the application materializes that due occurrence once

#### Scenario: Catch up after the application was closed
- **WHEN** the application opens or resumes after one or more due dates passed for a continuously enabled Schedule
- **THEN** every due occurrence through the current local date is materialized without gaps or duplicates

#### Scenario: Retry interrupted catch-up
- **WHEN** catch-up is retried after an interruption or persistence failure
- **THEN** already materialized Schedule/date/slot identities are preserved and only missing occurrences are added

### Requirement: Preview configuration-driven past backfill
Creating, editing, or enabling a Schedule SHALL require explicit confirmation
before adding unmaterialized due dates in the past. The preview SHALL identify
the inclusive date range, occurrence count, and due dates that already contain
one or more Expenses for the same billing target. Cancel SHALL leave the prior
Schedule configuration and all Expenses unchanged.

#### Scenario: Preview a past range
- **WHEN** a proposed Schedule configuration has unmaterialized due dates before the current local date
- **THEN** the application shows the exact range and number of additional occurrences before saving or enabling it

#### Scenario: Warn about overlapping Expenses
- **WHEN** one or more proposed backfill dates already contain an Expense for the same billing target
- **THEN** the preview warns that additional Expenses or occurrences will be added without modifying existing records

#### Scenario: Confirm past backfill
- **WHEN** the user confirms the preview
- **THEN** the Schedule change and every proposed past occurrence are saved atomically

#### Scenario: Cancel past backfill
- **WHEN** the user cancels the preview
- **THEN** the prior Schedule state, existing Expenses, and occurrence set remain unchanged

### Requirement: Keep each occurrence independent and idempotent
Each materialized occurrence SHALL snapshot its Schedule target, description,
original amount and currency, Client billing currency, due date, and recurrence
slot. Materialization SHALL NOT edit or replace any existing Expense. The same
Schedule/date/slot SHALL be created at most once, while different Schedules or
slots SHALL be allowed on the same target and date.

#### Scenario: Materialize beside an existing Expense
- **WHEN** the target and due date already contain a manual Expense or another Schedule's occurrence
- **THEN** the new occurrence is added as a separate record and the existing Expense remains unchanged

#### Scenario: Edit a Schedule after materialization
- **WHEN** the user changes a Schedule after one or more occurrences exist
- **THEN** existing occurrence snapshots and generated Expenses remain unchanged while only later materialization uses the new configuration

#### Scenario: Repeat the same materialization request
- **WHEN** the application processes a Schedule/date/slot that was already materialized
- **THEN** it reuses the existing occurrence and creates no duplicate

### Requirement: Enable and disable Schedules
Disabling a Schedule SHALL retain its configuration and generated history while
stopping new automatic materialization. Enabling it SHALL resume future
materialization and SHALL use the confirmed past-backfill flow when its active
date range contains unmaterialized past due dates.

#### Scenario: Disable a Schedule
- **WHEN** the user disables an enabled Schedule
- **THEN** its configuration and history remain visible and no later due occurrence is created while it stays disabled

#### Scenario: Enable without past due dates
- **WHEN** the user enables a disabled Schedule whose next due date is current or future
- **THEN** it becomes enabled without a past-backfill confirmation

#### Scenario: Enable with past due dates
- **WHEN** the user enables a disabled Schedule whose configured range includes unmaterialized past due dates
- **THEN** the application requires the past-backfill preview and confirmation before enabling it

### Requirement: Disable Schedules with archived catalog targets
Confirmed Project archival SHALL disable every enabled Schedule of that Project.
Confirmed Client archival SHALL disable every enabled direct Client Schedule and
every enabled Schedule of its Projects. Restoring the Client or Project SHALL
NOT enable those Schedules automatically.

#### Scenario: Archive a Project with enabled Schedules
- **WHEN** the user confirms Project archival
- **THEN** its enabled Schedules become disabled as part of the atomic hierarchy operation

#### Scenario: Archive a Client with enabled Schedules
- **WHEN** the user confirms Client archival
- **THEN** all enabled direct and Project Schedules beneath that Client become disabled as part of the atomic hierarchy operation

#### Scenario: Restore a catalog path
- **WHEN** an archived Client or Project is restored
- **THEN** related Schedules retain their disabled state until the user enables them separately

#### Scenario: Catalog cascade cannot be saved
- **WHEN** persistence fails while archiving a hierarchy that includes enabled Schedules
- **THEN** no included catalog record, Expense, pending occurrence, or Schedule changes state and the application displays a recoverable error with Retry

### Requirement: Retain Schedules and occurrence progress locally
The application SHALL retain Schedule configurations, enabled state, occurrence
snapshots, and materialization progress across restarts and complete local
backup/restore without transmitting them to an external service.

#### Scenario: Reopen the application
- **WHEN** the user reopens the application after saving Schedule changes
- **THEN** the same configurations, states, and occurrence history are available before catch-up runs

#### Scenario: Schedule data cannot be loaded
- **WHEN** local Schedule or occurrence data cannot be initialized or read
- **THEN** the Schedules view displays a recoverable error with Retry instead of presenting an empty state

#### Scenario: Restore scheduled data from backup
- **WHEN** the user restores a compatible complete backup containing Schedules and occurrences
- **THEN** their configurations, states, snapshots, and idempotency identities are restored
