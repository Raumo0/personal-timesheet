import Database, { type QueryResult } from "@tauri-apps/plugin-sql";

const DATABASE_URL = "sqlite:personal-timesheet.db";

export interface SqlDatabase {
  execute(query: string, bindValues?: unknown[]): Promise<QueryResult>;
  select(query: string, bindValues?: unknown[]): Promise<unknown[]>;
}

let databasePromise: Promise<Database> | undefined;

export function getClientDatabase(): Promise<SqlDatabase> {
  databasePromise ??= Database.load(DATABASE_URL);
  return databasePromise;
}

export async function checkpointAndCloseClientDatabase(): Promise<void> {
  databasePromise ??= Database.load(DATABASE_URL);
  const database = await databasePromise;
  await database.execute("PRAGMA wal_checkpoint(TRUNCATE)");
  const closed = await database.close();
  if (!closed) throw new Error("SQLite connection could not be closed");
  databasePromise = undefined;
}
