import { describe, expect, test } from "vitest";

import { runBackupServiceContract } from "./backup-service.contract";
import { InMemoryBackupService } from "./in-memory-backup-service";

const completedBackup = {
  status: "completed" as const,
  path: "/Backups/timesheet.ptimesheet-backup",
};
const readyRestore = {
  status: "ready" as const,
  preview: {
    filename: "timesheet.ptimesheet-backup",
    dataVersion: 1,
    clientCount: 3,
  },
};

runBackupServiceContract("in-memory", () => {
  const service = new InMemoryBackupService({
    backupResults: [completedBackup],
    restoreResults: [readyRestore],
  });
  return {
    service,
    expectedBackup: completedBackup,
    expectedRestore: readyRestore,
    events: service.events,
  };
});

describe("InMemoryBackupService", () => {
  test("can expose a recoverable commit failure followed by success", async () => {
    const failure = new Error("replacement failed");
    const service = new InMemoryBackupService({
      commitFailures: [failure, undefined],
    });

    await expect(service.commitRestore()).rejects.toBe(failure);
    await expect(service.commitRestore()).resolves.toBeUndefined();
  });
});
