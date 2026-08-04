import { describe, expect, test, vi } from "vitest";

import type {
  IndependentSqlStatementExecutor,
  SqlReadDatabase,
} from "@/infrastructure/sqlite/plugin-sql-adapter";
import { SqliteClientCatalog } from "./sqlite-client-catalog";

const now = "2026-07-31T10:00:00.000Z";
const row = {
  id: "client-1",
  name: "Acme",
  normalized_name: "acme",
  currency_code: "EUR",
  hourly_rate_minor: 12_500,
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

describe("SQLite client catalog", () => {
  test("uses separate active and archived queries and decodes rows", async () => {
    const database = createDatabase([row]);
    const catalog = new SqliteClientCatalog(databaseOptions(database));

    await expect(catalog.list("active")).resolves.toMatchObject([
      { id: "client-1", name: "Acme", hourlyRateMinor: 12_500 },
    ]);
    expect(database.select).toHaveBeenLastCalledWith(
      expect.stringContaining("archived_at IS NULL"),
    );

    await catalog.list("archived");
    expect(database.select).toHaveBeenLastCalledWith(
      expect.stringContaining("archived_at IS NOT NULL"),
    );
  });

  test("looks up active and archived clients by ID", async () => {
    const archivedRow = { ...row, id: "client-2", archived_at: now };
    const database = createDatabase();
    database.select
      .mockResolvedValueOnce([row])
      .mockResolvedValueOnce([archivedRow]);
    const catalog = new SqliteClientCatalog(databaseOptions(database));

    await expect(catalog.get("client-1")).resolves.toMatchObject({
      id: "client-1",
      archivedAt: null,
    });
    await expect(catalog.get("client-2")).resolves.toMatchObject({
      id: "client-2",
      archivedAt: now,
    });
    expect(database.select).toHaveBeenLastCalledWith(
      expect.stringContaining("WHERE id = $1"),
      ["client-2"],
    );
  });

  test("maps missing client ID lookup to not found", async () => {
    const database = createDatabase([]);
    const catalog = new SqliteClientCatalog(databaseOptions(database));

    await expect(catalog.get("missing-client")).rejects.toMatchObject({
      code: "not-found",
    });
  });

  test("binds normalized data when creating a client", async () => {
    const database = createDatabase();
    const catalog = new SqliteClientCatalog({
      ...databaseOptions(database),
      createId: () => "client-1",
      now: () => new Date(now),
    });

    await catalog.create({
      name: "Acme",
      currencyCode: "EUR",
      hourlyRateMinor: 0,
    });

    expect(database.execute).toHaveBeenCalledWith(
      expect.stringContaining("INSERT INTO clients"),
      ["client-1", "Acme", "acme", "EUR", 0, now, now],
    );
  });

  test("translates active-name uniqueness failures", async () => {
    const database = createDatabase();
    database.execute.mockRejectedValueOnce(
      new Error("UNIQUE constraint failed: clients.normalized_name"),
    );
    const catalog = new SqliteClientCatalog(databaseOptions(database));

    await expect(
      catalog.create({
        name: "Acme",
        currencyCode: "EUR",
        hourlyRateMinor: null,
      }),
    ).rejects.toMatchObject({ code: "duplicate-name" });
  });

  test("translates invalid rows and unexpected storage failures", async () => {
    const invalidDatabase = createDatabase([{ ...row, hourly_rate_minor: -1 }]);
    const invalidCatalog = new SqliteClientCatalog({
      ...databaseOptions(invalidDatabase),
    });
    await expect(invalidCatalog.list("active")).rejects.toMatchObject({
      code: "invalid-data",
    });

    const failingDatabase = createDatabase();
    failingDatabase.select.mockRejectedValueOnce(new Error("database locked"));
    const failingCatalog = new SqliteClientCatalog({
      ...databaseOptions(failingDatabase),
    });
    await expect(failingCatalog.list("active")).rejects.toMatchObject({
      code: "persistence",
    });
  });

  test("invokes the native command with the exact immutable Client update plan", async () => {
    const database = createDatabase();
    database.select
      .mockResolvedValueOnce([row])
      .mockResolvedValueOnce([
        { id: "project-z", hourly_rate_override_minor: 12_500, updated_at: now },
        { id: "project-zero", hourly_rate_override_minor: 0, updated_at: now },
      ])
      .mockResolvedValueOnce([
        { id: "task-z", hourly_rate_override_minor: 7_500, updated_at: now },
        { id: "task-zero", hourly_rate_override_minor: 0, updated_at: now },
      ])
      .mockResolvedValue([
        {
          ...row,
          name: "Acme Consulting",
          normalized_name: "acme consulting",
          currency_code: "JPY",
          hourly_rate_minor: 125,
        },
      ]);
    const savedClient = {
      id: "client-1",
      name: "Acme Consulting",
      normalizedName: "acme consulting",
      currencyCode: "JPY",
      hourlyRateMinor: 125,
      createdAt: now,
      updatedAt: now,
      archivedAt: null,
    };
    const invoke = vi.fn().mockResolvedValue(savedClient);
    const catalog = new SqliteClientCatalog({
      ...databaseOptions(database),
      now: () => new Date(now),
      invoke,
    });

    await catalog.update("client-1", {
      name: " Acme Consulting ",
      currencyCode: "JPY",
      hourlyRateMinor: 125,
    });

    expect(invoke).toHaveBeenCalledOnce();
    expect(invoke).toHaveBeenCalledWith("apply_client_update", {
      plan: {
        clientId: "client-1",
        expectedClient: {
          id: "client-1", name: "Acme", normalizedName: "acme",
          currencyCode: "EUR", hourlyRateMinor: 12_500,
          createdAt: now, updatedAt: now, archivedAt: null,
        },
        client: savedClient,
        overrides: [
          { kind: "project", id: "project-z", expectedHourlyRateOverrideMinor: 12_500, expectedUpdatedAt: now, hourlyRateOverrideMinor: 125 },
          { kind: "project", id: "project-zero", expectedHourlyRateOverrideMinor: 0, expectedUpdatedAt: now, hourlyRateOverrideMinor: 0 },
          { kind: "task", id: "task-z", expectedHourlyRateOverrideMinor: 7_500, expectedUpdatedAt: now, hourlyRateOverrideMinor: 75 },
          { kind: "task", id: "task-zero", expectedHourlyRateOverrideMinor: 0, expectedUpdatedAt: now, hourlyRateOverrideMinor: 0 },
        ],
        updatedAt: now,
      },
    });
    expect(database.execute).not.toHaveBeenCalled();
    expect(database.select).toHaveBeenCalledTimes(3);
  });

  test("routes an unchanged-currency Client edit with the complete unchanged descendant snapshot", async () => {
    const database = createDatabase();
    database.select
      .mockResolvedValueOnce([row])
      .mockResolvedValueOnce([
        { id: "project-z", hourly_rate_override_minor: 13_501, updated_at: now },
        { id: "project-a", hourly_rate_override_minor: 0, updated_at: now },
      ])
      .mockResolvedValueOnce([
        { id: "task-z", hourly_rate_override_minor: 9_503, updated_at: now },
        { id: "task-a", hourly_rate_override_minor: 0, updated_at: now },
      ])
      .mockRejectedValue(new Error("unexpected post-commit read"));
    const savedClient = {
      id: "client-1",
      name: "Acme Renamed",
      normalizedName: "acme renamed",
      currencyCode: "EUR",
      hourlyRateMinor: 13_000,
      createdAt: now,
      updatedAt: now,
      archivedAt: null,
    };
    const invoke = vi.fn().mockResolvedValue(savedClient);
    const catalog = new SqliteClientCatalog({
      ...databaseOptions(database),
      now: () => new Date(now),
      invoke,
    });

    await expect(catalog.update("client-1", {
      name: " Acme Renamed ",
      currencyCode: "EUR",
      hourlyRateMinor: 13_000,
    })).resolves.toEqual(savedClient);

    expect(invoke).toHaveBeenCalledOnce();
    expect(invoke).toHaveBeenCalledWith("apply_client_update", {
      plan: {
        clientId: "client-1",
        expectedClient: {
          id: "client-1", name: "Acme", normalizedName: "acme",
          currencyCode: "EUR", hourlyRateMinor: 12_500,
          createdAt: now, updatedAt: now, archivedAt: null,
        },
        client: savedClient,
        overrides: [
          { kind: "project", id: "project-a", expectedHourlyRateOverrideMinor: 0, expectedUpdatedAt: now, hourlyRateOverrideMinor: 0 },
          { kind: "project", id: "project-z", expectedHourlyRateOverrideMinor: 13_501, expectedUpdatedAt: now, hourlyRateOverrideMinor: 13_501 },
          { kind: "task", id: "task-a", expectedHourlyRateOverrideMinor: 0, expectedUpdatedAt: now, hourlyRateOverrideMinor: 0 },
          { kind: "task", id: "task-z", expectedHourlyRateOverrideMinor: 9_503, expectedUpdatedAt: now, hourlyRateOverrideMinor: 9_503 },
        ],
        updatedAt: now,
      },
    });
    expect(database.select).toHaveBeenCalledTimes(3);
    expect(database.execute).not.toHaveBeenCalled();
  });

  test("rejects a lossy currency change before updating the client", async () => {
    const database = createDatabase();
    database.select.mockImplementation((query: string) =>
      Promise.resolve(
        query.includes("FROM projects")
          ? [{ id: "project-1", hourly_rate_override_minor: 12_550, updated_at: now }]
          : [row],
      ),
    );
    const catalog = new SqliteClientCatalog(databaseOptions(database));

    await expect(
      catalog.update("client-1", {
        name: "Acme",
        currencyCode: "JPY",
        hourlyRateMinor: 125,
      }),
    ).rejects.toMatchObject({ code: "invalid-data" });
    expect(database.execute).not.toHaveBeenCalledWith(
      expect.stringContaining("UPDATE clients"),
      expect.anything(),
    );
  });

  test("rejects lossy task precision before any descendant or client update", async () => {
    const database = createDatabase();
    database.select.mockImplementation((query: string) => {
      if (query.includes("FROM projects")) {
        return Promise.resolve([
          { id: "project-1", hourly_rate_override_minor: 12_500, updated_at: now },
        ]);
      }
      if (query.includes("FROM tasks")) {
        return Promise.resolve([
          { id: "task-1", hourly_rate_override_minor: 7_550, updated_at: now },
        ]);
      }
      return Promise.resolve([row]);
    });
    const catalog = new SqliteClientCatalog(databaseOptions(database));

    await expect(
      catalog.update("client-1", {
        name: "Acme",
        currencyCode: "JPY",
        hourlyRateMinor: 125,
      }),
    ).rejects.toMatchObject({ code: "invalid-data" });
    expect(database.execute).not.toHaveBeenCalled();
  });

  test("rejects every malformed selected task row before beginning a transaction", async () => {
    const database = createDatabase();
    database.select.mockImplementation((query: string) => {
      if (query.includes("FROM projects")) return Promise.resolve([]);
      if (query.includes("FROM tasks")) {
        return Promise.resolve([
          {
            ...row,
            id: "task-1",
            hourly_rate_override_minor: "7_500",
          },
        ]);
      }
      return Promise.resolve([row]);
    });
    const catalog = new SqliteClientCatalog(databaseOptions(database));

    await expect(
      catalog.update("client-1", {
        name: "Acme",
        currencyCode: "JPY",
        hourlyRateMinor: 125,
      }),
    ).rejects.toMatchObject({ code: "invalid-data" });
    expect(database.execute).not.toHaveBeenCalled();
  });

  test.each([
    ["duplicate", "duplicate: UNIQUE constraint failed: clients.normalized_name", "duplicate-name"],
    ["missing", "missing: Client does not exist", "not-found"],
    ["stale plan", "stale-plan: Client or descendants changed", "persistence"],
    ["invalid native data", "invalid-data: inconsistent Client plan", "invalid-data"],
    ["persistence", "persistence: database locked", "persistence"],
    [
      "rollback failure",
      "persistence: database locked. Transaction rollback also failed: disk I/O error",
      "persistence",
    ],
  ])("translates a native %s failure", async (_label, nativeFailure, code) => {
    const database = createDatabase();
    database.select
      .mockResolvedValueOnce([row])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValue([
        { ...row, currency_code: "JPY", hourly_rate_minor: 125 },
      ]);
    const catalog = new SqliteClientCatalog({
      ...databaseOptions(database),
      invoke: vi.fn().mockRejectedValue(nativeFailure),
    });

    await expect(catalog.update("client-1", {
      name: "Acme",
      currencyCode: "JPY",
      hourlyRateMinor: 125,
    })).rejects.toMatchObject({ code });
  });

  test("returns the native success result without a post-commit read", async () => {
    const database = createDatabase();
    database.select
      .mockResolvedValueOnce([row])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error("post-commit read must not occur"));
    const savedClient = {
      id: "client-1", name: "Renamed", normalizedName: "renamed",
      currencyCode: "JPY", hourlyRateMinor: 125,
      createdAt: now, updatedAt: now, archivedAt: null,
    };
    const catalog = new SqliteClientCatalog({
      ...databaseOptions(database),
      now: () => new Date(now),
      invoke: vi.fn().mockResolvedValue(savedClient),
    });

    await expect(catalog.update("client-1", {
      name: "Renamed", currencyCode: "JPY", hourlyRateMinor: 125,
    })).resolves.toEqual(savedClient);
    expect(database.select).toHaveBeenCalledTimes(3);
  });
});
