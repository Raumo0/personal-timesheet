import type { LocalDate, Week, WorkReference } from "./weekly-time-entry";

export interface CatalogTaskSeed {
  readonly id: string;
  readonly name: string;
  readonly archivedAt: string | null;
}

export interface CatalogProjectSeed {
  readonly id: string;
  readonly name: string;
  readonly archivedAt: string | null;
  readonly tasks: readonly CatalogTaskSeed[];
}

export interface CatalogClientSeed {
  readonly id: string;
  readonly name: string;
  readonly archivedAt: string | null;
  readonly projects: readonly CatalogProjectSeed[];
}

export interface TimeEntryValue {
  readonly date: LocalDate;
  readonly reference: WorkReference;
  readonly minutes: number;
}

export interface WeeklyTimeEntryStoreSeed {
  readonly clients: readonly CatalogClientSeed[];
  readonly entries: readonly TimeEntryValue[];
}

export interface SelectableWork {
  readonly client: { readonly id: string; readonly name: string };
  readonly projects: readonly {
    readonly project: { readonly id: string; readonly name: string };
    readonly tasks: readonly { readonly id: string; readonly name: string }[];
  }[];
}

export interface WeeklyTimeEntryRow {
  readonly reference: WorkReference;
  readonly client: Omit<CatalogClientSeed, "projects">;
  readonly project: Omit<CatalogProjectSeed, "tasks">;
  readonly task?: CatalogTaskSeed;
  readonly active: boolean;
  readonly minutesByDate: Readonly<Partial<Record<LocalDate, number>>>;
}

export interface WeeklyTimeEntrySnapshot {
  readonly week: Week;
  readonly rows: readonly WeeklyTimeEntryRow[];
}

export type WeeklyTimeEntryStoreErrorCode =
  | "invalid-duration"
  | "inactive-work"
  | "daily-limit"
  | "entry-not-found"
  | "stale-plan"
  | "persistence";

const ERROR_MESSAGES: Record<WeeklyTimeEntryStoreErrorCode, string> = {
  "invalid-duration":
    "Duration must be a positive safe integer number of minutes.",
  "inactive-work": "The selected work item is no longer active.",
  "daily-limit": "Daily total cannot exceed 24:00.",
  "entry-not-found": "The time entry no longer exists.",
  "stale-plan": "The weekly time entry changed; reload and try again.",
  persistence: "Weekly time could not be saved locally.",
};

export class WeeklyTimeEntryStoreError extends Error {
  readonly code: WeeklyTimeEntryStoreErrorCode;
  readonly cause?: unknown;

  constructor(code: WeeklyTimeEntryStoreErrorCode, cause?: unknown) {
    super(ERROR_MESSAGES[code]);
    this.name = "WeeklyTimeEntryStoreError";
    this.code = code;
    this.cause = cause;
  }
}

export interface WeeklyTimeEntryStore {
  loadWeek(week: Week): Promise<WeeklyTimeEntrySnapshot>;
  listSelectableWork(): Promise<readonly SelectableWork[]>;
  upsert(entry: TimeEntryValue): Promise<TimeEntryValue>;
  delete(target: {
    readonly date: LocalDate;
    readonly reference: WorkReference;
  }): Promise<void>;
}
