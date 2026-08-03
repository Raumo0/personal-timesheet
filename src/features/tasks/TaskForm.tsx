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
  currencyFractionDigits,
  formatRate,
  parseRateToMinor,
} from "../clients/client";
import { taskCommandSchema, type Task, type TaskCommand } from "./task";

interface TaskFormProps {
  open: boolean;
  client: { currencyCode: string; hourlyRateMinor: number | null };
  project: { hourlyRateOverrideMinor: number | null };
  task?: Task;
  onOpenChange: (open: boolean) => void;
  onSave: (command: TaskCommand) => Promise<void>;
}

export function TaskForm({
  open,
  client,
  project,
  task,
  onOpenChange,
  onSave,
}: TaskFormProps) {
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"inherit" | "override">("inherit");
  const [rate, setRate] = useState("");
  const [error, setError] = useState<string>();
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const override = task?.hourlyRateOverrideMinor ?? null;
    const fractionDigits = currencyFractionDigits(client.currencyCode);
    setName(open && task ? task.name : "");
    setMode(override === null ? "inherit" : "override");
    setRate(
      override === null
        ? ""
        : (override / 10 ** fractionDigits).toFixed(fractionDigits),
    );
    setError(undefined);
  }, [client.currencyCode, open, task]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      let hourlyRateOverrideMinor: number | null = null;
      if (mode === "override") {
        if (rate.trim() === "") throw new Error("Enter an hourly rate");
        if (rate.trim().startsWith("-")) {
          throw new Error("Hourly rate cannot be negative");
        }

        try {
          hourlyRateOverrideMinor = parseRateToMinor(rate, client.currencyCode);
        } catch (caught) {
          const fractionDigits = currencyFractionDigits(client.currencyCode);
          const decimals = rate.trim().replace(",", ".").split(".")[1];
          if ((decimals?.length ?? 0) > fractionDigits) {
            throw new Error("Hourly rate must use the currency's supported precision");
          }
          throw caught;
        }
      }

      const command = taskCommandSchema.parse({ name, hourlyRateOverrideMinor });
      await onSave(command);
      onOpenChange(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Task was not saved");
      nameRef.current?.focus();
    }
  }

  const inheritedMinor =
    project.hourlyRateOverrideMinor ?? client.hourlyRateMinor;
  const inheritedSource =
    project.hourlyRateOverrideMinor !== null ? "project" : "client";
  const inheritedRate = formatRate(inheritedMinor, client.currencyCode);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{task ? "Edit task" : "Add task"}</DialogTitle>
          <DialogDescription>
            Choose how this task gets its hourly rate.
          </DialogDescription>
        </DialogHeader>
        <form id="task-form" className="grid gap-5" onSubmit={submit}>
          <div className="grid gap-2">
            <Label htmlFor="task-name">Task name</Label>
            <Input
              id="task-name"
              name="taskName"
              ref={nameRef}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <fieldset className="grid gap-3">
            <legend className="text-sm font-medium">Hourly rate</legend>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="rate-mode"
                checked={mode === "inherit"}
                onChange={() => setMode("inherit")}
              />
              Inherit project rate
            </label>
            {mode === "inherit" && (
              <p className="text-sm text-muted-foreground">
                {inheritedRate
                  ? `${inheritedRate} from ${inheritedSource}`
                  : "No inherited rate is set"}
              </p>
            )}
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="rate-mode"
                checked={mode === "override"}
                onChange={() => setMode("override")}
              />
              Override rate
            </label>
            {mode === "override" && (
              <div className="flex items-center gap-2">
                <Input
                  aria-label="Hourly rate"
                  inputMode="decimal"
                  value={rate}
                  onChange={(event) => setRate(event.target.value)}
                />
                <span className="text-sm text-muted-foreground">
                  {client.currencyCode}
                </span>
              </div>
            )}
          </fieldset>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </form>
        <DialogFooter>
          <Button form="task-form" type="submit">
            {task ? "Save changes" : "Save task"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
