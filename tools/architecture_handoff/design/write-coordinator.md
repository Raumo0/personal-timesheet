# Write Coordinator Technical Design

Part of
Architecture-to-OpenSpec Handoff Maintainer Design.

Repository governance owns workflow authority. This document describes the
package-level lifecycle and Return rules enforced by the coordinator.

## Status and Responsibility

**Status:** Implemented

The Write Coordinator adds controlled provider writes, write-gating preflight,
lifecycle mapping, Return Item transport, correlation, and readback
verification to the read-side package. Provider-neutral code owns the common
models and enforcement. The GitHub adapter maps them to GitHub Issues and
related GitHub resources.

Current provider inventory and future-adapter requirements are owned by
[[tools/architecture_handoff/README#Provider Support|Architecture Handoff —
Provider Support]]. The coordinator does not add a derived traceability index
or an unattended external-write workflow.

## Selected Approach

The package uses a provider-neutral Write Coordinator. The shorter phrase
`provider-neutral coordinator` refers to the same component.

The alternatives were:

1. Put preview, preflight, approval, and write behavior in each provider
   adapter. This duplicates protocol rules and lets providers change workflow
   meaning.
2. Keep one Write Coordinator above small provider adapters. This preserves one
   contract while allowing provider-specific mappings.
3. Build a persisted workflow engine. The package does not need durable
   orchestration, retries across sessions, or a new state store.

The selected approach is option 2.

## Target Binding

The host builds one immutable `WriteTargetConfig` from trusted target
configuration. It contains the exact active `TargetConfig` and its source
declarations. The Write Coordinator accepts only a write adapter and candidate
sources bound to that same target identity. It rejects a different logical
target, provider, repository, or source binding.

The prepared fingerprint includes the target configuration. Interaction
arguments cannot replace declarations or sources during execute. A source
declared `not-applicable` cannot have a bound adapter; an enabled source must
have one.

## Approval Enforcement

The canonical human gate is defined by the process. The package enforces it by
keeping `prepare` read-only and requiring `execute` to receive an explicit
authorization record bound to the prepared payload fingerprint.

The caller supplies an approval reference from the active interaction or host
tool. A boolean flag alone does not satisfy the interface. The coordinator
rejects a missing approval reference, fingerprint mismatch, or changed
preflight result.

One coordinator instance rejects repeated execution of the same fingerprint.
The host treats approval references as one-use across process restarts because
the package has no persistent authorization store.

## Core Types

### Write Intent

`WriteIntent` is an immutable provider-neutral request. It records:

- operation: `create` or `update`;
- logical target key;
- protocol item kind;
- canonical `work-route` when the item uses one;
- title and normalized body fields;
- current and previous lifecycle or intake state governed by the protocol;
- direct typed source relations;
- correlation ID when the route requires it;
- related work and expected links;
- provider item identity and expected provider state for an update.

The core validates route-required relations before preflight. It rejects
target-native internal work because documentation-side controlled writes do not
own that route.

### Preflight Source Declaration

Every preflight source has one kind:

```text
native-work
openspec
delivery
```

The target configuration supplied to the coordinator declares each source as:

```text
enabled
not-applicable
```

`not-applicable` requires a reason that states why the target has no applicable
source. An adapter limitation cannot use `not-applicable`.

An enabled source returns a result with:

- capability state: `supported`, `partial`, or `unsupported`;
- result completeness: `complete`, `partial`, or `unsupported`;
- searched scope;
- compact candidates;
- continuation information and limitations.

Every enabled source must return `complete` before a dependent write can
proceed. `partial` and `unsupported` block the write. A source declared
`not-applicable` does not run.

### Candidate and Human Disposition

Automation returns bounded candidates and their stable provider-qualified
identities. It does not decide semantic equivalence.

The human disposition is one of:

```text
reuse-or-reopen
link-and-narrow
supersede
create-distinct
```

`create-distinct` requires a short reason. `link-and-narrow` and `supersede`
require the selected related identities in the final intent. A changed intent
requires a new preview.

### Prepared Write

`PreparedWrite` contains:

- the immutable write-target configuration;
- the validated `WriteIntent`;
- the exact logical target;
- every preflight source declaration and result;
- compact candidate identities and relevant provider state;
- the human candidate disposition;
- the exact provider payload preview;
- a deterministic fingerprint.

The fingerprint covers the target, normalized intent, provider payload,
preflight source states, candidate identities, candidate status or revision,
and disposition. The coordinator does not persist the preview automatically.

### Authorization and Receipt

`WriteAuthorization` contains the prepared fingerprint and a non-empty approval
reference supplied by the caller.

`WriteReceipt` contains:

- operation;
- logical target and provider;
- stable provider ID and provider-qualified ID;
- resolvable URL;
- verified route, lifecycle or intake state, relations, and correlation;
- readback payload fingerprint.

The receipt reports transport evidence. It does not establish accepted product
meaning, architecture, or implementation completion.

## Adapter Contracts

### Candidate Sources

Each candidate source implements one bounded query contract. The Write
Coordinator can combine native work, OpenSpec, and delivery sources without
knowing their provider.

The GitHub adapter supplies:

- a native Issue source that includes open and closed Issues and excludes pull
  requests;
- delivery sources for related pull requests, branches, releases, and other
  configured GitHub delivery records;
- GitHub Issue create, update, and readback operations.

The adapter follows a configured request and item budget. It reports `complete`
only after it exhausts the selected scope within that budget. A continuation
cursor or provider result cap makes the result `partial` and blocks the write.

The host binds the configured OpenSpec candidate source when that source is
enabled for the target. A target without an applicable source declares it
`not-applicable` with a concrete reason. Missing adapter support does not
qualify as `not-applicable`.

### Write Adapter

The provider-neutral write adapter exposes:

```text
render_payload(intent)
create_item(payload)
update_item(provider_id, payload, expected_state)
get_item(provider_id)
normalize_readback(payload)
```

Only the adapter knows provider field names, label syntax, API paths, and native
response shapes. It does not run the human gate, choose candidate disposition,
or relax preflight.

The GitHub transport permits only the HTTPS API origin configured for the
adapter. It preserves the package timeout, same-origin redirect rule, token
validation, and token-safe errors. Controlled writes add only the required
`POST` and `PATCH` operations.

## Prepare and Execute Flow

### Prepare

1. Use one pre-resolved active logical target binding.
2. Validate the route, required relations, correlation, and initial state.
3. Resolve the declared preflight sources.
4. Run bounded candidate queries for every enabled source.
5. Stop if any enabled source is partial or unsupported.
6. Return candidates for human semantic review.
7. Apply the selected human disposition.
8. Render the exact provider payload.
9. Return `PreparedWrite` and its fingerprint without writing externally.

### Execute

1. Verify that authorization references the prepared fingerprint.
2. Re-run every enabled preflight source.
3. Re-render the provider payload.
4. Recompute the fingerprint.
5. Stop if the target, payload, candidates, provider state, or source
   completeness changed.
6. Perform one create or update operation.
7. Read the item back from the provider.
8. Compare the normalized readback with the prepared payload.
9. Return a `WriteReceipt`.

A failed write, missing readback, mismatched payload, or missing stable URL does
not produce a successful receipt. The caller may prepare again after inspecting
the failure.

## Protocol-State Enforcement

The coordinator validates Architecture Slice Brief transitions against the
canonical lifecycle. Before a GitHub update, the adapter verifies that the
current `status:*` label matches the intent's declared previous state.

A Conformance Referral or target-executed Spike uses the target's configured
initial native state. The coordinator does not manage its later target-owned
lifecycle.

Return Item creation sets `intake-state: pending`. Changing an item to
`handled` uses a separate prepared update. The core accepts only
`pending -> handled`, and the adapter verifies the provider item remains
pending before writing.

## Return Item Model

`ReturnIntent` is a specialized write intent. It requires:

- `return-kind`: `evidence-result`, `product-gap`, or `architecture-gap`;
- `intake-state: pending` for creation;
- correlation ID;
- one typed source relation to the originating Brief, referral, Spike, or
  Research Plan;
- originating target or experimental repository;
- evidence links;
- outcome, method, observations, and verification;
- produced artifacts;
- limitations and remaining unknowns;
- requested return route.

Return creation runs a bounded correlation lookup in the configured
documentation intake store. It does not run the outbound native, OpenSpec, and
delivery duplicate preflight. An incomplete correlation lookup blocks
creation. Readback verifies the return kind, intake state, correlation, source
relation, provider identity, and URL.

## Compatibility Renderer

`tools/architecture-slice-handoff/render_github_issue.py` remains a
compatibility builder. It produces a provider-neutral `WriteIntent` and
delegates GitHub rendering to the package adapter path.

The builder receives target identity through the canonical registry rather
than through Brief input or hard-coded pilot values:

`tools/architecture-slice-handoff/example-brief-input.json` is a shape-only
example. Its all-zero revision intentionally cannot pass renderer validation.
Copy it to a per-Brief working file and replace every sample identifier, path,
revision, and descriptive value with the selected Brief data before running
the builder. The prepared input is not canonical project configuration.

```bash
python3 tools/architecture-slice-handoff/render_github_issue.py \
  --docs-root . \
  --registry architecture-handoff.registry.json \
  --target example-implementation \
  --input /path/to/prepared-brief-input.json
```

The selected active target supplies the logical target, provider repository,
repository URL, and documentation repository relation. Brief input must not
repeat those configuration fields.

The compatibility path does not restore two obsolete pilot assumptions:

- a Product Requirement is not mandatory for architecture enablement, quality,
  compatibility, or migration work when the process records a justified
  not-applicable value;
- arc42 heading anchors are optional best-effort navigation hints at a pinned
  documentation revision.

The compatibility builder does not call GitHub. The Write Coordinator remains
the only controlled external-write path.

## Failure Handling

The coordinator fails closed for:

- an inactive or unresolved target;
- a missing route-required source relation;
- an invented or malformed provider identity;
- an enabled source with partial or unsupported results;
- a missing human candidate disposition;
- a missing approval reference;
- a stale prepared fingerprint;
- an invalid Brief lifecycle transition;
- a write or readback error;
- a readback mismatch;
- a cross-origin redirect or unsafe token.

Errors contain no credentials or full provider bodies. Compact preflight output
precedes any selected full-item inspection.

## Test Strategy

Unit tests cover immutable models, validation, lifecycle transitions,
fingerprints, candidate dispositions, and Return Item requirements.

Contract tests use fake candidate sources to cover all combinations of enabled,
not-applicable, complete, partial, and unsupported sources. They prove that an
incomplete enabled source blocks create and update operations.

Coordinator tests prove:

- prepare performs no external write;
- execute requires authorization bound to the exact fingerprint;
- changed candidates or payload invalidate authorization;
- semantic disposition remains a human input;
- create and update perform readback;
- mismatched readback fails closed;
- Return creation uses correlation preflight;
- Return handling uses a separate authorized update.

GitHub fixture tests cover bounded native and delivery queries, pagination,
payload rendering, `POST`, `PATCH`, readback, lifecycle labels, route labels,
same-origin redirects, and token-safe error paths.

Legacy renderer tests cover Product Requirement applicability and optional
arc42 anchors without restoring GitHub-only workflow rules.

The package, compatibility-renderer, and Working Note resolver suites remain
required regression checks.

## Implementation Map

| Responsibility | Module |
|---|---|
| Write intent and source declarations | `write_models.py` |
| Prepare, authorization, execute, and receipt | `write_coordinator.py` |
| Lifecycle validation | `lifecycle.py` |
| Return Item specialization | `return_items.py` |
| GitHub payload and write transport | `github_write.py` |
| GitHub native and delivery preflight | `github_preflight.py` |
