# Advanced Search Query Contract

Part of Architecture-to-OpenSpec Handoff Maintainer Design.

## Query Model

### Query Purposes

The provider-neutral contract supports these purposes:

| Purpose | Intended result |
|---|---|
| `inventory` | Compact active or all-state work grouped by route |
| `source-traceability` | Items citing a supplied accepted source reference |
| `logical-target` | Items addressed to one logical implementation target |
| `correlation` | Items carrying one exact correlation ID |
| `return-intake` | Return Items filtered by intake state and return kind |
| `stale-revision` | Items whose returned source metadata differs from a supplied current revision |
| `similarity` | Ranked candidates for supplied capability and expected-outcome text |
| `duplicate-preflight` | A composed coverage report over required exact and advisory candidate lanes |

The contract may add a provider function later without changing these
meanings.

### Predicates

A query may contain only predicates permitted by its purpose:

- one logical target key;
- zero or more work routes;
- active-only or all-state scope;
- one exact source reference;
- one expected current revision for that source;
- one exact correlation ID;
- one intake state;
- one return kind;
- capability text;
- expected-outcome text;
- one page cursor;
- a result limit from 1 through 100.

The core rejects contradictory predicates, empty strings, invalid enums,
unbounded limits, and provider syntax passed as provider-neutral data.

### Required and Advisory Lanes

Each query-plan lane is `required` or `advisory`.

- A required lane must return `supported` capability and `complete` results
  for its declared scope before a dependent negative conclusion or external
  write can proceed.
- An advisory lane enriches candidate discovery. A partial or unsupported
  advisory result remains visible but does not invalidate a completed exact
  preflight.
- A workflow may mark similarity coverage required. In that case, partial or
  unsupported semantic results block the dependent write until the agent
  completes an explicit alternative inspection workflow.

An alternative inspection completes a required similarity lane only when it
enumerates a finite configured store, exhausts every provider cursor without
truncation, loads every eligible record, and records the inspected scope.
Sampling, a page budget reached before cursor exhaustion, or selected-record
inspection remains partial. Human acknowledgment does not upgrade partial
evidence to complete.

Advisory results never support the statement that no equivalent work exists.

## Result Model

### Capability

Each function reports:

```text
supported
partial
unsupported
```

Capability describes what the adapter can express with the configured
provider and credentials. A runtime failure does not silently change a
capability declaration.

### Completeness

Each page reports:

```text
complete
partial
unsupported
```

`complete` means complete only for the declared provider query and searched
scope. It does not mean semantic completeness across all possible work.

A page is `partial` when:

- the provider returns a continuation cursor;
- the provider reports incomplete results;
- the adapter used a documented approximate provider search;
- a configured bound truncated the provider result;
- a returned record lacks metadata required for exact verification;
- provider indexing or authorization prevents a reliable negative result.

An empty partial result is not evidence that no matching item exists.

### Normalized Search Hit

Each compact hit contains:

- provider ID and provider-qualified stable identity;
- title, URL, provider state, and last-updated value;
- protocol route or Return Item classification when available;
- applicable protocol labels;
- matched exact signals;
- provider rank position for similarity results;
- metadata-verification state;
- no full body unless the user selects the item or the query purpose requires
  exact metadata comparison.

The core deduplicates by provider-qualified identity. It preserves provider
order inside a similarity lane and places exact required matches before
advisory matches. It does not create a cross-provider semantic score.
