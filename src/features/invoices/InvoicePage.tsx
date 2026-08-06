import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { FileText, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { Client } from "../clients/client";
import type { ClientCatalog } from "../clients/client-catalog";
import {
  currencyFractionDigits,
  formatMinorUnits,
  parseMinorUnits,
} from "../money/money";
import type {
  InvoiceDocument,
  InvoiceExpense,
  InvoiceRequest,
  ValidationIssue,
} from "./invoice";
import type { InvoiceService } from "./invoice-service";
import { InvoicePreview } from "./InvoicePreview";

interface InvoicePageProps {
  clientCatalog: ClientCatalog;
  invoiceService: InvoiceService;
  today?: () => Date;
}

type FieldErrors = Partial<
  Record<"clientId" | "senderName" | "issueDate" | "periodStart" | "periodEnd", string>
>;

interface IssueMessages {
  fields: FieldErrors;
  lines: Record<string, string>;
  general: string[];
}

type ExportState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string };

const defaultToday = () => new Date();

function markInvoicePrintPath(preview: HTMLElement): () => void {
  const path: HTMLElement[] = [];
  let current: HTMLElement | null = preview;
  while (current) {
    path.push(current);
    if (current === globalThis.document.body) break;
    current = current.parentElement;
  }
  if (path[path.length - 1] !== globalThis.document.body) {
    throw new Error("The invoice preview is not attached to the document body");
  }

  globalThis.document.documentElement.setAttribute("data-invoice-printing", "");
  for (const element of path) {
    element.setAttribute("data-invoice-print-path", "");
  }

  return () => {
    globalThis.document.documentElement.removeAttribute("data-invoice-printing");
    for (const element of path) {
      element.removeAttribute("data-invoice-print-path");
    }
  };
}

export function InvoicePage({
  clientCatalog,
  invoiceService,
  today = defaultToday,
}: InvoicePageProps) {
  const [clients, setClients] = useState<Client[]>([]);
  const [clientStatus, setClientStatus] = useState<"loading" | "loaded" | "error">(
    "loading",
  );
  const [clientId, setClientId] = useState("");
  const [senderName, setSenderName] = useState("");
  const [issueDate, setIssueDate] = useState(() => localIsoDate(today()));
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [paymentNoteEnabled, setPaymentNoteEnabled] = useState(false);
  const [paymentNote, setPaymentNote] = useState("");
  const [includeDailyActivity, setIncludeDailyActivity] = useState(false);
  const [includeWorkCategoryBreakdown, setIncludeWorkCategoryBreakdown] =
    useState(false);
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [document, setDocument] = useState<InvoiceDocument>();
  const [preparedRequest, setPreparedRequest] = useState<InvoiceRequest>();
  const [eligibleExpenses, setEligibleExpenses] = useState<InvoiceExpense[]>([]);
  const [selectedExpenseIds, setSelectedExpenseIds] = useState<string[]>([]);
  const [rateInputs, setRateInputs] = useState<Record<string, string>>({});
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [lineErrors, setLineErrors] = useState<Record<string, string>>({});
  const [generalIssues, setGeneralIssues] = useState<string[]>([]);
  const [prepareStatus, setPrepareStatus] = useState<"idle" | "loading" | "error">(
    "idle",
  );
  const [prepareError, setPrepareError] = useState<string>();
  const [exportState, setExportState] = useState<ExportState>({ status: "idle" });
  const clientLoad = useRef(0);
  const prepareLoad = useRef(0);
  const exportLoad = useRef(0);
  const previewRef = useRef<HTMLElement>(null);
  const printCleanup = useRef<(() => void) | null>(null);

  const clearPrintMode = useCallback(() => {
    const cleanup = printCleanup.current;
    printCleanup.current = null;
    cleanup?.();
  }, []);

  const loadClients = useCallback(async () => {
    const request = ++clientLoad.current;
    setClientStatus("loading");
    try {
      const activeClients = await clientCatalog.list("active");
      if (request !== clientLoad.current) return;
      setClients(activeClients);
      setClientStatus("loaded");
    } catch {
      if (request !== clientLoad.current) return;
      setClientStatus("error");
    }
  }, [clientCatalog]);

  useEffect(() => {
    void loadClients();
  }, [loadClients]);

  useEffect(() => clearPrintMode, [clearPrintMode]);

  const selectedClient = clients.find((client) => client.id === clientId);

  function invalidatePendingPrepare() {
    prepareLoad.current += 1;
    exportLoad.current += 1;
    clearPrintMode();
    setPrepareStatus("idle");
    setPrepareError(undefined);
    setPreparedRequest(undefined);
    setExportState({ status: "idle" });
  }

  function selectClient(nextClientId: string) {
    invalidatePendingPrepare();
    setClientId(nextClientId);
    setDocument(undefined);
    setEligibleExpenses([]);
    setSelectedExpenseIds([]);
    setRateInputs({});
    clearIssues();
  }

  function changeIdentity(setter: (value: string) => void, value: string) {
    invalidatePendingPrepare();
    setter(value);
    clearIssues();
  }

  function changePeriod(setter: (value: string) => void, value: string) {
    invalidatePendingPrepare();
    setter(value);
    setDocument(undefined);
    setRateInputs({});
    clearIssues();
  }

  function clearIssues() {
    setFieldErrors({});
    setLineErrors({});
    setGeneralIssues([]);
    setPrepareError(undefined);
  }

  async function prepareInvoice() {
    clearIssues();
    const localErrors = validateConfiguration({
      clientId,
      senderName,
      issueDate,
      periodStart,
      periodEnd,
    });
    const draftRates: Record<string, number> = {};
    const invalidRates: Record<string, string> = {};
    if (document) {
      for (const project of document.projects) {
        for (const line of project.workLines) {
          try {
            draftRates[line.key] = parseMinorUnits(
              rateInputs[line.key] ?? "",
              document.currencyCode,
            );
          } catch {
            invalidRates[line.key] = "Enter a non-negative hourly rate";
          }
        }
      }
    }
    if (Object.keys(localErrors).length > 0 || Object.keys(invalidRates).length > 0) {
      setFieldErrors(localErrors);
      setLineErrors(invalidRates);
      return;
    }

    const request: InvoiceRequest = {
      clientId,
      senderName,
      issueDate,
      invoiceNumber: invoiceNumber.trim() || null,
      periodStart,
      periodEnd,
      includedExpenseIds: document ? [...selectedExpenseIds] : null,
      draftRateOverridesMinor: draftRates,
      paymentNoteEnabled,
      paymentNote,
      includeDailyActivity,
      includeWorkCategoryBreakdown,
    };
    const requestId = ++prepareLoad.current;
    exportLoad.current += 1;
    setPrepareStatus("loading");
    setPreparedRequest(undefined);
    setExportState({ status: "idle" });
    try {
      let prepared = structuredClone(await invoiceService.prepare(request));
      if (requestId !== prepareLoad.current) return;
      let authoritativeRequest = request;
      if (request.includedExpenseIds === null) {
        const discoveredExpenses = prepared.expenses;
        const reconciledExpenseIds = reconcileExpenseSelection(
          eligibleExpenses,
          selectedExpenseIds,
          discoveredExpenses,
        );
        if (reconciledExpenseIds.length !== discoveredExpenses.length) {
          authoritativeRequest = {
            ...request,
            includedExpenseIds: reconciledExpenseIds,
          };
          prepared = structuredClone(
            await invoiceService.prepare(authoritativeRequest),
          );
          if (requestId !== prepareLoad.current) return;
        }
        setEligibleExpenses(discoveredExpenses);
        setSelectedExpenseIds(reconciledExpenseIds);
      } else {
        setEligibleExpenses((current) => mergeExpenses(current, prepared.expenses));
      }
      setDocument(prepared);
      setPreparedRequest(structuredClone(authoritativeRequest));
      setPrepareStatus("idle");
      setRateInputs(rateInputsFrom(prepared));
      const messages = messagesFrom(prepared.validationIssues);
      setFieldErrors(messages.fields);
      setLineErrors(messages.lines);
      setGeneralIssues(messages.general);
    } catch (error) {
      if (requestId !== prepareLoad.current) return;
      setPrepareStatus("error");
      setPrepareError(
        error instanceof Error ? error.message : "The invoice draft could not be prepared",
      );
    }
  }

  async function exportInvoice() {
    if (!document || !preparedRequest) return;
    const requestId = ++exportLoad.current;
    const request = structuredClone(preparedRequest);
    setExportState({ status: "loading" });
    try {
      const refreshed = structuredClone(await invoiceService.prepare(request));
      if (requestId !== exportLoad.current) return;
      setDocument(refreshed);
      setRateInputs(rateInputsFrom(refreshed));
      const messages = messagesFrom(refreshed.validationIssues);
      setFieldErrors(messages.fields);
      setLineErrors(messages.lines);
      setGeneralIssues(messages.general);
      if (!refreshed.exportable || refreshed.validationIssues.length > 0) {
        setExportState({ status: "idle" });
        return;
      }

      const preview = previewRef.current;
      if (!preview) {
        throw new Error("The invoice preview is unavailable");
      }
      clearPrintMode();
      const clearMarkedPath = markInvoicePrintPath(preview);
      const handleAfterPrint = () => clearPrintMode();
      globalThis.window.addEventListener("afterprint", handleAfterPrint);
      printCleanup.current = () => {
        globalThis.window.removeEventListener("afterprint", handleAfterPrint);
        clearMarkedPath();
      };
      if (globalThis.document.fonts) {
        await globalThis.document.fonts.ready;
      }
      await nextRenderedFrame();
      if (requestId !== exportLoad.current) return;
      await invoiceService.print();
      if (requestId === exportLoad.current) {
        setExportState({ status: "idle" });
      }
    } catch {
      if (requestId !== exportLoad.current) return;
      clearPrintMode();
      setExportState({
        status: "error",
        message: "The invoice print flow could not be started. Try again.",
      });
    }
  }

  const canExport = Boolean(
    document &&
      preparedRequest &&
      document.exportable &&
      document.validationIssues.length === 0 &&
      prepareStatus !== "loading" &&
      exportState.status !== "loading",
  );

  if (clientStatus === "loading") {
    return <PageStatus>Loading clients…</PageStatus>;
  }

  if (clientStatus === "error") {
    return (
      <StateCard
        description="Your local data was not changed. Try reading it again."
        role="alert"
        title="Clients could not be loaded"
      >
        <Button onClick={() => void loadClients()} variant="outline">
          <RotateCcw aria-hidden="true" />
          Retry
        </Button>
      </StateCard>
    );
  }

  if (clients.length === 0) {
    return (
      <StateCard
        description="Add a Client with a billing currency before preparing an invoice."
        title="No active clients"
      />
    );
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="max-w-3xl">
        <p className="text-xs font-medium tracking-wide text-primary uppercase">Reports</p>
        <h1 className="mt-1 text-balance text-2xl font-semibold tracking-tight">
          Invoice generator
        </h1>
        <p className="mt-2 text-pretty text-sm leading-6 text-muted-foreground">
          Configure a transient billing draft from saved time and eligible Expenses.
        </p>
      </header>

      <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(19rem,0.85fr)_minmax(28rem,1.4fr)]">
        <form
          aria-label="Invoice configuration"
          className="rounded-xl border bg-card p-5 shadow-xs"
          onSubmit={(event) => {
            event.preventDefault();
            void prepareInvoice();
          }}
        >
          <fieldset className="space-y-4">
            <legend className="text-sm font-semibold">Document identity</legend>
            <Field label="Client" error={fieldErrors.clientId}>
              <select
                aria-describedby={fieldErrors.clientId ? "client-error" : undefined}
                aria-invalid={Boolean(fieldErrors.clientId)}
                className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                onChange={(event) => selectClient(event.target.value)}
                value={clientId}
              >
                <option value="">Choose a Client</option>
                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Sender name" error={fieldErrors.senderName}>
              <Input
                aria-describedby={fieldErrors.senderName ? "sender-name-error" : undefined}
                aria-invalid={Boolean(fieldErrors.senderName)}
                onChange={(event) =>
                  changeIdentity(setSenderName, event.target.value)
                }
                value={senderName}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Issue date" error={fieldErrors.issueDate}>
                <Input
                  aria-describedby={fieldErrors.issueDate ? "issue-date-error" : undefined}
                  aria-invalid={Boolean(fieldErrors.issueDate)}
                  onChange={(event) =>
                    changeIdentity(setIssueDate, event.target.value)
                  }
                  type="date"
                  value={issueDate}
                />
              </Field>
              <Field label="Invoice no. (optional)">
                <Input
                  onChange={(event) =>
                    changeIdentity(setInvoiceNumber, event.target.value)
                  }
                  value={invoiceNumber}
                />
              </Field>
            </div>
          </fieldset>

          <fieldset className="mt-6 space-y-4 border-t pt-5">
            <legend className="text-sm font-semibold">Inclusive billing period</legend>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Period start" error={fieldErrors.periodStart}>
                <Input
                  aria-describedby={fieldErrors.periodStart ? "period-start-error" : undefined}
                  aria-invalid={Boolean(fieldErrors.periodStart)}
                  onChange={(event) =>
                    changePeriod(setPeriodStart, event.target.value)
                  }
                  type="date"
                  value={periodStart}
                />
              </Field>
              <Field label="Period end" error={fieldErrors.periodEnd}>
                <Input
                  aria-describedby={fieldErrors.periodEnd ? "period-end-error" : undefined}
                  aria-invalid={Boolean(fieldErrors.periodEnd)}
                  onChange={(event) =>
                    changePeriod(setPeriodEnd, event.target.value)
                  }
                  type="date"
                  value={periodEnd}
                />
              </Field>
            </div>
          </fieldset>

          <fieldset className="mt-6 space-y-3 border-t pt-5">
            <legend className="text-sm font-semibold">Document customization</legend>
            <Option
              checked={paymentNoteEnabled}
              label="Include Payment note"
              onChange={(checked) => {
                invalidatePendingPrepare();
                setPaymentNoteEnabled(checked);
              }}
            />
            {paymentNoteEnabled ? (
              <Label>
                <span>Payment note text</span>
                <textarea
                  className="mt-1 min-h-20 w-full resize-y rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  onChange={(event) =>
                    changeIdentity(setPaymentNote, event.target.value)
                  }
                  value={paymentNote}
                />
              </Label>
            ) : null}
            <Option
              checked={includeDailyActivity}
              label="Include Daily activity"
              onChange={(checked) => {
                invalidatePendingPrepare();
                setIncludeDailyActivity(checked);
              }}
            />
            <Option
              checked={includeWorkCategoryBreakdown}
              label="Include Work category breakdown"
              onChange={(checked) => {
                invalidatePendingPrepare();
                setIncludeWorkCategoryBreakdown(checked);
              }}
            />
          </fieldset>

          {selectedClient ? (
            <dl className="mt-6 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 border-y py-3 text-sm">
              <dt className="text-muted-foreground">Recipient</dt>
              <dd className="font-medium">{selectedClient.name}</dd>
              <dt className="text-muted-foreground">Currency</dt>
              <dd className="font-mono text-xs font-medium">{selectedClient.currencyCode}</dd>
            </dl>
          ) : null}

          <Button className="mt-5 w-full" disabled={prepareStatus === "loading"} type="submit">
            {document ? "Refresh draft" : "Prepare invoice"}
          </Button>
          {prepareStatus === "loading" ? (
            <p className="mt-3 text-center text-xs text-muted-foreground" role="status">
              Preparing invoice…
            </p>
          ) : null}
          {prepareStatus === "error" && prepareError ? (
            <div className="mt-4 rounded-lg bg-destructive/10 p-3 text-sm text-destructive" role="alert">
              <p>{prepareError}</p>
              <Button className="mt-3" onClick={() => void prepareInvoice()} size="sm" type="button" variant="outline">
                <RotateCcw aria-hidden="true" />
                Retry
              </Button>
            </div>
          ) : null}
        </form>

        <section aria-label="Invoice draft" className="min-w-0">
          {!document ? (
            <div className="flex min-h-80 flex-col items-center justify-center rounded-xl border bg-card p-8 text-center shadow-xs">
              <div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <FileText aria-hidden="true" className="size-5" />
              </div>
              <h2 className="mt-4 text-sm font-semibold">Prepare a billing draft</h2>
              <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
                Choose a Client and inclusive period to review rates and eligible Expenses.
              </p>
            </div>
          ) : (
            <div className="space-y-5">
              <InvoicePreview document={document} previewRef={previewRef} />
              <div className="rounded-xl border bg-card p-5 shadow-xs">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-sm font-semibold">Export invoice</h2>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      Choose a local destination for the current reviewed draft.
                    </p>
                  </div>
                  <Button
                    disabled={!canExport}
                    onClick={() => void exportInvoice()}
                    type="button"
                  >
                    {exportState.status === "loading" ? "Opening print dialog…" : "Export PDF"}
                  </Button>
                </div>
                {exportState.status === "error" ? (
                  <div
                    className="mt-3 rounded-lg bg-destructive/10 p-3 text-sm text-destructive"
                    role="alert"
                  >
                    <p>{exportState.message}</p>
                    <Button
                      className="mt-3"
                      onClick={() => void exportInvoice()}
                      size="sm"
                      type="button"
                      variant="outline"
                    >
                      <RotateCcw aria-hidden="true" />
                      Retry export
                    </Button>
                  </div>
                ) : null}
              </div>
              <div className="overflow-hidden rounded-xl border bg-card shadow-xs">
                <DraftControls
                  document={document}
                  eligibleExpenses={eligibleExpenses}
                  generalIssues={generalIssues}
                  lineErrors={lineErrors}
                  onExpenseChange={(expenseId, included) => {
                    invalidatePendingPrepare();
                    setSelectedExpenseIds((current) =>
                      included
                        ? [...current.filter((id) => id !== expenseId), expenseId]
                        : current.filter((id) => id !== expenseId),
                    );
                  }}
                  onRateChange={(lineKey, value) => {
                    invalidatePendingPrepare();
                    setRateInputs((current) => ({ ...current, [lineKey]: value }));
                  }}
                  rateInputs={rateInputs}
                  selectedExpenseIds={selectedExpenseIds}
                />
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function nextRenderedFrame(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof globalThis.requestAnimationFrame === "function") {
      globalThis.requestAnimationFrame(() => resolve());
      return;
    }
    globalThis.setTimeout(resolve, 0);
  });
}

function DraftControls({
  document,
  eligibleExpenses,
  generalIssues,
  lineErrors,
  onExpenseChange,
  onRateChange,
  rateInputs,
  selectedExpenseIds,
}: {
  document: InvoiceDocument;
  eligibleExpenses: InvoiceExpense[];
  generalIssues: string[];
  lineErrors: Record<string, string>;
  onExpenseChange: (expenseId: string, included: boolean) => void;
  onRateChange: (lineKey: string, value: string) => void;
  rateInputs: Record<string, string>;
  selectedExpenseIds: string[];
}) {
  return (
    <div>
      {generalIssues.length > 0 ? (
        <div className="border-b bg-destructive/10 px-5 py-3 text-sm text-destructive" role="alert">
          {generalIssues.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      ) : null}

      <fieldset className="p-5">
        <legend className="text-sm font-semibold">Work rates</legend>
        <div className="mt-3 space-y-4">
          {document.projects.flatMap((project) =>
            project.workLines.map((line) => {
              const errorId = `rate-${line.key}-error`;
              return (
                <div className="grid gap-2 sm:grid-cols-[1fr_9rem]" key={line.key}>
                  <div>
                    <p className="text-sm font-medium">{line.label}</p>
                    <p className="text-xs text-muted-foreground">{project.name}</p>
                  </div>
                  <div>
                    <Label htmlFor={`rate-${line.key}`}>Hourly rate for {line.label}</Label>
                    <Input
                      aria-describedby={lineErrors[line.key] ? errorId : undefined}
                      aria-invalid={Boolean(lineErrors[line.key])}
                      className="mt-1 text-right font-mono tabular-nums"
                      id={`rate-${line.key}`}
                      inputMode="decimal"
                      onChange={(event) => onRateChange(line.key, event.target.value)}
                      value={rateInputs[line.key] ?? ""}
                    />
                    <p className="mt-1 text-right text-xs text-muted-foreground">
                      {document.currencyCode} per hour
                    </p>
                    {lineErrors[line.key] ? (
                      <p className="mt-1 text-xs text-destructive" id={errorId}>
                        {lineErrors[line.key]}
                      </p>
                    ) : null}
                  </div>
                </div>
              );
            }),
          )}
        </div>
      </fieldset>

      <fieldset className="border-t p-5">
        <legend className="text-sm font-semibold">Eligible Expenses</legend>
        {eligibleExpenses.length === 0 ? (
          <p className="mt-3 text-xs text-muted-foreground">No eligible Expenses in this period.</p>
        ) : (
          <div className="mt-3 space-y-3">
            {eligibleExpenses.map((expense) => (
              <label className="flex items-start gap-3 rounded-lg border p-3" key={expense.id}>
                <input
                  aria-label={`Include ${expense.description}`}
                  checked={selectedExpenseIds.includes(expense.id)}
                  className="mt-0.5 size-4 accent-primary"
                  onChange={(event) => onExpenseChange(expense.id, event.target.checked)}
                  type="checkbox"
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">{expense.description}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {formatDate(expense.date)}
                    {expense.projectName ? ` · ${expense.projectName}` : " · Direct Client expense"}
                  </span>
                </span>
                <span className="font-mono text-xs font-medium tabular-nums">
                  {formatMinorUnits(
                    expense.billingAmountMinor,
                    document.currencyCode,
                    "en",
                  )}
                </span>
              </label>
            ))}
          </div>
        )}
      </fieldset>
    </div>
  );
}

function Field({
  children,
  error,
  label,
}: {
  children: ReactElement;
  error?: string;
  label: string;
}) {
  const errorId = `${label.toLowerCase().replace(/[^a-z]+/g, "-")}-error`;
  return (
    <div>
      <Label>
        <span>{label}</span>
        <span className="mt-1 block">{children}</span>
      </Label>
      {error ? (
        <p className="mt-1 text-xs text-destructive" id={errorId}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

function Option({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        checked={checked}
        className="size-4 accent-primary"
        onChange={(event) => onChange(event.target.checked)}
        type="checkbox"
      />
      <span>{label}</span>
    </label>
  );
}

function PageStatus({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-64 items-center justify-center text-sm text-muted-foreground" role="status">
      {children}
    </div>
  );
}

function StateCard({
  children,
  description,
  role,
  title,
}: {
  children?: ReactNode;
  description: string;
  role?: "alert";
  title: string;
}) {
  return (
    <div
      className="flex min-h-64 flex-col items-center justify-center rounded-xl border bg-card p-8 text-center"
      role={role}
    >
      <h1 className="text-sm font-semibold">{title}</h1>
      <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">{description}</p>
      {children ? <div className="mt-4">{children}</div> : null}
    </div>
  );
}

function validateConfiguration(input: {
  clientId: string;
  senderName: string;
  issueDate: string;
  periodStart: string;
  periodEnd: string;
}): FieldErrors {
  const errors: FieldErrors = {};
  if (!input.clientId) errors.clientId = "Choose a Client";
  if (!input.senderName.trim()) errors.senderName = "Enter a sender name";
  if (!validIsoDate(input.issueDate)) errors.issueDate = "Enter a valid issue date";
  if (!validIsoDate(input.periodStart)) errors.periodStart = "Enter a valid start date";
  if (!validIsoDate(input.periodEnd)) errors.periodEnd = "Enter a valid end date";
  if (
    validIsoDate(input.periodStart) &&
    validIsoDate(input.periodEnd) &&
    input.periodStart > input.periodEnd
  ) {
    errors.periodStart = "Start date must be on or before end date";
  }
  return errors;
}

function messagesFrom(issues: ValidationIssue[]): IssueMessages {
  const messages: IssueMessages = { fields: {}, lines: {}, general: [] };
  for (const issue of issues) {
    if (issue.lineKey) {
      messages.lines[issue.lineKey] =
        issue.code === "missing-rate" || issue.code === "invalid-rate"
          ? "Enter a non-negative hourly rate"
          : "This work line needs attention";
      continue;
    }
    if (issue.field) {
      const field = issue.field as keyof FieldErrors;
      messages.fields[field] = fieldMessage(field, issue.code);
      continue;
    }
    const message =
      issue.code === "empty-invoice"
        ? "There is nothing to invoice for this period"
        : issue.code === "amount-overflow"
          ? "An invoice amount is too large"
          : "The invoice draft needs attention";
    if (!messages.general.includes(message)) messages.general.push(message);
  }
  return messages;
}

function fieldMessage(field: keyof FieldErrors, code: string): string {
  if (field === "senderName" && code === "required") return "Enter a sender name";
  if (field === "issueDate") return "Enter a valid issue date";
  if (field === "periodStart" && code === "invalid-period") {
    return "Start date must be on or before end date";
  }
  if (field === "periodStart") return "Enter a valid start date";
  if (field === "periodEnd") return "Enter a valid end date";
  if (field === "clientId") return "Choose an active Client";
  return "This value needs attention";
}

function mergeExpenses(current: InvoiceExpense[], next: InvoiceExpense[]): InvoiceExpense[] {
  const merged = new Map(current.map((expense) => [expense.id, expense]));
  for (const expense of next) merged.set(expense.id, expense);
  return [...merged.values()];
}

function reconcileExpenseSelection(
  previousEligible: InvoiceExpense[],
  previousSelectedIds: string[],
  nextEligible: InvoiceExpense[],
): string[] {
  const previousIds = new Set(previousEligible.map((expense) => expense.id));
  const selectedIds = new Set(previousSelectedIds);
  return nextEligible
    .filter(
      (expense) => !previousIds.has(expense.id) || selectedIds.has(expense.id),
    )
    .map((expense) => expense.id);
}

function rateInputsFrom(document: InvoiceDocument): Record<string, string> {
  return Object.fromEntries(
    document.projects.flatMap((project) =>
      project.workLines.map((line) => [
        line.key,
        line.rateMinor === null ? "" : minorInput(line.rateMinor, document.currencyCode),
      ]),
    ),
  );
}

function minorInput(minorUnits: number, currencyCode: string): string {
  const digits = currencyFractionDigits(currencyCode);
  const divisor = 10 ** digits;
  if (digits === 0) return String(minorUnits);
  return `${Math.floor(minorUnits / divisor)}.${String(minorUnits % divisor).padStart(digits, "0")}`;
}

function localIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function validIsoDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return (
    date.getUTCFullYear() === Number(match[1]) &&
    date.getUTCMonth() === Number(match[2]) - 1 &&
    date.getUTCDate() === Number(match[3])
  );
}

function formatDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  return `${day} ${months[month - 1]} ${year}`;
}
