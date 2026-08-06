import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import { TimeEntryCell } from "./TimeEntryCell";

afterEach(cleanup);

function renderCell(
  overrides: Partial<React.ComponentProps<typeof TimeEntryCell>> = {},
) {
  const props: React.ComponentProps<typeof TimeEntryCell> = {
    label: "Monday, August 3 · Acme · Website",
    value: "",
    onChange: vi.fn(),
    onCommit: vi.fn(),
    onEscape: vi.fn(),
    ...overrides,
  };
  render(<TimeEntryCell {...props} />);
  return {
    input: screen.getByRole("textbox", { name: props.label }),
    props,
  };
}

test("renders an absent entry as a blank compact duration cell", () => {
  const { input } = renderCell();

  expect(input).toHaveValue("");
  expect(input).toHaveAttribute("placeholder", "H:MM");
  expect(input).toHaveAttribute("inputmode", "numeric");
});

test("reports each valid draft change without committing early", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const onCommit = vi.fn();
  const { input } = renderCell({ onChange, onCommit });

  await user.type(input, "1:30");

  expect(onChange).toHaveBeenLastCalledWith("0");
  expect(onCommit).not.toHaveBeenCalled();
});

test("associates invalid guidance without adding visible cell content", () => {
  const { input } = renderCell({
    value: "1:60",
    validationError: "Enter a duration in H:MM format.",
  });

  expect(input).toHaveAttribute("aria-invalid", "true");
  expect(input).toHaveAccessibleDescription(
    "Enter a duration in H:MM format.",
  );
  const guidance = screen.getByText("Enter a duration in H:MM format.");
  expect(guidance).toHaveClass("sr-only");
  expect(guidance).not.toHaveAttribute("aria-live");
});

test("Escape restores the saved value through the controlled callback and keeps focus", async () => {
  const user = userEvent.setup();
  const onEscape = vi.fn();
  const { input } = renderCell({ value: "2:15", onEscape });
  input.focus();

  await user.keyboard("{Escape}");

  expect(onEscape).toHaveBeenCalledOnce();
  expect(input).toHaveFocus();
});

test("Enter commits once without also triggering blur", async () => {
  const user = userEvent.setup();
  const onCommit = vi.fn();
  const { input } = renderCell({ value: "1:30", onCommit });
  input.focus();

  await user.keyboard("{Enter}");

  expect(onCommit).toHaveBeenCalledOnce();
  expect(onCommit).toHaveBeenCalledWith("1:30");
  expect(input).toHaveFocus();
});

test("blur commits the current draft", async () => {
  const user = userEvent.setup();
  const onCommit = vi.fn();
  const { input } = renderCell({ value: "0:45", onCommit });

  await user.click(input);
  await user.tab();

  expect(onCommit).toHaveBeenCalledWith("0:45");
});

test("read-only archived cells cannot be edited or committed", async () => {
  const user = userEvent.setup();
  const onCommit = vi.fn();
  const onChange = vi.fn();
  const { input } = renderCell({
    value: "1:00",
    readOnly: true,
    onCommit,
    onChange,
  });

  expect(input).toHaveAttribute("readonly");
  await user.click(input);
  await user.keyboard("{Enter}");
  await user.type(input, "2:00");

  expect(onCommit).not.toHaveBeenCalled();
  expect(onChange).not.toHaveBeenCalled();
});

test("associates a failed save alert with the identifiable cell", () => {
  const { input } = renderCell({
    value: "1:30",
    saveError: "Monday · Acme · Website was not saved.",
  });

  expect(input).toHaveAttribute("aria-invalid", "true");
  expect(input).toHaveAccessibleDescription(
    "Monday · Acme · Website was not saved.",
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Monday · Acme · Website was not saved.",
  );
});

test("restores focus when the parent issues a new focus request", () => {
  const props = {
    label: "Monday, August 3 · Acme · Website",
    value: "1:30",
    onChange: vi.fn(),
    onCommit: vi.fn(),
    onEscape: vi.fn(),
  };
  const { rerender } = render(<TimeEntryCell {...props} focusRequest={0} />);
  const input = screen.getByRole("textbox", { name: props.label });
  expect(input).not.toHaveFocus();

  rerender(<TimeEntryCell {...props} focusRequest={1} />);

  expect(input).toHaveFocus();
});
