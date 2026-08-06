import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { Client } from "../clients/client";
import type { ClientCatalog } from "../clients/client-catalog";
import { InMemoryClientCatalog } from "../clients/in-memory-client-catalog";
import type { InvoiceDocument, InvoiceRequest } from "./invoice";
import type { InvoiceService } from "./invoice-service";
import {
  invoiceServiceContractDocument,
  invoiceServiceContractRequest,
} from "./invoice-service.contract";
import { InvoicePage } from "./InvoicePage";

const timestamp = "2026-02-01T10:00:00.000Z";

function client(overrides: Partial<Client> = {}): Client {
  return {
    id: "client-1",
    name: "Atlas Labs",
    currencyCode: "EUR",
    hourlyRateMinor: 12_000,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt: null,
    ...overrides,
  };
}

function service(
  prepare: (request: InvoiceRequest) => InvoiceDocument | Promise<InvoiceDocument>,
  printInvoice: () => void | Promise<void> = async () => undefined,
): InvoiceService & { print: ReturnType<typeof vi.fn> } {
  return {
    prepare: vi.fn(async (request) => prepare(request)),
    print: vi.fn(async () => printInvoice()),
  } as InvoiceService & { print: ReturnType<typeof vi.fn> };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

function expectExactPrintPath(preview: HTMLElement) {
  let current: HTMLElement | null = preview;
  let pathLength = 0;
  while (current) {
    expect(current).toHaveAttribute("data-invoice-print-path");
    pathLength += 1;
    if (current === document.body) break;
    current = current.parentElement;
  }
  expect(current).toBe(document.body);
  expect(document.querySelectorAll("[data-invoice-print-path]")).toHaveLength(
    pathLength,
  );
}

function expectPrintModeCleared() {
  expect(document.documentElement).not.toHaveAttribute("data-invoice-printing");
  expect(document.querySelectorAll("[data-invoice-print-path]")).toHaveLength(0);
}

function expectAfterPrintListenerRemoved() {
  document.documentElement.setAttribute("data-invoice-printing", "sentinel");
  window.dispatchEvent(new Event("afterprint"));
  expect(document.documentElement).toHaveAttribute(
    "data-invoice-printing",
    "sentinel",
  );
  document.documentElement.removeAttribute("data-invoice-printing");
}

function renderPage(options: {
  catalog?: ClientCatalog;
  invoiceService?: InvoiceService;
} = {}) {
  const invoiceService =
    options.invoiceService ?? service(() => invoiceServiceContractDocument());
  render(
    <InvoicePage
      clientCatalog={
        options.catalog ?? new InMemoryClientCatalog({ clients: [client()] })
      }
      invoiceService={invoiceService}
      today={() => new Date(2026, 1, 8)}
    />,
  );
  return invoiceService;
}

async function completeConfiguration(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByRole("option", { name: "Atlas Labs" });
  await user.selectOptions(screen.getByRole("combobox", { name: "Client" }), "client-1");
  await user.type(screen.getByRole("textbox", { name: "Sender name" }), "Northstar Studio");
  await user.type(screen.getByLabelText("Period start"), "2026-02-01");
  await user.type(screen.getByLabelText("Period end"), "2026-02-07");
}

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-invoice-printing");
  document
    .querySelectorAll("[data-invoice-print-path]")
    .forEach((element) => element.removeAttribute("data-invoice-print-path"));
  vi.restoreAllMocks();
});

describe("InvoicePage", () => {
  test("shows client loading, empty, and retryable failure states", async () => {
    const pendingCatalog: ClientCatalog = {
      list: () => new Promise(() => undefined),
      get: async () => client(),
      create: async () => client(),
      update: async () => client(),
    };
    const first = renderPage({ catalog: pendingCatalog });
    expect(screen.getByRole("status")).toHaveTextContent("Loading clients");
    cleanup();

    renderPage({ catalog: new InMemoryClientCatalog() });
    expect(
      await screen.findByRole("heading", { name: "No active clients" }),
    ).toBeInTheDocument();
    cleanup();

    const list = vi
      .fn<ClientCatalog["list"]>()
      .mockRejectedValueOnce(new Error("database locked"))
      .mockResolvedValueOnce([client()]);
    const catalog: ClientCatalog = {
      list,
      get: async () => client(),
      create: async () => client(),
      update: async () => client(),
    };
    renderPage({ catalog, invoiceService: first });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Clients could not be loaded",
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("option", { name: "Atlas Labs" })).toBeInTheDocument();
  });

  test("prepares an inclusive invoice with recipient, local issue date, and full period", async () => {
    const user = userEvent.setup();
    const invoiceService = service((request) => ({
      ...invoiceServiceContractDocument(),
      invoiceNumber: request.invoiceNumber,
    }));
    renderPage({ invoiceService });
    await completeConfiguration(user);

    expect(screen.getByLabelText("Issue date")).toHaveValue("2026-02-08");
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));

    expect(invoiceService.prepare).toHaveBeenCalledWith({
      ...invoiceServiceContractRequest,
      invoiceNumber: null,
      includedExpenseIds: null,
      paymentNoteEnabled: false,
      paymentNote: "",
      includeDailyActivity: false,
      includeWorkCategoryBreakdown: false,
    });
    expect(
      await screen.findByRole("heading", { name: "Atlas Labs" }),
    ).toBeInTheDocument();
    expect(screen.getByText("1 Feb 2026 – 7 Feb 2026")).toBeInTheDocument();
    expect(screen.queryByText(/^Invoice no\.$/)).not.toBeInTheDocument();
  });

  test("preserves invalid configuration and does not prepare it", async () => {
    const user = userEvent.setup();
    const invoiceService = service(() => invoiceServiceContractDocument());
    renderPage({ invoiceService });
    await screen.findByRole("option", { name: "Atlas Labs" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Client" }), "client-1");
    await user.type(screen.getByLabelText("Period start"), "2026-02-08");
    await user.type(screen.getByLabelText("Period end"), "2026-02-07");
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));

    expect(screen.getByRole("textbox", { name: "Sender name" })).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "Sender name" })).toHaveAttribute(
      "aria-describedby",
      "sender-name-error",
    );
    expect(screen.getByLabelText("Period start")).toHaveAttribute(
      "aria-describedby",
      "period-start-error",
    );
    expect(screen.getByText("Enter a sender name")).toBeInTheDocument();
    expect(screen.getByText("Start date must be on or before end date")).toBeInTheDocument();
    expect(invoiceService.prepare).not.toHaveBeenCalled();
  });

  test("includes a manual invoice number and omits it again when cleared", async () => {
    const user = userEvent.setup();
    const invoiceService = service((request) => ({
      ...invoiceServiceContractDocument(),
      invoiceNumber: request.invoiceNumber,
    }));
    renderPage({ invoiceService });
    await completeConfiguration(user);
    const invoiceNumber = screen.getByRole("textbox", { name: "Invoice no. (optional)" });
    await user.type(invoiceNumber, "INV-2026-041");
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));
    expect(await screen.findByText("INV-2026-041")).toBeInTheDocument();

    await user.clear(invoiceNumber);
    await user.click(screen.getByRole("button", { name: "Refresh draft" }));
    await waitFor(() =>
      expect(invoiceService.prepare).toHaveBeenLastCalledWith(
        expect.objectContaining({ invoiceNumber: null }),
      ),
    );
    expect(screen.queryByText(/^Invoice no\.$/)).not.toBeInTheDocument();
    expect(screen.queryByText("INV-2026-041")).not.toBeInTheDocument();
  });

  test("prepares editable optional sections and integrates the invoice preview", async () => {
    const user = userEvent.setup();
    const invoiceService = service((request) => ({
      ...invoiceServiceContractDocument(),
      paymentNote: request.paymentNoteEnabled ? request.paymentNote : null,
      includeDailyActivity: request.includeDailyActivity,
      includeWorkCategoryBreakdown: request.includeWorkCategoryBreakdown,
    }));
    renderPage({ invoiceService });
    await completeConfiguration(user);

    await user.click(screen.getByRole("checkbox", { name: "Include Payment note" }));
    await user.type(
      screen.getByRole("textbox", { name: "Payment note text" }),
      "Please pay within 21 days.",
    );
    await user.click(screen.getByRole("checkbox", { name: "Include Daily activity" }));
    await user.click(
      screen.getByRole("checkbox", { name: "Include Work category breakdown" }),
    );
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));

    const preview = await screen.findByRole("article", { name: "Invoice preview" });
    expect(preview).toBeInTheDocument();
    expect(within(preview).getByText("Please pay within 21 days.")).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: "Daily activity" })).toBeInTheDocument();
    expect(
      screen.getByRole("figure", { name: "Work category breakdown" }),
    ).toBeInTheDocument();
    expect(invoiceService.prepare).toHaveBeenLastCalledWith(
      expect.objectContaining({
        paymentNoteEnabled: true,
        paymentNote: "Please pay within 21 days.",
        includeDailyActivity: true,
        includeWorkCategoryBreakdown: true,
      }),
    );
  });

  test("refreshes draft work rates in Client currency without mutating source data", async () => {
    const user = userEvent.setup();
    const source = invoiceServiceContractDocument();
    const invoiceService = service((request) => {
      const rate = request.draftRateOverridesMinor["project-1:task-1"] ?? 12_000;
      return {
        ...structuredClone(source),
        projects: [
          {
            ...structuredClone(source.projects[0]),
            workLines: [
              {
                ...structuredClone(source.projects[0].workLines[0]),
                rateMinor: rate,
                amountMinor: rate / 2,
              },
            ],
            subtotalMinor: rate / 2,
          },
        ],
      };
    });
    renderPage({ invoiceService });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));
    const rate = await screen.findByRole("textbox", {
      name: "Hourly rate for Product design",
    });
    expect(rate).toHaveValue("120.00");
    expect(screen.getByText("EUR per hour")).toBeInTheDocument();

    await user.clear(rate);
    await user.type(rate, "150.00");
    await user.click(screen.getByRole("button", { name: "Refresh draft" }));

    expect(invoiceService.prepare).toHaveBeenLastCalledWith(
      expect.objectContaining({
        draftRateOverridesMinor: { "project-1:task-1": 15_000 },
      }),
    );
    expect(source.projects[0].workLines[0].rateMinor).toBe(12_000);
  });

  test("renders zero-decimal currency rates without a decimal separator", async () => {
    const user = userEvent.setup();
    const document = invoiceServiceContractDocument();
    document.currencyCode = "JPY";
    renderPage({
      catalog: new InMemoryClientCatalog({
        clients: [client({ currencyCode: "JPY" })],
      }),
      invoiceService: service(() => document),
    });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));

    expect(
      await screen.findByRole("textbox", { name: "Hourly rate for Product design" }),
    ).toHaveValue("12000");
    expect(screen.getByText("JPY per hour")).toBeInTheDocument();
  });

  test("preserves eligible Expenses while selection changes refresh the draft", async () => {
    const user = userEvent.setup();
    const source = invoiceServiceContractDocument();
    const invoiceService = service((request) => ({
      ...structuredClone(source),
      expenses:
        request.includedExpenseIds === null || request.includedExpenseIds.includes("expense-1")
          ? structuredClone(source.expenses)
          : [],
    }));
    renderPage({ invoiceService });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));
    const expense = await screen.findByRole("checkbox", { name: "Include Travel" });
    expect(expense).toBeChecked();

    await user.click(expense);
    await user.click(screen.getByRole("button", { name: "Refresh draft" }));
    expect(invoiceService.prepare).toHaveBeenLastCalledWith(
      expect.objectContaining({ includedExpenseIds: [] }),
    );
    expect(screen.getByRole("checkbox", { name: "Include Travel" })).not.toBeChecked();

    await user.click(screen.getByRole("checkbox", { name: "Include Travel" }));
    await user.click(screen.getByRole("button", { name: "Refresh draft" }));
    expect(invoiceService.prepare).toHaveBeenLastCalledWith(
      expect.objectContaining({ includedExpenseIds: ["expense-1"] }),
    );
    expect(source.expenses).toHaveLength(1);
  });

  test("preserves configuration and retries a failed prepare", async () => {
    const user = userEvent.setup();
    const prepare = vi
      .fn<InvoiceService["prepare"]>()
      .mockRejectedValueOnce(new Error("Local invoice data is unavailable"))
      .mockResolvedValueOnce(invoiceServiceContractDocument());
    renderPage({
      invoiceService: { prepare, print: vi.fn() },
    });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Local invoice data is unavailable",
    );
    expect(screen.getByRole("textbox", { name: "Sender name" })).toHaveValue(
      "Northstar Studio",
    );
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(prepare).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("1 Feb 2026 – 7 Feb 2026")).toBeInTheDocument();
  });

  test("does not restore a pending draft after the Client changes", async () => {
    const user = userEvent.setup();
    const pending = deferred<InvoiceDocument>();
    renderPage({
      catalog: new InMemoryClientCatalog({
        clients: [client(), client({ id: "client-2", name: "Beacon Works" })],
      }),
      invoiceService: service(() => pending.promise),
    });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));
    await screen.findByText("Preparing invoice…");

    await user.selectOptions(
      screen.getByRole("combobox", { name: "Client" }),
      "client-2",
    );
    pending.resolve(invoiceServiceContractDocument());

    expect(
      await screen.findByRole("heading", { name: "Prepare a billing draft" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prepare invoice" })).toBeEnabled();
    expect(screen.queryByRole("heading", { name: "Atlas Labs" })).not.toBeInTheDocument();
  });

  test("replaces eligibility for a changed period and preserves retained selections", async () => {
    const user = userEvent.setup();
    const source = invoiceServiceContractDocument();
    const domPrint = vi.spyOn(window, "print").mockImplementation(() => undefined);
    const travel = structuredClone(source.expenses[0]);
    const meals = {
      ...structuredClone(travel),
      id: "expense-2",
      date: "2026-02-04",
      description: "Meals",
    };
    const lodging = {
      ...structuredClone(travel),
      id: "expense-3",
      date: "2026-02-08",
      description: "Lodging",
      billingAmountMinor: 4_000,
    };
    const invoiceService = service((request) => {
      const periodExpenses =
        request.periodStart === "2026-02-03" ? [meals, lodging] : [travel, meals];
      const included =
        request.includedExpenseIds === null
          ? periodExpenses
          : periodExpenses.filter((expense) =>
              request.includedExpenseIds?.includes(expense.id),
            );
      const expenseSubtotalMinor = included.reduce(
        (subtotal, expense) => subtotal + expense.billingAmountMinor,
        0,
      );
      return {
        ...structuredClone(source),
        periodStart: request.periodStart,
        periodEnd: request.periodEnd,
        expenses: structuredClone(included),
        expenseSubtotalMinor,
        totalDueMinor: source.workSubtotalMinor + expenseSubtotalMinor,
      };
    });
    renderPage({ invoiceService });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));
    await user.click(await screen.findByRole("checkbox", { name: "Include Meals" }));
    await user.click(screen.getByRole("button", { name: "Refresh draft" }));
    expect(screen.getByRole("checkbox", { name: "Include Meals" })).not.toBeChecked();

    await user.clear(screen.getByLabelText("Period start"));
    await user.type(screen.getByLabelText("Period start"), "2026-02-03");
    await user.clear(screen.getByLabelText("Period end"));
    await user.type(screen.getByLabelText("Period end"), "2026-02-10");
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));

    expect(
      await screen.findByRole("checkbox", { name: "Include Lodging" }),
    ).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Include Meals" })).not.toBeChecked();
    expect(screen.queryByRole("checkbox", { name: "Include Travel" })).not.toBeInTheDocument();
    expect(invoiceService.prepare).toHaveBeenLastCalledWith(
      expect.objectContaining({ includedExpenseIds: ["expense-3"] }),
    );

    const preview = screen.getByRole("article", { name: "Invoice preview" });
    expect(within(preview).queryByText("Meals")).not.toBeInTheDocument();
    expect(within(preview).getByText("Lodging")).toBeInTheDocument();
    expect(within(preview).getAllByText("€40.00")).toHaveLength(2);
    expect(within(preview).getByText("€100.00")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Export PDF" }));
    await waitFor(() => expect(invoiceService.print).toHaveBeenCalledOnce());
    expect(domPrint).not.toHaveBeenCalled();
    expect(invoiceService.prepare).toHaveBeenLastCalledWith(
      expect.objectContaining({ includedExpenseIds: ["expense-3"] }),
    );
  });

  test("maps native field, work-line, and empty-invoice validation issues", async () => {
    const user = userEvent.setup();
    const invalid: InvoiceDocument = {
      ...invoiceServiceContractDocument(),
      exportable: false,
      validationIssues: [
        { code: "invalid-date", field: "issueDate", lineKey: null },
        { code: "missing-rate", field: null, lineKey: "project-1:task-1" },
        { code: "empty-invoice", field: null, lineKey: null },
      ],
      projects: [
        {
          ...invoiceServiceContractDocument().projects[0],
          workLines: [
            {
              ...invoiceServiceContractDocument().projects[0].workLines[0],
              rateMinor: null,
              amountMinor: null,
            },
          ],
        },
      ],
    };
    renderPage({ invoiceService: service(() => invalid) });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));

    expect(await screen.findByText("Enter a valid issue date")).toBeInTheDocument();
    expect(screen.getByText("Enter a non-negative hourly rate")).toBeInTheDocument();
    expect(screen.getByText("There is nothing to invoice for this period")).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Hourly rate for Product design" }),
    ).toHaveAttribute("aria-invalid", "true");
  });

  test("refreshes the authoritative preview before printing its single document tree", async () => {
    const user = userEvent.setup();
    let preparation = 0;
    const domPrint = vi.spyOn(window, "print").mockImplementation(() => undefined);
    const invoiceService = service(
      () => {
        preparation += 1;
        const prepared = invoiceServiceContractDocument();
        if (preparation === 2) {
          prepared.expenses[0].billingAmountMinor = 3_000;
          prepared.expenseSubtotalMinor = 3_000;
          prepared.totalDueMinor = 9_000;
        }
        return prepared;
      },
      () => {
        expect(document.documentElement).toHaveAttribute("data-invoice-printing");
        expect(screen.getAllByRole("article", { name: "Invoice preview" })).toHaveLength(1);
        expect(
          within(screen.getByRole("article", { name: "Invoice preview" })).getByText(
            "€90.00",
          ),
        ).toBeInTheDocument();
      },
    );
    renderPage({ invoiceService });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));

    const exportButton = await screen.findByRole("button", { name: "Export PDF" });
    expect(exportButton).toBeEnabled();
    await user.click(exportButton);

    await waitFor(() => expect(invoiceService.print).toHaveBeenCalledOnce());
    expect(domPrint).not.toHaveBeenCalled();
    expect(invoiceService.prepare).toHaveBeenCalledTimes(2);
    expect(invoiceService.prepare).toHaveBeenLastCalledWith(
      expect.objectContaining({
        clientId: "client-1",
        senderName: "Northstar Studio",
        periodStart: "2026-02-01",
        periodEnd: "2026-02-07",
      }),
    );
    const preview = screen.getByRole("article", { name: "Invoice preview" });
    expect(document.documentElement).toHaveAttribute("data-invoice-printing");
    expectExactPrintPath(preview);

    window.dispatchEvent(new Event("afterprint"));
    expectPrintModeCleared();
    expectAfterPrintListenerRemoved();

    await user.type(
      screen.getByRole("textbox", { name: "Invoice no. (optional)" }),
      "INV-2026-001",
    );
    expect(exportButton).toBeDisabled();
  });

  test("keeps the draft without completion feedback when the print flow returns", async () => {
    const user = userEvent.setup();
    const domPrint = vi.spyOn(window, "print").mockImplementation(() => undefined);
    const invoiceService = service(() => invoiceServiceContractDocument());
    renderPage({ invoiceService });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));
    await user.click(await screen.findByRole("button", { name: "Export PDF" }));

    await waitFor(() => expect(invoiceService.print).toHaveBeenCalledOnce());
    expect(domPrint).not.toHaveBeenCalled();
    expect(document.documentElement).toHaveAttribute("data-invoice-printing");
    expectExactPrintPath(
      screen.getByRole("article", { name: "Invoice preview" }),
    );

    window.dispatchEvent(new Event("afterprint"));
    expectPrintModeCleared();
    expect(screen.getByRole("article", { name: "Invoice preview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export PDF" })).toBeEnabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  test("preserves the configured draft and retries a print-flow failure", async () => {
    const user = userEvent.setup();
    const print = vi
      .fn<() => Promise<void>>()
      .mockRejectedValueOnce(new Error("print unavailable"))
      .mockResolvedValueOnce(undefined);
    const domPrint = vi.spyOn(window, "print").mockImplementation(() => undefined);
    const invoiceService = service(() => invoiceServiceContractDocument(), print);
    renderPage({ invoiceService });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));
    await user.click(await screen.findByRole("button", { name: "Export PDF" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The invoice print flow could not be started. Try again.",
    );
    expect(screen.getByRole("textbox", { name: "Sender name" })).toHaveValue(
      "Northstar Studio",
    );
    expect(screen.getByRole("article", { name: "Invoice preview" })).toBeInTheDocument();
    expectPrintModeCleared();

    expectAfterPrintListenerRemoved();

    await user.click(screen.getByRole("button", { name: "Retry export" }));

    await waitFor(() => expect(invoiceService.print).toHaveBeenCalledTimes(2));
    expect(print).toHaveBeenCalledTimes(2);
    expect(domPrint).not.toHaveBeenCalled();
    expect(invoiceService.prepare).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("data-invoice-printing");
    expectExactPrintPath(
      screen.getByRole("article", { name: "Invoice preview" }),
    );
    window.dispatchEvent(new Event("afterprint"));
    expectPrintModeCleared();
  });

  test("removes print markers and the afterprint listener on unmount", async () => {
    const user = userEvent.setup();
    const invoiceService = service(() => invoiceServiceContractDocument());
    renderPage({ invoiceService });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));
    await user.click(await screen.findByRole("button", { name: "Export PDF" }));

    await waitFor(() => expect(invoiceService.print).toHaveBeenCalledOnce());
    expect(document.documentElement).toHaveAttribute("data-invoice-printing");
    expectExactPrintPath(
      screen.getByRole("article", { name: "Invoice preview" }),
    );

    cleanup();
    expectPrintModeCleared();

    expectAfterPrintListenerRemoved();
  });

  test("ignores a late authoritative refresh after the configuration changes", async () => {
    const user = userEvent.setup();
    const pending = deferred<InvoiceDocument>();
    let preparation = 0;
    const invoiceService = service(() => {
      preparation += 1;
      return preparation === 1
        ? invoiceServiceContractDocument()
        : pending.promise;
    });
    const domPrint = vi.spyOn(window, "print").mockImplementation(() => undefined);
    renderPage({ invoiceService });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));
    await user.click(await screen.findByRole("button", { name: "Export PDF" }));
    expect(
      screen.getByRole("button", { name: "Opening print dialog…" }),
    ).toBeDisabled();

    await user.type(
      screen.getByRole("textbox", { name: "Invoice no. (optional)" }),
      "INV-CHANGED",
    );
    pending.resolve(invoiceServiceContractDocument());

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Export PDF" })).toBeDisabled(),
    );
    expect(invoiceService.print).not.toHaveBeenCalled();
    expect(domPrint).not.toHaveBeenCalled();
    expect(document.documentElement).not.toHaveAttribute("data-invoice-printing");
  });

  test("blocks export for a draft with validation issues", async () => {
    const user = userEvent.setup();
    const invalid = invoiceServiceContractDocument();
    invalid.exportable = false;
    invalid.validationIssues = [
      { code: "empty-invoice", field: null, lineKey: null },
    ];
    const invoiceService = service(() => invalid);
    const domPrint = vi.spyOn(window, "print").mockImplementation(() => undefined);
    renderPage({ invoiceService });
    await completeConfiguration(user);
    await user.click(screen.getByRole("button", { name: "Prepare invoice" }));

    expect(await screen.findByRole("button", { name: "Export PDF" })).toBeDisabled();
    expect(invoiceService.prepare).toHaveBeenCalledOnce();
    expect(invoiceService.print).not.toHaveBeenCalled();
    expect(domPrint).not.toHaveBeenCalled();
  });
});
