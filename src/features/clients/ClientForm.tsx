import { useEffect, useRef, useState, type FormEvent } from "react";

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
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  clientCommandSchema,
  type Client,
  type ClientCommand,
  currencyFractionDigits,
  parseRateToMinor,
} from "./client";
import { ClientCatalogError } from "./client-catalog";

const currencies = ["EUR", "USD", "GBP", "HUF", "CHF", "CAD", "AUD", "JPY", "KWD"];

interface ClientFormProps {
  open: boolean;
  client?: Client;
  onOpenChange: (open: boolean) => void;
  onSave: (command: ClientCommand) => Promise<void>;
}

function rateForInput(client?: Client): string {
  if (!client || client.hourlyRateMinor === null) return "";
  const fractionDigits = currencyFractionDigits(client.currencyCode);
  return (client.hourlyRateMinor / 10 ** fractionDigits).toFixed(fractionDigits);
}

export function ClientForm({ open, client, onOpenChange, onSave }: ClientFormProps) {
  const [name, setName] = useState("");
  const [currencyCode, setCurrencyCode] = useState("EUR");
  const [rate, setRate] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const rateInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setName(open && client ? client.name : "");
    setCurrencyCode(open && client ? client.currencyCode : "EUR");
    setRate(open ? rateForInput(client) : "");
    setFieldErrors({});
    setSaveError(undefined);
    setSaving(false);
  }, [client, open]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFieldErrors({});
    setSaveError(undefined);

    let hourlyRateMinor: number | null;
    try {
      hourlyRateMinor = parseRateToMinor(rate, currencyCode);
    } catch (error) {
      setFieldErrors({
        rate: error instanceof Error ? error.message : "Enter a valid rate",
      });
      rateInputRef.current?.focus();
      return;
    }

    const result = clientCommandSchema.safeParse({
      name,
      currencyCode,
      hourlyRateMinor,
    });
    if (!result.success) {
      const errors: Record<string, string> = {};
      for (const issue of result.error.issues) {
        errors[String(issue.path[0])] = issue.message;
      }
      setFieldErrors(errors);
      if (errors.name) nameInputRef.current?.focus();
      return;
    }

    setSaving(true);
    try {
      await onSave(result.data);
      onOpenChange(false);
    } catch (error) {
      if (error instanceof ClientCatalogError && error.code === "duplicate-name") {
        setFieldErrors({ name: error.message });
        nameInputRef.current?.focus();
        return;
      }
      setSaveError(
        error instanceof Error ? error.message : "The client was not saved",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{client ? "Edit client" : "Add client"}</DialogTitle>
          <DialogDescription>
            {client
              ? "Update the billing defaults future work will inherit."
              : "Set the billing defaults that future projects can inherit."}
          </DialogDescription>
        </DialogHeader>

        <form id="client-form" className="grid gap-5" onSubmit={handleSubmit}>
          <div className="grid gap-2">
            <Label htmlFor="client-name">Client name</Label>
            <Input
              aria-describedby={fieldErrors.name ? "client-name-error" : undefined}
              aria-invalid={Boolean(fieldErrors.name)}
              autoComplete="off"
              id="client-name"
              name="clientName"
              onChange={(event) => setName(event.target.value)}
              ref={nameInputRef}
              value={name}
            />
            {fieldErrors.name && (
              <p aria-live="polite" className="text-xs text-destructive" id="client-name-error">
                {fieldErrors.name}
              </p>
            )}
          </div>

          <div className="grid grid-cols-[8rem_1fr] gap-4">
            <div className="grid gap-2">
              <Label htmlFor="client-currency">Currency</Label>
              <Select
                onValueChange={(value) => value && setCurrencyCode(value)}
                value={currencyCode}
              >
                <SelectTrigger className="w-full" id="client-currency">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {currencies.map((currency) => (
                    <SelectItem key={currency} value={currency}>
                      {currency}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="client-rate">Default hourly rate</Label>
              <Input
                aria-describedby={fieldErrors.rate ? "client-rate-help client-rate-error" : "client-rate-help"}
                aria-invalid={Boolean(fieldErrors.rate)}
                autoComplete="off"
                id="client-rate"
                inputMode="decimal"
                name="hourlyRate"
                onChange={(event) => setRate(event.target.value)}
                ref={rateInputRef}
                value={rate}
              />
              <p className="text-xs leading-5 text-muted-foreground" id="client-rate-help">
                Optional. Leave blank when no default rate applies.
              </p>
              {fieldErrors.rate && (
                <p aria-live="polite" className="text-xs text-destructive" id="client-rate-error">
                  {fieldErrors.rate}
                </p>
              )}
            </div>
          </div>

          {saveError && (
            <p className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {saveError}
            </p>
          )}
        </form>

        <DialogFooter>
          <Button disabled={saving} form="client-form" type="submit">
            {saving ? "Saving…" : client ? "Save changes" : "Save client"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
