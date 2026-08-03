import { expect, test } from "vitest";

import { ClientCatalogError } from "./client-catalog";
import { clientCatalogContract } from "./client-catalog.contract";
import { InMemoryClientCatalog } from "./in-memory-client-catalog";

clientCatalogContract("in-memory", () => new InMemoryClientCatalog());

test("surfaces configured persistence errors", async () => {
  const error = new ClientCatalogError("persistence", "Storage unavailable");
  const catalog = new InMemoryClientCatalog({ failure: error });

  await expect(catalog.list("active")).rejects.toBe(error);
  await expect(
    catalog.create({
      name: "Acme",
      currencyCode: "EUR",
      hourlyRateMinor: null,
    }),
  ).rejects.toBe(error);
  await expect(catalog.get("client-1")).rejects.toBe(error);
});
