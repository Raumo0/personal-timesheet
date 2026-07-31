import { useState } from "react";
import { DatabaseBackup, HardDriveDownload, RotateCcw, ShieldAlert } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

import type { BackupPreview, BackupService } from "./backup-service";

type Feedback = { tone: "success" | "error"; message: string } | null;
type Operation = "backup" | "restore" | null;

export function SettingsDataPage({ service }: { service: BackupService }) {
  const [operation, setOperation] = useState<Operation>(null);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [preview, setPreview] = useState<BackupPreview | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  const handleBackup = async () => {
    setOperation("backup");
    setFeedback(null);
    try {
      const result = await service.createBackup();
      if (result.status === "completed") {
        setFeedback({
          tone: "success",
          message: `Backup saved to ${result.path}`,
        });
      }
    } catch (error) {
      setFeedback({ tone: "error", message: errorMessage(error) });
    } finally {
      setOperation(null);
    }
  };

  const handleRestoreSelection = async () => {
    setOperation("restore");
    setFeedback(null);
    setRestoreError(null);
    try {
      const result = await service.selectRestore();
      if (result.status === "ready") setPreview(result.preview);
    } catch (error) {
      setFeedback({
        tone: "error",
        message: `${errorMessage(error)} Your current data was not changed.`,
      });
    } finally {
      setOperation(null);
    }
  };

  const handleCancelRestore = async () => {
    setPreview(null);
    setRestoreError(null);
    try {
      await service.cancelRestore();
    } catch (error) {
      setFeedback({ tone: "error", message: errorMessage(error) });
    }
  };

  const handleCommitRestore = async () => {
    setOperation("restore");
    setFeedback(null);
    try {
      await service.commitRestore();
      setPreview(null);
      setRestoreError(null);
      setFeedback({
        tone: "success",
        message: "Restore completed. Personal Timesheet is restarting.",
      });
    } catch (error) {
      setRestoreError(
        `${errorMessage(error)} Your current data was preserved.`,
      );
    } finally {
      setOperation(null);
    }
  };

  const isBusy = operation !== null;

  return (
    <div className="flex min-h-full flex-col">
      <header className="max-w-3xl">
        <h1 className="text-balance text-2xl font-semibold tracking-tight text-foreground">
          Settings
        </h1>
        <p className="mt-2 text-pretty text-sm leading-6 text-muted-foreground">
          Protect the local workspace and control how its data is restored.
        </p>
      </header>

      <section
        aria-labelledby="data-protection-title"
        className="mt-6 max-w-3xl overflow-hidden rounded-xl border bg-card shadow-xs"
      >
        <div className="flex items-start gap-3 border-b p-5">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <DatabaseBackup aria-hidden="true" className="size-5" />
          </div>
          <div>
            <h2
              className="text-base font-semibold tracking-tight"
              id="data-protection-title"
            >
              Data protection
            </h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              Back up or replace the complete local Personal Timesheet workspace.
            </p>
          </div>
        </div>

        <div className="divide-y">
          <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="max-w-xl">
              <h3 className="text-sm font-medium">Create a local backup</h3>
              <p className="mt-1 text-sm leading-5 text-muted-foreground">
                Save clients and all future workspace records as one consistent file.
              </p>
            </div>
            <Button
              disabled={isBusy}
              onClick={() => void handleBackup()}
              variant="default"
            >
              <HardDriveDownload aria-hidden="true" />
              {operation === "backup" ? "Backing up…" : "Back up data"}
            </Button>
          </div>

          <div className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="max-w-xl">
              <h3 className="text-sm font-medium">Restore the workspace</h3>
              <p className="mt-1 text-sm leading-5 text-muted-foreground">
                Validate a backup before replacing every current local record.
              </p>
            </div>
            <Button
              disabled={isBusy}
              onClick={() => void handleRestoreSelection()}
              variant="outline"
            >
              <RotateCcw aria-hidden="true" />
              {operation === "restore" && !preview
                ? "Checking…"
                : "Restore backup"}
            </Button>
          </div>
        </div>

        <div className="flex gap-3 border-t bg-muted/35 p-4 text-sm text-muted-foreground">
          <ShieldAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <p className="leading-5">
            Backup files are not encrypted. Store them somewhere private and secure.
          </p>
        </div>
      </section>

      {feedback && (
        <div
          className={
            feedback.tone === "error"
              ? "mt-4 max-w-3xl break-words rounded-lg border border-destructive/25 bg-destructive/10 px-4 py-3 text-sm text-destructive"
              : "mt-4 max-w-3xl break-words rounded-lg border border-primary/20 bg-primary/10 px-4 py-3 text-sm text-foreground"
          }
          role={feedback.tone === "error" ? "alert" : "status"}
        >
          {feedback.message}
        </div>
      )}

      <AlertDialog open={preview !== null}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogMedia className="bg-destructive/10 text-destructive">
              <RotateCcw aria-hidden="true" />
            </AlertDialogMedia>
            <AlertDialogTitle>Replace all local data?</AlertDialogTitle>
            <AlertDialogDescription>
              Restore <strong className="break-all">{preview?.filename}</strong>.
              This will replace all current local data and restart Personal
              Timesheet.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {preview && (
            <p className="rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">
              Data version {preview.dataVersion} · {preview.clientCount} clients
            </p>
          )}
          {restoreError && (
            <p
              className="rounded-lg border border-destructive/25 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              role="alert"
            >
              {restoreError}
            </p>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel
              disabled={isBusy}
              onClick={() => void handleCancelRestore()}
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={isBusy}
              onClick={() => void handleCommitRestore()}
              variant="destructive"
            >
              {operation === "restore"
                ? "Restoring…"
                : restoreError
                  ? "Retry restore"
                  : "Restore and restart"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Personal Timesheet could not complete the data operation.";
}
