import type { Client } from "../clients/client";
import type { Project } from "../projects/project";
import type { Task } from "../tasks/task";
import type { Expense } from "../expenses/expense";

export type LifecycleKind = "client" | "project" | "task" | "expense";
export type LifecycleOperation = "archive" | "restore";

export type LifecycleTarget = Readonly<{
  kind: LifecycleKind;
  id: string;
}>;

export interface CatalogHierarchy {
  readonly clients: readonly Client[];
  readonly projects: readonly Project[];
  readonly tasks: readonly Task[];
  readonly expenses?: readonly Expense[];
}

export type LifecycleRecord = Readonly<{
  kind: LifecycleKind;
  id: string;
  name: string;
  archivedAt: string | null;
}>;

export type LifecycleRequest = Readonly<{
  operation: LifecycleOperation;
  target: LifecycleTarget;
}>;

export type LifecyclePlan = Readonly<{
  operation: LifecycleOperation;
  target: LifecycleTarget;
  records: readonly LifecycleRecord[];
  impactDescription: string;
}>;

export interface CatalogLifecycle {
  preview(request: LifecycleRequest): Promise<LifecyclePlan>;
  apply(plan: LifecyclePlan): Promise<void>;
}

export type CatalogLifecycleErrorCode =
  | "not-found"
  | "invalid-state"
  | "invalid-hierarchy"
  | "stale-plan"
  | "persistence";

export class CatalogLifecycleError extends Error {
  public readonly cause?: unknown;

  constructor(
    public readonly code: CatalogLifecycleErrorCode,
    message: string,
    cause?: unknown,
  ) {
    super(message);
    this.name = "CatalogLifecycleError";
    this.cause = cause;
  }
}

export function planCatalogLifecycle(
  hierarchy: CatalogHierarchy,
  request: LifecycleRequest,
): LifecyclePlan {
  return request.operation === "archive"
    ? planArchive(hierarchy, request.target)
    : planRestore(hierarchy, request.target);
}

function planArchive(
  hierarchy: CatalogHierarchy,
  target: LifecycleTarget,
): LifecyclePlan {
  if (target.kind === "client") {
    const client = findClient(hierarchy, target.id);
    requireState(client.archivedAt === null, "Client is already archived");
    const projects = hierarchy.projects.filter(
      (project) => project.clientId === client.id,
    );
    const projectIds = new Set(projects.map((project) => project.id));
    const tasks = hierarchy.tasks.filter((task) => projectIds.has(task.projectId));
    const expenses = expenseRows(hierarchy).filter(
      (expense) =>
        expense.archivedAt === null &&
        ((expense.target.kind === "client" && expense.target.clientId === client.id) ||
          (expense.target.kind === "project" && projectIds.has(expense.target.projectId))),
    );
    const hasExpenses = expenses.length > 0;
    return freezePlan(
      "archive",
      target,
      [clientRecord(client), ...projects.map(projectRecord), ...tasks.map(taskRecord), ...expenses.map(expenseRecord)].filter(
        (record) => record.archivedAt === null,
      ),
      hasExpenses
        ? `Archive ${client.name} and every Project, Task, and Expense beneath it (${projects.length} ${plural(projects.length, "Project")}, ${tasks.length} ${plural(tasks.length, "Task")}, ${expenses.length} ${plural(expenses.length, "Expense")}).`
        : `Archive ${client.name} and every Project and Task beneath it (${projects.length} ${plural(projects.length, "Project")}, ${tasks.length} ${plural(tasks.length, "Task")}).`,
    );
  }

  if (target.kind === "project") {
    const project = findProject(hierarchy, target.id);
    requireProjectClient(hierarchy, project);
    requireState(project.archivedAt === null, "Project is already archived");
    const tasks = hierarchy.tasks.filter((task) => task.projectId === project.id);
    const expenses = expenseRows(hierarchy).filter(
      (expense) =>
        expense.archivedAt === null &&
        expense.target.kind === "project" &&
        expense.target.projectId === project.id,
    );
    return freezePlan(
      "archive",
      target,
      [projectRecord(project), ...tasks.map(taskRecord), ...expenses.map(expenseRecord)].filter(
        (record) => record.archivedAt === null,
      ),
      expenses.length > 0
        ? `Archive ${project.name} and every Task and Expense beneath it (${tasks.length} ${plural(tasks.length, "Task")}, ${expenses.length} ${plural(expenses.length, "Expense")}).`
        : `Archive ${project.name} and every Task beneath it (${tasks.length} ${plural(tasks.length, "Task")}).`,
    );
  }

  if (target.kind === "expense") {
    const expense = findExpense(hierarchy, target.id);
    requireExpenseTarget(hierarchy, expense);
    requireState(expense.archivedAt === null, "Expense is already archived");
    return freezePlan("archive", target, [expenseRecord(expense)], `Archive ${expense.description}.`);
  }

  const task = findTask(hierarchy, target.id);
  const taskProject = requireTaskProject(hierarchy, task);
  requireProjectClient(hierarchy, taskProject);
  requireState(task.archivedAt === null, "Task is already archived");
  return freezePlan(
    "archive",
    target,
    [taskRecord(task)],
    `Archive ${task.name}.`,
  );
}

function planRestore(
  hierarchy: CatalogHierarchy,
  target: LifecycleTarget,
): LifecyclePlan {
  if (target.kind === "client") {
    const client = findClient(hierarchy, target.id);
    requireState(client.archivedAt !== null, "Client is already active");
    return freezePlan(
      "restore",
      target,
      [clientRecord(client)],
      `Restore ${client.name} only. Archived Projects and Tasks remain archived.`,
    );
  }

  if (target.kind === "project") {
    const project = findProject(hierarchy, target.id);
    requireState(project.archivedAt !== null, "Project is already active");
    const client = requireProjectClient(hierarchy, project);
    const records = [
      ...(client.archivedAt === null ? [] : [clientRecord(client)]),
      projectRecord(project),
    ];
    const names = records.map((record) => record.name);
    return freezePlan(
      "restore",
      target,
      records,
      `Restore ${joinNames(names)}${names.length === 1 ? " only" : ""}. Tasks beneath ${project.name} remain archived.`,
    );
  }

  if (target.kind === "expense") {
    const expense = findExpense(hierarchy, target.id);
    requireState(expense.archivedAt !== null, "Expense is already active");
    const records: LifecycleRecord[] = [];
    if (expense.target.kind === "client") {
      const client = findClient(hierarchy, expense.target.clientId);
      if (client.archivedAt !== null) records.push(clientRecord(client));
    } else {
      const project = findProject(hierarchy, expense.target.projectId);
      const client = requireProjectClient(hierarchy, project);
      if (client.archivedAt !== null) records.push(clientRecord(client));
      if (project.archivedAt !== null) records.push(projectRecord(project));
    }
    records.push(expenseRecord(expense));
    return freezePlan(
      "restore",
      target,
      records,
      `Restore ${joinNames(records.map((record) => record.name))}${records.length === 1 ? " only" : ""}. Sibling records remain unchanged.`,
    );
  }

  const task = findTask(hierarchy, target.id);
  requireState(task.archivedAt !== null, "Task is already active");
  const project = requireTaskProject(hierarchy, task);
  const client = requireProjectClient(hierarchy, project);
  const records = [
    ...(client.archivedAt === null ? [] : [clientRecord(client)]),
    ...(project.archivedAt === null ? [] : [projectRecord(project)]),
    taskRecord(task),
  ];
  return freezePlan(
    "restore",
    target,
    records,
    `Restore ${joinNames(records.map((record) => record.name))}${records.length === 1 ? " only" : ""}. Sibling records remain unchanged.`,
  );
}

function findClient(hierarchy: CatalogHierarchy, id: string): Client {
  const client = hierarchy.clients.find((candidate) => candidate.id === id);
  if (!client) throw new CatalogLifecycleError("not-found", "Client was not found");
  return client;
}

function findProject(hierarchy: CatalogHierarchy, id: string): Project {
  const project = hierarchy.projects.find((candidate) => candidate.id === id);
  if (!project) throw new CatalogLifecycleError("not-found", "Project was not found");
  return project;
}

function findTask(hierarchy: CatalogHierarchy, id: string): Task {
  const task = hierarchy.tasks.find((candidate) => candidate.id === id);
  if (!task) throw new CatalogLifecycleError("not-found", "Task was not found");
  return task;
}

function findExpense(hierarchy: CatalogHierarchy, id: string): Expense {
  const expense = expenseRows(hierarchy).find((candidate) => candidate.id === id);
  if (!expense) throw new CatalogLifecycleError("not-found", "Expense was not found");
  return expense;
}

function expenseRows(hierarchy: CatalogHierarchy): readonly Expense[] {
  return hierarchy.expenses ?? [];
}

function requireExpenseTarget(hierarchy: CatalogHierarchy, expense: Expense): void {
  if (expense.target.kind === "client") {
    findClient(hierarchy, expense.target.clientId);
    return;
  }
  const project = findProject(hierarchy, expense.target.projectId);
  requireProjectClient(hierarchy, project);
}

function requireProjectClient(
  hierarchy: CatalogHierarchy,
  project: Project,
): Client {
  const client = hierarchy.clients.find(
    (candidate) => candidate.id === project.clientId,
  );
  if (!client) {
    throw new CatalogLifecycleError(
      "invalid-hierarchy",
      `Project ${project.id} does not belong to an available Client`,
    );
  }
  return client;
}

function requireTaskProject(
  hierarchy: CatalogHierarchy,
  task: Task,
): Project {
  const project = hierarchy.projects.find(
    (candidate) => candidate.id === task.projectId,
  );
  if (!project) {
    throw new CatalogLifecycleError(
      "invalid-hierarchy",
      `Task ${task.id} does not belong to an available Project`,
    );
  }
  return project;
}

function requireState(valid: boolean, message: string): void {
  if (!valid) throw new CatalogLifecycleError("invalid-state", message);
}

function clientRecord(client: Client): LifecycleRecord {
  return {
    kind: "client",
    id: client.id,
    name: client.name,
    archivedAt: client.archivedAt,
  };
}

function projectRecord(project: Project): LifecycleRecord {
  return {
    kind: "project",
    id: project.id,
    name: project.name,
    archivedAt: project.archivedAt,
  };
}

function taskRecord(task: Task): LifecycleRecord {
  return {
    kind: "task",
    id: task.id,
    name: task.name,
    archivedAt: task.archivedAt,
  };
}

function expenseRecord(expense: Expense): LifecycleRecord {
  return {
    kind: "expense",
    id: expense.id,
    name: expense.description,
    archivedAt: expense.archivedAt,
  };
}

function freezePlan(
  operation: LifecycleOperation,
  target: LifecycleTarget,
  records: LifecycleRecord[],
  impactDescription: string,
): LifecyclePlan {
  const frozenTarget = Object.freeze({ ...target });
  const frozenRecords = Object.freeze(
    records.map((record) => Object.freeze({ ...record })),
  );
  return Object.freeze({
    operation,
    target: frozenTarget,
    records: frozenRecords,
    impactDescription,
  });
}

function plural(count: number, singular: string): string {
  return count === 1 ? singular : `${singular}s`;
}

function joinNames(names: string[]): string {
  if (names.length < 2) return names[0] ?? "";
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`;
}
