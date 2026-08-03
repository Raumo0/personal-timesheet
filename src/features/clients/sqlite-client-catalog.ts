import { ZodError } from "zod";

import {
  clientCommandSchema,
  clientFromRow,
  type Client,
  type ClientCommand,
  normalizeClientName,
} from "./client";
import { rescaleProjectRateOverride } from "../projects/project";
import {
  type ClientCatalog,
  ClientCatalogError,
  type ClientList,
} from "./client-catalog";
import { getClientDatabase, type SqlDatabase } from "./database";

interface SqliteClientCatalogOptions {
  getDatabase?: () => Promise<SqlDatabase>;
  createId?: () => string;
  now?: () => Date;
}

const SELECT_COLUMNS = `
  SELECT id, name, normalized_name, currency_code, hourly_rate_minor,
         created_at, updated_at, archived_at
  FROM clients
`;

export class SqliteClientCatalog implements ClientCatalog {
  private readonly getDatabase: () => Promise<SqlDatabase>;
  private readonly createId: () => string;
  private readonly now: () => Date;

  constructor(options: SqliteClientCatalogOptions = {}) {
    this.getDatabase = options.getDatabase ?? getClientDatabase;
    this.createId = options.createId ?? (() => crypto.randomUUID());
    this.now = options.now ?? (() => new Date());
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
      const database = await this.getDatabase();
      await database.execute(
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
      const existingClient = clientFromRow(existingRows[0]);
      const projectRows =
        existingClient.currencyCode === command.currencyCode
          ? []
          : await database.select(
              `SELECT id, hourly_rate_override_minor FROM projects
               WHERE client_id = $1 AND hourly_rate_override_minor IS NOT NULL`,
              [id],
            );
      const rescaledOverrides = projectRows.map((row) => {
        if (
          typeof row !== "object" ||
          row === null ||
          typeof (row as { id?: unknown }).id !== "string" ||
          typeof (row as { hourly_rate_override_minor?: unknown })
            .hourly_rate_override_minor !== "number"
        ) {
          throw new ClientCatalogError("invalid-data", "Stored project data is invalid");
        }
        try {
          return {
            id: (row as { id: string }).id,
            hourlyRateOverrideMinor: rescaleProjectRateOverride(
              (row as { hourly_rate_override_minor: number }).hourly_rate_override_minor,
              existingClient.currencyCode,
              command.currencyCode,
            ),
          };
        } catch (error) {
          throw new ClientCatalogError(
            "invalid-data",
            "Project rates cannot be represented in the new currency",
            error,
          );
        }
      });

      if (rescaledOverrides.length > 0) await database.execute("BEGIN");
      try {
      const result = await database.execute(
        `UPDATE clients
         SET name = $1, normalized_name = $2, currency_code = $3,
             hourly_rate_minor = $4, updated_at = $5
         WHERE id = $6 AND archived_at IS NULL`,
        [
          command.name,
          normalizeClientName(command.name),
          command.currencyCode,
          command.hourlyRateMinor,
          timestamp,
          id,
        ],
      );
      if (result.rowsAffected === 0) {
        throw new ClientCatalogError("not-found", "Client was not found");
      }
      for (const override of rescaledOverrides) {
        await database.execute(
          "UPDATE projects SET hourly_rate_override_minor = $1 WHERE id = $2",
          [override.hourlyRateOverrideMinor, override.id],
        );
      }
      if (rescaledOverrides.length > 0) await database.execute("COMMIT");
      } catch (error) {
        if (rescaledOverrides.length > 0) await database.execute("ROLLBACK");
        throw error;
      }
      const rows = await database.select(
        `${SELECT_COLUMNS} WHERE id = $1 AND archived_at IS NULL`,
        [id],
      );
      if (rows.length !== 1) {
        throw new ClientCatalogError("not-found", "Client was not found");
      }
      return clientFromRow(rows[0]);
    });
  }

  async archive(id: string): Promise<void> {
    return this.translateErrors(async () => {
      const timestamp = this.now().toISOString();
      const database = await this.getDatabase();
      const result = await database.execute(
        `UPDATE clients
         SET archived_at = $1, updated_at = $1
         WHERE id = $2 AND archived_at IS NULL`,
        [timestamp, id],
      );
      if (result.rowsAffected === 0) {
        throw new ClientCatalogError("not-found", "Client was not found");
      }
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
