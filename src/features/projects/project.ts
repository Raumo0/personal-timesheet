import { z } from "zod";

import { rescaleMinorUnits } from "../money/money";

const hourlyRateOverrideMinorSchema = z
  .number()
  .int("Hourly rate must use the currency's supported precision")
  .nonnegative("Hourly rate cannot be negative")
  .nullable();

export const projectCommandSchema = z.object({
  name: z.string().trim().min(1, "Enter a project name"),
  hourlyRateOverrideMinor: hourlyRateOverrideMinorSchema,
});

export const projectRowSchema = z.object({
  id: z.string().min(1),
  client_id: z.string().min(1),
  name: z.string().trim().min(1),
  normalized_name: z.string().min(1),
  hourly_rate_override_minor: hourlyRateOverrideMinorSchema,
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
  archived_at: z.string().datetime().nullable(),
});

export type ProjectCommand = z.infer<typeof projectCommandSchema>;
export type ProjectRow = z.infer<typeof projectRowSchema>;

export interface Project {
  id: string;
  clientId: string;
  name: string;
  hourlyRateOverrideMinor: number | null;
  createdAt: string;
  updatedAt: string;
  archivedAt: string | null;
}

export type ProjectRateSource = "project" | "client" | "unset";

export interface ResolvedProjectRate {
  hourlyRateMinor: number | null;
  source: ProjectRateSource;
}

export function normalizeProjectName(name: string): string {
  return name.trim().toLocaleLowerCase();
}

export function resolveProjectRate(
  hourlyRateOverrideMinor: number | null,
  clientHourlyRateMinor: number | null,
): ResolvedProjectRate {
  if (hourlyRateOverrideMinor !== null) {
    return { hourlyRateMinor: hourlyRateOverrideMinor, source: "project" };
  }
  if (clientHourlyRateMinor !== null) {
    return { hourlyRateMinor: clientHourlyRateMinor, source: "client" };
  }
  return { hourlyRateMinor: null, source: "unset" };
}

export function rescaleRateOverride(
  hourlyRateOverrideMinor: number | null,
  fromCurrencyCode: string,
  toCurrencyCode: string,
): number | null {
  if (hourlyRateOverrideMinor === null) return null;

  try {
    return rescaleMinorUnits(
      hourlyRateOverrideMinor,
      fromCurrencyCode,
      toCurrencyCode,
    );
  } catch (error) {
    if (error instanceof Error) {
      throw new Error(error.message.replace("Money amount", "Hourly rate"));
    }
    throw error;
  }
}

export const rescaleProjectRateOverride = rescaleRateOverride;

export function projectFromRow(input: unknown): Project {
  const row = projectRowSchema.parse(input);
  return {
    id: row.id,
    clientId: row.client_id,
    name: row.name,
    hourlyRateOverrideMinor: row.hourly_rate_override_minor,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    archivedAt: row.archived_at,
  };
}
