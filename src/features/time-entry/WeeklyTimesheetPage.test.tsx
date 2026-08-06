import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type {
  CatalogLifecycle,
  LifecyclePlan,
} from "../catalog-lifecycle/catalog-lifecycle";
import { WeeklyTimesheetPage } from "./WeeklyTimesheetPage";
import type {
  TimeEntryLeaveRequest,
  TimeEntryNavigationCoordinator,
  TimeEntryNavigationGuardState,
} from "./time-entry-navigation-guard";
import { weekFromMonday } from "./weekly-time-entry";
import type {
  SelectableWork,
  WeeklyTimeEntrySnapshot,
  WeeklyTimeEntryStore,
} from "./weekly-time-entry-store";

const week = weekFromMonday("2026-08-03");
const work: readonly SelectableWork[] = [
  {
    client: { id: "client-1", name: "Acme" },
    projects: [
      {
        project: { id: "project-1", name: "Website" },
        tasks: [{ id: "task-1", name: "Design" }],
      },
    ],
  },
];

const populatedSnapshot: WeeklyTimeEntrySnapshot = {
  week,
  rows: [
    {
      reference: { kind: "project", projectId: "project-1" },
      client: { id: "client-1", name: "Acme", archivedAt: null },
      project: { id: "project-1", name: "Website", archivedAt: null },
      active: true,
      minutesByDate: {
        [week.dates[0]]: 60,
        [week.dates[2]]: 30,
      },
    },
    {
      reference: { kind: "task", taskId: "task-1" },
      client: { id: "client-1", name: "Acme", archivedAt: null },
      project: { id: "project-1", name: "Website", archivedAt: null },
      task: { id: "task-1", name: "Design", archivedAt: null },
      active: true,
      minutesByDate: {
        [week.dates[0]]: 45,
        [week.dates[1]]: 120,
      },
    },
  ],
};

const archivedSnapshot: WeeklyTimeEntrySnapshot = {
  week,
  rows: populatedSnapshot.rows.map((row) => ({
    ...row,
    client: { ...row.client, archivedAt: "2026-08-01T12:00:00.000Z" },
    project: { ...row.project, archivedAt: "2026-08-01T12:00:00.000Z" },
    task: row.task
      ? { ...row.task, archivedAt: "2026-08-01T12:00:00.000Z" }
      : undefined,
    active: false,
  })),
};

const restoreTaskPlan: LifecyclePlan = {
  operation: "restore",
  target: { kind: "task", id: "task-1" },
  records: [
    { kind: "client", id: "client-1", name: "Acme", archivedAt: "2026-08-01T12:00:00.000Z" },
    { kind: "project", id: "project-1", name: "Website", archivedAt: "2026-08-01T12:00:00.000Z" },
    { kind: "task", id: "task-1", name: "Design", archivedAt: "2026-08-01T12:00:00.000Z" },
  ],
  impactDescription:
    "Restore Acme, Website, and Design. Sibling records remain unchanged.",
};

function createStore(
  snapshot: WeeklyTimeEntrySnapshot = { week, rows: [] },
): WeeklyTimeEntryStore {
  return {
    loadWeek: vi.fn().mockResolvedValue(snapshot),
    listSelectableWork: vi.fn().mockResolvedValue(work),
    upsert: vi.fn(),
    delete: vi.fn(),
  };
}

function entryInput(name: string) {
  return screen.getByRole("textbox", { name });
}

function navigationHarness() {
  let routeHandler: ((request: TimeEntryLeaveRequest) => void) | undefined;
  let closeHandler: ((request: TimeEntryLeaveRequest) => void) | undefined;
  const states: TimeEntryNavigationGuardState[] = [];
  const coordinator: TimeEntryNavigationCoordinator = {
    registerRouteRequest(handler) {
      routeHandler = handler;
      return () => {
        routeHandler = undefined;
      };
    },
    registerNativeCloseRequest(handler) {
      closeHandler = handler;
      return () => {
        closeHandler = undefined;
      };
    },
    updateGuardState(state) {
      states.push(state);
    },
  };
  return {
    coordinator,
    requestRoute: (request: TimeEntryLeaveRequest) => routeHandler?.(request),
    requestClose: (request: TimeEntryLeaveRequest) => closeHandler?.(request),
    states,
  };
}

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

async function chooseWork(name: string) {
  const user = userEvent.setup();
  fireEvent.click(
    screen.getByRole("combobox", { name: "Select project or task" }),
  );
  await user.click(
    await screen.findByRole("option", {
      name: (accessibleName) => accessibleName.startsWith(name),
    }),
  );
}

test("opens the current local week with seven dated Monday–Sunday columns", async () => {
  const store = createStore();
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);

  expect(await screen.findByText("Aug 3–9, 2026")).toBeInTheDocument();
  expect(store.loadWeek).toHaveBeenCalledWith(week);
  expect(
    screen.getAllByRole("columnheader").map((heading) => heading.textContent),
  ).toEqual([
    "Work",
    "MonAug 3",
    "TueAug 4",
    "WedAug 5",
    "ThuAug 6",
    "FriAug 7",
    "SatAug 8",
    "SunAug 9",
    "Total",
  ]);
});

test("renders Project and Task rows, blank cells, and all totals", async () => {
  render(
    <WeeklyTimesheetPage
      now={new Date(2026, 7, 5)}
      store={createStore(populatedSnapshot)}
    />,
  );

  const projectRow = await screen.findByRole("row", {
    name: "Acme · Website · Project",
  });
  const taskRow = screen.getByRole("row", {
    name: "Acme · Website · Design · Task",
  });
  expect(within(projectRow).getByDisplayValue("1:00")).toBeInTheDocument();
  expect(
    within(projectRow).getByRole("textbox", {
      name: "Acme · Website · Tue Aug 4",
    }),
  ).toHaveValue("");
  expect(within(projectRow).getByText("1:30")).toBeInTheDocument();
  expect(within(taskRow).getByText("2:45")).toBeInTheDocument();

  const totals = screen.getByRole("row", { name: /Daily totals/ });
  expect(within(totals).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
    "Daily totals",
    "1:45",
    "2:00",
    "0:30",
    "0:00",
    "0:00",
    "0:00",
    "0:00",
    "4:15",
  ]);
});

test("shows an empty week without preloading rows and keeps zero totals", async () => {
  render(
    <WeeklyTimesheetPage
      now={new Date(2026, 7, 5)}
      store={createStore()}
    />,
  );

  expect(await screen.findByText("No rows this week")).toBeInTheDocument();
  expect(screen.queryAllByRole("textbox")).toHaveLength(0);
  expect(screen.getByRole("row", { name: /Daily totals/ })).toHaveTextContent(
    "0:00",
  );
  expect(screen.getByRole("status")).toHaveTextContent("No time saved");
});

test("adds a transient blank row from the selector", async () => {
  render(
    <WeeklyTimesheetPage
      now={new Date(2026, 7, 5)}
      store={createStore()}
    />,
  );
  await screen.findByText("No rows this week");

  await chooseWork("Project · Website");

  const row = screen.getByRole("row", { name: "Acme · Website · Project" });
  expect(within(row).getAllByRole("textbox")).toHaveLength(7);
  expect(within(row).getAllByRole("textbox")[0]).toHaveValue("");
  expect(screen.queryByText("No rows this week")).not.toBeInTheDocument();
});

test("selecting an existing row focuses its first day instead of duplicating it", async () => {
  render(
    <WeeklyTimesheetPage
      now={new Date(2026, 7, 5)}
      store={createStore(populatedSnapshot)}
    />,
  );
  await screen.findByRole("row", { name: "Acme · Website · Design · Task" });

  await chooseWork("Task · Design");

  expect(
    screen.getByRole("textbox", { name: "Acme · Website · Design · Mon Aug 3" }),
  ).toHaveFocus();
  expect(
    screen.getAllByRole("row", { name: "Acme · Website · Design · Task" }),
  ).toHaveLength(1);
});

test("fits compact columns at 1280px and retains narrow horizontal access", async () => {
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={createStore()} />);

  await screen.findByText("No rows this week");
  expect(screen.getByTestId("weekly-grid-scroll")).toHaveClass("overflow-x-auto");
  expect(screen.getByRole("table")).toHaveClass("min-w-[52rem]");
  expect(screen.getByRole("columnheader", { name: "Work" })).toHaveClass("w-40");
  expect(screen.getByRole("columnheader", { name: "MonAug 3" })).toHaveClass("w-20");
  expect(screen.getByRole("columnheader", { name: "Total" })).toHaveClass("w-20");
});

test("uses zebra rows and one emphasized treatment for totals", async () => {
  render(
    <WeeklyTimesheetPage
      now={new Date(2026, 7, 5)}
      store={createStore(populatedSnapshot)}
    />,
  );

  const projectRow = await screen.findByRole("row", {
    name: "Acme · Website · Project",
  });
  const taskRow = screen.getByRole("row", {
    name: "Acme · Website · Design · Task",
  });
  expect(projectRow).toHaveClass("odd:bg-muted/20");
  expect(taskRow).toHaveClass("even:bg-muted/5");
  const projectCells = within(projectRow).getAllByRole("cell");
  expect(projectCells[projectCells.length - 1]).toHaveClass("bg-muted/50");
  expect(screen.getByRole("row", { name: /Daily totals/ })).toHaveClass(
    "bg-muted/50",
  );
});

test("distinguishes loading and load failure from an empty week and retries", async () => {
  const store = createStore();
  vi.mocked(store.loadWeek)
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ week, rows: [] });
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);

  expect(screen.getByRole("status")).toHaveTextContent("Loading timesheet…");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Timesheet could not be loaded",
  );
  expect(screen.queryByText("No rows this week")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Retry" }));

  expect(await screen.findByText("No rows this week")).toBeInTheDocument();
  await waitFor(() => expect(store.loadWeek).toHaveBeenCalledTimes(2));
});

test("serializes Enter and blur saves and announces confirmed local state", async () => {
  const store = createStore(populatedSnapshot);
  let finishFirst: ((value: {
    date: typeof week.dates[0];
    reference: { kind: "project"; projectId: string };
    minutes: number;
  }) => void) | undefined;
  vi.mocked(store.upsert)
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishFirst = resolve;
        }),
    )
    .mockImplementationOnce(async (entry) => entry);
  const user = userEvent.setup();
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
  await screen.findByRole("row", { name: "Acme · Website · Project" });

  const projectMonday = entryInput("Acme · Website · Mon Aug 3");
  await user.clear(projectMonday);
  await user.type(projectMonday, "2:00{Enter}");
  const taskTuesday = entryInput("Acme · Website · Design · Tue Aug 4");
  await user.clear(taskTuesday);
  await user.type(taskTuesday, "1:00");
  await user.tab();

  expect(store.upsert).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("status")).toHaveTextContent("Saving…");
  finishFirst?.({
    date: week.dates[0],
    reference: { kind: "project", projectId: "project-1" },
    minutes: 120,
  });

  await waitFor(() => expect(store.upsert).toHaveBeenCalledTimes(2));
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent("Saved locally"),
  );
  expect(store.upsert).toHaveBeenNthCalledWith(2, {
    date: week.dates[1],
    reference: { kind: "task", taskId: "task-1" },
    minutes: 60,
  });
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("keeps invalid drafts unsaved and Escape restores the saved value", async () => {
  const store = createStore(populatedSnapshot);
  const user = userEvent.setup();
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
  const input = await screen.findByRole("textbox", {
    name: "Acme · Website · Mon Aug 3",
  });

  await user.clear(input);
  await user.type(input, "1:60");
  await user.tab();

  expect(input).toHaveValue("1:60");
  expect(input).toHaveAccessibleDescription(
    "Enter a duration in H:MM format.",
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    "Invalid duration · Use H:MM, for example 1:30",
  );
  expect(within(input.closest("td")!).getByText("Enter a duration in H:MM format.")).toHaveClass(
    "sr-only",
  );
  expect(store.upsert).not.toHaveBeenCalled();

  input.focus();
  await user.keyboard("{Escape}");
  expect(input).toHaveValue("1:00");
  expect(screen.getByRole("status")).toHaveTextContent("Saved locally");
});

test("keeps failed drafts, prioritizes failure status, and retries", async () => {
  const store = createStore(populatedSnapshot);
  vi.mocked(store.upsert)
    .mockRejectedValueOnce(new Error("disk full"))
    .mockImplementationOnce(async (entry) => entry);
  const user = userEvent.setup();
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
  const input = await screen.findByRole("textbox", {
    name: "Acme · Website · Mon Aug 3",
  });

  await user.clear(input);
  await user.type(input, "2:30{Enter}");

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Time entry could not be saved locally.",
  );
  expect(screen.getByRole("status")).toHaveTextContent("Not saved · Retry");
  expect(input).toHaveValue("2:30");

  const invalidInput = entryInput("Acme · Website · Design · Wed Aug 5");
  await user.type(invalidInput, "bad");
  expect(screen.getByRole("status")).toHaveTextContent("Not saved · Retry");

  await user.click(screen.getByRole("button", { name: "Not saved · Retry" }));
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent(
      "Invalid duration · Use H:MM, for example 1:30",
    ),
  );
  expect(store.upsert).toHaveBeenCalledTimes(2);
});

test("previews valid drafts in row, day, and grand totals before commit", async () => {
  const store = createStore(populatedSnapshot);
  const user = userEvent.setup();
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
  const input = await screen.findByRole("textbox", {
    name: "Acme · Website · Mon Aug 3",
  });

  await user.clear(input);
  await user.type(input, "2:00");

  const projectRow = screen.getByRole("row", {
    name: "Acme · Website · Project",
  });
  expect(within(projectRow).getByText("2:30")).toBeInTheDocument();
  const totals = screen.getByRole("row", { name: /Daily totals/ });
  expect(within(totals).getAllByRole("cell")[1]).toHaveTextContent("2:45");
  expect(within(totals).getAllByRole("cell")[8]).toHaveTextContent("5:15");
  expect(screen.getByRole("status")).toHaveTextContent("Unsaved changes");
  expect(store.upsert).not.toHaveBeenCalled();
});

test.each(["", "0:00"])(
  "asks before deleting a saved entry changed to %p and Cancel restores it",
  async (draft) => {
    const store = createStore(populatedSnapshot);
    const user = userEvent.setup();
    render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
    const input = await screen.findByRole("textbox", {
      name: "Acme · Website · Mon Aug 3",
    });

    await user.clear(input);
    if (draft) await user.type(input, draft);
    await user.keyboard("{Enter}");

    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Delete time entry?",
    );
    expect(store.delete).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(input).toHaveValue("1:00");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Saved locally");
  },
);

test("clears an unsaved draft without confirmation or persistence", async () => {
  const store = createStore();
  const user = userEvent.setup();
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
  await screen.findByText("No rows this week");
  await chooseWork("Project · Website");
  const input = entryInput("Acme · Website · Mon Aug 3");

  await user.type(input, "1:00");
  await user.clear(input);
  await user.tab();

  expect(input).toHaveValue("");
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(store.delete).not.toHaveBeenCalled();
  expect(store.upsert).not.toHaveBeenCalled();
  expect(screen.getByRole("status")).toHaveTextContent("No time saved");
});

test("confirms deletion and recalculates row, day, and grand totals", async () => {
  const store = createStore(populatedSnapshot);
  vi.mocked(store.delete).mockResolvedValueOnce();
  const user = userEvent.setup();
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
  const input = await screen.findByRole("textbox", {
    name: "Acme · Website · Mon Aug 3",
  });

  await user.clear(input);
  await user.keyboard("{Enter}");
  await user.click(screen.getByRole("button", { name: "Delete entry" }));

  await waitFor(() => expect(input).toHaveValue(""));
  expect(store.delete).toHaveBeenCalledWith({
    date: week.dates[0],
    reference: { kind: "project", projectId: "project-1" },
  });
  const projectRow = screen.getByRole("row", {
    name: "Acme · Website · Project",
  });
  expect(within(projectRow).getByText("0:30")).toBeInTheDocument();
  const totals = screen.getByRole("row", { name: /Daily totals/ });
  expect(within(totals).getAllByRole("cell")[1]).toHaveTextContent("0:45");
  expect(within(totals).getAllByRole("cell")[8]).toHaveTextContent("3:15");
});

test("retains authoritative saved totals after failed deletion and retries", async () => {
  const store = createStore(populatedSnapshot);
  vi.mocked(store.delete)
    .mockRejectedValueOnce(new Error("disk full"))
    .mockResolvedValueOnce();
  const user = userEvent.setup();
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
  const input = await screen.findByRole("textbox", {
    name: "Acme · Website · Mon Aug 3",
  });

  await user.clear(input);
  await user.keyboard("{Enter}");
  await user.click(screen.getByRole("button", { name: "Delete entry" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Time entry could not be saved locally.",
  );
  expect(input).toHaveValue("");
  expect(screen.getByRole("status")).toHaveTextContent("Not saved · Retry");
  expect(screen.getByRole("row", { name: /Daily totals/ })).toHaveTextContent(
    "4:15",
  );

  await user.click(screen.getByRole("button", { name: "Not saved · Retry" }));
  await waitFor(() => expect(input).toHaveValue(""));
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent("Saved locally"),
  );
  expect(store.delete).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("row", { name: /Daily totals/ })).toHaveTextContent(
    "3:15",
  );
});

test("navigates Previous, Next, and Current across local weeks", async () => {
  const store = createStore();
  vi.mocked(store.loadWeek).mockImplementation(async (requestedWeek) => ({
    week: requestedWeek,
    rows: [],
  }));
  const user = userEvent.setup();
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
  await screen.findByText("Aug 3–9, 2026");

  await user.click(screen.getByRole("button", { name: "Previous" }));
  expect(await screen.findByText("Jul 27–Aug 2, 2026")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Next" }));
  expect(await screen.findByText("Aug 3–9, 2026")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Next" }));
  expect(await screen.findByText("Aug 10–16, 2026")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Current" }));
  expect(await screen.findByText("Aug 3–9, 2026")).toBeInTheDocument();
});

test("commits the active valid cell and waits for its save before changing week", async () => {
  const store = createStore(populatedSnapshot);
  vi.mocked(store.loadWeek).mockImplementation(async (requestedWeek) =>
    requestedWeek.monday === week.monday
      ? populatedSnapshot
      : { week: requestedWeek, rows: [] },
  );
  let finishSave: ((value: Parameters<WeeklyTimeEntryStore["upsert"]>[0]) => void) | undefined;
  vi.mocked(store.upsert).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finishSave = resolve;
      }),
  );
  const user = userEvent.setup();
  render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
  const input = await screen.findByRole("textbox", {
    name: "Acme · Website · Mon Aug 3",
  });
  await user.clear(input);
  await user.type(input, "2:00");

  await user.click(screen.getByRole("button", { name: "Next" }));
  expect(store.loadWeek).toHaveBeenCalledTimes(1);
  expect(screen.getByText("Aug 3–9, 2026")).toBeInTheDocument();
  finishSave?.({
    date: week.dates[0],
    reference: { kind: "project", projectId: "project-1" },
    minutes: 120,
  });

  expect(await screen.findByText("Aug 10–16, 2026")).toBeInTheDocument();
  expect(store.loadWeek).toHaveBeenCalledTimes(2);
});

test.each(["invalid", "failed"])(
  "keeps the week and focuses the %s cell when navigation is blocked",
  async (kind) => {
    const store = createStore(populatedSnapshot);
    if (kind === "failed") {
      vi.mocked(store.upsert).mockRejectedValueOnce(new Error("disk full"));
    }
    const user = userEvent.setup();
    render(<WeeklyTimesheetPage now={new Date(2026, 7, 5)} store={store} />);
    const input = await screen.findByRole("textbox", {
      name: "Acme · Website · Mon Aug 3",
    });
    await user.clear(input);
    await user.type(input, kind === "invalid" ? "1:60" : "2:00{Enter}");
    if (kind === "failed") await screen.findByRole("alert");

    await user.click(screen.getByRole("button", { name: "Next" }));

    expect(screen.getByText("Aug 3–9, 2026")).toBeInTheDocument();
    expect(store.loadWeek).toHaveBeenCalledTimes(1);
    expect(input).toHaveFocus();
  },
);

test("offers Stay or Discard changes for a guarded route request", async () => {
  const harness = navigationHarness();
  const continueNavigation = vi.fn();
  const user = userEvent.setup();
  render(
    <WeeklyTimesheetPage
      navigationCoordinator={harness.coordinator}
      now={new Date(2026, 7, 5)}
      store={createStore(populatedSnapshot)}
    />,
  );
  const input = await screen.findByRole("textbox", {
    name: "Acme · Website · Mon Aug 3",
  });
  await user.clear(input);
  await user.type(input, "1:60");

  act(() => harness.requestRoute({ continueNavigation }));
  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    "Leave Timesheet?",
  );
  await user.click(screen.getByRole("button", { name: "Stay" }));
  expect(continueNavigation).not.toHaveBeenCalled();
  expect(input).toHaveValue("1:60");

  act(() => harness.requestRoute({ continueNavigation }));
  await screen.findByRole("alertdialog");
  await user.click(screen.getByRole("button", { name: "Discard changes" }));
  expect(continueNavigation).toHaveBeenCalledOnce();
  expect(input).toHaveValue("1:00");
});

test("coordinates native close guard state while empty transient rows stay clean", async () => {
  const harness = navigationHarness();
  const continueNavigation = vi.fn();
  const user = userEvent.setup();
  render(
    <WeeklyTimesheetPage
      navigationCoordinator={harness.coordinator}
      now={new Date(2026, 7, 5)}
      store={createStore()}
    />,
  );
  await screen.findByText("No rows this week");
  await chooseWork("Project · Website");
  expect(harness.states[harness.states.length - 1]).toEqual({
    shouldBlockNativeClose: false,
    shouldBlockRoute: false,
  });

  await user.type(entryInput("Acme · Website · Mon Aug 3"), "bad");
  await waitFor(() =>
    expect(
      harness.states[harness.states.length - 1]?.shouldBlockNativeClose,
    ).toBe(true),
  );
  act(() => harness.requestClose({ continueNavigation }));
  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    "Close Personal Timesheet?",
  );
  await user.click(screen.getByRole("button", { name: "Discard changes" }));
  expect(continueNavigation).toHaveBeenCalledOnce();
  expect(harness.states[harness.states.length - 1]).toEqual({
    shouldBlockNativeClose: false,
    shouldBlockRoute: false,
  });
});

test.each(["route", "native-close"] as const)(
  "waits for a pending %s save and continues only after guard state clears",
  async (source) => {
    const harness = navigationHarness();
    const store = createStore(populatedSnapshot);
    let finishSave:
      | ((value: Parameters<WeeklyTimeEntryStore["upsert"]>[0]) => void)
      | undefined;
    vi.mocked(store.upsert).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishSave = resolve;
        }),
    );
    const continueNavigation = vi.fn(() => {
      expect(harness.states[harness.states.length - 1]).toEqual({
        shouldBlockNativeClose: false,
        shouldBlockRoute: false,
      });
    });
    const user = userEvent.setup();
    render(
      <WeeklyTimesheetPage
        navigationCoordinator={harness.coordinator}
        now={new Date(2026, 7, 5)}
        store={store}
      />,
    );
    const input = await screen.findByRole("textbox", {
      name: "Acme · Website · Mon Aug 3",
    });
    await user.clear(input);
    await user.type(input, "2:00{Enter}");
    await waitFor(() =>
      expect(harness.states[harness.states.length - 1]).toEqual({
        shouldBlockNativeClose: true,
        shouldBlockRoute: true,
      }),
    );

    act(() =>
      source === "route"
        ? harness.requestRoute({ continueNavigation })
        : harness.requestClose({ continueNavigation }),
    );
    expect(continueNavigation).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();

    finishSave?.({
      date: week.dates[0],
      reference: { kind: "project", projectId: "project-1" },
      minutes: 120,
    });
    await waitFor(() => expect(continueNavigation).toHaveBeenCalledOnce());
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  },
);

test("offers Discard only after a pending native save fails and cannot persist later", async () => {
  const harness = navigationHarness();
  const store = createStore(populatedSnapshot);
  let failSave: ((reason?: unknown) => void) | undefined;
  vi.mocked(store.upsert).mockImplementationOnce(
    () =>
      new Promise((_, reject) => {
        failSave = reject;
      }),
  );
  const continueNavigation = vi.fn(() => {
    expect(harness.states[harness.states.length - 1]).toEqual({
      shouldBlockNativeClose: false,
      shouldBlockRoute: false,
    });
  });
  const user = userEvent.setup();
  render(
    <WeeklyTimesheetPage
      navigationCoordinator={harness.coordinator}
      now={new Date(2026, 7, 5)}
      store={store}
    />,
  );
  const input = await screen.findByRole("textbox", {
    name: "Acme · Website · Mon Aug 3",
  });
  await user.clear(input);
  await user.type(input, "2:00{Enter}");

  act(() => harness.requestClose({ continueNavigation }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  failSave?.(new Error("disk full"));

  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    "Close Personal Timesheet?",
  );
  await user.click(screen.getByRole("button", { name: "Discard changes" }));
  expect(continueNavigation).toHaveBeenCalledOnce();
  expect(store.upsert).toHaveBeenCalledTimes(1);
  await Promise.resolve();
  expect(store.upsert).toHaveBeenCalledTimes(1);
});

test("keeps archived rows visible and makes every time cell read-only", async () => {
  const lifecycle: CatalogLifecycle = {
    preview: vi.fn(),
    apply: vi.fn(),
  };
  render(
    <WeeklyTimesheetPage
      lifecycle={lifecycle}
      now={new Date(2026, 7, 5)}
      store={createStore(archivedSnapshot)}
    />,
  );

  const archivedRows = await screen.findAllByText("No longer active");
  expect(archivedRows).toHaveLength(2);
  expect(screen.getAllByRole("textbox")).toHaveLength(14);
  for (const input of screen.getAllByRole("textbox")) {
    expect(input).toHaveAttribute("readonly");
  }
  expect(
    screen.getByRole("button", { name: "Restore Acme · Website to edit" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", {
      name: "Restore Acme · Website · Design to edit",
    }),
  ).toBeInTheDocument();
});

test("previews the exact restore impact and returns focus when cancelled", async () => {
  const lifecycle: CatalogLifecycle = {
    preview: vi.fn().mockResolvedValue(restoreTaskPlan),
    apply: vi.fn(),
  };
  const user = userEvent.setup();
  render(
    <WeeklyTimesheetPage
      lifecycle={lifecycle}
      now={new Date(2026, 7, 5)}
      store={createStore(archivedSnapshot)}
    />,
  );
  const restore = await screen.findByRole("button", {
    name: "Restore Acme · Website · Design to edit",
  });

  await user.click(restore);
  expect(await screen.findByRole("alertdialog")).toHaveTextContent(
    restoreTaskPlan.impactDescription,
  );
  expect(lifecycle.preview).toHaveBeenCalledWith({
    operation: "restore",
    target: { kind: "task", id: "task-1" },
  });
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(restore).toHaveFocus());
  expect(lifecycle.apply).not.toHaveBeenCalled();
});

test("restores a row, reloads the row and selector, and retries with a fresh preview after failure", async () => {
  const lifecycle: CatalogLifecycle = {
    preview: vi.fn().mockResolvedValue(restoreTaskPlan),
    apply: vi
      .fn()
      .mockRejectedValueOnce(new Error("The task was not restored"))
      .mockResolvedValueOnce(undefined),
  };
  const store = createStore(archivedSnapshot);
  vi.mocked(store.listSelectableWork)
    .mockResolvedValueOnce([])
    .mockResolvedValueOnce(work);
  vi.mocked(store.loadWeek)
    .mockResolvedValueOnce(archivedSnapshot)
    .mockResolvedValueOnce(populatedSnapshot);
  const user = userEvent.setup();
  render(
    <WeeklyTimesheetPage
      lifecycle={lifecycle}
      now={new Date(2026, 7, 5)}
      store={store}
    />,
  );
  const restore = await screen.findByRole("button", {
    name: "Restore Acme · Website · Design to edit",
  });
  expect(screen.getByRole("combobox", { name: "Select project or task" })).toBeDisabled();

  await user.click(restore);
  await user.click(await screen.findByRole("button", { name: "Restore to edit" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The task was not restored",
  );
  await waitFor(() => expect(restore).toHaveFocus());
  expect(entryInput("Acme · Website · Design · Mon Aug 3")).toHaveAttribute("readonly");

  await user.click(screen.getByRole("button", { name: "Retry" }));
  await user.click(await screen.findByRole("button", { name: "Restore to edit" }));

  await waitFor(() =>
    expect(entryInput("Acme · Website · Design · Mon Aug 3")).not.toHaveAttribute(
      "readonly",
    ),
  );
  expect(screen.getByRole("combobox", { name: "Select project or task" })).toBeEnabled();
  expect(lifecycle.preview).toHaveBeenCalledTimes(2);
  expect(lifecycle.apply).toHaveBeenCalledTimes(2);
  expect(lifecycle.apply).toHaveBeenLastCalledWith(restoreTaskPlan);
  expect(store.loadWeek).toHaveBeenCalledTimes(2);
  expect(store.listSelectableWork).toHaveBeenCalledTimes(2);
});

test("retries only the reload when refresh fails after restore was applied", async () => {
  const lifecycle: CatalogLifecycle = {
    preview: vi.fn().mockResolvedValue(restoreTaskPlan),
    apply: vi.fn().mockResolvedValue(undefined),
  };
  const store = createStore(archivedSnapshot);
  vi.mocked(store.loadWeek)
    .mockResolvedValueOnce(archivedSnapshot)
    .mockRejectedValueOnce(new Error("refresh failed"))
    .mockResolvedValueOnce(populatedSnapshot);
  vi.mocked(store.listSelectableWork)
    .mockResolvedValueOnce([])
    .mockResolvedValueOnce(work)
    .mockResolvedValueOnce(work);
  const user = userEvent.setup();
  render(
    <WeeklyTimesheetPage
      lifecycle={lifecycle}
      now={new Date(2026, 7, 5)}
      store={store}
    />,
  );
  const restore = await screen.findByRole("button", {
    name: "Restore Acme · Website · Design to edit",
  });

  await user.click(restore);
  await user.click(await screen.findByRole("button", { name: "Restore to edit" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("refresh failed");
  await waitFor(() => expect(restore).toHaveFocus());

  await user.click(screen.getByRole("button", { name: "Retry" }));

  await waitFor(() =>
    expect(entryInput("Acme · Website · Design · Mon Aug 3")).not.toHaveAttribute(
      "readonly",
    ),
  );
  expect(lifecycle.preview).toHaveBeenCalledTimes(1);
  expect(lifecycle.apply).toHaveBeenCalledTimes(1);
  expect(store.loadWeek).toHaveBeenCalledTimes(3);
  expect(store.listSelectableWork).toHaveBeenCalledTimes(3);
});
