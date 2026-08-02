import { useCallback, useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatRate, type Client } from "../clients/client";
import { resolveProjectRate, type Project, type ProjectCommand } from "./project";
import type { ProjectCatalog, ProjectList } from "./project-catalog";
import { ProjectForm } from "./ProjectForm";

interface ProjectsPageProps {
  client: Client;
  catalog: ProjectCatalog;
}

export function ProjectsPage({ client, catalog }: ProjectsPageProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [filter, setFilter] = useState<ProjectList>("active");
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setProjects(await catalog.list(client.id, filter)); } finally { setLoading(false); }
  }, [catalog, client.id, filter]);

  useEffect(() => { void load(); }, [load]);

  async function save(command: ProjectCommand) {
    await catalog.create(client.id, command);
    await load();
  }

  return <div className="flex min-h-full flex-col">
    <header className="flex items-start justify-between gap-6"><div><h1 className="text-2xl font-semibold tracking-tight">Projects</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">{client.name}</p></div><Button onClick={() => setFormOpen(true)} disabled={client.archivedAt !== null}><Plus aria-hidden="true" />Add project</Button></header>
    <div className="mt-6 inline-flex rounded-lg bg-muted p-1"><button aria-pressed={filter === "active"} className="rounded-md px-3 py-1.5 text-sm" onClick={() => setFilter("active")} type="button">Active</button><button aria-pressed={filter === "archived"} className="rounded-md px-3 py-1.5 text-sm" onClick={() => setFilter("archived")} type="button">Archived</button></div>
    {loading ? <div className="mt-6" role="status">Loading projects…</div> : projects.length === 0 ? <section className="mt-6 flex min-h-64 flex-col items-center justify-center rounded-xl border p-8 text-center"><h2 className="text-sm font-semibold">No projects yet</h2><p className="mt-1 text-xs text-muted-foreground">Add a project to assign work beneath {client.name}.</p>{filter === "active" && <Button className="mt-4" onClick={() => setFormOpen(true)} disabled={client.archivedAt !== null}>Add your first project</Button>}</section> : <ul className="mt-6 space-y-2">{projects.map((project) => { const rate = resolveProjectRate(project.hourlyRateOverrideMinor, client.hourlyRateMinor); return <li className="rounded-lg border px-4 py-3" key={project.id}><p className="font-medium">{project.name}</p><p className="text-sm text-muted-foreground">{rate.hourlyRateMinor === null ? "Rate not set" : `${formatRate(rate.hourlyRateMinor, client.currencyCode)} from ${rate.source}`}</p></li>; })}</ul>}
    <ProjectForm client={client} open={formOpen} onOpenChange={setFormOpen} onSave={save} />
  </div>;
}
