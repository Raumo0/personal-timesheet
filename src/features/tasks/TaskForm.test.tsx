import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import type { Task } from "./task";
import { TaskForm } from "./TaskForm";

afterEach(cleanup);

const client = { currencyCode: "EUR", hourlyRateMinor: 12_500 };
const project = { hourlyRateOverrideMinor: 15_000 };

function task(hourlyRateOverrideMinor: number | null): Task {
  return {
    id: "task-1",
    projectId: "project-1",
    name: "Research",
    hourlyRateOverrideMinor,
    createdAt: "2026-08-03T08:00:00.000Z",
    updatedAt: "2026-08-03T08:00:00.000Z",
    archivedAt: null,
  };
}

test("shows the project rate as read-only when inheritance is selected", () => {
  render(
    <TaskForm
      open
      client={client}
      project={project}
      onOpenChange={vi.fn()}
      onSave={vi.fn()}
    />,
  );

  expect(screen.getByRole("dialog", { name: "Add task" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Inherit project rate" })).toBeChecked();
  expect(screen.getByText(/€150\.00.*project/i)).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Hourly rate" })).not.toBeInTheDocument();
});

test("shows the client fallback when the project has no override", () => {
  render(
    <TaskForm
      open
      client={client}
      project={{ hourlyRateOverrideMinor: null }}
      onOpenChange={vi.fn()}
      onSave={vi.fn()}
    />,
  );

  expect(screen.getByText(/€125\.00.*client/i)).toBeInTheDocument();
});

test("states that no inherited rate is set without changing mode", () => {
  render(
    <TaskForm
      open
      client={{ currencyCode: "EUR", hourlyRateMinor: null }}
      project={{ hourlyRateOverrideMinor: null }}
      onOpenChange={vi.fn()}
      onSave={vi.fn()}
    />,
  );

  expect(screen.getByText("No inherited rate is set")).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Inherit project rate" })).toBeChecked();
});

test("enables an override input in the client currency", async () => {
  const user = userEvent.setup();
  render(
    <TaskForm
      open
      client={client}
      project={project}
      onOpenChange={vi.fn()}
      onSave={vi.fn()}
    />,
  );

  await user.click(screen.getByRole("radio", { name: "Override rate" }));

  expect(screen.getByRole("textbox", { name: "Hourly rate" })).toBeEnabled();
  expect(screen.getByText("EUR")).toBeInTheDocument();
});

test("saves inheritance after switching from override back to inherit", async () => {
  const user = userEvent.setup();
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <TaskForm
      open
      client={client}
      project={project}
      onOpenChange={vi.fn()}
      onSave={onSave}
    />,
  );

  await user.type(screen.getByRole("textbox", { name: "Task name" }), "Research");
  await user.click(screen.getByRole("radio", { name: "Override rate" }));
  await user.type(screen.getByRole("textbox", { name: "Hourly rate" }), "75");
  await user.click(screen.getByRole("radio", { name: "Inherit project rate" }));
  await user.click(screen.getByRole("button", { name: "Save task" }));

  expect(onSave).toHaveBeenCalledWith({
    name: "Research",
    hourlyRateOverrideMinor: null,
  });
});

test("preserves the dialog and entered context after invalid override validation", async () => {
  const user = userEvent.setup();
  const onOpenChange = vi.fn();
  const onSave = vi.fn();
  render(
    <TaskForm
      open
      client={client}
      project={project}
      onOpenChange={onOpenChange}
      onSave={onSave}
    />,
  );

  await user.type(screen.getByRole("textbox", { name: "Task name" }), "Research");
  await user.click(screen.getByRole("radio", { name: "Override rate" }));
  await user.type(screen.getByRole("textbox", { name: "Hourly rate" }), "12.345");
  await user.click(screen.getByRole("button", { name: "Save task" }));

  expect(screen.getByRole("alert")).toHaveTextContent(/supported precision/i);
  expect(screen.getByRole("dialog", { name: "Add task" })).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Task name" })).toHaveValue("Research");
  expect(screen.getByRole("textbox", { name: "Hourly rate" })).toHaveValue("12.345");
  expect(onSave).not.toHaveBeenCalled();
  expect(onOpenChange).not.toHaveBeenCalledWith(false);
});

test.each([
  { enteredRate: "", expectedError: /enter an hourly rate/i },
  { enteredRate: "-1", expectedError: /cannot be negative/i },
])(
  "preserves context when the override rate '$enteredRate' is invalid",
  async ({ enteredRate, expectedError }) => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    const onSave = vi.fn();
    render(
      <TaskForm
        open
        client={client}
        project={project}
        onOpenChange={onOpenChange}
        onSave={onSave}
      />,
    );

    await user.type(screen.getByRole("textbox", { name: "Task name" }), "Research");
    await user.click(screen.getByRole("radio", { name: "Override rate" }));
    if (enteredRate) {
      await user.type(screen.getByRole("textbox", { name: "Hourly rate" }), enteredRate);
    }
    await user.click(screen.getByRole("button", { name: "Save task" }));

    expect(screen.getByRole("alert")).toHaveTextContent(expectedError);
    expect(screen.getByRole("dialog", { name: "Add task" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Task name" })).toHaveValue("Research");
    expect(screen.getByRole("textbox", { name: "Hourly rate" })).toHaveValue(enteredRate);
    expect(onSave).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  },
);

test.each([
  { savedRate: null, selectedMode: "Inherit project rate", hasRateInput: false },
  { savedRate: 15_000, selectedMode: "Override rate", hasRateInput: true },
])("restores the saved rate mode when editing $savedRate", ({ savedRate, selectedMode, hasRateInput }) => {
  render(
    <TaskForm
      open
      client={client}
      project={project}
      task={task(savedRate)}
      onOpenChange={vi.fn()}
      onSave={vi.fn()}
    />,
  );

  expect(screen.getByRole("dialog", { name: "Edit task" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: selectedMode })).toBeChecked();
  if (hasRateInput) {
    expect(screen.getByRole("textbox", { name: "Hourly rate" })).toHaveValue("150.00");
  } else {
    expect(screen.queryByRole("textbox", { name: "Hourly rate" })).not.toBeInTheDocument();
  }
});

test("saves an explicit zero override", async () => {
  const user = userEvent.setup();
  const onSave = vi.fn().mockResolvedValue(undefined);
  const onOpenChange = vi.fn();
  render(
    <TaskForm
      open
      client={client}
      project={project}
      onOpenChange={onOpenChange}
      onSave={onSave}
    />,
  );

  await user.type(screen.getByRole("textbox", { name: "Task name" }), "Research");
  await user.click(screen.getByRole("radio", { name: "Override rate" }));
  await user.type(screen.getByRole("textbox", { name: "Hourly rate" }), "0");
  await user.click(screen.getByRole("button", { name: "Save task" }));

  expect(onSave).toHaveBeenCalledWith({ name: "Research", hourlyRateOverrideMinor: 0 });
  expect(onOpenChange).toHaveBeenCalledWith(false);
});
