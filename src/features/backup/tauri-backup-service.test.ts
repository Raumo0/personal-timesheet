import { describe, expect, test, vi } from "vitest";

import {
  BackupServiceError,
  TauriBackupService,
  type TauriBackupDependencies,
} from "./tauri-backup-service";
import { runBackupServiceContract } from "./backup-service.contract";

function createDependencies(
  overrides: Partial<TauriBackupDependencies> = {},
): TauriBackupDependencies {
  return {
    saveDialog: vi.fn().mockResolvedValue(null),
    openDialog: vi.fn().mockResolvedValue(null),
    invoke: vi.fn().mockResolvedValue(undefined),
    checkpointAndClose: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

describe("TauriBackupService", () => {
  test("returns cancellation without creating a backup when save is dismissed", async () => {
    const dependencies = createDependencies();
    const service = new TauriBackupService(dependencies);

    await expect(service.createBackup()).resolves.toEqual({
      status: "cancelled",
    });
    expect(dependencies.invoke).not.toHaveBeenCalled();
  });

  test("creates a backup at the selected product-specific filename", async () => {
    const dependencies = createDependencies({
      saveDialog: vi.fn().mockResolvedValue("/Documents/july-backup"),
      invoke: vi.fn().mockResolvedValue({
        path: "/Documents/july-backup.ptimesheet-backup",
      }),
    });
    const service = new TauriBackupService(dependencies);

    await expect(service.createBackup()).resolves.toEqual({
      status: "completed",
      path: "/Documents/july-backup.ptimesheet-backup",
    });
    expect(dependencies.invoke).toHaveBeenCalledWith("create_data_backup", {
      destination: "/Documents/july-backup.ptimesheet-backup",
    });
  });

  test("returns cancellation without staging when open is dismissed", async () => {
    const dependencies = createDependencies();
    const service = new TauriBackupService(dependencies);

    await expect(service.selectRestore()).resolves.toEqual({
      status: "cancelled",
    });
    expect(dependencies.invoke).not.toHaveBeenCalled();
  });

  test("stages the selected backup and returns its safe preview", async () => {
    const dependencies = createDependencies({
      openDialog: vi
        .fn()
        .mockResolvedValue("/Documents/june.ptimesheet-backup"),
      invoke: vi.fn().mockResolvedValue({
        filename: "june.ptimesheet-backup",
        dataVersion: 1,
        clientCount: 4,
      }),
    });
    const service = new TauriBackupService(dependencies);

    await expect(service.selectRestore()).resolves.toEqual({
      status: "ready",
      preview: {
        filename: "june.ptimesheet-backup",
        dataVersion: 1,
        clientCount: 4,
      },
    });
    expect(dependencies.invoke).toHaveBeenCalledWith("stage_restore_backup", {
      source: "/Documents/june.ptimesheet-backup",
    });
  });

  test("cancels the app-owned staged restore", async () => {
    const dependencies = createDependencies();
    const service = new TauriBackupService(dependencies);

    await service.cancelRestore();

    expect(dependencies.invoke).toHaveBeenCalledWith("cancel_staged_restore");
  });

  test("checkpoints and closes SQLite before committing the restore", async () => {
    const events: string[] = [];
    const dependencies = createDependencies({
      checkpointAndClose: vi.fn().mockImplementation(async () => {
        events.push("checkpoint-and-close");
      }),
      invoke: vi.fn().mockImplementation(async (command: string) => {
        events.push(command);
      }),
    });
    const service = new TauriBackupService(dependencies);

    await service.commitRestore();

    expect(events).toEqual(["checkpoint-and-close", "commit_staged_restore"]);
  });

  test.each([
    {
      nativeMessage:
        "backup data version 4 is newer than supported version 3",
      code: "unsupported-version",
      message: "This backup requires a newer version of Personal Timesheet.",
    },
    {
      nativeMessage: "backup integrity check failed: file is not a database",
      code: "invalid-backup",
      message: "This file is damaged or is not a Personal Timesheet backup.",
    },
    {
      nativeMessage: "destination unavailable: disk full",
      code: "persistence",
      message:
        "Personal Timesheet could not complete the data operation. Try again or choose another file location.",
    },
  ] as const)("translates $code failures for the UI", async (scenario) => {
    const dependencies = createDependencies({
      openDialog: vi.fn().mockResolvedValue("/Documents/selected.backup"),
      invoke: vi.fn().mockRejectedValue(scenario.nativeMessage),
    });
    const service = new TauriBackupService(dependencies);

    const error = await service.selectRestore().catch((reason) => reason);

    expect(error).toBeInstanceOf(BackupServiceError);
    expect(error).toMatchObject({
      code: scenario.code,
      message: scenario.message,
    });
  });
});

runBackupServiceContract("Tauri", () => {
  const events: string[] = [];
  const expectedBackup = {
    status: "completed" as const,
    path: "/Documents/contract.ptimesheet-backup",
  };
  const expectedRestore = {
    status: "ready" as const,
    preview: {
      filename: "contract.ptimesheet-backup",
      dataVersion: 1,
      clientCount: 2,
    },
  };
  const dependencies = createDependencies({
    saveDialog: vi.fn().mockResolvedValue(expectedBackup.path),
    openDialog: vi.fn().mockResolvedValue(expectedBackup.path),
    invoke: vi.fn().mockImplementation(async (command: string) => {
      if (command === "create_data_backup") return { path: expectedBackup.path };
      if (command === "stage_restore_backup") return expectedRestore.preview;
      if (command === "cancel_staged_restore") events.push("cancel");
      if (command === "commit_staged_restore") events.push("commit");
    }),
  });

  return {
    service: new TauriBackupService(dependencies),
    expectedBackup,
    expectedRestore,
    events,
  };
});
