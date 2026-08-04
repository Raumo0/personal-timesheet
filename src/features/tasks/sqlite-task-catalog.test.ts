import { describe, expect, test, vi } from "vitest";

import type {
  IndependentSqlStatementExecutor,
  SqlReadDatabase,
} from "@/infrastructure/sqlite/plugin-sql-adapter";
import { taskCatalogContract } from "./task-catalog.contract";
import { SqliteTaskCatalog } from "./sqlite-task-catalog";
import type { TaskRow } from "./task";

const now = "2026-08-03T10:00:00.000Z";
const inheritedRow: TaskRow = {
  id: "task-1",
  project_id: "project-1",
  name: "Discovery",
  normalized_name: "discovery",
  hourly_rate_override_minor: null,
  created_at: now,
  updated_at: now,
  archived_at: null,
};

function createDatabase(initialRows: Array<typeof inheritedRow> = []) {
  const rows = initialRows.map((row) => ({ ...row }));
  const database = {
    execute: vi.fn(async (query: string, values: unknown[] = []) => {
      if (query.includes("INSERT INTO tasks")) {
        const [id, projectId, name, normalizedName, override, createdAt, updatedAt] =
          values;
        if (
          rows.some(
            (row) =>
              row.project_id === projectId &&
              row.normalized_name === normalizedName &&
              row.archived_at === null,
          )
        ) {
          throw new Error(
            "UNIQUE constraint failed: tasks.project_id, tasks.normalized_name",
          );
        }
        rows.push({
          id: String(id),
          project_id: String(projectId),
          name: String(name),
          normalized_name: String(normalizedName),
          hourly_rate_override_minor: override as number | null,
          created_at: String(createdAt),
          updated_at: String(updatedAt),
          archived_at: null,
        });
        return { rowsAffected: 1 };
      }


      if (query.includes("UPDATE tasks")) {
        const [name, normalizedName, override, updatedAt, id, projectId] = values;
        const row = rows.find(
          (candidate) =>
            candidate.id === id &&
            candidate.project_id === projectId &&
            candidate.archived_at === null,
        );
        if (!row) return { rowsAffected: 0 };
        row.name = String(name);
        row.normalized_name = String(normalizedName);
        row.hourly_rate_override_minor = override as number | null;
        row.updated_at = String(updatedAt);
        return { rowsAffected: 1 };
      }

      return { rowsAffected: 0 };
    }),
    select: vi.fn(async (query: string, values: unknown[] = []) => {
      const projectId = values[0];
      return rows
        .filter((row) => row.project_id === projectId)
        .filter((row) =>
          query.includes("archived_at IS NOT NULL")
            ? row.archived_at !== null
            : row.archived_at === null,
        )
        .sort((left, right) => left.name.localeCompare(right.name));
    }),
  } satisfies SqlReadDatabase & IndependentSqlStatementExecutor;
  return database;
}

function databaseOptions(database: ReturnType<typeof createDatabase>) {
  return { getDatabase: async () => database, statementExecutor: database };
}

let contractId = 0;
taskCatalogContract("SQLite", () => {
  const database = createDatabase();
  return new SqliteTaskCatalog({
    ...databaseOptions(database),
    createId: () => `task-${++contractId}`,
    now: () => new Date(now),
  });
});

describe("SQLite task catalog persistence", () => {
  test("updates without opening the read database", async () => {
    const statementExecutor = createDatabase([inheritedRow]);
    const catalog = new SqliteTaskCatalog({
      getDatabase: vi.fn().mockRejectedValue(new Error("read unavailable")),
      statementExecutor,
      now: () => new Date(now),
    });
    await expect(catalog.update("project-1", "task-1", { name: "Renamed", hourlyRateOverrideMinor: 0 })).resolves.toMatchObject({
      id: "task-1", projectId: "project-1", name: "Renamed", updatedAt: now,
    });
  });
  test("binds inherited NULL and maps an explicit zero row", async () => {
    const database = createDatabase([
      { ...inheritedRow, hourly_rate_override_minor: 0 },
    ]);
    const catalog = new SqliteTaskCatalog({
      ...databaseOptions(database),
      createId: () => "task-2",
      now: () => new Date(now),
    });

    await catalog.create("project-1", {
      name: "Planning",
      hourlyRateOverrideMinor: null,
    });
    expect(database.execute).toHaveBeenCalledWith(
      expect.stringContaining("INSERT INTO tasks"),
      ["task-2", "project-1", "Planning", "planning", null, now, now],
    );

    await expect(catalog.list("project-1", "active")).resolves.toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "task-1",
          projectId: "project-1",
          hourlyRateOverrideMinor: 0,
        }),
      ]),
    );
  });

  test("uses ordered project-scoped active and archived list SQL", async () => {
    const database = createDatabase([inheritedRow]);
    const catalog = new SqliteTaskCatalog(databaseOptions(database));

    await catalog.list("project-1", "active");
    expect(database.select).toHaveBeenLastCalledWith(
      expect.stringMatching(
        /project_id = \$1 AND archived_at IS NULL[\s\S]*ORDER BY name COLLATE NOCASE/,
      ),
      ["project-1"],
    );

    await catalog.list("project-1", "archived");
    expect(database.select).toHaveBeenLastCalledWith(
      expect.stringMatching(
        /project_id = \$1 AND archived_at IS NOT NULL[\s\S]*ORDER BY name COLLATE NOCASE/,
      ),
      ["project-1"],
    );
  });

  test("scopes update statements to both task and project", async () => {
    const database = createDatabase([inheritedRow]);
    const catalog = new SqliteTaskCatalog({
      ...databaseOptions(database),
      now: () => new Date(now),
    });

    await catalog.update("project-1", "task-1", {
      name: "Research",
      hourlyRateOverrideMinor: 0,
    });
    expect(database.execute).toHaveBeenLastCalledWith(
      expect.stringMatching(
        /UPDATE tasks[\s\S]*WHERE id = \$5 AND project_id = \$6 AND archived_at IS NULL/,
      ),
      ["Research", "research", 0, now, "task-1", "project-1"],
    );
  });

  test("maps read and write failures to persistence errors", async () => {
    const database = createDatabase();
    const catalog = new SqliteTaskCatalog(databaseOptions(database));

    database.select.mockRejectedValueOnce(new Error("database locked"));
    await expect(catalog.list("project-1", "active")).rejects.toMatchObject({
      code: "persistence",
    });

    database.execute.mockRejectedValueOnce(new Error("disk full"));
    await expect(
      catalog.create("project-1", {
        name: "Discovery",
        hourlyRateOverrideMinor: null,
      }),
    ).rejects.toMatchObject({ code: "persistence" });
  });
});
