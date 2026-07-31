import { useState } from "react";
import {
  ChevronsLeft,
  ChevronsRight,
  Clock3,
} from "lucide-react";
import {
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
} from "react-router";

import { ThemeMenu } from "@/app/theme/ThemeMenu";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import {
  navigationDestinations,
  type NavigationDestination,
} from "./navigation";
import { ProductPage } from "./pages/ProductPage";

function SidebarDestination({
  destination,
  isCollapsed,
}: {
  destination: NavigationDestination;
  isCollapsed: boolean;
}) {
  const Icon = destination.icon;
  const link = (
    <NavLink
      aria-label={destination.label}
      className={({ isActive }) =>
        cn(
          "flex h-10 items-center rounded-lg text-sm font-medium transition-colors",
          isCollapsed ? "justify-center px-0" : "gap-3 px-3",
          isActive
            ? "bg-sidebar-primary text-sidebar-primary-foreground shadow-sm"
            : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        )
      }
      end={destination.path === "/"}
      to={destination.path}
    >
      <Icon aria-hidden="true" className="size-[1.1rem]" />
      {!isCollapsed && <span>{destination.label}</span>}
    </NavLink>
  );

  if (!isCollapsed) return link;

  return (
    <Tooltip>
      <TooltipTrigger render={link} />
      <TooltipContent side="right">{destination.label}</TooltipContent>
    </Tooltip>
  );
}

export function AppShell() {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const location = useLocation();
  const activeDestination =
    navigationDestinations.find(
      ({ path }) =>
        path === location.pathname ||
        (path !== "/" && location.pathname.startsWith(`${path}/`)),
    ) ?? navigationDestinations[0];

  return (
    <div className="flex h-screen min-h-[640px] overflow-hidden bg-muted/35">
      <aside
        aria-label="Application sidebar"
        className={cn(
          "relative flex shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-out",
          isCollapsed ? "w-[4.5rem]" : "w-60",
        )}
      >
        <div className="flex h-16 items-center border-b px-4">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm shadow-primary/20">
            <Clock3 aria-hidden="true" className="size-[1.15rem]" />
          </div>
          {!isCollapsed && (
            <div className="ml-3 min-w-0">
              <p className="truncate text-sm font-semibold tracking-tight">
                Personal Timesheet
              </p>
              <p className="truncate text-[0.7rem] text-muted-foreground">
                Local workspace
              </p>
            </div>
          )}
        </div>

        <nav
          aria-label="Primary navigation"
          className="flex flex-1 flex-col gap-1 p-3"
        >
          {navigationDestinations.map((destination) => (
            <SidebarDestination
              key={destination.path}
              destination={destination}
              isCollapsed={isCollapsed}
            />
          ))}
        </nav>

        <div className="border-t p-3">
          <Button
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "text-muted-foreground",
              !isCollapsed && "w-full justify-start",
            )}
            onClick={() => setIsCollapsed((collapsed) => !collapsed)}
            size={isCollapsed ? "icon" : "default"}
            variant="ghost"
          >
            {isCollapsed ? (
              <ChevronsRight aria-hidden="true" />
            ) : (
              <>
                <ChevronsLeft aria-hidden="true" />
                <span>Collapse</span>
              </>
            )}
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between border-b bg-background/90 px-5 backdrop-blur">
          <div>
            <p className="text-sm font-medium">{activeDestination.label}</p>
            <p className="text-xs text-muted-foreground">Personal workspace</p>
          </div>
          <ThemeMenu />
        </header>

        <main
          className={cn(
            "min-w-0 flex-1 overflow-auto",
            activeDestination.density === "compact" ? "p-5" : "p-8",
          )}
          data-density={activeDestination.density}
        >
          <div
            className={cn(
              "mx-auto min-h-full",
              activeDestination.density === "compact"
                ? "max-w-none"
                : "max-w-6xl",
            )}
          >
            <Routes>
              {navigationDestinations.map((destination) => (
                <Route
                  key={destination.path}
                  element={<ProductPage destination={destination} />}
                  path={destination.path}
                />
              ))}
              <Route path="*" element={<Navigate replace to="/" />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}
