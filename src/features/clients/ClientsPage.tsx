import { useCallback, useEffect, useRef, useState } from "react";
import { Archive, Building2, Pencil, Plus, RotateCcw } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

import type { Client, ClientCommand } from "./client";
import { formatRate } from "./client";
import type { ClientCatalog, ClientList } from "./client-catalog";
import { ClientForm } from "./ClientForm";

export function ClientsPage({ catalog }: { catalog: ClientCatalog }) {
  const [filter, setFilter] = useState<ClientList>("active");
  const [clients, setClients] = useState<Client[]>([]);
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");
  const [formOpen, setFormOpen] = useState(false);
  const [editingClient, setEditingClient] = useState<Client>();
  const [archiveClient, setArchiveClient] = useState<Client>();
  const [mutationError, setMutationError] = useState<string>();
  const loadRequest = useRef(0);

  const loadClients = useCallback(async () => {
    const request = ++loadRequest.current;
    setStatus("loading");
    try {
      const nextClients = await catalog.list(filter);
      if (request !== loadRequest.current) return;
      setClients(nextClients);
      setStatus("loaded");
    } catch {
      if (request !== loadRequest.current) return;
      setStatus("error");
    }
  }, [catalog, filter]);

  useEffect(() => {
    void loadClients();
  }, [loadClients]);

  async function saveClient(command: ClientCommand) {
    if (editingClient) {
      await catalog.update(editingClient.id, command);
    } else {
      await catalog.create(command);
    }
    await loadClients();
  }

  async function confirmArchive() {
    if (!archiveClient) return;
    setMutationError(undefined);
    try {
      await catalog.archive(archiveClient.id);
      setArchiveClient(undefined);
      await loadClients();
    } catch (error) {
      setMutationError(
        error instanceof Error ? error.message : "The client was not archived",
      );
      setArchiveClient(undefined);
    }
  }

  function openCreateForm() {
    setEditingClient(undefined);
    setFormOpen(true);
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex items-start justify-between gap-6">
        <div className="max-w-3xl">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">
            Clients
          </h1>
          <p className="mt-2 text-pretty text-sm leading-6 text-muted-foreground">
            Keep billing defaults organized before assigning projects and tasks.
          </p>
        </div>
        <Button onClick={openCreateForm}>
          <Plus aria-hidden="true" />
          Add client
        </Button>
      </header>

      <section aria-label="Client catalog" className="mt-6 overflow-hidden rounded-xl border bg-card shadow-xs">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="inline-flex rounded-lg bg-muted p-1" aria-label="Client status filter">
            {(["active", "archived"] as const).map((value) => (
              <button
                aria-pressed={filter === value}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors motion-reduce:transition-none",
                  filter === value
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
                key={value}
                onClick={() => setFilter(value)}
                type="button"
              >
                {value === "active" ? "Active" : "Archived"}
              </button>
            ))}
          </div>
          {status === "loaded" && clients.length > 0 && (
            <p className="text-xs tabular-nums text-muted-foreground">
              {clients.length} {clients.length === 1 ? "client" : "clients"}
            </p>
          )}
        </div>

        {mutationError && (
          <div className="border-b bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">
            {mutationError}
          </div>
        )}

        {status === "loading" && (
          <div className="flex min-h-64 items-center justify-center text-sm text-muted-foreground" role="status">
            Loading clients…
          </div>
        )}

        {status === "error" && (
          <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
            <p className="text-sm font-medium">Clients could not be loaded</p>
            <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
              Your local data was not changed. Try reading it again.
            </p>
            <Button className="mt-4" onClick={() => void loadClients()} variant="outline">
              <RotateCcw aria-hidden="true" />
              Retry
            </Button>
          </div>
        )}

        {status === "loaded" && clients.length === 0 && (
          <div className="flex min-h-64 flex-col items-center justify-center p-8 text-center">
            <div className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Building2 aria-hidden="true" className="size-5" />
            </div>
            <h2 className="mt-4 text-sm font-semibold">
              {filter === "active" ? "No clients yet" : "No archived clients"}
            </h2>
            <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
              {filter === "active"
                ? "Add your first client to establish its billing currency and default rate."
                : "Archived clients will remain available here for historical records."}
            </p>
            {filter === "active" && (
              <Button className="mt-4" onClick={openCreateForm} variant="outline">
                Add your first client
              </Button>
            )}
          </div>
        )}

        {status === "loaded" && clients.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-11 px-4">Client</TableHead>
                <TableHead className="h-11 w-32">Currency</TableHead>
                <TableHead className="h-11 w-48 pr-4 text-right">Default hourly rate</TableHead>
                {filter === "active" && (
                  <TableHead className="h-11 w-24 pr-4">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {clients.map((client) => {
                const rate = formatRate(client.hourlyRateMinor, client.currencyCode);
                return (
                  <TableRow key={client.id}>
                    <TableCell className="max-w-96 px-4 py-3 font-medium">
                      <a className="block truncate hover:underline" href={`#/clients/${client.id}/projects`} title={client.name}>
                        {client.name}
                      </a>
                    </TableCell>
                    <TableCell className="py-3 text-muted-foreground">{client.currencyCode}</TableCell>
                    <TableCell className="py-3 pr-4 text-right font-medium tabular-nums">
                      {rate ?? <span className="font-normal text-muted-foreground">Not set</span>}
                    </TableCell>
                    {filter === "active" && (
                      <TableCell className="py-3 pr-4">
                        <div className="flex justify-end gap-1">
                          <Button
                            aria-label={`Edit ${client.name}`}
                            onClick={() => {
                              setEditingClient(client);
                              setFormOpen(true);
                            }}
                            size="icon-sm"
                            variant="ghost"
                          >
                            <Pencil aria-hidden="true" />
                          </Button>
                          <Button
                            aria-label={`Archive ${client.name}`}
                            onClick={() => setArchiveClient(client)}
                            size="icon-sm"
                            variant="ghost"
                          >
                            <Archive aria-hidden="true" />
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </section>

      <ClientForm
        client={editingClient}
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingClient(undefined);
        }}
        onSave={saveClient}
      />

      <AlertDialog
        open={Boolean(archiveClient)}
        onOpenChange={(open) => {
          if (!open) setArchiveClient(undefined);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Archive {archiveClient?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              The client will leave the active list but remain available in archived records.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmArchive()} variant="destructive">
              Archive client
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
