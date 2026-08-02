import { describe, expect, test } from "vitest";

import {
  normalizeProjectName,
  projectCommandSchema,
  projectRowSchema,
  rescaleProjectRateOverride,
  resolveProjectRate,
} from "./project";

describe("project domain", () => {
  test("normalizes surrounding whitespace and case for identity", () => {
    expect(normalizeProjectName("  Website Redesign  ")).toBe("website redesign");
  });

  test("distinguishes inherited rates from an explicit zero override", () => {
    expect(
      projectCommandSchema.parse({ name: "Website", hourlyRateOverrideMinor: null }),
    ).toMatchObject({ name: "Website", hourlyRateOverrideMinor: null });
    expect(
      projectCommandSchema.parse({ name: "Website", hourlyRateOverrideMinor: 0 }),
    ).toMatchObject({ name: "Website", hourlyRateOverrideMinor: 0 });
  });

  test("rejects invalid project names and overrides", () => {
    for (const command of [
      { name: "   ", hourlyRateOverrideMinor: null },
      { name: "Website", hourlyRateOverrideMinor: -1 },
      { name: "Website", hourlyRateOverrideMinor: 10.5 },
    ]) {
      expect(() => projectCommandSchema.parse(command)).toThrow();
    }
  });

  test("resolves a project override before the client rate", () => {
    expect(resolveProjectRate(5_000, 12_500)).toEqual({
      hourlyRateMinor: 5_000,
      source: "project",
    });
  });

  test("resolves a client rate when the project inherits", () => {
    expect(resolveProjectRate(null, 12_500)).toEqual({
      hourlyRateMinor: 12_500,
      source: "client",
    });
  });

  test("keeps an explicit zero override effective", () => {
    expect(resolveProjectRate(0, 12_500)).toEqual({
      hourlyRateMinor: 0,
      source: "project",
    });
  });

  test("reports an unset rate when neither project nor client sets one", () => {
    expect(resolveProjectRate(null, null)).toEqual({
      hourlyRateMinor: null,
      source: "unset",
    });
  });

  test.each([
    [12_500, "EUR", "JPY", 125],
    [125, "JPY", "EUR", 12_500],
    [125_500, "KWD", "EUR", 12_550],
    [0, "EUR", "JPY", 0],
    [null, "EUR", "JPY", null],
  ])("rescales %s exactly from %s to %s", (rate, fromCurrency, toCurrency, expected) => {
    expect(rescaleProjectRateOverride(rate, fromCurrency, toCurrency)).toBe(expected);
  });

  test("rejects a currency precision change that would lose non-zero digits", () => {
    expect(() => rescaleProjectRateOverride(12_550, "EUR", "JPY")).toThrow();
  });

  test("rejects invalid persisted project rows", () => {
    expect(() =>
      projectRowSchema.parse({
        id: "project-1",
        client_id: "client-1",
        name: "Website",
        normalized_name: "website",
        hourly_rate_override_minor: -1,
        created_at: "2026-08-02T10:00:00.000Z",
        updated_at: "2026-08-02T10:00:00.000Z",
        archived_at: null,
      }),
    ).toThrow();
  });
});
