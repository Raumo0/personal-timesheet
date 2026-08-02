# Return Channel Runtime Design

**Date:** 2026-07-31
**Status:** Implemented
**Scope:** GitHub Return Channel with provider-neutral runtime boundaries

Part of
Architecture-to-OpenSpec Handoff Maintainer Design.
Repository governance owns lifecycle authority for each adoption.

## Decision

Each adopting repository uses the same tested `tools/architecture_handoff`
package. Target-specific configuration and agent instructions remain outside
the package.

The copied package is a temporary vendored snapshot. A later change may move
the package and its agent instructions into one versioned skill or another
package distribution mechanism. That migration must preserve the protocol,
adapter boundary, Human Gates, and provider-neutral models.

The first documentation intake store uses GitHub Issues in
`example-org/example-documentation`. The store is selected through registry configuration.
GitHub is one adapter mapping, not part of Return Item semantics.

## Implemented Capability

The package already provides:

- `ReturnIntent` and provider-neutral Return Item validation;
- the `pending -> handled` intake transition;
- bounded correlation preflight;
- immutable write preparation and fingerprint-bound authorization;
- GitHub Issue create, update, and verified readback;
- read-only Return intake queries;
- automated tests with fake transports.

The documentation repository now provides:

- a registry record type and resolver for a documentation intake store;
- a stable agent-facing Return prepare and execute entry point;
- a read-only `returns --store` command for documentation intake.

The pilot target contains the tested package copy and its provenance record.
Cross-repository conformance passed, and the live Return round trip reached
`handled` through the configured documentation intake store.

These are shared runtime additions. They must not create a target-specific
fork of the protocol package.

## Package Boundary

The provider-neutral core owns:

- Return Item fields, typed relations, correlation, and lifecycle validation;
- candidate-source declarations and bounded preflight;
- prepared-write fingerprints and authorization checks;
- normalized provider readback and receipts;
- adapter interfaces and capability reporting.

A provider adapter owns:

- provider authentication and request transport;
- provider-native search, create, update, and readback mapping;
- labels, custom fields, workflow states, or frontmatter used to represent
  protocol fields;
- provider limitations and pagination.

The target integration owns:

- local agent instructions;
- selection of the logical documentation intake store;
- Return data collected from the selected Brief, referral, Spike, or Research
  Plan;
- invocation of the package prepare and execute operations.

Target code must not change protocol enums, validation, lifecycle, or
authorization behavior. Target-specific behavior belongs in configuration or
the thin agent-facing integration.

## Temporary Distribution

During this rollout:

1. Implement and test shared changes in the canonical package under
   `example-documentation/tools/architecture_handoff`.
2. Copy the complete package and its tests to
   `example-implementation/tools/architecture_handoff`.
3. Record the source repository revision and package digest beside the copied
   package.
4. Keep target configuration and instructions outside the copied directory.
5. Reject unrecorded target-local modifications to the copied package during
   conformance review.

The complete package is copied because its read, query, preflight, write, and
Return modules share models and validation. Extracting a sender-only subset
would create a second package boundary before the project has a package
distribution mechanism.

The digest hashes a versioned canonical manifest. Each manifest entry records
the sorted POSIX path, byte length, and SHA-256 of one package file.
Conformance rejects more than 4,096 visited filesystem entries, 512 included
files, 16,777,216 total bytes, or 1,048,576 bytes in one file before accepting
provenance. It prunes `__pycache__` directories and `.pyc` entries without
descending into ignored generated trees.

## Registry Model

The root registry keeps implementation targets and adds documentation intake
stores as separate record families. A store is not an implementation target
and does not receive ownership selectors, topology, or adoption state.

The first mapping is:

```json
{
  "stores": [
    {
      "key": "example-documentation-intake",
      "role": "documentation-intake",
      "provider": "github",
      "repository": "example-org/example-documentation",
      "tracker_reference": "github:example-org/example-documentation",
      "routing_status": "active"
    }
  ]
}
```

The core resolves the store by logical key and required role. It then binds
one adapter using `provider`. The GitHub adapter interprets `repository`.
Another adapter may use its own provider locator while preserving the store
key, role, Return Item model, and lifecycle.

The implementation repository keeps tracked configuration for the target and
the selected documentation intake store. It contains no credentials or local
filesystem paths.

## Runtime Policy

Query budgets and transport timeouts live in a tracked
`architecture-handoff.runtime.json` file. Registry configuration identifies
stores and targets; runtime policy limits provider work. Both repositories use
the same runtime policy during the temporary copied-package rollout.

The initial policy is:

```json
{
  "query_budgets": {
    "default": {
      "page_size": 50,
      "max_pages": 1,
      "max_items": 100
    },
    "return_correlation_fallback": {
      "page_size": 100,
      "max_pages": 1,
      "max_items": 100
    },
    "ceiling": {
      "max_pages": 20,
      "max_items": 2000
    }
  },
  "providers": {
    "github": {
      "request_timeout_seconds": 15
    }
  }
}
```

An operation may request a budget between the defaults and the configured
ceiling without changing the file. The selected budget appears in the preview
and prepared fingerprint. The write Human Gate cannot authorize a value above
the tracked ceiling. Raising that ceiling requires a separate reviewed
configuration change.

The provider adapter continues to enforce its native page-size maximum. The
runtime policy does not redefine protocol enums, lifecycle values, labels,
provider API versions, error-body bounds, or conformance file-size guards.

## GitHub Correlation Preflight

GitHub full-text Issue search is a fast candidate lookup, not complete
negative evidence. Return creation uses this sequence:

1. Search the correlation ID through the native GitHub Issue search request.
2. Stop and report a verified candidate when one is found. No Return is
   created from that incomplete lookup.
3. When search returns no verified candidate, run the configured
   `return_correlation_fallback` plan.
4. Request GitHub Issue pages filtered by `return-kind` and
   `intake-state:pending`; the agent controls continuation through the
   explicit page and item budget.
5. Parse returned protocol metadata and compare the exact correlation ID.
6. Report `complete` only after GitHub returns no continuation cursor within
   the approved budget.

Reaching either budget with a remaining cursor reports `partial` and blocks
the write. The agent may prepare a larger plan within the configured ceiling.
Exceeding the ceiling requires a reviewed runtime-policy change. The adapter
does not hide pagination, maintain an index, or create a Return after an
incomplete negative lookup.

## Agent-Facing Write Flow

The agent-facing integration exposes separate prepare and execute operations.
It does not add an unattended writer.

### Prepare

1. Resolve one active `documentation-intake` store.
2. Build and validate one `ReturnIntent`.
3. Run the fast correlation search and, when needed, the explicit bounded
   fallback in that store.
4. Stop when required coverage is incomplete.
5. Render the exact provider payload.
6. Return the target store, provider calls, candidates, limitations, payload,
   and prepared fingerprint without writing.

The agent presents this preview and requests the external-write Human Gate.

### Execute

1. Accept the same Return input, expected fingerprint, and approval reference.
2. Resolve the store and rerun the required preflight.
3. Rebuild the preview and reject a changed fingerprint.
4. Verify that the selected provider record is the same canonical Issue and
   that its immutable Return identity still matches the approved update.
5. Perform one provider write attempt.
6. Read the item back and verify its identity, URL, Return kind, intake state,
   correlation, relation, and body.
7. Return a verified receipt.

The integration performs no automatic retry. A failed or stale attempt
requires a new preview and approval.

The existing read-only CLI remains read-only. The Return writer uses a
separate agent-facing module or script so a future skill can wrap it without
changing package contracts.

## Authentication

The GitHub runtime receives `GITHUB_TOKEN` from the process environment. An
agent may derive it for one command from an existing GitHub CLI login:

```bash
GITHUB_TOKEN="$(gh auth token)" \
  python3 -m tools.architecture_handoff.return_cli ...
```

The package and registry do not store or print the token. Future adapters
provide their own credential transport without changing the Return workflow.

## Documentation-Side Intake

When the user asks about expected external results or feedback, the
documentation-side agent resolves `example-documentation-intake` and queries
pending Return Items. It reports compact counts by `return-kind`, then loads
one full item only after selection.

The read-only command resolves the store record and runtime policy:

```bash
python3 -m tools.architecture_handoff returns \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --store example-documentation-intake \
  --intake-state pending
```

After the user selects one compact Return hit, the same store binding loads
its full payload:

```bash
python3 -m tools.architecture_handoff get \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --store example-documentation-intake \
  --id <issue-number>
```

Target inventory, trace, stale-revision, similarity, and preflight commands
continue to resolve `--target`. The CLI rejects target coordinates for Return
intake.

The agent validates the selected item and routes it through the owning
research, product, architecture, or process workflow. A separate controlled
write changes `pending` to `handled` only after the durable follow-up exists
or is linked.

## Failure Handling

The runtime fails closed for:

- a missing, inactive, ambiguous, or wrong-role intake store;
- an unsupported provider adapter;
- incomplete correlation preflight;
- malformed Return data or source relation;
- a changed candidate set or prepared fingerprint;
- missing write authorization;
- provider write, readback, or payload mismatch;
- missing protocol labels in the provider;
- credentials exposed in configuration or output.

The agent reports provider limitations and does not replace a bounded query
with a hidden scan.

## Validation

Automated validation covers:

- registry parsing, role validation, and store resolution;
- backward compatibility for registries with only `targets`;
- provider-neutral Return prepare and execute flows;
- GitHub mapping for the configured documentation intake repository;
- exact preview and stale-fingerprint rejection;
- correlation duplicate detection;
- create readback and `pending -> handled` update readback;
- copied-package provenance and target conformance;
- existing package and pilot-target regression suites.

The live GitHub validation created one authorized pending Return Item in
`example-org/example-documentation`, discovered and inspected it through documentation intake,
linked the validation follow-up, and performed a separately authorized update
to `handled`. The handled Issue remains open as durable provider evidence.

## Acceptance Criteria

The completed rollout satisfies these criteria:

1. both repositories contain the same tested package revision;
2. both registries resolve the same active documentation intake store;
3. the target agent can prepare a Return without writing;
4. exact approval authorizes one verified GitHub Issue create;
5. the documentation agent discovers and inspects the pending Return;
6. a separate approval produces a verified `pending -> handled` update;
7. no credentials, local paths, provider-specific lifecycle rules, hidden
   scans, or unattended writes enter the package or registry.
