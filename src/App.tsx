import { HashRouter } from "react-router";

import { AppShell } from "@/app/AppShell";
import { ThemeProvider } from "@/app/theme/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SqliteClientCatalog } from "@/features/clients/sqlite-client-catalog";
import { SqliteProjectCatalog } from "@/features/projects/sqlite-project-catalog";
import { SqliteTaskCatalog } from "@/features/tasks/sqlite-task-catalog";
import { SqliteCatalogLifecycle } from "@/features/catalog-lifecycle/sqlite-catalog-lifecycle";
import { TauriBackupService } from "@/features/backup/tauri-backup-service";

const clientCatalog = new SqliteClientCatalog();
const projectCatalog = new SqliteProjectCatalog();
const taskCatalog = new SqliteTaskCatalog();
const catalogLifecycle = new SqliteCatalogLifecycle();
const backupService = new TauriBackupService();

function App() {
  return (
    <ThemeProvider>
      <TooltipProvider delay={350}>
        <HashRouter>
          <AppShell
            backupService={backupService}
            clientCatalog={clientCatalog}
            lifecycle={catalogLifecycle}
            projectCatalog={projectCatalog}
            taskCatalog={taskCatalog}
          />
        </HashRouter>
      </TooltipProvider>
    </ThemeProvider>
  );
}

export default App;
