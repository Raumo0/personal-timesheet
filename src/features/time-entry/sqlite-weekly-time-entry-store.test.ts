import { expect, test, vi } from "vitest";

import type { SqlReadDatabase } from "@/infrastructure/sqlite/plugin-sql-adapter";

import { InMemoryWeeklyTimeEntryStore } from "./in-memory-weekly-time-entry-store";
import { SqliteWeeklyTimeEntryStore } from "./sqlite-weekly-time-entry-store";
import { currentWeek, rowKey, weekFromMonday } from "./weekly-time-entry";
import { weeklyTimeEntryStoreContract } from "./weekly-time-entry-store.contract";
import type {
  TimeEntryValue,
  WeeklyTimeEntryStoreError,
  WeeklyTimeEntryStoreSeed,
} from "./weekly-time-entry-store";

const seed: WeeklyTimeEntryStoreSeed = {
  clients: [
    {
      id: "client-1",
      name: "Acme",
      archivedAt: null,
      projects: [
        {
          id: "project-1",
          name: "Website",
          archivedAt: null,
          tasks: [
            { id: "task-1", name: "Design", archivedAt: null },
            { id: "task-archived", name: "Old", archivedAt: "archived" },
          ],
        },
      ],
    },
  ],
  entries: [],
};

function sqliteHarness(initial: WeeklyTimeEntryStoreSeed = seed) {
  const memory = new InMemoryWeeklyTimeEntryStore(initial);
  const plans: unknown[] = [];
  const select = vi.fn(async (sql: string, values: unknown[] = []) => {
    if (sql.includes("/* weekly:entries */")) {
      const week = weekFromMonday(String(values[0]));
      const snapshot = await memory.loadWeek(week);
      return snapshot.rows.flatMap((row) =>
        Object.entries(row.minutesByDate).map(([date, minutes]) => ({
          entry_date: date,
          duration_minutes: minutes,
          work_kind: row.reference.kind,
          work_id:
            row.reference.kind === "project"
              ? row.reference.projectId
              : row.reference.taskId,
          client_id: row.client.id,
          client_name: row.client.name,
          client_archived_at: row.client.archivedAt,
          project_id: row.project.id,
          project_name: row.project.name,
          project_archived_at: row.project.archivedAt,
          task_id: row.task?.id ?? null,
          task_name: row.task?.name ?? null,
          task_archived_at: row.task?.archivedAt ?? null,
        })),
      );
    }
    if (sql.includes("/* weekly:selectable */")) {
      const groups = await memory.listSelectableWork();
      return groups.flatMap((group) =>
        group.projects.flatMap(({ project, tasks }) => [
          {
            client_id: group.client.id,
            client_name: group.client.name,
            project_id: project.id,
            project_name: project.name,
            task_id: null,
            task_name: null,
          },
          ...tasks.map((task) => ({
            client_id: group.client.id,
            client_name: group.client.name,
            project_id: project.id,
            project_name: project.name,
            task_id: task.id,
            task_name: task.name,
          })),
        ]),
      );
    }
    if (sql.includes("/* weekly:expected */")) {
      const [date, kind, id] = values.map(String);
      const reference =
        kind === "project"
          ? ({ kind, projectId: id } as const)
          : ({ kind: "task", taskId: id } as const);
      const week = currentWeek(new Date(`${date}T12:00:00`));
      const snapshot = await memory.loadWeek(week);
      const target = snapshot.rows.find(
        (row) => rowKey(row.reference) === rowKey(reference),
      );
      const client = initial.clients.find((candidate) =>
        candidate.projects.some(
          (project) =>
            project.id === (kind === "project" ? id : target?.project.id) ||
            project.tasks.some((task) => task.id === id),
        ),
      );
      const project = client?.projects.find(
        (candidate) =>
          candidate.id === (kind === "project" ? id : target?.project.id) ||
          candidate.tasks.some((task) => task.id === id),
      );
      const task = project?.tasks.find((candidate) => candidate.id === id);
      const existingMinutes = target?.minutesByDate[date as keyof typeof target.minutesByDate];
      const dailyTotal = snapshot.rows.reduce(
        (total, row) => total + (row.minutesByDate[date as keyof typeof row.minutesByDate] ?? 0),
        0,
      );
      return client && project
        ? [
            {
              client_archived_at: client.archivedAt,
              project_archived_at: project.archivedAt,
              task_archived_at: task?.archivedAt ?? null,
              existing_id: existingMinutes === undefined ? null : `seed-${rowKey(reference)}`,
              existing_minutes: existingMinutes ?? null,
              existing_updated_at: existingMinutes === undefined ? null : "old",
              daily_total: dailyTotal,
            },
          ]
        : [];
    }
    throw new Error(`Unexpected query: ${sql}`);
  });
  const database = { select } satisfies SqlReadDatabase;
  const invoke = vi.fn(async (command: string, args?: Record<string, unknown>) => {
    expect(command).toBe("apply_weekly_time_entry_mutation");
    const plan = args?.plan as {
      operation: "upsert" | "delete";
      date: TimeEntryValue["date"];
      reference: TimeEntryValue["reference"];
      minutes?: number;
    };
    plans.push(args?.plan);
    try {
      if (plan.operation === "upsert") {
        return await memory.upsert({
          date: plan.date,
          reference: plan.reference,
          minutes: plan.minutes!,
        });
      }
      await memory.delete({ date: plan.date, reference: plan.reference });
      return null;
    } catch (cause) {
      const error = cause as WeeklyTimeEntryStoreError;
      throw new Error(`${error.code}: ${error.message}`);
    }
  });
  return {
    store: new SqliteWeeklyTimeEntryStore({
      getDatabase: async () => database,
      invoke,
      createId: () => "entry-new",
      now: () => "2026-08-05T10:00:00.000Z",
    }),
    select,
    invoke,
    plans,
  };
}

weeklyTimeEntryStoreContract(
  "SqliteWeeklyTimeEntryStore contract",
  (contractSeed) => sqliteHarness(contractSeed).store,
);

test("uses bounded ordered reads and sends a frozen expected-state plan", async () => {
  const harness = sqliteHarness();
  const week = weekFromMonday("2026-08-03");
  await harness.store.loadWeek(week);
  await harness.store.listSelectableWork();
  await harness.store.upsert({
    date: week.dates[0],
    reference: { kind: "project", projectId: "project-1" },
    minutes: 30,
  });

  expect(harness.select.mock.calls[0][1]).toEqual([
    "2026-08-03",
    "2026-08-09",
  ]);
  expect(harness.select.mock.calls[0][0]).toContain("ORDER BY");
  expect(harness.select.mock.calls[1][0]).toContain("archived_at IS NULL");
  expect(harness.plans).toHaveLength(1);
  expect(Object.isFrozen(harness.plans[0])).toBe(true);
  expect(harness.plans[0]).toMatchObject({
    operation: "upsert",
    entryId: "entry-new",
    expected: { existingEntryId: null, existingMinutes: null, dailyTotal: 0 },
  });
});

test("maps stale native rejection to the stable store error", async () => {
  const database = { select: vi.fn().mockResolvedValue([{
    client_archived_at: null,
    project_archived_at: null,
    task_archived_at: null,
    existing_id: null,
    existing_minutes: null,
    existing_updated_at: null,
    daily_total: 0,
  }]) } satisfies SqlReadDatabase;
  const store = new SqliteWeeklyTimeEntryStore({
    getDatabase: async () => database,
    invoke: vi.fn().mockRejectedValue("stale-plan: weekly state changed"),
  });

  await expect(
    store.upsert({
      date: weekFromMonday("2026-08-03").dates[0],
      reference: { kind: "project", projectId: "project-1" },
      minutes: 30,
    }),
  ).rejects.toMatchObject({ code: "stale-plan" });
});
