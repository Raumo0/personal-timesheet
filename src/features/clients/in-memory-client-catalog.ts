import {
  clientCommandSchema,
  type Client,
  type ClientCommand,
  normalizeClientName,
} from "./client";
import {
  type ClientCatalog,
  ClientCatalogError,
  type ClientList,
} from "./client-catalog";

interface InMemoryClientCatalogOptions {
  clients?: Client[];
  failure?: ClientCatalogError;
  now?: () => Date;
  createId?: () => string;
}

export class InMemoryClientCatalog implements ClientCatalog {
  private readonly clients: Client[];
  private readonly failure?: ClientCatalogError;
  private readonly now: () => Date;
  private readonly createId: () => string;

  constructor(options: InMemoryClientCatalogOptions = {}) {
    this.clients = structuredClone(options.clients ?? []);
    this.failure = options.failure;
    this.now = options.now ?? (() => new Date());
    this.createId = options.createId ?? (() => crypto.randomUUID());
  }

  async list(filter: ClientList): Promise<Client[]> {
    this.throwConfiguredFailure();
    const archived = filter === "archived";
    return structuredClone(
      this.clients.filter((client) => (client.archivedAt !== null) === archived),
    );
  }

  async create(input: ClientCommand): Promise<Client> {
    this.throwConfiguredFailure();
    const command = clientCommandSchema.parse(input);
    this.assertUniqueName(command.name);
    const now = this.now().toISOString();
    const client: Client = {
      id: this.createId(),
      ...command,
      createdAt: now,
      updatedAt: now,
      archivedAt: null,
    };
    this.clients.push(client);
    return structuredClone(client);
  }

  async update(id: string, input: ClientCommand): Promise<Client> {
    this.throwConfiguredFailure();
    const command = clientCommandSchema.parse(input);
    const client = this.clients.find(
      (candidate) => candidate.id === id && candidate.archivedAt === null,
    );
    if (!client) {
      throw new ClientCatalogError("not-found", "Client was not found");
    }
    this.assertUniqueName(command.name, id);
    Object.assign(client, command, { updatedAt: this.now().toISOString() });
    return structuredClone(client);
  }

  async archive(id: string): Promise<void> {
    this.throwConfiguredFailure();
    const client = this.clients.find(
      (candidate) => candidate.id === id && candidate.archivedAt === null,
    );
    if (!client) {
      throw new ClientCatalogError("not-found", "Client was not found");
    }
    const now = this.now().toISOString();
    client.archivedAt = now;
    client.updatedAt = now;
  }

  private assertUniqueName(name: string, excludedId?: string) {
    const normalizedName = normalizeClientName(name);
    const duplicate = this.clients.some(
      (client) =>
        client.id !== excludedId &&
        client.archivedAt === null &&
        normalizeClientName(client.name) === normalizedName,
    );
    if (duplicate) {
      throw new ClientCatalogError(
        "duplicate-name",
        "An active client already uses this name",
      );
    }
  }

  private throwConfiguredFailure() {
    if (this.failure) throw this.failure;
  }
}
