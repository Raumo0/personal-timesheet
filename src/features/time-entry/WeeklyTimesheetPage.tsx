import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import type {
  CatalogLifecycle,
  LifecyclePlan,
  LifecycleRequest,
} from "../catalog-lifecycle/catalog-lifecycle";

import { TimeEntryCell } from "./TimeEntryCell";
import { WorkItemSelector } from "./WorkItemSelector";
import { useWeeklyAutosave } from "./use-weekly-autosave";
import {
  calculateDayTotals,
  calculateGrandTotal,
  calculateRowTotal,
  addWeeks,
  currentWeek,
  formatDuration,
  rowKey,
  type LocalDate,
  type WorkReference,
} from "./weekly-time-entry";
import type {
  SelectableWork,
  WeeklyTimeEntryRow,
  WeeklyTimeEntryStore,
} from "./weekly-time-entry-store";
import type {
  TimeEntryLeaveRequest,
  TimeEntryNavigationCoordinator,
} from "./time-entry-navigation-guard";

export interface WeeklyTimesheetPageProps {
  readonly store: WeeklyTimeEntryStore;
  readonly now?: Date;
  readonly navigationCoordinator?: TimeEntryNavigationCoordinator;
  readonly lifecycle?: CatalogLifecycle;
}

type LoadState = "loading" | "loaded" | "error";

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTH_NAMES = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function dateParts(value: LocalDate) {
  const [year, month, day] = value.split("-").map(Number);
  return { year, month, day };
}

function formatDay(value: LocalDate, index: number): string {
  const { month, day } = dateParts(value);
  return `${DAY_NAMES[index]} ${MONTH_NAMES[month - 1]} ${day}`;
}

function formatWeekRange(dates: readonly LocalDate[]): string {
  const first = dateParts(dates[0]);
  const last = dateParts(dates[dates.length - 1]);
  const firstMonth = MONTH_NAMES[first.month - 1];
  const lastMonth = MONTH_NAMES[last.month - 1];

  if (first.year === last.year && first.month === last.month) {
    return `${firstMonth} ${first.day}–${last.day}, ${last.year}`;
  }
  if (first.year === last.year) {
    return `${firstMonth} ${first.day}–${lastMonth} ${last.day}, ${last.year}`;
  }
  return `${firstMonth} ${first.day}, ${first.year}–${lastMonth} ${last.day}, ${last.year}`;
}

function rowLabel(row: WeeklyTimeEntryRow): string {
  return row.task
    ? `${row.client.name} · ${row.project.name} · ${row.task.name}`
    : `${row.client.name} · ${row.project.name}`;
}

function focusKey(reference: WorkReference, date: LocalDate): string {
  return `${rowKey(reference)}|${date}`;
}

function findTransientRow(
  reference: WorkReference,
  work: readonly SelectableWork[],
): WeeklyTimeEntryRow | undefined {
  for (const { client, projects } of work) {
    for (const { project, tasks } of projects) {
      if (reference.kind === "project" && reference.projectId === project.id) {
        return {
          reference,
          client: { ...client, archivedAt: null },
          project: { ...project, archivedAt: null },
          active: true,
          minutesByDate: {},
        };
      }
      if (reference.kind === "task") {
        const task = tasks.find((candidate) => candidate.id === reference.taskId);
        if (task) {
          return {
            reference,
            client: { ...client, archivedAt: null },
            project: { ...project, archivedAt: null },
            task: { ...task, archivedAt: null },
            active: true,
            minutesByDate: {},
          };
        }
      }
    }
  }
  return undefined;
}

export function WeeklyTimesheetPage({
  store,
  now = new Date(),
  navigationCoordinator,
  lifecycle,
}: WeeklyTimesheetPageProps) {
  const [localCurrentWeek] = useState(() => currentWeek(now));
  const [week, setWeek] = useState(localCurrentWeek);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [rows, setRows] = useState<readonly WeeklyTimeEntryRow[]>([]);
  const [work, setWork] = useState<readonly SelectableWork[]>([]);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [focusRequests, setFocusRequests] = useState<Record<string, number>>({});
  const [leaveRequest, setLeaveRequest] = useState<{
    readonly source: "route" | "native-close";
    readonly request: TimeEntryLeaveRequest;
  }>();
  const [restorePlan, setRestorePlan] = useState<LifecyclePlan>();
  const [retryRequest, setRetryRequest] = useState<LifecycleRequest>();
  const [retryRefresh, setRetryRefresh] = useState(false);
  const [restoreError, setRestoreError] = useState<string>();
  const restoreInitiator = useRef<HTMLButtonElement | null>(null);
  const autosave = useWeeklyAutosave(store, week.dates);
  const requestCellFocus = useCallback(
    (reference: WorkReference, date: LocalDate) => {
      const key = focusKey(reference, date);
      setFocusRequests((requests) => ({
        ...requests,
        [key]: (requests[key] ?? 0) + 1,
      }));
    },
    [],
  );

  useEffect(() => {
    let active = true;
    setLoadState("loading");

    void Promise.all([store.loadWeek(week), store.listSelectableWork()])
      .then(([snapshot, selectableWork]) => {
        if (!active) return;
        autosave.initialize(snapshot.rows);
        setRows(snapshot.rows);
        setWork(selectableWork);
        setLoadState("loaded");
      })
      .catch(() => {
        if (active) setLoadState("error");
      });

    return () => {
      active = false;
    };
  }, [autosave.initialize, loadAttempt, store, week]);

  useEffect(() => {
    navigationCoordinator?.updateGuardState(autosave.navigationGuard);
  }, [autosave.navigationGuard, navigationCoordinator]);

  useEffect(() => {
    if (!navigationCoordinator) return;
    const handleLeaveRequest = (
      source: "route" | "native-close",
      request: TimeEntryLeaveRequest,
    ) => {
      void autosave.prepareNavigation().then((result) => {
        if (result.ok) {
          navigationCoordinator.updateGuardState({
            shouldBlockNativeClose: false,
            shouldBlockRoute: false,
          });
          request.continueNavigation();
          return;
        }
        requestCellFocus(result.blocking.reference, result.blocking.date);
        setLeaveRequest({ source, request });
      });
    };
    const unregisterRoute = navigationCoordinator.registerRouteRequest(
      (request) => handleLeaveRequest("route", request),
    );
    const unregisterClose = navigationCoordinator.registerNativeCloseRequest(
      (request) => handleLeaveRequest("native-close", request),
    );
    return () => {
      unregisterRoute();
      unregisterClose();
    };
  }, [autosave.prepareNavigation, navigationCoordinator, requestCellFocus]);

  const existingRowKeys = useMemo(
    () => new Set(rows.map((row) => rowKey(row.reference))),
    [rows],
  );
  const minuteRows = useMemo(
    () =>
      rows.map((row) =>
        week.dates.map(
          (date) => {
            const cell = autosave.getCell(row.reference, date);
            return cell ? cell.previewMinutes : row.minutesByDate[date];
          },
        ),
      ),
    [autosave.getCell, rows, week.dates],
  );
  const dayTotals = useMemo(() => calculateDayTotals(minuteRows), [minuteRows]);
  const grandTotal = useMemo(
    () => calculateGrandTotal(minuteRows),
    [minuteRows],
  );
  const hasInvalidDuration = useMemo(
    () =>
      rows.some((row) =>
        week.dates.some(
          (date) => Boolean(autosave.getCell(row.reference, date)?.validationError),
        ),
      ),
    [autosave.getCell, rows, week.dates],
  );

  const addRow = useCallback(
    (reference: WorkReference) => {
      const row = findTransientRow(reference, work);
      if (row) {
        autosave.addRow(row);
        setRows((currentRows) => [...currentRows, row]);
      }
    },
    [autosave, work],
  );

  const requestRowFocus = useCallback((key: string) => {
    const firstDateKey = `${key}|${week.dates[0]}`;
    setFocusRequests((requests) => ({
      ...requests,
      [firstDateKey]: (requests[firstDateKey] ?? 0) + 1,
    }));
  }, [week.dates]);

  const restoreFocus = useCallback(() => {
    queueMicrotask(() => restoreInitiator.current?.focus());
  }, []);

  const requestRestore = useCallback(
    async (row: WeeklyTimeEntryRow, initiator?: HTMLButtonElement) => {
      if (!lifecycle) return;
      if (initiator) restoreInitiator.current = initiator;
      const request: LifecycleRequest = {
        operation: "restore",
        target:
          row.reference.kind === "project"
            ? { kind: "project", id: row.reference.projectId }
            : { kind: "task", id: row.reference.taskId },
      };
      setRestoreError(undefined);
      setRetryRefresh(false);
      try {
        setRestorePlan(await lifecycle.preview(request));
        setRetryRequest(undefined);
      } catch (error) {
        setRestoreError(
          error instanceof Error
            ? error.message
            : "The restore could not be prepared",
        );
        setRetryRequest(request);
        restoreFocus();
      }
    },
    [lifecycle, restoreFocus],
  );

  const reloadRestoredData = useCallback(async () => {
    try {
      const [snapshot, selectableWork] = await Promise.all([
        store.loadWeek(week),
        store.listSelectableWork(),
      ]);
      autosave.initialize(snapshot.rows);
      setRows(snapshot.rows);
      setWork(selectableWork);
      setRestoreError(undefined);
      setRetryRequest(undefined);
      setRetryRefresh(false);
    } catch (error) {
      setRestoreError(
        error instanceof Error ? error.message : "The restored work could not be reloaded",
      );
      setRetryRequest(undefined);
      setRetryRefresh(true);
      restoreFocus();
    }
  }, [autosave.initialize, restoreFocus, store, week]);

  const confirmRestore = useCallback(async () => {
    if (!lifecycle || !restorePlan) return;
    const request = {
      operation: restorePlan.operation,
      target: restorePlan.target,
    } satisfies LifecycleRequest;
    setRestoreError(undefined);
    try {
      await lifecycle.apply(restorePlan);
      setRestorePlan(undefined);
      setRetryRequest(undefined);
      await reloadRestoredData();
    } catch (error) {
      setRestoreError(
        error instanceof Error ? error.message : "The work item was not restored",
      );
      setRetryRequest(request);
      setRetryRefresh(false);
      setRestorePlan(undefined);
      restoreFocus();
    }
  }, [lifecycle, reloadRestoredData, restoreFocus, restorePlan]);

  const retryRestore = useCallback(async () => {
    if (retryRefresh) {
      await reloadRestoredData();
      return;
    }
    if (!retryRequest) return;
    const row = rows.find((candidate) => {
      if (retryRequest.target.kind === "project") {
        return candidate.reference.kind === "project" &&
          candidate.reference.projectId === retryRequest.target.id;
      }
      return candidate.reference.kind === "task" &&
        candidate.reference.taskId === retryRequest.target.id;
    });
    if (row) await requestRestore(row);
  }, [reloadRestoredData, requestRestore, retryRefresh, retryRequest, rows]);

  const navigateToWeek = useCallback(
    async (target: typeof week) => {
      const result = await autosave.prepareNavigation();
      if (!result.ok) {
        requestCellFocus(result.blocking.reference, result.blocking.date);
        return;
      }
      setWeek(target);
    },
    [autosave, requestCellFocus],
  );

  return (
    <section className="grid min-w-0 gap-4" aria-labelledby="timesheet-title">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-muted-foreground">Week</p>
          <h1 className="text-xl font-semibold tracking-tight" id="timesheet-title">
            Timesheet
          </h1>
          <p className="mt-0.5 text-sm tabular-nums text-muted-foreground">
            {formatWeekRange(week.dates)}
          </p>
          <div className="mt-2 flex items-center gap-1">
            <Button
              onClick={() => void navigateToWeek(addWeeks(week, -1))}
              size="sm"
              variant="outline"
            >
              Previous
            </Button>
            <Button
              onClick={() => void navigateToWeek(localCurrentWeek)}
              size="sm"
              variant="ghost"
            >
              Current
            </Button>
            <Button
              onClick={() => void navigateToWeek(addWeeks(week, 1))}
              size="sm"
              variant="outline"
            >
              Next
            </Button>
          </div>
        </div>
        {loadState === "loaded" ? (
          <div className="flex items-center gap-3">
            <div
              aria-live="polite"
              className="text-xs font-medium text-muted-foreground"
              role="status"
            >
              {autosave.status === "Not saved · Retry" ? (
                <Button
                  onClick={autosave.retryFailed}
                  size="sm"
                  variant="destructive"
                >
                  <RotateCcw aria-hidden="true" />
                  Not saved · Retry
                </Button>
              ) : hasInvalidDuration ? (
                "Invalid duration · Use H:MM, for example 1:30"
              ) : (
                autosave.status
              )}
            </div>
            <WorkItemSelector
              existingRowKeys={existingRowKeys}
              onRequestFocus={requestRowFocus}
              onSelect={addRow}
              work={work}
            />
          </div>
        ) : null}
      </header>

      {restoreError ? (
        <div
          className="flex items-center justify-between gap-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
          role="alert"
        >
          <span>{restoreError}</span>
          {retryRequest || retryRefresh ? (
            <Button onClick={() => void retryRestore()} size="sm" variant="outline">
              <RotateCcw aria-hidden="true" />
              Retry
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="overflow-hidden rounded-xl border bg-card shadow-xs">
        {loadState === "loading" ? (
          <div
            className="flex min-h-64 items-center justify-center text-sm text-muted-foreground"
            role="status"
          >
            Loading timesheet…
          </div>
        ) : null}

        {loadState === "error" ? (
          <div
            className="flex min-h-64 flex-col items-center justify-center p-8 text-center"
            role="alert"
          >
            <p className="text-sm font-medium">Timesheet could not be loaded</p>
            <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
              Your local time was not changed. Try reading it again.
            </p>
            <Button
              className="mt-4"
              onClick={() => setLoadAttempt((attempt) => attempt + 1)}
              variant="outline"
            >
              <RotateCcw aria-hidden="true" />
              Retry
            </Button>
          </div>
        ) : null}

        {loadState === "loaded" ? (
          <div
            className="overflow-x-auto [&_[data-slot=table-container]]:overflow-visible"
            data-testid="weekly-grid-scroll"
          >
            <Table className="min-w-[52rem] table-fixed">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="sticky left-0 z-10 w-40 bg-card px-4">
                    Work
                  </TableHead>
                  {week.dates.map((date, index) => {
                    const label = formatDay(date, index).split(" ");
                    return (
                      <TableHead className="w-20 text-center" key={date}>
                        <span className="block text-xs text-muted-foreground">
                          {label[0]}
                        </span>
                        <span className="block tabular-nums">
                          {label.slice(1).join(" ")}
                        </span>
                      </TableHead>
                    );
                  })}
                  <TableHead className="sticky right-0 z-10 w-20 bg-muted/50 pr-4 text-right">
                    Total
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.length === 0 ? (
                  <TableRow>
                    <TableCell
                      className="h-32 text-center text-sm text-muted-foreground"
                      colSpan={9}
                    >
                      No rows this week
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map((row, rowIndex) => {
                    const key = rowKey(row.reference);
                    const label = rowLabel(row);
                    const minutes = minuteRows[rowIndex];
                    return (
                      <TableRow
                        aria-label={`${label} · ${
                          row.reference.kind === "project" ? "Project" : "Task"
                        }`}
                        className="odd:bg-muted/20 even:bg-muted/5"
                        key={key}
                      >
                        <TableCell className="sticky left-0 z-10 bg-inherit px-4 py-2">
                          <span className="block truncate font-medium">
                            {row.task?.name ?? row.project.name}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {row.client.name} · {row.project.name}
                          </span>
                          <span className="sr-only">
                            {row.reference.kind === "project" ? "Project" : "Task"}
                          </span>
                          {!row.active ? (
                            <div className="mt-1 flex items-center gap-2">
                              <span className="text-xs font-medium text-muted-foreground">
                                No longer active
                              </span>
                              {lifecycle ? (
                                <Button
                                  aria-label={`Restore ${label} to edit`}
                                  onClick={(event) =>
                                    void requestRestore(row, event.currentTarget)
                                  }
                                  size="sm"
                                  variant="outline"
                                >
                                  Restore to edit
                                </Button>
                              ) : null}
                            </div>
                          ) : null}
                        </TableCell>
                        {week.dates.map((date, dayIndex) => (
                          <TableCell
                            className="px-1.5 py-2"
                            key={date}
                            onFocusCapture={() =>
                              autosave.setActiveCell(row.reference, date)
                            }
                          >
                            {(() => {
                              const cell = autosave.getCell(row.reference, date);
                              return (
                                <TimeEntryCell
                                  focusRequest={
                                    focusRequests[
                                      focusKey(row.reference, date)
                                    ]
                                  }
                                  label={`${label} · ${formatDay(date, dayIndex)}`}
                                  readOnly={!row.active}
                                  onChange={(value) =>
                                    autosave.change(row.reference, date, value)
                                  }
                                  onCommit={() =>
                                    autosave.commit(row.reference, date)
                                  }
                                  onEscape={() =>
                                    autosave.escape(row.reference, date)
                                  }
                                  saveError={cell?.saveError}
                                  validationError={cell?.validationError}
                                  value={
                                    cell
                                      ? cell.draft
                                      : minutes[dayIndex] === undefined
                                      ? ""
                                      : formatDuration(minutes[dayIndex])
                                  }
                                />
                              );
                            })()}
                          </TableCell>
                        ))}
                        <TableCell className="sticky right-0 z-10 bg-muted/50 pr-4 text-right font-medium tabular-nums">
                          {formatDuration(calculateRowTotal(minutes))}
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
              <TableFooter>
                <TableRow className="bg-muted/50 hover:bg-muted/50">
                  <TableCell className="sticky left-0 z-10 bg-muted/50 px-4">
                    Daily totals
                  </TableCell>
                  {dayTotals.map((minutes, index) => (
                    <TableCell
                      className="text-center font-mono tabular-nums"
                      key={week.dates[index]}
                    >
                      {formatDuration(minutes)}
                    </TableCell>
                  ))}
                  <TableCell className="sticky right-0 z-10 bg-muted/50 pr-4 text-right font-mono font-semibold tabular-nums">
                    {formatDuration(grandTotal)}
                  </TableCell>
                </TableRow>
              </TableFooter>
            </Table>
          </div>
        ) : null}
      </div>

      <AlertDialog
        onOpenChange={(open) => {
          if (!open) {
            setRestorePlan(undefined);
            restoreFocus();
          }
        }}
        open={Boolean(restorePlan)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Restore to edit?</AlertDialogTitle>
            <AlertDialogDescription>
              {restorePlan?.impactDescription}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmRestore()}>
              Restore to edit
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        onOpenChange={(open) => {
          if (!open) autosave.cancelDeletion();
        }}
        open={Boolean(autosave.deletionRequest)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete time entry?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the saved duration from this day. This action can be
              corrected by entering the time again.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={autosave.confirmDeletion}
              variant="destructive"
            >
              Delete entry
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        onOpenChange={(open) => {
          if (!open) setLeaveRequest(undefined);
        }}
        open={Boolean(leaveRequest)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {leaveRequest?.source === "native-close"
                ? "Close Personal Timesheet?"
                : "Leave Timesheet?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              Unsaved changes will be lost if you continue.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => leaveRequest?.request.cancelNavigation?.()}
            >
              Stay
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                const request = leaveRequest?.request;
                autosave.discardChanges();
                navigationCoordinator?.updateGuardState({
                  shouldBlockNativeClose: false,
                  shouldBlockRoute: false,
                });
                setLeaveRequest(undefined);
                request?.continueNavigation();
              }}
              variant="destructive"
            >
              Discard changes
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
