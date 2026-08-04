import { invoke } from "@tauri-apps/api/core";

import { getClientDatabase, type SqlDatabase } from "../clients/database";
import {
  CatalogLifecycleError,
  planCatalogLifecycle,
  type CatalogHierarchy,
  type CatalogLifecycle,
  type LifecyclePlan,
  type LifecycleRequest,
} from "./catalog-lifecycle";

interface SqliteCatalogLifecycleOptions {
  getDatabase?: () => Promise<SqlDatabase>;
  invoke?: Invoke;
}

type Invoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

type LifecycleTarget = LifecycleRequest["target"];

interface HierarchyQuery {
  clients: string;
  projects?: string;
  tasks?: string;
}

const placeholderTimestamp = "1970-01-01T00:00:00.000Z";

export class SqliteCatalogLifecycle implements CatalogLifecycle {
  private readonly getDatabase: () => Promise<SqlDatabase>;
  private readonly invoke: Invoke;

  constructor(options: SqliteCatalogLifecycleOptions = {}) {
    this.getDatabase = options.getDatabase ?? getClientDatabase;
    this.invoke = options.invoke ?? invoke;
  }

  async preview(request: LifecycleRequest): Promise<LifecyclePlan> {
    const database = await this.openDatabase();
    const hierarchy = await loadHierarchy(database, request.operation, request.target);
    return planCatalogLifecycle(hierarchy, request);
  }

  async apply(plan: LifecyclePlan): Promise<void> {
    try {
      await this.invoke("apply_catalog_lifecycle", {
        plan,
      });
    } catch (cause) {
      if (isStalePlanFailure(cause)) throw stalePlanError();
      throw persistenceError(
        `Lifecycle change was not saved: ${errorMessage(cause)}.`,
        cause,
      );
    }
  }

  private async openDatabase(): Promise<SqlDatabase> {
    try {
      return await this.getDatabase();
    } catch (cause) {
      throw persistenceError("Local catalog data is unavailable", cause);
    }
  }
}

function errorMessage(cause: unknown): string {
  if (cause instanceof Error && cause.message) return cause.message;
  if (typeof cause === "string" && cause) return cause;
  try {
    const serialized = JSON.stringify(cause);
    return serialized && serialized !== "{}"
      ? serialized
      : "Unknown local persistence error";
  } catch {
    return "Unknown local persistence error";
  }
}

async function loadHierarchy(
  database: SqlDatabase,
  operation: LifecycleRequest["operation"],
  target: LifecycleTarget,
): Promise<CatalogHierarchy> {
  const queries = hierarchyQueries(operation, target);
  let clientRows: unknown[];
  let projectRows: unknown[] = [];
  let taskRows: unknown[] = [];
  try {
    clientRows = await database.select(queries.clients, [target.id]);
    if (queries.projects) {
      projectRows = await database.select(queries.projects, [target.id]);
    }
    if (queries.tasks) taskRows = await database.select(queries.tasks, [target.id]);
  } catch (cause) {
    throw persistenceError("Catalog hierarchy could not be loaded", cause);
  }

  try {
    return {
      clients: clientRows.map(clientFromLifecycleRow),
      projects: projectRows.map(projectFromLifecycleRow),
      tasks: taskRows.map(taskFromLifecycleRow),
    };
  } catch (cause) {
    throw new CatalogLifecycleError(
      "invalid-hierarchy",
      "Catalog hierarchy contains invalid local data",
      cause,
    );
  }
}

function hierarchyQueries(
  operation: LifecycleRequest["operation"],
  target: LifecycleTarget,
): HierarchyQuery {
  if (target.kind === "client") {
    return {
      clients: `SELECT id, name, archived_at FROM clients WHERE id = $1 ORDER BY id`,
      projects:
        operation === "archive"
          ? `SELECT id, client_id, name, archived_at FROM projects WHERE client_id = $1 ORDER BY id`
          : undefined,
      tasks:
        operation === "archive"
          ? `SELECT id, project_id, name, archived_at FROM tasks WHERE project_id IN (SELECT id FROM projects WHERE client_id = $1) ORDER BY id`
          : undefined,
    };
  }
  if (target.kind === "project") {
    return {
      clients: `SELECT clients.id, clients.name, clients.archived_at FROM clients JOIN projects ON projects.client_id = clients.id WHERE projects.id = $1 ORDER BY clients.id`,
      projects: `SELECT id, client_id, name, archived_at FROM projects WHERE id = $1 ORDER BY id`,
      tasks:
        operation === "archive"
          ? `SELECT id, project_id, name, archived_at FROM tasks WHERE project_id = $1 ORDER BY id`
          : undefined,
    };
  }
  return {
    clients: `SELECT clients.id, clients.name, clients.archived_at FROM clients JOIN projects ON projects.client_id = clients.id JOIN tasks ON tasks.project_id = projects.id WHERE tasks.id = $1 ORDER BY clients.id`,
    projects: `SELECT projects.id, projects.client_id, projects.name, projects.archived_at FROM projects JOIN tasks ON tasks.project_id = projects.id WHERE tasks.id = $1 ORDER BY projects.id`,
    tasks: `SELECT id, project_id, name, archived_at FROM tasks WHERE id = $1 ORDER BY id`,
  };
}

function clientFromLifecycleRow(row: unknown): CatalogHierarchy["clients"][number] {
  const value = lifecycleRow(row);
  return {
    id: requiredString(value, "id"),
    name: requiredString(value, "name"),
    currencyCode: "EUR",
    hourlyRateMinor: null,
    createdAt: placeholderTimestamp,
    updatedAt: placeholderTimestamp,
    archivedAt: nullableString(value, "archived_at"),
  };
}

function projectFromLifecycleRow(row: unknown): CatalogHierarchy["projects"][number] {
  const value = lifecycleRow(row);
  return {
    id: requiredString(value, "id"),
    clientId: requiredString(value, "client_id"),
    name: requiredString(value, "name"),
    hourlyRateOverrideMinor: null,
    createdAt: placeholderTimestamp,
    updatedAt: placeholderTimestamp,
    archivedAt: nullableString(value, "archived_at"),
  };
}

function taskFromLifecycleRow(row: unknown): CatalogHierarchy["tasks"][number] {
  const value = lifecycleRow(row);
  return {
    id: requiredString(value, "id"),
    projectId: requiredString(value, "project_id"),
    name: requiredString(value, "name"),
    hourlyRateOverrideMinor: null,
    createdAt: placeholderTimestamp,
    updatedAt: placeholderTimestamp,
    archivedAt: nullableString(value, "archived_at"),
  };
}

function lifecycleRow(row: unknown): Record<string, unknown> {
  if (typeof row !== "object" || row === null || Array.isArray(row)) {
    throw new TypeError("Lifecycle row must be an object");
  }
  return row as Record<string, unknown>;
}

function requiredString(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  if (typeof value !== "string") throw new TypeError(`${key} must be a string`);
  return value;
}

function nullableString(row: Record<string, unknown>, key: string): string | null {
  const value = row[key];
  if (value !== null && typeof value !== "string") {
    throw new TypeError(`${key} must be a string or null`);
  }
  return value;
}

function stalePlanError(): CatalogLifecycleError {
  return new CatalogLifecycleError(
    "stale-plan",
    "Lifecycle plan is stale; preview the current hierarchy and try again",
  );
}

function isStalePlanFailure(cause: unknown): boolean {
  return errorMessage(cause).startsWith("stale-plan:");
}

function persistenceError(message: string, cause: unknown): CatalogLifecycleError {
  return new CatalogLifecycleError("persistence", message, cause);
}
