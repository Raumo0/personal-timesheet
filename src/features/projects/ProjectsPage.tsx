import { useCallback, useEffect, useRef, useState } from "react";
import { Archive, FolderKanban, Pencil, Plus, RotateCcw } from "lucide-react";
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
import { resolveProjectRate, type Project, type ProjectCommand } from "./project";
import type { ProjectCatalog, ProjectList } from "./project-catalog";
import { ProjectForm } from "./ProjectForm";

interface ProjectsPageProps {
  client: Client;
  catalog: ProjectCatalog;
  lifecycle?: CatalogLifecycle;
}

export function ProjectsPage({ client, catalog, lifecycle }: ProjectsPageProps) {
  const [filter, setFilter] = useState<ProjectList>("active");
  const [projects, setProjects] = useState<Project[]>([]);
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");
  const [formOpen, setFormOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<Project>();
  const [archiveProject, setArchiveProject] = useState<Project>();
  const [lifecyclePlan, setLifecyclePlan] = useState<LifecyclePlan>();
  const [retryRequest, setRetryRequest] = useState<LifecycleRequest>();
  const [mutationError, setMutationError] = useState<string>();
  const loadRequest = useRef(0);
  const lifecycleInitiator = useRef<HTMLButtonElement | null>(null);
  const isReadOnly = client.archivedAt !== null;
  const showActions =
    (!isReadOnly && filter === "active") ||
    (filter === "archived" && lifecycle !== undefined);

  const loadProjects = useCallback(async () => {
    const request = ++loadRequest.current;
    setStatus("loading");
    try {
      const nextProjects = await catalog.list(client.id, filter);
      if (request !== loadRequest.current) return;
      setProjects(nextProjects);
      setStatus("loaded");
    } catch {
      if (request !== loadRequest.current) return;
      setStatus("error");
    }
  }, [catalog, client.id, filter]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  async function saveProject(command: ProjectCommand) {
    if (editingProject) {
      await catalog.update(client.id, editingProject.id, command);
    } else {
      await catalog.create(client.id, command);
    }
    await loadProjects();
  }

  async function confirmArchive() {
    if (!archiveProject || !lifecycle || !lifecyclePlan) return;
    setMutationError(undefined);
    try {
      await lifecycle.apply(lifecyclePlan);
      setArchiveProject(undefined);
      setLifecyclePlan(undefined);
      setRetryRequest(undefined);
      await loadProjects();
    } catch (error) {
      setMutationError(
        error instanceof Error
          ? error.message
          : lifecyclePlan?.operation === "restore"
            ? "The project was not restored"
            : "The project was not archived",
      );
      if (lifecyclePlan) {
        setRetryRequest({
          operation: lifecyclePlan.operation,
          target: lifecyclePlan.target,
        });
      }
      setArchiveProject(undefined);
      setLifecyclePlan(undefined);
      restoreLifecycleFocus();
    }
  }

  async function requestLifecycle(
    targetProject: Project,
    operation: LifecycleOperation,
    initiator?: HTMLButtonElement,
  ) {
    if (!lifecycle) {
      return;
    }
    if (initiator) lifecycleInitiator.current = initiator;
    const request: LifecycleRequest = {
      operation,
      target: { kind: "project", id: targetProject.id },
    };
    setMutationError(undefined);
    try {
      const plan = await lifecycle.preview(request);
      setLifecyclePlan(plan);
      setArchiveProject(targetProject);
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
    const targetProject = projects.find(
      (candidate) => candidate.id === retryRequest.target.id,
    );
    if (!targetProject) return;
    await requestLifecycle(targetProject, retryRequest.operation);
  }

  function restoreLifecycleFocus() {
    queueMicrotask(() => lifecycleInitiator.current?.focus());
  }

  function openCreateForm() {
    setEditingProject(undefined);
    setFormOpen(true);
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex items-start justify-between gap-6">
        <div className="max-w-3xl">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-2 text-pretty text-sm leading-6 text-muted-foreground">
            {isReadOnly
              ? `${client.name} is archived. Its projects are retained as historical records.`
              : `Manage projects and rate choices for ${client.name}.`}
          </p>
        </div>
        <Button disabled={isReadOnly} onClick={openCreateForm}>
          <Plus aria-hidden="true" />
          Add project
        </Button>
      </header>

      <section aria-label="Project catalog" className="mt-6 overflow-hidden rounded-xl border bg-card shadow-xs">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div aria-label="Project status filter" className="inline-flex rounded-lg bg-muted p-1">
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
          {status === "loaded" && projects.length > 0 && (
            <p className="text-xs tabular-nums text-muted-foreground">
              {projects.length} {projects.length === 1 ? "project" : "projects"}
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
            Loading projects…
          </div>
        )}

        {status === "error" && (
          <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
            <p className="text-sm font-medium">Projects could not be loaded</p>
            <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
              Your local data was not changed. Try reading it again.
            </p>
            <Button className="mt-4" onClick={() => void loadProjects()} variant="outline">
              <RotateCcw aria-hidden="true" />
              Retry
            </Button>
          </div>
        )}

        {status === "loaded" && projects.length === 0 && (
          <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
            <div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <FolderKanban aria-hidden="true" className="size-5" />
            </div>
            <h2 className="mt-4 text-sm font-semibold">
              {filter === "active" ? "No projects yet" : "No archived projects"}
            </h2>
            <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
              {filter === "active"
                ? "Add a project to assign work beneath this client."
                : "Archived projects remain available here for historical records."}
            </p>
            {filter === "active" && !isReadOnly && (
              <Button className="mt-4" onClick={openCreateForm} variant="outline">
                Add your first project
              </Button>
            )}
          </div>
        )}

        {status === "loaded" && projects.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-11 px-4">Project</TableHead>
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
              {projects.map((project) => {
                const rate = resolveProjectRate(
                  project.hourlyRateOverrideMinor,
                  client.hourlyRateMinor,
                );
                return (
                  <TableRow key={project.id}>
                    <TableCell className="max-w-96 px-4 py-3 font-medium">
                      <Link
                        className="rounded-sm transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        to={`/clients/${client.id}/projects/${project.id}/tasks`}
                      >
                        {project.name}
                      </Link>
                    </TableCell>
                    <TableCell className="py-3 text-muted-foreground">
                      {project.hourlyRateOverrideMinor === null ? "Inherited" : "Override"}
                    </TableCell>
                    <TableCell className="py-3 text-muted-foreground">
                      {rate.source === "project"
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
                                aria-label={`Edit ${project.name}`}
                                onClick={() => {
                                  setEditingProject(project);
                                  setFormOpen(true);
                                }}
                                size="icon-sm"
                                variant="ghost"
                              >
                                <Pencil aria-hidden="true" />
                              </Button>
                              <Button
                                aria-label={`Archive ${project.name}`}
                                onClick={(event) =>
                                  void requestLifecycle(
                                    project,
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
                              aria-label={`Restore ${project.name}`}
                              onClick={(event) =>
                                void requestLifecycle(
                                  project,
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

      <ProjectForm
        client={client}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingProject(undefined);
        }}
        onSave={saveProject}
        open={formOpen}
        project={editingProject}
      />

      <AlertDialog
        onOpenChange={(open) => {
          if (!open) {
            setArchiveProject(undefined);
            setLifecyclePlan(undefined);
            restoreLifecycleFocus();
          }
        }}
        open={Boolean(archiveProject)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {lifecyclePlan?.operation === "restore" ? "Restore" : "Archive"}{" "}
              {archiveProject?.name}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {lifecyclePlan?.impactDescription ??
                "The project will leave the active list but remain available in archived records."}
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
                ? "Restore project"
                : "Archive project"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
