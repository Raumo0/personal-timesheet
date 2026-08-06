import type { DailyActivityAxis, DailyActivityPoint } from "./invoice";

interface DailyActivityChartProps {
  axis: DailyActivityAxis;
  points: DailyActivityPoint[];
}

const WIDTH = 760;
const HEIGHT = 280;
const PLOT = { left: 58, right: 744, top: 18, bottom: 202 };

export function DailyActivityChart({ axis, points }: DailyActivityChartProps) {
  const plotWidth = PLOT.right - PLOT.left;
  const plotHeight = PLOT.bottom - PLOT.top;
  const upperBound = axis.upperBoundHours > 0 ? axis.upperBoundHours : 1;
  const slotWidth = plotWidth / Math.max(points.length, 1);
  const barWidth = Math.max(Math.min(slotWidth * 0.54, 18), 2);
  const summary = points
    .map((point) => `${formatChartDate(point.date)}: ${formatDuration(point.minutes)}`)
    .join("; ");

  return (
    <figure aria-label="Daily activity" className="invoice-chart invoice-chart--daily">
      <h3 className="invoice-preview__section-title">Daily activity</h3>
      <div className="invoice-daily-chart__viewport">
        <svg
          aria-hidden="true"
          className="invoice-daily-chart"
          focusable="false"
          role="presentation"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        >
          {axis.ticks.map((tick) => {
            const y = PLOT.bottom - (tick / upperBound) * plotHeight;
            return (
              <g key={tick}>
                <line
                  className="invoice-daily-chart__guide"
                  x1={PLOT.left}
                  x2={PLOT.right}
                  y1={y}
                  y2={y}
                />
                <text
                  className="invoice-daily-chart__tick"
                  textAnchor="end"
                  x={PLOT.left - 10}
                  y={y + 4}
                >
                  {formatHourTick(tick)}
                </text>
              </g>
            );
          })}
          {points.map((point, index) => {
            const center = PLOT.left + slotWidth * (index + 0.5);
            const hours = point.minutes / 60;
            const barHeight = Math.min(hours / upperBound, 1) * plotHeight;
            return (
              <g key={point.date}>
                {barHeight > 0 ? (
                  <rect
                    className="invoice-daily-chart__bar"
                    height={barHeight}
                    rx="2"
                    width={barWidth}
                    x={center - barWidth / 2}
                    y={PLOT.bottom - barHeight}
                  />
                ) : null}
                <text
                  className="invoice-daily-chart__date"
                  textAnchor="end"
                  transform={`rotate(-38 ${center + 3} ${PLOT.bottom + 22})`}
                  x={center + 3}
                  y={PLOT.bottom + 22}
                >
                  {formatChartDate(point.date)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  );
}

function formatHourTick(value: number): string {
  const formatted = Number.isInteger(value)
    ? String(value)
    : value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  return `${formatted} h`;
}

function formatDuration(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
}

function formatChartDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return new Intl.DateTimeFormat("en", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(date);
}
