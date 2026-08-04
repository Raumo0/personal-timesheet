import { describe, expect, test } from "vitest";

import { buildClientUpdatePlan } from "./client-update-plan";

const createdAt = "2026-07-30T08:00:00.000Z";
const previousUpdatedAt = "2026-07-31T09:00:00.000Z";
const updateTimestamp = "2026-08-04T10:15:00.000Z";

const clientRow = {
  id: "client-1",
  name: "Acme",
  normalized_name: "acme",
  currency_code: "EUR",
  hourly_rate_minor: 12_500,
  created_at: createdAt,
  updated_at: previousUpdatedAt,
  archived_at: null,
};

const command = {
  name: " Acme Consulting ",
  currencyCode: "JPY",
  hourlyRateMinor: 125,
};

function buildPlan(overrides: Record<string, unknown> = {}) {
  return buildClientUpdatePlan({
    clientRow,
    command,
    projectRows: [],
    taskRows: [],
    updatedAt: updateTimestamp,
    ...overrides,
  });
}

describe("Client update plan", () => {
  test("keeps override values unchanged when the currency-change branch is accidentally taken", () => {
    const plan = buildPlan({
      command: {
        name: "Acme Consulting",
        currencyCode: "EUR",
        hourlyRateMinor: 13_000,
      },
      projectRows: [
        { id: "project-1", hourly_rate_override_minor: 12_501, updated_at: previousUpdatedAt },
      ],
      taskRows: [{ id: "task-1", hourly_rate_override_minor: 7_503, updated_at: previousUpdatedAt }],
    });

    expect(plan.overrides).toEqual([
      {
        kind: "project",
        id: "project-1",
        expectedHourlyRateOverrideMinor: 12_501,
        expectedUpdatedAt: previousUpdatedAt,
        hourlyRateOverrideMinor: 12_501,
      },
      {
        kind: "task",
        id: "task-1",
        expectedHourlyRateOverrideMinor: 7_503,
        expectedUpdatedAt: previousUpdatedAt,
        hourlyRateOverrideMinor: 7_503,
      },
    ]);
  });

  test("rescales Project and Task overrides exactly when either precision direction is implemented incorrectly", () => {
    const jpyToEur = buildPlan({
      clientRow: { ...clientRow, currency_code: "JPY", hourly_rate_minor: 125 },
      command: {
        name: "Acme",
        currencyCode: "EUR",
        hourlyRateMinor: 12_500,
      },
      projectRows: [{ id: "project-1", hourly_rate_override_minor: 125, updated_at: previousUpdatedAt }],
      taskRows: [{ id: "task-1", hourly_rate_override_minor: 75, updated_at: previousUpdatedAt }],
    });
    const eurToJpy = buildPlan({
      projectRows: [{ id: "project-1", hourly_rate_override_minor: 12_500, updated_at: previousUpdatedAt }],
      taskRows: [{ id: "task-1", hourly_rate_override_minor: 7_500, updated_at: previousUpdatedAt }],
    });

    expect(jpyToEur.overrides).toEqual([
      {
        kind: "project",
        id: "project-1",
        expectedHourlyRateOverrideMinor: 125,
        expectedUpdatedAt: previousUpdatedAt,
        hourlyRateOverrideMinor: 12_500,
      },
      {
        kind: "task",
        id: "task-1",
        expectedHourlyRateOverrideMinor: 75,
        expectedUpdatedAt: previousUpdatedAt,
        hourlyRateOverrideMinor: 7_500,
      },
    ]);
    expect(eurToJpy.overrides).toEqual([
      {
        kind: "project",
        id: "project-1",
        expectedHourlyRateOverrideMinor: 12_500,
        expectedUpdatedAt: previousUpdatedAt,
        hourlyRateOverrideMinor: 125,
      },
      {
        kind: "task",
        id: "task-1",
        expectedHourlyRateOverrideMinor: 7_500,
        expectedUpdatedAt: previousUpdatedAt,
        hourlyRateOverrideMinor: 75,
      },
    ]);
  });

  test("preserves zero overrides when truthiness filtering drops valid selected rows", () => {
    const plan = buildPlan({
      projectRows: [{ id: "project-zero", hourly_rate_override_minor: 0, updated_at: previousUpdatedAt }],
      taskRows: [{ id: "task-zero", hourly_rate_override_minor: 0, updated_at: previousUpdatedAt }],
    });

    expect(plan.overrides).toEqual([
      {
        kind: "project",
        id: "project-zero",
        expectedHourlyRateOverrideMinor: 0,
        expectedUpdatedAt: previousUpdatedAt,
        hourlyRateOverrideMinor: 0,
      },
      {
        kind: "task",
        id: "task-zero",
        expectedHourlyRateOverrideMinor: 0,
        expectedUpdatedAt: previousUpdatedAt,
        hourlyRateOverrideMinor: 0,
      },
    ]);
  });

  test("rejects lossy Project and Task precision when truncating division is introduced", () => {
    expect(() =>
      buildPlan({
        projectRows: [{ id: "project-lossy", hourly_rate_override_minor: 12_550, updated_at: previousUpdatedAt }],
      }),
    ).toThrow("Hourly rate cannot be represented in the new currency");
    expect(() =>
      buildPlan({
        taskRows: [{ id: "task-lossy", hourly_rate_override_minor: 7_550, updated_at: previousUpdatedAt }],
      }),
    ).toThrow("Hourly rate cannot be represented in the new currency");
  });

  test.each([
    ["non-object Project", "projectRows", null],
    ["empty Project ID", "projectRows", { id: "", hourly_rate_override_minor: 100 }],
    ["string Project rate", "projectRows", { id: "project-1", hourly_rate_override_minor: "100" }],
    ["fractional Task rate", "taskRows", { id: "task-1", hourly_rate_override_minor: 1.5 }],
    ["negative Task rate", "taskRows", { id: "task-1", hourly_rate_override_minor: -1 }],
    ["unsafe Task rate", "taskRows", { id: "task-1", hourly_rate_override_minor: Number.MAX_SAFE_INTEGER + 1 }],
  ])("rejects a malformed selected %s row when unchecked casts are introduced", (_label, collection, row) => {
    expect(() => buildPlan({ [collection]: [row] })).toThrow();
  });

  test("orders Projects before Tasks and each kind by ID when database row order leaks into the plan", () => {
    const plan = buildPlan({
      projectRows: [
        { id: "project-z", hourly_rate_override_minor: 20_000, updated_at: previousUpdatedAt },
        { id: "project-a", hourly_rate_override_minor: 10_000, updated_at: previousUpdatedAt },
      ],
      taskRows: [
        { id: "task-z", hourly_rate_override_minor: 9_000, updated_at: previousUpdatedAt },
        { id: "task-a", hourly_rate_override_minor: 8_000, updated_at: previousUpdatedAt },
      ],
    });

    expect(plan.overrides.map(({ kind, id }) => `${kind}:${id}`)).toEqual([
      "project:project-a",
      "project:project-z",
      "task:task-a",
      "task:task-z",
    ]);
  });

  test("orders override IDs by locale-independent ordinal value", () => {
    const plan = buildPlan({
      projectRows: [
        { id: "a-project", hourly_rate_override_minor: 10_000, updated_at: previousUpdatedAt },
        { id: "Z-project", hourly_rate_override_minor: 20_000, updated_at: previousUpdatedAt },
      ],
    });

    expect(plan.overrides.map(({ id }) => id)).toEqual([
      "Z-project",
      "a-project",
    ]);
  });

  test("captures the complete Client and descendant expected state when stale-plan fields are omitted", () => {
    const plan = buildPlan({
      projectRows: [{ id: "project-1", hourly_rate_override_minor: 12_500, updated_at: previousUpdatedAt }],
      taskRows: [{ id: "task-1", hourly_rate_override_minor: 7_500, updated_at: previousUpdatedAt }],
    });

    expect(plan).toEqual({
      clientId: "client-1",
      expectedClient: {
        id: "client-1",
        name: "Acme",
        normalizedName: "acme",
        currencyCode: "EUR",
        hourlyRateMinor: 12_500,
        createdAt,
        updatedAt: previousUpdatedAt,
        archivedAt: null,
      },
      client: {
        id: "client-1",
        name: "Acme Consulting",
        normalizedName: "acme consulting",
        currencyCode: "JPY",
        hourlyRateMinor: 125,
        createdAt,
        updatedAt: updateTimestamp,
        archivedAt: null,
      },
      overrides: [
        {
          kind: "project",
          id: "project-1",
          expectedHourlyRateOverrideMinor: 12_500,
          expectedUpdatedAt: previousUpdatedAt,
          hourlyRateOverrideMinor: 125,
        },
        {
          kind: "task",
          id: "task-1",
          expectedHourlyRateOverrideMinor: 7_500,
          expectedUpdatedAt: previousUpdatedAt,
          hourlyRateOverrideMinor: 75,
        },
      ],
      updatedAt: updateTimestamp,
    });
  });
});
