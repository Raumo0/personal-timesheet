import { describe, expect, test, vi } from "vitest";

import type { SqlDatabase } from "../clients/database";
import type { CatalogHierarchy } from "./catalog-lifecycle";
import {
  catalogLifecycleContract,
  type CatalogLifecycleHarnessOptions,
} from "./catalog-lifecycle.contract";
import { SqliteCatalogLifecycle } from "./sqlite-catalog-lifecycle";

const createdAt = "2026-08-03T08:00:00.000Z";
const archivedAt = "2026-08-04T09:00:00.000Z";
const appliedAt = "2026-08-05T10:30:00.000Z";

interface DatabaseHarness {
  database: SqlDatabase;
  events: string[];
  snapshot(): CatalogHierarchy;
  replaceSnapshot(hierarchy: CatalogHierarchy): void;
}

function createDatabaseHarness(
  hierarchy: CatalogHierarchy,
  applyFailure?: () => unknown | undefined,
): DatabaseHarness {
  let committed = structuredClone(hierarchy);
  let transaction: CatalogHierarchy | undefined;
  const events: string[] = [];

  const database = {
    select: vi.fn(async (query: string, values: unknown[] = []) => {
      const table = selectedTable(query);
      events.push(`SELECT ${table}`);
      const source = transaction ?? committed;
      return selectRows(source, table, query, values);
    }),
    execute: vi.fn(async (query: string, values: unknown[] = []) => {
      if (query === "BEGIN") {
        events.push("BEGIN");
        transaction = structuredClone(committed);
        return { rowsAffected: 0 };
      }
      if (query === "COMMIT") {
        events.push("COMMIT");
        if (!transaction) throw new Error("no transaction");
        committed = transaction;
        transaction = undefined;
        return { rowsAffected: 0 };
      }
      if (query === "ROLLBACK") {
        events.push("ROLLBACK");
        transaction = undefined;
        return { rowsAffected: 0 };
      }

      const table = updatedTable(query);
      events.push(`UPDATE ${table}`);
      const failure = applyFailure?.();
      if (failure !== undefined) throw failure;
      if (!transaction) throw new Error("update outside transaction");
      const [nextArchivedAt, updatedAt, id] = values;
      const rows =
        table === "clients"
          ? transaction.clients
          : table === "projects"
            ? transaction.projects
            : transaction.tasks;
      const record = rows.find((candidate) => candidate.id === id);
      if (!record) return { rowsAffected: 0 };
      record.archivedAt = nextArchivedAt as string | null;
      record.updatedAt = String(updatedAt);
      return { rowsAffected: 1 };
    }),
  } satisfies SqlDatabase;

  return {
    database,
    events,
    snapshot: () => structuredClone(committed),
    replaceSnapshot: (next) => {
      committed = structuredClone(next);
      transaction = undefined;
    },
  };
}

function createLifecycleHarness(
  hierarchy: CatalogHierarchy,
  options: CatalogLifecycleHarnessOptions = {},
) {
  const storage = createDatabaseHarness(hierarchy, options.applyFailure);
  const lifecycle = new SqliteCatalogLifecycle({
    getDatabase: async () => storage.database,
    now: options.now,
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
    for (const [query] of storage.database.select.mock.calls) {
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

    expect(storage.events).toEqual([
      "BEGIN",
      "SELECT clients",
      "SELECT projects",
      "SELECT tasks",
      "UPDATE clients",
      "UPDATE projects",
      "UPDATE tasks",
      "COMMIT",
    ]);
    expect(storage.database.execute).toHaveBeenCalledWith(
      expect.stringContaining("UPDATE clients"),
      [null, appliedAt, "client-1"],
    );
    expect(storage.database.execute).toHaveBeenCalledWith(
      expect.stringContaining("UPDATE projects"),
      [null, appliedAt, "project-1"],
    );
    expect(storage.database.execute).toHaveBeenCalledWith(
      expect.stringContaining("UPDATE tasks"),
      [null, appliedAt, "task-1"],
    );
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
    expect(storage.database.select).toHaveBeenNthCalledWith(
      4,
      expect.stringMatching(/FROM clients[\s\S]*tasks\.id = \$1/),
      ["task-1"],
    );
    expect(storage.database.select).toHaveBeenNthCalledWith(
      5,
      expect.stringMatching(/FROM projects[\s\S]*tasks\.id = \$1/),
      ["task-1"],
    );
    expect(storage.database.select).toHaveBeenNthCalledWith(
      6,
      expect.stringMatching(/FROM tasks\s+WHERE id = \$1/),
      ["task-1"],
    );
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

    await expect(lifecycle.apply(plan)).rejects.toMatchObject({
      code: "persistence",
    });
    expect(storage.events).toEqual([
      "BEGIN",
      "SELECT clients",
      "SELECT projects",
      "SELECT tasks",
      "UPDATE clients",
      "ROLLBACK",
    ]);
    expect(storage.snapshot()).toEqual(hierarchy);
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
    expect(storage.events).toEqual([
      "BEGIN",
      "SELECT clients",
      "SELECT projects",
      "SELECT tasks",
      "ROLLBACK",
    ]);
    expect(now).not.toHaveBeenCalled();
    expect(storage.snapshot()).toEqual(changed);
  });
});

function selectedTable(query: string): "clients" | "projects" | "tasks" {
  if (query.includes("FROM clients")) return "clients";
  if (query.includes("FROM tasks")) return "tasks";
  if (query.includes("FROM projects")) return "projects";
  throw new Error(`unexpected SELECT: ${query}`);
}

function selectRows(
  hierarchy: CatalogHierarchy,
  table: "clients" | "projects" | "tasks",
  query: string,
  values: unknown[],
) {
  const id = String(values[0]);
  if (table === "clients") {
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

function updatedTable(query: string): "clients" | "projects" | "tasks" {
  if (query.includes("UPDATE clients")) return "clients";
  if (query.includes("UPDATE projects")) return "projects";
  if (query.includes("UPDATE tasks")) return "tasks";
  throw new Error(`unexpected execute: ${query}`);
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
  };
}
