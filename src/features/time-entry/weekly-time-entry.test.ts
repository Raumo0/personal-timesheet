import { describe, expect, it } from "vitest";

import {
  addWeeks,
  calculateDayTotals,
  calculateGrandTotal,
  calculateRowTotal,
  currentWeek,
  formatDuration,
  parseDuration,
  rowKey,
  validateDailyTotal,
  weekFromMonday,
  type WorkReference,
} from "./weekly-time-entry";

describe("weekly local dates", () => {
  it("returns the Monday-Sunday week containing the local current date", () => {
    expect(currentWeek(new Date(2026, 7, 5, 23, 30)).dates).toEqual([
      "2026-08-03",
      "2026-08-04",
      "2026-08-05",
      "2026-08-06",
      "2026-08-07",
      "2026-08-08",
      "2026-08-09",
    ]);
  });

  it("moves to previous and next weeks and returns to the current week", () => {
    const current = currentWeek(new Date(2026, 7, 5));

    expect(addWeeks(current, -1).monday).toBe("2026-07-27");
    expect(addWeeks(current, 1).monday).toBe("2026-08-10");
    expect(currentWeek(new Date(2026, 7, 5))).toEqual(current);
  });

  it("keeps ordered local dates across month and year boundaries", () => {
    expect(weekFromMonday("2025-12-29").dates).toEqual([
      "2025-12-29",
      "2025-12-30",
      "2025-12-31",
      "2026-01-01",
      "2026-01-02",
      "2026-01-03",
      "2026-01-04",
    ]);
  });

  it("uses calendar-day arithmetic across DST-adjacent weeks", () => {
    expect(weekFromMonday("2026-03-23").dates).toEqual([
      "2026-03-23",
      "2026-03-24",
      "2026-03-25",
      "2026-03-26",
      "2026-03-27",
      "2026-03-28",
      "2026-03-29",
    ]);
    expect(addWeeks(weekFromMonday("2026-10-19"), 1).monday).toBe(
      "2026-10-26",
    );
  });

  it("rejects invalid dates and non-Monday week starts", () => {
    expect(() => weekFromMonday("2026-02-30")).toThrow("Invalid local date");
    expect(() => weekFromMonday("2026-08-04")).toThrow("must be a Monday");
  });
});

describe("duration values", () => {
  it.each([
    ["0:00", 0],
    ["1:30", 90],
    ["24:00", 1440],
  ])("parses %s as integer minutes", (text, minutes) => {
    expect(parseDuration(text)).toEqual({ ok: true, minutes });
  });

  it.each(["1:5", "1:60", "-1:30", "one hour", " 1:30 "])(
    "rejects malformed duration %s",
    (text) => {
      expect(parseDuration(text)).toEqual({
        ok: false,
        error: "Enter a duration in H:MM format.",
      });
    },
  );

  it("rejects a duration whose computed minutes exceed safe integer range", () => {
    expect(parseDuration("999999999999999:00")).toEqual({
      ok: false,
      error: "Enter a duration in H:MM format.",
    });
  });

  it("formats non-negative integer minutes as H:MM", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(90)).toBe("1:30");
    expect(formatDuration(1440)).toBe("24:00");
    expect(() => formatDuration(1.5)).toThrow("non-negative integer");
  });
});

describe("row identity and totals", () => {
  it("keeps project and task identities discriminated", () => {
    const project: WorkReference = { kind: "project", projectId: "shared" };
    const task: WorkReference = { kind: "task", taskId: "shared" };

    expect(rowKey(project)).toBe("project:shared");
    expect(rowKey(task)).toBe("task:shared");
  });

  it("calculates row, day, and grand totals without mutating inputs", () => {
    const rows = [
      [30, undefined, 60, undefined, undefined, undefined, undefined],
      [15, 45, undefined, undefined, undefined, undefined, undefined],
    ] as const;

    expect(calculateRowTotal(rows[0])).toBe(90);
    expect(calculateDayTotals(rows)).toEqual([45, 45, 60, 0, 0, 0, 0]);
    expect(calculateGrandTotal(rows)).toBe(150);
    expect(rows[0]).toEqual([
      30,
      undefined,
      60,
      undefined,
      undefined,
      undefined,
      undefined,
    ]);
  });

  it("accepts exactly 1440 daily minutes and rejects a larger total", () => {
    expect(validateDailyTotal([480, 960])).toEqual({ ok: true, total: 1440 });
    expect(validateDailyTotal([480, 961])).toEqual({
      ok: false,
      total: 1441,
      error: "Daily total cannot exceed 24:00.",
    });
  });

  it("rejects invalid minute values before calculating totals", () => {
    expect(() => calculateRowTotal([30, -1])).toThrow(
      "Minutes must be non-negative integers",
    );
  });
});
