import {
  normalizeProjectName,
  projectCommandSchema,
  type Project,
  type ProjectCommand,
} from "./project";
import {
  type ProjectCatalog,
  ProjectCatalogError,
  type ProjectList,
} from "./project-catalog";

interface InMemoryProjectCatalogOptions {
  projects?: Project[];
  failure?: ProjectCatalogError;
  now?: () => Date;
  createId?: () => string;
}

export class InMemoryProjectCatalog implements ProjectCatalog {
  private readonly projects: Project[];
  private readonly failure?: ProjectCatalogError;
  private readonly now: () => Date;
  private readonly createId: () => string;

  constructor(options: InMemoryProjectCatalogOptions = {}) {
    this.projects = structuredClone(options.projects ?? []);
    this.failure = options.failure;
    this.now = options.now ?? (() => new Date());
    this.createId = options.createId ?? (() => crypto.randomUUID());
  }

  async list(clientId: string, filter: ProjectList): Promise<Project[]> {
    this.throwConfiguredFailure();
    const archived = filter === "archived";
    return structuredClone(
      this.projects.filter(
        (project) =>
          project.clientId === clientId && (project.archivedAt !== null) === archived,
      ),
    );
  }

  async get(clientId: string, id: string): Promise<Project> {
    this.throwConfiguredFailure();
    const project = this.projects.find(
      (candidate) => candidate.id === id && candidate.clientId === clientId,
    );
    if (!project) {
      throw new ProjectCatalogError("not-found", "Project was not found");
    }
    return structuredClone(project);
  }

  async create(clientId: string, input: ProjectCommand): Promise<Project> {
    this.throwConfiguredFailure();
    const command = projectCommandSchema.parse(input);
    this.assertUniqueName(clientId, command.name);
    const now = this.now().toISOString();
    const project: Project = {
      id: this.createId(),
      clientId,
      ...command,
      createdAt: now,
      updatedAt: now,
      archivedAt: null,
    };
    this.projects.push(project);
    return structuredClone(project);
  }

  async update(
    clientId: string,
    id: string,
    input: ProjectCommand,
  ): Promise<Project> {
    this.throwConfiguredFailure();
    const command = projectCommandSchema.parse(input);
    const project = this.findActiveProject(clientId, id);
    this.assertUniqueName(clientId, command.name, id);
    Object.assign(project, command, { updatedAt: this.now().toISOString() });
    return structuredClone(project);
  }

  async archive(clientId: string, id: string): Promise<void> {
    this.throwConfiguredFailure();
    const project = this.findActiveProject(clientId, id);
    const now = this.now().toISOString();
    project.archivedAt = now;
    project.updatedAt = now;
  }

  private findActiveProject(clientId: string, id: string): Project {
    const project = this.projects.find(
      (candidate) =>
        candidate.id === id &&
        candidate.clientId === clientId &&
        candidate.archivedAt === null,
    );
    if (!project) {
      throw new ProjectCatalogError("not-found", "Project was not found");
    }
    return project;
  }

  private assertUniqueName(clientId: string, name: string, excludedId?: string) {
    const normalizedName = normalizeProjectName(name);
    const duplicate = this.projects.some(
      (project) =>
        project.id !== excludedId &&
        project.clientId === clientId &&
        project.archivedAt === null &&
        normalizeProjectName(project.name) === normalizedName,
    );
    if (duplicate) {
      throw new ProjectCatalogError(
        "duplicate-name",
        "An active project for this client already uses this name",
      );
    }
  }

  private throwConfiguredFailure() {
    if (this.failure) throw this.failure;
  }
}
