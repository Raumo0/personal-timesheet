import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";

import { BackupServiceError, type BackupService } from "./backup-service";
import { InMemoryBackupService } from "./in-memory-backup-service";
import { SettingsDataPage } from "./SettingsDataPage";

afterEach(cleanup);

const readyRestore = {
  status: "ready" as const,
  preview: {
    filename: "june.ptimesheet-backup",
    dataVersion: 1,
    clientCount: 4,
  },
};

describe("SettingsDataPage", () => {
  test("explains that local backup files are not encrypted", () => {
    render(<SettingsDataPage service={new InMemoryBackupService()} />);

    expect(
      screen.getByRole("heading", { name: "Settings" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/backup files are not encrypted/i)).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Back up data" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Restore backup" }),
    ).toBeEnabled();
  });

  test("reports the completed backup location", async () => {
    const user = userEvent.setup();
    const service = new InMemoryBackupService({
      backupResults: [
        {
          status: "completed",
          path: "/Backups/july.ptimesheet-backup",
        },
      ],
    });
    render(<SettingsDataPage service={service} />);

    await user.click(screen.getByRole("button", { name: "Back up data" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Backup saved to /Backups/july.ptimesheet-backup",
    );
  });

  test("leaves the page unchanged when backup selection is cancelled", async () => {
    const user = userEvent.setup();
    render(<SettingsDataPage service={new InMemoryBackupService()} />);

    await user.click(screen.getByRole("button", { name: "Back up data" }));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Back up data" }),
    ).toBeEnabled();
  });

  test("reports backup failures without hiding the actions", async () => {
    const user = userEvent.setup();
    const service = new InMemoryBackupService({
      backupFailures: [new Error("disk full")],
    });
    render(<SettingsDataPage service={service} />);

    await user.click(screen.getByRole("button", { name: "Back up data" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("disk full");
    expect(
      screen.getByRole("button", { name: "Back up data" }),
    ).toBeEnabled();
  });

  test("previews a compatible restore before replacing current data", async () => {
    const user = userEvent.setup();
    const service = new InMemoryBackupService({
      restoreResults: [readyRestore],
    });
    render(<SettingsDataPage service={service} />);

    await user.click(screen.getByRole("button", { name: "Restore backup" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("june.ptimesheet-backup");
    expect(dialog).toHaveTextContent("4 clients");
    expect(dialog).toHaveTextContent(/replace all current local data/i);
    expect(
      screen.getByRole("button", { name: "Restore and restart" }),
    ).toBeEnabled();
  });

  test("rejects incompatible files without changing current data", async () => {
    const user = userEvent.setup();
    const service = new InMemoryBackupService({
      restoreFailures: [
        new BackupServiceError(
          "unsupported-version",
          "This backup requires a newer version of Personal Timesheet.",
        ),
      ],
    });
    render(<SettingsDataPage service={service} />);

    await user.click(screen.getByRole("button", { name: "Restore backup" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This backup requires a newer version of Personal Timesheet.",
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Your current data was not changed.",
    );
  });

  test("cancels the staged restore from the confirmation", async () => {
    const user = userEvent.setup();
    const service = new InMemoryBackupService({
      restoreResults: [readyRestore],
    });
    render(<SettingsDataPage service={service} />);
    await user.click(screen.getByRole("button", { name: "Restore backup" }));
    await screen.findByRole("alertdialog");

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(service.events).toContain("cancel");
  });

  test("keeps current data preserved and offers retry after commit failure", async () => {
    const user = userEvent.setup();
    const service = new InMemoryBackupService({
      restoreResults: [readyRestore],
      commitFailures: [new Error("replacement failed"), undefined],
    });
    render(<SettingsDataPage service={service} />);
    await user.click(screen.getByRole("button", { name: "Restore backup" }));
    await user.click(
      await screen.findByRole("button", { name: "Restore and restart" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your current data was preserved.",
    );
    expect(
      screen.getByRole("button", { name: "Retry restore" }),
    ).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Retry restore" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Restore completed",
    );
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  test("disables duplicate restore actions while commit is pending", async () => {
    const user = userEvent.setup();
    let finishCommit: (() => void) | undefined;
    const commit = new Promise<void>((resolve) => {
      finishCommit = resolve;
    });
    const service: BackupService = {
      createBackup: async () => ({ status: "cancelled" }),
      selectRestore: async () => readyRestore,
      cancelRestore: async () => undefined,
      commitRestore: () => commit,
    };
    render(<SettingsDataPage service={service} />);
    await user.click(screen.getByRole("button", { name: "Restore backup" }));
    await user.click(
      await screen.findByRole("button", { name: "Restore and restart" }),
    );

    expect(
      await screen.findByRole("button", { name: "Restoring…" }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();

    finishCommit?.();
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Restore completed",
    );
  });
});
