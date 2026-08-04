import { afterEach, describe, expect, expectTypeOf, test, vi } from "vitest";

const plugin = vi.hoisted(() => {
  const database = {
    close: vi.fn<() => Promise<boolean>>().mockResolvedValue(true),
    execute: vi
      .fn<(query: string, bindValues?: unknown[]) => Promise<unknown>>()
      .mockResolvedValue({ rowsAffected: 1 }),
    select: vi
      .fn<(query: string, bindValues?: unknown[]) => Promise<unknown[]>>()
      .mockResolvedValue([{ id: "client-1" }]),
  };

  return {
    database,
    load: vi.fn().mockResolvedValue(database),
  };
});

vi.mock("@tauri-apps/plugin-sql", () => ({
  default: { load: plugin.load },
}));

import {
  checkpointAndCloseClientDatabase,
  getClientDatabase,
  getIndependentSqlStatementExecutor,
  type SqlReadDatabase,
} from "./plugin-sql-adapter";

afterEach(async () => {
  if (plugin.load.mock.calls.length > plugin.database.close.mock.calls.length) {
    plugin.database.close.mockResolvedValueOnce(true);
    await checkpointAndCloseClientDatabase();
  }
  vi.clearAllMocks();
  plugin.database.close.mockResolvedValue(true);
  plugin.database.execute.mockResolvedValue({ rowsAffected: 1 });
  plugin.database.select.mockResolvedValue([{ id: "client-1" }]);
});

describe("plugin SQL adapter", () => {
  test("exposes select without the plugin execute capability", async () => {
    expectTypeOf<SqlReadDatabase>().toHaveProperty("select");
    expectTypeOf<SqlReadDatabase>().not.toHaveProperty("execute");

    const database = await getClientDatabase();

    expect("execute" in database).toBe(false);
    await expect(database.select("SELECT id FROM clients WHERE id = $1", ["client-1"]))
      .resolves.toEqual([{ id: "client-1" }]);
  });

  test("reuses one loaded database until checkpoint and close", async () => {
    const first = await getClientDatabase();
    const second = await getClientDatabase();

    expect(second).toBe(first);
    expect(plugin.load).toHaveBeenCalledTimes(1);

    await checkpointAndCloseClientDatabase();

    expect(plugin.database.execute).toHaveBeenCalledWith(
      "PRAGMA wal_checkpoint(TRUNCATE)",
    );
    expect(plugin.database.close).toHaveBeenCalledTimes(1);

    await getClientDatabase();
    expect(plugin.load).toHaveBeenCalledTimes(2);
  });

  test("rejects a failed close and retains the database for retry", async () => {
    await getClientDatabase();
    plugin.database.close.mockResolvedValueOnce(false);

    await expect(checkpointAndCloseClientDatabase()).rejects.toThrow(
      "SQLite connection could not be closed",
    );
    await getClientDatabase();

    expect(plugin.load).toHaveBeenCalledTimes(1);

    await expect(checkpointAndCloseClientDatabase()).resolves.toBeUndefined();
    expect(plugin.database.close).toHaveBeenCalledTimes(2);
  });

  test("executes one bound independent statement", async () => {
    plugin.database.execute.mockResolvedValueOnce({
      lastInsertId: 7,
      rowsAffected: 1,
    });
    const executor = getIndependentSqlStatementExecutor();

    await expect(
      executor.execute("UPDATE clients SET name = $1 WHERE id = $2", [
        "Acme GmbH",
        "client-1",
      ]),
    ).resolves.toEqual({ lastInsertId: 7, rowsAffected: 1 });
    expect(plugin.database.execute).toHaveBeenCalledWith(
      "UPDATE clients SET name = $1 WHERE id = $2",
      ["Acme GmbH", "client-1"],
    );
  });

  test.each([
    ["empty input", ""],
    ["whitespace-only input", "  \n\t "],
    ["multiple statements", "UPDATE clients SET name = 'A'; DELETE FROM clients"],
    [
      "dynamically assembled multiple statements",
      ["UPDATE clients SET name = 'A'", "DELETE FROM clients"].join("; "),
    ],
    ["BEGIN", "BEGIN IMMEDIATE"],
    ["lowercase BEGIN with leading whitespace", "  \n begin transaction"],
    ["COMMIT", "COMMIT TRANSACTION"],
    ["mixed-case COMMIT", "CoMmIt"],
    ["ROLLBACK", "ROLLBACK TO savepoint_name"],
    ["block-comment-prefixed ROLLBACK", "/* retry write */ ROLLBACK"],
    ["SAVEPOINT", "SAVEPOINT update_client"],
    ["line-comment-prefixed SAVEPOINT", "-- nested write\nSAVEPOINT update_client"],
    ["RELEASE", "RELEASE SAVEPOINT update_client"],
    ["mixed-case RELEASE after a block comment", "/* done */ ReLeAsE update_client"],
    ["transactional END", "END TRANSACTION"],
    ["bare transactional END", "END"],
    ["lowercase END alias after a line comment", "-- commit alias\n end"],
  ])("rejects %s before invoking the plugin", async (_name, statement) => {
    const executor = getIndependentSqlStatementExecutor();

    await expect(executor.execute(statement)).rejects.toBeInstanceOf(Error);
    expect(plugin.database.execute).not.toHaveBeenCalled();
  });
});
