import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { createHashRouter, MemoryRouter, RouterProvider } from "react-router";

import App from "@/App";
import { AppShell } from "@/app/AppShell";
import { ThemeProvider } from "@/app/theme/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { InMemoryCatalogLifecycle } from "@/features/catalog-lifecycle/in-memory-catalog-lifecycle";
import { InMemoryClientCatalog } from "@/features/clients/in-memory-client-catalog";
import { InMemoryProjectCatalog } from "@/features/projects/in-memory-project-catalog";
import { InMemoryTaskCatalog } from "@/features/tasks/in-memory-task-catalog";
import { InMemoryBackupService } from "@/features/backup/in-memory-backup-service";
import { InMemoryWeeklyTimeEntryStore } from "@/features/time-entry/in-memory-weekly-time-entry-store";
import type { TimeEntryNativeWindow } from "@/features/time-entry/time-entry-navigation-coordinator";
import type { WeeklyTimeEntryStore } from "@/features/time-entry/weekly-time-entry-store";
import { weekFromMonday } from "@/features/time-entry/weekly-time-entry";

const timestamp = "2026-08-03T08:00:00.000Z";
const client = { id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: 12_500, createdAt: timestamp, updatedAt: timestamp, archivedAt: null };
const project = { id: "project-1", clientId: client.id, name: "Website", hourlyRateOverrideMinor: null, createdAt: timestamp, updatedAt: timestamp, archivedAt: null };
const task = { id: "task-1", projectId: project.id, name: "Research", hourlyRateOverrideMinor: null, createdAt: timestamp, updatedAt: timestamp, archivedAt: null };
const weeklySeed = {
  clients: [{
    id: client.id,
    name: client.name,
    archivedAt: null,
    projects: [{
      id: project.id,
      name: project.name,
      archivedAt: null,
      tasks: [{ id: task.id, name: task.name, archivedAt: null }],
    }],
  }],
  entries: [{
    date: weekFromMonday("2026-08-03").dates[0],
    reference: { kind: "task" as const, taskId: task.id },
    minutes: 60,
  }],
};

function renderTaskRoute(
  path = "/clients/client-1/projects/project-1/tasks",
  catalogs = {
    clientCatalog: new InMemoryClientCatalog({ clients: [client] }),
    projectCatalog: new InMemoryProjectCatalog({ projects: [project] }),
    taskCatalog: new InMemoryTaskCatalog(),
  },
  lifecycle?: InMemoryCatalogLifecycle,
) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  return render(
    <ThemeProvider>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <AppShell
            backupService={new InMemoryBackupService()}
            clientCatalog={catalogs.clientCatalog}
            projectCatalog={catalogs.projectCatalog}
            taskCatalog={catalogs.taskCatalog}
            lifecycle={lifecycle}
          />
        </MemoryRouter>
      </TooltipProvider>
    </ThemeProvider>,
  );
}

function lifecycleHarness(archived = false) {
  const archivedAt = archived ? timestamp : null;
  const hierarchy = {
    clients: [{ ...client, archivedAt }],
    projects: [{ ...project, archivedAt }],
    tasks: [{ ...task, archivedAt }],
  };
  return {
    catalogs: {
      clientCatalog: new InMemoryClientCatalog({ clients: hierarchy.clients }),
      projectCatalog: new InMemoryProjectCatalog({ projects: hierarchy.projects }),
      taskCatalog: new InMemoryTaskCatalog({ tasks: hierarchy.tasks }),
    },
    lifecycle: new InMemoryCatalogLifecycle({ hierarchy }),
  };
}

function renderApp() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );

  return render(<App />);
}

function renderTimesheet(
  weeklyStore: WeeklyTimeEntryStore,
  nativeWindow?: TimeEntryNativeWindow,
  useHashRouter = false,
) {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  const shell = (
    <AppShell
      backupService={new InMemoryBackupService()}
      clientCatalog={new InMemoryClientCatalog()}
      lifecycle={new InMemoryCatalogLifecycle({
        hierarchy: { clients: [], projects: [], tasks: [] },
      })}
      nativeWindow={nativeWindow}
      projectCatalog={new InMemoryProjectCatalog()}
      taskCatalog={new InMemoryTaskCatalog()}
      weeklyStore={weeklyStore}
    />
  );
  return render(
    <ThemeProvider>
      <TooltipProvider>
        {useHashRouter ? (
          <RouterProvider
            router={createHashRouter([{ path: "*", element: shell }])}
          />
        ) : (
          <MemoryRouter>{shell}</MemoryRouter>
        )}
      </TooltipProvider>
    </ThemeProvider>,
  );
}

afterEach(() => {
  cleanup();
  window.location.hash = "";
  localStorage.clear();
  document.documentElement.classList.remove("light", "dark");
  vi.unstubAllGlobals();
});

describe("application shell", () => {
  test("opens Timesheet with all primary destinations available", async () => {
    renderApp();

    expect(
      await screen.findByRole("heading", { name: "Timesheet" }),
    ).toBeInTheDocument();

    const navigation = screen.getByRole("navigation", {
      name: "Primary navigation",
    });
    const destinations = within(navigation).getAllByRole("link");

    expect(destinations).toHaveLength(5);
    expect(
      within(navigation).getByRole("link", { name: "Timesheet" }),
    ).toHaveAttribute("aria-current", "page");
  });

  test("navigates to Reports and identifies it as active", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("link", { name: "Reports" }));

    expect(screen.getByRole("heading", { name: "Reports" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reports" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  test("opens Clients from persistent navigation with an injected catalog", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    render(
      <ThemeProvider>
        <TooltipProvider>
          <MemoryRouter>
            <AppShell
              backupService={new InMemoryBackupService()}
              clientCatalog={new InMemoryClientCatalog()}
              projectCatalog={new InMemoryProjectCatalog()}
              taskCatalog={new InMemoryTaskCatalog()}
            />
          </MemoryRouter>
        </TooltipProvider>
      </ThemeProvider>,
    );

    const clientsLink = screen.getByRole("link", { name: "Clients" });
    clientsLink.focus();
    await user.keyboard("{Enter}");

    expect(
      await screen.findByRole("heading", { name: "Clients" }),
    ).toBeInTheDocument();
    expect(clientsLink).toHaveAttribute("aria-current", "page");
    expect(
      await screen.findByRole("heading", { name: "No clients yet" }),
    ).toBeInTheDocument();
  });

  test("opens a client project workspace from its deep link", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    render(
      <ThemeProvider><TooltipProvider><MemoryRouter initialEntries={["/clients/client-1/projects"]}>
        <AppShell backupService={new InMemoryBackupService()} clientCatalog={new InMemoryClientCatalog({ clients: [{ id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: 12_500, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }] })} projectCatalog={new InMemoryProjectCatalog()} taskCatalog={new InMemoryTaskCatalog()} />
      </MemoryRouter></TooltipProvider></ThemeProvider>,
    );
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
  });

  test("recovers a failed Project context load on Retry", async () => {
    const user = userEvent.setup();
    const clientCatalog = new InMemoryClientCatalog({ clients: [client] });
    const list = clientCatalog.list.bind(clientCatalog);
    const readFailure = new Error("local catalog is temporarily unavailable");
    vi.spyOn(clientCatalog, "list")
      .mockRejectedValueOnce(readFailure)
      .mockImplementation(list);
    renderTaskRoute("/clients/client-1/projects", {
      clientCatalog,
      projectCatalog: new InMemoryProjectCatalog({ projects: [project] }),
      taskCatalog: new InMemoryTaskCatalog(),
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Projects could not be opened",
    );

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByText("Website")).toBeInTheDocument();
  });

  test("opens a project task workspace from its deep link", async () => {
    renderTaskRoute(
      "/clients/client-1/projects/project-1/tasks",
      {
        clientCatalog: new InMemoryClientCatalog({ clients: [client] }),
        projectCatalog: new InMemoryProjectCatalog({ projects: [project] }),
        taskCatalog: new InMemoryTaskCatalog({ tasks: [{ id: "task-1", projectId: project.id, name: "Research", hourlyRateOverrideMinor: null, createdAt: timestamp, updatedAt: timestamp, archivedAt: null }] }),
      },
    );

    expect(await screen.findByRole("heading", { name: "Tasks" })).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("Website")).toBeInTheDocument();
    expect(await screen.findByText("Research")).toBeInTheDocument();
  });

  test("injects lifecycle archive planning into the Client screen", async () => {
    const user = userEvent.setup();
    const harness = lifecycleHarness();
    renderTaskRoute("/clients", harness.catalogs, harness.lifecycle);
    await screen.findByText("Acme");

    await user.click(screen.getByRole("button", { name: "Archive Acme" }));

    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "Archive Acme and every Project and Task beneath it (1 Project, 1 Task).",
    );
  });

  test("injects lifecycle archive planning into the Project screen", async () => {
    const user = userEvent.setup();
    const harness = lifecycleHarness();
    renderTaskRoute(
      "/clients/client-1/projects",
      harness.catalogs,
      harness.lifecycle,
    );
    await screen.findByText("Website");

    await user.click(screen.getByRole("button", { name: "Archive Website" }));

    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "Archive Website and every Task beneath it (1 Task).",
    );
  });

  test("injects lifecycle archive planning into the Task screen", async () => {
    const user = userEvent.setup();
    const harness = lifecycleHarness();
    renderTaskRoute(
      "/clients/client-1/projects/project-1/tasks",
      harness.catalogs,
      harness.lifecycle,
    );
    await screen.findByText("Research");

    await user.click(screen.getByRole("button", { name: "Archive Research" }));

    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "Archive Research.",
    );
  });

  test("navigates from an archived Client into its retained Project workspace", async () => {
    const user = userEvent.setup();
    const harness = lifecycleHarness(true);
    renderTaskRoute("/clients", harness.catalogs, harness.lifecycle);

    await user.click(screen.getByRole("button", { name: "Archived" }));
    const clientLink = await screen.findByRole("link", { name: "Acme" });
    await user.click(clientLink);

    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByText(/Acme is archived/)).toBeInTheDocument();
  });

  test("preserves archived Client and Project context for Task restore", async () => {
    const user = userEvent.setup();
    const harness = lifecycleHarness(true);
    renderTaskRoute(
      "/clients/client-1/projects",
      harness.catalogs,
      harness.lifecycle,
    );

    await screen.findByRole("heading", { name: "Projects" });
    await user.click(screen.getByRole("button", { name: "Archived" }));
    await user.click(await screen.findByRole("link", { name: "Website" }));
    const breadcrumb = await screen.findByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByText("Acme")).toBeInTheDocument();
    expect(within(breadcrumb).getByRole("link", { name: "Website" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Archived" }));
    await user.click(await screen.findByRole("button", { name: "Restore Research" }));

    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "Restore Acme, Website, and Research. Sibling records remain unchanged.",
    );
  });

  test("reconstructs task context from catalog lookups after a direct refresh", async () => {
    renderTaskRoute();

    expect(await screen.findByRole("heading", { name: "Tasks" })).toBeInTheDocument();
    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByText("Acme")).toBeInTheDocument();
    expect(within(breadcrumb).getByRole("link", { name: "Website" })).toHaveAttribute(
      "href",
      "/clients/client-1/projects",
    );
  });

  test.each([
    {
      context: "missing client",
      catalogs: {
        clientCatalog: new InMemoryClientCatalog(),
        projectCatalog: new InMemoryProjectCatalog({ projects: [project] }),
        taskCatalog: new InMemoryTaskCatalog(),
      },
    },
    {
      context: "project belonging to another client",
      catalogs: {
        clientCatalog: new InMemoryClientCatalog({ clients: [client] }),
        projectCatalog: new InMemoryProjectCatalog({ projects: [{ ...project, clientId: "client-2" }] }),
        taskCatalog: new InMemoryTaskCatalog(),
      },
    },
  ])("shows a bounded unavailable state for $context", async ({ catalogs }) => {
    renderTaskRoute("/clients/client-1/projects/project-1/tasks", catalogs);

    expect(await screen.findByRole("heading", { name: "Task workspace unavailable" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Tasks" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to clients" })).toHaveAttribute(
      "href",
      "/clients",
    );
  });

  test("returns from tasks to the selected client's project workspace", async () => {
    const user = userEvent.setup();
    renderTaskRoute();

    await user.click(await screen.findByRole("link", { name: "Website" }));

    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByText(/Manage projects and rate choices for Acme/)).toBeInTheDocument();
  });

  test("shows a task-route fallback while lazy content and context are loading", async () => {
    let resolveClient!: (value: typeof client) => void;
    const clientCatalog = new InMemoryClientCatalog({ clients: [client] });
    vi.spyOn(clientCatalog, "get").mockImplementationOnce(
      () => new Promise((resolve) => { resolveClient = resolve; }),
    );
    renderTaskRoute("/clients/client-1/projects/project-1/tasks", {
      clientCatalog,
      projectCatalog: new InMemoryProjectCatalog({ projects: [project] }),
      taskCatalog: new InMemoryTaskCatalog(),
    });

    expect(screen.getByRole("status")).toHaveTextContent("Opening tasks…");
    resolveClient(client);
    expect(await screen.findByRole("heading", { name: "Tasks" })).toBeInTheDocument();
  });

  test("keeps Clients active on a nested task route", async () => {
    renderTaskRoute();

    expect(await screen.findByRole("heading", { name: "Tasks" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Clients" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  test("keeps destinations accessible when the sidebar is collapsed", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(
      screen.getByRole("button", { name: "Collapse sidebar" }),
    );

    expect(
      screen.getByRole("button", { name: "Expand sidebar" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Timesheet" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Clients" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reports" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Expenses" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  test("shows only the tooltip for the collapsed destination under the pointer", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("link", { name: "Reports" }));
    await user.click(screen.getByRole("link", { name: "Expenses" }));
    await user.click(screen.getByRole("link", { name: "Settings" }));
    await user.click(
      screen.getByRole("button", { name: "Collapse sidebar" }),
    );

    expect(screen.queryByText("Reports")).not.toBeInTheDocument();
    expect(screen.queryByText("Expenses")).not.toBeInTheDocument();

    await user.hover(screen.getByRole("link", { name: "Reports" }));

    expect(await screen.findByText("Reports")).toBeInTheDocument();
    expect(screen.queryByText("Expenses")).not.toBeInTheDocument();
  });

  test("uses compact density only for Timesheet", async () => {
    const user = userEvent.setup();
    renderApp();

    expect(screen.getByRole("main")).toHaveAttribute(
      "data-density",
      "compact",
    );

    await user.click(screen.getByRole("link", { name: "Settings" }));

    expect(screen.getByRole("main")).toHaveAttribute(
      "data-density",
      "comfortable",
    );
  });

  test("opens the real Settings data workspace with an injected service", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    render(
      <ThemeProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={["/settings"]}>
            <AppShell
              backupService={new InMemoryBackupService()}
              clientCatalog={new InMemoryClientCatalog()}
              projectCatalog={new InMemoryProjectCatalog()}
              taskCatalog={new InMemoryTaskCatalog()}
            />
          </MemoryRouter>
        </TooltipProvider>
      </ThemeProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Settings" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Back up data" }),
    ).toBeEnabled();

    await user.click(screen.getByRole("link", { name: "Reports" }));
    expect(screen.getByRole("heading", { name: "Reports" })).toBeInTheDocument();
  });

  test("keeps page chrome aligned across workspace densities", async () => {
    const user = userEvent.setup();
    renderApp();

    const main = screen.getByRole("main");

    expect(main).toHaveClass("p-8");
    expect(screen.getAllByText("Timesheet")).toHaveLength(2);
    expect(screen.getAllByText("Local workspace")).toHaveLength(1);

    await user.click(screen.getByRole("link", { name: "Reports" }));

    expect(main).toHaveClass("p-8");
    expect(screen.getAllByText("Reports")).toHaveLength(2);
  });

  test("moves focus directly to the main workspace", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(
      screen.getByRole("link", { name: "Skip to main content" }),
    );

    expect(screen.getByRole("main")).toHaveFocus();
  });

  test("opens the lazy Timesheet route with compact density and injected weekly data", async () => {
    renderTimesheet(new InMemoryWeeklyTimeEntryStore(weeklySeed), undefined, true);

    expect(screen.getByRole("main")).toHaveAttribute("data-density", "compact");
    expect(await screen.findByRole("heading", { name: "Timesheet" })).toBeInTheDocument();
    expect(
      await screen.findByRole("row", { name: "Acme · Website · Research · Task" }),
    ).toBeInTheDocument();
  });

  test("shows loading and recovers a failed Timesheet load on Retry", async () => {
    const store = new InMemoryWeeklyTimeEntryStore(weeklySeed);
    const loadWeek = store.loadWeek.bind(store);
    vi.spyOn(store, "loadWeek")
      .mockRejectedValueOnce(new Error("database unavailable"))
      .mockImplementation(loadWeek);
    const user = userEvent.setup();
    renderTimesheet(store);

    expect(screen.getByRole("status")).toHaveTextContent(/Opening timesheet|Loading timesheet/);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Timesheet could not be loaded",
    );
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("heading", { name: "Timesheet" })).toBeInTheDocument();
    expect(await screen.findByText("Research")).toBeInTheDocument();
  });

  test("coordinates guarded router navigation with Stay and Discard", async () => {
    const user = userEvent.setup();
    renderTimesheet(new InMemoryWeeklyTimeEntryStore(weeklySeed), undefined, true);
    const input = await screen.findByRole("textbox", {
      name: /Acme · Website · Research · Mon/,
    });
    await user.clear(input);
    await user.type(input, "invalid");

    await user.click(screen.getByRole("link", { name: "Reports" }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("Leave Timesheet?");
    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.getByRole("heading", { name: "Timesheet" })).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Reports" }));
    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeInTheDocument();
  });

  test("guards HashRouter back navigation with Stay and Discard", async () => {
    const user = userEvent.setup();
    renderTimesheet(new InMemoryWeeklyTimeEntryStore(weeklySeed), undefined, true);
    await screen.findByRole("heading", { name: "Timesheet" });
    await user.click(screen.getByRole("link", { name: "Reports" }));
    await user.click(screen.getByRole("link", { name: "Timesheet" }));
    const input = await screen.findByRole("textbox", {
      name: /Acme · Website · Research · Mon/,
    });
    await user.clear(input);
    await user.type(input, "invalid");

    act(() => window.history.back());

    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "Leave Timesheet?",
    );
    await user.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.getByRole("heading", { name: "Timesheet" })).toBeInTheDocument();

    act(() => window.history.back());
    await user.click(await screen.findByRole("button", { name: "Discard changes" }));
    expect(await screen.findByRole("heading", { name: "Reports" })).toBeInTheDocument();
  });

  test("allows an unguarded Tauri close to use the default close path", async () => {
    let closeRequest: ((event: { preventDefault(): void }) => void) | undefined;
    const nativeWindow: TimeEntryNativeWindow = {
      destroy: vi.fn().mockResolvedValue(undefined),
      onCloseRequested: vi.fn(async (handler) => {
        closeRequest = handler;
        return vi.fn();
      }),
    };
    renderTimesheet(new InMemoryWeeklyTimeEntryStore(weeklySeed), nativeWindow);
    await screen.findByRole("heading", { name: "Timesheet" });
    await waitFor(() => expect(closeRequest).toBeDefined());
    const preventDefault = vi.fn();

    closeRequest?.({ preventDefault });

    expect(preventDefault).not.toHaveBeenCalled();
    expect(nativeWindow.destroy).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  test("keeps the native window and draft unchanged after Stay", async () => {
    let closeRequest: ((event: { preventDefault(): void }) => void) | undefined;
    const nativeWindow: TimeEntryNativeWindow = {
      destroy: vi.fn().mockResolvedValue(undefined),
      onCloseRequested: vi.fn(async (handler) => {
        closeRequest = handler;
        return vi.fn();
      }),
    };
    const user = userEvent.setup();
    renderTimesheet(new InMemoryWeeklyTimeEntryStore(weeklySeed), nativeWindow);
    const input = await screen.findByRole("textbox", {
      name: /Acme · Website · Research · Mon/,
    });
    await user.clear(input);
    await user.type(input, "invalid");
    await waitFor(() => expect(closeRequest).toBeDefined());

    closeRequest?.({ preventDefault: vi.fn() });
    await user.click(await screen.findByRole("button", { name: "Stay" }));

    expect(input).toHaveValue("invalid");
    expect(nativeWindow.destroy).not.toHaveBeenCalled();
  });

  test("destroys once after Discard without re-entering native close", async () => {
    let closeRequest: ((event: { preventDefault(): void }) => void) | undefined;
    let closeEvents = 0;
    const nativeWindow: TimeEntryNativeWindow = {
      destroy: vi.fn().mockResolvedValue(undefined),
      onCloseRequested: vi.fn(async (handler) => {
        closeRequest = (event) => {
          closeEvents += 1;
          handler(event);
        };
        return vi.fn();
      }),
    };
    const user = userEvent.setup();
    renderTimesheet(new InMemoryWeeklyTimeEntryStore(weeklySeed), nativeWindow);
    const input = await screen.findByRole("textbox", {
      name: /Acme · Website · Research · Mon/,
    });
    await user.clear(input);
    await user.type(input, "invalid");
    await waitFor(() => expect(closeRequest).toBeDefined());
    const preventDefault = vi.fn();

    closeRequest?.({ preventDefault });
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "Close Personal Timesheet?",
    );
    await user.click(screen.getByRole("button", { name: "Discard changes" }));

    expect(nativeWindow.destroy).toHaveBeenCalledOnce();
    expect(closeEvents).toBe(1);
    expect(nativeWindow.onCloseRequested).toHaveBeenCalledOnce();
  });
});
