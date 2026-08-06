import { rowKey, type WorkReference } from "./weekly-time-entry";
import {
  WeeklyTimeEntryStoreError,
  type CatalogClientSeed,
  type CatalogProjectSeed,
  type CatalogTaskSeed,
  type SelectableWork,
  type TimeEntryValue,
  type WeeklyTimeEntryRow,
  type WeeklyTimeEntrySnapshot,
  type WeeklyTimeEntryStore,
  type WeeklyTimeEntryStoreSeed,
} from "./weekly-time-entry-store";

interface ResolvedWork {
  readonly client: CatalogClientSeed;
  readonly project: CatalogProjectSeed;
  readonly task?: CatalogTaskSeed;
}

function entryKey(entry: Pick<TimeEntryValue, "date" | "reference">): string {
  return `${entry.date}\0${rowKey(entry.reference)}`;
}

function cloneReference(reference: WorkReference): WorkReference {
  return reference.kind === "project"
    ? { kind: "project", projectId: reference.projectId }
    : { kind: "task", taskId: reference.taskId };
}

export class InMemoryWeeklyTimeEntryStore implements WeeklyTimeEntryStore {
  private readonly clients: readonly CatalogClientSeed[];
  private readonly entries = new Map<string, TimeEntryValue>();

  constructor(seed: WeeklyTimeEntryStoreSeed) {
    this.clients = structuredClone(seed.clients);
    for (const entry of seed.entries) {
      this.entries.set(entryKey(entry), {
        ...entry,
        reference: cloneReference(entry.reference),
      });
    }
  }

  async loadWeek(
    week: WeeklyTimeEntrySnapshot["week"],
  ): Promise<WeeklyTimeEntrySnapshot> {
    const weekDates = new Set<string>(week.dates);
    const rows = new Map<string, WeeklyTimeEntryRow>();

    for (const entry of this.entries.values()) {
      if (!weekDates.has(entry.date)) continue;

      const key = rowKey(entry.reference);
      const existing = rows.get(key);
      if (existing) {
        rows.set(key, {
          ...existing,
          minutesByDate: {
            ...existing.minutesByDate,
            [entry.date]: entry.minutes,
          },
        });
        continue;
      }

      const resolved = this.resolve(entry.reference);
      if (!resolved) continue;
      rows.set(key, this.createRow(entry, resolved));
    }

    return { week, rows: [...rows.values()] };
  }

  async listSelectableWork(): Promise<readonly SelectableWork[]> {
    return this.clients
      .filter((client) => client.archivedAt === null)
      .map((client) => ({
        client: { id: client.id, name: client.name },
        projects: client.projects
          .filter((project) => project.archivedAt === null)
          .map((project) => ({
            project: { id: project.id, name: project.name },
            tasks: project.tasks
              .filter((task) => task.archivedAt === null)
              .map((task) => ({ id: task.id, name: task.name })),
          })),
      }))
      .filter((client) => client.projects.length > 0);
  }

  async upsert(entry: TimeEntryValue): Promise<TimeEntryValue> {
    if (!Number.isSafeInteger(entry.minutes) || entry.minutes <= 0) {
      throw new WeeklyTimeEntryStoreError("invalid-duration");
    }

    const resolved = this.resolve(entry.reference);
    if (!resolved || !this.isActive(resolved)) {
      throw new WeeklyTimeEntryStoreError("inactive-work");
    }

    const targetKey = entryKey(entry);
    let dailyTotal = entry.minutes;
    for (const [key, existing] of this.entries) {
      if (existing.date === entry.date && key !== targetKey) {
        dailyTotal += existing.minutes;
      }
    }
    if (dailyTotal > 1440) {
      throw new WeeklyTimeEntryStoreError("daily-limit");
    }

    const saved = { ...entry, reference: cloneReference(entry.reference) };
    this.entries.set(targetKey, saved);
    return { ...saved, reference: cloneReference(saved.reference) };
  }

  async delete(target: {
    readonly date: TimeEntryValue["date"];
    readonly reference: WorkReference;
  }): Promise<void> {
    if (!this.entries.delete(entryKey(target))) {
      throw new WeeklyTimeEntryStoreError("entry-not-found");
    }
  }

  private resolve(reference: WorkReference): ResolvedWork | undefined {
    for (const client of this.clients) {
      for (const project of client.projects) {
        if (reference.kind === "project" && project.id === reference.projectId) {
          return { client, project };
        }
        if (reference.kind === "task") {
          const task = project.tasks.find(
            (candidate) => candidate.id === reference.taskId,
          );
          if (task) return { client, project, task };
        }
      }
    }
    return undefined;
  }

  private isActive(work: ResolvedWork): boolean {
    return (
      work.client.archivedAt === null &&
      work.project.archivedAt === null &&
      (work.task?.archivedAt ?? null) === null
    );
  }

  private createRow(
    entry: TimeEntryValue,
    work: ResolvedWork,
  ): WeeklyTimeEntryRow {
    const { projects: _projects, ...client } = work.client;
    const { tasks: _tasks, ...project } = work.project;
    return {
      reference: cloneReference(entry.reference),
      client,
      project,
      ...(work.task ? { task: { ...work.task } } : {}),
      active: this.isActive(work),
      minutesByDate: { [entry.date]: entry.minutes },
    };
  }
}
