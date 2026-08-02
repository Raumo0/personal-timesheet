import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { ProjectForm } from "./ProjectForm";

afterEach(cleanup);

const client = { currencyCode: "EUR", hourlyRateMinor: 12_500 };

test("shows the client rate as read-only when inheritance is selected", () => {
  render(
    <ProjectForm open client={client} onOpenChange={vi.fn()} onSave={vi.fn()} />,
  );

  expect(screen.getByRole("radio", { name: "Inherit client rate" })).toBeChecked();
  expect(screen.getByText(/€125\.00.*client/i)).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Hourly rate" })).not.toBeInTheDocument();
});

test("enables an explicit zero override", async () => {
  const user = userEvent.setup();
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(<ProjectForm open client={client} onOpenChange={vi.fn()} onSave={onSave} />);

  await user.click(screen.getByRole("radio", { name: "Override rate" }));
  await user.type(screen.getByRole("textbox", { name: "Hourly rate" }), "0");
  await user.type(screen.getByRole("textbox", { name: "Project name" }), "Website");
  await user.click(screen.getByRole("button", { name: "Save project" }));

  expect(onSave).toHaveBeenCalledWith({ name: "Website", hourlyRateOverrideMinor: 0 });
});
