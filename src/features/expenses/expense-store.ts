import type { Client } from "../clients/client";
import type { Project } from "../projects/project";
import type { Expense, ExpenseCommand, ExpenseTarget } from "./expense";

export type ExpenseList = "active" | "archived";

export interface ExpenseTargetProject {
  readonly id: string;
  readonly name: string;
}

export interface ExpenseTargetGroup {
  readonly client: {
    readonly id: string;
    readonly name: string;
    readonly currencyCode: string;
  };
  readonly projects: readonly ExpenseTargetProject[];
}

export interface ExpenseWorkspaceSnapshot {
  readonly expenses: readonly Expense[];
  readonly targets: readonly ExpenseTargetGroup[];
  readonly targetDisplays: readonly ExpenseTargetDisplay[];
}

export interface ExpenseTargetDisplay {
  readonly target: ExpenseTarget;
  readonly name: string;
}

export interface ExpenseStore {
  loadWorkspace(list: ExpenseList): Promise<ExpenseWorkspaceSnapshot>;
  create(input: ExpenseCommand): Promise<Expense>;
  update(
    id: string,
    expectedUpdatedAt: string,
    input: ExpenseCommand,
  ): Promise<Expense>;
}

export type ExpenseStoreErrorCode =
  | "inactive-target"
  | "currency-changed"
  | "expense-not-found"
  | "archived-expense"
  | "stale-expense"
  | "invalid-expense"
  | "persistence";

const ERROR_MESSAGES: Record<ExpenseStoreErrorCode, string> = {
  "inactive-target": "The selected expense target is no longer active.",
  "currency-changed":
    "The target billing currency changed; review the conversion and try again.",
  "expense-not-found": "The expense no longer exists.",
  "archived-expense": "Archived expenses are read-only until restored.",
  "stale-expense": "The expense changed; reload it and try again.",
  "invalid-expense": "The expense contains invalid values.",
  persistence: "Expense data could not be saved or loaded. Try again.",
};

export class ExpenseStoreError extends Error {
  readonly code: ExpenseStoreErrorCode;
  readonly cause?: unknown;

  constructor(code: ExpenseStoreErrorCode, cause?: unknown) {
    super(ERROR_MESSAGES[code]);
    this.name = "ExpenseStoreError";
    this.code = code;
    this.cause = cause;
  }
}

export interface ExpenseStoreSeed {
  readonly clients: readonly Client[];
  readonly projects: readonly Project[];
  readonly expenses: readonly Expense[];
  readonly failure?: ExpenseStoreError;
}
