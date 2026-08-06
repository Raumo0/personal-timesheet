import { describe, expect, test } from "vitest";

import {
  convertMinorUnits,
  currencyFractionDigits,
  formatMinorUnits,
  parseFixedScaleRate,
  parseMinorUnits,
} from "./money";

describe("money domain", () => {
  test.each([
    ["JPY", 0],
    ["EUR", 2],
    ["KWD", 3],
  ])("reports the supported precision for %s", (currencyCode, expected) => {
    expect(currencyFractionDigits(currencyCode)).toBe(expected);
  });

  test("rejects unsupported currency codes", () => {
    expect(() => currencyFractionDigits("EURO")).toThrow("supported currency");
  });

  test.each([
    ["125", "JPY", 125],
    ["125.50", "EUR", 12_550],
    ["125,500", "KWD", 125_500],
    ["90071992547409.91", "EUR", Number.MAX_SAFE_INTEGER],
  ])("parses %s %s into exact safe minor units", (raw, currency, expected) => {
    expect(parseMinorUnits(raw, currency)).toBe(expected);
  });

  test.each([
    ["1.1", "JPY"],
    ["1.001", "EUR"],
    ["-1", "EUR"],
    ["90071992547409.92", "EUR"],
  ])("rejects invalid or unsafe minor units %s %s", (raw, currency) => {
    expect(() => parseMinorUnits(raw, currency)).toThrow();
  });

  test("formats safe minor units without floating-point precision loss", () => {
    expect(formatMinorUnits(Number.MAX_SAFE_INTEGER, "EUR", "en-IE")).toContain(
      "90,071,992,547,409.91",
    );
  });

  test.each([
    ["1", 1n, 0],
    ["1.25", 125n, 2],
    ["0.000000000001", 1n, 12],
  ])("parses positive fixed-scale rate %s", (raw, coefficient, scale) => {
    expect(parseFixedScaleRate(raw)).toEqual({ coefficient, scale });
  });

  test.each(["0", "-1", ".5", "1.0000000000001", "1e2"])(
    "rejects invalid rate %s",
    (raw) => expect(() => parseFixedScaleRate(raw)).toThrow(),
  );

  test("converts through BigInt and rounds half-up exactly once", () => {
    expect(convertMinorUnits(1, "JPY", "EUR", "0.005")).toBe(1);
    expect(convertMinorUnits(1, "JPY", "EUR", "0.004999999999")).toBe(0);
    expect(convertMinorUnits(12_345, "EUR", "KWD", "1.234567890123")).toBe(
      152_407,
    );
  });

  test("rejects a converted value outside safe minor-unit storage", () => {
    expect(() =>
      convertMinorUnits(Number.MAX_SAFE_INTEGER, "JPY", "EUR", "1"),
    ).toThrow("too large");
  });
});
