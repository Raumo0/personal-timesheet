# Provider Endpoint Provisioning

**Date:** 2026-07-31
**Status:** Implemented and live-validated
**Scope:** Provider-neutral setup contract and GitHub protocol-label rollout

Part of
Architecture-to-OpenSpec Handoff Maintainer Design.

## Problem

The registry identifies logical targets and stores, but registration does not
create provider resources. A new GitHub repository therefore lacks the labels
required for work routing, lifecycle filtering, and Return intake. Read and
write adapters currently assume that the selected provider endpoint has
already been provisioned.

Provisioning is a provider-adapter capability. Protocol meaning remains
provider-neutral; each adapter maps the required protocol classifiers to the
resources supported by its provider.

## Selected Approach

Add a separate provider-neutral `ProvisioningCoordinator` and a
`ProvisioningAdapter` contract. Do not add setup responsibilities to the
existing read or write adapters.

The coordinator owns:

- endpoint and role resolution from the registry;
- provider-neutral required classifier families and values;
- the read-only check, exact preview, fingerprint, authorization, execution,
  and readback lifecycle;
- stable classification of satisfied, missing, conflicting, and
  style-drifted resources;
- one-attempt execution and partial-success reporting.

Each provider adapter owns:

- provider resource types and API mappings;
- authentication transport;
- exact inspection and creation calls;
- provider-specific names, colors, descriptions, fields, workflows,
  templates, or schema mappings;
- capability and limitation reporting.

Two alternatives were rejected:

1. Extending the read and write adapters would mix item transport with
   repository administration and make their authorization boundaries harder
   to audit.
2. Keeping setup as manual provider scripts would duplicate protocol
   vocabulary, omit a shared Human Gate, and make new endpoint onboarding
   provider-specific from end to end.

## Role-Aware Requirements

The core derives requirements from the selected registry endpoint:

| Endpoint | Required classifier families |
|---|---|
| Implementation target | `work-route:*` and `status:*` |
| Documentation intake store | `return-kind:*` and `intake-state:*` |

The first GitHub implementation therefore provisions ten labels for an
implementation target or five labels for a documentation intake store. If one
physical repository serves both roles, running setup for both registry
endpoints produces the union. The second run is idempotent.

Registry records continue to contain logical and physical endpoint identity.
They do not duplicate provider presentation metadata or credentials.

## Setup Lifecycle

Setup is explicit and on demand. Registering an endpoint, resuming Target
Adoption, or a direct user request may trigger it. It does not run at session
start, before every query, on a schedule, or through a webhook.

### Check

The coordinator resolves one active target or store and asks its adapter to
inspect only the resources required by that endpoint role. The result records:

- exact provider scope and registry endpoint;
- every provider call;
- required resource identity;
- observed provider identity and presentation metadata;
- `satisfied`, `missing`, `conflicting`, or `style-drift` classification;
- capability, completeness, and limitations.

Check performs no provider write.

### Prepare

Prepare converts only missing resources into an ordered action list. It
returns the exact provider scope, action payloads, observations, calls,
limitations, and a deterministic content fingerprint. It also issues an
opaque preparation identity for one execution attempt. The identity does not
enter the content fingerprint. An empty action list is a successful no-op
preview. After the provider reads succeed, Prepare atomically records the
identity and fingerprint binding in the local replay ledger.

Conflicting resources block preparation. Style drift remains visible but does
not create an action. Prepare performs no provider write and does not consume
the preparation identity.

### Execute

Execute accepts the same request, approved fingerprint, opaque preparation
identity, and a non-empty approval reference. It repeats Check and Prepare,
rejects any changed fingerprint, and checks credentials against the exact
reprepared action list. This check occurs before the preparation identity is
consumed. A non-empty exact action list cannot reach a create without
credentials. An empty exact action list needs no write credential. Execute
then atomically consumes the preparation identity in an injected
provider-neutral attempt store. Consumption occurs before the first create or
no-op readback. Execute attempts each approved create action once and does not
retry.

After execution, the adapter reads every required resource back. Success
requires all required identities to be present and non-conflicting. If a
multi-action execution stops after partial success, the result reports the
actions that succeeded and the failed action. A new prepare cycle then sees
the completed subset and proposes only the remaining resources.

The receipt preserves one ordered provider call ledger. It derives the exact
sequence from the non-issuing CLI preflight Check, coordinator reprepare, each
action receipt, and full readback. Structured partial and readback failures
preserve the calls made before failure with `successful_stable_ids` and
`failed_stable_id`.

A failed first action or no-op readback still consumes the preparation
identity. A new Prepare and Human Gate may approve the same deterministic
content fingerprint with a new preparation identity.

The CLI attempt store writes a bounded replay ledger outside the repository.
Its default path is
`$XDG_STATE_HOME/architecture-handoff/provisioning-attempts-v1.json`,
or `~/.local/state/architecture-handoff/provisioning-attempts-v1.json`.
The directory uses `0700`; the ledger and lock files use `0600`. The store
uses a cross-process file lock and atomic replacement. It fails closed after
4,096 identities, after 524,288 bytes, on schema damage, or on an unsafe path.
Filesystem and lock failures become structured, token-safe store errors.
Each entry stores issued or consumed state and binds one preparation identity
to its fingerprint. The ledger contains no provider state, credentials,
action payloads, or approval references. It is not a provider-resource cache
or derived search index.

Provisioning never deletes, renames, or silently updates a provider resource.

## Style Drift Policy

The stable protocol name determines whether a resource is present. An
existing GitHub label with the exact required name satisfies setup even when
its color or description differs from the adapter default.

Color and description differences are advisory `style-drift`. They appear in
Check and Prepare output but do not block item operations and are not included
in the setup action list. Changing them requires a separate explicit preview
and authorization outside the initial provisioning flow.

A case mismatch, ambiguous identity, incompatible resource type, or provider
collision is `conflicting`, not style drift. Setup does not repair it
automatically.

## GitHub Mapping

The GitHub provisioning adapter maps each required classifier to one
repository label. Its tracked manifest owns the default name, color, and
description. Protocol enums remain the source of names; the manifest must
cover every value required by an enabled endpoint role and must not add an
undeclared protocol value.

Check uses the exact repository-label endpoint for each required name. This
bounds inspection to five calls for a documentation intake store or ten calls
for an implementation target and avoids listing or scanning unrelated labels.
A missing-label response becomes `missing`; permission, rate-limit, malformed
response, or ambiguous identity errors fail closed.

Execute creates one missing label per approved action, then performs exact
readback. It receives credentials from the process environment, including an
existing `gh auth` session. Tokens never enter the registry, preview,
fingerprint output, receipt, or logs.

The first manifest uses the live-validated Return label presentation:

| Label | Color | Description |
|---|---|---|
| `return-kind:evidence-result` | `1D76DB` | Returned evidence for validation and routing |
| `return-kind:product-gap` | `D93F0B` | Product clarification or decision required |
| `return-kind:architecture-gap` | `5319E7` | Architecture clarification or decision required |
| `intake-state:pending` | `FBCA04` | Awaiting documentation-side handling |
| `intake-state:handled` | `0E8A16` | Documentation-side follow-up completed or linked |

The implementation-target label presentation is tracked in the same adapter
manifest and follows the closed `work-route:*` and `status:*` vocabulary.

## Agent-Facing Interface

A thin agent-facing runner exposes separate commands:

```text
setup_cli prepare --registry ... (--target KEY | --store KEY)
setup_cli execute --registry ... (--target KEY | --store KEY)
  --expected-fingerprint SHA256 --preparation-id OPAQUE_ID
  --approval-reference REFERENCE
```

The runner contains no protocol decisions. It resolves configuration, invokes
the coordinator, prints compact JSON, and supplies provider credentials from
the process environment. A future skill may wrap the same package API.

## Other Providers

The shared contract does not require every provider to provision the same
resource type:

- GitLab may map classifiers to project labels.
- Jira may map them to issue types, fields, allowed values, or workflow
  states.
- Markdown may validate tracked templates and schemas without a remote write.
- An adapter may report a setup function `partial` or `unsupported` without
  making the adapter unusable for its other enabled roles.

Provider-specific setup cannot redefine protocol meaning, lifecycle,
authorization, or registry roles.

## Failure Handling

The coordinator fails closed for an unresolved or inactive endpoint, provider
mismatch, unsupported required setup capability, incomplete inspection,
conflicting resource, changed fingerprint, missing or replayed preparation
identity, attempt-ledger failure, missing approval reference, provider write
error, or readback mismatch.

No fallback scans, automatic retries, unattended writes, or credential
persistence are allowed.

## Validation

Automated validation covers:

- role-to-requirement derivation;
- immutable setup models and fingerprints;
- opaque preparation identities and cross-process replay rejection;
- read-only preparation;
- exact Human Gate binding;
- changed observation rejection;
- style drift as advisory and non-mutating;
- conflict blocking;
- partial-success resume;
- GitHub exact-name inspection, creation, and readback;
- ordered no-op, success, partial-failure, and readback-failure call ledgers;
- token-safe errors;
- target and documentation-store setup;
- copied-package provenance and cross-repository conformance.

Live GitHub validation exercised the same Check, Prepare, Execute, and readback
path against the configured documentation intake store and pilot target. The
target preparation found nine missing labels and one advisory style drift. An
authorized Execute created the nine labels and verified them by readback. A
fresh preparation produced no actions; a separately authorized no-op Execute
performed no provider write and completed exact readback.

## Non-Goals

- Implementing GitLab, Jira, or Markdown provisioning in the GitHub rollout.
- Running setup automatically at session start or before every item
  operation.
- Updating label colors or descriptions during initial provisioning.
- Deleting, renaming, or migrating existing provider resources.
- Creating a repository-local provider-resource cache or derived index.
- Replacing Target Adoption or introducing a new routine work route.
