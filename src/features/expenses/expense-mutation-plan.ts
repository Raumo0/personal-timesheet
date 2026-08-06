import type { ExpenseCommand, ExpenseTarget } from "./expense";

export interface ExpenseMutationExpectedTarget {
  readonly clientId: string;
  readonly clientCurrencyCode: string;
  readonly clientUpdatedAt: string;
  readonly clientArchivedAt: string | null;
  readonly projectId: string | null;
  readonly projectUpdatedAt: string | null;
  readonly projectArchivedAt: string | null;
}

export interface ExpenseMutationPlan {
  readonly operation: "create" | "update";
  readonly expenseId: string;
  readonly appliedAt: string;
  readonly command: ExpenseCommand;
  readonly expectedTarget: ExpenseMutationExpectedTarget;
  readonly expectedExpenseUpdatedAt: string | null;
  readonly expectedExpenseArchivedAt: string | null;
  readonly expectedExpenseTarget: ExpenseTarget | null;
  readonly expectedOriginalCurrencyCode: string | null;
  readonly expectedBillingCurrencyCode: string | null;
}

export function freezeExpenseMutationPlan(
  plan: ExpenseMutationPlan,
): ExpenseMutationPlan {
  return deepFreeze(structuredClone(plan));
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object") {
    for (const child of Object.values(value)) deepFreeze(child);
    Object.freeze(value);
  }
  return value;
}
