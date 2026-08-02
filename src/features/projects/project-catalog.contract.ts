import { describe, expect, test } from "vitest";

import type { ProjectCatalog } from "./project-catalog";

export function projectCatalogContract(
  label: string,
  createCatalog: () => ProjectCatalog,
) {
  describe(`${label} project catalog contract`, () => {
    test("creates, edits, and lists active projects for a client", async () => {
      const catalog = createCatalog();
      const project = await catalog.create("client-1", {
        name: "Website",
        hourlyRateOverrideMinor: null,
      });

      await catalog.update("client-1", project.id, {
        name: "Website redesign",
        hourlyRateOverrideMinor: 0,
      });

      await expect(catalog.list("client-1", "active")).resolves.toMatchObject([
        {
          id: project.id,
          clientId: "client-1",
          name: "Website redesign",
          hourlyRateOverrideMinor: 0,
          archivedAt: null,
        },
      ]);
    });

    test("scopes active name uniqueness to a client", async () => {
      const catalog = createCatalog();
      await catalog.create("client-1", {
        name: "Website",
        hourlyRateOverrideMinor: null,
      });

      await expect(
        catalog.create("client-1", {
          name: "  WEBSITE  ",
          hourlyRateOverrideMinor: null,
        }),
      ).rejects.toMatchObject({ code: "duplicate-name" });

      await expect(
        catalog.create("client-2", {
          name: "Website",
          hourlyRateOverrideMinor: null,
        }),
      ).resolves.toMatchObject({ clientId: "client-2" });
    });

    test("archives without deleting and keeps lists separate", async () => {
      const catalog = createCatalog();
      const project = await catalog.create("client-1", {
        name: "Website",
        hourlyRateOverrideMinor: null,
      });

      await catalog.archive("client-1", project.id);

      await expect(catalog.list("client-1", "active")).resolves.toEqual([]);
      await expect(catalog.list("client-1", "archived")).resolves.toMatchObject([
        { id: project.id, archivedAt: expect.any(String) },
      ]);
    });
  });
}
