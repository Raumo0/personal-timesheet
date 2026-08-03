import { catalogLifecycleContract } from "./catalog-lifecycle.contract";
import { InMemoryCatalogLifecycle } from "./in-memory-catalog-lifecycle";

catalogLifecycleContract("In-memory catalog lifecycle", (hierarchy, options) => {
  const lifecycle = new InMemoryCatalogLifecycle({
    hierarchy,
    now: options?.now,
    applyFailure: options?.applyFailure,
  });
  return {
    lifecycle,
    snapshot: () => lifecycle.snapshot(),
    replaceSnapshot: (nextHierarchy) => lifecycle.replaceSnapshot(nextHierarchy),
  };
});
