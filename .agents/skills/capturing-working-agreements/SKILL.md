---
name: capturing-working-agreements
description: Use when a human has approved part of an ongoing project discussion while another material point remains unresolved, discussion continues before implementation-plan approval, or an active Working Agreement Note needs handoff, reconciliation, or closeout.
---

# Capturing Working Agreements

## Overview

Preserve the approved subset of a continuing discussion in one temporary local note. The note records agreement; it grants no implementation, external-write, cross-repository, publication, or integration authority.

## Initial Capture Gate

Create a note only when:

1. at least one point is unambiguously approved; and
2. another material point remains unresolved, or discussion continues before an implementation plan is approved.

Do not activate when nothing is approved. Do not activate when the complete proposal is approved with immediate implementation authority.

Interpret approval by meaning, not phrase matching. Record only approved points; keep disputed or unclear points out of the Agreements section.
When the human approves the unchallenged remainder by meaning, enumerate and capture every identifiable unchallenged point while excluding all points still questioned, criticized, or awaiting replacement.
Never record secrets, credentials, or sensitive local state.

This gate does not block later work on an existing active note. Resume a matching note and append every newly approved point before handoff, reconciliation, or closeout, including a final approval that ends discussion.

## Workflow

1. Resolve the current checkout root before locating any support file:

   ```bash
   git rev-parse --show-toplevel
   ```

   Stop if this fails. Copy its absolute output. In every later tool call, replace `<checkout-root>` with that exact absolute path; never rely on a shell variable set by an earlier call. Read `<checkout-root>/processes/progressive-working-agreement-notes.md` completely when present; it is authoritative over this summary.
2. Resolve storage through the checkout-root copy of the resolver:

   ```bash
   python3 "<checkout-root>/tools/working-notes/resolve_primary_checkout.py" --repository "<checkout-root>"
   ```

   Substitute the absolute output before executing; never run the literal placeholder. Stop and ask for help if the script is absent, fails, returns an inaccessible path, or does not identify one primary checkout. Never substitute the current worktree for the resolver's output.
3. Inspect active `working-notes/*.md` files in that primary checkout, excluding `README.md` and `TEMPLATE.md`. Resume the matching topic. If two or more notes plausibly match, name them and stop for the human to choose. If none matches, determine the exact candidate path under `working-notes/`; do not create it yet.
4. When discussion changes to an independently plannable topic, determine a separate candidate path. Never combine unrelated work merely because it occurs in one conversation. Do not create or update a note in this step.
5. Before **any** topic-note write, verify the selected matching path or exact candidate path is ignored by Git and that `working-notes/README.md` and `working-notes/TEMPLATE.md` are tracked support files. Stop if this storage contract is not satisfied. Never stage or commit an active topic note.
6. Only after step 5 passes, create a new candidate from `working-notes/TEMPLATE.md`; otherwise update the selected matching note. Write only under the resolved primary checkout. Mirror the conversation's language, terminology, and code-switching. When linked worktrees materially relate, include a `Related worktrees` section with each local path and branch; otherwise omit it.
7. Append one concise entry per approved agreement. Use the next chronological `A-NNNN` ID after the note's highest ID. Never reuse, reorder, or silently rewrite an ID. Link an entry it amends or supersedes.
8. After any note change, begin the response with the changed IDs, one short sentence per ID, then an absolute local Markdown link to the note. Continue the discussion only after this micro-summary.

Example response opening:

```text
- A-0004 — The release gate remains manual.

[Working Agreement Note](/absolute/primary/working-notes/release.md)
```

For a reconciliation-only update, list the affected Agreement IDs and summarize their mapping or state changes. Do not imply that the append-only Agreement entries changed.

## Reconciliation Workflow

Reconcile when the request semantically moves from discussion to planning, implementation, durable transfer, full closeout, or deletion. There is no required keyword. Do not reconcile after every append. Showing, selecting, or explaining an agreement grants no implementation authority.

An explicit request to document or implement selected agreements starts partial handoff for that subset. Leave other agreements active. Full closeout starts only when every continuing agreement is being transferred or deliberately excluded.

Before updating the note or any destination artifact, announce that reconciliation is starting. Name `partial handoff` or `full closeout` and list the affected Agreement IDs.

At the first reconciliation trigger, create or populate one mutable `Reconciliation` section before append-only `Agreements` in the same note. Never create a companion file or generator. Reconciliation-table updates are not Agreement edits and do not use the Agreement amendment Human Gate.

For an authorized partial handoff, this order is mandatory:

1. Before editing a destination artifact, register the selected work as a bounded action. Set the action `in-progress`, affected ledger rows `mapped`, and relationships `planned`.
2. Implement only the authorized scope.
3. Validate the durable outputs.
4. Set the action `done`, verified relationships `verified`, and covered ledger rows to their evidence-backed result.

If one action also satisfies part of an unselected agreement, map that exact partial contribution without treating the agreement's remaining work as authorized or complete.

Never defer step 1 until after implementation. Urgency, a small change, or an intention to add evidence later does not bypass the pre-work mapping.

Maintain exactly these tables:

| Table | One row per | Required fields and values |
|---|---|---|
| Agreement Ledger | Agreement | `Agreement`; one or more `Treatment` values from `document`, `implement`, `constraint`, `already-covered`, `pilot-only`, `exclude`; `Durable destinations`; all `Action refs`; `Evidence or exclusion reason`; `State` from `pending`, `mapped`, `verified`, `excluded` |
| Action Register | Bounded action | note-local `Action` as `ACT-NNNN`; `Scope`; `Durable outputs`; `External refs`; `Validation`; `State` from `planned`, `in-progress`, `done`, `cancelled` |
| Coverage Matrix | Agreement–Action relationship | `Agreement`; `Action`; `Relation` from `documents`, `implements`, `validates`; `Coverage` from `partial`, `complete`; exact `Contribution`; `Validation`; `State` from `planned`, `verified` |

The mapping is many-to-many. One agreement may require several actions, one action may cover several agreements, and several actions may contribute to the same agreements. Never record `partial` without its exact contribution. `ACT-NNNN` is local to one note; link any native plan, Issue, OpenSpec Change, pull request, or other execution ID through `External refs`.

A durable destination is the persistent owner of the outcome outside the temporary note. Mark an agreement `verified` only after linking its durable result and validation evidence. Mark it `excluded` only with an explicit reason.

If work was implemented directly by meaning without citing an Agreement ID, verify the durable result and its validation before using `already-covered`. Missing original traceability does not invalidate completed work and does not silently verify the ledger.

New approvals after reconciliation continue at the end of `Agreements`. Add a `pending` ledger row. Add action and coverage rows only after mapping real work; never invent an action for a newly appended agreement.

Full closeout requires every Agreement Ledger row to be `verified` or `excluded`. A `pending` or `mapped` row blocks closeout and deletion. Note deletion still requires the separate exact Human Gate below.

## Exact Human Gates

An approved entry remains authoritative until the human approves its change. For any edit, first show:

- the exact current entry;
- why it must change;
- the exact replacement or new `amends`/`supersedes` entry.

Then ask: `Human Gate — approve this exact agreement change? (yes/no)` Make no change before an unambiguous yes. Prefer a new entry for semantic changes; direct edits are only for approved corrections or clearer wording.

Before deleting a note, verify every continuing agreement appears in its owning durable artifact and every deliberate exclusion is recorded. Show the note path, durable destinations, exclusions or information lost, and why deletion is safe. Then ask: `Human Gate — delete this exact note? (yes/no)` Do not delete before an unambiguous yes.

## Quick Reference

| Situation | Action |
|---|---|
| Zero approvals | Continue discussion; no note |
| Full approval plus implement now, no relevant active note | Implement under existing authority; create no note |
| Final approval with a relevant active note | Append the approved point, then reconcile under the granted authority |
| Relevant active note after discussion ends | Resume it for handoff or closeout |
| Partial approval | Resolve, inspect, append approved subset |
| Several plausible notes | Stop for human selection |
| Approved meaning changes | Preview and request exact Human Gate |
| New independently plannable topic | Create a separate note |
| Selected agreements authorized for work | Reconcile and hand off only that subset |
| Agreement shown or explained | Do not infer implementation authority |
| Direct work already exists | Verify it, then map as `already-covered` |
| New agreement after reconciliation | Append it; extend mutable tables above |
| Any ledger row `pending` or `mapped` | Block full closeout and deletion |
| Resolver or storage fails | Stop; create no fallback copy |
| Delete before durable transfer | Refuse; transfer or record exclusions first |

## Common Mistakes

- A note is not a plan, decision record, requirement, or permission to act.
- A linked worktree never owns its own active-note copy.
- Active topic notes stay ignored, unstaged, and uncommitted.
- Discussion context is not approval.
- Reconciliation metadata is not an Agreement amendment.
- Prose such as "partially covered" is not a substitute for an exact Coverage Matrix contribution.
- A working note is not implementation authority.
- Starting destination edits before registering an authorized partial handoff breaks traceability.
- Cleanup pressure does not bypass transfer verification or a Human Gate.
