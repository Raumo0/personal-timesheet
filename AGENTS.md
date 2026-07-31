# Personal Timesheet Development Guidelines

## Project

Personal Timesheet is a local-first, cross-platform time-tracking application.
Its core domain includes clients, projects, tasks, inherited billing rates,
weekly time entry, expenses, reports, and invoice-ready exports.

Do not describe planned behavior as implemented. Keep product decisions,
implementation facts, and open questions distinct.

## Current Stack

- Tauri 2 and Rust for the native application shell.
- React 19 and TypeScript for the interface.
- Vite for frontend development and builds.
- pnpm for JavaScript package management.

Use the existing package manager and lockfiles. Do not introduce a second tool
for the same responsibility.

## Working Approach

- Deliver small vertical slices that can be run and reviewed independently.
- Read relevant code and configuration before editing.
- Keep changes narrow. Do not modify adjacent areas without a concrete need.
- Prefer simple domain logic separated from UI and platform integration.
- Use test-driven development for features, bug fixes, refactoring, and
  behavioral changes.
- Treat generated scaffold and configuration-only changes as exceptions when
  they are verified by the appropriate build or validation command.
- Never claim completion without fresh verification.

## Git

Use Conventional Commits:

```text
<type>[optional scope]: <imperative description>
```

Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `build`, `ci`, and
`chore`.

- Keep one independently understandable change per commit.
- Keep the description concise, imperative, and under 72 characters.
- Inspect status and diffs before staging.
- Stage explicit paths. Do not use `git add .` or `git add -A`.
- Do not amend, force-push, skip hooks, or use destructive Git commands unless
  the user explicitly requests it.
- Never commit secrets, credentials, local databases, generated binaries, or
  rebuildable caches.

## Validation

Run checks appropriate to the changed area:

```bash
pnpm build
cargo check --manifest-path src-tauri/Cargo.toml
```

Run focused tests first when tests exist, then the relevant broader suite.
Review `git status` and the final diff before reporting completion.

## Project Skills

Project skills live in `.agents/skills/`. Their sources and hashes are recorded
in `skills-lock.json`.

- Read a relevant skill before following its workflow.
- Use `npx skills list` to inspect installed skills.
- Use `npx skills update <skill-name>` only when a skill update is requested.
- Use `npx skills experimental_install` to restore them from the lockfile.
- Review skill changes and bundled scripts before committing an update.

`AGENTS.md` is the canonical repository-wide instruction file.
