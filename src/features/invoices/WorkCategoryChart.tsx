import type { CSSProperties } from "react";

import type { WorkCategoryShare } from "./invoice";

interface WorkCategoryChartProps {
  shares: WorkCategoryShare[];
}

export function WorkCategoryChart({ shares }: WorkCategoryChartProps) {
  const projects = groupByProject(shares);
  const summary = shares
    .map(
      (share) =>
        `${share.projectName} — ${share.label}: ${formatDuration(share.minutes)}, ${formatPercent(share.share)}`,
    )
    .join("; ");

  return (
    <figure
      aria-label="Work category breakdown"
      className="invoice-chart invoice-chart--categories"
    >
      <h3 className="invoice-preview__section-title">Work category breakdown</h3>
      <div className="invoice-category-chart">
        {projects.map((project) => (
          <section className="invoice-category-chart__project" key={project.id}>
            <h4>{project.name}</h4>
            <div className="invoice-category-chart__rows">
              {project.shares.map((share) => (
                <div className="invoice-category-chart__row" key={share.lineKey}>
                  <div className="invoice-category-chart__label-row">
                    <span className="invoice-category-chart__label">{share.label}</span>
                    <span className="invoice-category-chart__value">
                      {formatDuration(share.minutes)} · {formatPercent(share.share)}
                    </span>
                  </div>
                  <div aria-hidden="true" className="invoice-category-chart__track">
                    <span
                      className="invoice-category-chart__fill"
                      style={
                        {
                          "--invoice-category-share": `${share.share * 100}%`,
                        } as CSSProperties
                      }
                    />
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  );
}

function groupByProject(shares: WorkCategoryShare[]) {
  const projects = new Map<
    string,
    { id: string; name: string; shares: WorkCategoryShare[] }
  >();
  for (const share of shares) {
    const project = projects.get(share.projectId);
    if (project) {
      project.shares.push(share);
    } else {
      projects.set(share.projectId, {
        id: share.projectId,
        name: share.projectName,
        shares: [share],
      });
    }
  }
  return [...projects.values()];
}

function formatDuration(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
}

function formatPercent(share: number): string {
  return new Intl.NumberFormat("en", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(share);
}
