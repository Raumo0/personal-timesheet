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
});
