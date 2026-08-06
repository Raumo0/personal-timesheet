import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { WorkCategoryChart } from "./WorkCategoryChart";

afterEach(cleanup);

describe("WorkCategoryChart", () => {
  test("groups directly labelled proportional tracks by Project", () => {
    render(
      <WorkCategoryChart
        shares={[
          {
            projectId: "project-1",
            projectName: "Atlas launch",
            lineKey: "project-1:task-1",
            label:
              "Discovery and stakeholder alignment for the international launch programme",
            minutes: 15,
            share: 0.05,
          },
          {
            projectId: "project-1",
            projectName: "Atlas launch",
            lineKey: "project-1:task-2",
            label: "Product design",
            minutes: 285,
            share: 0.95,
          },
        ]}
      />,
    );

    expect(screen.getByRole("figure", { name: "Work category breakdown" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Atlas launch" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Discovery and stakeholder alignment for the international launch programme",
      ),
    ).toBeVisible();
    expect(screen.getByText("0:15 · 5%")).toBeVisible();
    expect(screen.getByText("4:45 · 95%")).toBeVisible();
  });

  test("provides a non-visual Project and category summary", () => {
    render(
      <WorkCategoryChart
        shares={[
          {
            projectId: "project-1",
            projectName: "Atlas launch",
            lineKey: "project-1:task-1",
            label: "Product design",
            minutes: 30,
            share: 1,
          },
        ]}
      />,
    );

    expect(
      screen.getByText("Atlas launch — Product design: 0:30, 100%"),
    ).toHaveClass("sr-only");
  });
});
