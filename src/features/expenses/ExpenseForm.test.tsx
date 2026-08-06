import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterEach, expect, test, vi } from "vitest";

import type { Expense } from "./expense";
import type { ExpenseTargetGroup } from "./expense-store";
import { ExpenseForm } from "./ExpenseForm";

afterEach(cleanup);

const targets: readonly ExpenseTargetGroup[] = [
  {
    client: { id: "client-1", name: "Acme", currencyCode: "EUR" },
    projects: [{ id: "project-1", name: "Website" }],
  },
  {
    client: { id: "client-2", name: "Globex", currencyCode: "USD" },
    projects: [],
  },
];

function renderForm(overrides: Partial<ComponentProps<typeof ExpenseForm>> = {}) {
  const props: ComponentProps<typeof ExpenseForm> = {
    open: true,
    targets,
    onOpenChange: vi.fn(),
    onSave: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(<ExpenseForm {...props} />);
  return props;
}

async function choose(user: ReturnType<typeof userEvent.setup>, label: string) {
  await chooseFrom(user, "Billing target", label);
}

async function chooseFrom(
  user: ReturnType<typeof userEvent.setup>,
  combobox: string,
  label: string,
) {
  screen.getByRole("combobox", { name: combobox }).focus();
  await user.keyboard("{Enter}");
  await user.click(screen.getByRole("option", { name: label }));
}

test("offers direct Client and grouped Project targets from the active target tree", async () => {
  const user = userEvent.setup();
  renderForm();

  await user.click(screen.getByRole("combobox", { name: "Billing target" }));

  expect(screen.getByRole("group", { name: "Acme" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Client · Acme" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Project · Website" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Globex" })).toBeInTheDocument();
  expect(screen.queryByText("Archived project")).not.toBeInTheDocument();
});

test("identifies and focuses a missing billing target", async () => {
  const user = userEvent.setup();
  renderForm();

  await user.click(screen.getByRole("button", { name: "Save expense" }));

  const target = screen.getByRole("combobox", { name: "Billing target" });
  expect(target).toHaveAccessibleDescription("Choose a Client or Project");
  expect(target).toHaveFocus();
});

test("defaults currency to the selected Client and simplifies same-currency saving", async () => {
  const user = userEvent.setup();
  const { onSave } = renderForm();
  await choose(user, "Client · Acme");

  expect(screen.getByRole("combobox", { name: "Original currency" })).toHaveTextContent("EUR");
  expect(screen.queryByRole("textbox", { name: "Applied rate" })).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("Expense date"), "2026-08-06");
  await user.type(screen.getByLabelText("Description"), "Train");
  await user.type(screen.getByLabelText("Original amount"), "12.50");
  await user.click(screen.getByRole("button", { name: "Save expense" }));

  expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
    target: { kind: "client", clientId: "client-1" },
    originalCurrencyCode: "EUR",
    originalAmountMinor: 1250,
    billingCurrencyCode: "EUR",
    billingAmountMinor: 1250,
    appliedRate: "1",
  }));
});

test("links rate edits to a half-up billing amount preview", async () => {
  const user = userEvent.setup();
  renderForm();
  await choose(user, "Client · Acme");
  await chooseFrom(user, "Original currency", "JPY");
  await user.type(screen.getByLabelText("Original amount"), "1");
  await user.type(screen.getByRole("textbox", { name: "Applied rate" }), "0.005");

  expect(screen.getByText("1 JPY = 0.005 EUR")).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Billing amount" })).toHaveValue("0.01");
});

test("links billing amount edits back to the canonical rate direction", async () => {
  const user = userEvent.setup();
  renderForm();
  await choose(user, "Client · Acme");
  await chooseFrom(user, "Original currency", "USD");
  await user.type(screen.getByLabelText("Original amount"), "10.00");
  await user.type(screen.getByRole("textbox", { name: "Billing amount" }), "9.00");

  expect(screen.getByRole("textbox", { name: "Applied rate" })).toHaveValue("0.9");
  expect(screen.getByText("1 USD = 0.9 EUR")).toBeInTheDocument();
});

test("shows all core validation errors, retains the draft, and focuses the first error", async () => {
  const user = userEvent.setup();
  const { onSave, onOpenChange } = renderForm();
  await choose(user, "Client · Acme");
  await user.type(screen.getByLabelText("Expense date"), "2026-02-30");
  await user.type(screen.getByLabelText("Description"), "   ");
  await user.type(screen.getByLabelText("Original amount"), "0");
  await user.click(screen.getByRole("button", { name: "Save expense" }));

  expect(screen.getByText("Enter a valid local date")).toBeInTheDocument();
  expect(screen.getByText("Enter a description")).toBeInTheDocument();
  expect(screen.getByText("Amount must be positive")).toBeInTheDocument();
  expect(screen.getByLabelText("Expense date")).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByLabelText("Expense date")).toHaveAccessibleDescription(
    "Enter a valid local date",
  );
  expect(screen.getByLabelText("Expense date")).toHaveFocus();
  expect(screen.getByLabelText("Description")).toHaveValue("   ");
  expect(onSave).not.toHaveBeenCalled();
  expect(onOpenChange).not.toHaveBeenCalledWith(false);
});

test("focuses Applied rate when it is the first invalid conversion field", async () => {
  const user = userEvent.setup();
  renderForm();
  await choose(user, "Client · Acme");
  await chooseFrom(user, "Original currency", "USD");
  await user.type(screen.getByLabelText("Expense date"), "2026-08-06");
  await user.type(screen.getByLabelText("Description"), "Train");
  await user.type(screen.getByLabelText("Original amount"), "10.00");
  await user.type(screen.getByRole("textbox", { name: "Billing amount" }), "9.00");
  await user.clear(screen.getByRole("textbox", { name: "Applied rate" }));

  await user.click(screen.getByRole("button", { name: "Save expense" }));

  const rate = screen.getByRole("textbox", { name: "Applied rate" });
  expect(rate).toHaveFocus();
  expect(rate).toHaveAttribute("aria-invalid", "true");
  expect(rate).toHaveAccessibleDescription("Enter a positive rate with up to 12 decimals");
});

test("focuses Billing amount when it is the first invalid conversion field", async () => {
  const user = userEvent.setup();
  renderForm();
  await choose(user, "Client · Acme");
  await chooseFrom(user, "Original currency", "USD");
  await user.type(screen.getByLabelText("Expense date"), "2026-08-06");
  await user.type(screen.getByLabelText("Description"), "Train");
  await user.type(screen.getByLabelText("Original amount"), "10.00");
  await user.type(screen.getByRole("textbox", { name: "Applied rate" }), "0.9");
  await user.clear(screen.getByRole("textbox", { name: "Billing amount" }));

  await user.click(screen.getByRole("button", { name: "Save expense" }));

  const billingAmount = screen.getByRole("textbox", { name: "Billing amount" });
  expect(billingAmount).toHaveFocus();
  expect(billingAmount).toHaveAttribute("aria-invalid", "true");
  expect(billingAmount).toHaveAccessibleDescription(
    "Enter a non-negative amount with up to 2 decimals",
  );
});

test("retains entered values and exposes an accessible error when saving fails", async () => {
  const user = userEvent.setup();
  renderForm({ onSave: vi.fn().mockRejectedValue(new Error("Expense was not saved")) });
  await choose(user, "Client · Acme");
  await user.type(screen.getByLabelText("Expense date"), "2026-08-06");
  await user.type(screen.getByLabelText("Description"), "Train");
  await user.type(screen.getByLabelText("Original amount"), "12.50");
  await user.click(screen.getByRole("button", { name: "Save expense" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Expense was not saved");
  expect(screen.getByLabelText("Description")).toHaveValue("Train");
});

test("restores every saved value when editing without recomputing the billing snapshot", async () => {
  const expense: Expense = {
    id: "expense-1",
    target: { kind: "project", projectId: "project-1" },
    expenseDate: "2026-08-05",
    description: "Hotel",
    originalCurrencyCode: "USD",
    originalAmountMinor: 10_00,
    billingCurrencyCode: "GBP",
    billingAmountMinor: 8_00,
    appliedRate: "0.8",
    rateSource: "manual",
    rateObservedOn: null,
    rateManuallyAdjusted: false,
    createdAt: "2026-08-05T08:00:00.000Z",
    updatedAt: "2026-08-05T08:00:00.000Z",
    archivedAt: null,
  };
  renderForm({ expense });

  expect(screen.getByRole("dialog", { name: "Edit expense" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Billing target" })).toHaveTextContent("Project · Website");
  expect(screen.getByLabelText("Expense date")).toHaveValue("2026-08-05");
  expect(screen.getByLabelText("Description")).toHaveValue("Hotel");
  expect(screen.getByRole("combobox", { name: "Original currency" })).toHaveTextContent("USD");
  expect(screen.getByLabelText("Original amount")).toHaveValue("10.00");
  expect(screen.getByRole("textbox", { name: "Applied rate" })).toHaveValue("0.8");
  expect(screen.getByRole("textbox", { name: "Billing amount" })).toHaveValue("8.00");
  expect(screen.getByLabelText("Description")).toHaveFocus();
  await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
});
