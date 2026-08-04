import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";
import { vi } from "vitest";

import { CatalogLifecycleError } from "../catalog-lifecycle/catalog-lifecycle";
import { InMemoryCatalogLifecycle } from "../catalog-lifecycle/in-memory-catalog-lifecycle";
import type { Client } from "./client";
import type { ClientCatalog } from "./client-catalog";
import { InMemoryClientCatalog } from "./in-memory-client-catalog";
import { ClientsPage } from "./ClientsPage";

const timestamp = "2026-07-31T10:00:00.000Z";
const appliedAt = "2026-08-03T12:00:00.000Z";

function client(overrides: Partial<Client> = {}): Client {
  return {
    id: "client-1",
    name: "Acme Studio",
    currencyCode: "EUR",
    hourlyRateMinor: 12_500,
    createdAt: timestamp,
    updatedAt: timestamp,
    archivedAt: null,
    ...overrides,
  };
}

function lifecycleHarness(options: {
  archived?: boolean;
  applyFailure?: () => unknown | undefined;
} = {}) {
  const archivedAt = options.archived ? timestamp : null;
  const lifecycle = new InMemoryCatalogLifecycle({
    hierarchy: {
      clients: [client({ archivedAt })],
      projects: [
        {
          id: "project-1",
          clientId: "client-1",
          name: "Website",
          hourlyRateOverrideMinor: null,
          createdAt: timestamp,
          updatedAt: timestamp,
          archivedAt,
        },
      ],
      tasks: [
        {
          id: "task-1",
          projectId: "project-1",
          name: "Research",
          hourlyRateOverrideMinor: null,
          createdAt: timestamp,
          updatedAt: timestamp,
          archivedAt,
        },
      ],
    },
    now: () => new Date(appliedAt),
    applyFailure: options.applyFailure,
  });
  const catalog: ClientCatalog = {
    list: async (filter) =>
      lifecycle
        .snapshot()
        .clients.filter((candidate) =>
          filter === "active"
            ? candidate.archivedAt === null
            : candidate.archivedAt !== null,
        ),
    get: async () => lifecycle.snapshot().clients[0],
    create: async () => client(),
    update: async () => client(),
  };
  return { catalog, lifecycle };
}

afterEach(cleanup);

describe("Clients page", () => {
  test("links each client to its project workspace", async () => {
    render(<ClientsPage catalog={new InMemoryClientCatalog({ clients: [client()] })} />);

    expect(await screen.findByRole("link", { name: "Acme Studio" })).toHaveAttribute(
      "href",
      "#/clients/client-1/projects",
    );
  });

  test("shows a loading state while local data is being read", () => {
    const catalog: ClientCatalog = {
      list: () => new Promise(() => undefined),
      get: async () => client(),
      create: async () => client(),
      update: async () => client(),
    };

    render(<ClientsPage catalog={catalog} />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading clients");
  });

  test("shows a useful empty state", async () => {
    render(<ClientsPage catalog={new InMemoryClientCatalog()} />);

    expect(
      await screen.findByRole("heading", { name: "No clients yet" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Add your first client" }),
    ).toBeInTheDocument();
  });

  test("keeps active and archived clients in separate views", async () => {
    render(
      <ClientsPage
        catalog={
          new InMemoryClientCatalog({
            clients: [
              client(),
              client({
                id: "client-2",
                name: "Northwind",
                archivedAt: timestamp,
              }),
            ],
          })
        }
      />,
    );

    expect(await screen.findByText("Acme Studio")).toBeInTheDocument();
    expect(screen.queryByText("Northwind")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Archived" }));

    expect(await screen.findByText("Northwind")).toBeInTheDocument();
    expect(screen.queryByText("Acme Studio")).not.toBeInTheDocument();
  });

  test.each([
    ["125.50", "€125.50"],
    ["", "Not set"],
    ["0", "€0.00"],
  ])("creates a client with rate %s", async (rate, expectedRate) => {
    const user = userEvent.setup();
    render(<ClientsPage catalog={new InMemoryClientCatalog()} />);
    await screen.findByRole("heading", { name: "No clients yet" });

    await user.click(screen.getByRole("button", { name: "Add client" }));
    await user.type(screen.getByRole("textbox", { name: "Client name" }), "Acme");
    if (rate) {
      await user.type(
        screen.getByRole("textbox", { name: "Default hourly rate" }),
        rate,
      );
    }
    await user.click(screen.getByRole("button", { name: "Save client" }));

    expect(await screen.findByText("Acme")).toBeInTheDocument();
    expect(screen.getByText(expectedRate)).toBeInTheDocument();
  });

  test("preserves input and identifies invalid rates", async () => {
    const user = userEvent.setup();
    render(<ClientsPage catalog={new InMemoryClientCatalog()} />);
    await screen.findByRole("heading", { name: "No clients yet" });

    await user.click(screen.getByRole("button", { name: "Add client" }));
    await user.type(screen.getByRole("textbox", { name: "Client name" }), "Acme");
    const rateInput = screen.getByRole("textbox", {
      name: "Default hourly rate",
    });
    await user.type(rateInput, "-1");
    await user.click(screen.getByRole("button", { name: "Save client" }));

    expect(rateInput).toHaveValue("-1");
    expect(screen.getByText(/non-negative rate/i)).toBeInTheDocument();
  });

  test("edits an active client with the shared form", async () => {
    const user = userEvent.setup();
    render(
      <ClientsPage
        catalog={new InMemoryClientCatalog({ clients: [client()] })}
      />,
    );
    await screen.findByText("Acme Studio");

    await user.click(screen.getByRole("button", { name: "Edit Acme Studio" }));
    expect(screen.getByRole("heading", { name: "Edit client" })).toBeInTheDocument();
    const nameInput = screen.getByRole("textbox", { name: "Client name" });
    await user.clear(nameInput);
    await user.type(nameInput, "Acme Europe");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Acme Europe")).toBeInTheDocument();
    expect(screen.queryByText("Acme Studio")).not.toBeInTheDocument();
  });

  test("requires archival confirmation and respects cancel", async () => {
    const user = userEvent.setup();
    const { catalog, lifecycle } = lifecycleHarness();
    render(
      <ClientsPage
        catalog={catalog}
        lifecycle={lifecycle}
      />,
    );
    await screen.findByText("Acme Studio");

    await user.click(
      screen.getByRole("button", { name: "Archive Acme Studio" }),
    );
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Acme Studio")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Archive Acme Studio" }),
    );
    await user.click(screen.getByRole("button", { name: "Archive client" }));
    expect(await screen.findByRole("heading", { name: "No clients yet" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Archived" }));
    expect(await screen.findByText("Acme Studio")).toBeInTheDocument();
  });

  test("recovers from a load failure with retry", async () => {
    const list = vi
      .fn<ClientCatalog["list"]>()
      .mockRejectedValueOnce(new Error("database locked"))
      .mockResolvedValueOnce([client()]);
    const catalog: ClientCatalog = {
      list,
      get: async () => client(),
      create: async () => client(),
      update: async () => client(),
    };
    const user = userEvent.setup();
    render(<ClientsPage catalog={catalog} />);

    expect(
      await screen.findByText("Clients could not be loaded"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Acme Studio")).toBeInTheDocument();
  });

  test("preserves the form when a save fails", async () => {
    const catalog: ClientCatalog = {
      list: async () => [],
      get: async () => client(),
      create: async () => {
        throw new Error("The local change was not saved");
      },
      update: async () => client(),
    };
    const user = userEvent.setup();
    render(<ClientsPage catalog={catalog} />);
    await screen.findByRole("heading", { name: "No clients yet" });

    await user.click(screen.getByRole("button", { name: "Add client" }));
    const nameInput = screen.getByRole("textbox", { name: "Client name" });
    await user.type(nameInput, "Acme");
    await user.click(screen.getByRole("button", { name: "Save client" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("not saved");
    expect(nameInput).toHaveValue("Acme");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  test("describes the complete Client archive scope before confirmation", async () => {
    const user = userEvent.setup();
    const { catalog, lifecycle } = lifecycleHarness();
    render(<ClientsPage catalog={catalog} lifecycle={lifecycle} />);
    await screen.findByText("Acme Studio");

    await user.click(screen.getByRole("button", { name: "Archive Acme Studio" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Archive Acme Studio?");
    expect(dialog).toHaveTextContent(
      "Archive Acme Studio and every Project and Task beneath it (1 Project, 1 Task).",
    );
  });

  test("cancels archive without changing the hierarchy", async () => {
    const user = userEvent.setup();
    const { catalog, lifecycle } = lifecycleHarness();
    render(<ClientsPage catalog={catalog} lifecycle={lifecycle} />);
    await screen.findByText("Acme Studio");

    await user.click(screen.getByRole("button", { name: "Archive Acme Studio" }));
    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(screen.getByText("Acme Studio")).toBeInTheDocument();
    expect(lifecycle.snapshot().clients[0].archivedAt).toBeNull();
    expect(lifecycle.snapshot().projects[0].archivedAt).toBeNull();
    expect(lifecycle.snapshot().tasks[0].archivedAt).toBeNull();
  });

  test("restores an archived Client while its descendants remain archived", async () => {
    const user = userEvent.setup();
    const { catalog, lifecycle } = lifecycleHarness({ archived: true });
    render(<ClientsPage catalog={catalog} lifecycle={lifecycle} />);

    await user.click(screen.getByRole("button", { name: "Archived" }));
    await screen.findByText("Acme Studio");
    await user.click(screen.getByRole("button", { name: "Restore Acme Studio" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(
      "Restore Acme Studio only. Archived Projects and Tasks remain archived.",
    );
    await user.click(screen.getByRole("button", { name: "Restore client" }));

    expect(await screen.findByRole("heading", { name: "No archived clients" })).toBeInTheDocument();
    expect(lifecycle.snapshot().clients[0].archivedAt).toBeNull();
    expect(lifecycle.snapshot().projects[0].archivedAt).toBe(timestamp);
    expect(lifecycle.snapshot().tasks[0].archivedAt).toBe(timestamp);
  });

  test("restores focus to the initiating action when confirmation is cancelled", async () => {
    const user = userEvent.setup();
    const { catalog, lifecycle } = lifecycleHarness();
    render(<ClientsPage catalog={catalog} lifecycle={lifecycle} />);
    const archive = await screen.findByRole("button", {
      name: "Archive Acme Studio",
    });

    await user.click(archive);
    await user.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(archive).toHaveFocus();
  });

  test("keeps a stale-plan error visible and Retry requests a fresh preview", async () => {
    const user = userEvent.setup();
    const { catalog, lifecycle } = lifecycleHarness();
    render(<ClientsPage catalog={catalog} lifecycle={lifecycle} />);
    await screen.findByText("Acme Studio");

    await user.click(screen.getByRole("button", { name: "Archive Acme Studio" }));
    await screen.findByRole("alertdialog");
    const changed = lifecycle.snapshot();
    lifecycle.replaceSnapshot({
      ...changed,
      tasks: [
        ...changed.tasks,
        {
          ...changed.tasks[0],
          id: "task-2",
          name: "Delivery",
        },
      ],
    });
    await user.click(screen.getByRole("button", { name: "Archive client" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/stale/i);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "1 Project, 2 Tasks",
    );
  });

  test("keeps a persistence error visible and Retry previews before applying again", async () => {
    let fail = true;
    const user = userEvent.setup();
    const { catalog, lifecycle } = lifecycleHarness({
      applyFailure: () => {
        if (!fail) return undefined;
        fail = false;
        return new CatalogLifecycleError("persistence", "The hierarchy was not saved");
      },
    });
    render(<ClientsPage catalog={catalog} lifecycle={lifecycle} />);
    await screen.findByText("Acme Studio");

    await user.click(screen.getByRole("button", { name: "Archive Acme Studio" }));
    await user.click(await screen.findByRole("button", { name: "Archive client" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("not saved");
    expect(screen.getByText("Acme Studio")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "Archive Acme Studio and every Project and Task beneath it",
    );
    await user.click(screen.getByRole("button", { name: "Archive client" }));

    expect(await screen.findByRole("heading", { name: "No clients yet" })).toBeInTheDocument();
  });
});
