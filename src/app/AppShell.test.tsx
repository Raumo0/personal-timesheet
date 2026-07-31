import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import App from "@/App";

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

    expect(destinations).toHaveLength(4);
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
    expect(screen.getByRole("link", { name: "Reports" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Expenses" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
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
});
