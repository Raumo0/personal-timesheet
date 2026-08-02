## Why

The project-local `governed-spec-driven` schema is only a validated copy of
the default workflow. It does not yet encode validation and review artifacts,
make the governance lifecycle the default, or connect task execution to the
existing implementation loop.

## What Changes

- Evolve the project-local `governed-spec-driven` schema with change-level
  validation and review artifacts, with review depending on validation.
- Configure OpenSpec and repository guidance so a task selected through the
  native apply workflow must pass through the existing implementation loop,
  canonical validation, and independent review before its checkbox is marked.
- Add a small no-wrapper pilot that proves the handoff between native OpenSpec
  apply and the implementation loop.
- Make the governed schema the default only after the pilot succeeds.
- Preserve generated native OpenSpec skills and defer a wrapper skill unless
  the pilot identifies a concrete integration gap.

## Capabilities

### New Capabilities

None. This change governs repository workflow rather than product behavior.

### Modified Capabilities

None.

## Impact

- `openspec/schemas/governed-spec-driven/` and `openspec/config.yaml`
- `AGENTS.md`, the existing implementation-loop integration, and project
  validation/review evidence
- A focused pilot change created with the candidate governed schema
