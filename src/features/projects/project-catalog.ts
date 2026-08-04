import type { Project, ProjectCommand } from "./project";

export type ProjectList = "active" | "archived";
export type ProjectCatalogErrorCode =
  | "duplicate-name"
  | "not-found"
  | "persistence"
  | "invalid-data";

export class ProjectCatalogError extends Error {
  public readonly cause?: unknown;

  constructor(
    public readonly code: ProjectCatalogErrorCode,
    message: string,
    cause?: unknown,
  ) {
    super(message);
    this.name = "ProjectCatalogError";
    this.cause = cause;
  }
}

export interface ProjectCatalog {
  list(clientId: string, filter: ProjectList): Promise<Project[]>;
  get(clientId: string, id: string): Promise<Project>;
  create(clientId: string, command: ProjectCommand): Promise<Project>;
  update(clientId: string, id: string, command: ProjectCommand): Promise<Project>;
}
