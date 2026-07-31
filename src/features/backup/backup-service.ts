export type BackupPreview = {
  filename: string;
  dataVersion: number;
  clientCount: number;
};

export type BackupCreationResult =
  | { status: "cancelled" }
  | { status: "completed"; path: string };

export type RestoreSelectionResult =
  | { status: "cancelled" }
  | { status: "ready"; preview: BackupPreview };

export type BackupServiceErrorCode =
  | "invalid-backup"
  | "unsupported-version"
  | "persistence";

export class BackupServiceError extends Error {
  constructor(
    readonly code: BackupServiceErrorCode,
    message: string,
    readonly cause?: unknown,
  ) {
    super(message);
    this.name = "BackupServiceError";
  }
}

export interface BackupService {
  createBackup(): Promise<BackupCreationResult>;
  selectRestore(): Promise<RestoreSelectionResult>;
  cancelRestore(): Promise<void>;
  commitRestore(): Promise<void>;
}
