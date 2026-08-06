import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { WorkItemSelector } from "./WorkItemSelector";
import type { SelectableWork } from "./weekly-time-entry-store";

beforeEach(() => {
  vi.spyOn(document.documentElement, "clientWidth", "get").mockReturnValue(
    1024,
  );
  vi.spyOn(document.documentElement, "clientHeight", "get").mockReturnValue(
    768,
  );
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
    bottom: 132,
    height: 32,
    left: 100,
    right: 356,
    top: 100,
    width: 256,
    x: 100,
    y: 100,
    toJSON: () => ({}),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  document
    .querySelectorAll("[data-base-ui-portal]")
    .forEach((portal) => portal.remove());
});

function openSelector() {
  fireEvent.click(
    screen.getByRole("combobox", { name: "Select project or task" }),
  );
}

const work: readonly SelectableWork[] = [
  {
    client: { id: "client-1", name: "Acme" },
    projects: [
      {
        project: { id: "project-1", name: "Website" },
        tasks: [
          { id: "task-1", name: "Design" },
          { id: "task-2", name: "Research" },
        ],
      },
    ],
  },
  {
    client: { id: "client-2", name: "Globex" },
    projects: [
      {
        project: { id: "project-2", name: "Mobile app" },
        tasks: [],
      },
    ],
  },
];

test("groups direct Project and Task choices by Client hierarchy", async () => {
  render(
    <WorkItemSelector
      work={work}
      existingRowKeys={new Set()}
      onSelect={vi.fn()}
      onRequestFocus={vi.fn()}
    />,
  );

  openSelector();
  const listbox = screen.getByRole("listbox");
  expect(within(listbox).getByText("Acme")).toBeInTheDocument();
  expect(within(listbox).getByText("Globex")).toBeInTheDocument();
  expect(
    within(listbox).getByRole("option", { name: "Project · Website" }),
  ).toBeInTheDocument();
  expect(
    within(listbox).getByRole("option", { name: "Task · Design" }),
  ).toBeInTheDocument();
  expect(within(listbox).queryByText(/General Task/i)).not.toBeInTheDocument();
  expect(within(listbox).queryByText(/Archived/i)).not.toBeInTheDocument();
});

test("selects a direct Project and resets to the placeholder", async () => {
  const onSelect = vi.fn();
  render(
    <WorkItemSelector
      work={work}
      existingRowKeys={new Set()}
      onSelect={onSelect}
      onRequestFocus={vi.fn()}
    />,
  );

  const user = userEvent.setup();
  openSelector();
  await user.click(screen.getByRole("option", { name: "Project · Website" }));

  expect(onSelect).toHaveBeenCalledWith({
    kind: "project",
    projectId: "project-1",
  });
  expect(
    screen.getByRole("combobox", { name: "Select project or task" }),
  ).toHaveTextContent("Select project or task");
});

test("selects a Task with its discriminated identity", async () => {
  const onSelect = vi.fn();
  render(
    <WorkItemSelector
      work={work}
      existingRowKeys={new Set()}
      onSelect={onSelect}
      onRequestFocus={vi.fn()}
    />,
  );

  const user = userEvent.setup();
  openSelector();
  await user.click(screen.getByRole("option", { name: "Task · Design" }));

  expect(onSelect).toHaveBeenCalledWith({ kind: "task", taskId: "task-1" });
});

test("requests focus instead of duplicating an existing row", async () => {
  const onSelect = vi.fn();
  const onRequestFocus = vi.fn();
  render(
    <WorkItemSelector
      work={work}
      existingRowKeys={new Set(["task:task-1"])}
      onSelect={onSelect}
      onRequestFocus={onRequestFocus}
    />,
  );

  const user = userEvent.setup();
  openSelector();
  const existing = screen.getByRole("option", {
    name: "Task · Design Already added",
  });
  expect(existing).toHaveClass("bg-muted/60");
  expect(within(existing).getByText("Already added")).toBeInTheDocument();
  await user.click(existing);

  expect(onSelect).not.toHaveBeenCalled();
  expect(onRequestFocus).toHaveBeenCalledWith("task:task-1");
});

test("disables selection when no active work is available", () => {
  render(
    <WorkItemSelector
      work={[]}
      existingRowKeys={new Set()}
      onSelect={vi.fn()}
      onRequestFocus={vi.fn()}
    />,
  );

  expect(
    screen.getByRole("combobox", { name: "Select project or task" }),
  ).toBeDisabled();
});
