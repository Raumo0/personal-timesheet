import { describe, expect, test } from "vitest";

import {
  clientCommandSchema,
  clientRowSchema,
  formatRate,
  normalizeClientName,
  parseRateToMinor,
} from "./client";

describe("client domain", () => {
  test("normalizes surrounding whitespace and case for identity", () => {
    expect(normalizeClientName("  Acme Studio  ")).toBe("acme studio");
  });

  test("accepts supported uppercase ISO currency codes", () => {
    expect(
      clientCommandSchema.parse({
        name: "Acme",
        currencyCode: "EUR",
        hourlyRateMinor: null,
      }),
    ).toMatchObject({ name: "Acme", currencyCode: "EUR" });

    expect(() =>
      clientCommandSchema.parse({
        name: "Acme",
        currencyCode: "EURO",
        hourlyRateMinor: null,
      }),
    ).toThrow();
  });

  test("keeps an unset rate distinct from explicit zero", () => {
    expect(
      clientCommandSchema.parse({
        name: "Acme",
        currencyCode: "EUR",
        hourlyRateMinor: null,
      }).hourlyRateMinor,
    ).toBeNull();
    expect(
      clientCommandSchema.parse({
        name: "Acme",
        currencyCode: "EUR",
        hourlyRateMinor: 0,
      }).hourlyRateMinor,
    ).toBe(0);
  });

  test("rejects negative and fractional minor units", () => {
    for (const hourlyRateMinor of [-1, 10.5]) {
      expect(() =>
        clientCommandSchema.parse({
          name: "Acme",
          currencyCode: "EUR",
          hourlyRateMinor,
        }),
      ).toThrow();
    }
  });

  test.each([
    ["125", "JPY", 125],
    ["125.50", "EUR", 12_550],
    ["125.500", "KWD", 125_500],
    ["0", "EUR", 0],
    ["", "EUR", null],
  ])("parses %s %s exactly", (input, currencyCode, expected) => {
    expect(parseRateToMinor(input, currencyCode)).toBe(expected);
  });

  test.each([
    ["1.1", "JPY"],
    ["1.001", "EUR"],
    ["-1", "EUR"],
    ["money", "EUR"],
  ])("rejects invalid precision or value %s %s", (input, currencyCode) => {
    expect(() => parseRateToMinor(input, currencyCode)).toThrow();
  });

  test("formats explicit zero and leaves null visibly unset", () => {
    expect(formatRate(null, "EUR", "en-IE")).toBeNull();
    expect(formatRate(0, "EUR", "en-IE")).toContain("0.00");
  });

  test("rejects invalid persisted rows", () => {
    expect(() =>
      clientRowSchema.parse({
        id: "client-1",
        name: "Acme",
        normalized_name: "acme",
        currency_code: "EUR",
        hourly_rate_minor: -1,
        created_at: "2026-07-31T10:00:00.000Z",
        updated_at: "2026-07-31T10:00:00.000Z",
        archived_at: null,
      }),
    ).toThrow();
  });
});
