# Personal Timesheet

A local-first, cross-platform replacement for a personal Clockify workflow.
The application will track time and expenses across clients, projects, and
tasks, then produce useful reports and invoice-ready exports.

## Status

The application is under active development. Client catalog and the project
domain foundation are implemented; the project workspace is still in progress.

## Quick start

Requirements: Node.js, pnpm, Rust, and the platform prerequisites for Tauri 2.

From the repository root:

```bash
pnpm install
pnpm tauri dev
```

The second command starts Vite and opens the native Personal Timesheet Dev
window. Press `Ctrl+C` in the terminal to stop it.

To run only the browser interface during frontend work:

```bash
pnpm dev
```

Then open <http://localhost:1420>.

### RustRover

Use the built-in terminal to run the native application:

```bash
pnpm tauri dev
```

For a reusable Run Configuration, choose **Run → Edit Configurations → + →
NPM** and set:

- **package.json:** the root `package.json`
- **Command:** `run-script`
- **Scripts:** `tauri`
- **Arguments:** `dev`
- **Package manager:** `Project` after selecting `pnpm` in **Settings →
  Languages & Frameworks → JavaScript Runtime**

The NPM configuration name is generic: it runs pnpm when pnpm is the project
package manager. Tauri starts Vite automatically through its `beforeDevCommand`;
do not add a separate Vite configuration.

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

### Development and production data

Development command: `pnpm tauri dev`. This supported entry point applies the
development identity `com.personal.timesheet.dev` automatically. Direct
`pnpm exec tauri dev` invocation bypasses that protection and is unsupported.

Production build command: `pnpm tauri build`. It keeps the installed
application identity `com.personal.timesheet`.

On macOS, the SQLite files are stored at these exact paths:

- Production:
  `~/Library/Application Support/com.personal.timesheet/personal-timesheet.db`
- Development:
  `~/Library/Application Support/com.personal.timesheet.dev/personal-timesheet.db`

On Windows and Linux, Tauri uses the platform-specific application
configuration directory. The final application directory is derived from the
same environment identifier, and the database filename remains
`personal-timesheet.db`.

No data is automatically copied, migrated, or synchronized between the two
identities. Existing production data stays in the production directory, while
the first development launch starts with separate development data.

Build the frontend:

```bash
pnpm build
```

Check the Rust application:

```bash
cargo check --manifest-path src-tauri/Cargo.toml
```

Run tests:

```bash
pnpm test
cargo test --manifest-path src-tauri/Cargo.toml
```

## Specification Workflow

OpenSpec stores implemented behavior in `openspec/specs/` and proposed changes
in `openspec/changes/`.

```bash
pnpm spec list
pnpm spec:doctor
```

In Codex, start every feature or material behavior change with
`$openspec-explore`. After agreeing on the direction, create a reviewable
change with `$openspec-propose`. Implement with `$openspec-apply-change`, then
synchronize and archive the completed change.

Small documentation and configuration changes do not require an OpenSpec
change. Behavioral fixes still use test-driven development.

## Project Skills

Project-local agent skills are stored in `.agents/skills/` and locked in
`skills-lock.json`. The workflow assumes Codex, either the desktop application
or Codex CLI. The `skills` CLI is invoked through `npx` to inspect and restore
the locked skills:

```bash
npx skills list
npx skills experimental_install
```

Review each skill and its bundled scripts before installing or updating it.
Use `npx skills update <skill-name>` only when an update is intended.
Repository-wide working rules are defined in [`AGENTS.md`](AGENTS.md).

OpenSpec CLI is already installed as a project dependency and should be run
through the `pnpm spec` scripts or `pnpm exec openspec`; no global installation
is required. The optional `opensrc` skill additionally requires the `opensrc`
CLI on `PATH`:

```bash
pnpm add --global opensrc
opensrc --version
```

`opensrc` downloads dependency sources into the user-level `~/.opensrc/`
cache. Keep that cache outside the repository and treat fetched code as
read-only reference material.

## Project Structure

```text
src/                 React frontend
src-tauri/           Tauri and Rust application
.agents/skills/      Project-local agent workflows
.codex/skills/       OpenSpec-generated Codex workflows
openspec/            Product specifications and proposed changes
AGENTS.md            Repository-wide agent instructions
skills-lock.json     Reproducible skill sources and hashes
```
