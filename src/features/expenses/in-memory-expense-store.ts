import type { Client } from "../clients/client";
import type { Project } from "../projects/project";
import {
  createExpenseCommandSchema,
  type Expense,
  type ExpenseCommand,
  type ExpenseTarget,
} from "./expense";
import {
  ExpenseStoreError,
  type ExpenseList,
  type ExpenseStore,
  type ExpenseStoreSeed,
  type ExpenseTargetGroup,
  type ExpenseWorkspaceSnapshot,
} from "./expense-store";

const WORKSPACE_LIMIT = 200;

interface InMemoryExpenseStoreOptions extends ExpenseStoreSeed {
  readonly now?: () => Date;
  readonly createId?: () => string;
}

export class InMemoryExpenseStore implements ExpenseStore {
  private readonly clients: Client[];
  private readonly projects: Project[];
  private readonly expenses: Expense[];
  private readonly failure?: ExpenseStoreError;
  private readonly now: () => Date;
  private readonly createId: () => string;

  constructor(options: InMemoryExpenseStoreOptions) {
    this.clients = structuredClone([...options.clients]);
    this.projects = structuredClone([...options.projects]);
    this.expenses = structuredClone([...options.expenses]);
    this.failure = options.failure;
    this.now = options.now ?? (() => new Date());
    this.createId = options.createId ?? (() => crypto.randomUUID());
  }

  async loadWorkspace(list: ExpenseList): Promise<ExpenseWorkspaceSnapshot> {
    this.throwConfiguredFailure();
    const archived = list === "archived";
    const expenses = this.expenses
      .filter((expense) => (expense.archivedAt !== null) === archived)
      .sort(compareExpenses)
      .slice(0, WORKSPACE_LIMIT);
    return structuredClone({
      expenses,
      targets: this.activeTargets(),
      targetDisplays: expenses.map((expense) => ({
        target: expense.target,
        name: this.targetDisplayName(expense.target),
      })),
    });
  }

  async create(input: ExpenseCommand): Promise<Expense> {
    this.throwConfiguredFailure();
    const command = this.parseCommand(input);
    const client = this.resolveActiveTargetClient(command.target);
    if (command.billingCurrencyCode !== client.currencyCode) {
      throw new ExpenseStoreError("currency-changed");
    }

    const now = this.now().toISOString();
    const expense: Expense = {
      id: this.createId(),
      ...command,
      createdAt: now,
      updatedAt: now,
      archivedAt: null,
    };
    this.expenses.push(expense);
    return structuredClone(expense);
  }

  async update(
    id: string,
    expectedUpdatedAt: string,
    input: ExpenseCommand,
  ): Promise<Expense> {
    this.throwConfiguredFailure();
    const command = this.parseCommand(input);
    const index = this.expenses.findIndex((expense) => expense.id === id);
    if (index < 0) throw new ExpenseStoreError("expense-not-found");
    const current = this.expenses[index];
    if (current.archivedAt !== null) {
      throw new ExpenseStoreError("archived-expense");
    }
    if (current.updatedAt !== expectedUpdatedAt) {
      throw new ExpenseStoreError("stale-expense");
    }

    const client = this.resolveActiveTargetClient(command.target);
    const conversionContextChanged =
      !sameTarget(current.target, command.target) ||
      current.originalCurrencyCode !== command.originalCurrencyCode;
    const expectedBillingCurrency = conversionContextChanged
      ? client.currencyCode
      : current.billingCurrencyCode;
    if (command.billingCurrencyCode !== expectedBillingCurrency) {
      throw new ExpenseStoreError("currency-changed");
    }

    const updated: Expense = {
      ...current,
      ...command,
      updatedAt: this.now().toISOString(),
    };
    this.expenses[index] = updated;
    return structuredClone(updated);
  }

  private parseCommand(input: ExpenseCommand): ExpenseCommand {
    const result = createExpenseCommandSchema.safeParse(input);
    if (!result.success) {
      throw new ExpenseStoreError("invalid-expense", result.error);
    }
    return result.data;
  }

  private resolveActiveTargetClient(target: ExpenseTarget): Client {
    if (target.kind === "client") {
      const client = this.clients.find(
        (candidate) =>
          candidate.id === target.clientId && candidate.archivedAt === null,
      );
      if (!client) throw new ExpenseStoreError("inactive-target");
      return client;
    }

    const project = this.projects.find(
      (candidate) =>
        candidate.id === target.projectId && candidate.archivedAt === null,
    );
    const client = project
      ? this.clients.find(
          (candidate) =>
            candidate.id === project.clientId && candidate.archivedAt === null,
        )
      : undefined;
    if (!client) throw new ExpenseStoreError("inactive-target");
    return client;
  }

  private activeTargets(): ExpenseTargetGroup[] {
    return this.clients
      .filter((client) => client.archivedAt === null)
      .sort(compareNames)
      .map((client) => ({
        client: {
          id: client.id,
          name: client.name,
          currencyCode: client.currencyCode,
        },
        projects: this.projects
          .filter(
            (project) =>
              project.clientId === client.id && project.archivedAt === null,
          )
          .sort(compareNames)
          .map((project) => ({ id: project.id, name: project.name })),
      }));
  }

  private targetDisplayName(target: ExpenseTarget): string {
    if (target.kind === "client") {
      return this.clients.find(({ id }) => id === target.clientId)?.name ?? target.clientId;
    }
    return this.projects.find(({ id }) => id === target.projectId)?.name ?? target.projectId;
  }

  private throwConfiguredFailure(): void {
    if (this.failure) throw this.failure;
  }
}

function sameTarget(left: ExpenseTarget, right: ExpenseTarget): boolean {
  if (left.kind !== right.kind) return false;
  return left.kind === "client"
    ? left.clientId === (right as Extract<ExpenseTarget, { kind: "client" }>).clientId
    : left.projectId ===
        (right as Extract<ExpenseTarget, { kind: "project" }>).projectId;
}

function compareNames(left: { name: string }, right: { name: string }): number {
  return left.name.localeCompare(right.name) ||
    ("id" in left && "id" in right
      ? String(left.id).localeCompare(String(right.id))
      : 0);
}

function compareExpenses(left: Expense, right: Expense): number {
  return (
    right.expenseDate.localeCompare(left.expenseDate) ||
    right.createdAt.localeCompare(left.createdAt) ||
    left.id.localeCompare(right.id)
  );
}
