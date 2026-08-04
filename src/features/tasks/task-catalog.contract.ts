import { describe, expect, test } from "vitest";

import type { TaskCatalog } from "./task-catalog";

export function taskCatalogContract(
  label: string,
  createCatalog: () => TaskCatalog,
) {
  describe(`${label} task catalog contract`, () => {
    test("creates, edits, and lists active tasks for a project", async () => {
      const catalog = createCatalog();
      const task = await catalog.create("project-1", {
        name: "Discovery",
        hourlyRateOverrideMinor: null,
      });

      await catalog.update("project-1", task.id, {
        name: "Discovery workshop",
        hourlyRateOverrideMinor: 0,
      });

      await expect(catalog.list("project-1", "active")).resolves.toMatchObject([
        {
          id: task.id,
          projectId: "project-1",
          name: "Discovery workshop",
          hourlyRateOverrideMinor: 0,
          archivedAt: null,
        },
      ]);
    });

    test("scopes active name uniqueness to a project", async () => {
      const catalog = createCatalog();
      await catalog.create("project-1", {
        name: "Discovery",
        hourlyRateOverrideMinor: null,
      });

      await expect(
        catalog.create("project-1", {
          name: "  DISCOVERY  ",
          hourlyRateOverrideMinor: null,
        }),
      ).rejects.toMatchObject({ code: "duplicate-name" });

      await expect(
        catalog.create("project-2", {
          name: "Discovery",
          hourlyRateOverrideMinor: null,
        }),
      ).resolves.toMatchObject({ projectId: "project-2" });
    });

  });
}
