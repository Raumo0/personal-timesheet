import type { InvoiceDocument, InvoiceRequest } from "./invoice";

export interface InvoiceService {
  prepare(request: InvoiceRequest): Promise<InvoiceDocument>;
  print(): Promise<void>;
}

/** Compatibility shape for the AppShell dependency prop outside this task's scope. */
export interface ExportingInvoiceService extends InvoiceService {
  exportPdf?: unknown;
}
