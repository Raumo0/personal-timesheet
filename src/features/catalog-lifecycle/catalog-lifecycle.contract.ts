import { expect, test, vi } from "vitest";

import {
  CatalogLifecycleError,
  planCatalogLifecycle,
  type CatalogHierarchy,
  type CatalogLifecycle,
  type LifecycleRequest,
} from "./catalog-lifecycle";

export interface CatalogLifecycleHarness {
  lifecycle: CatalogLifecycle;
  snapshot(): CatalogHierarchy;
  replaceSnapshot(hierarchy: CatalogHierarchy): void;
}

export interface CatalogLifecycleHarnessOptions {
  now?: () => Date;
  applyFailure?: () => unknown | undefined;
}

export function catalogLifecycleContract(
  adapterName: string,
  createHarness: (
    hierarchy: CatalogHierarchy,
    options?: CatalogLifecycleHarnessOptions,
  ) => CatalogLifecycleHarness,
) {
  const archivedAt = "2026-08-04T09:00:00.000Z";
  const appliedAt = "2026-08-05T10:30:00.000Z";

  test(`${adapterName} previews with the shared directional planner`, async () => {
    const hierarchy = hierarchyFixture();
    const harness = createHarness(hierarchy);
    const request: LifecycleRequest = {
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    };

    await expect(harness.lifecycle.preview(request)).resolves.toEqual(
      planCatalogLifecycle(hierarchy, request),
    );
    expect(harness.snapshot()).toEqual(hierarchy);
  });

  test(`${adapterName} atomically applies archive records with one fresh timestamp`, async () => {
    const hierarchy = hierarchyFixture({ archivedTaskAt: archivedAt });
    const harness = createHarness(hierarchy, {
      now: () => new Date(appliedAt),
    });
    const plan = await harness.lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });

    await harness.lifecycle.apply(plan);

    expect(harness.snapshot()).toEqual(
      hierarchyFixture({
        clientArchivedAt: appliedAt,
        clientUpdatedAt: appliedAt,
        projectArchivedAt: appliedAt,
        projectUpdatedAt: appliedAt,
        activeTaskArchivedAt: appliedAt,
        activeTaskUpdatedAt: appliedAt,
        archivedTaskAt: archivedAt,
      }),
    );
  });

  test(`${adapterName} restores only the target and archived ancestor path`, async () => {
    const hierarchy = hierarchyFixture({
      clientArchivedAt: archivedAt,
      projectArchivedAt: archivedAt,
      activeTaskArchivedAt: archivedAt,
      archivedTaskAt: archivedAt,
    });
    const harness = createHarness(hierarchy, {
      now: () => new Date(appliedAt),
    });
    const plan = await harness.lifecycle.preview({
      operation: "restore",
      target: { kind: "task", id: "task-1" },
    });

    await harness.lifecycle.apply(plan);

    expect(harness.snapshot()).toEqual(
      hierarchyFixture({
        clientArchivedAt: null,
        clientUpdatedAt: appliedAt,
        projectArchivedAt: null,
        projectUpdatedAt: appliedAt,
        activeTaskArchivedAt: null,
        activeTaskUpdatedAt: appliedAt,
        archivedTaskAt: archivedAt,
      }),
    );
  });

  test(`${adapterName} rejects a stale plan without a partial update`, async () => {
    const hierarchy = hierarchyFixture();
    const harness = createHarness(hierarchy, {
      now: () => new Date(appliedAt),
    });
    const staleClientPlan = await harness.lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });
    const taskPlan = await harness.lifecycle.preview({
      operation: "archive",
      target: { kind: "task", id: "task-1" },
    });
    await harness.lifecycle.apply(taskPlan);
    const beforeStaleApply = harness.snapshot();

    await expect(harness.lifecycle.apply(staleClientPlan)).rejects.toEqual(
      expect.objectContaining<CatalogLifecycleError>({ code: "stale-plan" }),
    );
    expect(harness.snapshot()).toEqual(beforeStaleApply);
  });

  test(`${adapterName} rejects a plan when a new active descendant changes its scope`, async () => {
    const hierarchy = hierarchyFixture();
    const now = vi.fn(() => new Date(appliedAt));
    const applyFailure = vi.fn(() => undefined);
    const harness = createHarness(hierarchy, { now, applyFailure });
    const plan = await harness.lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });
    const current = harness.snapshot();
    const changed: CatalogHierarchy = {
      ...current,
      tasks: [
        ...current.tasks,
        {
          id: "task-new",
          projectId: "project-1",
          name: "New scope",
          hourlyRateOverrideMinor: null,
          createdAt: "2026-08-05T09:00:00.000Z",
          updatedAt: "2026-08-05T09:00:00.000Z",
          archivedAt: null,
        },
      ],
    };
    harness.replaceSnapshot(changed);

    await expect(harness.lifecycle.apply(plan)).rejects.toEqual(
      expect.objectContaining<CatalogLifecycleError>({ code: "stale-plan" }),
    );
    expect(harness.snapshot()).toEqual(changed);
    expect(now).not.toHaveBeenCalled();
    expect(applyFailure).not.toHaveBeenCalled();
  });

  test(`${adapterName} rejects a plan when an excluded archived descendant disappears`, async () => {
    const hierarchy = hierarchyFixture({ archivedTaskAt: archivedAt });
    const now = vi.fn(() => new Date(appliedAt));
    const applyFailure = vi.fn(() => undefined);
    const harness = createHarness(hierarchy, { now, applyFailure });
    const plan = await harness.lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });
    const current = harness.snapshot();
    const changed: CatalogHierarchy = {
      ...current,
      tasks: current.tasks.filter((task) => task.id !== "task-2"),
    };
    harness.replaceSnapshot(changed);

    await expect(harness.lifecycle.apply(plan)).rejects.toEqual(
      expect.objectContaining<CatalogLifecycleError>({ code: "stale-plan" }),
    );
    expect(harness.snapshot()).toEqual(changed);
    expect(now).not.toHaveBeenCalled();
    expect(applyFailure).not.toHaveBeenCalled();
  });

  test(`${adapterName} leaves the hierarchy unchanged when apply persistence fails`, async () => {
    const hierarchy = hierarchyFixture();
    const harness = createHarness(hierarchy, {
      now: () => new Date(appliedAt),
      applyFailure: () => new Error("disk unavailable"),
    });
    const plan = await harness.lifecycle.preview({
      operation: "archive",
      target: { kind: "client", id: "client-1" },
    });

    await expect(harness.lifecycle.apply(plan)).rejects.toEqual(
      expect.objectContaining<CatalogLifecycleError>({ code: "persistence" }),
    );
    expect(harness.snapshot()).toEqual(hierarchy);
  });

  test(`${adapterName} can preview a fresh retry after a transient atomic failure`, async () => {
    const hierarchy = hierarchyFixture();
    let attempts = 0;
    const harness = createHarness(hierarchy, {
      now: () => new Date(appliedAt),
      applyFailure: () =>
        attempts++ === 0 ? new Error("database busy") : undefined,
    });
    const firstPlan = await harness.lifecycle.preview({
      operation: "archive",
      target: { kind: "project", id: "project-1" },
    });
    await expect(harness.lifecycle.apply(firstPlan)).rejects.toEqual(
      expect.objectContaining<CatalogLifecycleError>({ code: "persistence" }),
    );

    const retryPlan = await harness.lifecycle.preview({
      operation: "archive",
      target: { kind: "project", id: "project-1" },
    });
    expect(retryPlan).toEqual(firstPlan);
    await harness.lifecycle.apply(retryPlan);

    expect(harness.snapshot().projects[0].archivedAt).toBe(appliedAt);
    expect(harness.snapshot().tasks[0].archivedAt).toBe(appliedAt);
  });
}

function hierarchyFixture(
  states: {
    clientArchivedAt?: string | null;
    clientUpdatedAt?: string;
    projectArchivedAt?: string | null;
    projectUpdatedAt?: string;
    activeTaskArchivedAt?: string | null;
    activeTaskUpdatedAt?: string;
    archivedTaskAt?: string | null;
  } = {},
): CatalogHierarchy {
  const createdAt = "2026-08-03T08:00:00.000Z";
  return {
    clients: [
      {
        id: "client-1",
        name: "Acme",
        currencyCode: "EUR",
        hourlyRateMinor: null,
        createdAt,
        updatedAt: states.clientUpdatedAt ?? createdAt,
        archivedAt: states.clientArchivedAt ?? null,
      },
      {
        id: "client-2",
        name: "Globex",
        currencyCode: "EUR",
        hourlyRateMinor: null,
        createdAt,
        updatedAt: createdAt,
        archivedAt: null,
      },
    ],
    projects: [
      {
        id: "project-1",
        clientId: "client-1",
        name: "Website",
        hourlyRateOverrideMinor: null,
        createdAt,
        updatedAt: states.projectUpdatedAt ?? createdAt,
        archivedAt: states.projectArchivedAt ?? null,
      },
      {
        id: "project-2",
        clientId: "client-2",
        name: "Portal",
        hourlyRateOverrideMinor: null,
        createdAt,
        updatedAt: createdAt,
        archivedAt: null,
      },
    ],
    tasks: [
      {
        id: "task-1",
        projectId: "project-1",
        name: "Research",
        hourlyRateOverrideMinor: null,
        createdAt,
        updatedAt: states.activeTaskUpdatedAt ?? createdAt,
        archivedAt: states.activeTaskArchivedAt ?? null,
      },
      {
        id: "task-2",
        projectId: "project-1",
        name: "Retired review",
        hourlyRateOverrideMinor: null,
        createdAt,
        updatedAt: createdAt,
        archivedAt: states.archivedTaskAt ?? null,
      },
      {
        id: "task-3",
        projectId: "project-2",
        name: "Audit",
        hourlyRateOverrideMinor: null,
        createdAt,
        updatedAt: createdAt,
        archivedAt: null,
      },
    ],
  };
}
