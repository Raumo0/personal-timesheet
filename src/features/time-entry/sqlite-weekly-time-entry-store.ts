import { invoke } from "@tauri-apps/api/core";

import {
  getClientDatabase,
  type SqlReadDatabase,
} from "@/infrastructure/sqlite/plugin-sql-adapter";

import { rowKey, type LocalDate, type WorkReference } from "./weekly-time-entry";
import {
  freezeWeeklyMutationPlan,
  type WeeklyMutationExpectedState,
  type WeeklyTimeEntryMutationPlan,
} from "./weekly-time-entry-mutation-plan";
import {
  WeeklyTimeEntryStoreError,
  type SelectableWork,
  type TimeEntryValue,
  type WeeklyTimeEntryRow,
  type WeeklyTimeEntrySnapshot,
  type WeeklyTimeEntryStore,
} from "./weekly-time-entry-store";

type Invoke = (command: string, args?: Record<string, unknown>) => Promise<unknown>;

interface Options {
  getDatabase?: () => Promise<SqlReadDatabase>;
  invoke?: Invoke;
  createId?: () => string;
  now?: () => string;
}

const ENTRIES_QUERY = `/* weekly:entries */
SELECT time_entries.entry_date, time_entries.duration_minutes,
       CASE WHEN time_entries.project_id IS NOT NULL THEN 'project' ELSE 'task' END AS work_kind,
       COALESCE(time_entries.project_id, time_entries.task_id) AS work_id,
       clients.id AS client_id, clients.name AS client_name, clients.archived_at AS client_archived_at,
       projects.id AS project_id, projects.name AS project_name, projects.archived_at AS project_archived_at,
       tasks.id AS task_id, tasks.name AS task_name, tasks.archived_at AS task_archived_at
FROM time_entries
LEFT JOIN tasks ON tasks.id = time_entries.task_id
JOIN projects ON projects.id = COALESCE(time_entries.project_id, tasks.project_id)
JOIN clients ON clients.id = projects.client_id
WHERE time_entries.entry_date BETWEEN $1 AND $2
ORDER BY clients.name COLLATE NOCASE, projects.name COLLATE NOCASE,
         tasks.name COLLATE NOCASE, work_kind, work_id, time_entries.entry_date`;

const SELECTABLE_QUERY = `/* weekly:selectable */
SELECT clients.id AS client_id, clients.name AS client_name,
       projects.id AS project_id, projects.name AS project_name,
       tasks.id AS task_id, tasks.name AS task_name
FROM clients
JOIN projects ON projects.client_id = clients.id AND projects.archived_at IS NULL
LEFT JOIN tasks ON tasks.project_id = projects.id AND tasks.archived_at IS NULL
WHERE clients.archived_at IS NULL
ORDER BY clients.name COLLATE NOCASE, projects.name COLLATE NOCASE,
         tasks.name COLLATE NOCASE, clients.id, projects.id, tasks.id`;

const EXPECTED_QUERY = `/* weekly:expected */
SELECT clients.archived_at AS client_archived_at,
       projects.archived_at AS project_archived_at,
       tasks.archived_at AS task_archived_at,
       target.id AS existing_id,
       target.duration_minutes AS existing_minutes,
       target.updated_at AS existing_updated_at,
       COALESCE((SELECT SUM(duration_minutes) FROM time_entries WHERE entry_date = $1), 0) AS daily_total
FROM projects
JOIN clients ON clients.id = projects.client_id
LEFT JOIN tasks ON tasks.project_id = projects.id AND tasks.id = CASE WHEN $2 = 'task' THEN $3 END
LEFT JOIN time_entries AS target ON target.entry_date = $1
 AND (($2 = 'project' AND target.project_id = $3) OR ($2 = 'task' AND target.task_id = $3))
WHERE ($2 = 'project' AND projects.id = $3) OR ($2 = 'task' AND tasks.id = $3)
LIMIT 1`;

export class SqliteWeeklyTimeEntryStore implements WeeklyTimeEntryStore {
  private readonly getDatabase: () => Promise<SqlReadDatabase>;
  private readonly invoke: Invoke;
  private readonly createId: () => string;
  private readonly now: () => string;

  constructor(options: Options = {}) {
    this.getDatabase = options.getDatabase ?? getClientDatabase;
    this.invoke = options.invoke ?? invoke;
    this.createId = options.createId ?? (() => crypto.randomUUID());
    this.now = options.now ?? (() => new Date().toISOString());
  }

  async loadWeek(week: WeeklyTimeEntrySnapshot["week"]): Promise<WeeklyTimeEntrySnapshot> {
    const database = await this.database();
    try {
      const values = await database.select(ENTRIES_QUERY, [
        week.dates[0],
        week.dates[6],
      ]);
      return { week, rows: entryRows(values) };
    } catch (cause) {
      throw persistence(cause);
    }
  }

  async listSelectableWork(): Promise<readonly SelectableWork[]> {
    const database = await this.database();
    try {
      return selectableGroups(await database.select(SELECTABLE_QUERY));
    } catch (cause) {
      throw persistence(cause);
    }
  }

  async upsert(entry: TimeEntryValue): Promise<TimeEntryValue> {
    if (!Number.isSafeInteger(entry.minutes) || entry.minutes <= 0) {
      throw new WeeklyTimeEntryStoreError("invalid-duration");
    }
    const expected = await this.expected(entry.date, entry.reference);
    const plan = this.plan("upsert", entry.date, entry.reference, entry.minutes, expected);
    await this.apply(plan);
    return { ...entry, reference: cloneReference(entry.reference) };
  }

  async delete(target: { readonly date: LocalDate; readonly reference: WorkReference }): Promise<void> {
    const expected = await this.expected(target.date, target.reference);
    if (expected.existingMinutes === null) {
      throw new WeeklyTimeEntryStoreError("entry-not-found");
    }
    await this.apply(this.plan("delete", target.date, target.reference, null, expected));
  }

  private async database(): Promise<SqlReadDatabase> {
    try {
      return await this.getDatabase();
    } catch (cause) {
      throw persistence(cause);
    }
  }

  private async expected(date: LocalDate, reference: WorkReference): Promise<WeeklyMutationExpectedState> {
    const database = await this.database();
    const id = reference.kind === "project" ? reference.projectId : reference.taskId;
    let rows: unknown[];
    try {
      rows = await database.select(EXPECTED_QUERY, [date, reference.kind, id]);
    } catch (cause) {
      throw persistence(cause);
    }
    if (rows.length !== 1) throw new WeeklyTimeEntryStoreError("inactive-work");
    const row = objectRow(rows[0]);
    const expected = {
      clientArchivedAt: nullableString(row, "client_archived_at"),
      projectArchivedAt: nullableString(row, "project_archived_at"),
      taskArchivedAt: nullableString(row, "task_archived_at"),
      existingEntryId: nullableString(row, "existing_id"),
      existingMinutes: nullableInteger(row, "existing_minutes"),
      existingUpdatedAt: nullableString(row, "existing_updated_at"),
      dailyTotal: integer(row, "daily_total"),
    };
    if (expected.clientArchivedAt || expected.projectArchivedAt || expected.taskArchivedAt) {
      throw new WeeklyTimeEntryStoreError("inactive-work");
    }
    return expected;
  }

  private plan(
    operation: WeeklyTimeEntryMutationPlan["operation"],
    date: LocalDate,
    reference: WorkReference,
    minutes: number | null,
    expected: WeeklyMutationExpectedState,
  ): WeeklyTimeEntryMutationPlan {
    return freezeWeeklyMutationPlan({
      operation,
      entryId: this.createId(),
      date,
      reference: cloneReference(reference),
      minutes,
      appliedAt: this.now(),
      expected: { ...expected },
    });
  }

  private async apply(plan: WeeklyTimeEntryMutationPlan): Promise<void> {
    try {
      await this.invoke("apply_weekly_time_entry_mutation", { plan });
    } catch (cause) {
      const message = errorMessage(cause);
      if (message.startsWith("stale-plan:")) {
        throw new WeeklyTimeEntryStoreError("stale-plan", cause);
      }
      if (message.startsWith("daily-limit:")) {
        throw new WeeklyTimeEntryStoreError("daily-limit", cause);
      }
      if (message.startsWith("inactive-work:")) {
        throw new WeeklyTimeEntryStoreError("inactive-work", cause);
      }
      if (message.startsWith("entry-not-found:")) {
        throw new WeeklyTimeEntryStoreError("entry-not-found", cause);
      }
      throw persistence(cause);
    }
  }
}

function entryRows(values: unknown[]): WeeklyTimeEntryRow[] {
  const rows = new Map<string, WeeklyTimeEntryRow>();
  for (const value of values) {
    const row = objectRow(value);
    const kind = requiredString(row, "work_kind");
    const id = requiredString(row, "work_id");
    const reference: WorkReference = kind === "project"
      ? { kind, projectId: id }
      : kind === "task"
        ? { kind, taskId: id }
        : invalid("work_kind");
    const key = rowKey(reference);
    const taskId = nullableString(row, "task_id");
    const taskArchivedAt = nullableString(row, "task_archived_at");
    const existing = rows.get(key);
    const minutesByDate = {
      ...(existing?.minutesByDate ?? {}),
      [requiredString(row, "entry_date")]: integer(row, "duration_minutes"),
    };
    rows.set(key, existing ? { ...existing, minutesByDate } : {
      reference,
      client: { id: requiredString(row, "client_id"), name: requiredString(row, "client_name"), archivedAt: nullableString(row, "client_archived_at") },
      project: { id: requiredString(row, "project_id"), name: requiredString(row, "project_name"), archivedAt: nullableString(row, "project_archived_at") },
      ...(taskId ? { task: { id: taskId, name: requiredString(row, "task_name"), archivedAt: taskArchivedAt } } : {}),
      active: nullableString(row, "client_archived_at") === null && nullableString(row, "project_archived_at") === null && taskArchivedAt === null,
      minutesByDate,
    });
  }
  return [...rows.values()];
}

function selectableGroups(values: unknown[]): SelectableWork[] {
  const clients = new Map<string, { client: { id: string; name: string }; projects: Map<string, { project: { id: string; name: string }; tasks: { id: string; name: string }[] }> }>();
  for (const value of values) {
    const row = objectRow(value);
    const clientId = requiredString(row, "client_id");
    const projectId = requiredString(row, "project_id");
    let client = clients.get(clientId);
    if (!client) {
      client = { client: { id: clientId, name: requiredString(row, "client_name") }, projects: new Map() };
      clients.set(clientId, client);
    }
    let project = client.projects.get(projectId);
    if (!project) {
      project = { project: { id: projectId, name: requiredString(row, "project_name") }, tasks: [] };
      client.projects.set(projectId, project);
    }
    const taskId = nullableString(row, "task_id");
    if (taskId) project.tasks.push({ id: taskId, name: requiredString(row, "task_name") });
  }
  return [...clients.values()].map(({ client, projects }) => ({ client, projects: [...projects.values()] }));
}

function cloneReference(reference: WorkReference): WorkReference {
  return reference.kind === "project" ? { kind: "project", projectId: reference.projectId } : { kind: "task", taskId: reference.taskId };
}
function objectRow(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new TypeError("Weekly query row must be an object");
  return value as Record<string, unknown>;
}
function requiredString(row: Record<string, unknown>, key: string): string {
  if (typeof row[key] !== "string") throw new TypeError(`${key} must be a string`);
  return row[key];
}
function nullableString(row: Record<string, unknown>, key: string): string | null {
  if (row[key] !== null && typeof row[key] !== "string") throw new TypeError(`${key} must be a string or null`);
  return row[key] as string | null;
}
function integer(row: Record<string, unknown>, key: string): number {
  if (!Number.isSafeInteger(row[key])) throw new TypeError(`${key} must be an integer`);
  return row[key] as number;
}
function nullableInteger(row: Record<string, unknown>, key: string): number | null {
  return row[key] === null ? null : integer(row, key);
}
function invalid(key: string): never { throw new TypeError(`${key} is invalid`); }
function errorMessage(cause: unknown): string { return cause instanceof Error ? cause.message : String(cause); }
function persistence(cause: unknown): WeeklyTimeEntryStoreError { return new WeeklyTimeEntryStoreError("persistence", cause); }
