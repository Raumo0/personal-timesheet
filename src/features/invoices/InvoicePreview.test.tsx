import { cleanup, render, screen, within } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, test } from "vitest";

import { invoiceServiceContractDocument } from "./invoice-service.contract";
import { InvoicePreview } from "./InvoicePreview";

afterEach(cleanup);

describe("InvoicePreview", () => {
  test("exposes the existing preview article for print isolation", () => {
    const previewRef = createRef<HTMLElement>();

    render(
      <InvoicePreview
        document={invoiceServiceContractDocument()}
        previewRef={previewRef}
      />,
    );

    expect(previewRef.current).toBe(
      screen.getByRole("article", { name: "Invoice preview" }),
    );
    expect(screen.getAllByRole("article", { name: "Invoice preview" })).toHaveLength(1);
  });

  test("renders invoice identity, lines, subtotals, and one final Total due", () => {
    const document = invoiceServiceContractDocument();
    document.projects[0].workLines[0].label =
      "Product discovery, interface architecture, and stakeholder alignment";
    render(<InvoicePreview document={document} />);

    const preview = screen.getByRole("article", { name: "Invoice preview" });
    expect(within(preview).getByRole("heading", { name: "Invoice" })).toBeInTheDocument();
    expect(within(preview).getByText("Northstar Studio")).toBeInTheDocument();
    expect(within(preview).getByText("Atlas Labs")).toBeInTheDocument();
    expect(within(preview).getByText("8 Feb 2026")).toBeInTheDocument();
    expect(within(preview).getByText("1 Feb 2026 – 7 Feb 2026")).toBeInTheDocument();
    expect(within(preview).getByText("INV-2026-002")).toBeInTheDocument();
    expect(within(preview).getAllByText("Atlas launch")).toHaveLength(2);
    expect(
      within(preview).getByText(
        "Product discovery, interface architecture, and stakeholder alignment",
      ),
    ).toBeInTheDocument();
    expect(within(preview).getByText("Travel")).toBeInTheDocument();
    expect(within(preview).getAllByText("Total due")).toHaveLength(1);
    expect(within(preview).getByText("€85.00")).toBeInTheDocument();
    expect(within(preview).queryByText("Personal Timesheet")).not.toBeInTheDocument();
  });

  test("shows enabled optional content with approved summary metrics", () => {
    render(<InvoicePreview document={invoiceServiceContractDocument()} />);

    expect(screen.getByRole("heading", { name: "Payment note" })).toBeInTheDocument();
    expect(screen.getByText("Payment due within 14 days.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Work summary" })).toBeInTheDocument();
    expect(screen.getByText("Total hours")).toBeInTheDocument();
    expect(screen.getByText("Active days")).toBeInTheDocument();
    expect(screen.queryByText(/Tasks|Work categories/)).not.toBeInTheDocument();
    expect(screen.getByRole("figure", { name: "Daily activity" })).toBeInTheDocument();
    expect(
      screen.getByRole("figure", { name: "Work category breakdown" }),
    ).toBeInTheDocument();
  });

  test("omits complete optional blocks when disabled", () => {
    const document = invoiceServiceContractDocument();
    document.invoiceNumber = null;
    document.paymentNote = null;
    document.includeDailyActivity = false;
    document.includeWorkCategoryBreakdown = false;
    render(<InvoicePreview document={document} />);

    expect(screen.queryByText(/^Invoice no\.$/)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Payment note" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Work summary" })).not.toBeInTheDocument();
    expect(screen.queryByRole("figure")).not.toBeInTheDocument();
  });

  test("keeps summary metrics when exactly one chart is enabled", () => {
    const document = invoiceServiceContractDocument();
    document.includeDailyActivity = true;
    document.includeWorkCategoryBreakdown = false;
    render(<InvoicePreview document={document} />);

    expect(screen.getByRole("heading", { name: "Work summary" })).toBeInTheDocument();
    expect(screen.getByText("Total hours")).toBeInTheDocument();
    expect(screen.getByText("Active days")).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: "Daily activity" })).toBeInTheDocument();
    expect(
      screen.queryByRole("figure", { name: "Work category breakdown" }),
    ).not.toBeInTheDocument();
  });
});
