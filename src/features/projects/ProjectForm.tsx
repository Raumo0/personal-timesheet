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
import { projectCommandSchema, type Project, type ProjectCommand } from "./project";

interface ProjectFormProps {
  open: boolean;
  client: { currencyCode: string; hourlyRateMinor: number | null };
  project?: Project;
  onOpenChange: (open: boolean) => void;
  onSave: (command: ProjectCommand) => Promise<void>;
}

export function ProjectForm({ open, client, project, onOpenChange, onSave }: ProjectFormProps) {
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"inherit" | "override">("inherit");
  const [rate, setRate] = useState("");
  const [error, setError] = useState<string>();
  const nameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setName(open && project ? project.name : "");
    const override = project?.hourlyRateOverrideMinor ?? null;
    setMode(override === null ? "inherit" : "override");
    setRate(override === null ? "" : (override / 10 ** currencyFractionDigits(client.currencyCode)).toFixed(currencyFractionDigits(client.currencyCode)));
    setError(undefined);
  }, [client.currencyCode, open, project]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let hourlyRateOverrideMinor: number | null = null;
    try {
      hourlyRateOverrideMinor = mode === "inherit" ? null : parseRateToMinor(rate, client.currencyCode);
      if (mode === "override" && hourlyRateOverrideMinor === null) throw new Error("Enter an hourly rate");
      const command = projectCommandSchema.parse({ name, hourlyRateOverrideMinor });
      await onSave(command);
      onOpenChange(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Project was not saved");
      nameRef.current?.focus();
    }
  }

  const inheritedRate = formatRate(client.hourlyRateMinor, client.currencyCode);
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="sm:max-w-md">
    <DialogHeader><DialogTitle>{project ? "Edit project" : "Add project"}</DialogTitle><DialogDescription>Choose how this project gets its hourly rate.</DialogDescription></DialogHeader>
    <form id="project-form" className="grid gap-5" onSubmit={submit}>
      <div className="grid gap-2"><Label htmlFor="project-name">Project name</Label><Input id="project-name" name="projectName" ref={nameRef} value={name} onChange={(event) => setName(event.target.value)} /></div>
      <fieldset className="grid gap-3"><legend className="text-sm font-medium">Hourly rate</legend>
        <label className="flex items-center gap-2"><input type="radio" name="rate-mode" checked={mode === "inherit"} onChange={() => setMode("inherit")} /> Inherit client rate</label>
        {mode === "inherit" && <p className="text-sm text-muted-foreground">{inheritedRate ? `${inheritedRate} from client` : "No client rate is set"}</p>}
        <label className="flex items-center gap-2"><input type="radio" name="rate-mode" checked={mode === "override"} onChange={() => setMode("override")} /> Override rate</label>
        {mode === "override" && <Input aria-label="Hourly rate" inputMode="decimal" value={rate} onChange={(event) => setRate(event.target.value)} />}
      </fieldset>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </form>
    <DialogFooter><Button form="project-form" type="submit">{project ? "Save changes" : "Save project"}</Button></DialogFooter>
  </DialogContent></Dialog>;
}
