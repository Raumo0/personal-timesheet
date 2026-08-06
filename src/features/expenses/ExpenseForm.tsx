import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  convertMinorUnits,
  currencyFractionDigits,
  parseFixedScaleRate,
  parseMinorUnits,
} from "../money/money";
import {
  createExpenseCommandSchema,
  type Expense,
  type ExpenseCommand,
  type ExpenseTarget,
} from "./expense";
import type { ExpenseTargetGroup } from "./expense-store";

const currencies = ["EUR", "USD", "GBP", "HUF", "CHF", "CAD", "AUD", "JPY", "KWD"];

export interface ExpenseFormProps {
  open: boolean;
  targets: readonly ExpenseTargetGroup[];
  expense?: Expense;
  onOpenChange: (open: boolean) => void;
  onSave: (command: ExpenseCommand) => Promise<void>;
}

function targetKey(target: ExpenseTarget): string {
  return target.kind === "client"
    ? `client:${target.clientId}`
    : `project:${target.projectId}`;
}

function decodeTarget(value: string): ExpenseTarget | undefined {
  const [kind, id] = value.split(":", 2);
  if (!id) return undefined;
  if (kind === "client") return { kind, clientId: id };
  if (kind === "project") return { kind, projectId: id };
  return undefined;
}

function inputAmount(minor: number, currency: string): string {
  const digits = currencyFractionDigits(currency);
  return (minor / 10 ** digits).toFixed(digits);
}

function canonicalRate(
  originalMinor: number,
  originalCurrency: string,
  billingMinor: number,
  billingCurrency: string,
): string {
  const numerator =
    BigInt(billingMinor) * 10n ** BigInt(currencyFractionDigits(originalCurrency));
  const denominator =
    BigInt(originalMinor) * 10n ** BigInt(currencyFractionDigits(billingCurrency));
  const scale = 10n ** 12n;
  const scaled = (numerator * scale + denominator / 2n) / denominator;
  const whole = scaled / scale;
  const fraction = (scaled % scale).toString().padStart(12, "0").replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : whole.toString();
}

function billingCurrencyFor(
  targets: readonly ExpenseTargetGroup[],
  value: string,
): string | undefined {
  const target = decodeTarget(value);
  if (!target) return undefined;
  for (const group of targets) {
    if (target.kind === "client" && group.client.id === target.clientId) {
      return group.client.currencyCode;
    }
    if (
      target.kind === "project" &&
      group.projects.some((project) => project.id === target.projectId)
    ) {
      return group.client.currencyCode;
    }
  }
  return undefined;
}

function targetLabel(targets: readonly ExpenseTargetGroup[], value: string): string {
  const target = decodeTarget(value);
  if (!target) return "Choose a Client or Project";
  for (const group of targets) {
    if (target.kind === "client" && group.client.id === target.clientId) {
      return `Client · ${group.client.name}`;
    }
    const project = group.projects.find(
      (candidate) => target.kind === "project" && candidate.id === target.projectId,
    );
    if (project) return `Project · ${project.name}`;
  }
  return "Choose a Client or Project";
}

export function ExpenseForm({
  open,
  targets,
  expense,
  onOpenChange,
  onSave,
}: ExpenseFormProps) {
  const [selectedTarget, setSelectedTarget] = useState("");
  const [expenseDate, setExpenseDate] = useState("");
  const [description, setDescription] = useState("");
  const [originalCurrency, setOriginalCurrency] = useState("EUR");
  const [originalAmount, setOriginalAmount] = useState("");
  const [billingCurrency, setBillingCurrency] = useState("EUR");
  const [billingAmount, setBillingAmount] = useState("");
  const [appliedRate, setAppliedRate] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const dateRef = useRef<HTMLInputElement>(null);
  const descriptionRef = useRef<HTMLInputElement>(null);
  const amountRef = useRef<HTMLInputElement>(null);
  const rateRef = useRef<HTMLInputElement>(null);
  const billingAmountRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setSelectedTarget(open && expense ? targetKey(expense.target) : "");
    setExpenseDate(open && expense ? expense.expenseDate : "");
    setDescription(open && expense ? expense.description : "");
    setOriginalCurrency(open && expense ? expense.originalCurrencyCode : "EUR");
    setOriginalAmount(
      open && expense
        ? inputAmount(expense.originalAmountMinor, expense.originalCurrencyCode)
        : "",
    );
    setBillingCurrency(open && expense ? expense.billingCurrencyCode : "EUR");
    setBillingAmount(
      open && expense
        ? inputAmount(expense.billingAmountMinor, expense.billingCurrencyCode)
        : "",
    );
    setAppliedRate(open && expense ? expense.appliedRate : "");
    setErrors({});
    setSaveError(undefined);
    setSaving(false);
  }, [expense, open]);

  const sameCurrency = originalCurrency === billingCurrency;

  function selectTarget(value: string | null) {
    if (!value) return;
    const currency = billingCurrencyFor(targets, value);
    if (!currency) return;
    setSelectedTarget(value);
    setBillingCurrency(currency);
    setOriginalCurrency(currency);
    setAppliedRate("1");
    setBillingAmount(originalAmount);
    setErrors((current) => ({ ...current, target: "" }));
  }

  function changeOriginalCurrency(value: string | null) {
    if (!value) return;
    setOriginalCurrency(value);
    if (value === billingCurrency) {
      setAppliedRate("1");
      setBillingAmount(originalAmount);
    } else {
      setAppliedRate("");
      setBillingAmount("");
    }
  }

  function changeOriginalAmount(value: string) {
    setOriginalAmount(value);
    if (originalCurrency === billingCurrency) {
      setBillingAmount(value);
      return;
    }
    try {
      const minor = parseMinorUnits(value, originalCurrency);
      parseFixedScaleRate(appliedRate);
      const converted = convertMinorUnits(
        minor,
        originalCurrency,
        billingCurrency,
        appliedRate,
      );
      setBillingAmount(inputAmount(converted, billingCurrency));
    } catch {
      // Preserve the draft until both linked inputs are valid.
    }
  }

  function changeRate(value: string) {
    setAppliedRate(value);
    try {
      const minor = parseMinorUnits(originalAmount, originalCurrency);
      const converted = convertMinorUnits(
        minor,
        originalCurrency,
        billingCurrency,
        value,
      );
      setBillingAmount(inputAmount(converted, billingCurrency));
    } catch {
      setBillingAmount("");
    }
  }

  function changeBillingAmount(value: string) {
    setBillingAmount(value);
    try {
      const originalMinor = parseMinorUnits(originalAmount, originalCurrency);
      const billingMinor = parseMinorUnits(value, billingCurrency);
      if (originalMinor === 0 || billingMinor === 0) return;
      setAppliedRate(
        canonicalRate(
          originalMinor,
          originalCurrency,
          billingMinor,
          billingCurrency,
        ),
      );
    } catch {
      // Preserve the draft until both linked inputs are valid.
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors({});
    setSaveError(undefined);
    const nextErrors: Record<string, string> = {};
    const target = decodeTarget(selectedTarget);
    if (!target) nextErrors.target = "Choose a Client or Project";

    let originalAmountMinor = 0;
    let billingAmountMinor = 0;
    try {
      originalAmountMinor = parseMinorUnits(originalAmount, originalCurrency);
    } catch (caught) {
      nextErrors.originalAmount = caught instanceof Error ? caught.message : "Enter an amount";
    }
    if (sameCurrency) {
      billingAmountMinor = originalAmountMinor;
    } else {
      try {
        billingAmountMinor = parseMinorUnits(billingAmount, billingCurrency);
      } catch (caught) {
        nextErrors.billingAmount =
          caught instanceof Error ? caught.message : "Enter a billing amount";
      }
      try {
        parseFixedScaleRate(appliedRate);
      } catch (caught) {
        nextErrors.appliedRate = caught instanceof Error ? caught.message : "Enter an applied rate";
      }
    }

    if (!target) {
      setErrors(nextErrors);
      document.getElementById("expense-target")?.focus();
      return;
    }
    const result = createExpenseCommandSchema.safeParse({
      target,
      expenseDate,
      description,
      originalCurrencyCode: originalCurrency,
      originalAmountMinor,
      billingCurrencyCode: billingCurrency,
      billingAmountMinor,
      appliedRate: sameCurrency ? "1" : appliedRate,
      rateSource: "manual",
      rateObservedOn: null,
      rateManuallyAdjusted: false,
    });
    if (!result.success) {
      for (const issue of result.error.issues) {
        const field = String(issue.path[0]);
        nextErrors[field === "originalAmountMinor" ? "originalAmount" : field] = issue.message;
      }
    }
    if (Object.values(nextErrors).some(Boolean)) {
      setErrors(nextErrors);
      if (nextErrors.expenseDate) dateRef.current?.focus();
      else if (nextErrors.description) descriptionRef.current?.focus();
      else if (nextErrors.originalAmount) amountRef.current?.focus();
      else if (nextErrors.appliedRate) rateRef.current?.focus();
      else if (nextErrors.billingAmount) billingAmountRef.current?.focus();
      return;
    }

    setSaving(true);
    try {
      await onSave(result.data!);
      onOpenChange(false);
    } catch (caught) {
      setSaveError(caught instanceof Error ? caught.message : "Expense was not saved");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{expense ? "Edit expense" : "Add expense"}</DialogTitle>
          <DialogDescription>
            Record the original cost and the amount accepted in the Client billing currency.
          </DialogDescription>
        </DialogHeader>

        <form className="grid gap-5" id="expense-form" onSubmit={submit}>
          <div className="grid gap-2">
            <Label htmlFor="expense-target">Billing target</Label>
            <Select onValueChange={selectTarget} value={selectedTarget || null}>
              <SelectTrigger aria-describedby={errors.target ? "expense-target-error" : undefined} aria-invalid={Boolean(errors.target)} className="w-full" id="expense-target">
                <SelectValue>{targetLabel(targets, selectedTarget)}</SelectValue>
              </SelectTrigger>
              <SelectContent align="start" alignItemWithTrigger={false}>
                {targets.map((group) => (
                  <SelectGroup key={group.client.id}>
                    <SelectLabel>{group.client.name}</SelectLabel>
                    <SelectItem value={`client:${group.client.id}`}>Client · {group.client.name}</SelectItem>
                    {group.projects.map((project) => (
                      <SelectItem key={project.id} value={`project:${project.id}`}>
                        Project · {project.name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
            {errors.target ? <FieldError id="expense-target-error">{errors.target}</FieldError> : null}
          </div>

          <div className="grid grid-cols-[9rem_1fr] gap-4">
            <Field label="Expense date" error={errors.expenseDate} id="expense-date">
              <Input aria-describedby={errors.expenseDate ? "expense-date-error" : undefined} aria-invalid={Boolean(errors.expenseDate)} id="expense-date" ref={dateRef} type="date" value={expenseDate} onChange={(event) => setExpenseDate(event.target.value)} />
            </Field>
            <Field label="Description" error={errors.description} id="expense-description">
              <Input aria-describedby={errors.description ? "expense-description-error" : undefined} aria-invalid={Boolean(errors.description)} autoFocus id="expense-description" ref={descriptionRef} value={description} onChange={(event) => setDescription(event.target.value)} />
            </Field>
          </div>

          <div className="grid grid-cols-[8rem_1fr] gap-4">
            <div className="grid gap-2">
              <Label htmlFor="expense-currency">Original currency</Label>
              <Select onValueChange={changeOriginalCurrency} value={originalCurrency}>
                <SelectTrigger className="w-full" id="expense-currency"><SelectValue /></SelectTrigger>
                <SelectContent>{currencies.map((currency) => <SelectItem key={currency} value={currency}>{currency}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <Field label="Original amount" error={errors.originalAmount} id="expense-original-amount">
              <Input aria-describedby={errors.originalAmount ? "expense-original-amount-error" : undefined} aria-invalid={Boolean(errors.originalAmount)} id="expense-original-amount" inputMode="decimal" ref={amountRef} value={originalAmount} onChange={(event) => changeOriginalAmount(event.target.value)} />
            </Field>
          </div>

          {!sameCurrency ? (
            <fieldset className="grid gap-4 rounded-lg border p-3">
              <legend className="px-1 text-sm font-medium">Manual conversion</legend>
              <p className="text-xs text-muted-foreground">1 {originalCurrency} = {appliedRate || "—"} {billingCurrency}</p>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Applied rate" error={errors.appliedRate} id="expense-rate">
                  <Input aria-describedby={errors.appliedRate ? "expense-rate-error" : undefined} aria-invalid={Boolean(errors.appliedRate)} id="expense-rate" inputMode="decimal" ref={rateRef} value={appliedRate} onChange={(event) => changeRate(event.target.value)} />
                </Field>
                <Field label="Billing amount" error={errors.billingAmount} id="expense-billing-amount">
                  <Input aria-describedby={errors.billingAmount ? "expense-billing-amount-error" : undefined} aria-invalid={Boolean(errors.billingAmount)} id="expense-billing-amount" inputMode="decimal" ref={billingAmountRef} value={billingAmount} onChange={(event) => changeBillingAmount(event.target.value)} />
                </Field>
              </div>
            </fieldset>
          ) : null}

          {saveError ? <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{saveError}</p> : null}
        </form>

        <DialogFooter>
          <Button disabled={saving} form="expense-form" type="submit">
            {saving ? "Saving…" : expense ? "Save changes" : "Save expense"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  id,
  label,
  error,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? <FieldError id={`${id}-error`}>{error}</FieldError> : null}
    </div>
  );
}

function FieldError({ id, children }: { id: string; children: ReactNode }) {
  return <p aria-live="polite" className="text-xs text-destructive" id={id}>{children}</p>;
}
