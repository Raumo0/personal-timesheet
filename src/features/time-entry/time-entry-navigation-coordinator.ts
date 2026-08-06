import type {
  TimeEntryLeaveRequest,
  TimeEntryNavigationCoordinator,
  TimeEntryNavigationGuardState,
} from "./time-entry-navigation-guard";

export interface TimeEntryNativeWindow {
  onCloseRequested(
    handler: (event: { preventDefault(): void }) => void,
  ): Promise<() => void>;
  destroy(): Promise<void>;
}

type LeaveHandler = (request: TimeEntryLeaveRequest) => void;

export class AppTimeEntryNavigationCoordinator
  implements TimeEntryNavigationCoordinator
{
  private routeHandler?: LeaveHandler;
  private nativeCloseHandler?: LeaveHandler;
  private state: TimeEntryNavigationGuardState = {
    shouldBlockRoute: false,
    shouldBlockNativeClose: false,
  };
  private readonly listeners = new Set<() => void>();

  registerRouteRequest(handler: LeaveHandler): () => void {
    this.routeHandler = handler;
    return () => {
      if (this.routeHandler === handler) this.routeHandler = undefined;
    };
  }

  registerNativeCloseRequest(handler: LeaveHandler): () => void {
    this.nativeCloseHandler = handler;
    return () => {
      if (this.nativeCloseHandler === handler) this.nativeCloseHandler = undefined;
    };
  }

  updateGuardState(state: TimeEntryNavigationGuardState): void {
    this.state = state;
    for (const listener of this.listeners) listener();
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getGuardState = (): TimeEntryNavigationGuardState => this.state;

  requestRoute(
    continueNavigation: () => void,
    cancelNavigation?: () => void,
  ): boolean {
    if (!this.state.shouldBlockRoute || !this.routeHandler) return false;
    this.routeHandler({ continueNavigation, cancelNavigation });
    return true;
  }

  requestNativeClose(continueNavigation: () => void): boolean {
    if (!this.state.shouldBlockNativeClose || !this.nativeCloseHandler) {
      return false;
    }
    this.nativeCloseHandler({ continueNavigation });
    return true;
  }
}
