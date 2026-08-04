import { describe, expect, test } from "vitest";

import type { ClientCatalog } from "./client-catalog";

export function clientCatalogContract(
  label: string,
  createCatalog: () => ClientCatalog,
) {
  describe(`${label} client catalog contract`, () => {
    test("creates, edits, and lists active clients", async () => {
      const catalog = createCatalog();
      const client = await catalog.create({
        name: "Acme",
        currencyCode: "EUR",
        hourlyRateMinor: 12_500,
      });

      await catalog.update(client.id, {
        name: "Acme Studio",
        currencyCode: "USD",
        hourlyRateMinor: 0,
      });

      await expect(catalog.list("active")).resolves.toMatchObject([
        {
          id: client.id,
          name: "Acme Studio",
          currencyCode: "USD",
          hourlyRateMinor: 0,
          archivedAt: null,
        },
      ]);
    });

    test("rejects normalized duplicate names among active clients", async () => {
      const catalog = createCatalog();
      await catalog.create({
        name: "Acme",
        currencyCode: "EUR",
        hourlyRateMinor: null,
      });

      await expect(
        catalog.create({
          name: "  ACME  ",
          currencyCode: "USD",
          hourlyRateMinor: null,
        }),
      ).rejects.toMatchObject({ code: "duplicate-name" });
    });

    test("looks up an active client by ID", async () => {
      const catalog = createCatalog();
      const activeClient = await catalog.create({
        name: "Acme",
        currencyCode: "EUR",
        hourlyRateMinor: null,
      });

      await expect(catalog.get(activeClient.id)).resolves.toMatchObject({
        id: activeClient.id,
        archivedAt: null,
      });
    });

    test("rejects a missing client ID lookup", async () => {
      const catalog = createCatalog();

      await expect(catalog.get("missing-client")).rejects.toMatchObject({
        code: "not-found",
      });
    });
  });
}
