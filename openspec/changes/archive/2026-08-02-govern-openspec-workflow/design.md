## Context

The project-local `governed-spec-driven` schema currently validates, but it
contains only the standard proposal, specs, design, and tasks artifacts. The
native OpenSpec CLI resolves schemas, dependency order, context files, and apply
instructions; its generated apply skill selects and tracks tasks, but does not
dispatch the project's implementation loop. The repository already has named
implementer and reviewer profiles, a canonical validation contract, and an
`implementation-loop` skill that can enforce the task lifecycle once invoked.

## Goals / Non-Goals

**Goals:**

- Make `governed-spec-driven` describe a complete, reviewable change workflow
  without modifying generated native OpenSpec skills.
- Make validation and review explicit change artifacts and require them before
  task execution can begin.
- Establish one documented handoff: native apply selects the task; the existing
  implementation loop executes it through validation and independent review.
- Prove the handoff with an explicitly selected-schema pilot before changing
  the repository default.

**Non-Goals:**

- Do not replace OpenSpec's artifact graph, context resolution, or task tracker.
- Do not create a wrapper skill in this slice.
- Do not change named profiles or the validation-gate registry unless a later,
  separately approved change supplies an exact preview and Human Gate.
- Do not use a product feature as the first governance pilot.

## Decisions

### Keep native planning artifacts and add two governance artifacts

The schema retains `proposal`, `specs`, `design`, and `tasks`. It adds
`validation` after tasks and `review` after validation. Both are required by
`apply`, so a governed change cannot begin implementation until its validation
plan and review plan exist. `validation.md` defines the deterministic evidence
required for the change; `review.md` defines the independent-review scope,
inputs, verdict format, and checkbox rule. Execution evidence remains in the
existing `.agentic-workflow/` state and report paths; these artifacts do not
attempt to duplicate it.

### Use a two-layer handoff rather than a schema runtime hook

Schema and CLI stay responsible for artifact dependency order, generated
instructions, context, and task selection. `AGENTS.md` and governed apply
instructions require the agent to invoke `implementation-loop` once native
apply has selected a task. The loop then owns dispatch, validation, reviewer
handoff, fix rounds, and the precondition for checking the task. This reflects
the boundary available in OpenSpec today: schema instructions guide agents but
cannot execute a project skill themselves.

### Bootstrap with an explicit-schema pilot

The governance change itself remains on `spec-driven`. After the candidate
schema and instructions validate, create one narrow repository-workflow pilot
with `openspec new change --schema governed-spec-driven`. Complete one bounded
non-product task through the two-layer handoff, then validate and archive that
pilot. Only after this proof updates `openspec/config.yaml` to make
`governed-spec-driven` the default for later changes.

### Defer wrapper automation

A project-local wrapper could invoke native apply and then the implementation
loop in one entry point, but it would add a new orchestration surface before a
real failure mode is known. The pilot is the decision point: create a wrapper
only if native apply plus repository instructions proves insufficient or easy
to bypass in practice.

## Risks / Trade-offs

- **Schema instructions are guidance, not a runtime hook** → The no-wrapper
  pilot must demonstrate that agents consistently honour the documented
  handoff; otherwise pause before switching the default.
- **Change-level artifacts can be mistaken for per-task evidence** → Templates
  explicitly point to the canonical execution-state and evidence paths.
- **Switching the default too early could strand a change on an unproven
  workflow** → Use `--schema governed-spec-driven` for the pilot and change the
  default only after its validation and review succeed.
- **A governance pilot could accidentally become product work** → Limit it to
  one repository-workflow task and archive it independently.

## Migration Plan

1. Extend and validate the project-local candidate schema and its templates.
2. Add the repository instructions that bind native apply to the existing loop.
3. Create and complete an explicit-schema pilot without a wrapper.
4. Review the pilot evidence; switch the default only when the handoff is
   demonstrated and no material gap remains.
5. Roll back by keeping `schema: spec-driven` in `openspec/config.yaml`; no
   product data or OpenSpec change artifacts are deleted.
