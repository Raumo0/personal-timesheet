import { describe, expect, test } from "vitest";

import type { InvoiceDocument, InvoiceRequest } from "./invoice";
import type { InvoiceService } from "./invoice-service";

export type InvoicePrepareHandler = (
  request: InvoiceRequest,
) => InvoiceDocument | Promise<InvoiceDocument> | unknown;

export type InvoiceServiceFactory = (
  prepare: InvoicePrepareHandler,
) => InvoiceService;

export const invoiceServiceContractRequest: InvoiceRequest = {
  clientId: "client-1",
  senderName: "Northstar Studio",
  issueDate: "2026-02-08",
  invoiceNumber: "INV-2026-002",
  periodStart: "2026-02-01",
  periodEnd: "2026-02-07",
  includedExpenseIds: ["expense-1"],
  draftRateOverridesMinor: {},
  paymentNoteEnabled: true,
  paymentNote: "Payment due within 14 days.",
  includeDailyActivity: true,
  includeWorkCategoryBreakdown: true,
};

export function invoiceServiceContractDocument(
  rateMinor = 12_000,
): InvoiceDocument {
  return {
    senderName: "Northstar Studio",
    recipientName: "Atlas Labs",
    issueDate: "2026-02-08",
    invoiceNumber: "INV-2026-002",
    paymentNote: "Payment due within 14 days.",
    includeDailyActivity: true,
    includeWorkCategoryBreakdown: true,
    periodStart: "2026-02-01",
    periodEnd: "2026-02-07",
    currencyCode: "EUR",
    projects: [
      {
        id: "project-1",
        name: "Atlas launch",
        workLines: [
          {
            key: "project-1:task-1",
            label: "Product design",
            taskId: "task-1",
            minutes: 30,
            rateMinor,
            amountMinor: rateMinor / 2,
          },
        ],
        subtotalMinor: rateMinor / 2,
      },
    ],
    expenses: [
      {
        id: "expense-1",
        projectId: null,
        projectName: null,
        date: "2026-02-03",
        description: "Travel",
        billingAmountMinor: 2_500,
      },
    ],
    workSubtotalMinor: rateMinor / 2,
    expenseSubtotalMinor: 2_500,
    totalDueMinor: rateMinor / 2 + 2_500,
    totalMinutes: 30,
    activeDays: 1,
    dailyActivity: [
      { date: "2026-02-01", minutes: 0 },
      { date: "2026-02-02", minutes: 30 },
    ],
    dailyActivityAxis: { upperBoundHours: 1, ticks: [0, 0.2, 0.4, 0.6, 0.8, 1] },
    workCategoryShares: [
      {
        projectId: "project-1",
        projectName: "Atlas launch",
        lineKey: "project-1:task-1",
        label: "Product design",
        minutes: 30,
        share: 1,
      },
    ],
    validationIssues: [],
    exportable: true,
  };
}

export function runInvoiceServiceContract(
  implementation: string,
  createService: InvoiceServiceFactory,
): void {
  describe(`${implementation} invoice service contract`, () => {
    test("applies draft rate overrides without mutating caller data", async () => {
      const request = structuredClone(invoiceServiceContractRequest);
      request.draftRateOverridesMinor["project-1:task-1"] = 15_000;
      const originalRequest = structuredClone(request);
      const service = createService((received) => {
        const rate =
          received.draftRateOverridesMinor["project-1:task-1"] ?? 12_000;
        received.includedExpenseIds?.push("adapter-only-mutation");
        return invoiceServiceContractDocument(rate);
      });

      const document = await service.prepare(request);

      expect(document.projects[0].workLines[0]).toMatchObject({
        rateMinor: 15_000,
        amountMinor: 7_500,
      });
      expect(request).toEqual(originalRequest);
    });

    test("returns documents detached from adapter source data", async () => {
      const source = invoiceServiceContractDocument();
      const service = createService(() => source);

      const document = await service.prepare(invoiceServiceContractRequest);
      document.projects[0].workLines[0].label = "Caller-only mutation";

      expect(source.projects[0].workLines[0]).toMatchObject({
        label: "Product design",
        rateMinor: 12_000,
        amountMinor: 6_000,
      });
    });

    test("rejects malformed requests before calling the adapter", async () => {
      let calls = 0;
      const service = createService(() => {
        calls += 1;
        return invoiceServiceContractDocument();
      });
      const malformed = {
        ...invoiceServiceContractRequest,
        clientId: 42,
      };

      await expect(
        service.prepare(malformed as unknown as InvoiceRequest),
      ).rejects.toMatchObject({ name: "ZodError" });
      expect(calls).toBe(0);
    });

    test("rejects malformed adapter documents", async () => {
      const malformed = {
        ...invoiceServiceContractDocument(),
        activeDays: "one",
      };
      const service = createService(() => malformed);

      await expect(
        service.prepare(invoiceServiceContractRequest),
      ).rejects.toMatchObject({ name: "ZodError" });
    });
  });
}
