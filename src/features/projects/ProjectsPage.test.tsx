import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import userEvent from "@testing-library/user-event";

import { InMemoryProjectCatalog } from "./in-memory-project-catalog";
import { ProjectsPage } from "./ProjectsPage";

afterEach(cleanup);

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
  expect(screen.getByText(/€125\.00.*client/i)).toBeInTheDocument();
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
