import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import App from "@/App";

const STORAGE_KEY = "personal-timesheet.appearance";

function installSystemTheme(initiallyDark: boolean) {
  let matches = initiallyDark;
  const listeners = new Set<(event: MediaQueryListEvent) => void>();

  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: (
        type: string,
        listener: (event: MediaQueryListEvent) => void,
      ) => {
        if (type === "change") listeners.add(listener);
      },
      removeEventListener: (
        type: string,
        listener: (event: MediaQueryListEvent) => void,
      ) => {
        if (type === "change") listeners.delete(listener);
      },
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );

  return {
    setDark(nextMatches: boolean) {
      matches = nextMatches;
      act(() => {
        listeners.forEach((listener) =>
          listener({
            matches,
            media: "(prefers-color-scheme: dark)",
          } as MediaQueryListEvent),
        );
      });
    },
  };
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.documentElement.classList.remove("light", "dark");
  vi.unstubAllGlobals();
});

describe("application appearance", () => {
  test("follows the dark system appearance on first launch", () => {
    installSystemTheme(true);

    render(<App />);

    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  test("responds when the system appearance changes", () => {
    const systemTheme = installSystemTheme(false);
    render(<App />);

    expect(document.documentElement).toHaveClass("light");

    systemTheme.setDark(true);

    expect(document.documentElement).toHaveClass("dark");
  });

  test("applies and persists an explicit dark appearance", async () => {
    installSystemTheme(false);
    const user = userEvent.setup();
    render(<App />);

    await user.click(
      screen.getByRole("button", { name: "Appearance: System" }),
    );
    await user.click(await screen.findByRole("menuitem", { name: "Dark" }));

    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("dark");
  });

  test("restores an explicit light appearance", () => {
    localStorage.setItem(STORAGE_KEY, "light");
    installSystemTheme(true);

    render(<App />);

    expect(document.documentElement).toHaveClass("light");
    expect(
      screen.getByRole("button", { name: "Appearance: Light" }),
    ).toBeInTheDocument();
  });
});
