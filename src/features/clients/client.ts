import { z } from "zod";

import {
  currencyFractionDigits as sharedCurrencyFractionDigits,
  formatMinorUnits,
  parseMinorUnits,
} from "../money/money";

const currencyCodeSchema = z
  .string()
  .regex(/^[A-Z]{3}$/, "Choose a valid billing currency")
  .refine(
    (code) =>
      (
        Intl as typeof Intl & {
          supportedValuesOf(key: "currency"): string[];
        }
      )
        .supportedValuesOf("currency")
        .includes(code),
    "Choose a supported billing currency",
  );

const hourlyRateMinorSchema = z
  .number()
  .int("Hourly rate must use the currency's supported precision")
  .nonnegative("Hourly rate cannot be negative")
  .nullable();

export const clientCommandSchema = z.object({
  name: z.string().trim().min(1, "Enter a client name"),
  currencyCode: currencyCodeSchema,
  hourlyRateMinor: hourlyRateMinorSchema,
});

export const clientRowSchema = z.object({
  id: z.string().min(1),
  name: z.string().trim().min(1),
  normalized_name: z.string().min(1),
  currency_code: currencyCodeSchema,
  hourly_rate_minor: hourlyRateMinorSchema,
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
  archived_at: z.string().datetime().nullable(),
});

export type ClientCommand = z.infer<typeof clientCommandSchema>;
export type ClientRow = z.infer<typeof clientRowSchema>;

export interface Client {
  id: string;
  name: string;
  currencyCode: string;
  hourlyRateMinor: number | null;
  createdAt: string;
  updatedAt: string;
  archivedAt: string | null;
}

export function normalizeClientName(name: string): string {
  return name.trim().toLocaleLowerCase();
}

export function currencyFractionDigits(currencyCode: string): number {
  return sharedCurrencyFractionDigits(currencyCode);
}

export function parseRateToMinor(
  rawValue: string,
  currencyCode: string,
): number | null {
  const value = rawValue.trim();
  if (value === "") return null;

  try {
    return parseMinorUnits(value, currencyCode);
  } catch (error) {
    if (error instanceof Error) {
      throw new Error(
        error.message
          .replace("Money amount", "Hourly rate")
          .replace("amount", "rate"),
      );
    }
    throw error;
  }
}

export function formatRate(
  hourlyRateMinor: number | null,
  currencyCode: string,
  locale?: string,
): string | null {
  if (hourlyRateMinor === null) return null;

  return formatMinorUnits(hourlyRateMinor, currencyCode, locale);
}

export function clientFromRow(input: unknown): Client {
  const row = clientRowSchema.parse(input);
  return {
    id: row.id,
    name: row.name,
    currencyCode: row.currency_code,
    hourlyRateMinor: row.hourly_rate_minor,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    archivedAt: row.archived_at,
  };
}
