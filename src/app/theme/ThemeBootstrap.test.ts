import { readFileSync } from "node:fs";

import { afterEach, describe, expect, test, vi } from "vitest";

const STORAGE_KEY = "personal-timesheet.appearance";

function runThemeBootstrap({
  storedAppearance,
  systemDark,
}: {
  storedAppearance?: string;
  systemDark: boolean;
}) {
  if (storedAppearance) {
    localStorage.setItem(STORAGE_KEY, storedAppearance);
  }

  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: systemDark,
      media: "(prefers-color-scheme: dark)",
    }),
  );

  const html = readFileSync("index.html", "utf8");
  const parsedDocument = new DOMParser().parseFromString(html, "text/html");
  const bootstrap = parsedDocument.querySelector(
    "script[data-theme-bootstrap]",
  )?.textContent;

  expect(bootstrap).toBeTruthy();
  if (!bootstrap) return;

  Function(bootstrap)();
}

afterEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("light", "dark");
  document.documentElement.style.removeProperty("color-scheme");
  vi.unstubAllGlobals();
});

describe("pre-render appearance bootstrap", () => {
  test("applies the saved dark appearance before React starts", () => {
    runThemeBootstrap({ storedAppearance: "dark", systemDark: false });

    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  test("applies the saved light appearance before React starts", () => {
    runThemeBootstrap({ storedAppearance: "light", systemDark: true });

    expect(document.documentElement).toHaveClass("light");
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  test("follows the operating system when no explicit appearance is saved", () => {
    runThemeBootstrap({ systemDark: true });

    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });
});
