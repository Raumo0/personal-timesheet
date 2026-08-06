## Purpose

Defines how a local user composes one Client's saved time and Expenses into a polished, configurable, invoice-ready PDF.

## ADDED Requirements

### Requirement: Configure one Client invoice period
The application SHALL provide an invoice generator in Reports for one active Client and one valid inclusive local-date range. It SHALL require a sender name, use the selected Client name as the recipient, default the issue date to the current local date, and allow an optional manually entered `Invoice no.` such as `INV-2026-001` without changing Client data. A blank Invoice no. SHALL remove the field completely from the preview and PDF.

#### Scenario: Start an invoice
- **WHEN** the user selects an active Client and enters a start date no later than the end date
- **THEN** the application prepares a draft for that Client, inclusive period, and Client billing currency

#### Scenario: Reject an invalid invoice identity or period
- **WHEN** the sender name is blank, either boundary is invalid, or the start date is after the end date
- **THEN** the application preserves the entered configuration, identifies each invalid value, and does not prepare an exportable document

#### Scenario: Keep document identity separate from Client data
- **WHEN** the user changes the sender name, issue date, or optional Invoice no. in the invoice generator
- **THEN** those draft values affect only the generated document and do not update the selected Client or other catalog records

#### Scenario: Omit a blank Invoice no.
- **WHEN** Invoice no. is blank
- **THEN** no Invoice no. label, value, or reserved space appears in the preview or exported PDF

### Requirement: Compose work lines from saved time
The application SHALL include saved nonzero time entries for the selected Client whose local dates fall within the inclusive period, including entries whose retained Project or Task is now archived. It SHALL group Task time beneath its Project and label the Task as `Work category`; direct Project time SHALL appear as `General project work` beneath that Project.

#### Scenario: Group Task time as a work category
- **WHEN** multiple included entries target the same Task within one Project
- **THEN** the draft presents one Work category line with their summed duration

#### Scenario: Keep Projects distinct
- **WHEN** included time belongs to more than one Project
- **THEN** the draft groups Work performed lines within their respective Projects without creating a project-distribution chart

#### Scenario: Include retained archived work
- **WHEN** a saved in-period time entry targets a Project or Task that was archived after entry
- **THEN** the draft retains that entry under its saved Project and Work category identity

#### Scenario: Present direct Project time
- **WHEN** an included time entry targets a Project without a Task
- **THEN** its duration contributes to that Project's `General project work` line

### Requirement: Calculate editable work amounts
Each Work performed line SHALL initially use the current effective hourly rate resolved from Task to Project to Client. The user SHALL be able to replace that line's draft rate with a non-negative value in the Client billing currency without updating the catalog. A line amount SHALL equal total line minutes multiplied by its draft hourly rate, divided by 60, and rounded once half-up to the billing currency's minor-unit precision.

#### Scenario: Use a Task override
- **WHEN** a Work category has an explicit Task hourly-rate override
- **THEN** its Work performed line initially uses that override

#### Scenario: Inherit a Project or Client rate
- **WHEN** a Work category has no Task override
- **THEN** its Work performed line initially uses the nearest available Project override or Client default hourly rate

#### Scenario: Override a draft rate
- **WHEN** the user enters a valid replacement rate for a Work performed line
- **THEN** the preview and exported amount use that rate while the underlying Task, Project, and Client rates remain unchanged

#### Scenario: Block a missing or invalid rate
- **WHEN** an included Work performed line has no available effective rate or contains an invalid draft rate
- **THEN** the application identifies that line and does not allow PDF export until a valid rate is entered

#### Scenario: Round a work line once
- **WHEN** a line's total minutes and hourly rate produce a fractional billing minor unit
- **THEN** the displayed and exported line amount is rounded half-up once at line level

### Requirement: Include eligible Expenses
The draft SHALL offer each active Expense belonging to the selected Client whose local expense date falls within the inclusive period. Eligible Expenses SHALL be selected by default, MAY be individually excluded from the draft, and SHALL use their saved billing currency and billing amount without conversion or recomputation.

#### Scenario: Include a Project Expense
- **WHEN** an active in-period Expense belongs to a Project of the selected Client
- **THEN** the draft selects it by default and identifies its Project, date, description, and saved billing amount

#### Scenario: Include a direct Client Expense
- **WHEN** an active in-period Expense belongs directly to the selected Client
- **THEN** the draft selects it by default without inventing a Project

#### Scenario: Exclude an Expense from this document
- **WHEN** the user deselects an eligible Expense
- **THEN** it is absent from the preview, totals, and PDF while its saved Expense record remains unchanged

#### Scenario: Preserve saved conversion
- **WHEN** an included Expense was recorded in another original currency
- **THEN** the invoice uses its saved Client billing amount and does not recalculate an exchange rate

### Requirement: Preview invoice totals and content
The generator SHALL preview Work performed lines, included Expenses, Work performed subtotal, Expenses subtotal, and one Total due in the Client billing currency. Total due SHALL equal the two subtotals, and export SHALL remain unavailable when the draft contains neither billable work time nor an included Expense.

#### Scenario: Calculate complete totals
- **WHEN** the draft contains valid Work performed lines and included Expenses
- **THEN** each subtotal equals its included lines and Total due equals Work performed plus Expenses

#### Scenario: Avoid duplicating Total due
- **WHEN** the invoice is previewed or exported
- **THEN** Total due appears once after the final Work performed and Expenses calculations and is not repeated in the header

#### Scenario: Reject an empty invoice
- **WHEN** the selected period contains no billable time and no included Expense
- **THEN** the application explains that there is nothing to invoice and does not allow PDF export

### Requirement: Configure optional document sections
The generator SHALL let the user independently include or omit an editable Payment note, Daily activity, and Work category breakdown. A disabled option SHALL remove its complete block from the preview and exported PDF rather than leaving an empty heading or space.

#### Scenario: Include an edited Payment note
- **WHEN** Payment note is enabled with non-empty text
- **THEN** that exact draft text appears in the invoice section without modifying stored Client data

#### Scenario: Omit the Payment note
- **WHEN** Payment note is disabled
- **THEN** no Payment note heading, text, or reserved space appears in the document

#### Scenario: Omit the work-summary page
- **WHEN** both Daily activity and Work category breakdown are disabled
- **THEN** the PDF contains no Work summary page

#### Scenario: Include one summary chart
- **WHEN** exactly one summary-chart option is enabled
- **THEN** the Work summary contains only that chart plus the approved summary metrics

### Requirement: Render a readable quiet-fintech document
The exported PDF SHALL use A4 pages, a strict grid, compact typography, one restrained deep accent, tabular numeric alignment, subtle separators, and deterministic pagination. It SHALL identify the document as `Invoice` without displaying the internal product name `Personal Timesheet`, and SHALL keep text, tables, totals, charts, and page footers inside printable bounds without overlap or clipping.

#### Scenario: Format the full period
- **WHEN** the document language is English and the period is 1 through 28 February 2026
- **THEN** the period is displayed as `1 Feb 2026 – 28 Feb 2026`

#### Scenario: Paginate long content
- **WHEN** Work performed or Expenses do not fit in the remaining page space
- **THEN** the document continues them on another A4 page with repeated column headings and places the final totals after the final included line

#### Scenario: Render long work-category names
- **WHEN** a Work category name exceeds the normal single-line width
- **THEN** it wraps within its allocated area without colliding with hours, rates, amounts, or chart values

#### Scenario: Render invoice identity
- **WHEN** the PDF is generated
- **THEN** it shows `Invoice`, sender, recipient, Project context, issue date, optional Invoice no., and the full period without showing `Personal Timesheet`

### Requirement: Render Daily activity
When enabled, Daily activity SHALL display one vertical bar for every date in the inclusive period, including zero-hour dates. It SHALL use an adaptive hours axis with approximately five to eight human-readable intervals, a rounded upper bound at or above the maximum daily duration, thin dotted horizontal guides, and angled date labels formatted like `Mon, Feb 2`.

#### Scenario: Display worked and unworked dates
- **WHEN** the period contains both dates with saved time and dates without saved time
- **THEN** every date appears in chronological order and only worked dates have positive-height bars

#### Scenario: Scale a short daily maximum
- **WHEN** the maximum daily duration is small
- **THEN** the hours axis uses a fractional human-readable step and still provides approximately five to eight intervals

#### Scenario: Scale a large daily maximum
- **WHEN** the maximum daily duration is large
- **THEN** the hours axis uses a larger human-readable step and its rounded upper bound does not clip the maximum bar

#### Scenario: Label every date compactly
- **WHEN** Daily activity is rendered for a multi-week period
- **THEN** its date labels use abbreviated weekday and month names, include the day number, and are angled to remain distinguishable

### Requirement: Render Work category breakdown
When enabled, Work category breakdown SHALL show categories as a vertical list of horizontal proportional tracks grouped by Project. Each track SHALL display the full Work category label, total duration, and share of included work time; the Work summary SHALL show Total hours and Active days but SHALL NOT show a count of Tasks or Work categories.

#### Scenario: Compare work categories
- **WHEN** included time spans multiple Work categories
- **THEN** each category receives one directly labelled horizontal track proportional to its duration

#### Scenario: Keep a short bar readable
- **WHEN** a Work category represents a small share of total work time
- **THEN** its full label and value remain readable without depending on the filled bar width

#### Scenario: Show approved summary metrics
- **WHEN** at least one work-summary chart is enabled
- **THEN** the summary shows Total hours and the count of distinct dates with positive included time as Active days, without a Task or Work category count

### Requirement: Export through a native save flow
The application SHALL open a native PDF save dialog from an exportable preview, suggest a filesystem-safe filename derived from Client and period, and write a valid PDF only to the user-selected path. Cancelling SHALL leave the draft intact without an error, and generation or write failures SHALL leave source records unchanged and expose a recoverable error.

#### Scenario: Export a PDF
- **WHEN** the user confirms a destination in the native save dialog
- **THEN** the application writes the previewed invoice content as a PDF at that path and reports completion

#### Scenario: Cancel export
- **WHEN** the user closes the native save dialog without selecting a path
- **THEN** no file is written, no error is shown, and the configured draft remains available

#### Scenario: Export fails
- **WHEN** PDF generation or the selected filesystem write fails
- **THEN** no source time, Expense, Client, Project, or Task record changes and the interface displays a retryable error

### Requirement: Keep invoice generation local and transient
The application SHALL read source data and generate the invoice entirely on the local device. This slice SHALL NOT persist invoice drafts, exported-document history, payment state, or associations that mark source records as invoiced.

#### Scenario: Reopen Reports after export
- **WHEN** the user closes and later reopens the application after exporting a PDF
- **THEN** source time and Expenses remain available but no invoice-history record or payment status is inferred from that export

#### Scenario: Generate without network access
- **WHEN** the device has no network connection
- **THEN** invoice preview and PDF export remain available from local data
