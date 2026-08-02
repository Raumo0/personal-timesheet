import { expect, test } from "vitest";

import { InMemoryProjectCatalog } from "./in-memory-project-catalog";
import { ProjectCatalogError } from "./project-catalog";
import { projectCatalogContract } from "./project-catalog.contract";

projectCatalogContract("in-memory", () => new InMemoryProjectCatalog());

test("surfaces configured persistence errors", async () => {
  const error = new ProjectCatalogError("persistence", "Storage unavailable");
  const catalog = new InMemoryProjectCatalog({ failure: error });

  await expect(catalog.list("client-1", "active")).rejects.toBe(error);
  await expect(
    catalog.create("client-1", {
      name: "Website",
      hourlyRateOverrideMinor: null,
    }),
  ).rejects.toBe(error);
});
