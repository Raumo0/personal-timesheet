import {
  createContext,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Appearance = "system" | "light" | "dark";

type ThemeContextValue = {
  appearance: Appearance;
  setAppearance: (appearance: Appearance) => void;
};

const STORAGE_KEY = "personal-timesheet.appearance";
const SYSTEM_QUERY = "(prefers-color-scheme: dark)";
const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStoredAppearance(): Appearance {
  const stored = localStorage.getItem(STORAGE_KEY);
  return stored === "light" || stored === "dark" || stored === "system"
    ? stored
    : "system";
}

function resolveAppearance(appearance: Appearance) {
  return (
    appearance === "system"
      ? window.matchMedia(SYSTEM_QUERY).matches
        ? "dark"
        : "light"
      : appearance
  );
}

function applyAppearance(appearance: Appearance) {
  const resolved = resolveAppearance(appearance);
  document.documentElement.classList.remove("light", "dark");
  document.documentElement.classList.add(resolved);
  document.documentElement.style.colorScheme = resolved;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [appearance, setAppearanceState] =
    useState<Appearance>(readStoredAppearance);

  useLayoutEffect(() => {
    applyAppearance(appearance);

    if (appearance !== "system") return;

    const mediaQuery = window.matchMedia(SYSTEM_QUERY);
    const handleChange = () => applyAppearance("system");
    mediaQuery.addEventListener("change", handleChange);

    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [appearance]);

  const value = useMemo(
    () => ({
      appearance,
      setAppearance(nextAppearance: Appearance) {
        localStorage.setItem(STORAGE_KEY, nextAppearance);
        setAppearanceState(nextAppearance);
      },
    }),
    [appearance],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);

  if (!value) {
    throw new Error("useTheme must be used within ThemeProvider");
  }

  return value;
}
