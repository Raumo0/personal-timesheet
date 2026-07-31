import { describe, expect, test } from "vitest";

import type {
  BackupCreationResult,
  BackupService,
  RestoreSelectionResult,
} from "./backup-service";

export type BackupServiceContractHarness = {
  service: BackupService;
  expectedBackup: BackupCreationResult;
  expectedRestore: RestoreSelectionResult;
  events: string[];
};

export function runBackupServiceContract(
  implementation: string,
  createHarness: () => BackupServiceContractHarness,
) {
  describe(`${implementation} backup service contract`, () => {
    test("creates a backup with the configured result", async () => {
      const harness = createHarness();
      await expect(harness.service.createBackup()).resolves.toEqual(
        harness.expectedBackup,
      );
    });

    test("selects a restore with the configured result", async () => {
      const harness = createHarness();
      await expect(harness.service.selectRestore()).resolves.toEqual(
        harness.expectedRestore,
      );
    });

    test("supports cancellation and confirmed commit", async () => {
      const harness = createHarness();
      await harness.service.cancelRestore();
      await harness.service.commitRestore();
      expect(harness.events).toEqual(["cancel", "commit"]);
    });
  });
}
