import Database, { type QueryResult } from "@tauri-apps/plugin-sql";

const DATABASE_URL = "sqlite:personal-timesheet.db";

export interface SqlReadDatabase {
  select(query: string, bindValues?: unknown[]): Promise<unknown[]>;
}

export interface IndependentSqlStatementExecutor {
  execute(statement: string, bindValues?: unknown[]): Promise<QueryResult>;
}

let databasePromise: Promise<Database> | undefined;
let readDatabasePromise: Promise<SqlReadDatabase> | undefined;

function getPluginDatabase(): Promise<Database> {
  databasePromise ??= Database.load(DATABASE_URL);
  return databasePromise;
}

export function getClientDatabase(): Promise<SqlReadDatabase> {
  readDatabasePromise ??= getPluginDatabase().then((database) => ({
    select: (query, bindValues) => database.select(query, bindValues),
  }));
  return readDatabasePromise;
}

const independentExecutor: IndependentSqlStatementExecutor = {
  async execute(statement, bindValues) {
    assertIndependentStatement(statement);
    const database = await getPluginDatabase();
    return database.execute(statement, bindValues);
  },
};

export function getIndependentSqlStatementExecutor(): IndependentSqlStatementExecutor {
  return independentExecutor;
}

export async function checkpointAndCloseClientDatabase(): Promise<void> {
  const database = await getPluginDatabase();
  await database.execute("PRAGMA wal_checkpoint(TRUNCATE)");
  const closed = await database.close();
  if (!closed) throw new Error("SQLite connection could not be closed");
  databasePromise = undefined;
  readDatabasePromise = undefined;
}

function assertIndependentStatement(statement: string): void {
  const sql = stripLeadingTrivia(statement);
  if (sql.length === 0) throw new Error("Independent SQL statement cannot be empty");
  if (sql.includes(";")) {
    throw new Error("Independent SQL executor accepts only one statement");
  }
  const verb = /^([A-Za-z]+)/.exec(sql)?.[1]?.toUpperCase();
  if (
    verb === "BEGIN" ||
    verb === "COMMIT" ||
    verb === "ROLLBACK" ||
    verb === "SAVEPOINT" ||
    verb === "RELEASE" ||
    verb === "END"
  ) {
    throw new Error(`Transaction-control statement ${verb} is not allowed`);
  }
}

function stripLeadingTrivia(statement: string): string {
  let remaining = statement.trimStart();
  while (remaining.length > 0) {
    if (remaining.startsWith("--")) {
      const newline = remaining.indexOf("\n");
      remaining = newline === -1 ? "" : remaining.slice(newline + 1).trimStart();
      continue;
    }
    if (remaining.startsWith("/*")) {
      const end = remaining.indexOf("*/", 2);
      if (end === -1) return "";
      remaining = remaining.slice(end + 2).trimStart();
      continue;
    }
    return remaining.trimEnd();
  }
  return remaining;
}
