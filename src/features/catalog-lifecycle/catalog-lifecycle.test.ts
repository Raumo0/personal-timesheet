import { expect, test } from "vitest";

import type { Client } from "../clients/client";
import type { Project } from "../projects/project";
import type { Task } from "../tasks/task";
import type { Expense } from "../expenses/expense";
import {
  planCatalogLifecycle,
  type CatalogHierarchy,
  type LifecycleRecord,
} from "./catalog-lifecycle";

const activeTimestamp = "2026-08-03T08:00:00.000Z";
const archivedTimestamp = "2026-08-04T09:00:00.000Z";
const earlierArchivedTimestamp = "2026-07-20T07:00:00.000Z";

function client(
  id: string,
  name: string,
  archivedAt: string | null = null,
): Client {
  return {
    id,
    name,
    currencyCode: "EUR",
    hourlyRateMinor: null,
    createdAt: activeTimestamp,
    updatedAt: activeTimestamp,
    archivedAt,
  };
}

function project(
  id: string,
  clientId: string,
  name: string,
  archivedAt: string | null = null,
): Project {
  return {
    id,
    clientId,
    name,
    hourlyRateOverrideMinor: null,
    createdAt: activeTimestamp,
    updatedAt: activeTimestamp,
    archivedAt,
  };
}

function task(
  id: string,
  projectId: string,
  name: string,
  archivedAt: string | null = null,
): Task {
  return {
    id,
    projectId,
    name,
    hourlyRateOverrideMinor: null,
    createdAt: activeTimestamp,
    updatedAt: activeTimestamp,
    archivedAt,
  };
}

function record(
  kind: LifecycleRecord["kind"],
  id: string,
  name: string,
  archivedAt: string | null,
): LifecycleRecord {
  return { kind, id, name, archivedAt };
}

function expense(
  id: string,
  target: Expense["target"],
  description: string,
  archivedAt: string | null = null,
): Expense {
  return {
    id, target, expenseDate: "2026-08-06", description,
    originalCurrencyCode: "EUR", originalAmountMinor: 100,
    billingCurrencyCode: "EUR", billingAmountMinor: 100, appliedRate: "1",
    rateSource: "manual", rateObservedOn: null, rateManuallyAdjusted: false,
    createdAt: activeTimestamp, updatedAt: activeTimestamp, archivedAt,
  };
}

const activeHierarchy: CatalogHierarchy = {
  clients: [client("client-1", "Acme"), client("client-2", "Globex")],
  projects: [
    project("project-1", "client-1", "Website"),
    project("project-2", "client-1", "Mobile app"),
    project("project-3", "client-2", "Portal"),
  ],
  tasks: [
    task("task-1", "project-1", "Research"),
    task("task-2", "project-1", "Delivery"),
    task("task-3", "project-2", "Prototype"),
    task("task-4", "project-3", "Audit"),
  ],
};

test("plans an Expense-only archive with exact impact", () => {
  const hierarchy: CatalogHierarchy = {
    ...activeHierarchy,
    expenses: [
      expense("expense-1", { kind: "client", clientId: "client-1" }, "Train"),
      expense("expense-2", { kind: "client", clientId: "client-1" }, "Hotel"),
    ],
  };
  const plan = planCatalogLifecycle(hierarchy, {
    operation: "archive",
    target: { kind: "expense", id: "expense-1" },
  });
  expect(plan.records).toEqual([record("expense", "expense-1", "Train", null)]);
  expect(plan.impactDescription).toBe("Archive Train.");
});

test("includes active Project Expenses in Project archive and preserves siblings", () => {
  const hierarchy: CatalogHierarchy = {
    ...activeHierarchy,
    expenses: [
      expense("expense-1", { kind: "project", projectId: "project-1" }, "Train"),
      expense("expense-old", { kind: "project", projectId: "project-1" }, "Old", earlierArchivedTimestamp),
      expense("expense-sibling", { kind: "project", projectId: "project-2" }, "Sibling"),
    ],
  };
  const plan = planCatalogLifecycle(hierarchy, {
    operation: "archive",
    target: { kind: "project", id: "project-1" },
  });
  expect(plan.records).toContainEqual(record("expense", "expense-1", "Train", null));
  expect(plan.records).not.toContainEqual(record("expense", "expense-old", "Old", earlierArchivedTimestamp));
  expect(plan.records).not.toContainEqual(record("expense", "expense-sibling", "Sibling", null));
  expect(plan.impactDescription).toBe(
    "Archive Website and every Task and Expense beneath it (2 Tasks, 1 Expense).",
  );
});

test("includes direct and Project Expenses in Client archive with exact totals", () => {
  const hierarchy: CatalogHierarchy = {
    ...activeHierarchy,
    expenses: [
      expense("expense-direct", { kind: "client", clientId: "client-1" }, "Train"),
      expense("expense-project", { kind: "project", projectId: "project-1" }, "Hotel"),
      expense("expense-second", { kind: "project", projectId: "project-2" }, "Taxi"),
      expense("expense-other", { kind: "client", clientId: "client-2" }, "Other"),
    ],
  };
  const plan = planCatalogLifecycle(hierarchy, {
    operation: "archive",
    target: { kind: "client", id: "client-1" },
  });
  expect(plan.records.filter((item) => item.kind === "expense")).toEqual([
    record("expense", "expense-direct", "Train", null),
    record("expense", "expense-project", "Hotel", null),
    record("expense", "expense-second", "Taxi", null),
  ]);
  expect(plan.impactDescription).toBe(
    "Archive Acme and every Project, Task, and Expense beneath it (2 Projects, 3 Tasks, 3 Expenses).",
  );
});

test("excludes archived Expenses from a Project archive impact total", () => {
  const hierarchy: CatalogHierarchy = {
    ...activeHierarchy,
    expenses: [
      expense("expense-active", { kind: "project", projectId: "project-1" }, "Train"),
      expense(
        "expense-archived",
        { kind: "project", projectId: "project-1" },
        "Hotel",
        earlierArchivedTimestamp,
      ),
    ],
  };

  const plan = planCatalogLifecycle(hierarchy, {
    operation: "archive",
    target: { kind: "project", id: "project-1" },
  });

  expect(plan.impactDescription).toBe(
    "Archive Website and every Task and Expense beneath it (2 Tasks, 1 Expense).",
  );
});

test("excludes archived Expenses from a Client archive impact total", () => {
  const hierarchy: CatalogHierarchy = {
    ...activeHierarchy,
    expenses: [
      expense("expense-active", { kind: "client", clientId: "client-1" }, "Train"),
      expense(
        "expense-archived",
        { kind: "project", projectId: "project-1" },
        "Hotel",
        earlierArchivedTimestamp,
      ),
    ],
  };

  const plan = planCatalogLifecycle(hierarchy, {
    operation: "archive",
    target: { kind: "client", id: "client-1" },
  });

  expect(plan.impactDescription).toBe(
    "Archive Acme and every Project, Task, and Expense beneath it (2 Projects, 3 Tasks, 1 Expense).",
  );
});

test.each([
  {
    label: "direct Client Expense",
    target: { kind: "client", clientId: "client-1" } as const,
    expected: [
      record("client", "client-1", "Acme", archivedTimestamp),
      record("expense", "expense-1", "Train", archivedTimestamp),
    ],
    description: "Restore Acme and Train. Sibling records remain unchanged.",
  },
  {
    label: "Project Expense",
    target: { kind: "project", projectId: "project-1" } as const,
    expected: [
      record("client", "client-1", "Acme", archivedTimestamp),
      record("project", "project-1", "Website", archivedTimestamp),
      record("expense", "expense-1", "Train", archivedTimestamp),
    ],
    description: "Restore Acme, Website, and Train. Sibling records remain unchanged.",
  },
])("restores a $label with only required ancestors", ({ target, expected, description }) => {
  const hierarchy: CatalogHierarchy = {
    clients: [client("client-1", "Acme", archivedTimestamp)],
    projects: [project("project-1", "client-1", "Website", archivedTimestamp)],
    tasks: [],
    expenses: [
      expense("expense-1", target, "Train", archivedTimestamp),
      expense("expense-sibling", target, "Sibling", archivedTimestamp),
    ],
  };
  const plan = planCatalogLifecycle(hierarchy, {
    operation: "restore",
    target: { kind: "expense", id: "expense-1" },
  });
  expect(plan.records).toEqual(expected);
  expect(plan.impactDescription).toBe(description);
});

test("rejects a stale Expense plan request after lifecycle state changes", () => {
  const hierarchy: CatalogHierarchy = {
    ...activeHierarchy,
    expenses: [expense("expense-1", { kind: "client", clientId: "client-1" }, "Train", archivedTimestamp)],
  };
  expect(() => planCatalogLifecycle(hierarchy, {
    operation: "archive",
    target: { kind: "expense", id: "expense-1" },
  })).toThrowError(expect.objectContaining({ code: "invalid-state" }));
});

test("plans a Client archive downward through only its active Projects and Tasks", () => {
  const plan = planCatalogLifecycle(activeHierarchy, {
    operation: "archive",
    target: { kind: "client", id: "client-1" },
  });

  expect(plan).toEqual({
    operation: "archive",
    target: { kind: "client", id: "client-1" },
    records: [
      record("client", "client-1", "Acme", null),
      record("project", "project-1", "Website", null),
      record("project", "project-2", "Mobile app", null),
      record("task", "task-1", "Research", null),
      record("task", "task-2", "Delivery", null),
      record("task", "task-3", "Prototype", null),
    ],
    impactDescription:
      "Archive Acme and every Project and Task beneath it (2 Projects, 3 Tasks).",
  });
  expect(plan.records).not.toContainEqual(
    record("project", "project-3", "Portal", null),
  );
  expect(plan.records).not.toContainEqual(record("task", "task-4", "Audit", null));
});

test("plans a Project archive downward through its Tasks without changing siblings", () => {
  const plan = planCatalogLifecycle(activeHierarchy, {
    operation: "archive",
    target: { kind: "project", id: "project-1" },
  });

  expect(plan.records).toEqual([
    record("project", "project-1", "Website", null),
    record("task", "task-1", "Research", null),
    record("task", "task-2", "Delivery", null),
  ]);
  expect(plan.impactDescription).toBe(
    "Archive Website and every Task beneath it (2 Tasks).",
  );
});

test("plans a Task archive without changing its ancestors or sibling Tasks", () => {
  const plan = planCatalogLifecycle(activeHierarchy, {
    operation: "archive",
    target: { kind: "task", id: "task-1" },
  });

  expect(plan.records).toEqual([record("task", "task-1", "Research", null)]);
  expect(plan.impactDescription).toBe("Archive Research.");
});

test("preserves already archived descendant timestamps outside an archive plan", () => {
  const hierarchy: CatalogHierarchy = {
    ...activeHierarchy,
    projects: activeHierarchy.projects.map((candidate) =>
      candidate.id === "project-2"
        ? { ...candidate, archivedAt: earlierArchivedTimestamp }
        : candidate,
    ),
    tasks: activeHierarchy.tasks.map((candidate) =>
      candidate.id === "task-2"
        ? { ...candidate, archivedAt: earlierArchivedTimestamp }
        : candidate,
    ),
  };

  const plan = planCatalogLifecycle(hierarchy, {
    operation: "archive",
    target: { kind: "client", id: "client-1" },
  });

  expect(plan.records).toEqual([
    record("client", "client-1", "Acme", null),
    record("project", "project-1", "Website", null),
    record("task", "task-1", "Research", null),
    record("task", "task-3", "Prototype", null),
  ]);
  expect(hierarchy.projects[1].archivedAt).toBe(earlierArchivedTimestamp);
  expect(hierarchy.tasks[1].archivedAt).toBe(earlierArchivedTimestamp);
  expect(plan.impactDescription).toBe(
    "Archive Acme and every Project and Task beneath it (2 Projects, 3 Tasks).",
  );
});

test("restores only a Client target and leaves every descendant archived", () => {
  const hierarchy: CatalogHierarchy = {
    clients: [client("client-1", "Acme", archivedTimestamp)],
    projects: [project("project-1", "client-1", "Website", archivedTimestamp)],
    tasks: [task("task-1", "project-1", "Research", archivedTimestamp)],
  };

  const plan = planCatalogLifecycle(hierarchy, {
    operation: "restore",
    target: { kind: "client", id: "client-1" },
  });

  expect(plan.records).toEqual([
    record("client", "client-1", "Acme", archivedTimestamp),
  ]);
  expect(plan.impactDescription).toBe(
    "Restore Acme only. Archived Projects and Tasks remain archived.",
  );
});

test("restores a Project with only its archived Client ancestor", () => {
  const hierarchy: CatalogHierarchy = {
    clients: [client("client-1", "Acme", archivedTimestamp)],
    projects: [
      project("project-1", "client-1", "Website", archivedTimestamp),
      project("project-2", "client-1", "Mobile app", archivedTimestamp),
    ],
    tasks: [
      task("task-1", "project-1", "Research", archivedTimestamp),
      task("task-2", "project-2", "Prototype", archivedTimestamp),
    ],
  };

  const plan = planCatalogLifecycle(hierarchy, {
    operation: "restore",
    target: { kind: "project", id: "project-1" },
  });

  expect(plan.records).toEqual([
    record("client", "client-1", "Acme", archivedTimestamp),
    record("project", "project-1", "Website", archivedTimestamp),
  ]);
  expect(plan.impactDescription).toBe(
    "Restore Acme and Website. Tasks beneath Website remain archived.",
  );
});

test("restores an archived Project without including its active Client", () => {
  const hierarchy: CatalogHierarchy = {
    clients: [client("client-1", "Acme")],
    projects: [
      project("project-1", "client-1", "Website", archivedTimestamp),
      project("project-2", "client-1", "Mobile app", archivedTimestamp),
    ],
    tasks: [task("task-1", "project-1", "Research", archivedTimestamp)],
  };

  const plan = planCatalogLifecycle(hierarchy, {
    operation: "restore",
    target: { kind: "project", id: "project-1" },
  });

  expect(plan.records).toEqual([
    record("project", "project-1", "Website", archivedTimestamp),
  ]);
  expect(plan.impactDescription).toBe(
    "Restore Website only. Tasks beneath Website remain archived.",
  );
});

test("restores a Task with exactly its archived ancestor path", () => {
  const hierarchy: CatalogHierarchy = {
    clients: [
      client("client-1", "Acme", archivedTimestamp),
      client("client-2", "Globex", archivedTimestamp),
    ],
    projects: [
      project("project-1", "client-1", "Website", archivedTimestamp),
      project("project-2", "client-1", "Mobile app", archivedTimestamp),
      project("project-3", "client-2", "Portal", archivedTimestamp),
    ],
    tasks: [
      task("task-1", "project-1", "Research", archivedTimestamp),
      task("task-2", "project-1", "Delivery", archivedTimestamp),
      task("task-3", "project-2", "Prototype", archivedTimestamp),
      task("task-4", "project-3", "Audit", archivedTimestamp),
    ],
  };

  const plan = planCatalogLifecycle(hierarchy, {
    operation: "restore",
    target: { kind: "task", id: "task-1" },
  });

  expect(plan.records).toEqual([
    record("client", "client-1", "Acme", archivedTimestamp),
    record("project", "project-1", "Website", archivedTimestamp),
    record("task", "task-1", "Research", archivedTimestamp),
  ]);
  expect(plan.impactDescription).toBe(
    "Restore Acme, Website, and Research. Sibling records remain unchanged.",
  );
});

test.each([
  {
    state: "active Client and Project",
    clientArchivedAt: null,
    projectArchivedAt: null,
    expectedRecords: [record("task", "task-1", "Research", archivedTimestamp)],
    expectedDescription: "Restore Research only. Sibling records remain unchanged.",
  },
  {
    state: "active Client and archived Project",
    clientArchivedAt: null,
    projectArchivedAt: archivedTimestamp,
    expectedRecords: [
      record("project", "project-1", "Website", archivedTimestamp),
      record("task", "task-1", "Research", archivedTimestamp),
    ],
    expectedDescription:
      "Restore Website and Research. Sibling records remain unchanged.",
  },
  {
    state: "archived Client and active Project",
    clientArchivedAt: archivedTimestamp,
    projectArchivedAt: null,
    expectedRecords: [
      record("client", "client-1", "Acme", archivedTimestamp),
      record("task", "task-1", "Research", archivedTimestamp),
    ],
    expectedDescription:
      "Restore Acme and Research. Sibling records remain unchanged.",
  },
])(
  "restores a Task through $state without including active ancestors",
  ({ clientArchivedAt, projectArchivedAt, expectedRecords, expectedDescription }) => {
    const hierarchy: CatalogHierarchy = {
      clients: [client("client-1", "Acme", clientArchivedAt)],
      projects: [
        project("project-1", "client-1", "Website", projectArchivedAt),
        project("project-2", "client-1", "Mobile app", archivedTimestamp),
      ],
      tasks: [
        task("task-1", "project-1", "Research", archivedTimestamp),
        task("task-2", "project-1", "Delivery", archivedTimestamp),
      ],
    };

    const plan = planCatalogLifecycle(hierarchy, {
      operation: "restore",
      target: { kind: "task", id: "task-1" },
    });

    expect(plan.records).toEqual(expectedRecords);
    expect(plan.impactDescription).toBe(expectedDescription);
  },
);

test("returns an immutable plan without mutating the hierarchy snapshot", () => {
  const hierarchy = structuredClone(activeHierarchy);
  const before = structuredClone(hierarchy);

  const plan = planCatalogLifecycle(hierarchy, {
    operation: "archive",
    target: { kind: "project", id: "project-1" },
  });

  expect(hierarchy).toEqual(before);
  expect(Object.isFrozen(plan)).toBe(true);
  expect(Object.isFrozen(plan.target)).toBe(true);
  expect(Object.isFrozen(plan.records)).toBe(true);
  for (const affected of plan.records) {
    expect(Object.isFrozen(affected)).toBe(true);
  }
});

test.each(["archive", "restore"] as const)(
  "rejects a Project %s when its required Client relationship is missing",
  (operation) => {
    const hierarchy: CatalogHierarchy = {
      clients: [],
      projects: [
        project(
          "project-1",
          "client-1",
          "Website",
          operation === "restore" ? archivedTimestamp : null,
        ),
      ],
      tasks: [],
    };

    expect(() =>
      planCatalogLifecycle(hierarchy, {
        operation,
        target: { kind: "project", id: "project-1" },
      }),
    ).toThrowError(
      expect.objectContaining({ code: "invalid-hierarchy" }),
    );
  },
);

test("rejects a Project whose Client identifier does not match any available Client", () => {
  const hierarchy: CatalogHierarchy = {
    clients: [client("client-1", "Acme")],
    projects: [project("project-1", "client-2", "Website")],
    tasks: [],
  };

  expect(() =>
    planCatalogLifecycle(hierarchy, {
      operation: "archive",
      target: { kind: "project", id: "project-1" },
    }),
  ).toThrowError(
    expect.objectContaining({ code: "invalid-hierarchy" }),
  );
});

test.each(["archive", "restore"] as const)(
  "rejects a Task %s when its required Project relationship is missing",
  (operation) => {
    const hierarchy: CatalogHierarchy = {
      clients: [client("client-1", "Acme")],
      projects: [],
      tasks: [
        task(
          "task-1",
          "project-1",
          "Research",
          operation === "restore" ? archivedTimestamp : null,
        ),
      ],
    };

    expect(() =>
      planCatalogLifecycle(hierarchy, {
        operation,
        target: { kind: "task", id: "task-1" },
      }),
    ).toThrowError(
      expect.objectContaining({ code: "invalid-hierarchy" }),
    );
  },
);

test("rejects a Task whose Project identifier does not match an available Project", () => {
  const hierarchy: CatalogHierarchy = {
    clients: [client("client-1", "Acme")],
    projects: [project("project-1", "client-1", "Website")],
    tasks: [task("task-1", "project-2", "Research")],
  };

  expect(() =>
    planCatalogLifecycle(hierarchy, {
      operation: "archive",
      target: { kind: "task", id: "task-1" },
    }),
  ).toThrowError(
    expect.objectContaining({ code: "invalid-hierarchy" }),
  );
});

test.each(["archive", "restore"] as const)(
  "rejects a Task %s when its Project has no matching Client",
  (operation) => {
    const hierarchy: CatalogHierarchy = {
      clients: [client("client-1", "Acme")],
      projects: [project("project-1", "client-2", "Website")],
      tasks: [
        task(
          "task-1",
          "project-1",
          "Research",
          operation === "restore" ? archivedTimestamp : null,
        ),
      ],
    };

    expect(() =>
      planCatalogLifecycle(hierarchy, {
        operation,
        target: { kind: "task", id: "task-1" },
      }),
    ).toThrowError(
      expect.objectContaining({ code: "invalid-hierarchy" }),
    );
  },
);

test("keeps an absent requested target distinct from malformed hierarchy", () => {
  expect(() =>
    planCatalogLifecycle(activeHierarchy, {
      operation: "archive",
      target: { kind: "task", id: "missing-task" },
    }),
  ).toThrowError(
    expect.objectContaining({ code: "not-found" }),
  );
});
