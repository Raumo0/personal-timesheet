import { z } from "zod";

import {
  currencyFractionDigits,
  parseFixedScaleRate,
} from "../money/money";

const idSchema = z.string().min(1);

const localDateSchema = z.string().refine((value) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}, "Enter a valid local date");

const currencyCodeSchema = z.string().refine((value) => {
  try {
    currencyFractionDigits(value);
    return true;
  } catch {
    return false;
  }
}, "Choose a supported currency");

const positiveMinorUnitsSchema = z
  .number()
  .int("Amount must use the currency's supported precision")
  .positive("Amount must be positive")
  .refine(Number.isSafeInteger, "Amount is too large");

const appliedRateSchema = z.string().refine((value) => {
  try {
    parseFixedScaleRate(value);
    return true;
  } catch {
    return false;
  }
}, "Enter a positive rate with up to 12 decimals");

export const expenseTargetSchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("client"), clientId: idSchema }).strict(),
  z.object({ kind: z.literal("project"), projectId: idSchema }).strict(),
]);

const expenseValuesSchema = z
  .object({
    target: expenseTargetSchema,
    expenseDate: localDateSchema,
    description: z.string().trim().min(1, "Enter a description"),
    originalCurrencyCode: currencyCodeSchema,
    originalAmountMinor: positiveMinorUnitsSchema,
    billingCurrencyCode: currencyCodeSchema,
    billingAmountMinor: positiveMinorUnitsSchema,
    appliedRate: appliedRateSchema,
    rateSource: z.literal("manual"),
    rateObservedOn: z.null(),
    rateManuallyAdjusted: z.literal(false),
  })
  .superRefine((value, context) => {
    if (value.originalCurrencyCode !== value.billingCurrencyCode) return;
    if (value.appliedRate !== "1") {
      context.addIssue({
        code: "custom",
        path: ["appliedRate"],
        message: "Matching currencies require an applied rate of 1",
      });
    }
    if (value.originalAmountMinor !== value.billingAmountMinor) {
      context.addIssue({
        code: "custom",
        path: ["billingAmountMinor"],
        message: "Matching currencies require equal amounts",
      });
    }
  });

export const createExpenseCommandSchema = expenseValuesSchema;
export const expenseCommandSchema = createExpenseCommandSchema;
export const updateExpenseCommandSchema = z.intersection(
  z.object({ id: idSchema }),
  expenseValuesSchema,
);

export const expenseRowSchema = z
  .object({
    id: idSchema,
    client_id: idSchema.nullable(),
    project_id: idSchema.nullable(),
    expense_date: localDateSchema,
    description: z.string().trim().min(1),
    original_currency_code: currencyCodeSchema,
    original_amount_minor: positiveMinorUnitsSchema,
    billing_currency_code: currencyCodeSchema,
    billing_amount_minor: positiveMinorUnitsSchema,
    applied_rate: appliedRateSchema,
    rate_source: z.literal("manual"),
    rate_observed_on: z.null(),
    rate_manually_adjusted: z.literal(false),
    created_at: z.string().datetime(),
    updated_at: z.string().datetime(),
    archived_at: z.string().datetime().nullable(),
  })
  .superRefine((row, context) => {
    if ((row.client_id === null) === (row.project_id === null)) {
      context.addIssue({
        code: "custom",
        path: ["client_id"],
        message: "Expense must reference exactly one Client or Project",
      });
    }
    if (row.original_currency_code !== row.billing_currency_code) return;
    if (
      row.applied_rate !== "1" ||
      row.original_amount_minor !== row.billing_amount_minor
    ) {
      context.addIssue({
        code: "custom",
        path: ["billing_amount_minor"],
        message: "Matching currencies require rate 1 and equal amounts",
      });
    }
  });

export type ExpenseTarget = z.infer<typeof expenseTargetSchema>;
export type CreateExpenseCommand = z.infer<typeof createExpenseCommandSchema>;
export type ExpenseCommand = CreateExpenseCommand;
export type UpdateExpenseCommand = z.infer<typeof updateExpenseCommandSchema>;
export type ExpenseRow = z.infer<typeof expenseRowSchema>;

export interface Expense {
  readonly id: string;
  readonly target: ExpenseTarget;
  readonly expenseDate: string;
  readonly description: string;
  readonly originalCurrencyCode: string;
  readonly originalAmountMinor: number;
  readonly billingCurrencyCode: string;
  readonly billingAmountMinor: number;
  readonly appliedRate: string;
  readonly rateSource: "manual";
  readonly rateObservedOn: null;
  readonly rateManuallyAdjusted: false;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly archivedAt: string | null;
}

export function expenseFromRow(input: unknown): Expense {
  const row = expenseRowSchema.parse(input);
  const target: ExpenseTarget = row.client_id
    ? { kind: "client", clientId: row.client_id }
    : { kind: "project", projectId: row.project_id! };

  return Object.freeze({
    id: row.id,
    target: Object.freeze(target),
    expenseDate: row.expense_date,
    description: row.description,
    originalCurrencyCode: row.original_currency_code,
    originalAmountMinor: row.original_amount_minor,
    billingCurrencyCode: row.billing_currency_code,
    billingAmountMinor: row.billing_amount_minor,
    appliedRate: row.applied_rate,
    rateSource: row.rate_source,
    rateObservedOn: row.rate_observed_on,
    rateManuallyAdjusted: row.rate_manually_adjusted,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
    archivedAt: row.archived_at,
  });
}
