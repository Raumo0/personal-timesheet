import { ZodError } from "zod";

import { getClientDatabase, type SqlDatabase } from "../clients/database";
import {
  normalizeProjectName,
  projectCommandSchema,
  projectFromRow,
  type Project,
  type ProjectCommand,
} from "./project";
import {
  type ProjectCatalog,
  ProjectCatalogError,
  type ProjectList,
} from "./project-catalog";

interface SqliteProjectCatalogOptions {
  getDatabase?: () => Promise<SqlDatabase>;
  createId?: () => string;
  now?: () => Date;
}

const SELECT_COLUMNS = `
  SELECT id, client_id, name, normalized_name, hourly_rate_override_minor,
         created_at, updated_at, archived_at
  FROM projects
`;

export class SqliteProjectCatalog implements ProjectCatalog {
  private readonly getDatabase: () => Promise<SqlDatabase>;
  private readonly createId: () => string;
  private readonly now: () => Date;

  constructor(options: SqliteProjectCatalogOptions = {}) {
    this.getDatabase = options.getDatabase ?? getClientDatabase;
    this.createId = options.createId ?? (() => crypto.randomUUID());
    this.now = options.now ?? (() => new Date());
  }

  async list(clientId: string, filter: ProjectList): Promise<Project[]> {
    return this.translateErrors(async () => {
      const database = await this.getDatabase();
      const archiveClause = filter === "active" ? "IS NULL" : "IS NOT NULL";
      const rows = await database.select(
        `${SELECT_COLUMNS} WHERE client_id = $1 AND archived_at ${archiveClause} ORDER BY name COLLATE NOCASE`,
        [clientId],
      );
      return rows.map(projectFromRow);
    });
  }

  async get(clientId: string, id: string): Promise<Project> {
    return this.translateErrors(async () => {
      const database = await this.getDatabase();
      const rows = await database.select(
        `${SELECT_COLUMNS} WHERE id = $1 AND client_id = $2`,
        [id, clientId],
      );
      if (rows.length !== 1) {
        throw new ProjectCatalogError("not-found", "Project was not found");
      }
      return projectFromRow(rows[0]);
    });
  }

  async create(clientId: string, input: ProjectCommand): Promise<Project> {
    return this.translateErrors(async () => {
      const command = projectCommandSchema.parse(input);
      const id = this.createId();
      const timestamp = this.now().toISOString();
      const database = await this.getDatabase();
      await database.execute(
        `INSERT INTO projects (
          id, client_id, name, normalized_name, hourly_rate_override_minor,
          created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)`,
        [id, clientId, command.name, normalizeProjectName(command.name), command.hourlyRateOverrideMinor, timestamp, timestamp],
      );
      return { id, clientId, ...command, createdAt: timestamp, updatedAt: timestamp, archivedAt: null };
    });
  }

  async update(clientId: string, id: string, input: ProjectCommand): Promise<Project> {
    return this.translateErrors(async () => {
      const command = projectCommandSchema.parse(input);
      const timestamp = this.now().toISOString();
      const database = await this.getDatabase();
      const result = await database.execute(
        `UPDATE projects SET name = $1, normalized_name = $2, hourly_rate_override_minor = $3, updated_at = $4 WHERE id = $5 AND client_id = $6 AND archived_at IS NULL`,
        [command.name, normalizeProjectName(command.name), command.hourlyRateOverrideMinor, timestamp, id, clientId],
      );
      if (result.rowsAffected === 0) throw new ProjectCatalogError("not-found", "Project was not found");
      const rows = await database.select(`${SELECT_COLUMNS} WHERE id = $1 AND client_id = $2 AND archived_at IS NULL`, [id, clientId]);
      if (rows.length !== 1) throw new ProjectCatalogError("not-found", "Project was not found");
      return projectFromRow(rows[0]);
    });
  }

  async archive(clientId: string, id: string): Promise<void> {
    return this.translateErrors(async () => {
      const database = await this.getDatabase();
      const timestamp = this.now().toISOString();
      const result = await database.execute(
        `UPDATE projects SET archived_at = $1, updated_at = $1 WHERE id = $2 AND client_id = $3 AND archived_at IS NULL`,
        [timestamp, id, clientId],
      );
      if (result.rowsAffected === 0) throw new ProjectCatalogError("not-found", "Project was not found");
    });
  }

  private async translateErrors<T>(operation: () => Promise<T>): Promise<T> {
    try { return await operation(); } catch (error) {
      if (error instanceof ProjectCatalogError) throw error;
      if (error instanceof ZodError) throw new ProjectCatalogError("invalid-data", "Stored project data is invalid", error);
      if (error instanceof Error && error.message.includes("projects.client_id, projects.normalized_name")) {
        throw new ProjectCatalogError("duplicate-name", "An active project for this client already uses this name", error);
      }
      throw new ProjectCatalogError("persistence", "Local project data is unavailable", error);
    }
  }
}
