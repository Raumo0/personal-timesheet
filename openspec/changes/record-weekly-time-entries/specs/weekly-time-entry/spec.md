## Purpose

Defines how a local user selects catalog work and records, reviews, saves, and
corrects daily durations within a navigable Monday–Sunday Timesheet.

## ADDED Requirements

### Requirement: Navigate local calendar weeks
The application SHALL open the Monday–Sunday week containing the user's current
local date and SHALL provide Previous, Current, and Next controls. Past and
future weeks SHALL remain available for time entry.

#### Scenario: Open the current local week
- **WHEN** the user opens Timesheet on any local calendar date
- **THEN** the application displays the Monday through Sunday containing that local date

#### Scenario: Open the previous or next week
- **WHEN** the user chooses Previous or Next
- **THEN** the application displays the immediately adjacent Monday–Sunday week

#### Scenario: Return to the current week
- **WHEN** the user chooses Current while viewing any other week
- **THEN** the application returns to the week containing the current local date

#### Scenario: Cross a month or year boundary
- **WHEN** an adjacent Monday–Sunday week spans another month or year
- **THEN** every displayed day retains its correct local calendar date and order

#### Scenario: Correct a past week
- **WHEN** the user opens an earlier week
- **THEN** eligible saved entries in that week remain editable

### Requirement: Select hierarchical work rows
The application SHALL provide a `Select project or task` control grouped by
Client → Project → Task. It SHALL allow direct Project selection or Task
selection and SHALL include only records whose complete hierarchy path is
active. It SHALL NOT create an implicit or automatic General Task.

#### Scenario: Select a project directly
- **WHEN** the user selects an active Project beneath an active Client
- **THEN** one Project row is added with its Client and Project context

#### Scenario: Select a task
- **WHEN** the user selects an active Task beneath an active Project and Client
- **THEN** one Task row is added with its Client, Project, and Task context

#### Scenario: Exclude an inactive hierarchy path
- **WHEN** a Client, Project, or Task is archived
- **THEN** the selector excludes that record and every option whose required ancestor path is not fully active

#### Scenario: Select an existing row again
- **WHEN** the user selects a Project or Task already present in the displayed week
- **THEN** the application focuses the existing row instead of creating a duplicate

#### Scenario: Open a week without entries
- **WHEN** the displayed week has no saved time entries
- **THEN** the Timesheet shows its header, selector, and zero totals without preloading catalog rows

#### Scenario: Reload an empty selected row
- **WHEN** the user selects a work row but records no nonzero entry before reloading or reopening the week
- **THEN** that transient row is absent because empty row selection is not persisted

#### Scenario: Reload saved work rows
- **WHEN** the user reopens a week containing saved entries
- **THEN** the application reconstructs exactly the distinct Project and Task rows represented by those entries

### Requirement: Display a weekly entry grid and totals
The application SHALL display one work column, seven daily columns ordered
Monday through Sunday, and a Total column. It SHALL calculate a total for every
row, a total for every day, and a weekly grand total at their intersection.
Cells without saved entries SHALL appear blank rather than displaying zero.

#### Scenario: Display a project row
- **WHEN** a direct Project row is present
- **THEN** the work column identifies its Client and Project and provides one entry cell for each day

#### Scenario: Display a task row
- **WHEN** a Task row is present
- **THEN** the work column identifies its Client, Project, and Task and provides one entry cell for each day

#### Scenario: Calculate row and column totals
- **WHEN** saved entries exist in multiple rows and days
- **THEN** each row Total equals its seven entries, each footer day total equals that day's entries, and the grand total equals the complete week

#### Scenario: Display an absent entry
- **WHEN** no time entry is saved for a work item and date
- **THEN** its cell is visually empty while contributing zero to totals

### Requirement: Enter validated durations
The application SHALL accept daily durations in `H:MM` format and persist them
as non-negative integer minutes. Minutes SHALL contain two digits from `00`
through `59`, and the sum of all entries on one date SHALL NOT exceed `24:00`.

#### Scenario: Enter a valid duration
- **WHEN** the user enters a valid `H:MM` value such as `1:30`
- **THEN** the application interprets and displays it as 90 minutes

#### Scenario: Reject invalid minutes
- **WHEN** the user enters a value whose minute component is outside `00`–`59`
- **THEN** the value remains an unsaved draft and the cell identifies the format error

#### Scenario: Reject malformed or negative input
- **WHEN** the user enters a negative or non-`H:MM` value
- **THEN** the value remains an unsaved draft and the cell identifies the format error

#### Scenario: Accept exactly twenty-four hours in a day
- **WHEN** the proposed entry makes that date's total exactly `24:00`
- **THEN** the application accepts the duration

#### Scenario: Reject more than twenty-four hours in a day
- **WHEN** the proposed entry would make that date's total exceed `24:00`
- **THEN** the value remains unsaved and the changed cell identifies the daily-limit error

### Requirement: Autosave cell edits with persistent status
The application SHALL save a valid changed cell when the user presses Enter or
leaves the cell. It SHALL expose one persistent status near week navigation as
`No time saved`, `Unsaved changes`, `Saving…`, `Saved locally`, or
`Not saved · Retry`, and SHALL announce status changes accessibly.

#### Scenario: Save on Enter
- **WHEN** the user presses Enter in a changed cell containing a valid duration
- **THEN** the status moves through Saving… and reaches Saved locally only after local storage confirms the write

#### Scenario: Save on blur
- **WHEN** the user leaves a changed cell containing a valid duration
- **THEN** the application performs the same confirmed local save

#### Scenario: Restore the saved value
- **WHEN** the user presses Escape while editing a changed cell
- **THEN** the cell restores its last saved value and clears that draft

#### Scenario: Keep invalid input unsaved
- **WHEN** Enter or blur occurs with an invalid duration
- **THEN** the draft remains visible, the status is Unsaved changes, and local storage is not updated

#### Scenario: Save fails
- **WHEN** local persistence rejects a valid change
- **THEN** the entered draft remains visible, the cell is marked as failed, and the persistent status becomes Not saved · Retry

#### Scenario: Retry a failed save
- **WHEN** the user activates Retry after a failed save
- **THEN** the application retries that draft and reports Saved locally only after confirmed persistence

#### Scenario: Announce without success toasts
- **WHEN** cell saves succeed
- **THEN** the persistent status is announced through an aria-live region without creating a success toast for each cell

#### Scenario: Expose a persistent error
- **WHEN** a cell cannot be saved
- **THEN** the error remains available as an alert with the failed cell identifiable until retry, correction, or discard resolves it

### Requirement: Confirm deletion of saved time
The application SHALL interpret blank or `0:00` as deletion. Replacing an
existing nonzero saved entry with either value SHALL require confirmation and
SHALL display the cell as blank only after confirmed deletion.

#### Scenario: Confirm entry deletion
- **WHEN** the user replaces a saved nonzero entry with blank or `0:00` and confirms deletion
- **THEN** the saved entry is removed, the cell becomes blank, and totals are recalculated

#### Scenario: Cancel entry deletion
- **WHEN** the user cancels deletion of a saved nonzero entry
- **THEN** the cell restores its saved duration and totals remain unchanged

#### Scenario: Clear an unsaved draft
- **WHEN** a cell has no saved entry and the user clears its draft
- **THEN** no deletion confirmation is required and no time entry is persisted

#### Scenario: Entry deletion cannot be saved
- **WHEN** local persistence fails after the user confirms deletion
- **THEN** the saved value remains authoritative, the failed draft remains visible, and the interface exposes Not saved · Retry

### Requirement: Protect navigation with pending edits
The application SHALL wait for an in-progress save before changing weeks. It
SHALL keep the current week and focus the affected cell when saving fails or
input is invalid. Leaving Timesheet or closing the application with an unsaved
or invalid draft SHALL require `Stay` or `Discard changes`, with Stay as the
safe default.

#### Scenario: Navigate while saving
- **WHEN** the user requests another week while a cell is saving
- **THEN** the application waits and opens the requested week only after the save succeeds

#### Scenario: Save blocks week navigation
- **WHEN** the pending save fails
- **THEN** the current week remains open and focus returns to the failed cell

#### Scenario: Invalid draft blocks week navigation
- **WHEN** the user requests another week while a cell contains an invalid draft
- **THEN** the current week remains open and focus returns to the invalid cell

#### Scenario: Stay with unsaved changes
- **WHEN** the user attempts to leave Timesheet or close the application with an unsaved draft and chooses Stay
- **THEN** the Timesheet remains open with the draft unchanged

#### Scenario: Discard unsaved changes
- **WHEN** the user chooses Discard changes in the leave confirmation
- **THEN** unsaved drafts are discarded and the requested navigation or close continues without altering saved entries

### Requirement: Handle archived work rows
The application SHALL retain saved rows whose Client, Project, or Task later
becomes archived. Such a row SHALL display `No longer active`, make all entry
cells read-only, and provide `Restore to edit` that confirms and restores the
target plus only the archived ancestors required by its hierarchy.

#### Scenario: Display an archived project row
- **WHEN** a saved direct Project row has an archived Project or Client
- **THEN** the row remains visible as No longer active and its daily cells cannot be edited

#### Scenario: Display an archived task row
- **WHEN** a saved Task row has an archived Task, Project, or Client
- **THEN** the row remains visible as No longer active and its daily cells cannot be edited

#### Scenario: Preview restore to edit
- **WHEN** the user activates Restore to edit on a read-only row
- **THEN** the confirmation lists the target and each archived ancestor that will become active

#### Scenario: Restore the row to editing
- **WHEN** the user confirms Restore to edit and the lifecycle operation succeeds
- **THEN** exactly the confirmed hierarchy path becomes active and the row's daily cells become editable

#### Scenario: Restore to edit fails
- **WHEN** the lifecycle operation cannot be saved
- **THEN** the row remains read-only, no hierarchy state changes, and the interface exposes a recoverable error with Retry

### Requirement: Retain weekly time locally
The application SHALL retain successfully saved nonzero time entries across
application restarts and SHALL NOT transmit them to an external service. A load
failure SHALL be distinguishable from a week with no saved entries.

#### Scenario: Reopen the application
- **WHEN** the user closes and later reopens the application after saving time
- **THEN** the same dated work rows, durations, and totals are reconstructed

#### Scenario: Weekly data cannot be loaded
- **WHEN** local weekly data cannot be initialized or read
- **THEN** Timesheet displays a recoverable error with Retry instead of an empty week
