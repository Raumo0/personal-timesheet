import { cleanup, render as testingLibraryRender, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";

import { InMemoryProjectCatalog } from "./in-memory-project-catalog";
import { ProjectsPage } from "./ProjectsPage";

afterEach(cleanup);

function render(ui: React.ReactNode) {
  return testingLibraryRender(<MemoryRouter>{ui}</MemoryRouter>);
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
      catalog={{ list, create: async () => { throw new Error("not used"); }, update: async () => { throw new Error("not used"); }, archive: async () => undefined }}
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
  render(
    <ProjectsPage
      client={{ id: "client-1", name: "Acme", currencyCode: "EUR", hourlyRateMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }}
      catalog={new InMemoryProjectCatalog({ projects: [{ id: "project-1", clientId: "client-1", name: "Website", hourlyRateOverrideMinor: null, createdAt: "2026-08-02T10:00:00.000Z", updatedAt: "2026-08-02T10:00:00.000Z", archivedAt: null }] })}
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
