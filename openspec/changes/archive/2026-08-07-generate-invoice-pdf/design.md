## Context

See `proposal.md` for motivation. Reports is currently an empty routed destination. Time entries, catalog rates, and Expenses already persist locally in SQLite, but there is no billing projection or PDF renderer. The existing Tauri dialog plugin already supplies a cross-platform save path.

The feature crosses React presentation, exact billing calculations, SQLite reads, and native WebView printing. The first implementation used an independent Rust PDF layout and exposed visible preview/export drift. The preview must now be the document renderer rather than merely a second representation of shared data.

## Goals / Non-Goals

**Goals:**

- Keep source selection, billing calculation, and chart data behind a small native invoice interface.
- Render preview and PDF from the same React document tree and CSS design system.
- Render selectable text, CSS tables, and SVG charts in a polished A4 PDF.
- Keep the first slice migration-free and usable offline.

**Non-Goals:**

- Persist invoice entities, snapshots, numbering sequences, payment state, or source-entry billing state.
- Build a reusable analytics/reporting platform before the invoice.
- Implement legal, tax, address, or company-profile rules.
- Introduce a second PDF-specific component tree or drawing engine.

## Decisions

### Use one native invoice facade

Add an `invoice` Rust module with one Tauri command:

- `prepare_invoice(request) -> InvoiceDocument`

`InvoiceRequest` contains the selected Client, inclusive dates, document identity including an optional manual Invoice no., included Expense IDs, per-line draft rate overrides, and optional-section settings. `InvoiceDocument` contains normalized Projects, Work performed lines, Expenses, exact minor-unit totals, Daily activity points and ticks, Work category shares, and validation issues.

The command owns source queries and all billing calculations. Before printing, the frontend refreshes the document from the current request so the visible print tree uses authoritative current data rather than frontend-calculated totals. The React side owns form state and renders the returned document.

Alternatives considered:

- Calculating in React would simplify preview updates but duplicate authority when Rust writes the PDF.
- A generic Reports query layer would broaden the slice before a second consumer exists.

### Keep invoice composition pure after one source query

The native adapter loads one `InvoiceSourceSnapshot` in a read transaction: Client identity and currency, Projects and Tasks needed by matching time entries, their current rate chain, included time entries, and active in-period Expenses. Archived work targets remain queryable for retained time; archived Expenses are not candidates.

A pure composer validates the request, groups minutes, resolves initial rates Task → Project → Client, applies draft-only overrides, calculates each line once in integer minor units with explicit half-up rounding, and derives totals and chart data. It does not write SQLite. Focused unit tests exercise this module without Tauri or a real file system.

Alternatives considered:

- Reading through several existing frontend catalogs would require coordination across independent snapshots and expose partial-load states.
- Adding invoice tables now would imply history and lifecycle behavior outside this slice.

### Keep invoice identity manual and optional

The first slice labels the field `Invoice no.` and accepts a manual value such as `INV-2026-001`. It does not generate, reserve, validate uniqueness, or persist a numbering sequence. Normalized blank input becomes absence, and the renderer allocates no label or space for it.

This avoids exposing the internal `PT` product abbreviation while keeping the document professionally identifiable. Automatic sequential numbering belongs with future persisted invoice history.

### Represent direct Project time explicitly

Task names are externally labelled `Work category`. Direct Project time becomes a synthetic presentation line named `General project work`; it is not persisted as a Task. Group keys retain Project and optional Task identity so equal category names in different Projects never merge.

This preserves the existing time-entry model without inventing catalog data or treating a Task as an assigned to-do.

### Print the React document instead of redrawing it

`InvoicePreview` is the single document component. Screen styles present that component inside the generator; print orchestration marks its ancestor path so `@media print` removes sibling application chrome and controls from layout while flattening only those ancestors. The existing preview therefore becomes the sole normal-flow print document without cloning or absolutely positioning it. A4 rules preserve colors and apply deterministic breaks to document sections and table rows. The same HTML, CSS, fonts, and SVG chart components therefore reach both preview and PDF.

Export invokes a registered Tauri command that calls the current WebView's native `print()` API. This keeps the operating-system print dialog behind an explicit native boundary instead of depending on a direct DOM `window.print()` call that can return without opening a dialog in the packaged WebView. The operating system owns destination selection, including Save as PDF. The application does not rasterize the preview or ship a browser runtime.

Alternatives considered:

- Keeping `printpdf` preserves direct filesystem writes but repeats every layout decision and caused the observed mismatch.
- `html2canvas` and screenshot-based PDF libraries preserve pixels but lose selectable vector text and degrade charts.
- React PDF libraries still require a second renderer-specific component tree.
- Shipping Playwright or Chromium would reproduce browser output but add an unsuitable runtime dependency to the desktop application.

### Share one chart implementation

The composer returns Daily activity values, an hours-axis upper bound, and approximately five to eight human-readable ticks selected by a deterministic nice-step function. It also returns grouped Work category durations and percentage shares.

React uses those values once in SVG chart components shared by screen and print. Zero-hour dates remain in the Daily activity model, and print CSS may resize the chart container without changing its direction, scale, ticks, or labels.

### Treat document sections as explicit options

`PaymentNote`, `DailyActivity`, and `WorkCategoryBreakdown` each have one enabled state in `InvoiceRequest`. Payment-note text is meaningful only while enabled. The PDF layout builds a section list first, so disabled content allocates no heading, page, or residual spacing. A Work summary page is created only when at least one chart is enabled.

The UI presents these settings together under document customization instead of scattering them through the preview.

### Use the system print destination flow

The frontend refreshes the authoritative draft, marks the existing preview and its ancestor path for invoice-only printing, waits for fonts and the next rendered frame, and asks the invoice adapter to invoke the registered native print command for the current WebView. Because the native command only schedules WebKit's print operation, successful command return does not clear print mode. The `afterprint` event clears it after cancellation or saving; command failure and component unmount clear it immediately. Cancelling or saving does not modify source data, and a failure to start printing becomes a retryable interface error.

## Risks / Trade-offs

- **[Current rates are not historical rates]** → Show every resolved rate in the draft, permit explicit draft replacement, and state in non-goals that invoice history and rate snapshots require a later change.
- **[WebViews can differ in pagination details]** → Keep document geometry in standards-based print CSS, avoid fragile fixed coordinates, and render representative A4 PDFs with Chromium in deterministic validation while manually checking the native macOS flow.
- **[Long tables or labels can overflow fixed pages]** → Use wrapping plus CSS break rules on semantic sections and rows; validate short, long, and multi-project fixtures.
- **[System print dialogs do not report save versus cancel]** → Treat return from the print flow as neutral completion, preserve the draft, and never infer invoice history or payment state.
- **[Repeated export can bill the same source twice]** → Keep this limitation explicit in the interface and non-goals; invoice history and billed-state ownership need a separate design.

## Migration Plan

No database migration is required. Remove the Rust PDF renderer and its assets, keep the native composer, and route export through print styles on the existing React preview. Rollback restores the prior renderer without changing saved user data or exported files.
