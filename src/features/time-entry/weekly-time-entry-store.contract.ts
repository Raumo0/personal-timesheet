import { describe, expect, it } from "vitest";

import { weekFromMonday, type WorkReference } from "./weekly-time-entry";
import {
  type WeeklyTimeEntryStore,
  type WeeklyTimeEntryStoreSeed,
} from "./weekly-time-entry-store";

export type WeeklyTimeEntryStoreFactory = (
  seed: WeeklyTimeEntryStoreSeed,
) => WeeklyTimeEntryStore;

const activeSeed: WeeklyTimeEntryStoreSeed = {
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
            {
              id: "task-archived",
              name: "Old task",
              archivedAt: "2026-08-01T10:00:00.000Z",
            },
          ],
        },
        {
          id: "project-archived",
          name: "Old project",
          archivedAt: "2026-08-01T10:00:00.000Z",
          tasks: [
            { id: "task-under-archived", name: "Hidden", archivedAt: null },
          ],
        },
      ],
    },
    {
      id: "client-archived",
      name: "Old client",
      archivedAt: "2026-08-01T10:00:00.000Z",
      projects: [
        {
          id: "project-under-archived",
          name: "Hidden project",
          archivedAt: null,
          tasks: [],
        },
      ],
    },
  ],
  entries: [],
};

const projectReference: WorkReference = {
  kind: "project",
  projectId: "project-1",
};
const taskReference: WorkReference = { kind: "task", taskId: "task-1" };
const monday = weekFromMonday("2026-08-03").dates[0];
const tuesday = weekFromMonday("2026-08-03").dates[1];

export function weeklyTimeEntryStoreContract(
  name: string,
  createStore: WeeklyTimeEntryStoreFactory,
): void {
  describe(name, () => {
    it("loads an empty week distinctly and lists only fully active work", async () => {
      const store = createStore(activeSeed);

      await expect(store.loadWeek(weekFromMonday("2026-08-03"))).resolves.toEqual({
        week: weekFromMonday("2026-08-03"),
        rows: [],
      });
      await expect(store.listSelectableWork()).resolves.toEqual([
        {
          client: { id: "client-1", name: "Acme" },
          projects: [
            {
              project: { id: "project-1", name: "Website" },
              tasks: [{ id: "task-1", name: "Design" }],
            },
          ],
        },
      ]);
    });

    it("upserts unique Project and Task entries for the same date", async () => {
      const store = createStore(activeSeed);

      await store.upsert({ date: monday, reference: projectReference, minutes: 30 });
      await store.upsert({ date: monday, reference: projectReference, minutes: 45 });
      await store.upsert({ date: monday, reference: taskReference, minutes: 60 });

      const snapshot = await store.loadWeek(weekFromMonday("2026-08-03"));
      expect(snapshot.rows).toHaveLength(2);
      expect(snapshot.rows.map((row) => row.reference)).toEqual([
        projectReference,
        taskReference,
      ]);
      expect(snapshot.rows.map((row) => row.minutesByDate[monday])).toEqual([
        45, 60,
      ]);
    });

    it("deletes an entry and removes its row when no saved entries remain", async () => {
      const store = createStore({
        ...activeSeed,
        entries: [
          { date: monday, reference: projectReference, minutes: 30 },
          { date: tuesday, reference: projectReference, minutes: 60 },
        ],
      });

      await store.delete({ date: monday, reference: projectReference });
      expect((await store.loadWeek(weekFromMonday("2026-08-03"))).rows[0]
        .minutesByDate).toEqual({ [tuesday]: 60 });

      await store.delete({ date: tuesday, reference: projectReference });
      expect((await store.loadWeek(weekFromMonday("2026-08-03"))).rows).toEqual([]);
    });

    it("retains saved archived rows with current hierarchy and read-only state", async () => {
      const archivedReference: WorkReference = {
        kind: "task",
        taskId: "task-archived",
      };
      const store = createStore({
        ...activeSeed,
        entries: [{ date: monday, reference: archivedReference, minutes: 90 }],
      });

      expect((await store.loadWeek(weekFromMonday("2026-08-03"))).rows).toEqual([
        {
          reference: archivedReference,
          client: { id: "client-1", name: "Acme", archivedAt: null },
          project: { id: "project-1", name: "Website", archivedAt: null },
          task: {
            id: "task-archived",
            name: "Old task",
            archivedAt: "2026-08-01T10:00:00.000Z",
          },
          active: false,
          minutesByDate: { [monday]: 90 },
        },
      ]);
    });

    it("rejects inactive work with a stable error and no partial write", async () => {
      const store = createStore(activeSeed);
      const reference: WorkReference = {
        kind: "task",
        taskId: "task-under-archived",
      };

      await expect(
        store.upsert({ date: monday, reference, minutes: 30 }),
      ).rejects.toMatchObject({
        name: "WeeklyTimeEntryStoreError",
        code: "inactive-work",
        message: "The selected work item is no longer active.",
      });
      expect((await store.loadWeek(weekFromMonday("2026-08-03"))).rows).toEqual([]);
    });

    it("rejects zero and invalid minute values with stable errors", async () => {
      const store = createStore(activeSeed);

      for (const minutes of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
        await expect(
          store.upsert({ date: monday, reference: projectReference, minutes }),
        ).rejects.toMatchObject({
          code: "invalid-duration",
          message: "Duration must be a positive safe integer number of minutes.",
        });
      }
      expect((await store.loadWeek(weekFromMonday("2026-08-03"))).rows).toEqual([]);
    });

    it("accepts exactly 1440 daily minutes", async () => {
      const store = createStore(activeSeed);

      await store.upsert({
        date: monday,
        reference: projectReference,
        minutes: 900,
      });
      await store.upsert({ date: monday, reference: taskReference, minutes: 540 });

      expect((await store.loadWeek(weekFromMonday("2026-08-03"))).rows).toHaveLength(2);
    });

    it("rejects a daily total over 1440 atomically", async () => {
      const store = createStore({
        ...activeSeed,
        entries: [
          { date: monday, reference: projectReference, minutes: 900 },
          { date: monday, reference: taskReference, minutes: 500 },
        ],
      });

      await expect(
        store.upsert({ date: monday, reference: taskReference, minutes: 541 }),
      ).rejects.toMatchObject({
        code: "daily-limit",
        message: "Daily total cannot exceed 24:00.",
      });
      const rows = (await store.loadWeek(weekFromMonday("2026-08-03"))).rows;
      expect(rows.map((row) => row.minutesByDate[monday])).toEqual([900, 500]);
    });

    it("reports deletion of a missing entry with a stable error", async () => {
      const store = createStore(activeSeed);

      await expect(
        store.delete({ date: monday, reference: projectReference }),
      ).rejects.toMatchObject({
        code: "entry-not-found",
        message: "The time entry no longer exists.",
      });
    });
  });
}
