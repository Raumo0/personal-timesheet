import { describe, expect, test } from "vitest";

import type { Client } from "../clients/client";
import type { Project } from "../projects/project";
import type { Expense, ExpenseCommand } from "./expense";
import {
  ExpenseStoreError,
  type ExpenseStore,
  type ExpenseStoreSeed,
} from "./expense-store";

export type ExpenseStoreFactory = (seed: ExpenseStoreSeed) => ExpenseStore;

const timestamp = "2026-08-06T10:00:00.000Z";
const laterTimestamp = "2026-08-06T11:00:00.000Z";

const clients: Client[] = [
  {
    id: "client-b",
    name: "Beta",
    currencyCode: "USD",
    hourlyRateMinor: null,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt: null,
  },
  {
    id: "client-a",
    name: "Acme",
    currencyCode: "EUR",
    hourlyRateMinor: null,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt: null,
  },
  {
    id: "client-old",
    name: "Old client",
    currencyCode: "EUR",
    hourlyRateMinor: null,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt: timestamp,
  },
];

const projects: Project[] = [
  {
    id: "project-z",
    clientId: "client-a",
    name: "Zulu",
    hourlyRateOverrideMinor: null,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt: null,
  },
  {
    id: "project-a",
    clientId: "client-a",
    name: "Alpha",
    hourlyRateOverrideMinor: null,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt: null,
  },
  {
    id: "project-old",
    clientId: "client-a",
    name: "Old project",
    hourlyRateOverrideMinor: null,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt: timestamp,
  },
];

function expense(overrides: Partial<Expense> = {}): Expense {
  return {
    id: "expense-1",
    target: { kind: "project", projectId: "project-a" },
    expenseDate: "2026-08-05",
    description: "Travel",
    originalCurrencyCode: "HUF",
    originalAmountMinor: 10_000,
    billingCurrencyCode: "EUR",
    billingAmountMinor: 2_500,
    appliedRate: "0.25",
    rateSource: "manual",
    rateObservedOn: null,
    rateManuallyAdjusted: false,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt: null,
    ...overrides,
  };
}

const command: ExpenseCommand = {
  target: { kind: "project", projectId: "project-a" },
  expenseDate: "2026-08-06",
  description: "Train",
  originalCurrencyCode: "HUF",
  originalAmountMinor: 12_000,
  billingCurrencyCode: "EUR",
  billingAmountMinor: 3_000,
  appliedRate: "0.25",
  rateSource: "manual",
  rateObservedOn: null,
  rateManuallyAdjusted: false,
};

const baseSeed: ExpenseStoreSeed = { clients, projects, expenses: [] };

export function expenseStoreContract(
  name: string,
  createStore: ExpenseStoreFactory,
): void {
  describe(name, () => {
    test("loads bounded ordered views and a sorted active target tree", async () => {
      const expenses = Array.from({ length: 205 }, (_, index) =>
        expense({
          id: `expense-${String(index).padStart(3, "0")}`,
          expenseDate: index === 204 ? "2026-08-06" : "2026-08-05",
          archivedAt: index % 2 === 0 ? null : timestamp,
        }),
      );
      const store = createStore({ ...baseSeed, expenses });

      const active = await store.loadWorkspace("active");
      expect(active.expenses).toHaveLength(103);
      expect(active.expenses[0].id).toBe("expense-204");
      expect(active.targets).toEqual([
        {
          client: { id: "client-a", name: "Acme", currencyCode: "EUR" },
          projects: [
            { id: "project-a", name: "Alpha" },
            { id: "project-z", name: "Zulu" },
          ],
        },
        {
          client: { id: "client-b", name: "Beta", currencyCode: "USD" },
          projects: [],
        },
      ]);
      expect((await store.loadWorkspace("archived")).expenses).toHaveLength(102);
    });

    test("caps each workspace read at 200 expenses", async () => {
      const store = createStore({
        ...baseSeed,
        expenses: Array.from({ length: 205 }, (_, index) =>
          expense({ id: `expense-${index}` }),
        ),
      });
      expect((await store.loadWorkspace("active")).expenses).toHaveLength(200);
    });

    test("retains archived target names without offering them as active targets", async () => {
      const store = createStore({
        ...baseSeed,
        expenses: [
          expense({
            id: "expense-client-old",
            target: { kind: "client", clientId: "client-old" },
            archivedAt: timestamp,
          }),
          expense({
            id: "expense-project-old",
            target: { kind: "project", projectId: "project-old" },
            archivedAt: timestamp,
          }),
        ],
      });

      const workspace = await store.loadWorkspace("archived");
      expect(workspace.targetDisplays).toEqual([
        {
          target: { kind: "client", clientId: "client-old" },
          name: "Old client",
        },
        {
          target: { kind: "project", projectId: "project-old" },
          name: "Old project",
        },
      ]);
      expect(workspace.targets.flatMap(({ client, projects }) => [
        client.id,
        ...projects.map(({ id }) => id),
      ])).not.toContain("client-old");
      expect(workspace.targets.flatMap(({ projects }) =>
        projects.map(({ id }) => id),
      )).not.toContain("project-old");
    });

    test("creates atomically against the current active target and currency", async () => {
      const store = createStore(baseSeed);
      await expect(store.create(command)).resolves.toMatchObject({
        id: "expense-new",
        billingCurrencyCode: "EUR",
        archivedAt: null,
      });
      expect((await store.loadWorkspace("active")).expenses).toHaveLength(1);
    });

    test("isolates seed and loaded workspace aliases from stored state", async () => {
      const seededClients = structuredClone(clients);
      const seededProjects = structuredClone(projects);
      const seededExpenses = [expense()];
      const store = createStore({
        clients: seededClients,
        projects: seededProjects,
        expenses: seededExpenses,
      });

      seededClients[1].name = "Changed outside";
      seededProjects[1].archivedAt = timestamp;
      (seededExpenses[0] as { description: string }).description =
        "Changed outside";
      const first = await store.loadWorkspace("active");
      expect(first.targets[0].client.name).toBe("Acme");
      expect(first.targets[0].projects).toHaveLength(2);
      expect(first.expenses[0].description).toBe("Travel");

      (first.expenses[0] as { description: string }).description = "Changed return";
      (first.targets[0].client as { name: string }).name = "Changed return";
      const second = await store.loadWorkspace("active");
      expect(second.expenses[0].description).toBe("Travel");
      expect(second.targets[0].client.name).toBe("Acme");
    });

    test("isolates returned create and update values from stored state", async () => {
      const store = createStore(baseSeed);
      const created = await store.create(command);
      (created as { description: string }).description = "Changed return";
      expect((await store.loadWorkspace("active")).expenses[0].description).toBe(
        "Train",
      );

      const updated = await store.update(
        "expense-new",
        created.updatedAt,
        { ...command, description: "Taxi" },
      );
      (updated as { billingAmountMinor: number }).billingAmountMinor = 1;
      expect((await store.loadWorkspace("active")).expenses[0]).toMatchObject({
        description: "Taxi",
        billingAmountMinor: 3_000,
      });
    });

    test("rejects malformed commands atomically with a typed failure", async () => {
      const store = createStore(baseSeed);
      await expect(
        store.create({ ...command, originalAmountMinor: 0 }),
      ).rejects.toMatchObject({
        name: "ExpenseStoreError",
        code: "invalid-expense",
      });
      expect((await store.loadWorkspace("active")).expenses).toEqual([]);
    });

    test("rejects inactive targets and stale billing currencies without writes", async () => {
      const store = createStore(baseSeed);
      await expect(
        store.create({
          ...command,
          target: { kind: "project", projectId: "project-old" },
        }),
      ).rejects.toMatchObject({ code: "inactive-target" });
      await expect(
        store.create({ ...command, billingCurrencyCode: "USD" }),
      ).rejects.toMatchObject({ code: "currency-changed" });
      expect((await store.loadWorkspace("active")).expenses).toEqual([]);
    });

    test("updates atomically after rechecking the expected version", async () => {
      const store = createStore({ ...baseSeed, expenses: [expense()] });
      await expect(
        store.update("expense-1", timestamp, { ...command, description: "Taxi" }),
      ).resolves.toMatchObject({ description: "Taxi", updatedAt: laterTimestamp });
      await expect(
        store.update("expense-1", timestamp, command),
      ).rejects.toMatchObject({ code: "stale-expense" });
      expect((await store.loadWorkspace("active")).expenses[0].description).toBe(
        "Taxi",
      );
    });

    test("distinguishes missing and archived update failures", async () => {
      const store = createStore({
        ...baseSeed,
        expenses: [expense({ archivedAt: timestamp })],
      });
      await expect(
        store.update("missing", timestamp, command),
      ).rejects.toMatchObject({ code: "expense-not-found" });
      await expect(
        store.update("expense-1", timestamp, command),
      ).rejects.toMatchObject({ code: "archived-expense" });
      expect((await store.loadWorkspace("archived")).expenses).toEqual([
        expense({ archivedAt: timestamp }),
      ]);
    });

    test("retains a saved billing snapshot for ordinary edits", async () => {
      const changedClients = clients.map((client) =>
        client.id === "client-a" ? { ...client, currencyCode: "USD" } : client,
      );
      const store = createStore({
        clients: changedClients,
        projects,
        expenses: [expense()],
      });
      await expect(
        store.update("expense-1", timestamp, {
          ...command,
          expenseDate: "2026-08-05",
          description: "Updated travel",
          originalAmountMinor: 10_000,
          billingAmountMinor: 2_500,
        }),
      ).resolves.toMatchObject({ billingCurrencyCode: "EUR" });
    });

    test("rechecks current currency when target or original currency changes", async () => {
      const store = createStore({ ...baseSeed, expenses: [expense()] });
      await expect(
        store.update("expense-1", timestamp, {
          ...command,
          target: { kind: "client", clientId: "client-b" },
          billingCurrencyCode: "EUR",
        }),
      ).rejects.toMatchObject({ code: "currency-changed" });
      await expect(
        store.update("expense-1", timestamp, {
          ...command,
          originalCurrencyCode: "USD",
          billingCurrencyCode: "USD",
          billingAmountMinor: 12_000,
          appliedRate: "1",
        }),
      ).rejects.toMatchObject({ code: "currency-changed" });
      expect((await store.loadWorkspace("active")).expenses[0]).toEqual(expense());
    });

    test("returns typed recoverable persistence failures", async () => {
      const failure = new ExpenseStoreError("persistence", new Error("disk full"));
      const store = createStore({ ...baseSeed, failure });
      await expect(store.loadWorkspace("active")).rejects.toMatchObject({
        name: "ExpenseStoreError",
        code: "persistence",
      });
      await expect(store.create(command)).rejects.toBe(failure);
    });
  });
}

export const expenseStoreContractDefaults = {
  createId: () => "expense-new",
  now: () => new Date(laterTimestamp),
};
