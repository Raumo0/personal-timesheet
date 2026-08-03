import { describe, expect, test } from "vitest";

import {
  normalizeTaskName,
  resolveTaskRate,
  taskCommandSchema,
  taskFromRow,
  taskRowSchema,
} from "./task";

describe("task domain", () => {
  test("normalizes surrounding whitespace and case for project-scoped identity", () => {
    expect(normalizeTaskName("  Discovery Workshop  ")).toBe("discovery workshop");
  });

  test("accepts inheriting and explicit-zero task rate modes", () => {
    expect(
      taskCommandSchema.parse({ name: "Discovery", hourlyRateOverrideMinor: null }),
    ).toMatchObject({ name: "Discovery", hourlyRateOverrideMinor: null });
    expect(
      taskCommandSchema.parse({ name: "Discovery", hourlyRateOverrideMinor: 0 }),
    ).toMatchObject({ name: "Discovery", hourlyRateOverrideMinor: 0 });
  });

  test("rejects blank task names and invalid overrides", () => {
    for (const command of [
      { name: "   ", hourlyRateOverrideMinor: null },
      { name: "Discovery", hourlyRateOverrideMinor: -1 },
      { name: "Discovery", hourlyRateOverrideMinor: 12.5 },
    ]) {
      expect(() => taskCommandSchema.parse(command)).toThrow();
    }
  });

  test("maps a valid persisted task row at the storage boundary", () => {
    expect(
      taskFromRow({
        id: "task-1",
        project_id: "project-1",
        name: "Discovery",
        normalized_name: "discovery",
        hourly_rate_override_minor: 5_000,
        created_at: "2026-08-03T10:00:00.000Z",
        updated_at: "2026-08-03T10:00:00.000Z",
        archived_at: null,
      }),
    ).toMatchObject({
      id: "task-1",
      projectId: "project-1",
      name: "Discovery",
      hourlyRateOverrideMinor: 5_000,
      archivedAt: null,
    });
  });

  test("rejects persisted rows with invalid task ownership or overrides", () => {
    for (const row of [
      {
        id: "task-1",
        project_id: "",
        name: "Discovery",
        normalized_name: "discovery",
        hourly_rate_override_minor: null,
        created_at: "2026-08-03T10:00:00.000Z",
        updated_at: "2026-08-03T10:00:00.000Z",
        archived_at: null,
      },
      {
        id: "task-1",
        project_id: "project-1",
        name: "Discovery",
        normalized_name: "discovery",
        hourly_rate_override_minor: -1,
        created_at: "2026-08-03T10:00:00.000Z",
        updated_at: "2026-08-03T10:00:00.000Z",
        archived_at: null,
      },
    ]) {
      expect(() => taskRowSchema.parse(row)).toThrow();
    }
  });

  test("resolves a task override before project and client values", () => {
    expect(resolveTaskRate(2_500, 5_000, 12_500)).toEqual({
      hourlyRateMinor: 2_500,
      source: "task",
    });
  });

  test("resolves a project override when the task inherits", () => {
    expect(resolveTaskRate(null, 5_000, 12_500)).toEqual({
      hourlyRateMinor: 5_000,
      source: "project",
    });
  });

  test("resolves a client default when task and project inherit", () => {
    expect(resolveTaskRate(null, null, 12_500)).toEqual({
      hourlyRateMinor: 12_500,
      source: "client",
    });
  });

  test("reports an unset rate when every level inherits", () => {
    expect(resolveTaskRate(null, null, null)).toEqual({
      hourlyRateMinor: null,
      source: "unset",
    });
  });

  test.each([
    [0, 5_000, 12_500, "task"],
    [null, 0, 12_500, "project"],
    [null, null, 0, "client"],
  ])("keeps an explicit zero effective from the nearest %s source", (taskRate, projectRate, clientRate, source) => {
    expect(resolveTaskRate(taskRate, projectRate, clientRate)).toEqual({
      hourlyRateMinor: 0,
      source,
    });
  });
});
