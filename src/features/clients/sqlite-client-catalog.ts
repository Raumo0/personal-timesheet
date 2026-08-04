import { invoke } from "@tauri-apps/api/core";
import { ZodError } from "zod";

import {
  getClientDatabase,
  getIndependentSqlStatementExecutor,
  type IndependentSqlStatementExecutor,
  type SqlReadDatabase,
} from "@/infrastructure/sqlite/plugin-sql-adapter";

import {
  clientCommandSchema,
  clientFromRow,
  type Client,
  type ClientCommand,
  normalizeClientName,
} from "./client";
import {
  type ClientCatalog,
  ClientCatalogError,
  type ClientList,
} from "./client-catalog";
import {
  buildClientUpdatePlan,
  type ClientUpdatePlan,
  type ClientUpdatePlanClient,
} from "./client-update-plan";
interface SqliteClientCatalogOptions {
  getDatabase?: () => Promise<SqlReadDatabase>;
  statementExecutor?: IndependentSqlStatementExecutor;
  createId?: () => string;
  now?: () => Date;
  invoke?: Invoke;
}

type Invoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

const SELECT_COLUMNS = `
  SELECT id, name, normalized_name, currency_code, hourly_rate_minor,
         created_at, updated_at, archived_at
  FROM clients
`;

export class SqliteClientCatalog implements ClientCatalog {
  private readonly getDatabase: () => Promise<SqlReadDatabase>;
  private readonly statementExecutor: IndependentSqlStatementExecutor;
  private readonly createId: () => string;
  private readonly now: () => Date;
  private readonly invoke: Invoke;

  constructor(options: SqliteClientCatalogOptions = {}) {
    this.getDatabase = options.getDatabase ?? getClientDatabase;
    this.statementExecutor =
      options.statementExecutor ?? getIndependentSqlStatementExecutor();
    this.createId = options.createId ?? (() => crypto.randomUUID());
    this.now = options.now ?? (() => new Date());
    this.invoke = options.invoke ?? invoke;
  }

  async list(filter: ClientList): Promise<Client[]> {
    return this.translateErrors(async () => {
      const database = await this.getDatabase();
      const archiveClause =
        filter === "active"
          ? "WHERE archived_at IS NULL"
          : "WHERE archived_at IS NOT NULL";
      const rows = await database.select(
        `${SELECT_COLUMNS} ${archiveClause} ORDER BY name COLLATE NOCASE`,
      );
      return rows.map(clientFromRow);
    });
  }

  async get(id: string): Promise<Client> {
    return this.translateErrors(async () => {
      const database = await this.getDatabase();
      const rows = await database.select(`${SELECT_COLUMNS} WHERE id = $1`, [id]);
      if (rows.length !== 1) {
        throw new ClientCatalogError("not-found", "Client was not found");
      }
      return clientFromRow(rows[0]);
    });
  }

  async create(input: ClientCommand): Promise<Client> {
    return this.translateErrors(async () => {
      const command = clientCommandSchema.parse(input);
      const id = this.createId();
      const timestamp = this.now().toISOString();
      await this.statementExecutor.execute(
        `INSERT INTO clients (
          id, name, normalized_name, currency_code, hourly_rate_minor,
          created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)`,
        [
          id,
          command.name,
          normalizeClientName(command.name),
          command.currencyCode,
          command.hourlyRateMinor,
          timestamp,
          timestamp,
        ],
      );
      return {
        id,
        ...command,
        createdAt: timestamp,
        updatedAt: timestamp,
        archivedAt: null,
      };
    });
  }

  async update(id: string, input: ClientCommand): Promise<Client> {
    return this.translateErrors(async () => {
      const command = clientCommandSchema.parse(input);
      const timestamp = this.now().toISOString();
      const database = await this.getDatabase();
      const existingRows = await database.select(
        `${SELECT_COLUMNS} WHERE id = $1 AND archived_at IS NULL`,
        [id],
      );
      if (existingRows.length !== 1) {
        throw new ClientCatalogError("not-found", "Client was not found");
      }
      const projectRows = await database.select(
        `SELECT id, hourly_rate_override_minor, updated_at FROM projects
         WHERE client_id = $1 AND archived_at IS NULL
           AND hourly_rate_override_minor IS NOT NULL
         ORDER BY id`,
        [id],
      );
      const taskRows = await database.select(
        `SELECT tasks.id, tasks.hourly_rate_override_minor, tasks.updated_at
         FROM tasks
         JOIN projects ON projects.id = tasks.project_id
         WHERE projects.client_id = $1
           AND projects.archived_at IS NULL
           AND tasks.archived_at IS NULL
           AND tasks.hourly_rate_override_minor IS NOT NULL
         ORDER BY tasks.id`,
        [id],
      );
      let plan: ClientUpdatePlan;
      try {
        plan = buildClientUpdatePlan({
          clientRow: existingRows[0],
          command,
          projectRows,
          taskRows,
          updatedAt: timestamp,
        });
      } catch (error) {
        if (error instanceof ZodError) throw error;
        throw new ClientCatalogError(
          "invalid-data",
          "Descendant rates cannot be represented in the new currency",
          error,
        );
      }
      return this.invoke<ClientUpdatePlanClient>("apply_client_update", { plan });
    });
  }

  private async translateErrors<T>(operation: () => Promise<T>): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      if (error instanceof ClientCatalogError) throw error;
      if (error instanceof ZodError) {
        throw new ClientCatalogError(
          "invalid-data",
          "Stored client data is invalid",
          error,
        );
      }
      const nativeMessage = errorMessage(error);
      if (nativeMessage.startsWith("duplicate:")) {
        throw new ClientCatalogError(
          "duplicate-name",
          "An active client already uses this name",
          error,
        );
      }
      if (nativeMessage.startsWith("missing:")) {
        throw new ClientCatalogError("not-found", "Client was not found", error);
      }
      if (nativeMessage.startsWith("invalid-data:")) {
        throw new ClientCatalogError(
          "invalid-data",
          "Stored client data is invalid",
          error,
        );
      }
      if (
        error instanceof Error &&
        error.message.includes("clients.normalized_name")
      ) {
        throw new ClientCatalogError(
          "duplicate-name",
          "An active client already uses this name",
          error,
        );
      }
      throw new ClientCatalogError(
        "persistence",
        "Local client data is unavailable",
        error,
      );
    }
  }
}

function errorMessage(error: unknown): string {
  if (typeof error === "string") return error;
  if (error instanceof Error) return error.message;
  return "";
}
