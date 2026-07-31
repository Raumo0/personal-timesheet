# Personal Timesheet

A local-first, cross-platform replacement for a personal Clockify workflow.
The application will track time and expenses across clients, projects, and
tasks, then produce useful reports and invoice-ready exports.

## Status

The repository currently contains a verified Tauri starter. Product features
have not been implemented yet.

## Planned Capabilities

- Clients, projects, and tasks with hierarchical selection.
- Client billing rates inherited by projects and tasks, with overrides.
- Weekly time entry with previous and next week navigation.
- Expenses linked to clients and projects.
- Reports by client, project, task, and date range.
- PDF or invoice-ready exports containing time and expenses.
- Local persistence, with cloud synchronization considered separately.

## Technology

- Tauri 2 and Rust
- React 19 and TypeScript
- Vite
- pnpm

## Development

Install dependencies:

```bash
pnpm install
```

Run the native application:

```bash
pnpm tauri dev
```

Build the frontend:

```bash
pnpm build
```

Check the Rust application:

```bash
cargo check --manifest-path src-tauri/Cargo.toml
```

## Project Skills

Project-local agent skills are stored in `.agents/skills/` and locked in
`skills-lock.json`.

```bash
npx skills list
npx skills experimental_install
```

Review each skill and its bundled scripts before installing or updating it.
Use `npx skills update <skill-name>` only when an update is intended.
Repository-wide working rules are defined in [`AGENTS.md`](AGENTS.md).

## Project Structure

```text
src/                 React frontend
src-tauri/           Tauri and Rust application
.agents/skills/      Project-local agent workflows
AGENTS.md            Repository-wide agent instructions
skills-lock.json     Reproducible skill sources and hashes
```
