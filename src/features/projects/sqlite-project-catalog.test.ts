import { expect, test, vi } from "vitest";

import type { SqlDatabase } from "../clients/database";
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
  } satisfies SqlDatabase;
}

test("persists an inherited null override and scopes active project queries to a client", async () => {
  const database = createDatabase([row]);
  const catalog = new SqliteProjectCatalog({
    getDatabase: async () => database,
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

test("preserves an explicit zero override and maps persistence failures", async () => {
  const database = createDatabase([{ ...row, hourly_rate_override_minor: 0 }]);
  const catalog = new SqliteProjectCatalog({ getDatabase: async () => database });
  await expect(catalog.list("client-1", "active")).resolves.toMatchObject([
    { hourlyRateOverrideMinor: 0 },
  ]);

  database.select.mockRejectedValueOnce(new Error("database locked"));
  await expect(catalog.list("client-1", "active")).rejects.toMatchObject({
    code: "persistence",
  });
});
