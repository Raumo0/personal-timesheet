import { useCallback, useEffect, useRef, useState } from "react";
import { Archive, Pencil, Plus, ReceiptText, RotateCcw } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

import { formatMinorUnits } from "../money/money";
import type {
  CatalogLifecycle,
  LifecycleOperation,
  LifecyclePlan,
  LifecycleRequest,
} from "../catalog-lifecycle/catalog-lifecycle";
import type { Expense, ExpenseCommand } from "./expense";
import type {
  ExpenseList,
  ExpenseStore,
  ExpenseTargetDisplay,
  ExpenseTargetGroup,
} from "./expense-store";
import { ExpenseForm } from "./ExpenseForm";

export interface ExpensesPageProps {
  store: ExpenseStore;
  lifecycle?: CatalogLifecycle;
}

export function ExpensesPage({ store, lifecycle }: ExpensesPageProps) {
  const [filter, setFilter] = useState<ExpenseList>("active");
  const [expenses, setExpenses] = useState<readonly Expense[]>([]);
  const [targets, setTargets] = useState<readonly ExpenseTargetGroup[]>([]);
  const [targetDisplays, setTargetDisplays] = useState<readonly ExpenseTargetDisplay[]>([]);
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");
  const [formOpen, setFormOpen] = useState(false);
  const [editingExpense, setEditingExpense] = useState<Expense>();
  const [lifecycleExpense, setLifecycleExpense] = useState<Expense>();
  const [lifecyclePlan, setLifecyclePlan] = useState<LifecyclePlan>();
  const [retryRequest, setRetryRequest] = useState<LifecycleRequest>();
  const [mutationError, setMutationError] = useState<string>();
  const loadRequest = useRef(0);
  const lifecycleInitiator = useRef<HTMLButtonElement | null>(null);

  const loadExpenses = useCallback(async () => {
    const request = ++loadRequest.current;
    setStatus("loading");
    try {
      const snapshot = await store.loadWorkspace(filter);
      if (request !== loadRequest.current) return;
      setExpenses(
        [...snapshot.expenses].sort(
          (left, right) =>
            right.expenseDate.localeCompare(left.expenseDate) ||
            right.createdAt.localeCompare(left.createdAt) ||
            left.id.localeCompare(right.id),
        ),
      );
      setTargets(snapshot.targets);
      setTargetDisplays(snapshot.targetDisplays);
      setStatus("loaded");
    } catch {
      if (request !== loadRequest.current) return;
      setStatus("error");
    }
  }, [filter, store]);

  useEffect(() => {
    void loadExpenses();
  }, [loadExpenses]);

  async function saveExpense(command: ExpenseCommand) {
    if (editingExpense) {
      await store.update(editingExpense.id, editingExpense.updatedAt, command);
    } else {
      await store.create(command);
    }
    await loadExpenses();
  }

  async function requestLifecycle(
    targetExpense: Expense,
    operation: LifecycleOperation,
    initiator?: HTMLButtonElement,
  ) {
    if (!lifecycle) return;
    if (initiator) lifecycleInitiator.current = initiator;
    const request: LifecycleRequest = {
      operation,
      target: { kind: "expense", id: targetExpense.id },
    };
    setMutationError(undefined);
    try {
      const plan = await lifecycle.preview(request);
      setLifecyclePlan(plan);
      setLifecycleExpense(targetExpense);
      setRetryRequest(undefined);
    } catch (error) {
      setMutationError(
        error instanceof Error
          ? error.message
          : "The lifecycle change could not be prepared",
      );
      setRetryRequest(request);
      restoreLifecycleFocus();
    }
  }

  async function confirmLifecycle() {
    if (!lifecycle || !lifecyclePlan) return;
    setMutationError(undefined);
    try {
      await lifecycle.apply(lifecyclePlan);
      setLifecycleExpense(undefined);
      setLifecyclePlan(undefined);
      setRetryRequest(undefined);
      await loadExpenses();
    } catch (error) {
      setMutationError(
        error instanceof Error
          ? error.message
          : lifecyclePlan.operation === "restore"
            ? "The expense was not restored"
            : "The expense was not archived",
      );
      setRetryRequest({
        operation: lifecyclePlan.operation,
        target: lifecyclePlan.target,
      });
      setLifecycleExpense(undefined);
      setLifecyclePlan(undefined);
      restoreLifecycleFocus();
    }
  }

  async function retryLifecycle() {
    if (!retryRequest) return;
    const targetExpense = expenses.find(({ id }) => id === retryRequest.target.id);
    if (!targetExpense) return;
    await requestLifecycle(targetExpense, retryRequest.operation);
  }

  function restoreLifecycleFocus() {
    queueMicrotask(() => lifecycleInitiator.current?.focus());
  }

  function openCreateForm() {
    setEditingExpense(undefined);
    setFormOpen(true);
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex items-start justify-between gap-6">
        <div className="max-w-3xl">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">Expenses</h1>
          <p className="mt-2 text-pretty text-sm leading-6 text-muted-foreground">
            Track costs against Clients and Projects in their original and billing currencies.
          </p>
        </div>
        <Button onClick={openCreateForm}>
          <Plus aria-hidden="true" />
          Add expense
        </Button>
      </header>

      <section aria-label="Expense ledger" className="mt-6 overflow-hidden rounded-xl border bg-card shadow-xs">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div aria-label="Expense status filter" className="inline-flex rounded-lg bg-muted p-1">
            {(["active", "archived"] as const).map((value) => (
              <button
                aria-pressed={filter === value}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors motion-reduce:transition-none",
                  filter === value
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
                key={value}
                onClick={() => setFilter(value)}
                type="button"
              >
                {value === "active" ? "Active" : "Archived"}
              </button>
            ))}
          </div>
          {status === "loaded" && expenses.length > 0 ? (
            <p className="text-xs tabular-nums text-muted-foreground">
              {expenses.length} {expenses.length === 1 ? "expense" : "expenses"}
            </p>
          ) : null}
        </div>

        {mutationError ? (
          <div
            className="flex items-center justify-between gap-4 border-b bg-destructive/10 px-4 py-3 text-sm text-destructive"
            role="alert"
          >
            <span>{mutationError}</span>
            {retryRequest ? (
              <Button onClick={() => void retryLifecycle()} size="sm" variant="outline">
                <RotateCcw aria-hidden="true" />
                Retry
              </Button>
            ) : null}
          </div>
        ) : null}

        {status === "loading" ? (
          <div className="flex min-h-64 items-center justify-center text-sm text-muted-foreground" role="status">
            Loading expenses…
          </div>
        ) : null}

        {status === "error" ? (
          <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center" role="alert">
            <p className="text-sm font-medium">Expenses could not be loaded</p>
            <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
              Your local data was not changed. Try reading it again.
            </p>
            <Button className="mt-4" onClick={() => void loadExpenses()} variant="outline">
              <RotateCcw aria-hidden="true" />
              Retry
            </Button>
          </div>
        ) : null}

        {status === "loaded" && expenses.length === 0 ? (
          <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
            <div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <ReceiptText aria-hidden="true" className="size-5" />
            </div>
            <h2 className="mt-4 text-sm font-semibold">
              {filter === "active" ? "No expenses yet" : "No archived expenses"}
            </h2>
            <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
              {filter === "active"
                ? "Add the first cost you want to retain against a Client or Project."
                : "Archived expenses remain available here as read-only records."}
            </p>
            {filter === "active" ? (
              <Button className="mt-4" onClick={openCreateForm} variant="outline">
                Add your first expense
              </Button>
            ) : null}
          </div>
        ) : null}

        {status === "loaded" && expenses.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-11 px-4">Date</TableHead>
                <TableHead className="h-11">Client / Project</TableHead>
                <TableHead className="h-11">Description</TableHead>
                <TableHead className="h-11 text-right">Original</TableHead>
                <TableHead className="h-11 text-right">Billing amount</TableHead>
                <TableHead className="h-11 w-24 pr-4"><span className="sr-only">Actions</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {expenses.map((expense) => (
                <TableRow key={expense.id}>
                  <TableCell className="px-4 py-3 tabular-nums text-muted-foreground">{expense.expenseDate}</TableCell>
                  <TableCell className="max-w-56 py-3"><span className="block truncate" title={expenseTargetLabel(expense, targets, targetDisplays)}>{expenseTargetLabel(expense, targets, targetDisplays)}</span></TableCell>
                  <TableCell className="max-w-72 py-3 font-medium"><span className="block truncate" title={expense.description}>{expense.description}</span></TableCell>
                  <TableCell className="py-3 text-right font-medium tabular-nums">{formatMinorUnits(expense.originalAmountMinor, expense.originalCurrencyCode)}</TableCell>
                  <TableCell className="py-3 text-right font-medium tabular-nums">{formatMinorUnits(expense.billingAmountMinor, expense.billingCurrencyCode)}</TableCell>
                  <TableCell className="py-3 pr-4">
                    <div className="flex justify-end gap-1">
                      {filter === "active" ? (
                        <>
                          <Button
                            aria-label={`Edit ${expense.description}`}
                            onClick={() => {
                              setEditingExpense(expense);
                              setFormOpen(true);
                            }}
                            size="icon-sm"
                            variant="ghost"
                          >
                            <Pencil aria-hidden="true" />
                          </Button>
                          {lifecycle ? (
                            <Button
                              aria-label={`Archive ${expense.description}`}
                              onClick={(event) => void requestLifecycle(expense, "archive", event.currentTarget)}
                              size="icon-sm"
                              variant="ghost"
                            >
                              <Archive aria-hidden="true" />
                            </Button>
                          ) : null}
                        </>
                      ) : lifecycle ? (
                        <Button
                          aria-label={`Restore ${expense.description}`}
                          onClick={(event) => void requestLifecycle(expense, "restore", event.currentTarget)}
                          size="sm"
                          variant="ghost"
                        >
                          <RotateCcw aria-hidden="true" />
                          Restore
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">Read-only</span>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </section>

      <ExpenseForm
        expense={editingExpense}
        open={formOpen}
        targets={targets}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingExpense(undefined);
        }}
        onSave={saveExpense}
      />

      <AlertDialog
        onOpenChange={(open) => {
          if (!open) {
            setLifecycleExpense(undefined);
            setLifecyclePlan(undefined);
            restoreLifecycleFocus();
          }
        }}
        open={Boolean(lifecycleExpense)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {lifecyclePlan?.operation === "restore" ? "Restore" : "Archive"}{" "}
              {lifecycleExpense?.description}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {lifecyclePlan?.impactDescription ??
                "The expense will remain available in archived records."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void confirmLifecycle()}
              variant={lifecyclePlan?.operation === "restore" ? "default" : "destructive"}
            >
              {lifecyclePlan?.operation === "restore"
                ? "Restore expense"
                : "Archive expense"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function expenseTargetLabel(
  expense: Expense,
  targets: readonly ExpenseTargetGroup[],
  targetDisplays: readonly ExpenseTargetDisplay[],
): string {
  const retainedName = targetDisplays.find(({ target }) =>
    target.kind === expense.target.kind &&
    (target.kind === "client"
      ? target.clientId === (expense.target as Extract<Expense["target"], { kind: "client" }>).clientId
      : target.projectId === (expense.target as Extract<Expense["target"], { kind: "project" }>).projectId),
  )?.name;
  if (expense.target.kind === "client") {
    const clientId = expense.target.clientId;
    const group = targets.find(({ client }) => client.id === clientId);
    return `Client · ${retainedName ?? group?.client.name ?? clientId}`;
  }
  const projectId = expense.target.projectId;
  for (const group of targets) {
    const project = group.projects.find(({ id }) => id === projectId);
    if (project) return `Project · ${project.name}`;
  }
  return `Project · ${retainedName ?? projectId}`;
}
