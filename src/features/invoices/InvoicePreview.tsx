import type { Ref } from "react";

import { formatMinorUnits } from "../money/money";
import { DailyActivityChart } from "./DailyActivityChart";
import type { InvoiceDocument } from "./invoice";
import { WorkCategoryChart } from "./WorkCategoryChart";
import "./invoice.css";

interface InvoicePreviewProps {
  document: InvoiceDocument;
  previewRef?: Ref<HTMLElement>;
}

export function InvoicePreview({ document, previewRef }: InvoicePreviewProps) {
  const showSummary =
    document.includeDailyActivity || document.includeWorkCategoryBreakdown;

  return (
    <article
      aria-label="Invoice preview"
      className="invoice-preview"
      ref={previewRef}
    >
      <header className="invoice-preview__header">
        <div className="invoice-preview__masthead">
          <div>
            <p className="invoice-preview__eyebrow">Prepared by</p>
            <p className="invoice-preview__sender">{document.senderName}</p>
          </div>
          <h2>Invoice</h2>
        </div>
        <div className="invoice-preview__identity-grid">
          <div className="invoice-preview__recipient">
            <p className="invoice-preview__eyebrow">Bill to</p>
            <h3>{document.recipientName}</h3>
          </div>
          <dl className="invoice-preview__meta">
            <div>
              <dt>Issue date</dt>
              <dd>{formatDate(document.issueDate)}</dd>
            </div>
            {document.invoiceNumber ? (
              <div>
                <dt>Invoice no.</dt>
                <dd>{document.invoiceNumber}</dd>
              </div>
            ) : null}
            <div>
              <dt>Period</dt>
              <dd>{formatPeriod(document.periodStart, document.periodEnd)}</dd>
            </div>
          </dl>
        </div>
      </header>

      <section className="invoice-preview__section" aria-labelledby="invoice-work-title">
        <h3 className="invoice-preview__section-title" id="invoice-work-title">
          Work performed
        </h3>
        <div className="invoice-preview__table-wrap">
          <table className="invoice-preview__table invoice-preview__work-table">
            <colgroup>
              <col className="invoice-preview__work-column" />
              <col className="invoice-preview__hours-column" />
              <col className="invoice-preview__money-column" />
              <col className="invoice-preview__money-column" />
            </colgroup>
            <thead>
              <tr>
                <th scope="col">Work category</th>
                <th scope="col">Hours</th>
                <th scope="col">Rate</th>
                <th scope="col">Amount</th>
              </tr>
            </thead>
            <tbody>
              {document.projects.map((project) => (
                <InvoiceProjectRows
                  currencyCode={document.currencyCode}
                  key={project.id}
                  project={project}
                />
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th colSpan={3} scope="row">Work performed subtotal</th>
                <td data-label="Work performed subtotal">
                  <span>{money(document.workSubtotalMinor, document.currencyCode)}</span>
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>

      <section className="invoice-preview__section" aria-labelledby="invoice-expenses-title">
        <h3 className="invoice-preview__section-title" id="invoice-expenses-title">
          Expenses
        </h3>
        <div className="invoice-preview__table-wrap">
          <table className="invoice-preview__table invoice-preview__expense-table">
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col">Project</th>
                <th scope="col">Description</th>
                <th scope="col">Amount</th>
              </tr>
            </thead>
            <tbody>
              {document.expenses.map((expense) => (
                <tr key={expense.id}>
                  <td data-label="Date"><span>{formatDate(expense.date)}</span></td>
                  <td data-label="Project">
                    <span>{expense.projectName ?? "Direct Client expense"}</span>
                  </td>
                  <td data-label="Description">
                    <span>{expense.description}</span>
                  </td>
                  <td data-label="Amount">
                    <span>{money(expense.billingAmountMinor, document.currencyCode)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th colSpan={3} scope="row">Expenses subtotal</th>
                <td data-label="Expenses subtotal">
                  <span>{money(document.expenseSubtotalMinor, document.currencyCode)}</span>
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>

      <div className="invoice-preview__closing">
        {document.paymentNote ? (
          <section className="invoice-preview__payment-note">
            <h3>Payment note</h3>
            <p>{document.paymentNote}</p>
          </section>
        ) : null}
        <dl className="invoice-preview__total">
          <dt>Total due</dt>
          <dd>{money(document.totalDueMinor, document.currencyCode)}</dd>
        </dl>
      </div>

      {showSummary ? (
        <section className="invoice-preview__summary" aria-labelledby="invoice-summary-title">
          <div className="invoice-preview__summary-header">
            <h2 id="invoice-summary-title">Work summary</h2>
            <dl className="invoice-preview__metrics">
              <div>
                <dt>Total hours</dt>
                <dd>{formatDuration(document.totalMinutes)}</dd>
              </div>
              <div>
                <dt>Active days</dt>
                <dd>{document.activeDays}</dd>
              </div>
            </dl>
          </div>
          {document.includeDailyActivity ? (
            <DailyActivityChart
              axis={document.dailyActivityAxis}
              points={document.dailyActivity}
            />
          ) : null}
          {document.includeWorkCategoryBreakdown ? (
            <WorkCategoryChart shares={document.workCategoryShares} />
          ) : null}
        </section>
      ) : null}
    </article>
  );
}

function InvoiceProjectRows({
  currencyCode,
  project,
}: {
  currencyCode: string;
  project: InvoiceDocument["projects"][number];
}) {
  return (
    <>
      <tr className="invoice-preview__project-row">
        <th colSpan={4} scope="rowgroup">{project.name}</th>
      </tr>
      {project.workLines.map((line) => (
        <tr key={line.key}>
          <td className="invoice-preview__work-label" data-label="Work category">
            <span>{line.label}</span>
          </td>
          <td data-label="Hours"><span>{formatDuration(line.minutes)}</span></td>
          <td data-label="Rate">
            <span>{line.rateMinor === null ? "—" : money(line.rateMinor, currencyCode)}</span>
          </td>
          <td data-label="Amount">
            <span>{line.amountMinor === null ? "—" : money(line.amountMinor, currencyCode)}</span>
          </td>
        </tr>
      ))}
      <tr className="invoice-preview__project-subtotal">
        <th colSpan={3} scope="row">Project subtotal</th>
        <td data-label="Project subtotal">
          <span>{money(project.subtotalMinor, currencyCode)}</span>
        </td>
      </tr>
    </>
  );
}

function money(minor: number, currencyCode: string): string {
  return formatMinorUnits(minor, currencyCode, "en");
}

function formatDuration(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
}

function formatPeriod(start: string, end: string): string {
  return `${formatDate(start)} – ${formatDate(end)}`;
}

function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return `${day} ${months[month - 1]} ${year}`;
}
