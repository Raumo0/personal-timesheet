import { z } from "zod";

import { resolveProjectRate } from "../projects/project";

const hourlyRateOverrideMinorSchema = z
  .number()
  .int("Hourly rate must use the currency's supported precision")
  .nonnegative("Hourly rate cannot be negative")
  .nullable();

export const taskCommandSchema = z.object({
  name: z.string().trim().min(1, "Enter a task name"),
  hourlyRateOverrideMinor: hourlyRateOverrideMinorSchema,
});

export const taskRowSchema = z.object({
  id: z.string().min(1),
  project_id: z.string().min(1),
  name: z.string().trim().min(1),
  normalized_name: z.string().min(1),
  hourly_rate_override_minor: hourlyRateOverrideMinorSchema,
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
  archived_at: z.string().datetime().nullable(),
});

export type TaskCommand = z.infer<typeof taskCommandSchema>;
export type TaskRow = z.infer<typeof taskRowSchema>;

export interface Task {
  id: string;
  projectId: string;
  name: string;
  hourlyRateOverrideMinor: number | null;
  createdAt: string;
  updatedAt: string;
  archivedAt: string | null;
}

export type TaskRateSource = "task" | "project" | "client" | "unset";

export interface ResolvedTaskRate {
  hourlyRateMinor: number | null;
  source: TaskRateSource;
}

export function normalizeTaskName(name: string): string {
  return name.trim().toLocaleLowerCase();
}

export function resolveTaskRate(
  hourlyRateOverrideMinor: number | null,
  projectHourlyRateOverrideMinor: number | null,
  clientHourlyRateMinor: number | null,
): ResolvedTaskRate {
  if (hourlyRateOverrideMinor !== null) {
    return { hourlyRateMinor: hourlyRateOverrideMinor, source: "task" };
  }

  return resolveProjectRate(
    projectHourlyRateOverrideMinor,
    clientHourlyRateMinor,
  );
}

export function taskFromRow(input: unknown): Task {
  const row = taskRowSchema.parse(input);
  return {
    id: row.id,
    projectId: row.project_id,
    name: row.name,
    hourlyRateOverrideMinor: row.hourly_rate_override_minor,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    archivedAt: row.archived_at,
  };
}
