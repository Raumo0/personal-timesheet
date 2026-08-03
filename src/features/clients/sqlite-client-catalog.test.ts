import { describe, expect, test, vi } from "vitest";

import type { SqlDatabase } from "./database";
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
  } satisfies SqlDatabase;
}

describe("SQLite client catalog", () => {
  test("uses separate active and archived queries and decodes rows", async () => {
    const database = createDatabase([row]);
    const catalog = new SqliteClientCatalog({ getDatabase: async () => database });

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
    const catalog = new SqliteClientCatalog({ getDatabase: async () => database });

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
    const catalog = new SqliteClientCatalog({ getDatabase: async () => database });

    await expect(catalog.get("missing-client")).rejects.toMatchObject({
      code: "not-found",
    });
  });

  test("binds normalized data when creating a client", async () => {
    const database = createDatabase();
    const catalog = new SqliteClientCatalog({
      getDatabase: async () => database,
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
    const catalog = new SqliteClientCatalog({ getDatabase: async () => database });

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
      getDatabase: async () => invalidDatabase,
    });
    await expect(invalidCatalog.list("active")).rejects.toMatchObject({
      code: "invalid-data",
    });

    const failingDatabase = createDatabase();
    failingDatabase.select.mockRejectedValueOnce(new Error("database locked"));
    const failingCatalog = new SqliteClientCatalog({
      getDatabase: async () => failingDatabase,
    });
    await expect(failingCatalog.list("active")).rejects.toMatchObject({
      code: "persistence",
    });
  });

  test("rescales project overrides exactly with a client currency change", async () => {
    const database = createDatabase([
      { ...row, currency_code: "JPY", hourly_rate_minor: 125 },
    ]);
    database.select
      .mockResolvedValueOnce([row])
      .mockResolvedValueOnce([{ id: "project-1", hourly_rate_override_minor: 12_500 }])
      .mockResolvedValueOnce([{ ...row, currency_code: "JPY", hourly_rate_minor: 125 }]);
    const catalog = new SqliteClientCatalog({
      getDatabase: async () => database,
      now: () => new Date(now),
    });

    await catalog.update("client-1", {
      name: "Acme",
      currencyCode: "JPY",
      hourlyRateMinor: 125,
    });

    expect(database.execute).toHaveBeenNthCalledWith(1, "BEGIN");
    expect(database.execute).toHaveBeenCalledWith(
      expect.stringContaining("UPDATE projects"),
      [125, "project-1"],
    );
    expect(database.execute).toHaveBeenLastCalledWith("COMMIT");
  });

  test("rejects a lossy currency change before updating the client", async () => {
    const database = createDatabase();
    database.select.mockImplementation((query: string) =>
      Promise.resolve(
        query.includes("FROM projects")
          ? [{ id: "project-1", hourly_rate_override_minor: 12_550 }]
          : [row],
      ),
    );
    const catalog = new SqliteClientCatalog({ getDatabase: async () => database });

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
});
