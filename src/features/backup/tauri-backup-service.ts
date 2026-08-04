import { invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";

import { checkpointAndCloseClientDatabase } from "@/infrastructure/sqlite/plugin-sql-adapter";

import {
  BackupServiceError,
  type BackupCreationResult,
  type BackupPreview,
  type BackupService,
  type RestoreSelectionResult,
} from "./backup-service";

const BACKUP_EXTENSION = ".ptimesheet-backup";
const BACKUP_FILTER = {
  name: "Personal Timesheet backup",
  extensions: ["ptimesheet-backup"],
};

type Invoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

export interface TauriBackupDependencies {
  saveDialog: typeof save;
  openDialog: typeof open;
  invoke: Invoke;
  checkpointAndClose: () => Promise<void>;
}

const productionDependencies: TauriBackupDependencies = {
  saveDialog: save,
  openDialog: open,
  invoke,
  checkpointAndClose: checkpointAndCloseClientDatabase,
};

export { BackupServiceError } from "./backup-service";

export class TauriBackupService implements BackupService {
  constructor(
    private readonly dependencies: TauriBackupDependencies =
      productionDependencies,
  ) {}

  async createBackup(): Promise<BackupCreationResult> {
    const selected = await this.dependencies.saveDialog({
      title: "Back up Personal Timesheet data",
      defaultPath: `personal-timesheet-${new Date().toISOString().slice(0, 10)}${BACKUP_EXTENSION}`,
      filters: [BACKUP_FILTER],
      canCreateDirectories: true,
    });
    if (selected === null) return { status: "cancelled" };

    const destination = selected.endsWith(BACKUP_EXTENSION)
      ? selected
      : `${selected}${BACKUP_EXTENSION}`;

    try {
      const receipt = await this.dependencies.invoke<{ path: string }>(
        "create_data_backup",
        { destination },
      );
      return { status: "completed", path: receipt.path };
    } catch (error) {
      throw translateBackupError(error);
    }
  }

  async selectRestore(): Promise<RestoreSelectionResult> {
    const selected = await this.dependencies.openDialog({
      title: "Restore Personal Timesheet backup",
      filters: [BACKUP_FILTER],
      multiple: false,
      directory: false,
      fileAccessMode: "scoped",
    });
    if (selected === null) return { status: "cancelled" };
    if (Array.isArray(selected)) {
      throw new BackupServiceError(
        "persistence",
        "Personal Timesheet could not read the selected backup.",
      );
    }

    try {
      const preview = await this.dependencies.invoke<BackupPreview>(
        "stage_restore_backup",
        { source: selected },
      );
      return { status: "ready", preview };
    } catch (error) {
      throw translateBackupError(error);
    }
  }

  async cancelRestore(): Promise<void> {
    try {
      await this.dependencies.invoke("cancel_staged_restore");
    } catch (error) {
      throw translateBackupError(error);
    }
  }

  async commitRestore(): Promise<void> {
    try {
      await this.dependencies.checkpointAndClose();
      await this.dependencies.invoke("commit_staged_restore");
    } catch (error) {
      throw translateBackupError(error);
    }
  }
}

function translateBackupError(error: unknown): BackupServiceError {
  if (error instanceof BackupServiceError) return error;

  const nativeMessage = error instanceof Error ? error.message : String(error);
  if (nativeMessage.includes("newer than supported")) {
    return new BackupServiceError(
      "unsupported-version",
      "This backup requires a newer version of Personal Timesheet.",
      error,
    );
  }
  if (
    nativeMessage.includes("integrity check failed") ||
    nativeMessage.includes("not a Personal Timesheet backup")
  ) {
    return new BackupServiceError(
      "invalid-backup",
      "This file is damaged or is not a Personal Timesheet backup.",
      error,
    );
  }

  return new BackupServiceError(
    "persistence",
    "Personal Timesheet could not complete the data operation. Try again or choose another file location.",
    error,
  );
}
