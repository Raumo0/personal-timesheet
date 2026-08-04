import {
  normalizeTaskName,
  taskCommandSchema,
  type Task,
  type TaskCommand,
} from "./task";
import {
  type TaskCatalog,
  TaskCatalogError,
  type TaskList,
} from "./task-catalog";

interface InMemoryTaskCatalogOptions {
  tasks?: Task[];
  failure?: TaskCatalogError;
  now?: () => Date;
  createId?: () => string;
}

export class InMemoryTaskCatalog implements TaskCatalog {
  private readonly tasks: Task[];
  private readonly failure?: TaskCatalogError;
  private readonly now: () => Date;
  private readonly createId: () => string;

  constructor(options: InMemoryTaskCatalogOptions = {}) {
    this.tasks = structuredClone(options.tasks ?? []);
    this.failure = options.failure;
    this.now = options.now ?? (() => new Date());
    this.createId = options.createId ?? (() => crypto.randomUUID());
  }

  async list(projectId: string, filter: TaskList): Promise<Task[]> {
    this.throwConfiguredFailure();
    const archived = filter === "archived";
    return structuredClone(
      this.tasks.filter(
        (task) =>
          task.projectId === projectId && (task.archivedAt !== null) === archived,
      ),
    );
  }

  async create(projectId: string, input: TaskCommand): Promise<Task> {
    this.throwConfiguredFailure();
    const command = taskCommandSchema.parse(input);
    this.assertUniqueName(projectId, command.name);
    const now = this.now().toISOString();
    const task: Task = {
      id: this.createId(),
      projectId,
      ...command,
      createdAt: now,
      updatedAt: now,
      archivedAt: null,
    };
    this.tasks.push(task);
    return structuredClone(task);
  }

  async update(
    projectId: string,
    id: string,
    input: TaskCommand,
  ): Promise<Task> {
    this.throwConfiguredFailure();
    const command = taskCommandSchema.parse(input);
    const task = this.findActiveTask(projectId, id);
    this.assertUniqueName(projectId, command.name, id);
    Object.assign(task, command, { updatedAt: this.now().toISOString() });
    return structuredClone(task);
  }

  private findActiveTask(projectId: string, id: string): Task {
    const task = this.tasks.find(
      (candidate) =>
        candidate.id === id &&
        candidate.projectId === projectId &&
        candidate.archivedAt === null,
    );
    if (!task) {
      throw new TaskCatalogError("not-found", "Task was not found");
    }
    return task;
  }

  private assertUniqueName(projectId: string, name: string, excludedId?: string) {
    const normalizedName = normalizeTaskName(name);
    const duplicate = this.tasks.some(
      (task) =>
        task.id !== excludedId &&
        task.projectId === projectId &&
        task.archivedAt === null &&
        normalizeTaskName(task.name) === normalizedName,
    );
    if (duplicate) {
      throw new TaskCatalogError(
        "duplicate-name",
        "An active task for this project already uses this name",
      );
    }
  }

  private throwConfiguredFailure() {
    if (this.failure) throw this.failure;
  }
}
