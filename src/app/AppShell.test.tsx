import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router";

import App from "@/App";
import { AppShell } from "@/app/AppShell";
import { ThemeProvider } from "@/app/theme/ThemeProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { InMemoryClientCatalog } from "@/features/clients/in-memory-client-catalog";
import { InMemoryBackupService } from "@/features/backup/in-memory-backup-service";

function renderApp() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );

  return render(<App />);
}

afterEach(() => {
  cleanup();
  window.location.hash = "";
  localStorage.clear();
  document.documentElement.classList.remove("light", "dark");
  vi.unstubAllGlobals();
});

describe("application shell", () => {
  test("opens Timesheet with all primary destinations available", () => {
    renderApp();

    expect(
      screen.getByRole("heading", { name: "Timesheet" }),
    ).toBeInTheDocument();

    const navigation = screen.getByRole("navigation", {
      name: "Primary navigation",
    });
    const destinations = within(navigation).getAllByRole("link");

    expect(destinations).toHaveLength(5);
    expect(
      within(navigation).getByRole("link", { name: "Timesheet" }),
    ).toHaveAttribute("aria-current", "page");
  });

  test("navigates to Reports and identifies it as active", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("link", { name: "Reports" }));

    expect(screen.getByRole("heading", { name: "Reports" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reports" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  test("opens Clients from persistent navigation with an injected catalog", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    render(
      <ThemeProvider>
        <TooltipProvider>
          <MemoryRouter>
            <AppShell
              backupService={new InMemoryBackupService()}
              clientCatalog={new InMemoryClientCatalog()}
            />
          </MemoryRouter>
        </TooltipProvider>
      </ThemeProvider>,
    );

    const clientsLink = screen.getByRole("link", { name: "Clients" });
    clientsLink.focus();
    await user.keyboard("{Enter}");

    expect(
      await screen.findByRole("heading", { name: "Clients" }),
    ).toBeInTheDocument();
    expect(clientsLink).toHaveAttribute("aria-current", "page");
    expect(
      await screen.findByRole("heading", { name: "No clients yet" }),
    ).toBeInTheDocument();
  });

  test("keeps destinations accessible when the sidebar is collapsed", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(
      screen.getByRole("button", { name: "Collapse sidebar" }),
    );

    expect(
      screen.getByRole("button", { name: "Expand sidebar" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Timesheet" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Clients" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reports" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Expenses" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  test("shows only the tooltip for the collapsed destination under the pointer", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getByRole("link", { name: "Reports" }));
    await user.click(screen.getByRole("link", { name: "Expenses" }));
    await user.click(screen.getByRole("link", { name: "Settings" }));
    await user.click(
      screen.getByRole("button", { name: "Collapse sidebar" }),
    );

    expect(screen.queryByText("Reports")).not.toBeInTheDocument();
    expect(screen.queryByText("Expenses")).not.toBeInTheDocument();

    await user.hover(screen.getByRole("link", { name: "Reports" }));

    expect(await screen.findByText("Reports")).toBeInTheDocument();
    expect(screen.queryByText("Expenses")).not.toBeInTheDocument();
  });

  test("uses compact density only for Timesheet", async () => {
    const user = userEvent.setup();
    renderApp();

    expect(screen.getByRole("main")).toHaveAttribute(
      "data-density",
      "compact",
    );

    await user.click(screen.getByRole("link", { name: "Settings" }));

    expect(screen.getByRole("main")).toHaveAttribute(
      "data-density",
      "comfortable",
    );
  });

  test("opens the real Settings data workspace with an injected service", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
    render(
      <ThemeProvider>
        <TooltipProvider>
          <MemoryRouter initialEntries={["/settings"]}>
            <AppShell
              backupService={new InMemoryBackupService()}
              clientCatalog={new InMemoryClientCatalog()}
            />
          </MemoryRouter>
        </TooltipProvider>
      </ThemeProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Settings" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Back up data" }),
    ).toBeEnabled();

    await user.click(screen.getByRole("link", { name: "Reports" }));
    expect(screen.getByRole("heading", { name: "Reports" })).toBeInTheDocument();
  });

  test("keeps page chrome aligned across workspace densities", async () => {
    const user = userEvent.setup();
    renderApp();

    const main = screen.getByRole("main");

    expect(main).toHaveClass("p-8");
    expect(screen.getAllByText("Timesheet")).toHaveLength(2);
    expect(screen.getAllByText("Local workspace")).toHaveLength(1);

    await user.click(screen.getByRole("link", { name: "Reports" }));

    expect(main).toHaveClass("p-8");
    expect(screen.getAllByText("Reports")).toHaveLength(2);
  });

  test("moves focus directly to the main workspace", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(
      screen.getByRole("link", { name: "Skip to main content" }),
    );

    expect(screen.getByRole("main")).toHaveFocus();
  });
});
