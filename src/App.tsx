import { createHashRouter, RouterProvider } from "react-router";
import { useMemo } from "react";

import { AppShell } from "@/app/AppShell";
import { ThemeProvider } from "@/app/theme/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SqliteClientCatalog } from "@/features/clients/sqlite-client-catalog";
import { SqliteProjectCatalog } from "@/features/projects/sqlite-project-catalog";
import { SqliteTaskCatalog } from "@/features/tasks/sqlite-task-catalog";
import { SqliteCatalogLifecycle } from "@/features/catalog-lifecycle/sqlite-catalog-lifecycle";
import { TauriBackupService } from "@/features/backup/tauri-backup-service";
import { SqliteWeeklyTimeEntryStore } from "@/features/time-entry/sqlite-weekly-time-entry-store";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { isTauri } from "@tauri-apps/api/core";

const clientCatalog = new SqliteClientCatalog();
const projectCatalog = new SqliteProjectCatalog();
const taskCatalog = new SqliteTaskCatalog();
const catalogLifecycle = new SqliteCatalogLifecycle();
const backupService = new TauriBackupService();
const weeklyStore = new SqliteWeeklyTimeEntryStore();

function App() {
  const router = useMemo(
    () =>
      createHashRouter([
        {
          path: "*",
          element: (
            <ThemeProvider>
              <TooltipProvider delay={350}>
                <AppShell
                  backupService={backupService}
                  clientCatalog={clientCatalog}
                  lifecycle={catalogLifecycle}
                  nativeWindow={isTauri() ? getCurrentWindow() : undefined}
                  projectCatalog={projectCatalog}
                  taskCatalog={taskCatalog}
                  weeklyStore={weeklyStore}
                />
              </TooltipProvider>
            </ThemeProvider>
          ),
        },
      ]),
    [],
  );
  return <RouterProvider router={router} />;
}

export default App;
