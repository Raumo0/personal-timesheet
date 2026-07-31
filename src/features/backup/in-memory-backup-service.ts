import type {
  BackupCreationResult,
  BackupService,
  RestoreSelectionResult,
} from "./backup-service";

type InMemoryBackupServiceOptions = {
  backupResults?: BackupCreationResult[];
  restoreResults?: RestoreSelectionResult[];
  backupFailures?: (Error | undefined)[];
  restoreFailures?: (Error | undefined)[];
  commitFailures?: (Error | undefined)[];
};

export class InMemoryBackupService implements BackupService {
  readonly events: string[] = [];
  private readonly backupResults: BackupCreationResult[];
  private readonly restoreResults: RestoreSelectionResult[];
  private readonly backupFailures: (Error | undefined)[];
  private readonly restoreFailures: (Error | undefined)[];
  private readonly commitFailures: (Error | undefined)[];

  constructor(options: InMemoryBackupServiceOptions = {}) {
    this.backupResults = [...(options.backupResults ?? [])];
    this.restoreResults = [...(options.restoreResults ?? [])];
    this.backupFailures = [...(options.backupFailures ?? [])];
    this.restoreFailures = [...(options.restoreFailures ?? [])];
    this.commitFailures = [...(options.commitFailures ?? [])];
  }

  async createBackup(): Promise<BackupCreationResult> {
    const failure = this.backupFailures.shift();
    if (failure) throw failure;
    return this.backupResults.shift() ?? { status: "cancelled" };
  }

  async selectRestore(): Promise<RestoreSelectionResult> {
    const failure = this.restoreFailures.shift();
    if (failure) throw failure;
    return this.restoreResults.shift() ?? { status: "cancelled" };
  }

  async cancelRestore(): Promise<void> {
    this.events.push("cancel");
  }

  async commitRestore(): Promise<void> {
    this.events.push("commit");
    const failure = this.commitFailures.shift();
    if (failure) throw failure;
  }
}
