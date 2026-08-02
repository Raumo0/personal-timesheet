# Architecture Handoff

This package provides provider-neutral discovery and controlled-write
contracts for Architecture-to-OpenSpec handoffs.

Repository governance defines the workflow and authority rules for each
adoption. This README documents package commands and implementation behavior.

The read side supports:

- an explicit logical-target registry;
- canonical `work-route` values;
- compact task inventory across protocol and target-native work;
- one GitHub Issues adapter for bounded `list` and `get` operations;
- provider capability and query-completeness reporting;
- bounded Return intake, traceability, stale-revision, similarity, and
  duplicate-preflight plans;
- GitHub exact label filters, partial body search, and authenticated semantic
  or hybrid candidate retrieval.

The write side supports:

- immutable provider-neutral write intents;
- separate read-only prepare and authorized execute operations;
- bounded duplicate preflight across declared candidate sources;
- human candidate disposition;
- fingerprint-bound authorization;
- GitHub Issue create, update, and verified readback;
- correlated Return Item creation and intake updates.

The coordinator composes correlation views and stale-revision reports from
returned forward metadata. It uses no derived index and does not infer human
approval.

## Provider Support

The package currently ships one provider adapter: GitHub Issues. The
provider-neutral contracts allow other adapters, but do not imply that one
already exists or conforms.

Add a GitLab, Jira, Markdown, or other adapter only when a real target needs
it. That work requires a separate provider mapping, capability declaration,
permission model, lifecycle mapping, controlled-write behavior, and
conformance scope. An unavailable adapter limits operation through that
provider; it does not change the provider-neutral protocol.

## Design Documentation

Maintainers should start with `design/README.md`. It links the Write
Coordinator, query contract, GitHub adapter, endpoint provisioning contract,
and implementation-flow documentation. This README remains the package
reference for commands and behavior.

## Provision a Provider Endpoint

The root registry is an inactive example configuration. Before running any
command below, replace every example value with the intended repositories and
references, replace the vendor placeholders, review the configuration, and
change only the required endpoint records from `suspended` to `active`.

`setup_cli` provisions one active registry endpoint. The selected role fixes
the requirement set: an implementation target needs `work-route:*` and
`status:*`; a documentation intake store needs `return-kind:*` and
`intake-state:*`.

Prepare performs exact read-only inspection and prints the exact preview:

```bash
python3 -m tools.architecture_handoff.setup_cli prepare \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --target example-implementation
```

Use `--store example-documentation-intake` instead of the target argument for
the documentation intake role. Direct store setup does not create an
Architecture Slice Brief. Store setup does not create another slice artifact:

```bash
python3 -m tools.architecture_handoff.setup_cli prepare \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --store example-documentation-intake
```

The JSON contains the resolved endpoint, role-specific `requirements`,
classified `observations`, exact `provider_calls`, missing-resource `actions`,
`limitations`, advisory `style_drift`, a deterministic content `fingerprint`,
and a separate opaque `preparation_id`.
An empty `actions` list is a successful no-op. A conflicting resource blocks
Prepare. Style drift never creates a setup action.

Show the full endpoint, action payloads, limitations, fingerprint, and
`preparation_id`. Obtain the Endpoint Setup Human Gate for that exact preview.
Prepare binds the identity to the fingerprint in the local replay ledger. It
does not write to the provider.
Execute accepts the approved fingerprint and preparation identity:

```bash
GITHUB_TOKEN="$(gh auth token)" \
python3 -m tools.architecture_handoff.setup_cli execute \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --target example-implementation \
  --expected-fingerprint PREPARED_SHA256 \
  --preparation-id PREPARED_OPAQUE_ID \
  --approval-reference ENDPOINT_SETUP_HUMAN_GATE_REFERENCE
```

Execute prepares again and rejects a changed fingerprint. It then checks
credentials against that exact action list before consuming the preparation
identity or creating anything. No token is required when the exact reprepare
has no actions. It returns provider readback after any create. Its ordered
provider call ledger contains the CLI preflight Check, coordinator reprepare,
each create, and full readback. The immutable success receipt derives this
exact ledger from phase-owned calls. Structured partial and readback failures
preserve the calls made so far, `successful_stable_ids`, and
`failed_stable_id`.

Execute atomically consumes `preparation_id` before the first create or no-op
readback. It does not retry. A new Prepare and Endpoint Setup Human Gate
follows partial success, a failed first action, or a readback failure. The
content fingerprint may recur when provider state stays unchanged, but the
new preview has another preparation identity.

The CLI uses a bounded local replay ledger outside the repository:
`$XDG_STATE_HOME/architecture-handoff/provisioning-attempts-v1.json`,
or `~/.local/state/architecture-handoff/provisioning-attempts-v1.json`
when `XDG_STATE_HOME` is unset. It holds at most 4,096 identities or 524,288
bytes and fails closed at capacity. The directory uses mode `0700`; the
ledger and lock files use `0600`. Each entry stores issued or consumed state
and binds one preparation identity to its fingerprint. The ledger stores no
provider state, credentials, payloads, or approvals. It is not a
provider-resource cache or derived search index.

The runner supports the GitHub-only rollout. Run `gh auth login` and
`gh auth status`, then pass `GITHUB_TOKEN="$(gh auth token)"` to Prepare when
the repository requires authentication and to Execute. Prepare can inspect a
public repository without a token. The runner does not scan provider work
items, list unrelated labels, delete or rename resources, or rewrite style.
GitLab, Jira, and Markdown provisioning remain unsupported.

Conformance computes copied-package provenance from a versioned canonical
manifest. Each entry records its sorted POSIX path, byte length, and file
SHA-256. The package digest hashes the canonical manifest. Verification allows
at most 4,096 visited filesystem entries, 512 included files, 16,777,216 total
bytes, and 1,048,576 bytes per file. It prunes `__pycache__` directories and
`.pyc` entries before descent or inclusion.

## Controlled writes

`WriteCoordinator.prepare` validates the intent, runs every enabled preflight
source, records the human disposition, renders the exact provider payload, and
returns a deterministic fingerprint. It does not write.

The coordinator receives one immutable `WriteTargetConfig` from trusted
registry configuration, not from conversational write arguments. Work Items
bind an active implementation `TargetConfig`; Return Items bind an active
`documentation-intake` store. The write adapter and every enabled candidate
source must name the same endpoint. The fingerprint includes that binding.

`WriteCoordinator.execute` requires a non-empty approval reference bound to
that fingerprint. It repeats preflight, rejects stale candidates or payloads,
performs one provider operation, reads the item back, and verifies the
normalized result before returning a receipt.

One coordinator instance rejects a second execution of the same fingerprint.
The host must also treat approval references as one-use across process
restarts; the package does not add a persistent authorization store.

Outbound work declares `native-work`, `openspec`, and `delivery` sources. A
Return Item declares `return-intake`. Each declaration is `enabled` or
`not-applicable`; the latter requires a concrete reason. An enabled
`partial` or `unsupported` source blocks the write. It cannot be hidden by
changing its declaration to `not-applicable`. A `not-applicable` declaration
cannot have a bound source adapter.

Candidate equivalence remains a human decision:

- `reuse-or-reopen` selects existing work instead of creating;
- `link-and-narrow` creates narrower work linked to selected candidates;
- `supersede` replaces selected lifecycle-critical work;
- `create-distinct` requires a reason when candidates exist.

Return Items require a `return-kind`, exact correlation ID, one typed source
relation, evidence links, and `intake-state: pending`. A handled update is a
separate authorized transition.

The GitHub adapter supplies bounded native-Issue, pull-request, branch,
release, and Return Item candidate sources plus Issue writes. Pagination or an
exceeded item budget reports `partial` and blocks execution. The automated
tests use fake transports; they never perform a live provider write.

Documentation-side operator guidance and target-side OpenSpec intake are
published separately from this provider adapter.

## Prepare and execute a Return Item

The separate Return runner keeps preview and external mutation in different
commands. Prepare resolves the configured intake store, reports the query
budget and every provider call, completes the bounded correlation fallback,
and returns candidates, limitations, the exact provider payload, and a
fingerprint. It performs no provider write.

```bash
python3 -m tools.architecture_handoff.return_cli prepare \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --input /path/to/return-input.json
```

After reviewing that output, obtain the external-write Human Gate. Execute
repeats live preparation and accepts only the approved fingerprint:

```bash
GITHUB_TOKEN="$(gh auth token)" \
python3 -m tools.architecture_handoff.return_cli execute \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --input /path/to/return-input.json \
  --expected-fingerprint PREPARED_SHA256 \
  --approval-reference HUMAN_GATE_REFERENCE
```

The runner performs one write attempt and verifies provider readback. It does not retry.
A changed fingerprint, incomplete fallback, provider error, or readback
mismatch requires a new preparation and Human Gate. Optional
`--limit`, `--max-pages`, and `--max-items` values may raise one
operation's fallback budget only within the tracked runtime ceiling.

## GitHub conformance

Run the bounded pilot auditor against explicit documentation and target roots:

```bash
python3 -B -m tools.architecture_handoff.conformance \
  --documentation-root /path/to/documentation \
  --target-root /path/to/implementation-target \
  --working-note /path/to/working-agreement-note.md
```

The completion form requires clean Git revisions. It reads only declared
protocol surfaces and returns JSON with audited roots, revisions, dirty state,
a content digest, check count, explicit limitations, and structured findings.
Exit status is zero only when every required check passes. Use
`--allow-dirty-or-unversioned` only for fixture or exploratory runs, never for
completion evidence.

The auditor checks section-scoped route, authority, discovery, selection,
adoption, endpoint setup, Return, exact GitHub template metadata,
route-conditioned OpenSpec, the exact protocol-label manifest, and Working
Note controlled-write and extended-registry reconciliation contracts. It
performs no provider calls or writes. It checks the current GitHub adapter
mapping, not future provider adapters, and complements package tests,
target-local tests, OpenSpec validation, or human review.

## Registry

The example project registry is
[`architecture-handoff.registry.json`](../../architecture-handoff.registry.json)
in the repository root. It is intentionally suspended and must be replaced
with reviewed project routing before use. Add or change either record family
through normal Git review.

The tracked
[`architecture-handoff.runtime.json`](../../architecture-handoff.runtime.json)
owns query budgets and GitHub request timeouts. Commands require both files.
An operation may override a query budget within the tracked runtime ceiling.
Coverage that remains `partial` at the selected bound blocks a required
negative claim or controlled write.

Target keys, repository URLs, source references, and tracker references are
provider-neutral routing data. `repository` remains the adapter-native
repository reference used by the current GitHub adapter. A separate
`tracker_reference` lets a future adapter address a Jira project or another
Brief store without pretending that it is the implementation repository.

Legacy minimal registry records remain valid. Extended records may also declare:

- `repository_url` for the physical implementation repository;
- `scoped_path` for one logical target inside a monorepository;
- `source_references` for exact canonical documentation identities;
- `topology` as `repository`, `monorepo`, or `submodule`;
- `superproject_target` and `submodule_path` for a submodule target;
- `adoption_reference` and `adoption_state` as a paired provider-qualified
  reference and canonical Brief/adoption lifecycle value.

Monorepository targets require a relative `scoped_path`. Submodule targets
require an existing `superproject_target` and a relative `submodule_path`.
Registry loading rejects relationship cycles, path traversal, overlapping
`owns` and `excludes`, duplicate physical scopes, and incomplete adoption
pairs. Distinct `scoped_path` values may still represent separate logical
targets inside one physical repository or submodule.

`resolve_routed_target` requires one target to own every supplied ownership
selector and matches source-reference strings exactly. It can constrain
matching by repository and relative path, including a submodule path viewed
through its superproject. A scoped-path match must be the most specific unique
match. The resolver stops on missing criteria, partial ownership, zero
matches, multiple matches, or an ownership/exclusion conflict; it never picks
the only active target implicitly.

The current executable discovery path still accepts only active GitHub
targets. The extended registry adds no new provider adapter.

## GitHub authentication

Public repositories can be queried without authentication. For private
repositories, higher provider limits, semantic search, or controlled writes,
authenticate with GitHub CLI:

```bash
gh auth login
gh auth status
```

The package reads `GITHUB_TOKEN`; it does not silently inspect the GitHub CLI
keyring. Pass the token from the existing `gh` keyring session only to the
command process:

```bash
GITHUB_TOKEN="$(gh auth token)" \
python3 -m tools.architecture_handoff list \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --target example-implementation \
  --limit 50
```

CI may supply its existing `GITHUB_TOKEN` directly. Never print or persist the
token, and never store it in the registry.

## List available work

```bash
python3 -m tools.architecture_handoff list \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --target example-implementation \
  --limit 50
```

The result contains compact items, category counts, practical English hints, provider capabilities, searched scopes, completeness, limitations, and a continuation cursor. If `next_cursor` is present, repeat the request with `--cursor <value>`.

## Inspect one selected item

```bash
python3 -m tools.architecture_handoff get \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --target example-implementation \
  --id 1
```

`get` returns the full provider payload only after an item is selected. Provider permissions still control visibility.
Use `--store` instead of `--target` for a selected Return Item:

```bash
python3 -m tools.architecture_handoff get \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --store example-documentation-intake \
  --id 1
```

## Search by source or correlation

```bash
python3 -m tools.architecture_handoff search \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --target example-implementation \
  --correlation-id corr-12 \
  --limit 20
```

Use exactly one of `--source-reference` or `--correlation-id`. GitHub implements both through bounded provider full-text candidate retrieval, so the result reports `partial` rather than claiming exact or read-after-write-complete matching.

## Run advanced read operations

The advanced commands create an explicit bounded plan and return compact JSON.
Each provider call returns one provider page. The coordinator follows a
continuation cursor only within `--max-pages` and `--max-items`.
`--max-items` bounds raw provider records, including filtered pull requests
and duplicate records, rather than only accepted unique hits. Each reported
provider call includes its raw record count.

```bash
python3 -m tools.architecture_handoff returns \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --store example-documentation-intake \
  --return-kind evidence-result \
  --intake-state pending \
  --limit 10 \
  --max-pages 1 \
  --max-items 10
```

Use `trace` with exactly one of `--source-reference` or `--correlation-id`.
Use `stale` with one source and its full current revision. GitHub retrieves
source candidates; the coordinator compares observed revisions and reports
`current`, `stale`, `missing-revision`, or `malformed-metadata`.

```bash
python3 -m tools.architecture_handoff trace \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --target example-implementation \
  --correlation-id corr-12

python3 -m tools.architecture_handoff stale \
  --registry architecture-handoff.registry.json \
  --runtime architecture-handoff.runtime.json \
  --target example-implementation \
  --source-reference git:https://github.com/organization/documentation:architecture/09-architecture-decisions.md#adr-0003 \
  --current-revision REVISION
```

Canonical source identities use
`git:<documentation-repository>:<path>[#anchor]`. The relation target is revision-independent; the pinned revision remains only in `relation.revision`.

`similarity` uses advisory candidate enrichment. Select `--mode hybrid` or
`--mode semantic`; GitHub semantic search requires authenticated provider
support. An incomplete or unsupported advisory result cannot support a
negative duplicate claim. `preflight` requires `--source-reference`, runs that
required exact-source lane, and adds an advisory similarity lane when
`--capability` or `--expected-outcome` is supplied. It creates no authorization
and calls no write adapter.

Every advanced response includes query plans, lane requirements, capability,
completeness, searched scopes, provider calls, continuation state,
limitations, compact candidates, and any correlation or stale-revision
report. The required predicates remain separate from advisory similarity
evidence.

## Run tests

```bash
python3 -B -m unittest discover \
  -s tools/architecture_handoff/tests \
  -p 'test_*.py' \
  -v
```
