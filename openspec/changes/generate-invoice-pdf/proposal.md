## Why

Recorded time and Expenses cannot yet be turned into a document that can be reviewed and sent for payment. The first invoice slice should produce one polished PDF directly from a Client and billing period without requiring a separate general-purpose Reports feature first.

## What Changes

- Replace the empty Reports destination with an invoice generator for one Client and an explicit inclusive date range.
- Aggregate saved time into Project and externally labelled `Work category` lines, use current effective hourly rates as editable draft values, and include eligible Expenses in the Client billing currency.
- Preview Work performed, Expenses, subtotals, and one non-duplicated Total due before export; block export until every included work line has a valid rate.
- Allow an optional manually entered `Invoice no.` such as `INV-2026-001` and omit the field completely when blank.
- Let the user include or omit an editable Payment note, Daily activity, and Work category breakdown from the exported document.
- Export a polished A4 PDF through a native save dialog using the approved quiet-fintech document system, complete period labels, readable tables, and deterministic charts.
- Keep this slice local-only and read-only with respect to source time and Expense records.
- Treat saved invoice drafts, invoice history, payment status, automatic numbering, tax/legal profiles, a general Reports workspace, and a project-distribution chart as explicit non-goals.

## Capabilities

### New Capabilities

- `invoice-pdf-generation`: Configure, calculate, preview, and export one Client's time-and-expense invoice PDF with an optional work-summary page.

### Modified Capabilities

None.

## Impact

- The existing Reports route gains the invoice-generation interface.
- New frontend domain, preview, and export adapters consume Client, Project, Task, time-entry, and Expense data without modifying those records.
- New Tauri commands query invoice source data and write generated PDF bytes to a user-selected local path.
- The native application adds a PDF-rendering dependency and reuses the existing Tauri dialog integration for the destination path.
- Focused TypeScript and Rust tests cover aggregation, money and duration totals, option-controlled content, chart scaling, and PDF generation failure handling.
