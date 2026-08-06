import { invoke } from "@tauri-apps/api/core";

import {
  invoiceDocumentSchema,
  invoiceRequestSchema,
  type InvoiceDocument,
  type InvoiceRequest,
} from "./invoice";
import type { InvoiceService } from "./invoice-service";

type Invoke = (
  command: string,
  args?: Record<string, unknown>,
) => Promise<unknown>;

export interface TauriInvoiceDependencies {
  invoke: Invoke;
}

const productionDependencies: TauriInvoiceDependencies = {
  invoke,
};

export class TauriInvoiceService implements InvoiceService {
  constructor(
    private readonly dependencies: TauriInvoiceDependencies =
      productionDependencies,
  ) {}

  async prepare(input: InvoiceRequest): Promise<InvoiceDocument> {
    const request = invoiceRequestSchema.parse(input);
    const document = await this.dependencies.invoke("prepare_invoice", {
      request,
    });
    return invoiceDocumentSchema.parse(document);
  }

  async print(): Promise<void> {
    await this.dependencies.invoke("print_invoice");
  }
}
