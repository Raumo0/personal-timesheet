# Advanced Search GitHub Adapter

Part of Architecture-to-OpenSpec Handoff Maintainer Design.

## GitHub Protocol Metadata

### Closed Label Vocabulary

GitHub uses four independent protocol label families:

| Family | Values |
|---|---|
| `work-route:*` | `architecture-slice-handoff`, `implementation-conformance-referral`, `spike-evidence` |
| `status:*` | `draft`, `backlog`, `ready`, `in-progress`, `in-review`, `done`, `cancelled` |
| `return-kind:*` | `evidence-result`, `product-gap`, `architecture-gap` |
| `intake-state:*` | `pending`, `handled` |

The repository therefore needs at most 15 protocol label definitions. These
families do not form combined labels.

One Issue carries at most one applicable label from each family:

- an Architecture Slice Brief normally carries one route and one status;
- a Conformance Referral or Spike carries one route;
- a Return Item carries one return kind and one intake state.

Target-owned labels remain independent. The adapter preserves non-protocol
labels during controlled updates.

### High-Cardinality Metadata

The following values never become labels:

- logical target key;
- typed source relations and pinned revisions;
- correlation ID;
- capability;
- expected outcome.

They remain part of the canonical Issue payload and the existing
machine-readable `architecture-handoff-protocol` body block. The block gains
a schema version and the fields needed by the originating route. Relations
retain canonical JSON encoding.

The metadata parser treats missing fields in legacy Issues as unknown. It
does not infer a source, revision, target, capability, or outcome. A query
that requires absent metadata reports partial coverage.

The protocol block supports exact verification after retrieval. Whether
GitHub indexes a particular body fragment remains a GitHub capability and
must not be assumed by the core.

## GitHub Label Provisioning

The GitHub-only rollout maps every protocol label name to one tracked manifest
entry with a default color and description. The manifest must cover the exact
closed vocabulary above. A target endpoint selects the `work-route:*` and
`status:*` subset. A documentation intake store selects the `return-kind:*`
and `intake-state:*` subset.

Inspection uses one exact request per required label:

```text
GET /repos/{owner}/{repository}/labels/{name}
```

A missing response becomes a create action. Execute submits each approved
action once:

```text
POST /repos/{owner}/{repository}/labels
```

The request body contains only the manifest name, color, and description.
Readback repeats the exact GET mapping. The setup adapter does not list, scan,
rename, delete, or rewrite existing labels. Color or description differences
remain advisory style drift.

GitLab, Jira, and Markdown provisioning remain unsupported in this rollout.
Their future adapters may use other resource types, but cannot change role
requirements, the Prepare and Execute split, the Endpoint Setup Human Gate,
or one-attempt execution.

For a case or name conflict, the adapter preserves the safe observed label
name, color, and description as structured observation fields. It discards
unknown response fields and never serializes the raw response body.

## GitHub Query Mapping

The GitHub adapter uses native endpoints only:

| Provider-neutral function | GitHub mapping | Expected support |
|---|---|---|
| Route and lifecycle inventory | Repository Issues endpoint with `state` and `labels` | Supported, page-bounded |
| Return intake | Repository Issues endpoint with `return-kind:*` and `intake-state:*` labels | Supported, page-bounded |
| Exact source reference | Issue Search with repository, Issue type, state, and quoted body term | Partial candidate retrieval |
| Exact correlation ID | Issue Search with repository, Issue type, state, and quoted body term | Partial candidate retrieval |
| Logical target | Issue Search over the canonical target field when indexed | Partial candidate retrieval |
| Capability and expected outcome | Authenticated Issue Search with `search_type=hybrid` or `semantic` plus repository and Issue qualifiers | Advisory provider-ranked retrieval |
| Revision inequality | No single native predicate | Unsupported as one adapter query |
| Correlation graph | No native graph operation | Unsupported as one adapter query |

The agent implements stale-revision and correlation-chain workflows by
composing explicit adapter calls:

- source lookup, selected-record inspection, then revision comparison;
- correlation lookup, explicit pagination, selected-record inspection, then
  graph assembly from forward relations.

These composed workflows do not upgrade the underlying adapter capability.
Their reports state the pages and records actually inspected.

GitHub's REST Search API documents lexical, semantic, and hybrid Issue
search. Semantic and hybrid modes require authentication and have a separate
rate limit. The adapter advertises them only when its configured API version
and authentication support the function.

References:

- [REST API endpoints for search](https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests)
- [Searching issues and pull requests](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests)
- [REST API endpoints for issues](https://docs.github.com/en/rest/issues/issues)

The rollout does not depend on GitHub Issue Fields because they are not
available for user-owned repositories.

## Compatibility and Migration

- Current target registry files remain valid.
- Existing `QueryRequest`, inventory, and `get` callers keep their behavior.
- New query types may wrap or extend the current read contract without
  changing route meanings.
- Existing GitHub Issues remain readable.
- Legacy Issues missing new metadata participate only as unverified
  candidates and reduce exact-query completeness when the missing field is
  required.
- No automatic rewrite or bulk migration occurs.
- A future adapter implements the same query purposes and declares its own
  capability matrix. It may support functions that GitHub cannot express.
