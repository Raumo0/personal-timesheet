import { weeklyTimeEntryStoreContract } from "./weekly-time-entry-store.contract";
import { InMemoryWeeklyTimeEntryStore } from "./in-memory-weekly-time-entry-store";

weeklyTimeEntryStoreContract(
  "InMemoryWeeklyTimeEntryStore",
  (seed) => new InMemoryWeeklyTimeEntryStore(seed),
);
