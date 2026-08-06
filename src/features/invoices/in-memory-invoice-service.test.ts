import { runInvoiceServiceContract } from "./invoice-service.contract";
import { InMemoryInvoiceService } from "./in-memory-invoice-service";

runInvoiceServiceContract(
  "InMemoryInvoiceService",
  (prepare) => new InMemoryInvoiceService(prepare),
);
