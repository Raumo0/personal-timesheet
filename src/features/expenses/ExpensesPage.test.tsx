import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import {
  CatalogLifecycleError,
  type CatalogLifecycle,
  type LifecyclePlan,
} from "../catalog-lifecycle/catalog-lifecycle";
import type { Expense } from "./expense";
import type { ExpenseStore, ExpenseWorkspaceSnapshot } from "./expense-store";
import { ExpensesPage } from "./ExpensesPage";

afterEach(cleanup);

const targets: ExpenseWorkspaceSnapshot["targets"] = [
  {
    client: { id: "client-1", name: "Acme", currencyCode: "EUR" },
    projects: [{ id: "project-1", name: "Website" }],
  },
];
const targetDisplays: ExpenseWorkspaceSnapshot["targetDisplays"] = [];

function expense(
  id: string,
  date: string,
  description: string,
  target: Expense["target"] = { kind: "project", projectId: "project-1" },
  archivedAt: string | null = null,
): Expense {
  return {
    id,
    target,
    expenseDate: date,
    description,
    originalCurrencyCode: "USD",
    originalAmountMinor: 1250,
    billingCurrencyCode: "EUR",
    billingAmountMinor: 1000,
    appliedRate: "0.8",
    rateSource: "manual",
    rateObservedOn: null,
    rateManuallyAdjusted: false,
    createdAt: `2026-08-0${id === "expense-1" ? "1" : "2"}T08:00:00.000Z`,
    updatedAt: "2026-08-03T08:00:00.000Z",
    archivedAt,
  };
}

function store(overrides: Partial<ExpenseStore> = {}): ExpenseStore {
  return {
    loadWorkspace: vi.fn().mockResolvedValue({ expenses: [], targets, targetDisplays }),
    create: vi.fn(),
    update: vi.fn(),
    ...overrides,
  };
}

function lifecycle(overrides: Partial<CatalogLifecycle> = {}): CatalogLifecycle {
  return {
    preview: vi.fn(),
    apply: vi.fn(),
    ...overrides,
  };
}

function lifecyclePlan(
  operation: "archive" | "restore",
  expense: Expense,
  impactDescription: string,
): LifecyclePlan {
  return {
    operation,
    target: { kind: "expense", id: expense.id },
    records: [{
      kind: "expense",
      id: expense.id,
      name: expense.description,
      archivedAt: expense.archivedAt,
    }],
    impactDescription,
  };
}

test("shows loading and then an actionable empty active ledger", async () => {
  let resolve!: (value: ExpenseWorkspaceSnapshot) => void;
  const pending = new Promise<ExpenseWorkspaceSnapshot>((next) => { resolve = next; });
  const expenseStore = store({ loadWorkspace: vi.fn(() => pending) });
  render(<ExpensesPage store={expenseStore} />);

  expect(screen.getByRole("status")).toHaveTextContent("Loading expenses");
  resolve({ expenses: [], targets, targetDisplays });

  expect(await screen.findByText("No expenses yet")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add your first expense" })).toBeEnabled();
});

test("shows a recoverable load error and retries the active view", async () => {
  const loadWorkspace = vi
    .fn()
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ expenses: [], targets, targetDisplays });
  render(<ExpensesPage store={store({ loadWorkspace })} />);

  expect(await screen.findByText("Expenses could not be loaded")).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));

  expect(await screen.findByText("No expenses yet")).toBeInTheDocument();
  expect(loadWorkspace).toHaveBeenNthCalledWith(2, "active");
});

test("switches between active and archived views and keeps archived rows read-only", async () => {
  const active = expense("expense-1", "2026-08-05", "Train");
  const archived = expense(
    "expense-2",
    "2026-08-04",
    "Hotel",
    { kind: "client", clientId: "client-1" },
    "2026-08-06T08:00:00.000Z",
  );
  const loadWorkspace = vi
    .fn()
    .mockResolvedValueOnce({ expenses: [active], targets, targetDisplays })
    .mockResolvedValueOnce({ expenses: [archived], targets, targetDisplays });
  render(<ExpensesPage store={store({ loadWorkspace })} />);

  expect(await screen.findByText("Train")).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button", { name: "Archived" }));

  expect(await screen.findByText("Hotel")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Edit Hotel" })).not.toBeInTheDocument();
  expect(screen.getByText("Read-only")).toBeInTheDocument();
  expect(loadWorkspace).toHaveBeenLastCalledWith("archived");
});

test("renders descending dates, named targets, and both authoritative amounts", async () => {
  const older = expense("expense-1", "2026-08-04", "Train");
  const newer = expense(
    "expense-2",
    "2026-08-06",
    "Hotel",
    { kind: "client", clientId: "client-1" },
  );
  render(
    <ExpensesPage
      store={store({
        loadWorkspace: vi.fn().mockResolvedValue({ expenses: [older, newer], targets, targetDisplays }),
      })}
    />,
  );

  const rows = await screen.findAllByRole("row");
  expect(rows[1]).toHaveTextContent("2026-08-06");
  expect(rows[1]).toHaveTextContent("Client · Acme");
  expect(rows[2]).toHaveTextContent("2026-08-04");
  expect(rows[2]).toHaveTextContent("Project · Website");
  expect(rows[1]).toHaveTextContent(/\$12\.50/);
  expect(rows[1]).toHaveTextContent(/€10\.00/);
});

test("renders retained names for archived direct Client and Project targets", async () => {
  const archivedClient = expense(
    "expense-1",
    "2026-08-05",
    "Client cost",
    { kind: "client", clientId: "client-old" },
    "2026-08-06T08:00:00.000Z",
  );
  const archivedProject = expense(
    "expense-2",
    "2026-08-04",
    "Project cost",
    { kind: "project", projectId: "project-old" },
    "2026-08-06T08:00:00.000Z",
  );
  render(
    <ExpensesPage
      store={store({
        loadWorkspace: vi.fn().mockResolvedValue({
          expenses: [archivedClient, archivedProject],
          targets,
          targetDisplays: [
            { target: archivedClient.target, name: "Former client" },
            { target: archivedProject.target, name: "Retired project" },
          ],
        }),
      })}
    />,
  );

  expect(await screen.findByText("Client · Former client")).toBeInTheDocument();
  expect(screen.getByText("Project · Retired project")).toBeInTheDocument();
  expect(screen.queryByText(/client-old|project-old/)).not.toBeInTheDocument();
});

test("creates through the real form and refreshes the ledger", async () => {
  const user = userEvent.setup();
  const created = expense(
    "expense-1",
    "2026-08-06",
    "Train",
    { kind: "client", clientId: "client-1" },
  );
  const loadWorkspace = vi
    .fn()
    .mockResolvedValueOnce({ expenses: [], targets, targetDisplays })
    .mockResolvedValueOnce({ expenses: [created], targets, targetDisplays });
  const create = vi.fn().mockResolvedValue(created);
  render(<ExpensesPage store={store({ loadWorkspace, create })} />);
  await screen.findByText("No expenses yet");

  await user.click(screen.getByRole("button", { name: "Add expense" }));
  const target = screen.getByRole("combobox", { name: "Billing target" });
  target.focus();
  await user.keyboard("{Enter}");
  await user.click(screen.getByRole("option", { name: "Client · Acme" }));
  await user.type(screen.getByLabelText("Expense date"), "2026-08-06");
  await user.type(screen.getByLabelText("Description"), "Train");
  await user.type(screen.getByLabelText("Original amount"), "12.50");
  await user.click(screen.getByRole("button", { name: "Save expense" }));

  expect(create).toHaveBeenCalled();
  expect(await screen.findByText("Train")).toBeInTheDocument();
  expect(loadWorkspace).toHaveBeenCalledTimes(2);
});

test("edits an active row through the real form and refreshes it", async () => {
  const user = userEvent.setup();
  const current = expense("expense-1", "2026-08-05", "Train");
  const updated = { ...current, description: "Hotel", updatedAt: "2026-08-06T09:00:00.000Z" };
  const loadWorkspace = vi
    .fn()
    .mockResolvedValueOnce({ expenses: [current], targets, targetDisplays })
    .mockResolvedValueOnce({ expenses: [updated], targets, targetDisplays });
  const update = vi.fn().mockResolvedValue(updated);
  render(<ExpensesPage store={store({ loadWorkspace, update })} />);
  await screen.findByText("Train");

  await user.click(screen.getByRole("button", { name: "Edit Train" }));
  await user.clear(screen.getByLabelText("Description"));
  await user.type(screen.getByLabelText("Description"), "Hotel");
  await user.click(screen.getByRole("button", { name: "Save changes" }));

  expect(update).toHaveBeenCalledWith("expense-1", current.updatedAt, expect.objectContaining({ description: "Hotel" }));
  expect(await screen.findByText("Hotel")).toBeInTheDocument();
});

test("keeps the form draft and exposes a persistent accessible CRUD failure", async () => {
  const user = userEvent.setup();
  const create = vi.fn().mockRejectedValue(new Error("Expense data could not be saved"));
  render(<ExpensesPage store={store({ create })} />);
  await screen.findByText("No expenses yet");
  await user.click(screen.getByRole("button", { name: "Add expense" }));
  const target = screen.getByRole("combobox", { name: "Billing target" });
  target.focus();
  await user.keyboard("{Enter}");
  await user.click(screen.getByRole("option", { name: "Client · Acme" }));
  await user.type(screen.getByLabelText("Expense date"), "2026-08-06");
  await user.type(screen.getByLabelText("Description"), "Train");
  await user.type(screen.getByLabelText("Original amount"), "12.50");
  await user.click(screen.getByRole("button", { name: "Save expense" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Expense data could not be saved");
  expect(screen.getByLabelText("Description")).toHaveValue("Train");
  expect(screen.getByRole("dialog", { name: "Add expense" })).toBeInTheDocument();
});

test("previews the exact archive impact and cancel restores action focus", async () => {
  const user = userEvent.setup();
  const current = expense("expense-1", "2026-08-05", "Train");
  const plan = lifecyclePlan("archive", current, "Archive Train.");
  const preview = vi.fn().mockResolvedValue(plan);
  const apply = vi.fn();
  render(
    <ExpensesPage
      lifecycle={lifecycle({ preview, apply })}
      store={store({
        loadWorkspace: vi.fn().mockResolvedValue({ expenses: [current], targets, targetDisplays }),
      })}
    />,
  );
  const archive = await screen.findByRole("button", { name: "Archive Train" });

  await user.click(archive);

  expect(await screen.findByRole("alertdialog")).toHaveTextContent("Archive Train.");
  expect(preview).toHaveBeenCalledWith({
    operation: "archive",
    target: { kind: "expense", id: "expense-1" },
  });
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(apply).not.toHaveBeenCalled();
  expect(archive).toHaveFocus();
});

test("applies archive, refreshes workspace targets, and leaves sibling rows unchanged", async () => {
  const user = userEvent.setup();
  const current = expense("expense-1", "2026-08-05", "Train");
  const sibling = expense("expense-2", "2026-08-04", "Hotel");
  const plan = lifecyclePlan("archive", current, "Archive Train.");
  const nextTargets = [{
    client: { id: "client-2", name: "Globex", currencyCode: "USD" },
    projects: [],
  }];
  const loadWorkspace = vi.fn()
    .mockResolvedValueOnce({ expenses: [current, sibling], targets, targetDisplays })
    .mockResolvedValueOnce({ expenses: [sibling], targets: nextTargets, targetDisplays });
  const apply = vi.fn().mockResolvedValue(undefined);
  render(
    <ExpensesPage
      lifecycle={lifecycle({ preview: vi.fn().mockResolvedValue(plan), apply })}
      store={store({ loadWorkspace })}
    />,
  );

  await user.click(await screen.findByRole("button", { name: "Archive Train" }));
  await user.click(await screen.findByRole("button", { name: "Archive expense" }));

  expect(await screen.findByText("Hotel")).toBeInTheDocument();
  expect(screen.queryByText("Train")).not.toBeInTheDocument();
  expect(apply).toHaveBeenCalledWith(plan);
  expect(loadWorkspace).toHaveBeenCalledTimes(2);
  await user.click(screen.getByRole("button", { name: "Add expense" }));
  const target = screen.getByRole("combobox", { name: "Billing target" });
  target.focus();
  await user.keyboard("{Enter}");
  expect(screen.getByRole("option", { name: "Client · Globex" })).toBeInTheDocument();
});

test("previews and applies a targeted restore without changing archived siblings", async () => {
  const user = userEvent.setup();
  const archived = expense("expense-1", "2026-08-05", "Train", undefined, "2026-08-06T08:00:00.000Z");
  const sibling = expense("expense-2", "2026-08-04", "Hotel", undefined, "2026-08-06T08:00:00.000Z");
  const plan = lifecyclePlan(
    "restore",
    archived,
    "Restore Acme, Website, and Train.",
  );
  const loadWorkspace = vi.fn()
    .mockResolvedValueOnce({ expenses: [], targets, targetDisplays })
    .mockResolvedValueOnce({ expenses: [archived, sibling], targets, targetDisplays })
    .mockResolvedValueOnce({ expenses: [sibling], targets, targetDisplays });
  const apply = vi.fn().mockResolvedValue(undefined);
  render(
    <ExpensesPage
      lifecycle={lifecycle({ preview: vi.fn().mockResolvedValue(plan), apply })}
      store={store({ loadWorkspace })}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Archived" }));

  await user.click(await screen.findByRole("button", { name: "Restore Train" }));
  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    "Restore Acme, Website, and Train.",
  );
  await user.click(screen.getByRole("button", { name: "Restore expense" }));

  expect(await screen.findByText("Hotel")).toBeInTheDocument();
  expect(screen.queryByText("Train")).not.toBeInTheDocument();
  expect(apply).toHaveBeenCalledWith(plan);
});

test("keeps a stale-plan failure visible, restores focus, and Retry previews afresh", async () => {
  const user = userEvent.setup();
  const current = expense("expense-1", "2026-08-05", "Train");
  const stale = lifecyclePlan("archive", current, "Archive Train.");
  const fresh = lifecyclePlan("archive", current, "Archive updated Train.");
  const preview = vi.fn()
    .mockResolvedValueOnce(stale)
    .mockResolvedValueOnce(fresh);
  const apply = vi.fn().mockRejectedValue(
    new CatalogLifecycleError("stale-plan", "The lifecycle preview is stale"),
  );
  render(
    <ExpensesPage
      lifecycle={lifecycle({ preview, apply })}
      store={store({
        loadWorkspace: vi.fn().mockResolvedValue({ expenses: [current], targets, targetDisplays }),
      })}
    />,
  );
  const archive = await screen.findByRole("button", { name: "Archive Train" });
  await user.click(archive);
  await user.click(await screen.findByRole("button", { name: "Archive expense" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("preview is stale");
  expect(archive).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("alertdialog")).toHaveTextContent("Archive updated Train.");
  expect(preview).toHaveBeenCalledTimes(2);
});

test("recovers from a lifecycle preview failure through Retry", async () => {
  const user = userEvent.setup();
  const current = expense("expense-1", "2026-08-05", "Train");
  const preview = vi.fn()
    .mockRejectedValueOnce(new CatalogLifecycleError("persistence", "The preview could not be loaded"))
    .mockResolvedValueOnce(lifecyclePlan("archive", current, "Archive Train."));
  render(
    <ExpensesPage
      lifecycle={lifecycle({ preview })}
      store={store({
        loadWorkspace: vi.fn().mockResolvedValue({ expenses: [current], targets, targetDisplays }),
      })}
    />,
  );

  await user.click(await screen.findByRole("button", { name: "Archive Train" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("alertdialog")).toHaveTextContent("Archive Train.");
});
