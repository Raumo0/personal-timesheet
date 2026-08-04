---
name: implementation-loop
description: Use when an approved OpenSpec change is ready for implementation or an interrupted OpenSpec execution must resume.
---

# Implementation Loop

## Core rule

Execute one caller-authorized OpenSpec task at a time in its assigned worktree.
`tasks.md` is the sole selection and completion authority. Local execution state
supports interruption recovery but never authorizes work or overrides a checked
checkbox.

Use `scripts/execution_state.py` for selection, dispatch construction,
compatibility decisions, phase transitions, and atomic state reads and writes.
Do not reproduce those decisions in prompts or scratch notes.

## Select and resume

1. Read `AGENTS.md` and the approved OpenSpec proposal, design, delta specs, and
   `tasks.md`. Do not create or use a parallel implementation plan.
2. Pass the exact OpenSpec change ID, normal caller-authorized task IDs, and
   separately authorized prerequisite IDs to `select_task`. It chooses the
   first unchecked authorized ID in file order. Persisted state may be
   prioritized only when its task remains unchecked, its change ID matches,
   and its task is in the current authority union. Empty or revoked authority
   selects nothing.
3. An unchecked persisted task in `selected`, `implementing`, `validated`,
   `review`, `fixing`, `blocked`, or `approved` resumes before new selection.
   Once its checkbox is checked, persisted state cannot select it.
4. Store one ignored file at the canonical path
   `.agentic-workflow/executions/<change-id>.json`. Derive it only with
   `execution_state_path(repository_root, expected_change_id)`. Use
   `write_state(repository_root, expected_change_id, state)` and
   `read_state(repository_root, expected_change_id)`; they reject traversal,
   arbitrary paths, and mismatched state/change identity. Both validate the
   exact schema, and writes atomically replace the prior file.

Schema version `1` has exactly these fields: `schema`, `change_id`, `task_id`,
`phase`, `worktree`, `base_identity`, `diff_identity`,
`validator_evidence_path`, `validator_hash`, `validator_worktree_digest`,
`validator_status`, `implementer_report`, `reviewer_report`,
`reviewer_verdict`, `fix_round`, `pending_gate`, `created_at`, and `updated_at`.
The helper rejects extra keys, wrong types, malformed identifiers or timestamps,
invalid nullable values, and phase-inconsistent evidence on read and write.

## Dispatch

Call `prepare_dispatch` for every direct, named-profile, or bounded
general-purpose assignment. Every assignment must preserve separately:

- binding source paths;
- acceptance evidence;
- allowed scope;
- required focused test evidence, including an allowed passing result or an
  explicitly expected failure when the behavior is not yet implemented;
- prohibited external actions; and
- durable report path.

Use `implementer` (`Task Implementer`) for implementation. Default dispatch
omits `model`; only a caller-supplied model may be forwarded. Never create or
edit a named profile at runtime.

If neither named profile fits, state the mismatch and ask the caller to
authorize one complete bounded `general-purpose` assignment. Missing authority
or any missing assignment field blocks dispatch. A durable profile change still
requires its own exact diff, authority impact, and Human Gate.

Use `reviewer` (`Independent Reviewer`) only from a validated execution state
for the same task and worktree. `prepare_dispatch` issues a local reviewer
dispatch receipt with an opaque identity, exact report path, task, and current
diff identity. A reviewer result must identify that receipt, `reviewer` profile,
task, diff, verdict, and unresolved Important/Critical finding count; copied,
renamed, self-authored, malformed, or stale reports are rejected. `prepare_dispatch` re-reads the actual evidence
file and reuses `tools/agentic_workflow/validate.py` from the assigned worktree
to recompute repository identity. It verifies evidence-file SHA-256, current
Validation Contract SHA-256, repository path and revision, current worktree
digest and state, overall status, and the exact current gate registry without
rerunning gates. Gate order, ID, applicability, mandatory flag, redacted
command, and re-evaluated applicability must match. It then supplies the
implementer report, verified diff identity, evidence path, file SHA-256,
worktree digest, and `pass` status. Missing, edited, fabricated, stale,
caller-supplied, or mismatched evidence blocks dispatch. If the canonical
validator or its identity API is unavailable, fail closed.

## State transitions

Use `transition` except for `implementing -> validated`, which only
`run_canonical_validation` may perform. Never edit state fields directly.

| From | To | Required persisted input |
|---|---|---|
| `selected` | `implementing` | base identity |
| `implementing` | `validated` | dedicated `run_canonical_validation` operation and implementer report; ordinary `transition` is forbidden |
| `validated` | `review` | the already persisted passing evidence; no caller replacement |
| `review` | `fixing` | `NEEDS_FIXES` and reviewer report; increment `fix_round` |
| `review` | `approved` | `APPROVED` and reviewer report |
| `fixing` | `implementing` | no evidence replacement |
| active phase | `blocked` | optional exact pending-gate identifier |
| `blocked` | `implementing`, `validated`, or `review` | explicit resolution, allowed return phase, and exact approval when a gate is pending |

All other jumps fail. A pending gate blocks progress until its exact identifier
is supplied as approval. Approval and resolution are transition controls: clear
the pending gate and never persist as extra schema fields.

Persist state after selection and every successful transition. The
`approved` phase is recoverable until the controller updates the corresponding
checkbox. Do not mark that checkbox from the helper.

At `implementing -> validated`, call `run_canonical_validation` with the
implementer report. It invokes the assigned worktree's canonical
`tools/agentic_workflow/validate.py` entrypoint without a shell, writes
`.agentic-workflow/validation-evidence.json`, requires a successful exit, then
verifies and derives the persisted identity. Never accept pre-existing JSON or
a caller-shaped hash, digest, status, contract identity, evidence path, or diff
identity as authority to enter `validated`.

Evidence must report `overall_status: pass`, exact current repository path, Git
revision, worktree state/digest, and Validation Contract hash. Its gate list
must exactly match the declared registry in order, ID, applicability, mandatory
flag, and redacted command. Re-evaluate each applicability rule: `always` and
present paths cannot be `not-applicable`; absent paths must be. Every applicable
mandatory gate must pass. Missing, extra, duplicate, reordered, altered, failed,
or skipped mandatory evidence blocks validation and reviewer dispatch. Persist
`validator_hash` as the evidence file SHA-256, `validator_worktree_digest` from
the canonical validator identity, and `validator_status: pass`.

`diff_identity` is derived, never supplied: SHA-256 of the current Git revision,
a NUL separator, and the canonical current worktree digest. This binds the
implementation diff to the exact repository revision and dirty contents.
The evidence file hash binds the evidence-contained contract hash. Recompute
and compare all of these values again immediately before reviewer dispatch.

## Support-skill compatibility

Call `support_allowed` immediately before activating a support skill. Unknown
or incomplete contexts return false. Incompatible external skills stay inactive
unless every listed prerequisite passes:

- `requesting-code-review`: always inactive because it conflicts with the
  approved named reviewer.
- `subagent-driven-development`: its context has exactly these seven keys and
  no others: `caller_model`, `runtime_compatible`, `openspec_compatible`,
  `profile_compatible`, `unapproved_commits_prohibited`,
  `repository_local_review`, and `automatic_cleanup_prohibited`.
  `caller_model` is a non-empty string; the other six fields must each be
  literal `true`. Missing, extra, or wrong-valued fields keep the skill
  inactive.
- `dispatching-parallel-agents`: caller-supplied model, profile compatibility,
  independent tasks, no shared state, and no Human Gate.
- `git-commit`: explicit commit authority.
- `finishing-a-development-branch`: inactive until a separate explicit Human
  Gate authorizes branch completion after implementation and review.
  No caller-supplied completion, authority, task, or review evidence can
  activate it.
- `capturing-working-agreements`: its activation trigger is present.
- `using-git-worktrees`: isolation is absent.
- `test-driven-development`: active for implementation and bugfix work.

Do not silently adapt an external skill. Invoke only repository-local skills or
skills recorded in `skills-lock.json`, and keep any skill with unmet model,
profile, OpenSpec, authority, shared-state, Human Gate, commit, or completion
prerequisites inactive.

## Validate, review, and stop

1. Use `run_canonical_validation` to run the current versioned Validation
   Contract entrypoint and enter `validated` only from its fresh result.
2. Stop before reviewer dispatch when mandatory evidence is missing, stale,
   failed, skipped without authority, or does not match the current worktree.
3. Persist the passing identity and enter `validated` before building reviewer
   dispatch. Then enter `review` without replacing evidence. At verdict
   acceptance, recompute the worktree diff while excluding only the reviewer
   report itself; it must still equal both the issued receipt and persisted
   validation identity.
4. Persist the independent report and exact verdict. `NEEDS_FIXES` enters a
   bounded fix round; revalidation must replace the prior validation identity
   before another review. `APPROVED` enters recoverable `approved` state.
5. Stop on a material coverage gap, unresolved Important or Critical finding,
   missing authority, profile or skill change, Validation Contract change,
   external write, publication, merge, cleanup, or destructive action.

For an authorized whole-change review, this controller owns the handoff:
`prepare_whole_change_review_dispatch` → read-only reviewer JSON →
`persist_reviewer_result` with the issued `review_dispatch` receipt →
`record_whole_change_review`. The receipt derives the only persisted result
destination under `.agentic-workflow/`; validate the returned JSON, verdict
truth table, and provenance before persisting it. These artifacts are
operational evidence in the implementer-writable worktree, not tamper-resistant
or independent proof of integrity. A `BLOCKED` whole-change coverage gap is
recorded, then `require_whole_change_coverage_gap_human_gate` names the exact
gate before dependent continuation. Do not delete reviewer evidence.

After current validation and independent `APPROVED`, the controller may persist
the final state and mark only that OpenSpec task checkbox. Issue or pull-request
writes, commits, profile or skill changes, branch completion, merge, cleanup,
and destructive actions remain separately authorized.
