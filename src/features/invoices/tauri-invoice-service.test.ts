import { expect, test, vi } from "vitest";

import {
  invoiceServiceContractDocument,
  invoiceServiceContractRequest,
  runInvoiceServiceContract,
} from "./invoice-service.contract";
import { TauriInvoiceService } from "./tauri-invoice-service";

runInvoiceServiceContract("TauriInvoiceService", (prepare) =>
  new TauriInvoiceService({
    invoke: async (_command, args) =>
      prepare(args?.request as typeof invoiceServiceContractRequest),
  }),
);

test("invokes prepare_invoice with the exact parsed request payload", async () => {
  const invoke = vi.fn().mockResolvedValue(invoiceServiceContractDocument());
  const service = new TauriInvoiceService({ invoke });

  await expect(service.prepare(invoiceServiceContractRequest)).resolves.toEqual(
    invoiceServiceContractDocument(),
  );
  expect(invoke).toHaveBeenCalledOnce();
  expect(invoke).toHaveBeenCalledWith("prepare_invoice", {
    request: invoiceServiceContractRequest,
  });
});

test("invokes print_invoice without a payload", async () => {
  const invoke = vi.fn().mockResolvedValue(undefined);
  const service = new TauriInvoiceService({ invoke });

  await expect(service.print()).resolves.toBeUndefined();

  expect(invoke).toHaveBeenCalledOnce();
  expect(invoke).toHaveBeenCalledWith("print_invoice");
});
