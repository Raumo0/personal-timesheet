import { cleanup, render as testingLibraryRender, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";

import { CatalogLifecycleError } from "../catalog-lifecycle/catalog-lifecycle";
import { InMemoryCatalogLifecycle } from "../catalog-lifecycle/in-memory-catalog-lifecycle";
import type { Client } from "../clients/client";
import type { ProjectCatalog } from "./project-catalog";
import { InMemoryProjectCatalog } from "./in-memory-project-catalog";
import { ProjectsPage } from "./ProjectsPage";

const timestamp = "2026-08-02T10:00:00.000Z";
const earlierArchivedAt = "2026-08-01T09:00:00.000Z";
const appliedAt = "2026-08-03T12:00:00.000Z";

afterEach(cleanup);

function render(ui: React.ReactNode) {
  return testingLibraryRender(<MemoryRouter>{ui}</MemoryRouter>);
}

function lifecycleHarness(options: {
  archivedClient?: boolean;
  archivedProject?: boolean;
  applyFailure?: () => unknown | undefined;
} = {}) {
  const client: Client = {
    id: "client-1",
    name: "Acme",
    currencyCode: "EUR",
    hourlyRateMinor: 12_500,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt: options.archivedClient ? timestamp : null,
  };
  const lifecycle = new InMemoryCatalogLifecycle({
    hierarchy: {
      clients: [client],
      projects: [
        {
          id: "project-1",
          clientId: client.id,
          name: "Website",
          hourlyRateOverrideMinor: null,
          createdAt: timestamp,
          updatedAt: timestamp,
          archivedAt: options.archivedProject ? timestamp : null,
        },
        {
          id: "project-sibling",
          clientId: client.id,
          name: "Retained sibling",
          hourlyRateOverrideMinor: null,
          createdAt: timestamp,
          updatedAt: timestamp,
          archivedAt: earlierArchivedAt,
        },
      ],
      tasks: [
        {
          id: "task-active",
          projectId: "project-1",
          name: "Research",
          hourlyRateOverrideMinor: null,
          createdAt: timestamp,
          updatedAt: timestamp,
          archivedAt: options.archivedProject ? timestamp : null,
        },
        {
          id: "task-archived",
          projectId: "project-1",
          name: "Retired review",
          hourlyRateOverrideMinor: null,
          createdAt: timestamp,
          updatedAt: timestamp,
          archivedAt: earlierArchivedAt,
        },
        {
          id: "task-sibling",
          projectId: "project-sibling",
          name: "Sibling task",
          hourlyRateOverrideMinor: null,
          createdAt: timestamp,
          updatedAt: timestamp,
          archivedAt: earlierArchivedAt,
        },
      ],
    },
    now: () => new Date(appliedAt),
    applyFailure: options.applyFailure,
  });
  const catalog: ProjectCatalog = {
    list: async (clientId, filter) =>
      lifecycle
        .snapshot()
        .projects.filter(
          (project) =>
            project.clientId === clientId &&
            (filter === "active"
              ? project.archivedAt === null
              : project.archivedAt !== null),
        ),
    get: async () => lifecycle.snapshot().projects[0],
    create: async () => lifecycle.snapshot().projects[0],
    update: async () => lifecycle.snapshot().projects[0],
  };
  return { catalog, client, lifecycle };
}

test("shows an empty project workspace with a create action", async () => {
  render(
    <ProjectsPage
      client={{ id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: 12_500, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }}
      catalog={new InMemoryProjectCatalog()}
    />,
  );

  expect(await screen.findByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add project" })).toBeInTheDocument();
});

test("shows an active project's effective client rate", async () => {
  render(
    <ProjectsPage
      client={{ id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: 12_500, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }}
      catalog={new InMemoryProjectCatalog({ projects: [{ id: "project-1", clientId: "client-1", name: "Website", hourlyRateOverrideMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }] })}
    />,
  );

  expect(await screen.findByText("Website")).toBeInTheDocument();
  expect(screen.getByText("€125.00")).toBeInTheDocument();
  expect(screen.getByText("Client default")).toBeInTheDocument();
});

test("links the project name to its task screen without replacing row actions", async () => {
  render(
    <ProjectsPage
      client={{ id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: 12_500, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }}
      catalog={new InMemoryProjectCatalog({ projects: [{ id: "project-1", clientId: "client-1", name: "Website", hourlyRateOverrideMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }] })}
    />,
  );

  expect(await screen.findByRole("link", { name: "Website" })).toHaveAttribute(
    "href",
    "/clients/client-1/projects/project-1/tasks",
  );
  expect(screen.getByRole("button", { name: "Edit Website" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Archive Website" })).toBeInTheDocument();
});

test("keeps archived projects out of the active workspace", async () => {
  render(<ProjectsPage client={{ id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }} catalog={new InMemoryProjectCatalog({ projects: [{ id: "project-1", clientId: "client-1", name: "Old site", hourlyRateOverrideMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: "2026-08-02T10:00:00.000Z" }] })} />);
  expect(await screen.findByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
  expect(screen.queryByText("Old site")).not.toBeInTheDocument();
});

test("opens archived projects in a separate view", async () => {
  const user = userEvent.setup();
  render(<ProjectsPage client={{ id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }} catalog={new InMemoryProjectCatalog({ projects: [{ id: "project-1", clientId: "client-1", name: "Old site", hourlyRateOverrideMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: "2026-08-02T10:00:00.000Z" }] })} />);
  await user.click(screen.getByRole("button", { name: "Archived" }));
  expect(await screen.findByText("Old site")).toBeInTheDocument();
});

test("recovers from a project catalog read failure", async () => {
  const list = vi
    .fn()
    .mockRejectedValueOnce(new Error("database locked"))
    .mockResolvedValueOnce([]);
  const user = userEvent.setup();

  render(
    <ProjectsPage
      client={{ id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }}
      catalog={{ list, get: async () => { throw new Error("not used"); }, create: async () => { throw new Error("not used"); }, update: async () => { throw new Error("not used"); } }}
    />,
  );

  expect(await screen.findByText("Projects could not be loaded")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
});

test("opens an active project for editing", async () => {
  const user = userEvent.setup();
  render(
    <ProjectsPage
      client={{ id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }}
      catalog={new InMemoryProjectCatalog({ projects: [{ id: "project-1", clientId: "client-1", name: "Website", hourlyRateOverrideMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }] })}
    />,
  );

  await user.click(await screen.findByRole("button", { name: "Edit Website" }));
  expect(screen.getByRole("dialog", { name: "Edit project" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Project name" })).toHaveValue("Website");
});

test("archives an active project after confirmation", async () => {
  const user = userEvent.setup();
  const { catalog, client, lifecycle } = lifecycleHarness();
  render(
    <ProjectsPage
      client={client}
      catalog={catalog}
      lifecycle={lifecycle}
    />,
  );

  await user.click(await screen.findByRole("button", { name: "Archive Website" }));
  expect(screen.getByRole("alertdialog", { name: "Archive Website?" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Archive project" }));
  expect(await screen.findByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
});

test("keeps an archived client's project workspace read-only", async () => {
  render(
    <ProjectsPage
      client={{ id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: "2026-08-02T11:00:00.000Z" }}
      catalog={new InMemoryProjectCatalog({ projects: [{ id: "project-1", clientId: "client-1", name: "Website", hourlyRateOverrideMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }] })}
    />,
  );

  expect(await screen.findByText("Website")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add project" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Edit Website" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Archive Website" })).not.toBeInTheDocument();
});

test("describes every Task beneath a Project before archive confirmation", async () => {
  const user = userEvent.setup();
  const { catalog, client, lifecycle } = lifecycleHarness();
  render(<ProjectsPage client={client} catalog={catalog} lifecycle={lifecycle} />);
  await screen.findByText("Website");

  await user.click(screen.getByRole("button", { name: "Archive Website" }));

  const dialog = await screen.findByRole("alertdialog");
  expect(dialog).toHaveTextContent("Archive Website?");
  expect(dialog).toHaveTextContent(
    "Archive Website and every Task beneath it (2 Tasks).",
  );
});

test("archives active Tasks but preserves an already archived Task timestamp", async () => {
  const user = userEvent.setup();
  const { catalog, client, lifecycle } = lifecycleHarness();
  render(<ProjectsPage client={client} catalog={catalog} lifecycle={lifecycle} />);
  await screen.findByText("Website");

  await user.click(screen.getByRole("button", { name: "Archive Website" }));
  await user.click(await screen.findByRole("button", { name: "Archive project" }));

  expect(await screen.findByRole("heading", { name: "No projects yet" })).toBeInTheDocument();
  const snapshot = lifecycle.snapshot();
  expect(snapshot.projects[0].archivedAt).toBe(appliedAt);
  expect(snapshot.tasks[0].archivedAt).toBe(appliedAt);
  expect(snapshot.tasks[1].archivedAt).toBe(earlierArchivedAt);
});

test("cancels Project archive without changing the Project or its Tasks", async () => {
  const user = userEvent.setup();
  const { catalog, client, lifecycle } = lifecycleHarness();
  render(<ProjectsPage client={client} catalog={catalog} lifecycle={lifecycle} />);
  await screen.findByText("Website");

  await user.click(screen.getByRole("button", { name: "Archive Website" }));
  await user.click(await screen.findByRole("button", { name: "Cancel" }));

  expect(screen.getByText("Website")).toBeInTheDocument();
  expect(lifecycle.snapshot().projects[0].archivedAt).toBeNull();
  expect(lifecycle.snapshot().tasks[0].archivedAt).toBeNull();
  expect(lifecycle.snapshot().tasks[1].archivedAt).toBe(earlierArchivedAt);
});

test("restores an archived Client and Project while Tasks and siblings stay archived", async () => {
  const user = userEvent.setup();
  const { catalog, client, lifecycle } = lifecycleHarness({
    archivedClient: true,
    archivedProject: true,
  });
  render(<ProjectsPage client={client} catalog={catalog} lifecycle={lifecycle} />);

  expect(screen.getByText(/Acme is archived/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Archived" }));
  await screen.findByText("Website");
  await user.click(screen.getByRole("button", { name: "Restore Website" }));

  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    "Restore Acme and Website. Tasks beneath Website remain archived.",
  );
  await user.click(screen.getByRole("button", { name: "Restore project" }));

  const snapshot = lifecycle.snapshot();
  expect(snapshot.clients[0].archivedAt).toBeNull();
  expect(snapshot.projects[0].archivedAt).toBeNull();
  expect(snapshot.tasks[0].archivedAt).toBe(timestamp);
  expect(snapshot.tasks[1].archivedAt).toBe(earlierArchivedAt);
  expect(snapshot.projects[1].archivedAt).toBe(earlierArchivedAt);
  expect(snapshot.tasks[2].archivedAt).toBe(earlierArchivedAt);
});

test("restores focus to the Project action after cancelling confirmation", async () => {
  const user = userEvent.setup();
  const { catalog, client, lifecycle } = lifecycleHarness();
  render(<ProjectsPage client={client} catalog={catalog} lifecycle={lifecycle} />);
  const archive = await screen.findByRole("button", { name: "Archive Website" });

  await user.click(archive);
  await user.click(await screen.findByRole("button", { name: "Cancel" }));

  expect(archive).toHaveFocus();
});

test("keeps a persistence error visible and Retry opens a fresh Project preview", async () => {
  let fail = true;
  const user = userEvent.setup();
  const { catalog, client, lifecycle } = lifecycleHarness({
    applyFailure: () => {
      if (!fail) return undefined;
      fail = false;
      return new CatalogLifecycleError("persistence", "The Project hierarchy was not saved");
    },
  });
  render(<ProjectsPage client={client} catalog={catalog} lifecycle={lifecycle} />);
  await screen.findByText("Website");

  await user.click(screen.getByRole("button", { name: "Archive Website" }));
  await user.click(await screen.findByRole("button", { name: "Archive project" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("not saved");
  const changed = lifecycle.snapshot();
  lifecycle.replaceSnapshot({
    ...changed,
    tasks: [
      ...changed.tasks,
      {
        ...changed.tasks[0],
        id: "task-new",
        name: "Delivery",
      },
    ],
  });
  await user.click(screen.getByRole("button", { name: "Retry" }));

  expect(await screen.findByRole("alertdialog")).toHaveTextContent("3 Tasks");
});
