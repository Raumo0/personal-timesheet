import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";

import { CatalogLifecycleError } from "../catalog-lifecycle/catalog-lifecycle";
import { InMemoryCatalogLifecycle } from "../catalog-lifecycle/in-memory-catalog-lifecycle";
import type { Client } from "../clients/client";
import type { Project } from "../projects/project";
import { InMemoryTaskCatalog } from "./in-memory-task-catalog";
import type { TaskCatalog } from "./task-catalog";
import type { Task } from "./task";
import { TasksPage } from "./TasksPage";

afterEach(cleanup);

const timestamp = "2026-08-03T08:00:00.000Z";
const siblingArchivedAt = "2026-08-02T07:00:00.000Z";
const appliedAt = "2026-08-04T12:00:00.000Z";

const client: Client = {
  id: "client-1",
  name: "Acme",
  currencyCode: "EUR",
  hourlyRateMinor: 12_500,
  createdAt: timestamp,
  updatedAt: timestamp,
  archivedAt: null,
};

const project: Project = {
  id: "project-1",
  clientId: client.id,
  name: "Website",
  hourlyRateOverrideMinor: 15_000,
  createdAt: timestamp,
  updatedAt: timestamp,
  archivedAt: null,
};

function task(
  id: string,
  name: string,
  hourlyRateOverrideMinor: number | null,
  archivedAt: string | null = null,
): Task {
  return {
    id,
    projectId: project.id,
    name,
    hourlyRateOverrideMinor,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt,
  };
}

function renderPage(
  catalog: TaskCatalog,
  options: {
    client?: Client;
    project?: Project;
    lifecycle?: InMemoryCatalogLifecycle;
  } = {},
) {
  return render(
    <MemoryRouter>
      <TasksPage
        client={options.client ?? client}
        project={options.project ?? project}
        catalog={catalog}
        lifecycle={options.lifecycle}
      />
    </MemoryRouter>,
  );
}

function lifecycleHarness(options: {
  archivedAncestors?: boolean;
  archivedTask?: boolean;
  applyFailure?: () => unknown | undefined;
} = {}) {
  const targetClient = {
    ...client,
    archivedAt: options.archivedAncestors ? timestamp : null,
  };
  const targetProject = {
    ...project,
    archivedAt: options.archivedAncestors ? timestamp : null,
  };
  const lifecycle = new InMemoryCatalogLifecycle({
    hierarchy: {
      clients: [targetClient],
      projects: [
        targetProject,
        {
          ...project,
          id: "project-sibling",
          name: "Sibling project",
          archivedAt: siblingArchivedAt,
        },
      ],
      tasks: [
        task(
          "task-1",
          "Research",
          null,
          options.archivedTask ? timestamp : null,
        ),
        task("task-sibling", "Sibling task", null, siblingArchivedAt),
        {
          ...task("task-other-project", "Other project task", null),
          projectId: "project-sibling",
          archivedAt: siblingArchivedAt,
        },
      ],
    },
    now: () => new Date(appliedAt),
    applyFailure: options.applyFailure,
  });
  const catalog: TaskCatalog = {
    list: async (projectId, filter) =>
      lifecycle
        .snapshot()
        .tasks.filter(
          (candidate) =>
            candidate.projectId === projectId &&
            (filter === "active"
              ? candidate.archivedAt === null
              : candidate.archivedAt !== null),
        ),
    create: async () => lifecycle.snapshot().tasks[0],
    update: async () => lifecycle.snapshot().tasks[0],
  };
  return { catalog, client: targetClient, lifecycle, project: targetProject };
}

function catalogWith(
  base: TaskCatalog,
  overrides: Partial<TaskCatalog>,
): TaskCatalog {
  return {
    list: base.list.bind(base),
    create: base.create.bind(base),
    update: base.update.bind(base),
    ...overrides,
  };
}

test("keeps archived tasks out of the default active view and lists them separately", async () => {
  const user = userEvent.setup();
  renderPage(
    new InMemoryTaskCatalog({
      tasks: [
        task("task-1", "Research", null),
        task("task-2", "Retired review", null, timestamp),
      ],
    }),
  );

  expect(await screen.findByText("Research")).toBeInTheDocument();
  expect(screen.queryByText("Retired review")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Active" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await user.click(screen.getByRole("button", { name: "Archived" }));

  expect(await screen.findByText("Retired review")).toBeInTheDocument();
  expect(screen.queryByText("Research")).not.toBeInTheDocument();
});

test("shows each task's rate mode, effective rate, and nearest source", async () => {
  renderPage(
    new InMemoryTaskCatalog({
      tasks: [
        task("task-1", "Task priced", 20_000),
        task("task-2", "Task free", 0),
        task("task-3", "Project priced", null),
      ],
    }),
  );

  const taskRateRow = within(
    (await screen.findByText("Task priced")).closest("tr")!,
  );
  expect(taskRateRow.getByText("Override")).toBeInTheDocument();
  expect(taskRateRow.getByText("Task override")).toBeInTheDocument();
  expect(taskRateRow.getByText("€200.00")).toBeInTheDocument();

  const zeroRow = within(screen.getByText("Task free").closest("tr")!);
  expect(zeroRow.getByText("Override")).toBeInTheDocument();
  expect(zeroRow.getByText("Task override")).toBeInTheDocument();
  expect(zeroRow.getByText("€0.00")).toBeInTheDocument();

  const projectRateRow = within(screen.getByText("Project priced").closest("tr")!);
  expect(projectRateRow.getByText("Inherited")).toBeInTheDocument();
  expect(projectRateRow.getByText("Project override")).toBeInTheDocument();
  expect(projectRateRow.getByText("€150.00")).toBeInTheDocument();
});

test("shows client and unset sources for tasks inheriting through the project", async () => {
  const catalog = new InMemoryTaskCatalog({ tasks: [task("task-1", "Research", null)] });
  const { unmount } = renderPage(catalog, {
    project: { ...project, hourlyRateOverrideMinor: null },
  });

  let row = within((await screen.findByText("Research")).closest("tr")!);
  expect(row.getByText("Inherited")).toBeInTheDocument();
  expect(row.getByText("Client default")).toBeInTheDocument();
  expect(row.getByText("€125.00")).toBeInTheDocument();

  unmount();
  renderPage(catalog, {
    client: { ...client, hourlyRateMinor: null },
    project: { ...project, hourlyRateOverrideMinor: null },
  });

  row = within((await screen.findByText("Research")).closest("tr")!);
  expect(row.getByText("Inherited")).toBeInTheDocument();
  expect(row.getByText("No rate set")).toBeInTheDocument();
  expect(row.getByText("Not set")).toBeInTheDocument();
});

test.each([
  {
    source: "project",
    zeroClient: client,
    zeroProject: { ...project, hourlyRateOverrideMinor: 0 },
    expectedSource: "Project override",
  },
  {
    source: "client",
    zeroClient: { ...client, hourlyRateMinor: 0 },
    zeroProject: { ...project, hourlyRateOverrideMinor: null },
    expectedSource: "Client default",
  },
])(
  "shows an inherited explicit zero from the $source as the nearest rate",
  async ({ zeroClient, zeroProject, expectedSource }) => {
    renderPage(
      new InMemoryTaskCatalog({ tasks: [task("task-1", "Research", null)] }),
      { client: zeroClient, project: zeroProject },
    );

    const row = within((await screen.findByText("Research")).closest("tr")!);
    expect(row.getByText("Inherited")).toBeInTheDocument();
    expect(row.getByText(expectedSource)).toBeInTheDocument();
    expect(row.getByText("€0.00")).toBeInTheDocument();
  },
);

test("archives only the selected Task after an exact confirmation", async () => {
  const user = userEvent.setup();
  const harness = lifecycleHarness();
  renderPage(harness.catalog, harness);
  await screen.findByText("Research");

  await user.click(screen.getByRole("button", { name: "Archive Research" }));
  const dialog = await screen.findByRole("alertdialog");
  expect(dialog).toHaveTextContent("Archive Research?");
  expect(dialog).toHaveTextContent("Archive Research.");
  await user.click(screen.getByRole("button", { name: "Archive task" }));

  expect(await screen.findByRole("heading", { name: "No tasks yet" })).toBeInTheDocument();
  const snapshot = harness.lifecycle.snapshot();
  expect(snapshot.clients[0].archivedAt).toBeNull();
  expect(snapshot.projects[0].archivedAt).toBeNull();
  expect(snapshot.tasks[0].archivedAt).toBe(appliedAt);
  expect(snapshot.tasks[1].archivedAt).toBe(siblingArchivedAt);
});

test("restores the Task and archived Client and Project but no siblings", async () => {
  const user = userEvent.setup();
  const harness = lifecycleHarness({
    archivedAncestors: true,
    archivedTask: true,
  });
  renderPage(harness.catalog, harness);

  const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
  expect(within(breadcrumb).getByText("Acme")).toBeInTheDocument();
  expect(within(breadcrumb).getByRole("link", { name: "Website" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Archived" }));
  await screen.findByText("Research");
  await user.click(screen.getByRole("button", { name: "Restore Research" }));

  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    "Restore Acme, Website, and Research. Sibling records remain unchanged.",
  );
  await user.click(screen.getByRole("button", { name: "Restore task" }));

  const snapshot = harness.lifecycle.snapshot();
  expect(snapshot.clients[0].archivedAt).toBeNull();
  expect(snapshot.projects[0].archivedAt).toBeNull();
  expect(snapshot.tasks[0].archivedAt).toBeNull();
  expect(snapshot.tasks[1].archivedAt).toBe(siblingArchivedAt);
  expect(snapshot.projects[1].archivedAt).toBe(siblingArchivedAt);
  expect(snapshot.tasks[2].archivedAt).toBe(siblingArchivedAt);
});

test("cancels Task archive without changing hierarchy state", async () => {
  const user = userEvent.setup();
  const harness = lifecycleHarness();
  renderPage(harness.catalog, harness);
  await screen.findByText("Research");

  await user.click(screen.getByRole("button", { name: "Archive Research" }));
  await user.click(await screen.findByRole("button", { name: "Cancel" }));

  expect(screen.getByText("Research")).toBeInTheDocument();
  expect(harness.lifecycle.snapshot().tasks[0].archivedAt).toBeNull();
  expect(harness.lifecycle.snapshot().tasks[1].archivedAt).toBe(siblingArchivedAt);
});

test("returns focus to the initiating Task action after cancel", async () => {
  const user = userEvent.setup();
  const harness = lifecycleHarness();
  renderPage(harness.catalog, harness);
  const archive = await screen.findByRole("button", { name: "Archive Research" });

  await user.click(archive);
  await user.click(await screen.findByRole("button", { name: "Cancel" }));

  expect(archive).toHaveFocus();
});

test("keeps a lifecycle apply error visible and Retry requests a fresh preview", async () => {
  let fail = true;
  const user = userEvent.setup();
  const harness = lifecycleHarness({
    applyFailure: () => {
      if (!fail) return undefined;
      fail = false;
      return new CatalogLifecycleError("persistence", "The Task was not saved");
    },
  });
  renderPage(harness.catalog, harness);
  await screen.findByText("Research");

  await user.click(screen.getByRole("button", { name: "Archive Research" }));
  await user.click(await screen.findByRole("button", { name: "Archive task" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("not saved");
  expect(harness.lifecycle.snapshot().tasks[0].archivedAt).toBeNull();
  const changed = harness.lifecycle.snapshot();
  harness.lifecycle.replaceSnapshot({
    ...changed,
    tasks: changed.tasks.map((candidate) =>
      candidate.id === "task-1"
        ? { ...candidate, name: "Updated research" }
        : candidate,
    ),
  });
  await user.click(screen.getByRole("button", { name: "Retry" }));

  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    "Archive Updated research.",
  );
});

test("shows an empty active workspace with a first-task create action", async () => {
  const user = userEvent.setup();
  renderPage(new InMemoryTaskCatalog());

  expect(await screen.findByRole("heading", { name: "No tasks yet" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Add your first task" }));
  expect(screen.getByRole("dialog", { name: "Add task" })).toBeInTheDocument();
});

test("announces loading and recovers from a task catalog read failure", async () => {
  let resolveLoad!: (tasks: Task[]) => void;
  const list = vi
    .fn<TaskCatalog["list"]>()
    .mockImplementationOnce(() => new Promise((resolve) => { resolveLoad = resolve; }))
    .mockRejectedValueOnce(new Error("database locked"))
    .mockResolvedValueOnce([]);
  const catalog: TaskCatalog = {
    list,
    create: async () => { throw new Error("not used"); },
    update: async () => { throw new Error("not used"); },
  };
  const user = userEvent.setup();
  renderPage(catalog);

  expect(screen.getByRole("status")).toHaveTextContent("Loading tasks…");
  resolveLoad([]);
  expect(await screen.findByRole("heading", { name: "No tasks yet" })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Archived" }));
  expect(await screen.findByText("Tasks could not be loaded")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "No archived tasks" })).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("heading", { name: "No archived tasks" })).toBeInTheDocument();
});

test("creates a task and shows it in the active list", async () => {
  const user = userEvent.setup();
  renderPage(new InMemoryTaskCatalog());

  await user.click(await screen.findByRole("button", { name: "Add task" }));
  await user.type(screen.getByRole("textbox", { name: "Task name" }), "Research");
  await user.click(screen.getByRole("button", { name: "Save task" }));

  expect(await screen.findByText("Research")).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "Add task" })).not.toBeInTheDocument();
});

test("discards an unfinished task when creation is cancelled", async () => {
  const user = userEvent.setup();
  renderPage(new InMemoryTaskCatalog());

  await user.click(await screen.findByRole("button", { name: "Add task" }));
  await user.type(screen.getByRole("textbox", { name: "Task name" }), "Research");
  await user.keyboard("{Escape}");

  expect(screen.queryByRole("dialog", { name: "Add task" })).not.toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: "No tasks yet" })).toBeInTheDocument();
  expect(screen.queryByText("Research")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Archived" }));
  expect(await screen.findByRole("heading", { name: "No archived tasks" })).toBeInTheDocument();
});

test("preserves create form context when the task cannot be saved", async () => {
  const catalog = catalogWith(new InMemoryTaskCatalog(), {
    create: async () => {
      throw new Error("Task was not saved because local data is unavailable");
    },
  });
  const user = userEvent.setup();
  renderPage(catalog);

  await user.click(await screen.findByRole("button", { name: "Add task" }));
  await user.type(screen.getByRole("textbox", { name: "Task name" }), "Research");
  await user.click(screen.getByRole("button", { name: "Save task" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/local data is unavailable/i);
  expect(screen.getByRole("dialog", { name: "Add task" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Task name" })).toHaveValue("Research");
});

test("edits a task and preserves edit context when persistence fails", async () => {
  const catalog = catalogWith(new InMemoryTaskCatalog({
    tasks: [task("task-1", "Research", null)],
  }), {
    update: async () => {
      throw new Error("Task changes were not saved");
    },
  });
  const user = userEvent.setup();
  renderPage(catalog);

  await user.click(await screen.findByRole("button", { name: "Edit Research" }));
  const name = screen.getByRole("textbox", { name: "Task name" });
  await user.clear(name);
  await user.type(name, "Discovery");
  await user.click(screen.getByRole("button", { name: "Save changes" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Task changes were not saved");
  expect(screen.getByRole("dialog", { name: "Edit task" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Task name" })).toHaveValue("Discovery");
  expect(screen.getByText("Research")).toBeInTheDocument();
});

test("saves task edits and refreshes the visible rate details", async () => {
  const user = userEvent.setup();
  renderPage(new InMemoryTaskCatalog({ tasks: [task("task-1", "Research", null)] }));

  await user.click(await screen.findByRole("button", { name: "Edit Research" }));
  const name = screen.getByRole("textbox", { name: "Task name" });
  await user.clear(name);
  await user.type(name, "Discovery");
  await user.click(screen.getByRole("radio", { name: "Override rate" }));
  await user.type(screen.getByRole("textbox", { name: "Hourly rate" }), "75");
  await user.click(screen.getByRole("button", { name: "Save changes" }));

  const row = within((await screen.findByText("Discovery")).closest("tr")!);
  expect(row.getByText("Override")).toBeInTheDocument();
  expect(row.getByText("Task override")).toBeInTheDocument();
  expect(row.getByText("€75.00")).toBeInTheDocument();
});

test("discards task edits when editing is cancelled", async () => {
  const user = userEvent.setup();
  renderPage(new InMemoryTaskCatalog({ tasks: [task("task-1", "Research", null)] }));

  await user.click(await screen.findByRole("button", { name: "Edit Research" }));
  const name = screen.getByRole("textbox", { name: "Task name" });
  await user.clear(name);
  await user.type(name, "Discovery");
  await user.click(screen.getByRole("radio", { name: "Override rate" }));
  await user.type(screen.getByRole("textbox", { name: "Hourly rate" }), "75");
  await user.keyboard("{Escape}");

  expect(screen.queryByRole("dialog", { name: "Edit task" })).not.toBeInTheDocument();
  const row = within((await screen.findByText("Research")).closest("tr")!);
  expect(row.queryByText("Discovery")).not.toBeInTheDocument();
  expect(row.getByText("Inherited")).toBeInTheDocument();
  expect(row.getByText("Project override")).toBeInTheDocument();
  expect(row.getByText("€150.00")).toBeInTheDocument();
});

test("cancels task archival without changing the active task", async () => {
  const user = userEvent.setup();
  const { catalog, lifecycle } = lifecycleHarness();
  renderPage(catalog, { lifecycle });

  await user.click(await screen.findByRole("button", { name: "Archive Research" }));
  expect(screen.getByRole("alertdialog", { name: "Archive Research?" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Cancel" }));

  expect(screen.queryByRole("alertdialog", { name: "Archive Research?" })).not.toBeInTheDocument();
  expect(screen.getByText("Research")).toBeInTheDocument();
});

test("confirms archival and moves the task to the archived view", async () => {
  const user = userEvent.setup();
  const { catalog, lifecycle } = lifecycleHarness();
  renderPage(catalog, { lifecycle });

  await user.click(await screen.findByRole("button", { name: "Archive Research" }));
  await user.click(screen.getByRole("button", { name: "Archive task" }));

  expect(await screen.findByRole("heading", { name: "No tasks yet" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Archived" }));
  expect(await screen.findByText("Research")).toBeInTheDocument();
});

test("keeps the active row when archival persistence fails", async () => {
  const { catalog, lifecycle } = lifecycleHarness({
    applyFailure: () => new Error("Task was not archived"),
  });
  const user = userEvent.setup();
  renderPage(catalog, { lifecycle });

  await user.click(await screen.findByRole("button", { name: "Archive Research" }));
  await user.click(screen.getByRole("button", { name: "Archive task" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Task was not archived");
  expect(screen.getByText("Research")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Archive Research" })).toBeInTheDocument();
});

test("shows Client, Project, and Tasks hierarchy with a project return link", async () => {
  renderPage(new InMemoryTaskCatalog());

  const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
  expect(within(breadcrumb).getByText("Acme")).toBeInTheDocument();
  expect(within(breadcrumb).getByText("Tasks")).toBeInTheDocument();
  expect(within(breadcrumb).getByRole("link", { name: "Website" })).toHaveAttribute(
    "href",
    "/clients/client-1/projects",
  );
  expect(await screen.findByRole("heading", { name: "Tasks" })).toBeInTheDocument();
});

test.each([
  {
    ancestor: "client",
    archivedClient: { ...client, archivedAt: timestamp },
    archivedProject: project,
  },
  {
    ancestor: "project",
    archivedClient: client,
    archivedProject: { ...project, archivedAt: timestamp },
  },
])(
  "keeps tasks read-only when the $ancestor is archived",
  async ({ archivedClient, archivedProject }) => {
    const user = userEvent.setup();
    renderPage(
      new InMemoryTaskCatalog({
        tasks: [
          task("task-1", "Research", null),
          task("task-2", "Retired review", null, timestamp),
        ],
      }),
      { client: archivedClient, project: archivedProject },
    );

    expect(await screen.findByText("Research")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add task" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Edit Research" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Archive Research" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Archived" }));
    expect(await screen.findByText("Retired review")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit Retired review/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Archive Retired review/ })).not.toBeInTheDocument();
  },
);

test.each([
  {
    ancestor: "client",
    archivedClient: { ...client, archivedAt: timestamp },
    archivedProject: project,
  },
  {
    ancestor: "project",
    archivedClient: client,
    archivedProject: { ...project, archivedAt: timestamp },
  },
])(
  "does not offer first-task creation in an empty archived-$ancestor workspace",
  async ({ archivedClient, archivedProject }) => {
    renderPage(new InMemoryTaskCatalog(), {
      client: archivedClient,
      project: archivedProject,
    });

    expect(await screen.findByRole("heading", { name: "No tasks yet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add task" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Add your first task" })).not.toBeInTheDocument();
  },
);
