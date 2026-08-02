# Progressive Working Agreement Notes

This process preserves partial, human-approved agreement while a material discussion remains unresolved or continues before an implementation plan is approved. A `working-agreement-note` is a temporary local artifact. It is not a canonical decision, implementation plan, requirement, ADR, accepted architecture, research result, or authorization to cross a repository boundary.

## Activation

Use these conditions only when deciding whether to create a note:

1. The human has unambiguously approved at least one proposed point.
2. At least one other material point remains unresolved, or the conversation continues before an implementation plan is approved.

Do not start it when the human approves the complete proposal and immediately authorizes implementation, or when the human has approved nothing. Do not record secrets, credentials, or sensitive local state.

These conditions do not block later work on an existing active note. Resume a matching active note, append every newly approved point, then perform any authorized handoff, reconciliation, or closeout even after discussion has ended or the complete proposal has been approved.

## Authority Boundary

The note records the approved subset of a discussion. It does not replace the lifecycle, authority, review, or approval rules of a destination artifact. It does not grant permission for external writes, repository changes, implementation, publication, or destructive actions.

## Primary Checkout and Storage

Keep the tracked support files in the primary checkout at the repository root:

```text
working-notes/
  README.md
  TEMPLATE.md
  <active-topic>.md
```

Track `README.md` and `TEMPLATE.md` in Git. Ignore active topic notes. Tracked repository content remains English. Each active note mirrors its conversation's language, terminology, code-switching, and established expressions; it does not translate or normalize wording without a reason. Stable metadata keys may remain English for tooling.

All linked worktrees for the repository share the active-note directory in the primary checkout. Feature worktrees do not keep copies. An agent started in a linked worktree resolves the primary checkout before reading or updating a note. If it cannot identify or access that checkout, it stops and asks rather than creating another copy.

When one or more linked worktrees materially relate to a topic, add an optional `Related worktrees` section with each local path and branch. Omit it when no linked worktree applies.

An ignored note persists only in its primary local checkout. Before changing machines or clones, the human must retain that checkout or authorize promotion of its unique information to a tracked artifact.

## Capture and Amendment

- Record every unambiguously approved agreement.
- Do not record a point as approved while its acceptance is unclear or the human explicitly keeps it under discussion.
- Interpret approval semantically; do not depend on one exact phrase.
- When the human approves the unchallenged remainder of a proposal, record those points and exclude every point still under discussion.
- Append new agreement IDs at the end of the note so the latest additions remain easy to review.
- Keep each entry concise. Preserve a short exact quotation only when wording materially affects the agreement.
- Link a later entry to earlier entries when it extends, qualifies, amends, or supersedes them.

If an approved point returns to discussion, retain its recorded state until the human approves a change. Before editing an existing entry, show the exact entry, explain the reason, preview the replacement, and request explicit approval. Prefer a new `amends` or `supersedes` entry for a material semantic change. Use an approved direct edit only for a correction or clearer wording.

## Response Contract

After creating or updating a note, start the user-facing response with:

1. A compact list of new or changed agreement IDs.
2. One short sentence per ID.
3. A link to the local note.

Do not repeat the full entries in the response. The micro-summary makes persisted changes and omissions visible.

For a reconciliation-only update, list every affected Agreement ID and summarize its mapping or state change without implying that the append-only Agreement entry itself changed.

## Resume and Topic Boundaries

At the start of a relevant session, resolve the primary checkout and inspect its active local notes before reconstructing agreement from chat history. Resume the one note whose topic matches the request. If several notes may apply, ask which one to continue. If none applies, create a note when the activation conditions first become true.

Create a new note when the discussion changes to an independently plannable topic. Do not combine unrelated work only because it occurs in the same conversation.

## Reconciliation and Handoff

Reconciliation is the traceable transfer of agreements into planning, implementation, or another durable destination. It has no command keyword. Start it when the conversation semantically moves from discussion to:

- planning or documenting continuing agreements;
- implementing selected agreements;
- verifying work already performed by meaning;
- preparing a full note closeout or deletion.

Before updating reconciliation records or destination artifacts, announce that reconciliation is starting. Name whether it is a partial handoff or full closeout and identify the affected agreements.

Do not run reconciliation after every agreement append. Showing, selecting, or explaining an agreement does not authorize implementation. The note itself never grants implementation, external-write, cross-repository, publication, or destructive authority.

A request to implement or document selected agreements starts a partial handoff for that subset. Other agreements remain active. A full closeout begins only when every continuing agreement is being transferred or deliberately excluded.

Keep one mutable `Reconciliation` section before the append-only `Agreements` section in the same note. Do not create a companion reconciliation file or generator. The section contains three tables.

For authorized partial handoff, register the bounded action and every affected Agreement–Action relationship before editing a destination artifact. Use `mapped`, `in-progress`, and `planned` for pre-work records. After implementation and validation, replace them with the verified result and evidence. If the action covers only part of an unselected agreement, record that contribution without authorizing or completing its remaining work.

### Agreement Ledger

Keep exactly one row per agreement:

| Field | Contract |
|---|---|
| `Agreement` | Stable `A-NNNN` identifier |
| `Treatment` | One or more of `document`, `implement`, `constraint`, `already-covered`, `pilot-only`, or `exclude` |
| `Durable destinations` | Owning canonical documents, decisions, plans, work items, OpenSpec Changes, code, configuration, tests, or other persistent outputs |
| `Action refs` | Every local action that contributes to the agreement |
| `Evidence or exclusion reason` | Durable links and validation for verified work, or the explicit exclusion reason |
| `State` | `pending`, `mapped`, `verified`, or `excluded` |

### Action Register

Keep exactly one row per bounded local action:

| Field | Contract |
|---|---|
| `Action` | Note-local `ACT-NNNN` identifier |
| `Scope` | One bounded description of the work |
| `Durable outputs` | Persistent artifacts the action creates or changes |
| `External refs` | Native plan task, Issue, OpenSpec Change, pull request, or other execution identifiers when they exist |
| `Validation` | Required evidence that the outputs are correct |
| `State` | `planned`, `in-progress`, `done`, or `cancelled` |

`ACT-NNNN` may repeat in another note. When durable work receives a native identifier, link that identifier instead of replacing it with the local action ID.

### Coverage Matrix

Keep one row for every Agreement–Action relationship:

| Field | Contract |
|---|---|
| `Agreement` | Referenced `A-NNNN` |
| `Action` | Referenced `ACT-NNNN` |
| `Relation` | `documents`, `implements`, or `validates` |
| `Coverage` | `partial` or `complete` |
| `Contribution` | Exact part of the agreement supplied by this action |
| `Validation` | Evidence required for this relationship |
| `State` | `planned` or `verified` |

The mapping is many-to-many. One agreement may require several actions, one action may cover several agreements, and several actions may contribute to the same set of agreements. `partial` without an exact contribution is invalid.

When a new agreement is appended after reconciliation has begun, add its `pending` Agreement Ledger row. Add Action Register and Coverage Matrix rows only when a real action is mapped; do not invent an action merely to populate the tables.

Reconciliation metadata is mutable and does not amend an Agreement entry. Do not invoke the Agreement amendment Human Gate merely to update these tables.

### Durable transfer and direct implementation

A durable artifact is the persistent owner of an agreement's outcome outside the temporary note. Durable transfer means documenting or implementing the agreement there, linking the result, and recording validation evidence.

An explicit implementation request may be executed by meaning even when it does not cite an Agreement ID. At later reconciliation, use `already-covered` only after verifying the durable result and its validation. Failure to recognize the original relationship does not invalidate completed work and does not silently verify the ledger row.

## Full Closeout and Deletion

Full closeout requires every Agreement Ledger row to be `verified` or `excluded`. A verified row links its durable destination and validation evidence. An excluded row records the explicit reason. `pending` and `mapped` rows block closeout.

Delete a note only through an explicit Human Gate. Before requesting deletion, show:

- the note path;
- the durable destinations of its agreements;
- any information that would be lost;
- the reason deletion is safe.

## Validation

Before relying on this process, verify that active topic notes are ignored while `working-notes/README.md` and `working-notes/TEMPLATE.md` remain tracked. Validate interruption, partial approval, amendment, multi-note resume, language, semantic reconciliation triggers, partial handoff, many-to-many coverage, later `already-covered` detection, append-after-reconciliation, incomplete closeout, and deletion scenarios before declaring a rollout complete.
