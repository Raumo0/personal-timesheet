import { z } from "zod";

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
  currencyCodeSchema.parse(currencyCode);
  return new Intl.NumberFormat("en", {
    style: "currency",
    currency: currencyCode,
  }).resolvedOptions().maximumFractionDigits ?? 2;
}

export function parseRateToMinor(
  rawValue: string,
  currencyCode: string,
): number | null {
  const value = rawValue.trim();
  if (value === "") return null;

  const fractionDigits = currencyFractionDigits(currencyCode);
  const normalizedValue = value.includes(".") ? value : value.replace(",", ".");
  const match = normalizedValue.match(/^(\d+)(?:\.(\d+))?$/);
  if (!match || (match[2]?.length ?? 0) > fractionDigits) {
    throw new Error(`Enter a non-negative rate with up to ${fractionDigits} decimals`);
  }

  const whole = match[1];
  const fraction = (match[2] ?? "").padEnd(fractionDigits, "0");
  const minor = Number(`${whole}${fraction}`);
  if (!Number.isSafeInteger(minor)) {
    throw new Error("Hourly rate is too large");
  }

  return minor;
}

export function formatRate(
  hourlyRateMinor: number | null,
  currencyCode: string,
  locale?: string,
): string | null {
  if (hourlyRateMinor === null) return null;

  const fractionDigits = currencyFractionDigits(currencyCode);
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: currencyCode,
  }).format(hourlyRateMinor / 10 ** fractionDigits);
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
