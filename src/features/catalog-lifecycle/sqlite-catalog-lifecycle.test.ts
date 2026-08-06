import { describe, expect, test, vi } from "vitest";
import { execFileSync } from "node:child_process";

import type { SqlReadDatabase } from "@/infrastructure/sqlite/plugin-sql-adapter";
import {
  CatalogLifecycleError,
  planCatalogLifecycle,
  type CatalogHierarchy,
  type LifecyclePlan,
} from "./catalog-lifecycle";
import {
  catalogLifecycleContract,
  type CatalogLifecycleHarnessOptions,
} from "./catalog-lifecycle.contract";
import { SqliteCatalogLifecycle } from "./sqlite-catalog-lifecycle";

const createdAt = "2026-08-03T08:00:00.000Z";
const archivedAt = "2026-08-04T09:00:00.000Z";
const appliedAt = "2026-08-05T10:30:00.000Z";

interface DatabaseHarness {
  database: SqlReadDatabase;
  events: string[];
  apply(plan: LifecyclePlan, appliedAt: string): void;
  snapshot(): CatalogHierarchy;
  replaceSnapshot(hierarchy: CatalogHierarchy): void;
}

function createDatabaseHarness(
  hierarchy: CatalogHierarchy,
  applyFailure?: () => unknown | undefined,
  rollbackFailure?: () => unknown | undefined,
): DatabaseHarness {
  let committed = structuredClone(hierarchy);
  const events: string[] = [];

  const database = {
    select: vi.fn(async (query: string, values: unknown[] = []) => {
      const table = selectedTable(query);
      events.push(`SELECT ${table}`);
      return selectRows(committed, table, query, values);
    }),
  } satisfies SqlReadDatabase;

  return {
    database,
    events,
    apply: (plan, appliedAt) => {
      events.push("INVOKE apply_catalog_lifecycle");
      const currentPlan = planCatalogLifecycle(committed, {
        operation: plan.operation,
        target: plan.target,
      });
      if (!samePlan(plan, currentPlan)) throw new Error("stale-plan: hierarchy changed");

      const failure = applyFailure?.();
      if (failure !== undefined) {
        const rollback = rollbackFailure?.();
        if (rollback !== undefined) {
          throw new Error(
            `Lifecycle change was not saved: ${String(failure)}. Transaction rollback also failed: ${String(rollback)}.`,
          );
        }
        throw failure;
      }

      const nextArchivedAt = plan.operation === "archive" ? appliedAt : null;
      for (const record of plan.records) {
        const rows =
          record.kind === "client"
            ? committed.clients
            : record.kind === "project"
              ? committed.projects
              : record.kind === "task"
                ? committed.tasks
                : (committed.expenses ?? []);
        const row = rows.find((candidate) => candidate.id === record.id) as
          | { archivedAt: string | null; updatedAt: string }
          | undefined;
        if (!row) throw new Error("stale-plan: record disappeared");
        row.archivedAt = nextArchivedAt;
        row.updatedAt = appliedAt;
      }
    },
    snapshot: () => structuredClone(committed),
    replaceSnapshot: (next) => {
      committed = structuredClone(next);
    },
  };
}

function createLifecycleHarness(
  hierarchy: CatalogHierarchy,
  options: CatalogLifecycleHarnessOptions & {
    rollbackFailure?: () => unknown | undefined;
  } = {},
) {
  const storage = createDatabaseHarness(
    hierarchy,
    options.applyFailure,
    options.rollbackFailure,
  );
  const lifecycle = new SqliteCatalogLifecycle({
    getDatabase: async () => storage.database,
    invoke: async <T>(command: string, args?: Record<string, unknown>) => {
      expect(command).toBe("apply_catalog_lifecycle");
      const { plan } = args as { plan: LifecyclePlan };
      storage.apply(plan, appliedAt);
      return undefined as T;
    },
  });
  return { lifecycle, storage };
}

catalogLifecycleContract("SQLite catalog lifecycle", (hierarchy, options) => {
  const { lifecycle, storage } = createLifecycleHarness(hierarchy, options);
  return {
    lifecycle,
    snapshot: storage.snapshot,
    replaceSnapshot: storage.replaceSnapshot,
  };
});

describe("SQLite lifecycle transaction boundary", () => {
  test.each([
    {
      label: "direct Client",
      expenseId: "expense-direct",
      clientId: "client-1",
      projectId: null,
      expectedImpact: "Restore Acme and expense-direct. Sibling records remain unchanged.",
    },
    {
      label: "Project",
      expenseId: "expense-project",
      clientId: null,
      projectId: "project-1",
      expectedImpact: "Restore Acme, Website, and expense-project. Sibling records remain unchanged.",
    },
  ])("previews a $label Expense through SQLite-valid target hierarchy SQL", async ({
    expenseId,
    clientId,
    projectId,
    expectedImpact,
  }) => {
    const database: SqlReadDatabase = {
      select: vi.fn(async (query: string) => {
        if (query.includes("SELECT clients.id")) {
          const script = `
            CREATE TABLE clients (id TEXT, name TEXT, archived_at TEXT);
            CREATE TABLE projects (id TEXT, client_id TEXT, name TEXT, archived_at TEXT);
            CREATE TABLE expenses (id TEXT, client_id TEXT, project_id TEXT, description TEXT, archived_at TEXT);
            INSERT INTO clients VALUES ('client-1', 'Acme', '${archivedAt}');
            INSERT INTO projects VALUES ('project-1', 'client-1', 'Website', '${archivedAt}');
            INSERT INTO expenses VALUES ('${expenseId}', ${clientId ? `'${clientId}'` : "NULL"}, ${projectId ? `'${projectId}'` : "NULL"}, '${expenseId}', '${archivedAt}');
            ${query.split("$1").join(`'${expenseId}'`)};
          `;
          const output = execFileSync("sqlite3", ["-json", ":memory:"], {
            encoding: "utf8",
            input: script,
          });
          return output.trim() ? JSON.parse(output) as unknown[] : [];
        }
        if (query.includes("FROM projects")) {
          return projectId
            ? [{ id: projectId, client_id: "client-1", name: "Website", archived_at: archivedAt }]
            : [];
        }
        return [{
          id: expenseId,
          client_id: clientId,
          project_id: projectId,
          description: expenseId,
          archived_at: archivedAt,
        }];
      }),
    };
    const lifecycle = new SqliteCatalogLifecycle({ getDatabase: async () => database });

    await expect(lifecycle.preview({
      operation: "restore",
      target: { kind: "expense", id: expenseId },
    })).resolves.toMatchObject({ impactDescription: expectedImpact });
  });

  test("loads hierarchy in deterministic Client, Project, Task order", async () => {
    const { lifecycle, storage } = createLifecycleHarness(activeHierarchy());

    await lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });

    expect(storage.events).toEqual([
      "SELECT clients",
      "SELECT projects",
      "SELECT tasks",
      "SELECT expenses",
    ]);
    expect(storage.database.select).toHaveBeenNthCalledWith(
      1,
      expect.stringMatching(
        /SELECT\s+id, name, archived_at\s+FROM clients\s+WHERE id = \$1\s+ORDER BY id/,
      ),
      ["client-1"],
    );
    expect(storage.database.select).toHaveBeenNthCalledWith(
      2,
      expect.stringMatching(
        /SELECT\s+id, client_id, name, archived_at\s+FROM projects\s+WHERE client_id = \$1\s+ORDER BY id/,
      ),
      ["client-1"],
    );
    expect(storage.database.select).toHaveBeenNthCalledWith(
      3,
      expect.stringMatching(
        /SELECT\s+id, project_id, name, archived_at\s+FROM tasks\s+WHERE project_id IN \([\s\S]*client_id = \$1[\s\S]*\)\s+ORDER BY id/,
      ),
      ["client-1"],
    );
    for (const [query] of vi.mocked(storage.database.select).mock.calls) {
      expect(query).not.toMatch(/normalized_name|currency_code|hourly_rate|created_at|updated_at/);
    }
  });

  test("restores ancestors and target in one exact ordered transaction", async () => {
    const hierarchy = archivedHierarchy();
    const { lifecycle, storage } = createLifecycleHarness(hierarchy, {
      now: () => new Date(appliedAt),
    });
    const plan = await lifecycle.preview({
      operation: "restore",
      target: { kind: "task", id: "task-1" },
    });
    storage.events.length = 0;

    await lifecycle.apply(plan);

    expect(storage.events).toEqual(["INVOKE apply_catalog_lifecycle"]);
    expect(storage.snapshot().tasks[1].archivedAt).toBe(archivedAt);
    expect(storage.database.select).toHaveBeenNthCalledWith(
      1,
      expect.stringMatching(/FROM clients[\s\S]*tasks\.id = \$1/),
      ["task-1"],
    );
    expect(storage.database.select).toHaveBeenNthCalledWith(
      2,
      expect.stringMatching(/FROM projects[\s\S]*tasks\.id = \$1/),
      ["task-1"],
    );
    expect(storage.database.select).toHaveBeenNthCalledWith(
      3,
      expect.stringMatching(/FROM tasks\s+WHERE id = \$1/),
      ["task-1"],
    );
  });

  test("applies confirmed lifecycle plans through the native transaction command", async () => {
    const { lifecycle, storage } = createLifecycleHarness(activeHierarchy(), {
      now: () => new Date(appliedAt),
    });
    const plan = await lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });
    storage.events.length = 0;

    await lifecycle.apply(plan);

    expect(storage.events).toEqual(["INVOKE apply_catalog_lifecycle"]);
  });

  test("rolls back every write and maps an update failure to persistence", async () => {
    let failed = false;
    const hierarchy = activeHierarchy();
    const { lifecycle, storage } = createLifecycleHarness(hierarchy, {
      now: () => new Date(appliedAt),
      applyFailure: () => {
        if (failed) return undefined;
        failed = true;
        return new Error("database locked");
      },
    });
    const plan = await lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });
    storage.events.length = 0;

    const error = await lifecycle.apply(plan).catch((caught: unknown) => caught);
    expect(error).toMatchObject({ code: "persistence" });
    expect((error as Error).message).toContain("database locked");
    expect(storage.events).toEqual(["INVOKE apply_catalog_lifecycle"]);
    expect(storage.snapshot()).toEqual(hierarchy);
  });

  test("shows a string persistence failure from the local driver", async () => {
    const { lifecycle } = createLifecycleHarness(activeHierarchy(), {
      applyFailure: () => "database is locked",
    });
    const plan = await lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });

    const error = await lifecycle.apply(plan).catch((caught: unknown) => caught);

    expect((error as Error).message).toContain("database is locked");
  });

  test("exposes the original apply failure when rollback also fails", async () => {
    const applyFailure = new Error("database locked");
    const rollbackFailure = new Error("rollback connection lost");
    const { lifecycle, storage } = createLifecycleHarness(activeHierarchy(), {
      now: () => new Date(appliedAt),
      applyFailure: () => applyFailure,
      rollbackFailure: () => rollbackFailure,
    });
    const plan = await lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });
    storage.events.length = 0;

    const error = await lifecycle.apply(plan).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(CatalogLifecycleError);
    expect((error as CatalogLifecycleError).code).toBe("persistence");
    expect((error as CatalogLifecycleError).message).toContain(
      applyFailure.message,
    );
    expect((error as CatalogLifecycleError).message).toContain(
      rollbackFailure.message,
    );
    expect(storage.events).toEqual(["INVOKE apply_catalog_lifecycle"]);
  });

  test("rolls back a stale scope before timestamp or update execution", async () => {
    const now = vi.fn(() => new Date(appliedAt));
    const hierarchy = activeHierarchy();
    const { lifecycle, storage } = createLifecycleHarness(hierarchy, { now });
    const plan = await lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });
    const changed: CatalogHierarchy = {
      ...hierarchy,
      tasks: [
        ...hierarchy.tasks,
        {
          id: "task-new",
          projectId: "project-1",
          name: "New scope",
          hourlyRateOverrideMinor: null,
          createdAt,
          updatedAt: createdAt,
          archivedAt: null,
        },
      ],
    };
    storage.replaceSnapshot(changed);
    storage.events.length = 0;

    await expect(lifecycle.apply(plan)).rejects.toMatchObject({
      code: "stale-plan",
    });
    expect(storage.events).toEqual(["INVOKE apply_catalog_lifecycle"]);
    expect(now).not.toHaveBeenCalled();
    expect(storage.snapshot()).toEqual(changed);
  });
});

function selectedTable(query: string): "clients" | "projects" | "tasks" | "expenses" {
  if (query.includes("SELECT clients.id")) return "clients";
  if (query.includes("FROM expenses")) return "expenses";
  if (query.includes("FROM clients")) return "clients";
  if (query.includes("FROM tasks")) return "tasks";
  if (query.includes("FROM projects")) return "projects";
  throw new Error(`unexpected SELECT: ${query}`);
}

function selectRows(
  hierarchy: CatalogHierarchy,
  table: "clients" | "projects" | "tasks" | "expenses",
  query: string,
  values: unknown[],
) {
  const id = String(values[0]);
  if (table === "expenses") {
    if (query.includes("LEFT JOIN projects")) {
      const projectIds = new Set(
        hierarchy.projects
          .filter((candidate) => candidate.clientId === id)
          .map((candidate) => candidate.id),
      );
      return (hierarchy.expenses ?? [])
        .filter(
          (candidate) =>
            (candidate.target.kind === "client" && candidate.target.clientId === id) ||
            (candidate.target.kind === "project" && projectIds.has(candidate.target.projectId)),
        )
        .map(expenseRow);
    }
    if (query.includes("project_id = $1")) {
      return (hierarchy.expenses ?? [])
        .filter(
          (candidate) =>
            candidate.target.kind === "project" && candidate.target.projectId === id,
        )
        .map(expenseRow);
    }
    return (hierarchy.expenses ?? [])
      .filter((candidate) => candidate.id === id)
      .map(expenseRow);
  }
  if (table === "clients") {
    if (query.includes("JOIN expenses") || query.includes("FROM expenses")) {
      const expense = hierarchy.expenses?.find((candidate) => candidate.id === id);
      const project = hierarchy.projects.find(
        (candidate) =>
          expense?.target.kind === "project" && candidate.id === expense.target.projectId,
      );
      const clientId =
        expense?.target.kind === "client" ? expense.target.clientId : project?.clientId;
      return hierarchy.clients.filter((candidate) => candidate.id === clientId).map(clientRow);
    }
    if (query.includes("JOIN tasks")) {
      const task = hierarchy.tasks.find((candidate) => candidate.id === id);
      const project = hierarchy.projects.find(
        (candidate) => candidate.id === task?.projectId,
      );
      return hierarchy.clients
        .filter((candidate) => candidate.id === project?.clientId)
        .map(clientRow);
    }
    if (query.includes("JOIN projects")) {
      const project = hierarchy.projects.find((candidate) => candidate.id === id);
      return hierarchy.clients
        .filter((candidate) => candidate.id === project?.clientId)
        .map(clientRow);
    }
    return hierarchy.clients.filter((candidate) => candidate.id === id).map(clientRow);
  }
  if (table === "projects") {
    if (query.includes("JOIN expenses")) {
      const expense = hierarchy.expenses?.find((candidate) => candidate.id === id);
      return hierarchy.projects
        .filter(
          (candidate) =>
            expense?.target.kind === "project" && candidate.id === expense.target.projectId,
        )
        .map(projectRow);
    }
    if (query.includes("JOIN tasks")) {
      const task = hierarchy.tasks.find((candidate) => candidate.id === id);
      return hierarchy.projects
        .filter((candidate) => candidate.id === task?.projectId)
        .map(projectRow);
    }
    if (query.includes("client_id = $1")) {
      return hierarchy.projects
        .filter((candidate) => candidate.clientId === id)
        .map(projectRow);
    }
    return hierarchy.projects.filter((candidate) => candidate.id === id).map(projectRow);
  }
  if (query.includes("project_id IN")) {
    const projectIds = new Set(
      hierarchy.projects
        .filter((candidate) => candidate.clientId === id)
        .map((candidate) => candidate.id),
    );
    return hierarchy.tasks
      .filter((candidate) => projectIds.has(candidate.projectId))
      .map(taskRow);
  }
  if (query.includes("project_id = $1")) {
    return hierarchy.tasks
      .filter((candidate) => candidate.projectId === id)
      .map(taskRow);
  }
  return hierarchy.tasks.filter((candidate) => candidate.id === id).map(taskRow);
}

function clientRow(client: CatalogHierarchy["clients"][number]) {
  return {
    id: client.id,
    name: client.name,
    archived_at: client.archivedAt,
  };
}

function projectRow(project: CatalogHierarchy["projects"][number]) {
  return {
    id: project.id,
    client_id: project.clientId,
    name: project.name,
    archived_at: project.archivedAt,
  };
}

function taskRow(task: CatalogHierarchy["tasks"][number]) {
  return {
    id: task.id,
    project_id: task.projectId,
    name: task.name,
    archived_at: task.archivedAt,
  };
}

function expenseRow(expense: NonNullable<CatalogHierarchy["expenses"]>[number]) {
  return {
    id: expense.id,
    client_id: expense.target.kind === "client" ? expense.target.clientId : null,
    project_id: expense.target.kind === "project" ? expense.target.projectId : null,
    description: expense.description,
    archived_at: expense.archivedAt,
  };
}

function samePlan(expected: LifecyclePlan, current: LifecyclePlan): boolean {
  return (
    expected.operation === current.operation &&
    expected.target.kind === current.target.kind &&
    expected.target.id === current.target.id &&
    expected.impactDescription === current.impactDescription &&
    expected.records.length === current.records.length &&
    expected.records.every((record, index) => {
      const candidate = current.records[index];
      return (
        candidate?.kind === record.kind &&
        candidate.id === record.id &&
        candidate.name === record.name &&
        candidate.archivedAt === record.archivedAt
      );
    })
  );
}

function activeHierarchy(): CatalogHierarchy {
  return hierarchy(null);
}

function archivedHierarchy(): CatalogHierarchy {
  return hierarchy(archivedAt);
}

function hierarchy(state: string | null): CatalogHierarchy {
  return {
    clients: [
      {
        id: "client-1",
        name: "Acme",
        currencyCode: "EUR",
        hourlyRateMinor: null,
        createdAt,
        updatedAt: createdAt,
        archivedAt: state,
      },
    ],
    projects: [
      {
        id: "project-1",
        clientId: "client-1",
        name: "Website",
        hourlyRateOverrideMinor: null,
        createdAt,
        updatedAt: createdAt,
        archivedAt: state,
      },
    ],
    tasks: [
      {
        id: "task-1",
        projectId: "project-1",
        name: "Research",
        hourlyRateOverrideMinor: null,
        createdAt,
        updatedAt: createdAt,
        archivedAt: state,
      },
      {
        id: "task-2",
        projectId: "project-1",
        name: "Retired review",
        hourlyRateOverrideMinor: null,
        createdAt,
        updatedAt: createdAt,
        archivedAt: archivedAt,
      },
    ],
    expenses: [
      expense("expense-direct", { kind: "client", clientId: "client-1" }, state),
      expense("expense-project", { kind: "project", projectId: "project-1" }, state),
      expense("expense-archived", { kind: "project", projectId: "project-1" }, archivedAt),
    ],
  };
}

function expense(
  id: string,
  target: { kind: "client"; clientId: string } | { kind: "project"; projectId: string },
  state: string | null,
): NonNullable<CatalogHierarchy["expenses"]>[number] {
  return {
    id,
    target,
    expenseDate: "2026-08-03",
    description: id,
    originalCurrencyCode: "EUR",
    originalAmountMinor: 100,
    billingCurrencyCode: "EUR",
    billingAmountMinor: 100,
    appliedRate: "1",
    rateSource: "manual",
    rateObservedOn: null,
    rateManuallyAdjusted: false,
    createdAt,
    updatedAt: createdAt,
    archivedAt: state,
  };
}
