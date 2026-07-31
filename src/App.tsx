import { HashRouter } from "react-router";

import { AppShell } from "@/app/AppShell";
import { ThemeProvider } from "@/app/theme/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";

function App() {
  return (
    <ThemeProvider>
      <TooltipProvider>
        <HashRouter>
          <AppShell />
        </HashRouter>
      </TooltipProvider>
    </ThemeProvider>
  );
}

export default App;
