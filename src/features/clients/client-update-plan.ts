import { z } from "zod";

import {
  clientCommandSchema,
  clientRowSchema,
  normalizeClientName,
} from "./client";
import { rescaleRateOverride } from "../projects/project";

const selectedOverrideRowSchema = z.object({
  id: z.string().min(1),
  hourly_rate_override_minor: z.number().int().nonnegative(),
  updated_at: z.string().datetime(),
});

const updateTimestampSchema = z.string().datetime();

export interface ClientUpdatePlanClient {
  readonly id: string;
  readonly name: string;
  readonly normalizedName: string;
  readonly currencyCode: string;
  readonly hourlyRateMinor: number | null;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly archivedAt: string | null;
}

export interface ClientUpdatePlanOverride {
  readonly kind: "project" | "task";
  readonly id: string;
  readonly expectedHourlyRateOverrideMinor: number;
  readonly expectedUpdatedAt: string;
  readonly hourlyRateOverrideMinor: number;
}

export interface ClientUpdatePlan {
  readonly clientId: string;
  readonly expectedClient: ClientUpdatePlanClient;
  readonly client: ClientUpdatePlanClient;
  readonly overrides: readonly ClientUpdatePlanOverride[];
  readonly updatedAt: string;
}

export interface BuildClientUpdatePlanInput {
  readonly clientRow: unknown;
  readonly command: unknown;
  readonly projectRows: readonly unknown[];
  readonly taskRows: readonly unknown[];
  readonly updatedAt: string;
}

export function buildClientUpdatePlan(
  input: BuildClientUpdatePlanInput,
): ClientUpdatePlan {
  const clientRow = clientRowSchema.parse(input.clientRow);
  const command = clientCommandSchema.parse(input.command);
  const updatedAt = updateTimestampSchema.parse(input.updatedAt);

  const expectedClient: ClientUpdatePlanClient = {
    id: clientRow.id,
    name: clientRow.name,
    normalizedName: clientRow.normalized_name,
    currencyCode: clientRow.currency_code,
    hourlyRateMinor: clientRow.hourly_rate_minor,
    createdAt: clientRow.created_at,
    updatedAt: clientRow.updated_at,
    archivedAt: clientRow.archived_at,
  };
  const client: ClientUpdatePlanClient = {
    id: clientRow.id,
    name: command.name,
    normalizedName: normalizeClientName(command.name),
    currencyCode: command.currencyCode,
    hourlyRateMinor: command.hourlyRateMinor,
    createdAt: clientRow.created_at,
    updatedAt,
    archivedAt: clientRow.archived_at,
  };

  const buildOverrides = (
    kind: ClientUpdatePlanOverride["kind"],
    rows: readonly unknown[],
  ): ClientUpdatePlanOverride[] =>
    rows
      .map((inputRow) => selectedOverrideRowSchema.parse(inputRow))
      .sort((left, right) =>
        left.id < right.id ? -1 : left.id > right.id ? 1 : 0,
      )
      .map((row) => {
        const hourlyRateOverrideMinor = rescaleRateOverride(
          row.hourly_rate_override_minor,
          clientRow.currency_code,
          command.currencyCode,
        );
        if (hourlyRateOverrideMinor === null) {
          throw new Error("Selected override rate is required");
        }
        return Object.freeze({
          kind,
          id: row.id,
          expectedHourlyRateOverrideMinor: row.hourly_rate_override_minor,
          expectedUpdatedAt: row.updated_at,
          hourlyRateOverrideMinor,
        });
      });

  return Object.freeze({
    clientId: clientRow.id,
    expectedClient: Object.freeze(expectedClient),
    client: Object.freeze(client),
    overrides: Object.freeze([
      ...buildOverrides("project", input.projectRows),
      ...buildOverrides("task", input.taskRows),
    ]),
    updatedAt,
  });
}
