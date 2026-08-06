import { useCallback, useMemo, useRef, useState } from "react";

import {
  formatDuration,
  parseDuration,
  rowKey,
  validateDailyTotal,
  type LocalDate,
  type WorkReference,
} from "./weekly-time-entry";
import type {
  WeeklyTimeEntryRow,
  WeeklyTimeEntryStore,
} from "./weekly-time-entry-store";
import { deriveTimeEntryNavigationGuard } from "./time-entry-navigation-guard";

type CellPhase = "clean" | "dirty" | "pending" | "failed";

interface AutosaveCell {
  readonly reference: WorkReference;
  readonly date: LocalDate;
  readonly savedMinutes?: number;
  readonly draft: string;
  readonly previewMinutes?: number;
  readonly validationError?: string;
  readonly saveError?: string;
  readonly phase: CellPhase;
  readonly failedOperation?: "upsert" | "delete";
  readonly revision: number;
}

export interface DeletionRequest {
  readonly reference: WorkReference;
  readonly date: LocalDate;
}

export type WeeklySaveStatus =
  | "No time saved"
  | "Unsaved changes"
  | "Saving…"
  | "Saved locally"
  | "Not saved · Retry";

const SAVE_ERROR = "Time entry could not be saved locally.";

function cellKey(reference: WorkReference, date: LocalDate): string {
  return `${rowKey(reference)}|${date}`;
}

function savedDraft(minutes: number | undefined): string {
  return minutes === undefined ? "" : formatDuration(minutes);
}

function cellsForRows(
  rows: readonly WeeklyTimeEntryRow[],
  dates: readonly LocalDate[],
): Record<string, AutosaveCell> {
  const cells: Record<string, AutosaveCell> = {};
  for (const row of rows) {
    for (const date of dates) {
      const savedMinutes = row.minutesByDate[date];
      cells[cellKey(row.reference, date)] = {
        reference: row.reference,
        date,
        savedMinutes,
        draft: savedDraft(savedMinutes),
        previewMinutes: savedMinutes,
        phase: "clean",
        revision: 0,
      };
    }
  }
  return cells;
}

export function useWeeklyAutosave(
  store: WeeklyTimeEntryStore,
  dates: readonly LocalDate[],
) {
  const [cells, setCells] = useState<Record<string, AutosaveCell>>({});
  const [deletionRequest, setDeletionRequest] =
    useState<DeletionRequest>();
  const cellsRef = useRef(cells);
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const activeCellKeyRef = useRef<string | undefined>(undefined);
  const failedKeysRef = useRef(new Set<string>());

  const updateCells = useCallback(
    (
      update: (
        current: Record<string, AutosaveCell>,
      ) => Record<string, AutosaveCell>,
    ) => {
      setCells((current) => {
        const next = update(current);
        cellsRef.current = next;
        return next;
      });
    },
    [],
  );

  const initialize = useCallback(
    (rows: readonly WeeklyTimeEntryRow[]) => {
      const next = cellsForRows(rows, dates);
      cellsRef.current = next;
      setCells(next);
      setDeletionRequest(undefined);
      queueRef.current = Promise.resolve();
      failedKeysRef.current.clear();
    },
    [dates],
  );

  const addRow = useCallback(
    (row: WeeklyTimeEntryRow) => {
      updateCells((current) => ({
        ...current,
        ...cellsForRows([row], dates),
      }));
    },
    [dates, updateCells],
  );

  const change = useCallback(
    (reference: WorkReference, date: LocalDate, draft: string) => {
      const key = cellKey(reference, date);
      failedKeysRef.current.delete(key);
      updateCells((current) => {
        const cell = current[key];
        if (!cell) return current;

        const parsed = draft === "" ? undefined : parseDuration(draft);
        let validationError: string | undefined =
          parsed && !parsed.ok ? parsed.error : undefined;
        let previewMinutes =
          parsed?.ok === true ? parsed.minutes : cell.savedMinutes;

        if (parsed?.ok) {
          const otherMinutes = Object.entries(current)
            .filter(([candidateKey, candidate]) =>
              candidateKey !== key && candidate.date === date,
            )
            .map(([, candidate]) => candidate.previewMinutes);
          const dailyTotal = validateDailyTotal([
            ...otherMinutes,
            parsed.minutes,
          ]);
          if (!dailyTotal.ok) {
            validationError = dailyTotal.error;
            previewMinutes = cell.savedMinutes;
          }
        }

        if (
          cell.savedMinutes !== undefined &&
          (draft === "" || (parsed?.ok && parsed.minutes === 0))
        ) {
          previewMinutes = cell.savedMinutes;
        }

        const clean = draft === savedDraft(cell.savedMinutes);
        return {
          ...current,
          [key]: {
            ...cell,
            draft,
            previewMinutes,
            validationError,
            saveError: undefined,
            failedOperation: undefined,
            phase: clean ? "clean" : "dirty",
            revision: cell.revision + 1,
          },
        };
      });
    },
    [updateCells],
  );

  const enqueue = useCallback(
    (key: string, expectedRevision: number, minutes: number) => {
      failedKeysRef.current.delete(key);
      updateCells((current) => {
        const cell = current[key];
        if (!cell || cell.revision !== expectedRevision) return current;
        return {
          ...current,
          [key]: {
            ...cell,
            phase: "pending",
            saveError: undefined,
            failedOperation: undefined,
          },
        };
      });

      queueRef.current = queueRef.current.then(async () => {
        const queuedCell = cellsRef.current[key];
        if (!queuedCell) return;
        try {
          const saved = await store.upsert({
            date: queuedCell.date,
            reference: queuedCell.reference,
            minutes,
          });
          updateCells((current) => {
            const cell = current[key];
            if (!cell) return current;
            const unchanged = cell.revision === expectedRevision;
            return {
              ...current,
              [key]: {
                ...cell,
                savedMinutes: saved.minutes,
                draft: unchanged ? formatDuration(saved.minutes) : cell.draft,
                previewMinutes: unchanged
                  ? saved.minutes
                  : cell.previewMinutes,
                validationError: unchanged
                  ? undefined
                  : cell.validationError,
                saveError: undefined,
                failedOperation: undefined,
                phase: unchanged ? "clean" : "dirty",
              },
            };
          });
        } catch {
          failedKeysRef.current.add(key);
          updateCells((current) => {
            const cell = current[key];
            if (!cell) return current;
            return {
              ...current,
              [key]: {
                ...cell,
                phase: "failed",
                saveError: SAVE_ERROR,
                failedOperation: "upsert",
              },
            };
          });
        }
      });
    },
    [store, updateCells],
  );

  const commit = useCallback(
    (reference: WorkReference, date: LocalDate) => {
      const key = cellKey(reference, date);
      failedKeysRef.current.delete(key);
      const cell = cellsRef.current[key];
      if (
        !cell ||
        cell.validationError ||
        cell.phase === "pending" ||
        cell.phase === "failed"
      ) {
        return;
      }
      if (cell.draft === savedDraft(cell.savedMinutes)) return;

      const parsed = cell.draft === "" ? undefined : parseDuration(cell.draft);
      if (
        cell.savedMinutes !== undefined &&
        (parsed === undefined || (parsed.ok && parsed.minutes === 0))
      ) {
        setDeletionRequest({ reference, date });
        return;
      }
      if (!parsed?.ok || parsed.minutes === 0) return;
      enqueue(key, cell.revision, parsed.minutes);
    },
    [enqueue],
  );

  const escape = useCallback(
    (reference: WorkReference, date: LocalDate) => {
      const key = cellKey(reference, date);
      updateCells((current) => {
        const cell = current[key];
        if (!cell) return current;
        return {
          ...current,
          [key]: {
            ...cell,
            draft: savedDraft(cell.savedMinutes),
            previewMinutes: cell.savedMinutes,
            validationError: undefined,
            saveError: undefined,
            failedOperation: undefined,
            phase: "clean",
            revision: cell.revision + 1,
          },
        };
      });
    },
    [updateCells],
  );

  const cancelDeletion = useCallback(() => {
    const request = deletionRequest;
    setDeletionRequest(undefined);
    if (request) escape(request.reference, request.date);
  }, [deletionRequest, escape]);

  const enqueueDelete = useCallback(
    (key: string, expectedRevision: number) => {
      failedKeysRef.current.delete(key);
      updateCells((current) => {
        const cell = current[key];
        if (!cell || cell.revision !== expectedRevision) return current;
        return {
          ...current,
          [key]: {
            ...cell,
            phase: "pending",
            saveError: undefined,
            failedOperation: undefined,
          },
        };
      });

      queueRef.current = queueRef.current.then(async () => {
        const queuedCell = cellsRef.current[key];
        if (!queuedCell) return;
        try {
          await store.delete({
            date: queuedCell.date,
            reference: queuedCell.reference,
          });
          updateCells((current) => {
            const cell = current[key];
            if (!cell) return current;
            const unchanged = cell.revision === expectedRevision;
            return {
              ...current,
              [key]: {
                ...cell,
                savedMinutes: undefined,
                draft: unchanged ? "" : cell.draft,
                previewMinutes: unchanged ? undefined : cell.previewMinutes,
                validationError: unchanged
                  ? undefined
                  : cell.validationError,
                saveError: undefined,
                failedOperation: undefined,
                phase: unchanged ? "clean" : "dirty",
              },
            };
          });
        } catch {
          failedKeysRef.current.add(key);
          updateCells((current) => {
            const cell = current[key];
            if (!cell) return current;
            return {
              ...current,
              [key]: {
                ...cell,
                phase: "failed",
                saveError: SAVE_ERROR,
                failedOperation: "delete",
              },
            };
          });
        }
      });
    },
    [store, updateCells],
  );

  const confirmDeletion = useCallback(() => {
    const request = deletionRequest;
    setDeletionRequest(undefined);
    if (!request) return;
    const key = cellKey(request.reference, request.date);
    const cell = cellsRef.current[key];
    if (cell) enqueueDelete(key, cell.revision);
  }, [deletionRequest, enqueueDelete]);

  const retryFailed = useCallback(() => {
    const failedEntry = Object.entries(cellsRef.current).find(
      ([, cell]) => cell.phase === "failed",
    );
    if (!failedEntry) return;
    const [key, cell] = failedEntry;
    if (cell.failedOperation === "delete") {
      enqueueDelete(key, cell.revision);
      return;
    }
    const parsed = parseDuration(cell.draft);
    if (parsed.ok && parsed.minutes > 0) {
      enqueue(key, cell.revision, parsed.minutes);
    }
  }, [enqueue, enqueueDelete]);

  const setActiveCell = useCallback(
    (reference: WorkReference, date: LocalDate) => {
      activeCellKeyRef.current = cellKey(reference, date);
    },
    [],
  );

  const discardChanges = useCallback(() => {
    setDeletionRequest(undefined);
    failedKeysRef.current.clear();
    updateCells((current) =>
      Object.fromEntries(
        Object.entries(current).map(([key, cell]) => [
          key,
          {
            ...cell,
            draft: savedDraft(cell.savedMinutes),
            previewMinutes: cell.savedMinutes,
            validationError: undefined,
            saveError: undefined,
            failedOperation: undefined,
            phase: "clean" as const,
            revision: cell.revision + 1,
          },
        ]),
      ),
    );
  }, [updateCells]);

  const prepareNavigation = useCallback(async () => {
    const activeKey = activeCellKeyRef.current;
    const activeCell = activeKey ? cellsRef.current[activeKey] : undefined;
    if (activeCell?.phase === "dirty" && !activeCell.validationError) {
      commit(activeCell.reference, activeCell.date);
    }

    await queueRef.current;
    const failedKey = failedKeysRef.current.values().next().value as
      | string
      | undefined;
    const blockingCell = failedKey
      ? cellsRef.current[failedKey]
      : Object.values(cellsRef.current).find(
          (cell) => cell.phase === "failed" || cell.phase === "dirty",
        );
    return blockingCell
      ? {
          ok: false as const,
          blocking: {
            reference: blockingCell.reference,
            date: blockingCell.date,
          },
        }
      : { ok: true as const };
  }, [commit]);

  const status = useMemo<WeeklySaveStatus>(() => {
    const values = Object.values(cells);
    if (values.some((cell) => cell.phase === "failed")) {
      return "Not saved · Retry";
    }
    if (values.some((cell) => cell.phase === "pending")) return "Saving…";
    if (values.some((cell) => cell.phase === "dirty")) {
      return "Unsaved changes";
    }
    if (values.some((cell) => cell.savedMinutes !== undefined)) {
      return "Saved locally";
    }
    return "No time saved";
  }, [cells]);

  const navigationGuard = useMemo(() => {
    const values = Object.values(cells);
    return deriveTimeEntryNavigationGuard({
      hasDirtyDraft: values.some((cell) => cell.phase === "dirty"),
      hasFailedWrite: values.some((cell) => cell.phase === "failed"),
      hasPendingWrite: values.some((cell) => cell.phase === "pending"),
    });
  }, [cells]);

  const getCell = useCallback(
    (reference: WorkReference, date: LocalDate) =>
      cells[cellKey(reference, date)],
    [cells],
  );

  return {
    addRow,
    cancelDeletion,
    change,
    commit,
    confirmDeletion,
    deletionRequest,
    discardChanges,
    escape,
    getCell,
    initialize,
    navigationGuard,
    prepareNavigation,
    retryFailed,
    setActiveCell,
    status,
  };
}
