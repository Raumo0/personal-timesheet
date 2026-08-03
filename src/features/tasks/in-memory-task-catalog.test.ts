import { expect, test } from "vitest";

import { InMemoryTaskCatalog } from "./in-memory-task-catalog";
import { TaskCatalogError } from "./task-catalog";
import { taskCatalogContract } from "./task-catalog.contract";

taskCatalogContract("in-memory", () => new InMemoryTaskCatalog());

test("surfaces configured persistence errors", async () => {
  const error = new TaskCatalogError("persistence", "Storage unavailable");
  const catalog = new InMemoryTaskCatalog({ failure: error });

  await expect(catalog.list("project-1", "active")).rejects.toBe(error);
  await expect(
    catalog.create("project-1", {
      name: "Discovery",
      hourlyRateOverrideMinor: null,
    }),
  ).rejects.toBe(error);
});
