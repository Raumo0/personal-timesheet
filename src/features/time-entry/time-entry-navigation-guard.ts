export interface TimeEntryNavigationSignals {
  readonly hasDirtyDraft: boolean;
  readonly hasPendingWrite: boolean;
  readonly hasFailedWrite: boolean;
}

export interface TimeEntryNavigationGuardState {
  readonly shouldBlockRoute: boolean;
  readonly shouldBlockNativeClose: boolean;
}

export interface TimeEntryLeaveRequest {
  readonly continueNavigation: () => void;
  readonly cancelNavigation?: () => void;
}

export interface TimeEntryNavigationCoordinator {
  registerRouteRequest(
    handler: (request: TimeEntryLeaveRequest) => void,
  ): () => void;
  registerNativeCloseRequest(
    handler: (request: TimeEntryLeaveRequest) => void,
  ): () => void;
  updateGuardState(state: TimeEntryNavigationGuardState): void;
}

export function deriveTimeEntryNavigationGuard(
  signals: TimeEntryNavigationSignals,
): TimeEntryNavigationGuardState {
  const shouldBlock =
    signals.hasDirtyDraft ||
    signals.hasPendingWrite ||
    signals.hasFailedWrite;
  return {
    shouldBlockRoute: shouldBlock,
    shouldBlockNativeClose: shouldBlock,
  };
}
