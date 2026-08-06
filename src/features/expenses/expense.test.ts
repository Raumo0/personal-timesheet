import { describe, expect, test } from "vitest";

import {
  createExpenseCommandSchema,
  expenseFromRow,
  expenseRowSchema,
  expenseTargetSchema,
  updateExpenseCommandSchema,
} from "./expense";

const validCommand = {
  target: { kind: "project" as const, projectId: "project-1" },
  expenseDate: "2026-08-06",
  description: "Train to client workshop",
  originalCurrencyCode: "HUF",
  originalAmountMinor: 12_345,
  billingCurrencyCode: "EUR",
  billingAmountMinor: 3_086,
  appliedRate: "0.25",
  rateSource: "manual" as const,
  rateObservedOn: null,
  rateManuallyAdjusted: false,
};

const validRow = {
  id: "expense-1",
  client_id: null,
  project_id: "project-1",
  expense_date: "2026-08-06",
  description: "Train to client workshop",
  original_currency_code: "HUF",
  original_amount_minor: 12_345,
  billing_currency_code: "EUR",
  billing_amount_minor: 3_086,
  applied_rate: "0.25",
  rate_source: "manual",
  rate_observed_on: null,
  rate_manually_adjusted: false,
  created_at: "2026-08-06T10:00:00.000Z",
  updated_at: "2026-08-06T10:00:00.000Z",
  archived_at: null,
};

describe("expense domain", () => {
  test.each([
    [{ kind: "client", clientId: "client-1" }],
    [{ kind: "project", projectId: "project-1" }],
  ])("accepts exactly one discriminated target", (target) => {
    expect(expenseTargetSchema.parse(target)).toEqual(target);
  });

  test.each([
    [{}],
    [{ kind: "client", clientId: "", projectId: "project-1" }],
    [{ kind: "project", clientId: "client-1", projectId: "project-1" }],
  ])("rejects malformed target %#", (target) => {
    expect(() => expenseTargetSchema.parse(target)).toThrow();
  });

  test("accepts valid create and update commands", () => {
    expect(createExpenseCommandSchema.parse(validCommand)).toEqual(validCommand);
    expect(
      updateExpenseCommandSchema.parse({ id: "expense-1", ...validCommand }),
    ).toMatchObject({ id: "expense-1", description: validCommand.description });
  });

  test.each([
    [{ originalAmountMinor: 0 }],
    [{ originalAmountMinor: -1 }],
    [{ originalAmountMinor: 1.5 }],
    [{ billingAmountMinor: 0 }],
    [{ originalCurrencyCode: "EURO" }],
    [{ expenseDate: "2026-02-30" }],
    [{ description: "   " }],
    [{ appliedRate: "0" }],
    [{ appliedRate: "1.0000000000001" }],
    [{ rateSource: "ECB" }],
    [{ rateObservedOn: "2026-08-05" }],
    [{ rateManuallyAdjusted: true }],
  ])("rejects invalid command values %#", (override) => {
    expect(() =>
      createExpenseCommandSchema.parse({ ...validCommand, ...override }),
    ).toThrow();
  });

  test("requires rate 1 and equal amounts for the same currency", () => {
    expect(() =>
      createExpenseCommandSchema.parse({
        ...validCommand,
        originalCurrencyCode: "EUR",
      }),
    ).toThrow();
    expect(
      createExpenseCommandSchema.parse({
        ...validCommand,
        originalCurrencyCode: "EUR",
        originalAmountMinor: 3_086,
        appliedRate: "1",
      }),
    ).toMatchObject({ billingAmountMinor: 3_086, appliedRate: "1" });
  });

  test("maps a row into an immutable saved billing snapshot", () => {
    expect(expenseFromRow(validRow)).toEqual({
      id: "expense-1",
      target: { kind: "project", projectId: "project-1" },
      expenseDate: "2026-08-06",
      description: "Train to client workshop",
      originalCurrencyCode: "HUF",
      originalAmountMinor: 12_345,
      billingCurrencyCode: "EUR",
      billingAmountMinor: 3_086,
      appliedRate: "0.25",
      rateSource: "manual",
      rateObservedOn: null,
      rateManuallyAdjusted: false,
      createdAt: "2026-08-06T10:00:00.000Z",
      updatedAt: "2026-08-06T10:00:00.000Z",
      archivedAt: null,
    });
  });

  test("maps a direct Client row without a Project", () => {
    expect(
      expenseFromRow({ ...validRow, client_id: "client-1", project_id: null }).target,
    ).toEqual({ kind: "client", clientId: "client-1" });
  });

  test("returns a runtime-immutable saved snapshot", () => {
    const expense = expenseFromRow(validRow);
    expect(Object.isFrozen(expense)).toBe(true);
    expect(Object.isFrozen(expense.target)).toBe(true);
  });

  test.each([
    [{ client_id: null, project_id: null }],
    [{ client_id: "client-1", project_id: "project-1" }],
    [{ original_amount_minor: 0 }],
    [{ billing_currency_code: "EURO" }],
    [{ applied_rate: "not-a-rate" }],
    [{ archived_at: "not-a-timestamp" }],
  ])("rejects malformed persisted rows %#", (override) => {
    expect(() => expenseRowSchema.parse({ ...validRow, ...override })).toThrow();
  });
});
