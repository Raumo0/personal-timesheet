# Architecture-to-OpenSpec Handoff Maintainer Design

**Date:** 2026-07-30
**Status:** Implemented core
**Scope:** Provider-neutral coordinator contracts and the current GitHub adapter

This directory documents the implementation in `tools/architecture_handoff`.
Repository governance owns adoption-specific workflow and authority rules. For
package commands, see `../README.md`.

## Design Documents

| Document | Responsibility |
|---|---|
| Write Coordinator | Controlled-write models, target binding, prepare and execute internals, adapter interfaces, failure handling, and tests |
| Query Contract | Typed query purposes, predicates, lanes, normalized results, capability, and completeness |
| GitHub Adapter | Protocol labels, high-cardinality metadata, native GitHub query mapping, compatibility, and migration |
| Advanced Search Implementation Flows and Safety | Coordinator and adapter flows, failure handling, CLI presentation, validation strategy, and acceptance criteria |
| Return Channel Runtime | Documentation intake configuration, temporary target-side package distribution, agent-facing Return writes, and live round-trip validation |
| Provider Endpoint Provisioning | Role-aware setup contract, Human Gate, adapter responsibilities, style drift, and GitHub label provisioning |

## Advanced Search Context

The Architecture-to-OpenSpec handoff already supports target discovery,
compact GitHub Issue inventory, item inspection, bounded source and
correlation candidate lookup, controlled writes, duplicate preflight, Return
Item transport, and topology-aware routing.

The advanced-search rollout completes the agreed search surface for GitHub
without building a documentation-repository index. It adds typed queries for
source relations, logical targets, correlation chains, Return intake, stale
source revisions, and similarity candidates. The design preserves the
existing human gates for semantic disposition and external writes.

Current provider support is listed in
Architecture Handoff.

## Advanced Search Goals

- Define one provider-neutral query contract whose functions may have
  different support levels in different adapters.
- Map the supported functions to native GitHub Issue filters and search.
- Keep provider calls bounded and page-oriented.
- Let the agent explicitly request continuation pages and item details.
- Return enough metadata to explain searched scope, limitations, and
  completeness.
- Improve duplicate and overlap candidate retrieval without automating
  semantic disposition.
- Support on-demand Return intake, correlation reconstruction, and
  stale-revision checks.
- Preserve compatibility with existing registry, read, write, and preflight
  contracts.

## Current Design Constraints and Non-Goals

- A persisted workflow engine or authorization store inside the package.
- A durable, cached, or repository-local search index.
- Background synchronization, webhooks, scheduled polling, or session-start
  scans.
- Adapter-side scans that emulate a predicate missing from the provider.
- Local embeddings or a project-owned semantic-search model.
- Automatic duplicate, overlap, supersession, readiness, or lifecycle
  decisions, including unattended routing or implementation start.
- Automatic migration of existing GitHub Issues.
- Stable identifiers for arc42 headings or fragments.

## Advanced Search Selected Approach

The core defines typed queries and normalized results. The GitHub adapter
translates one query into one native GitHub API request and returns one
normalized page with a continuation cursor. The agent or a provider-neutral
coordinator decides whether to request another page, inspect a specific
Issue, or combine several query results.

The adapter does not maintain state between calls beyond immutable
configuration. It does not follow cursors to hide pagination, fetch all
Issues to simulate an unsupported filter, rank text with local heuristics, or
materialize reverse links.

GitHub performs lexical, semantic, or hybrid retrieval. The core preserves
provider rank and exact-match signals, deduplicates stable identities, and
reports coverage. A human reviewer decides semantic equivalence and
disposition.

## Advanced Search Component Boundaries

### Provider-Neutral Query Core

The core owns:

- query purposes and typed predicates;
- required versus advisory lanes;
- query validation and bounds;
- capability and completeness semantics;
- normalized pages and inspected protocol metadata;
- deterministic identity deduplication;
- aggregation of explicitly requested pages;
- traceability and stale-revision analysis over returned records;
- query-plan coverage used by controlled-write preflight.

The core does not own provider syntax, credentials, rate-limit policy, search
indexing, or semantic embeddings.

### Provider Adapter

An adapter:

1. declares support for each query function;
2. maps a valid query to one provider-native request;
3. normalizes one response page;
4. returns the provider cursor, searched scope, and limitations;
5. rejects malformed or ambiguous provider records.

An adapter does not claim support by scanning all work items. When the
provider cannot express a predicate, the adapter reports `partial` or
`unsupported`.

### Agent or Query Coordinator

The agent uses the core contract to:

- select query purposes and predicates;
- show the user the planned provider scope;
- request continuation pages explicitly;
- load full records after compact candidate selection;
- combine results from exact and advisory lanes;
- build a correlation view from returned forward metadata;
- compare pinned and current revisions;
- present candidate evidence and limitations;
- ask for human semantic disposition and write authorization.

The coordinator may make these operations reusable. It must expose every
provider request and continuation decision through its result record.

An explicit continuation plan contains the query, maximum pages, maximum
items, and stop conditions selected by the agent. The coordinator may follow
cursors only within that plan. It records every page request. Exhausting all
provider cursors within the plan can complete an exact lane; reaching either
bound leaves the lane partial.
