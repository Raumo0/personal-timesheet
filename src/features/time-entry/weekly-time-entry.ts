export type LocalDate = string & { readonly __localDate: unique symbol };

export type WorkReference =
  | { readonly kind: "project"; readonly projectId: string }
  | { readonly kind: "task"; readonly taskId: string };

export interface Week {
  readonly monday: LocalDate;
  readonly dates: readonly [
    LocalDate,
    LocalDate,
    LocalDate,
    LocalDate,
    LocalDate,
    LocalDate,
    LocalDate,
  ];
}

export type DurationParseResult =
  | { readonly ok: true; readonly minutes: number }
  | {
      readonly ok: false;
      readonly error: "Enter a duration in H:MM format.";
    };

export type DailyTotalResult =
  | { readonly ok: true; readonly total: number }
  | {
      readonly ok: false;
      readonly total: number;
      readonly error: "Daily total cannot exceed 24:00.";
    };

const DURATION_ERROR = "Enter a duration in H:MM format." as const;
const DAILY_LIMIT_ERROR = "Daily total cannot exceed 24:00." as const;
const DAYS_PER_WEEK = 7;
const MINUTES_PER_DAY = 1440;

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function formatLocalDate(date: Date): LocalDate {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` as LocalDate;
}

function parseLocalDate(value: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    throw new Error(`Invalid local date: ${value}`);
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day, 12);

  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    throw new Error(`Invalid local date: ${value}`);
  }

  return date;
}

function addCalendarDays(value: string, days: number): LocalDate {
  const date = parseLocalDate(value);
  date.setDate(date.getDate() + days);
  return formatLocalDate(date);
}

export function weekFromMonday(monday: string): Week {
  if (parseLocalDate(monday).getDay() !== 1) {
    throw new Error(`Week start must be a Monday: ${monday}`);
  }

  const dates = Array.from({ length: DAYS_PER_WEEK }, (_, index) =>
    addCalendarDays(monday, index),
  ) as unknown as Week["dates"];

  return { monday: dates[0], dates };
}

export function currentWeek(now: Date = new Date()): Week {
  if (Number.isNaN(now.getTime())) {
    throw new Error("Current date must be valid");
  }

  const date = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
    12,
  );
  const daysSinceMonday = (date.getDay() + 6) % DAYS_PER_WEEK;
  date.setDate(date.getDate() - daysSinceMonday);
  return weekFromMonday(formatLocalDate(date));
}

export function addWeeks(week: Week, amount: number): Week {
  if (!Number.isInteger(amount)) {
    throw new Error("Week offset must be an integer");
  }
  return weekFromMonday(addCalendarDays(week.monday, amount * DAYS_PER_WEEK));
}

export function parseDuration(value: string): DurationParseResult {
  const match = /^(\d+):([0-5]\d)$/.exec(value);
  if (!match) {
    return { ok: false, error: DURATION_ERROR };
  }

  const minutes = Number(match[1]) * 60 + Number(match[2]);
  return Number.isSafeInteger(minutes)
    ? { ok: true, minutes }
    : { ok: false, error: DURATION_ERROR };
}

function assertMinutes(minutes: number): void {
  if (!Number.isSafeInteger(minutes) || minutes < 0) {
    throw new Error("Minutes must be non-negative integers");
  }
}

export function formatDuration(minutes: number): string {
  assertMinutes(minutes);
  return `${Math.floor(minutes / 60)}:${pad(minutes % 60)}`;
}

export function rowKey(reference: WorkReference): string {
  return reference.kind === "project"
    ? `project:${reference.projectId}`
    : `task:${reference.taskId}`;
}

export function calculateRowTotal(
  minutes: readonly (number | undefined)[],
): number {
  return minutes.reduce<number>((total, value) => {
    const presentValue = value ?? 0;
    assertMinutes(presentValue);
    return total + presentValue;
  }, 0);
}

export function calculateDayTotals(
  rows: readonly (readonly (number | undefined)[])[],
): number[] {
  const totals = Array.from({ length: DAYS_PER_WEEK }, () => 0);
  for (const row of rows) {
    for (let dayIndex = 0; dayIndex < DAYS_PER_WEEK; dayIndex += 1) {
      const value = row[dayIndex] ?? 0;
      assertMinutes(value);
      totals[dayIndex] += value;
    }
  }
  return totals;
}

export function calculateGrandTotal(
  rows: readonly (readonly (number | undefined)[])[],
): number {
  return calculateDayTotals(rows).reduce((total, value) => total + value, 0);
}

export function validateDailyTotal(
  minutes: readonly (number | undefined)[],
): DailyTotalResult {
  const total = calculateRowTotal(minutes);
  return total <= MINUTES_PER_DAY
    ? { ok: true, total }
    : { ok: false, total, error: DAILY_LIMIT_ERROR };
}
