import Database, { type QueryResult } from "@tauri-apps/plugin-sql";

const DATABASE_URL = "sqlite:personal-timesheet.db";

export interface SqlDatabase {
  execute(query: string, bindValues?: unknown[]): Promise<QueryResult>;
  select(query: string, bindValues?: unknown[]): Promise<unknown[]>;
}

let databasePromise: Promise<SqlDatabase> | undefined;

export function getClientDatabase(): Promise<SqlDatabase> {
  databasePromise ??= Database.load(DATABASE_URL);
  return databasePromise;
}
