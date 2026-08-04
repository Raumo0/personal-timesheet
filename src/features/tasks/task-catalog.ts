import type { Task, TaskCommand } from "./task";

export type TaskList = "active" | "archived";
export type TaskCatalogErrorCode =
  | "duplicate-name"
  | "not-found"
  | "persistence"
  | "invalid-data";

export class TaskCatalogError extends Error {
  public readonly cause?: unknown;

  constructor(
    public readonly code: TaskCatalogErrorCode,
    message: string,
    cause?: unknown,
  ) {
    super(message);
    this.name = "TaskCatalogError";
    this.cause = cause;
  }
}

export interface TaskCatalog {
  list(projectId: string, filter: TaskList): Promise<Task[]>;
  create(projectId: string, command: TaskCommand): Promise<Task>;
  update(projectId: string, id: string, command: TaskCommand): Promise<Task>;
}
