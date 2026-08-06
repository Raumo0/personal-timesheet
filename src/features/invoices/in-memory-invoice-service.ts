import {
  invoiceDocumentSchema,
  invoiceRequestSchema,
  type InvoiceDocument,
  type InvoiceRequest,
} from "./invoice";
import type { InvoiceService } from "./invoice-service";

type InvoicePrepare = (request: InvoiceRequest) => unknown;
type InvoicePrint = () => void | Promise<void>;

export class InMemoryInvoiceService implements InvoiceService {
  constructor(
    private readonly prepareInvoice: InvoicePrepare,
    private readonly printInvoice: InvoicePrint = () => undefined,
  ) {}

  async prepare(input: InvoiceRequest): Promise<InvoiceDocument> {
    const request = invoiceRequestSchema.parse(input);
    const document = await this.prepareInvoice(request);
    return invoiceDocumentSchema.parse(document);
  }

  async print(): Promise<void> {
    await this.printInvoice();
  }
}
