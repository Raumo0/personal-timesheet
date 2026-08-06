import { expect, test, vi } from "vitest";

import type { SqlReadDatabase } from "@/infrastructure/sqlite/plugin-sql-adapter";

import type { Expense, ExpenseCommand } from "./expense";
import { expenseStoreContract, expenseStoreContractDefaults } from "./expense-store.contract";
import type { ExpenseStoreError, ExpenseStoreSeed } from "./expense-store";
import { InMemoryExpenseStore } from "./in-memory-expense-store";
import { SqliteExpenseStore } from "./sqlite-expense-store";

function expenseRow(expense: Expense, seed?: ExpenseStoreSeed) {
  const projectId = expense.target.kind === "project" ? expense.target.projectId : undefined;
  const project = projectId
    ? seed?.projects.find(({ id }) => id === projectId)
    : undefined;
  const clientId = expense.target.kind === "client"
    ? expense.target.clientId
    : project?.clientId;
  const client = seed?.clients.find(({ id }) => id === clientId);
  return {
    id: expense.id,
    client_id: expense.target.kind === "client" ? expense.target.clientId : null,
    project_id: expense.target.kind === "project" ? expense.target.projectId : null,
    expense_date: expense.expenseDate,
    description: expense.description,
    original_currency_code: expense.originalCurrencyCode,
    original_amount_minor: expense.originalAmountMinor,
    billing_currency_code: expense.billingCurrencyCode,
    billing_amount_minor: expense.billingAmountMinor,
    applied_rate: expense.appliedRate,
    rate_source: expense.rateSource,
    rate_observed_on: expense.rateObservedOn,
    rate_manually_adjusted: expense.rateManuallyAdjusted ? 1 : 0,
    created_at: expense.createdAt,
    updated_at: expense.updatedAt,
    archived_at: expense.archivedAt,
    client_name: client?.name,
    project_name: project?.name ?? null,
  };
}

function harness(seed: ExpenseStoreSeed) {
  const memory = new InMemoryExpenseStore({ ...seed, ...expenseStoreContractDefaults });
  const plans: unknown[] = [];
  const select = vi.fn(async (sql: string, values: unknown[] = []) => {
    if (sql.includes("/* expenses:workspace */")) {
      const snapshot = await memory.loadWorkspace(String(values[0]) as "active" | "archived");
      return snapshot.expenses.map((expense) => expenseRow(expense, seed));
    }
    if (sql.includes("/* expenses:targets */")) {
      return (await memory.loadWorkspace("active")).targets.flatMap((group) => [
        {
          client_id: group.client.id,
          client_name: group.client.name,
          currency_code: group.client.currencyCode,
          project_id: null,
          project_name: null,
        },
        ...group.projects.map((project) => ({
          client_id: group.client.id,
          client_name: group.client.name,
          currency_code: group.client.currencyCode,
          project_id: project.id,
          project_name: project.name,
        })),
      ]);
    }
    if (sql.includes("/* expenses:target */")) {
      const [kind, id] = values.map(String);
      const client = kind === "client"
        ? seed.clients.find((candidate) => candidate.id === id)
        : seed.clients.find((candidate) =>
            seed.projects.some((project) => project.id === id && project.clientId === candidate.id),
          );
      const project = kind === "project"
        ? seed.projects.find((candidate) => candidate.id === id)
        : undefined;
      return client
        ? [{
            client_id: client.id,
            client_currency_code: client.currencyCode,
            client_updated_at: client.updatedAt,
            client_archived_at: client.archivedAt,
            project_id: project?.id ?? null,
            project_updated_at: project?.updatedAt ?? null,
            project_archived_at: project?.archivedAt ?? null,
          }]
        : [];
    }
    if (sql.includes("/* expenses:expected */")) {
      const all = [
        ...(await memory.loadWorkspace("active")).expenses,
        ...(await memory.loadWorkspace("archived")).expenses,
      ];
      const found = all.find((expense) => expense.id === String(values[0]));
      return found ? [expenseRow(found, seed)] : [];
    }
    throw new Error(`Unexpected query: ${sql}`);
  });
  const invoke = vi.fn(async (command: string, args?: Record<string, unknown>) => {
    expect(command).toBe("apply_expense_mutation");
    const plan = args?.plan as {
      operation: "create" | "update";
      expenseId: string;
      expectedExpenseUpdatedAt: string | null;
      command: ExpenseCommand;
    };
    plans.push(plan);
    try {
      return plan.operation === "create"
        ? await memory.create(plan.command)
        : await memory.update(
            plan.expenseId,
            plan.expectedExpenseUpdatedAt!,
            plan.command,
          );
    } catch (cause) {
      const error = cause as ExpenseStoreError;
      if (error.code === "persistence") throw error;
      throw new Error(`${error.code}: ${error.message}`);
    }
  });
  return {
    store: new SqliteExpenseStore({
      getDatabase: async () => ({ select } satisfies SqlReadDatabase),
      invoke,
      ...expenseStoreContractDefaults,
    }),
    select,
    invoke,
    plans,
  };
}

expenseStoreContract("SqliteExpenseStore contract", (seed) => harness(seed).store);

test("uses bounded reads and sends immutable expected-state plans", async () => {
  const seed: ExpenseStoreSeed = {
    clients: [{
      id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: null,
      createdAt: "2026-08-01T10:00:00.000Z", updatedAt: "client-version", archivedAt: null,
    }],
    projects: [],
    expenses: [],
  };
  const subject = harness(seed);
  const command: ExpenseCommand = {
    target: { kind: "client", clientId: "client-1" }, expenseDate: "2026-08-06",
    description: "Train", originalCurrencyCode: "EUR", originalAmountMinor: 100,
    billingCurrencyCode: "EUR", billingAmountMinor: 100, appliedRate: "1",
    rateSource: "manual", rateObservedOn: null, rateManuallyAdjusted: false,
  };
  await subject.store.loadWorkspace("active");
  await subject.store.create(command);
  expect(subject.select.mock.calls[0][0]).toContain("LIMIT 200");
  expect(Object.isFrozen(subject.plans[0])).toBe(true);
  expect(Object.isFrozen((subject.plans[0] as { command: object }).command)).toBe(true);
  expect(subject.plans[0]).toMatchObject({
    operation: "create", expenseId: "expense-new",
    expectedTarget: { clientUpdatedAt: "client-version", clientCurrencyCode: "EUR" },
  });
});

test("rejects malformed rows and maps native failures to typed errors", async () => {
  const malformed = new SqliteExpenseStore({
    getDatabase: async () => ({ select: vi.fn().mockResolvedValue([{ id: "broken" }]) }),
  });
  await expect(malformed.loadWorkspace("active")).rejects.toMatchObject({ code: "persistence" });

  const seed: ExpenseStoreSeed = { clients: [], projects: [], expenses: [] };
  const subject = harness(seed);
  subject.select.mockResolvedValueOnce([{
    client_id: "client-1", client_currency_code: "EUR", client_updated_at: "v",
    client_archived_at: null, project_id: null, project_updated_at: null,
    project_archived_at: null,
  }]);
  subject.invoke.mockRejectedValueOnce("stale-plan: target changed");
  await expect(subject.store.create({
    target: { kind: "client", clientId: "client-1" }, expenseDate: "2026-08-06",
    description: "Train", originalCurrencyCode: "EUR", originalAmountMinor: 100,
    billingCurrencyCode: "EUR", billingAmountMinor: 100, appliedRate: "1",
    rateSource: "manual", rateObservedOn: null, rateManuallyAdjusted: false,
  })).rejects.toMatchObject({ code: "stale-expense" });
});
