# Advanced Search Implementation Flows and Safety

Part of Architecture-to-OpenSpec Handoff Maintainer Design.

This document describes coordinator and adapter execution. Repository
governance determines when those operations are authorized.

## Coordinator and Adapter Flows

### Task Inventory

1. The agent resolves one active logical target.
2. It sends an inventory query with state, route, limit, and optional cursor.
3. The adapter uses repository Issue filters and returns one compact page.
4. The agent shows category counts, category hints, completeness, and cursor.
5. The user selects a category, cursor continuation, or item.
6. Full Issue inspection occurs only after item selection.

### Return Intake

1. The agent queries `intake-state:pending` and an optional return kind.
2. The adapter uses both label filters in one native Issue request.
3. The agent presents compact counts and records.
4. The user selects one Return Item.
5. The agent loads and validates its correlation, typed source relation,
   evidence links, origin, and requested return route.
6. A separate authorized workflow creates or links the durable follow-up.
7. A separately authorized update changes `pending` to `handled`.

### Source and Correlation Traceability

1. The core creates an exact source or correlation query.
2. The adapter performs one bounded GitHub Issue Search request.
3. The agent may request more pages explicitly.
4. Selected Issues are parsed through the protocol metadata parser.
5. The agent reports verified matches, unverifiable legacy candidates,
   searched pages, and limitations.
6. Correlation-chain presentation uses only observed forward relations.

### Stale Revision Detection

1. The caller supplies one accepted source reference and its current revision.
2. The adapter performs the native source-reference query.
3. The agent explicitly requests any needed continuation pages.
4. The agent loads candidate metadata and compares each pinned revision with
   the supplied current revision.
5. The result separates current, stale, missing-revision, and malformed
   records.
6. The agent cannot claim global stale-revision coverage beyond the supplied
   source and inspected pages.

### Duplicate and Overlap Preflight

1. The coordinator builds a plan from required exact lanes and advisory
   similarity lanes.
2. Exact lanes query configured native work, OpenSpec, delivery, or Return
   intake sources as required by the write intent.
3. GitHub similarity uses capability and expected-outcome text through native
   hybrid or semantic search.
4. The core deduplicates identities and records exact signals and provider
   rank.
5. Required incomplete lanes block the dependent write.
6. Advisory limitations remain in the preview.
7. The human reviewer chooses reuse or reopen, link and narrow, supersede, or
   create distinct.
8. The prepared-write fingerprint includes the explicit continuation plan,
   coverage, candidates, disposition, payload, and target configuration.
9. Execution reruns the same fingerprinted required plan through the
   coordinator. The receipt exposes every provider call.
10. A new cursor, changed candidate set, exceeded bound, or incomplete
    provider response makes the authorization stale and blocks the write.

## Failure Handling

- Invalid provider-neutral queries fail before a provider call.
- Malformed GitHub records fail closed instead of being skipped as
  non-matches.
- Duplicate protocol labels or invalid label-family values fail inspection.
- A missing full-text match remains a partial negative result when indexing
  may be stale.
- A continuation cursor makes the current aggregate partial until the agent
  requests and incorporates the remaining pages.
- Rate limiting, missing authentication, unsupported API versions, and
  provider errors include a typed limitation without exposing credentials.
- Cross-origin redirects remain rejected.
- The adapter never converts a failed or unsupported request into an empty
  complete result.
- A partial required lane blocks the dependent external write.
- Inspection never changes lifecycle or intake state.

## CLI and Agent Presentation

Existing `list`, `get`, and bounded `search` behavior remains compatible.
The CLI adds these read-only operations:

- `returns` for intake state and return kind;
- `trace` for source or correlation lookup and explicit continuation;
- `stale` for one source and supplied current revision;
- `similarity` for capability and expected-outcome candidates;
- `preflight` for the composed exact and advisory query plan.

Every operation uses the same normalized result model. None performs a
provider write.

Compact output includes:

- target and provider;
- query purpose and predicates;
- capability and completeness;
- searched scopes and provider-call count;
- next cursor;
- limitations;
- category counts and English source hints;
- compact hits with exact signals or provider rank.

Agent guidance keeps the English source copy in tracked documentation and
presents explanations in the active conversation language.

## Test Strategy

Implementation follows TDD. Tests cover:

- query validation, enums, bounds, and required/advisory lanes;
- normalized pages, cursors, scopes, limitations, and identity deduplication;
- the 15-value closed label vocabulary and family exclusivity;
- protocol metadata rendering, parsing, legacy gaps, and round trips;
- exact GitHub Issue parameters for route, Return, source, target, and
  correlation queries;
- authenticated semantic and hybrid query parameters;
- missing authentication, rate limiting, unsupported API versions, malformed
  payloads, and incomplete provider results;
- explicit pagination and prohibition of hidden adapter scans;
- correlation assembly from observed forward relations;
- stale-revision comparison for current, stale, unknown, and malformed
  records;
- required-lane write blocking and advisory-lane disclosure;
- prepared-write invalidation when query coverage or candidates change;
- CLI compact output, drill-down, and localized agent presentation;
- backward compatibility for existing registry, read, write, renderer, and
  conformance suites.

Automated package tests use fake transports and perform no live provider
operation. No external write is required for implementation validation. A
live Issue write remains optional and requires separate exact-target,
exact-payload, operation, and cleanup-or-retention approval.

## Acceptance Criteria

The rollout is complete when:

1. all provider-neutral query purposes have typed contracts and tests;
2. the GitHub capability matrix matches native provider behavior;
3. the adapter performs no hidden scans, indexing, or local semantic
   matching;
4. exact inventory and Return filters use native GitHub labels;
5. source, target, and correlation lookup report their actual limitations;
6. GitHub-native semantic or hybrid search returns advisory ranked
   candidates when configured;
7. agent workflows reconstruct correlation and stale-revision views only
   from explicitly retrieved records;
8. required incomplete lanes block dependent writes;
9. advisory limitations remain visible through preview and readback;
10. existing tests and new search tests pass;
11. documentation and agent guidance use the same capability and
    completeness rules;
12. no derived index, polling, unattended routing, or provider-specific
    behavior in the provider-neutral core enters the change.
