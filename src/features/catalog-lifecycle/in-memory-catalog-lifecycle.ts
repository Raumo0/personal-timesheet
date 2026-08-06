import {
  CatalogLifecycleError,
  planCatalogLifecycle,
  type CatalogHierarchy,
  type CatalogLifecycle,
  type LifecyclePlan,
  type LifecycleRecord,
  type LifecycleRequest,
} from "./catalog-lifecycle";

interface InMemoryCatalogLifecycleOptions {
  hierarchy: CatalogHierarchy;
  now?: () => Date;
  applyFailure?: () => unknown | undefined;
}

export class InMemoryCatalogLifecycle implements CatalogLifecycle {
  private hierarchy: CatalogHierarchy;
  private readonly now: () => Date;
  private readonly applyFailure?: () => unknown | undefined;

  constructor(options: InMemoryCatalogLifecycleOptions) {
    this.hierarchy = structuredClone(options.hierarchy);
    this.now = options.now ?? (() => new Date());
    this.applyFailure = options.applyFailure;
  }

  async preview(request: LifecycleRequest): Promise<LifecyclePlan> {
    return planCatalogLifecycle(this.hierarchy, request);
  }

  async apply(plan: LifecyclePlan): Promise<void> {
    this.assertFresh(plan);
    const replacement = structuredClone(this.hierarchy);
    const appliedAt = this.now().toISOString();

    for (const record of plan.records) {
      const candidate = findRecord(replacement, record);
      candidate.archivedAt = plan.operation === "archive" ? appliedAt : null;
      candidate.updatedAt = appliedAt;
    }

    try {
      const failure = this.applyFailure?.();
      if (failure !== undefined) throw failure;
    } catch (cause) {
      throw new CatalogLifecycleError(
        "persistence",
        cause instanceof Error ? cause.message : "Lifecycle change was not saved",
        cause,
      );
    }

    this.hierarchy = replacement;
  }

  snapshot(): CatalogHierarchy {
    return structuredClone(this.hierarchy);
  }

  replaceSnapshot(hierarchy: CatalogHierarchy): void {
    this.hierarchy = structuredClone(hierarchy);
  }

  private assertFresh(plan: LifecyclePlan): void {
    let currentPlan: LifecyclePlan;
    try {
      currentPlan = planCatalogLifecycle(this.hierarchy, {
        operation: plan.operation,
        target: plan.target,
      });
    } catch {
      throw stalePlanError();
    }

    if (!samePlan(plan, currentPlan)) {
      throw stalePlanError();
    }
  }
}

type MutableLifecycleRecord = {
  id: string;
  archivedAt: string | null;
  updatedAt: string;
};

function findRecord(
  hierarchy: CatalogHierarchy,
  record: LifecycleRecord,
): MutableLifecycleRecord {
  const records =
    record.kind === "client"
      ? hierarchy.clients
      : record.kind === "project"
        ? hierarchy.projects
        : record.kind === "task"
          ? hierarchy.tasks
          : (hierarchy.expenses ?? []);
  const found = records.find((candidate) => candidate.id === record.id);
  if (!found) {
    throw new CatalogLifecycleError(
      "invalid-hierarchy",
      "Lifecycle plan contains a record outside the hierarchy",
    );
  }
  return found;
}

function samePlan(expected: LifecyclePlan, current: LifecyclePlan): boolean {
  if (
    expected.operation !== current.operation ||
    expected.target.kind !== current.target.kind ||
    expected.target.id !== current.target.id ||
    expected.impactDescription !== current.impactDescription ||
    expected.records.length !== current.records.length
  ) {
    return false;
  }

  return expected.records.every((record, index) => {
    const candidate = current.records[index];
    return (
      candidate !== undefined &&
      record.kind === candidate.kind &&
      record.id === candidate.id &&
      record.name === candidate.name &&
      record.archivedAt === candidate.archivedAt
    );
  });
}

function stalePlanError(): CatalogLifecycleError {
  return new CatalogLifecycleError(
    "stale-plan",
    "Lifecycle plan is stale; preview the current hierarchy and try again",
  );
}
