## 1. Native invoice domain

- [ ] 1.1 Add `src-tauri/src/invoice.rs` and focused unit tests for request validation, inclusive date filtering, archived work retention, Project and Work category grouping, `General project work`, effective-rate resolution, draft overrides, exact half-up line rounding, subtotals, Active days, and nice Daily activity ticks; verify with `cargo test --manifest-path src-tauri/Cargo.toml invoice::tests`.
- [ ] 1.2 Add the SQLite `InvoiceSourceSnapshot` loader and `prepare_invoice` command in `src-tauri/src/invoice.rs`, register it in `src-tauri/src/lib.rs`, and cover retained archived targets, active Expense eligibility, Client ownership, and read-only behavior in `src-tauri/tests/invoice_source.rs`; verify with `cargo test --manifest-path src-tauri/Cargo.toml --test invoice_source`.

## 2. Native PDF renderer

- [ ] 2.1 Add the pinned minimal PDF dependency to `src-tauri/Cargo.toml` and `src-tauri/Cargo.lock`, licensed font assets under `src-tauri/assets/fonts/`, and `src-tauri/src/invoice_pdf.rs` with measured A4 primitives, compact quiet-fintech tokens, wrapped text, Work performed and Expenses tables, repeated headings, footers, optional Payment note, optional Invoice no., and one final Total due; verify with `cargo test --manifest-path src-tauri/Cargo.toml invoice_pdf::tests::invoice_pages`.
- [ ] 2.2 Extend `src-tauri/src/invoice_pdf.rs` with optional Work summary pagination, adaptive Daily activity axes and dotted guides, angled `Mon, Feb 2` labels, and grouped horizontal Work category tracks; add short, long-label, long-table, multi-project, single-chart, and no-summary fixtures under `src-tauri/tests/fixtures/invoices/`; verify with `cargo test --manifest-path src-tauri/Cargo.toml invoice_pdf::tests`.

## 3. Frontend invoice boundary

- [ ] 3.1 Add parsed invoice request/document types and an `InvoiceService` interface in `src/features/invoices/invoice.ts` and `src/features/invoices/invoice-service.ts`, plus `InMemoryInvoiceService` and `TauriInvoiceService` adapters with contract tests in `src/features/invoices/invoice-service.contract.ts`, `src/features/invoices/in-memory-invoice-service.test.ts`, and `src/features/invoices/tauri-invoice-service.test.ts`; verify with `pnpm test -- src/features/invoices/in-memory-invoice-service.test.ts src/features/invoices/tauri-invoice-service.test.ts`.

## 4. Invoice generator interface

- [ ] 4.1 Build `src/features/invoices/InvoicePage.tsx` and `src/features/invoices/InvoicePage.test.tsx` for active Client selection, required sender, recipient display, issue date, optional manual Invoice no. with complete blank-state omission, full `D Mon YYYY – D Mon YYYY` period, inclusive date validation, loading/retry/empty states, editable work rates, and individual Expense inclusion; verify with `pnpm test -- src/features/invoices/InvoicePage.test.tsx`.
- [ ] 4.2 Add `src/features/invoices/InvoicePreview.tsx`, `src/features/invoices/DailyActivityChart.tsx`, `src/features/invoices/WorkCategoryChart.tsx`, their focused tests, and `src/features/invoices/invoice.css` for the approved responsive quiet-fintech preview, non-duplicated Total due, optional Payment note, optional Work summary, adaptive labelled axes, long-name wrapping, and accessible chart summaries; verify with `pnpm test -- src/features/invoices/InvoicePreview.test.tsx src/features/invoices/DailyActivityChart.test.tsx src/features/invoices/WorkCategoryChart.test.tsx`.

## 5. Export and application integration

- [ ] 5.1 Add atomic `export_invoice_pdf` behavior across `src-tauri/src/invoice.rs`, `src-tauri/src/invoice_pdf.rs`, and `src-tauri/src/lib.rs`, then wire native `.pdf` destination selection, safe default filename, cancellation, success, and retryable failures through `src/features/invoices/tauri-invoice-service.ts`; verify with `cargo test --manifest-path src-tauri/Cargo.toml invoice_export` and `pnpm test -- src/features/invoices/tauri-invoice-service.test.ts`.
- [ ] 5.2 Replace the Reports placeholder with lazy-loaded `InvoicePage` wiring in `src/App.tsx`, `src/app/AppShell.tsx`, and `src/app/AppShell.test.tsx`, preserving navigation and Timesheet leave guards; verify with `pnpm test -- src/app/AppShell.test.tsx src/features/invoices/InvoicePage.test.tsx`.

## 6. Integrated verification and visual quality

- [ ] 6.1 Add `tools/agentic_workflow/validate_invoice_pdf.py` with deterministic semantic and rendered-page checks, register its exact command through the Validation Contract Human Gate in `docs/agentic-workflow/validation-contract.md`, and verify the gate script directly before relying on it.
- [ ] 6.2 Validate representative exported PDFs at A4 size for font embedding, selectable text, page bounds, long labels, adaptive scales, optional sections, and quiet-fintech visual balance; then run `pnpm build`, `cargo check --manifest-path src-tauri/Cargo.toml`, and `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json` before independent review.
