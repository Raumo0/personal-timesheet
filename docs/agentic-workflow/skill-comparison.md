# Project Skill Inventory

Project skills are installed in `.agents/skills/`. Upstream identities and
hashes are recorded in `skills-lock.json`; custom project skills need not have
an upstream lock entry.

## Locally adapted skills

- `using-superpowers` routes OpenSpec work through the current
  `$openspec-*` skills.
- `subagent-driven-development` executes approved OpenSpec tasks through the
  registered implementer and reviewer profiles.
- `implementation-loop` coordinates implementation and stops at a separate
  Human Gate before branch completion.
- `capturing-working-agreements` preserves approved discussion state before
  durable handoff.

The contract tests validate the current lock inventory and the installed
directories. They do not freeze an obsolete skill count or treat upstream
hashes as hashes of approved local adaptations.
