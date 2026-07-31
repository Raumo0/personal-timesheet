import { HashRouter } from "react-router";

import { AppShell } from "@/app/AppShell";
import { ThemeProvider } from "@/app/theme/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SqliteClientCatalog } from "@/features/clients/sqlite-client-catalog";

const clientCatalog = new SqliteClientCatalog();

function App() {
  return (
    <ThemeProvider>
      <TooltipProvider delay={350}>
        <HashRouter>
          <AppShell clientCatalog={clientCatalog} />
        </HashRouter>
      </TooltipProvider>
    </ThemeProvider>
  );
}

export default App;
