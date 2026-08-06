import type { LocalDate, WorkReference } from "./weekly-time-entry";

export interface WeeklyMutationExpectedState {
  readonly clientArchivedAt: string | null;
  readonly projectArchivedAt: string | null;
  readonly taskArchivedAt: string | null;
  readonly existingEntryId: string | null;
  readonly existingMinutes: number | null;
  readonly existingUpdatedAt: string | null;
  readonly dailyTotal: number;
}

export interface WeeklyTimeEntryMutationPlan {
  readonly operation: "upsert" | "delete";
  readonly entryId: string;
  readonly date: LocalDate;
  readonly reference: WorkReference;
  readonly minutes: number | null;
  readonly appliedAt: string;
  readonly expected: WeeklyMutationExpectedState;
}

export function freezeWeeklyMutationPlan(
  plan: WeeklyTimeEntryMutationPlan,
): WeeklyTimeEntryMutationPlan {
  Object.freeze(plan.reference);
  Object.freeze(plan.expected);
  return Object.freeze(plan);
}
