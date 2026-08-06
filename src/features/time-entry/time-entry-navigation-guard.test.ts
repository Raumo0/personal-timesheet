import { expect, test } from "vitest";

import { deriveTimeEntryNavigationGuard } from "./time-entry-navigation-guard";

test("saved data and empty transient rows do not guard route or native close", () => {
  expect(
    deriveTimeEntryNavigationGuard({
      hasDirtyDraft: false,
      hasFailedWrite: false,
      hasPendingWrite: false,
    }),
  ).toEqual({ shouldBlockNativeClose: false, shouldBlockRoute: false });
});

test.each([
  { hasDirtyDraft: true, hasPendingWrite: false, hasFailedWrite: false },
  { hasDirtyDraft: false, hasPendingWrite: true, hasFailedWrite: false },
  { hasDirtyDraft: false, hasPendingWrite: false, hasFailedWrite: true },
])("guards both leave paths for unsaved state %#", (state) => {
  expect(deriveTimeEntryNavigationGuard(state)).toEqual({
    shouldBlockNativeClose: true,
    shouldBlockRoute: true,
  });
});
