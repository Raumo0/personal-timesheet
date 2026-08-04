import { expect, test, vi } from "vitest";

import type {
  IndependentSqlStatementExecutor,
  SqlReadDatabase,
} from "@/infrastructure/sqlite/plugin-sql-adapter";
import { SqliteProjectCatalog } from "./sqlite-project-catalog";

const now = "2026-08-02T10:00:00.000Z";
const row = {
  id: "project-1",
  client_id: "client-1",
  name: "Website",
  normalized_name: "website",
  hourly_rate_override_minor: null,
  created_at: now,
  updated_at: now,
  archived_at: null,
};

function createDatabase(rows: unknown[] = []) {
  return {
    execute: vi.fn().mockResolvedValue({ rowsAffected: 1 }),
    select: vi.fn().mockResolvedValue(rows),
  } satisfies SqlReadDatabase & IndependentSqlStatementExecutor;
}

function databaseOptions(database: ReturnType<typeof createDatabase>) {
  return { getDatabase: async () => database, statementExecutor: database };
}

test("persists an inherited null override and scopes active project queries to a client", async () => {
  const database = createDatabase([row]);
  const catalog = new SqliteProjectCatalog({
    ...databaseOptions(database),
    createId: () => "project-1",
    now: () => new Date(now),
  });

  await catalog.create("client-1", {
    name: "Website",
    hourlyRateOverrideMinor: null,
  });
  expect(database.execute).toHaveBeenCalledWith(
    expect.stringContaining("INSERT INTO projects"),
    ["project-1", "client-1", "Website", "website", null, now, now],
  );

  await expect(catalog.list("client-1", "active")).resolves.toMatchObject([
    { id: "project-1", clientId: "client-1", hourlyRateOverrideMinor: null },
  ]);
  expect(database.select).toHaveBeenLastCalledWith(
    expect.stringContaining("client_id = $1 AND archived_at IS NULL"),
    ["client-1"],
  );
});

test("looks up active and archived projects by matching client and project IDs", async () => {
  const archivedRow = { ...row, id: "project-2", archived_at: now };
  const database = createDatabase();
  database.select
    .mockResolvedValueOnce([row])
    .mockResolvedValueOnce([archivedRow]);
  const catalog = new SqliteProjectCatalog(databaseOptions(database));

  await expect(catalog.get("client-1", "project-1")).resolves.toMatchObject({
    id: "project-1",
    clientId: "client-1",
    archivedAt: null,
  });
  await expect(catalog.get("client-1", "project-2")).resolves.toMatchObject({
    id: "project-2",
    clientId: "client-1",
    archivedAt: now,
  });
  expect(database.select).toHaveBeenLastCalledWith(
    expect.stringContaining("WHERE id = $1 AND client_id = $2"),
    ["project-2", "client-1"],
  );
});

test("maps missing and mismatched project lookups to not found", async () => {
  const database = createDatabase([]);
  const catalog = new SqliteProjectCatalog(databaseOptions(database));

  await expect(catalog.get("client-1", "missing-project")).rejects.toMatchObject({
    code: "not-found",
  });
  await expect(catalog.get("client-2", "project-1")).rejects.toMatchObject({
    code: "not-found",
  });
});

test("preserves an explicit zero override and maps persistence failures", async () => {
  const database = createDatabase([{ ...row, hourly_rate_override_minor: 0 }]);
  const catalog = new SqliteProjectCatalog(databaseOptions(database));
  await expect(catalog.list("client-1", "active")).resolves.toMatchObject([
    { hourlyRateOverrideMinor: 0 },
  ]);

  database.select.mockRejectedValueOnce(new Error("database locked"));
  await expect(catalog.list("client-1", "active")).rejects.toMatchObject({
    code: "persistence",
  });
});

test("updates without opening the read database", async () => {
  const statementExecutor = createDatabase();
  const catalog = new SqliteProjectCatalog({
    getDatabase: vi.fn().mockRejectedValue(new Error("read unavailable")),
    statementExecutor,
    now: () => new Date(now),
  });
  await expect(catalog.update("client-1", "project-1", { name: "Renamed", hourlyRateOverrideMinor: 0 })).resolves.toMatchObject({
    id: "project-1", clientId: "client-1", name: "Renamed", updatedAt: now,
  });
});
