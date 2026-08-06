import { z } from "zod";

const idSchema = z.string().min(1);
const safeIntegerSchema = z
  .number()
  .int()
  .refine(Number.isSafeInteger, "Value exceeds JavaScript's safe integer range");
const nonnegativeIntegerSchema = safeIntegerSchema.nonnegative();

export const invoiceRequestSchema = z
  .object({
    clientId: idSchema,
    senderName: z.string(),
    issueDate: z.string(),
    invoiceNumber: z.string().nullable(),
    periodStart: z.string(),
    periodEnd: z.string(),
    includedExpenseIds: z.array(idSchema).nullable(),
    draftRateOverridesMinor: z.record(idSchema, nonnegativeIntegerSchema),
    paymentNoteEnabled: z.boolean(),
    paymentNote: z.string(),
    includeDailyActivity: z.boolean(),
    includeWorkCategoryBreakdown: z.boolean(),
  })
  .strict();

export const validationIssueSchema = z
  .object({
    code: z.string().min(1),
    field: z.string().nullable(),
    lineKey: z.string().nullable(),
  })
  .strict();

export const workLineSchema = z
  .object({
    key: idSchema,
    label: z.string(),
    taskId: z.string().nullable(),
    minutes: nonnegativeIntegerSchema,
    rateMinor: nonnegativeIntegerSchema.nullable(),
    amountMinor: nonnegativeIntegerSchema.nullable(),
  })
  .strict();

export const invoiceProjectSchema = z
  .object({
    id: idSchema,
    name: z.string(),
    workLines: z.array(workLineSchema),
    subtotalMinor: nonnegativeIntegerSchema,
  })
  .strict();

export const invoiceExpenseSchema = z
  .object({
    id: idSchema,
    projectId: z.string().nullable(),
    projectName: z.string().nullable(),
    date: z.string(),
    description: z.string(),
    billingAmountMinor: nonnegativeIntegerSchema,
  })
  .strict();

export const dailyActivityPointSchema = z
  .object({
    date: z.string(),
    minutes: nonnegativeIntegerSchema,
  })
  .strict();

export const dailyActivityAxisSchema = z
  .object({
    upperBoundHours: z.number().finite().nonnegative(),
    ticks: z.array(z.number().finite().nonnegative()),
  })
  .strict();

export const workCategoryShareSchema = z
  .object({
    projectId: idSchema,
    projectName: z.string(),
    lineKey: idSchema,
    label: z.string(),
    minutes: nonnegativeIntegerSchema,
    share: z.number().finite().min(0).max(1),
  })
  .strict();

export const invoiceDocumentSchema = z
  .object({
    senderName: z.string(),
    recipientName: z.string(),
    issueDate: z.string(),
    invoiceNumber: z.string().nullable(),
    paymentNote: z.string().nullable(),
    includeDailyActivity: z.boolean(),
    includeWorkCategoryBreakdown: z.boolean(),
    periodStart: z.string(),
    periodEnd: z.string(),
    currencyCode: z.string(),
    projects: z.array(invoiceProjectSchema),
    expenses: z.array(invoiceExpenseSchema),
    workSubtotalMinor: nonnegativeIntegerSchema,
    expenseSubtotalMinor: nonnegativeIntegerSchema,
    totalDueMinor: nonnegativeIntegerSchema,
    totalMinutes: nonnegativeIntegerSchema,
    activeDays: nonnegativeIntegerSchema,
    dailyActivity: z.array(dailyActivityPointSchema),
    dailyActivityAxis: dailyActivityAxisSchema,
    workCategoryShares: z.array(workCategoryShareSchema),
    validationIssues: z.array(validationIssueSchema),
    exportable: z.boolean(),
  })
  .strict();

export type InvoiceRequest = z.infer<typeof invoiceRequestSchema>;
export type ValidationIssue = z.infer<typeof validationIssueSchema>;
export type WorkLine = z.infer<typeof workLineSchema>;
export type InvoiceProject = z.infer<typeof invoiceProjectSchema>;
export type InvoiceExpense = z.infer<typeof invoiceExpenseSchema>;
export type DailyActivityPoint = z.infer<typeof dailyActivityPointSchema>;
export type DailyActivityAxis = z.infer<typeof dailyActivityAxisSchema>;
export type WorkCategoryShare = z.infer<typeof workCategoryShareSchema>;
export type InvoiceDocument = z.infer<typeof invoiceDocumentSchema>;
