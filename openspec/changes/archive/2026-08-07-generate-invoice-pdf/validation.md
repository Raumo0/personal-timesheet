## Validation plan

### Deterministic evidence

- Run native domain and source coverage first:
  - `cargo test --manifest-path src-tauri/Cargo.toml invoice::tests`
  - `cargo test --manifest-path src-tauri/Cargo.toml --test invoice_source`
- Run native invoice composition coverage after removing the separate PDF renderer:
  - `cargo test --manifest-path src-tauri/Cargo.toml invoice::tests`
  - `cargo test --manifest-path src-tauri/Cargo.toml --test invoice_source`
- Run focused frontend contracts and interactions:
  - `pnpm test -- src/features/invoices/in-memory-invoice-service.test.ts src/features/invoices/tauri-invoice-service.test.ts`
  - `pnpm test -- src/features/invoices/InvoicePage.test.tsx src/features/invoices/InvoicePreview.test.tsx src/features/invoices/DailyActivityChart.test.tsx src/features/invoices/WorkCategoryChart.test.tsx`
  - `pnpm test -- src/app/AppShell.test.tsx`
- Verify the native print regression explicitly:
  - `pnpm test -- src/features/invoices/tauri-invoice-service.test.ts src/features/invoices/InvoicePage.test.tsx`
  - `cargo check --manifest-path src-tauri/Cargo.toml`
- Verify invoice-only native print lifecycle and layout isolation:
  - `pnpm test -- src/features/invoices/InvoicePage.test.tsx`
  - confirm print mode and the marked ancestor path survive resolved native command dispatch until `afterprint`, but are removed on command failure and unmount
  - render the user-provided native macOS PDF as diagnosis evidence and confirm the regression is application chrome plus blank trailing pages rather than an invoice-composition error
- Run `python3 tools/agentic_workflow/validate_invoice_pdf.py` against representative short, long-label, multi-page, multi-project, optional-section, present-and-blank Invoice no., and adaptive-axis fixtures rendered from the real React preview with browser print CSS. Evidence must confirm A4 page boxes, selectable expected text, no content outside printable bounds, expected page/section presence, axis bounds at or above every bar, and visual parity with the preview DOM.
- Run broader compile and build checks:
  - `pnpm build`
  - `cargo check --manifest-path src-tauri/Cargo.toml`
- Run `pnpm exec openspec validate generate-invoice-pdf --strict --no-interactive` while refining the change and `pnpm exec openspec validate --all --strict --no-interactive` before review.
- Run the canonical registry with `python3 tools/agentic_workflow/validate.py --output .agentic-workflow/validation-evidence.json` immediately before independent review. Canonical task execution evidence and reviewer reports remain under `.agentic-workflow/`; this artifact does not duplicate their results.

### Manual limitations

- Automated bounds, text, font, and image-baseline checks cannot decide whether the final document achieves the intended quiet-fintech visual balance. A human must inspect representative rendered A4 pages at normal reading size before final approval.
- Native print-dialog appearance and PDF destination controls vary by operating system. Automated tests cover print orchestration and browser-generated PDF output; the implementation environment validates the real macOS flow, while other supported desktop platforms remain limited to compile and WebView API evidence until exercised there.
- This slice uses current effective rates plus visible draft overrides because historical rate snapshots do not exist. Validation can prove calculation consistency, but the user remains responsible for confirming rates before export.
