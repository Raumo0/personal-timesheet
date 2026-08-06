import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { DailyActivityChart } from "./DailyActivityChart";

afterEach(cleanup);

describe("DailyActivityChart", () => {
  test("renders every date against the supplied adaptive hours axis", () => {
    render(
      <DailyActivityChart
        axis={{ upperBoundHours: 1, ticks: [0, 0.25, 0.5, 0.75, 1] }}
        points={[
          { date: "2026-02-01", minutes: 0 },
          { date: "2026-02-02", minutes: 30 },
          { date: "2026-02-03", minutes: 60 },
        ]}
      />,
    );

    const chart = screen.getByRole("figure", { name: "Daily activity" });
    expect(within(chart).getByText("0 h")).toBeInTheDocument();
    expect(within(chart).getByText("0.25 h")).toBeInTheDocument();
    expect(within(chart).getByText("1 h")).toBeInTheDocument();
    expect(within(chart).getByText("Sun, Feb 1")).toBeInTheDocument();
    expect(within(chart).getByText("Mon, Feb 2")).toBeInTheDocument();
    expect(within(chart).getByText("Tue, Feb 3")).toBeInTheDocument();
  });

  test("provides a non-visual summary including zero-hour dates", () => {
    render(
      <DailyActivityChart
        axis={{ upperBoundHours: 1, ticks: [0, 0.5, 1] }}
        points={[
          { date: "2026-02-01", minutes: 0 },
          { date: "2026-02-02", minutes: 30 },
        ]}
      />,
    );

    expect(screen.getByText("Sun, Feb 1: 0:00; Mon, Feb 2: 0:30")).toHaveClass(
      "sr-only",
    );
  });
});
