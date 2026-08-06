import { invoke } from "@tauri-apps/api/core";

import {
  getClientDatabase,
  type SqlReadDatabase,
} from "@/infrastructure/sqlite/plugin-sql-adapter";

import {
  createExpenseCommandSchema,
  expenseFromRow,
  type Expense,
  type ExpenseCommand,
  type ExpenseTarget,
} from "./expense";
import {
  freezeExpenseMutationPlan,
  type ExpenseMutationExpectedTarget,
  type ExpenseMutationPlan,
} from "./expense-mutation-plan";
import {
  ExpenseStoreError,
  type ExpenseList,
  type ExpenseStore,
  type ExpenseTargetGroup,
  type ExpenseWorkspaceSnapshot,
} from "./expense-store";

type Invoke = (command: string, args?: Record<string, unknown>) => Promise<unknown>;

interface Options {
  getDatabase?: () => Promise<SqlReadDatabase>;
  invoke?: Invoke;
  createId?: () => string;
  now?: () => Date;
}

const WORKSPACE_QUERY = `/* expenses:workspace */
SELECT expenses.id, expenses.client_id, expenses.project_id,
       expenses.expense_date, expenses.description,
       expenses.original_currency_code, expenses.original_amount_minor,
       expenses.billing_currency_code, expenses.billing_amount_minor,
       expenses.applied_rate, expenses.rate_source, expenses.rate_observed_on,
       expenses.rate_manually_adjusted, expenses.created_at,
       expenses.updated_at, expenses.archived_at,
       clients.name AS client_name, projects.name AS project_name
FROM expenses
LEFT JOIN projects ON projects.id = expenses.project_id
JOIN clients ON clients.id = COALESCE(expenses.client_id, projects.client_id)
WHERE ($1 = 'archived') = (expenses.archived_at IS NOT NULL)
ORDER BY expenses.expense_date DESC, expenses.created_at DESC, expenses.id
LIMIT 200`;

const TARGETS_QUERY = `/* expenses:targets */
SELECT clients.id AS client_id, clients.name AS client_name,
       clients.currency_code, projects.id AS project_id, projects.name AS project_name
FROM clients
LEFT JOIN projects ON projects.client_id = clients.id AND projects.archived_at IS NULL
WHERE clients.archived_at IS NULL
ORDER BY clients.name COLLATE NOCASE, clients.id,
         projects.name COLLATE NOCASE, projects.id`;

const TARGET_QUERY = `/* expenses:target */
SELECT clients.id AS client_id, clients.currency_code AS client_currency_code,
       clients.updated_at AS client_updated_at, clients.archived_at AS client_archived_at,
       projects.id AS project_id, projects.updated_at AS project_updated_at,
       projects.archived_at AS project_archived_at
FROM clients
LEFT JOIN projects ON projects.client_id = clients.id AND projects.id = CASE WHEN $1 = 'project' THEN $2 END
WHERE ($1 = 'client' AND clients.id = $2) OR ($1 = 'project' AND projects.id = $2)
LIMIT 1`;

const EXPECTED_QUERY = `/* expenses:expected */
SELECT id, client_id, project_id, expense_date, description,
       original_currency_code, original_amount_minor, billing_currency_code,
       billing_amount_minor, applied_rate, rate_source, rate_observed_on,
       rate_manually_adjusted, created_at, updated_at, archived_at
FROM expenses WHERE id = $1 LIMIT 1`;

export class SqliteExpenseStore implements ExpenseStore {
  private readonly getDatabase: () => Promise<SqlReadDatabase>;
  private readonly invoke: Invoke;
  private readonly createId: () => string;
  private readonly now: () => Date;

  constructor(options: Options = {}) {
    this.getDatabase = options.getDatabase ?? getClientDatabase;
    this.invoke = options.invoke ?? invoke;
    this.createId = options.createId ?? (() => crypto.randomUUID());
    this.now = options.now ?? (() => new Date());
  }

  async loadWorkspace(list: ExpenseList): Promise<ExpenseWorkspaceSnapshot> {
    try {
      const database = await this.database();
      const [expenseRows, targetRows] = await Promise.all([
        database.select(WORKSPACE_QUERY, [list]),
        database.select(TARGETS_QUERY),
      ]);
      return {
        expenses: expenseRows.map(expenseFromDatabaseRow),
        targets: targetGroups(targetRows),
        targetDisplays: expenseRows.map(targetDisplayFromDatabaseRow),
      };
    } catch (cause) {
      if (cause instanceof ExpenseStoreError) throw cause;
      throw persistence(cause);
    }
  }

  async create(input: ExpenseCommand): Promise<Expense> {
    const command = this.command(input);
    const expectedTarget = await this.target(command.target);
    if (command.billingCurrencyCode !== expectedTarget.clientCurrencyCode) {
      throw new ExpenseStoreError("currency-changed");
    }
    return this.apply(freezeExpenseMutationPlan({
      operation: "create",
      expenseId: this.createId(),
      appliedAt: this.now().toISOString(),
      command,
      expectedTarget,
      expectedExpenseUpdatedAt: null,
      expectedExpenseArchivedAt: null,
      expectedExpenseTarget: null,
      expectedOriginalCurrencyCode: null,
      expectedBillingCurrencyCode: null,
    }));
  }

  async update(
    id: string,
    expectedUpdatedAt: string,
    input: ExpenseCommand,
  ): Promise<Expense> {
    const command = this.command(input);
    const current = await this.expense(id);
    if (current.archivedAt !== null) throw new ExpenseStoreError("archived-expense");
    if (current.updatedAt !== expectedUpdatedAt) {
      throw new ExpenseStoreError("stale-expense");
    }
    const expectedTarget = await this.target(command.target);
    const changed =
      !sameTarget(current.target, command.target) ||
      current.originalCurrencyCode !== command.originalCurrencyCode;
    const currency = changed
      ? expectedTarget.clientCurrencyCode
      : current.billingCurrencyCode;
    if (command.billingCurrencyCode !== currency) {
      throw new ExpenseStoreError("currency-changed");
    }
    return this.apply(freezeExpenseMutationPlan({
      operation: "update",
      expenseId: id,
      appliedAt: this.now().toISOString(),
      command,
      expectedTarget,
      expectedExpenseUpdatedAt: current.updatedAt,
      expectedExpenseArchivedAt: current.archivedAt,
      expectedExpenseTarget: current.target,
      expectedOriginalCurrencyCode: current.originalCurrencyCode,
      expectedBillingCurrencyCode: current.billingCurrencyCode,
    }));
  }

  private command(input: ExpenseCommand): ExpenseCommand {
    const result = createExpenseCommandSchema.safeParse(input);
    if (!result.success) throw new ExpenseStoreError("invalid-expense", result.error);
    return result.data;
  }

  private async database(): Promise<SqlReadDatabase> {
    try {
      return await this.getDatabase();
    } catch (cause) {
      throw persistence(cause);
    }
  }

  private async target(target: ExpenseTarget): Promise<ExpenseMutationExpectedTarget> {
    try {
      const database = await this.database();
      const id = target.kind === "client" ? target.clientId : target.projectId;
      const rows = await database.select(TARGET_QUERY, [target.kind, id]);
      if (rows.length !== 1) throw new ExpenseStoreError("inactive-target");
      const row = objectRow(rows[0]);
      const expected = {
        clientId: string(row, "client_id"),
        clientCurrencyCode: string(row, "client_currency_code"),
        clientUpdatedAt: string(row, "client_updated_at"),
        clientArchivedAt: nullableString(row, "client_archived_at"),
        projectId: nullableString(row, "project_id"),
        projectUpdatedAt: nullableString(row, "project_updated_at"),
        projectArchivedAt: nullableString(row, "project_archived_at"),
      };
      if (expected.clientArchivedAt || expected.projectArchivedAt) {
        throw new ExpenseStoreError("inactive-target");
      }
      return expected;
    } catch (cause) {
      if (cause instanceof ExpenseStoreError) throw cause;
      throw persistence(cause);
    }
  }

  private async expense(id: string): Promise<Expense> {
    try {
      const database = await this.database();
      const rows = await database.select(EXPECTED_QUERY, [id]);
      if (rows.length !== 1) throw new ExpenseStoreError("expense-not-found");
      return expenseFromDatabaseRow(rows[0]);
    } catch (cause) {
      if (cause instanceof ExpenseStoreError) throw cause;
      throw persistence(cause);
    }
  }

  private async apply(plan: ExpenseMutationPlan): Promise<Expense> {
    try {
      return returnedExpense(await this.invoke("apply_expense_mutation", { plan }));
    } catch (cause) {
      if (cause instanceof ExpenseStoreError) throw cause;
      const prefix = errorMessage(cause).split(":", 1)[0];
      const codes = [
        "inactive-target", "currency-changed", "expense-not-found",
        "archived-expense", "invalid-expense",
      ] as const;
      if (prefix === "stale-plan") throw new ExpenseStoreError("stale-expense", cause);
      if (codes.includes(prefix as (typeof codes)[number])) {
        throw new ExpenseStoreError(prefix as (typeof codes)[number], cause);
      }
      throw persistence(cause);
    }
  }
}

function expenseFromDatabaseRow(value: unknown): Expense {
  const row = objectRow(value);
  return structuredClone(expenseFromRow({
    ...row,
    rate_manually_adjusted:
      row.rate_manually_adjusted === 0 ? false : row.rate_manually_adjusted,
  }));
}

function targetDisplayFromDatabaseRow(value: unknown) {
  const row = objectRow(value);
  const projectId = nullableString(row, "project_id");
  return projectId
    ? {
        target: { kind: "project" as const, projectId },
        name: string(row, "project_name"),
      }
    : {
        target: { kind: "client" as const, clientId: string(row, "client_id") },
        name: string(row, "client_name"),
      };
}

function returnedExpense(value: unknown): Expense {
  const row = objectRow(value);
  const target = objectRow(row.target);
  const command = createExpenseCommandSchema.parse({
    target,
    expenseDate: row.expenseDate,
    description: row.description,
    originalCurrencyCode: row.originalCurrencyCode,
    originalAmountMinor: row.originalAmountMinor,
    billingCurrencyCode: row.billingCurrencyCode,
    billingAmountMinor: row.billingAmountMinor,
    appliedRate: row.appliedRate,
    rateSource: row.rateSource,
    rateObservedOn: row.rateObservedOn,
    rateManuallyAdjusted: row.rateManuallyAdjusted,
  });
  return structuredClone({
    id: string(row, "id"),
    ...command,
    createdAt: string(row, "createdAt"),
    updatedAt: string(row, "updatedAt"),
    archivedAt: nullableString(row, "archivedAt"),
  });
}

function targetGroups(values: unknown[]): ExpenseTargetGroup[] {
  const groups = new Map<string, ExpenseTargetGroup & { projects: { id: string; name: string }[] }>();
  for (const value of values) {
    const row = objectRow(value);
    const clientId = string(row, "client_id");
    let group = groups.get(clientId);
    if (!group) {
      group = {
        client: { id: clientId, name: string(row, "client_name"), currencyCode: string(row, "currency_code") },
        projects: [],
      };
      groups.set(clientId, group);
    }
    const projectId = nullableString(row, "project_id");
    if (projectId) group.projects.push({ id: projectId, name: string(row, "project_name") });
  }
  return [...groups.values()];
}

function sameTarget(left: ExpenseTarget, right: ExpenseTarget): boolean {
  return left.kind === right.kind &&
    (left.kind === "client"
      ? left.clientId === (right as Extract<ExpenseTarget, { kind: "client" }>).clientId
      : left.projectId === (right as Extract<ExpenseTarget, { kind: "project" }>).projectId);
}
function objectRow(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new TypeError("Expense query row must be an object");
  return value as Record<string, unknown>;
}
function string(row: Record<string, unknown>, key: string): string {
  if (typeof row[key] !== "string") throw new TypeError(`${key} must be a string`);
  return row[key];
}
function nullableString(row: Record<string, unknown>, key: string): string | null {
  if (row[key] !== null && typeof row[key] !== "string") throw new TypeError(`${key} must be a string or null`);
  return row[key] as string | null;
}
function errorMessage(cause: unknown): string { return cause instanceof Error ? cause.message : String(cause); }
function persistence(cause: unknown): ExpenseStoreError { return new ExpenseStoreError("persistence", cause); }
