import { useCallback, useEffect, useRef, useState } from "react";
import { Archive, CheckSquare, Pencil, Plus, RotateCcw } from "lucide-react";
import { Link } from "react-router";

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

import type {
  CatalogLifecycle,
  LifecycleOperation,
  LifecyclePlan,
  LifecycleRequest,
} from "../catalog-lifecycle/catalog-lifecycle";
import { formatRate, type Client } from "../clients/client";
import type { Project } from "../projects/project";
import { resolveTaskRate, type Task, type TaskCommand } from "./task";
import type { TaskCatalog, TaskList } from "./task-catalog";
import { TaskForm } from "./TaskForm";

interface TasksPageProps {
  client: Client;
  project: Project;
  catalog: TaskCatalog;
  lifecycle?: CatalogLifecycle;
}

export function TasksPage({
  client,
  project,
  catalog,
  lifecycle,
}: TasksPageProps) {
  const [filter, setFilter] = useState<TaskList>("active");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");
  const [formOpen, setFormOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task>();
  const [archiveTask, setArchiveTask] = useState<Task>();
  const [lifecyclePlan, setLifecyclePlan] = useState<LifecyclePlan>();
  const [retryRequest, setRetryRequest] = useState<LifecycleRequest>();
  const [mutationError, setMutationError] = useState<string>();
  const loadRequest = useRef(0);
  const lifecycleInitiator = useRef<HTMLButtonElement | null>(null);
  const isReadOnly = client.archivedAt !== null || project.archivedAt !== null;
  const showActions =
    (!isReadOnly && filter === "active") ||
    (filter === "archived" && lifecycle !== undefined);

  const loadTasks = useCallback(async () => {
    const request = ++loadRequest.current;
    setStatus("loading");
    try {
      const nextTasks = await catalog.list(project.id, filter);
      if (request !== loadRequest.current) return;
      setTasks(nextTasks);
      setStatus("loaded");
    } catch {
      if (request !== loadRequest.current) return;
      setStatus("error");
    }
  }, [catalog, filter, project.id]);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  async function saveTask(command: TaskCommand) {
    if (editingTask) {
      await catalog.update(project.id, editingTask.id, command);
    } else {
      await catalog.create(project.id, command);
    }
    await loadTasks();
  }

  async function confirmArchive() {
    if (!archiveTask || !lifecycle || !lifecyclePlan) return;
    setMutationError(undefined);
    try {
      await lifecycle.apply(lifecyclePlan);
      setArchiveTask(undefined);
      setLifecyclePlan(undefined);
      setRetryRequest(undefined);
      await loadTasks();
    } catch (error) {
      setMutationError(
        error instanceof Error
          ? error.message
          : lifecyclePlan?.operation === "restore"
            ? "The task was not restored"
            : "The task was not archived",
      );
      if (lifecyclePlan) {
        setRetryRequest({
          operation: lifecyclePlan.operation,
          target: lifecyclePlan.target,
        });
      }
      setArchiveTask(undefined);
      setLifecyclePlan(undefined);
      restoreLifecycleFocus();
    }
  }

  async function requestLifecycle(
    targetTask: Task,
    operation: LifecycleOperation,
    initiator?: HTMLButtonElement,
  ) {
    if (!lifecycle) {
      return;
    }
    if (initiator) lifecycleInitiator.current = initiator;
    const request: LifecycleRequest = {
      operation,
      target: { kind: "task", id: targetTask.id },
    };
    setMutationError(undefined);
    try {
      const plan = await lifecycle.preview(request);
      setLifecyclePlan(plan);
      setArchiveTask(targetTask);
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

  async function retryLifecycle() {
    if (!lifecycle || !retryRequest) return;
    const targetTask = tasks.find(
      (candidate) => candidate.id === retryRequest.target.id,
    );
    if (!targetTask) return;
    await requestLifecycle(targetTask, retryRequest.operation);
  }

  function restoreLifecycleFocus() {
    queueMicrotask(() => lifecycleInitiator.current?.focus());
  }

  function openCreateForm() {
    setEditingTask(undefined);
    setFormOpen(true);
  }

  return (
    <div className="flex min-h-full flex-col">
      <nav aria-label="Breadcrumb" className="mb-4 flex items-center gap-2 text-sm text-muted-foreground">
        <span>{client.name}</span>
        <span aria-hidden="true">→</span>
        <Link
          className="rounded-sm transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          to={`/clients/${client.id}/projects`}
        >
          {project.name}
        </Link>
        <span aria-hidden="true">→</span>
        <span aria-current="page" className="text-foreground">Tasks</span>
      </nav>

      <header className="flex items-start justify-between gap-6">
        <div className="max-w-3xl">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">Tasks</h1>
          <p className="mt-2 text-pretty text-sm leading-6 text-muted-foreground">
            {isReadOnly
              ? `${project.name} is retained as a read-only historical workspace.`
              : `Manage tasks and rate choices for ${project.name}.`}
          </p>
        </div>
        <Button disabled={isReadOnly} onClick={openCreateForm}>
          <Plus aria-hidden="true" />
          Add task
        </Button>
      </header>

      <section aria-label="Task catalog" className="mt-6 overflow-hidden rounded-xl border bg-card shadow-xs">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div aria-label="Task status filter" className="inline-flex rounded-lg bg-muted p-1">
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
          {status === "loaded" && tasks.length > 0 && (
            <p className="text-xs tabular-nums text-muted-foreground">
              {tasks.length} {tasks.length === 1 ? "task" : "tasks"}
            </p>
          )}
        </div>

        {mutationError && (
          <div
            className="flex items-center justify-between gap-4 border-b bg-destructive/10 px-4 py-3 text-sm text-destructive"
            role="alert"
          >
            <span>{mutationError}</span>
            {retryRequest && (
              <Button
                onClick={() => void retryLifecycle()}
                size="sm"
                variant="outline"
              >
                <RotateCcw aria-hidden="true" />
                Retry
              </Button>
            )}
          </div>
        )}

        {status === "loading" && (
          <div className="flex min-h-64 items-center justify-center text-sm text-muted-foreground" role="status">
            Loading tasks…
          </div>
        )}

        {status === "error" && (
          <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
            <p className="text-sm font-medium">Tasks could not be loaded</p>
            <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
              Your local data was not changed. Try reading it again.
            </p>
            <Button className="mt-4" onClick={() => void loadTasks()} variant="outline">
              <RotateCcw aria-hidden="true" />
              Retry
            </Button>
          </div>
        )}

        {status === "loaded" && tasks.length === 0 && (
          <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
            <div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <CheckSquare aria-hidden="true" className="size-5" />
            </div>
            <h2 className="mt-4 text-sm font-semibold">
              {filter === "active" ? "No tasks yet" : "No archived tasks"}
            </h2>
            <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
              {filter === "active"
                ? "Add a task to organize work beneath this project."
                : "Archived tasks remain available here for historical records."}
            </p>
            {filter === "active" && !isReadOnly && (
              <Button className="mt-4" onClick={openCreateForm} variant="outline">
                Add your first task
              </Button>
            )}
          </div>
        )}

        {status === "loaded" && tasks.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-11 px-4">Task</TableHead>
                <TableHead className="h-11 w-36">Rate mode</TableHead>
                <TableHead className="h-11 w-48">Rate source</TableHead>
                <TableHead className="h-11 w-40 pr-4 text-right">Effective hourly rate</TableHead>
                {showActions && (
                  <TableHead className="h-11 w-24 pr-4">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {tasks.map((task) => {
                const rate = resolveTaskRate(
                  task.hourlyRateOverrideMinor,
                  project.hourlyRateOverrideMinor,
                  client.hourlyRateMinor,
                );
                return (
                  <TableRow key={task.id}>
                    <TableCell className="max-w-96 px-4 py-3 font-medium">{task.name}</TableCell>
                    <TableCell className="py-3 text-muted-foreground">
                      {task.hourlyRateOverrideMinor === null ? "Inherited" : "Override"}
                    </TableCell>
                    <TableCell className="py-3 text-muted-foreground">
                      {rate.source === "task"
                        ? "Task override"
                        : rate.source === "project"
                          ? "Project override"
                          : rate.source === "client"
                            ? "Client default"
                            : "No rate set"}
                    </TableCell>
                    <TableCell className="py-3 pr-4 text-right font-medium tabular-nums">
                      {formatRate(rate.hourlyRateMinor, client.currencyCode) ?? (
                        <span className="font-normal text-muted-foreground">Not set</span>
                      )}
                    </TableCell>
                    {showActions && (
                      <TableCell className="py-3 pr-4">
                        <div className="flex justify-end gap-1">
                          {filter === "active" ? (
                            <>
                              <Button
                                aria-label={`Edit ${task.name}`}
                                onClick={() => {
                                  setEditingTask(task);
                                  setFormOpen(true);
                                }}
                                size="icon-sm"
                                variant="ghost"
                              >
                                <Pencil aria-hidden="true" />
                              </Button>
                              <Button
                                aria-label={`Archive ${task.name}`}
                                onClick={(event) =>
                                  void requestLifecycle(
                                    task,
                                    "archive",
                                    event.currentTarget,
                                  )
                                }
                                size="icon-sm"
                                variant="ghost"
                              >
                                <Archive aria-hidden="true" />
                              </Button>
                            </>
                          ) : (
                            <Button
                              aria-label={`Restore ${task.name}`}
                              onClick={(event) =>
                                void requestLifecycle(
                                  task,
                                  "restore",
                                  event.currentTarget,
                                )
                              }
                              size="icon-sm"
                              variant="ghost"
                            >
                              <RotateCcw aria-hidden="true" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </section>

      <TaskForm
        client={client}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingTask(undefined);
        }}
        onSave={saveTask}
        open={formOpen}
        project={project}
        task={editingTask}
      />

      <AlertDialog
        onOpenChange={(open) => {
          if (!open) {
            setArchiveTask(undefined);
            setLifecyclePlan(undefined);
            restoreLifecycleFocus();
          }
        }}
        open={Boolean(archiveTask)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {lifecyclePlan?.operation === "restore" ? "Restore" : "Archive"}{" "}
              {archiveTask?.name}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {lifecyclePlan?.impactDescription ??
                "The task will leave the active list but remain available in archived records."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void confirmArchive()}
              variant={
                lifecyclePlan?.operation === "restore" ? "default" : "destructive"
              }
            >
              {lifecyclePlan?.operation === "restore"
                ? "Restore task"
                : "Archive task"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
