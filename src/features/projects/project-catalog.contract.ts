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

    test("looks up active and archived projects by their client and project IDs", async () => {
      const catalog = createCatalog();
      const activeProject = await catalog.create("client-1", {
        name: "Website",
        hourlyRateOverrideMinor: null,
      });
      const archivedProject = await catalog.create("client-1", {
        name: "Mobile app",
        hourlyRateOverrideMinor: 0,
      });
      await catalog.archive("client-1", archivedProject.id);

      await expect(catalog.get("client-1", activeProject.id)).resolves.toMatchObject({
        id: activeProject.id,
        clientId: "client-1",
        archivedAt: null,
      });
      await expect(catalog.get("client-1", archivedProject.id)).resolves.toMatchObject({
        id: archivedProject.id,
        clientId: "client-1",
        archivedAt: expect.any(String),
      });
    });

    test("rejects missing and mismatched project ID lookups", async () => {
      const catalog = createCatalog();
      const project = await catalog.create("client-1", {
        name: "Website",
        hourlyRateOverrideMinor: null,
      });

      await expect(catalog.get("client-1", "missing-project")).rejects.toMatchObject({
        code: "not-found",
      });
      await expect(catalog.get("client-2", project.id)).rejects.toMatchObject({
        code: "not-found",
      });
    });
  });
}
