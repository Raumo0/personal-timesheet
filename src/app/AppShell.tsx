import { lazy, Suspense, useEffect, useState } from "react";
import {
  ChevronsLeft,
  ChevronsRight,
  Clock3,
} from "lucide-react";
import {
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
  useParams,
} from "react-router";

import { ThemeMenu } from "@/app/theme/ThemeMenu";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { ClientCatalog } from "@/features/clients/client-catalog";
import type { CatalogLifecycle } from "@/features/catalog-lifecycle/catalog-lifecycle";
import type { ProjectCatalog } from "@/features/projects/project-catalog";
import type { TaskCatalog } from "@/features/tasks/task-catalog";
import type { BackupService } from "@/features/backup/backup-service";

import {
  navigationDestinations,
  type NavigationDestination,
} from "./navigation";
import { ProductPage } from "./pages/ProductPage";

const ClientsPage = lazy(() =>
  import("@/features/clients/ClientsPage").then((module) => ({
    default: module.ClientsPage,
  })),
);

const SettingsDataPage = lazy(() =>
  import("@/features/backup/SettingsDataPage").then((module) => ({
    default: module.SettingsDataPage,
  })),
);
const ProjectsPage = lazy(() => import("@/features/projects/ProjectsPage").then((module) => ({ default: module.ProjectsPage })));
const TasksPage = lazy(() => import("@/features/tasks/TasksPage").then((module) => ({ default: module.TasksPage })));

function ProjectWorkspaceRoute({ clientCatalog, projectCatalog, lifecycle }: { clientCatalog: ClientCatalog; projectCatalog: ProjectCatalog; lifecycle?: CatalogLifecycle }) {
  const { clientId } = useParams();
  const [attempt, setAttempt] = useState(0);
  const [context, setContext] = useState<{ status: "loading" } | { status: "loaded"; client: import("@/features/clients/client").Client } | { status: "error" }>({ status: "loading" });
  useEffect(() => { let current = true; setContext({ status: "loading" }); void (async () => {
    try { const active = await clientCatalog.list("active"); const client = active.find((candidate) => candidate.id === clientId) ?? (await clientCatalog.list("archived")).find((candidate) => candidate.id === clientId); if (current && client) setContext({ status: "loaded", client }); else if (current) setContext({ status: "error" }); }
    catch { if (current) setContext({ status: "error" }); }
  })(); return () => { current = false; }; }, [attempt, clientCatalog, clientId]);
  if (context.status === "loading") return <p role="status">Opening projects…</p>;
  if (context.status === "error") return <div role="alert"><p>Projects could not be opened</p><Button onClick={() => setAttempt((value) => value + 1)}>Retry</Button></div>;
  return <ProjectsPage client={context.client} catalog={projectCatalog} lifecycle={lifecycle} />;
}

function TaskWorkspaceUnavailable() {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center text-center">
      <h1 className="text-xl font-semibold tracking-tight">Task workspace unavailable</h1>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
        The selected client or project could not be found in local data.
      </p>
      <Button className="mt-4" render={<NavLink to="/clients" />} variant="outline">
        Back to clients
      </Button>
    </div>
  );
}

function TaskWorkspaceRoute({
  clientCatalog,
  projectCatalog,
  taskCatalog,
  lifecycle,
}: {
  clientCatalog: ClientCatalog;
  projectCatalog: ProjectCatalog;
  taskCatalog: TaskCatalog;
  lifecycle?: CatalogLifecycle;
}) {
  const { clientId, projectId } = useParams();
  const [context, setContext] = useState<
    | { status: "loading" }
    | { status: "unavailable" }
    | {
        status: "loaded";
        client: import("@/features/clients/client").Client;
        project: import("@/features/projects/project").Project;
      }
  >({ status: "loading" });

  useEffect(() => {
    let current = true;
    setContext({ status: "loading" });
    void (async () => {
      if (!clientId || !projectId) {
        if (current) setContext({ status: "unavailable" });
        return;
      }
      try {
        const [client, project] = await Promise.all([
          clientCatalog.get(clientId),
          projectCatalog.get(clientId, projectId),
        ]);
        if (!current) return;
        if (project.clientId !== client.id) {
          setContext({ status: "unavailable" });
          return;
        }
        setContext({ status: "loaded", client, project });
      } catch {
        if (current) setContext({ status: "unavailable" });
      }
    })();
    return () => {
      current = false;
    };
  }, [clientCatalog, clientId, projectCatalog, projectId]);

  if (context.status === "loading") return <p role="status">Opening tasks…</p>;
  if (context.status === "unavailable") return <TaskWorkspaceUnavailable />;
  return (
    <TasksPage
      catalog={taskCatalog}
      client={context.client}
      project={context.project}
      lifecycle={lifecycle}
    />
  );
}

function SidebarDestination({
  destination,
  isCollapsed,
}: {
  destination: NavigationDestination;
  isCollapsed: boolean;
}) {
  const Icon = destination.icon;
  const link = (
    <NavLink
      aria-label={destination.label}
      className={({ isActive }) =>
        cn(
          "flex h-10 items-center rounded-lg text-sm font-medium transition-colors",
          isCollapsed ? "justify-center px-0" : "gap-3 px-3",
          isActive
            ? "bg-sidebar-primary text-sidebar-primary-foreground shadow-sm"
            : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        )
      }
      end={destination.path === "/"}
      to={destination.path}
    >
      <Icon aria-hidden="true" className="size-[1.1rem]" />
      {!isCollapsed && <span>{destination.label}</span>}
    </NavLink>
  );

  if (!isCollapsed) return link;

  return (
    <Tooltip>
      <TooltipTrigger render={link} />
      <TooltipContent side="right">{destination.label}</TooltipContent>
    </Tooltip>
  );
}

export function AppShell({
  backupService,
  clientCatalog,
  projectCatalog,
  taskCatalog,
  lifecycle,
}: {
  backupService: BackupService;
  clientCatalog: ClientCatalog;
  projectCatalog: ProjectCatalog;
  taskCatalog: TaskCatalog;
  lifecycle?: CatalogLifecycle;
}) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const location = useLocation();
  const activeDestination =
    navigationDestinations.find(
      ({ path }) =>
        path === location.pathname ||
        (path !== "/" && location.pathname.startsWith(`${path}/`)),
    ) ?? navigationDestinations[0];

  return (
    <div className="flex h-screen min-h-[640px] overflow-hidden bg-muted/35">
      <a
        className="sr-only z-50 rounded-lg bg-background px-3 py-2 text-sm font-medium shadow-lg focus:not-sr-only focus:fixed focus:top-4 focus:left-4"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        Skip to main content
      </a>
      <aside
        aria-label="Application sidebar"
        className={cn(
          "relative flex shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-out motion-reduce:transition-none",
          isCollapsed ? "w-[4.5rem]" : "w-60",
        )}
      >
        <div className="flex h-16 items-center border-b px-4">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm shadow-primary/20">
            <Clock3 aria-hidden="true" className="size-[1.15rem]" />
          </div>
          {!isCollapsed && (
            <div className="ml-3 min-w-0">
              <p className="truncate text-sm font-semibold tracking-tight">
                Personal Timesheet
              </p>
              <p className="truncate text-[0.7rem] text-muted-foreground">
                Local workspace
              </p>
            </div>
          )}
        </div>

        <nav
          aria-label="Primary navigation"
          className="flex flex-1 flex-col gap-1 p-3"
        >
          {navigationDestinations.map((destination) => (
            <SidebarDestination
              key={destination.path}
              destination={destination}
              isCollapsed={isCollapsed}
            />
          ))}
        </nav>

        <div className="border-t p-3">
          <Button
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "text-muted-foreground",
              !isCollapsed && "w-full justify-start",
            )}
            onClick={() => setIsCollapsed((collapsed) => !collapsed)}
            size={isCollapsed ? "icon" : "default"}
            variant="ghost"
          >
            {isCollapsed ? (
              <ChevronsRight aria-hidden="true" />
            ) : (
              <>
                <ChevronsLeft aria-hidden="true" />
                <span>Collapse</span>
              </>
            )}
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between border-b bg-background/90 px-5 backdrop-blur">
          <p className="text-sm font-medium">Personal workspace</p>
          <ThemeMenu />
        </header>

        <main
          className="min-w-0 flex-1 overflow-auto p-8"
          data-density={activeDestination.density}
          id="main-content"
          tabIndex={-1}
        >
          <div
            className={cn(
              "mx-auto min-h-full",
              activeDestination.density === "compact"
                ? "max-w-none"
                : "max-w-6xl",
            )}
          >
            <Routes>
              <Route
                path="/clients/:clientId/projects/:projectId/tasks"
                element={
                  <Suspense fallback={<p role="status">Opening tasks…</p>}>
                    <TaskWorkspaceRoute
                      clientCatalog={clientCatalog}
                      projectCatalog={projectCatalog}
                      taskCatalog={taskCatalog}
                      lifecycle={lifecycle}
                    />
                  </Suspense>
                }
              />
              <Route path="/clients/:clientId/projects" element={<Suspense fallback={<p role="status">Opening projects…</p>}><ProjectWorkspaceRoute clientCatalog={clientCatalog} projectCatalog={projectCatalog} lifecycle={lifecycle} /></Suspense>} />
              {navigationDestinations.map((destination) => (
                <Route
                  key={destination.path}
                  element={
                    destination.path === "/clients" ? (
                      <Suspense
                        fallback={
                          <p className="text-sm text-muted-foreground" role="status">
                            Opening clients…
                          </p>
                        }
                      >
                        <ClientsPage catalog={clientCatalog} lifecycle={lifecycle} />
                      </Suspense>
                    ) : destination.path === "/settings" ? (
                      <Suspense
                        fallback={
                          <p className="text-sm text-muted-foreground" role="status">
                            Opening settings…
                          </p>
                        }
                      >
                        <SettingsDataPage service={backupService} />
                      </Suspense>
                    ) : (
                      <ProductPage destination={destination} />
                    )
                  }
                  path={destination.path}
                />
              ))}
              <Route path="*" element={<Navigate replace to="/" />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}
