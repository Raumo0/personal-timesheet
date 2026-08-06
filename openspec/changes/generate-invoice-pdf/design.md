## Context

See `proposal.md` for motivation. Reports is currently an empty routed destination. Time entries, catalog rates, and Expenses already persist locally in SQLite, but there is no billing projection or PDF renderer. The existing Tauri dialog plugin already supplies a cross-platform save path.

The feature crosses React presentation, exact billing calculations, SQLite reads, native file output, and visual PDF composition. The document must be deterministic and independently testable without coupling the preview to the PDF library.

## Goals / Non-Goals

**Goals:**

- Keep source selection, billing calculation, chart data, and PDF layout behind a small native invoice interface.
- Produce the same amounts and chart inputs in preview and export.
- Render selectable text, vector tables, and vector charts in a polished A4 PDF.
- Keep the first slice migration-free and usable offline.

**Non-Goals:**

- Persist invoice entities, snapshots, numbering sequences, payment state, or source-entry billing state.
- Build a reusable analytics/reporting platform before the invoice.
- Implement legal, tax, address, or company-profile rules.
- Guarantee pixel identity between the responsive React preview and fixed A4 output; they share content and hierarchy, not a rendering engine.

## Decisions

### Use one native invoice facade

Add an `invoice` Rust module with two Tauri commands:

- `prepare_invoice(request) -> InvoiceDocument`
- `export_invoice_pdf(path, request) -> ExportReceipt`

`InvoiceRequest` contains the selected Client, inclusive dates, document identity including an optional manual Invoice no., included Expense IDs, per-line draft rate overrides, and optional-section settings. `InvoiceDocument` contains normalized Projects, Work performed lines, Expenses, exact minor-unit totals, Daily activity points and ticks, Work category shares, and validation issues.

Both commands call the same query and composition path. Export recomposes from the request instead of accepting frontend-calculated totals, preventing preview/export drift and stale source data from being silently exported. The React side owns only form state and renders the returned document.

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

### Generate fixed-layout vector PDF in Rust

Use a pinned `printpdf` dependency through a narrow `InvoicePdfRenderer` module. Build pages from explicit PDF operations, embedded licensed font assets, measured text, reusable `Work performed` and Expenses table pagination, and small chart primitives. Do not use the crate's evolving HTML-to-PDF path for the primary renderer: the approved document needs predictable wrapping, chart axes, and page boundaries.

The renderer accepts only `InvoiceDocument`; it does not query data or calculate money. Golden structural tests inspect page count, text, and bounds from representative fixtures. Rendered PDF fixtures are rasterized during deterministic validation for visual review at A4 dimensions.

Alternatives considered:

- WebView printing lacks a stable cross-platform Tauri contract for selecting and writing the exact PDF.
- Rasterizing the preview would make text less accessible and produce larger, lower-quality documents.

### Share semantic chart models, not drawing code

The composer returns Daily activity values, an hours-axis upper bound, and approximately five to eight human-readable ticks selected by a deterministic nice-step function. It also returns grouped Work category durations and percentage shares.

React uses those values for the preview, while the PDF renderer draws them with native vector primitives. This keeps scales and labels identical while allowing each surface to use its appropriate layout engine. Zero-hour dates remain in the Daily activity model.

### Treat document sections as explicit options

`PaymentNote`, `DailyActivity`, and `WorkCategoryBreakdown` each have one enabled state in `InvoiceRequest`. Payment-note text is meaningful only while enabled. The PDF layout builds a section list first, so disabled content allocates no heading, page, or residual spacing. A Work summary page is created only when at least one chart is enabled.

The UI presents these settings together under document customization instead of scattering them through the preview.

### Reuse the native save dialog and write atomically

The frontend reuses `@tauri-apps/plugin-dialog` to request a `.pdf` path and passes the chosen path to the export command. The native side renders bytes, writes a sibling temporary file, and atomically replaces the destination where the platform permits. A cancelled dialog never invokes export. A failed render or write returns a stable error category and leaves the draft visible.

## Risks / Trade-offs

- **[Current rates are not historical rates]** → Show every resolved rate in the draft, permit explicit draft replacement, and state in non-goals that invoice history and rate snapshots require a later change.
- **[Preview and PDF use different drawing engines]** → Share one native `InvoiceDocument`, deterministic chart ticks, and render representative PDFs during validation.
- **[Long tables or labels can overflow fixed pages]** → Centralize text measurement, wrapping, table row height, and page-break logic; validate short, long, and multi-project fixtures.
- **[PDF dependency increases native build size]** → Disable unused image/HTML features, embed only the required font weights, and record the release-size delta during validation.
- **[Repeated export can bill the same source twice]** → Keep this limitation explicit in the interface and non-goals; invoice history and billed-state ownership need a separate design.

## Migration Plan

No database migration is required. Add the native composer and renderer behind new commands, then replace the Reports empty state with the invoice generator. Rollback removes the route content and commands without changing saved user data or exported files.
