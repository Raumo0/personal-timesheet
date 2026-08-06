import type { InvoiceDocument } from "../invoice";

const dailyActivity = [
  { date: "2026-02-01", minutes: 0 },
  { date: "2026-02-02", minutes: 165 },
  { date: "2026-02-03", minutes: 300 },
  { date: "2026-02-04", minutes: 0 },
  { date: "2026-02-05", minutes: 90 },
  { date: "2026-02-06", minutes: 240 },
  { date: "2026-02-07", minutes: 0 },
];

const baseDocument: InvoiceDocument = {
  senderName: "Northstar Studio",
  recipientName: "Atlas Labs Europe",
  issueDate: "2026-02-08",
  invoiceNumber: "INV-2026-002",
  paymentNote: "Payment due within 14 days. Please quote the invoice number.",
  includeDailyActivity: true,
  includeWorkCategoryBreakdown: true,
  periodStart: "2026-02-01",
  periodEnd: "2026-02-07",
  currencyCode: "EUR",
  projects: [
    {
      id: "project-1",
      name: "International Atlas launch",
      workLines: [
        {
          key: "project-1:task-1",
          label: "Product discovery and interface architecture",
          taskId: "task-1",
          minutes: 600,
          rateMinor: 14_500,
          amountMinor: 145_000,
        },
        {
          key: "project-1:task-2",
          label: "Stakeholder alignment",
          taskId: "task-2",
          minutes: 195,
          rateMinor: 12_000,
          amountMinor: 39_000,
        },
      ],
      subtotalMinor: 184_000,
    },
  ],
  expenses: [
    {
      id: "expense-1",
      projectId: "project-1",
      projectName: "International Atlas launch",
      date: "2026-02-03",
      description: "Rail travel for the on-site discovery workshop",
      billingAmountMinor: 18_900,
    },
  ],
  workSubtotalMinor: 184_000,
  expenseSubtotalMinor: 18_900,
  totalDueMinor: 202_900,
  totalMinutes: 795,
  activeDays: 4,
  dailyActivity,
  dailyActivityAxis: {
    upperBoundHours: 6,
    ticks: [0, 1, 2, 3, 4, 5, 6],
  },
  workCategoryShares: [
    {
      projectId: "project-1",
      projectName: "International Atlas launch",
      lineKey: "project-1:task-1",
      label: "Product discovery and interface architecture",
      minutes: 600,
      share: 600 / 795,
    },
    {
      projectId: "project-1",
      projectName: "International Atlas launch",
      lineKey: "project-1:task-2",
      label: "Stakeholder alignment",
      minutes: 195,
      share: 195 / 795,
    },
  ],
  validationIssues: [],
  exportable: true,
};

const longLabel =
  "Discovery, multilingual information architecture, stakeholder alignment, accessibility review, and final interaction specifications for the international launch programme";

export function invoiceValidationDocument(caseName: string): InvoiceDocument {
  const document = structuredClone(baseDocument);
  if (caseName === "long-label") {
    document.projects[0].workLines[0].label = longLabel;
    document.workCategoryShares[0].label = longLabel;
    return document;
  }
  if (caseName === "both-charts") return document;
  if (caseName === "single-chart") {
    document.includeWorkCategoryBreakdown = false;
    return document;
  }
  if (caseName === "no-optional") {
    document.invoiceNumber = null;
    document.paymentNote = null;
    document.includeDailyActivity = false;
    document.includeWorkCategoryBreakdown = false;
    return document;
  }
  if (caseName === "multi-project") {
    document.projects.push({
      id: "project-2",
      name: "Operations portal",
      workLines: [
        {
          key: "project-2:task-1",
          label: "Service operations",
          taskId: "task-3",
          minutes: 240,
          rateMinor: 12_000,
          amountMinor: 48_000,
        },
      ],
      subtotalMinor: 48_000,
    });
    document.workSubtotalMinor += 48_000;
    document.totalDueMinor += 48_000;
    document.totalMinutes += 240;
    document.workCategoryShares = [
      ...document.workCategoryShares.map((share) => ({
        ...share,
        share: share.minutes / document.totalMinutes,
      })),
      {
        projectId: "project-2",
        projectName: "Operations portal",
        lineKey: "project-2:task-1",
        label: "Service operations",
        minutes: 240,
        share: 240 / document.totalMinutes,
      },
    ];
    return document;
  }
  if (caseName === "long-table") {
    const workLines = Array.from({ length: 48 }, (_, index) => ({
      key: `project-1:generated-${index + 1}`,
      label: `Generated work category ${String(index + 1).padStart(2, "0")} with a complete descriptive label`,
      taskId: `generated-${index + 1}`,
      minutes: 30,
      rateMinor: 12_000,
      amountMinor: 6_000,
    }));
    document.projects[0].workLines = workLines;
    document.projects[0].subtotalMinor = workLines.length * 6_000;
    document.workSubtotalMinor = workLines.length * 6_000;
    document.totalDueMinor = document.workSubtotalMinor + document.expenseSubtotalMinor;
    document.totalMinutes = workLines.length * 30;
    document.paymentNote = null;
    document.includeDailyActivity = false;
    document.includeWorkCategoryBreakdown = false;
    document.dailyActivity = [];
    document.workCategoryShares = [];
    return document;
  }
  throw new Error(`Unknown invoice preview validation case: ${caseName}`);
}
