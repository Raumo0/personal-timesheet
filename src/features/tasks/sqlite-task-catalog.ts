import { ZodError } from "zod";

import { getClientDatabase, type SqlDatabase } from "../clients/database";
import {
  normalizeTaskName,
  taskCommandSchema,
  taskFromRow,
  type Task,
  type TaskCommand,
} from "./task";
import {
  type TaskCatalog,
  TaskCatalogError,
  type TaskList,
} from "./task-catalog";

interface SqliteTaskCatalogOptions {
  getDatabase?: () => Promise<SqlDatabase>;
  createId?: () => string;
  now?: () => Date;
}

const SELECT_COLUMNS = `
  SELECT id, project_id, name, normalized_name, hourly_rate_override_minor,
         created_at, updated_at, archived_at
  FROM tasks
`;

export class SqliteTaskCatalog implements TaskCatalog {
  private readonly getDatabase: () => Promise<SqlDatabase>;
  private readonly createId: () => string;
  private readonly now: () => Date;

  constructor(options: SqliteTaskCatalogOptions = {}) {
    this.getDatabase = options.getDatabase ?? getClientDatabase;
    this.createId = options.createId ?? (() => crypto.randomUUID());
    this.now = options.now ?? (() => new Date());
  }

  async list(projectId: string, filter: TaskList): Promise<Task[]> {
    return this.translateErrors(async () => {
      const database = await this.getDatabase();
      const archiveClause = filter === "active" ? "IS NULL" : "IS NOT NULL";
      const rows = await database.select(
        `${SELECT_COLUMNS} WHERE project_id = $1 AND archived_at ${archiveClause} ORDER BY name COLLATE NOCASE`,
        [projectId],
      );
      return rows.map(taskFromRow);
    });
  }

  async create(projectId: string, input: TaskCommand): Promise<Task> {
    return this.translateErrors(async () => {
      const command = taskCommandSchema.parse(input);
      const id = this.createId();
      const timestamp = this.now().toISOString();
      const database = await this.getDatabase();
      await database.execute(
        `INSERT INTO tasks (
          id, project_id, name, normalized_name, hourly_rate_override_minor,
          created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)`,
        [
          id,
          projectId,
          command.name,
          normalizeTaskName(command.name),
          command.hourlyRateOverrideMinor,
          timestamp,
          timestamp,
        ],
      );
      return {
        id,
        projectId,
        ...command,
        createdAt: timestamp,
        updatedAt: timestamp,
        archivedAt: null,
      };
    });
  }

  async update(
    projectId: string,
    id: string,
    input: TaskCommand,
  ): Promise<Task> {
    return this.translateErrors(async () => {
      const command = taskCommandSchema.parse(input);
      const timestamp = this.now().toISOString();
      const database = await this.getDatabase();
      const result = await database.execute(
        `UPDATE tasks
         SET name = $1, normalized_name = $2,
             hourly_rate_override_minor = $3, updated_at = $4
         WHERE id = $5 AND project_id = $6 AND archived_at IS NULL`,
        [
          command.name,
          normalizeTaskName(command.name),
          command.hourlyRateOverrideMinor,
          timestamp,
          id,
          projectId,
        ],
      );
      if (result.rowsAffected === 0) {
        throw new TaskCatalogError("not-found", "Task was not found");
      }
      const rows = await database.select(
        `${SELECT_COLUMNS} WHERE project_id = $1 AND id = $2 AND archived_at IS NULL`,
        [projectId, id],
      );
      if (rows.length !== 1) {
        throw new TaskCatalogError("not-found", "Task was not found");
      }
      return taskFromRow(rows[0]);
    });
  }

  private async translateErrors<T>(operation: () => Promise<T>): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      if (error instanceof TaskCatalogError) throw error;
      if (error instanceof ZodError) {
        throw new TaskCatalogError(
          "invalid-data",
          "Stored task data is invalid",
          error,
        );
      }
      if (
        error instanceof Error &&
        error.message.includes("tasks.project_id, tasks.normalized_name")
      ) {
        throw new TaskCatalogError(
          "duplicate-name",
          "An active task for this project already uses this name",
          error,
        );
      }
      throw new TaskCatalogError(
        "persistence",
        "Local task data is unavailable",
        error,
      );
    }
  }
}
