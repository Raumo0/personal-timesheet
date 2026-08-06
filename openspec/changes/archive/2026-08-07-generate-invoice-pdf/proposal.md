## Why

Recorded time and Expenses cannot yet be turned into a document that can be reviewed and sent for payment. The first invoice slice should produce one polished PDF directly from a Client and billing period without requiring a separate general-purpose Reports feature first.

## What Changes

- Replace the empty Reports destination with an invoice generator for one Client and an explicit inclusive date range.
- Aggregate saved time into Project and externally labelled `Work category` lines, use current effective hourly rates as editable draft values, and include eligible Expenses in the Client billing currency.
- Preview Work performed, Expenses, subtotals, and one non-duplicated Total due before export; block export until every included work line has a valid rate.
- Allow an optional manually entered `Invoice no.` such as `INV-2026-001` and omit the field completely when blank.
- Let the user include or omit an editable Payment note, Daily activity, and Work category breakdown from the exported document.
- Export the exact React invoice preview through the native WebView print flow using A4 print styles, the approved quiet-fintech document system, complete period labels, readable tables, and deterministic charts.
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
- New Tauri commands query invoice source data while the existing React preview becomes the single document renderer for screen and print.
- The native application uses the WebView's system print flow, where the user can save the rendered document as PDF without a second layout implementation.
- Focused TypeScript and Rust tests cover aggregation, money and duration totals, option-controlled content, chart scaling, and PDF generation failure handling.
