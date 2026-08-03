import type { Client, ClientCommand } from "./client";

export type ClientList = "active" | "archived";
export type ClientCatalogErrorCode =
  | "duplicate-name"
  | "not-found"
  | "persistence"
  | "invalid-data";

export class ClientCatalogError extends Error {
  public readonly cause?: unknown;

  constructor(
    public readonly code: ClientCatalogErrorCode,
    message: string,
    cause?: unknown,
  ) {
    super(message);
    this.name = "ClientCatalogError";
    this.cause = cause;
  }
}

export interface ClientCatalog {
  list(filter: ClientList): Promise<Client[]>;
  get(id: string): Promise<Client>;
  create(command: ClientCommand): Promise<Client>;
  update(id: string, command: ClientCommand): Promise<Client>;
  archive(id: string): Promise<void>;
}
