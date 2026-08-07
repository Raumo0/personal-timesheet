## Context

The base Tauri configuration currently owns the production identifier and the package exposes the Tauri CLI without an environment-aware boundary. Relative `sqlite:personal-timesheet.db` URLs resolve below Tauri's identifier-derived application configuration directory, and native backup and mutation commands resolve the same directory through `app_config_dir()`.

## Goals / Non-Goals

**Goals:**

- Keep one authoritative production configuration.
- Make the repository's normal development entry point select a development overlay automatically.
- Test configuration selection without starting a GUI process.

**Non-Goals:**

- Prevent manually invoking the underlying Tauri binary with arbitrary configuration.
- Move or copy existing production data.
- Add runtime environment switching inside the application.

## Decisions

### Keep production in the base configuration

`src-tauri/tauri.conf.json` remains the configuration used by production builds. This preserves `com.personal.timesheet` and avoids a production data migration. A small `src-tauri/tauri.dev.conf.json` overlay replaces only the identifier, product name, and main-window title for development.

Alternative considered: make development the base and overlay production. Rejected because an omitted build flag could produce a development-identified release and because the current installed identity is already production.

### Put environment selection behind the package command

The existing `pnpm tauri ...` entry point becomes a small Node wrapper. It appends the development overlay when the first Tauri subcommand is `dev` and delegates other subcommands unchanged. Pure argument construction is exported and covered by Node tests; process spawning stays a thin boundary.

Alternative considered: add only a separate `tauri:dev` script. Rejected because the familiar `pnpm tauri dev` command would remain an easy path to the production database.

### Validate resolved configuration statically

A deterministic validation script checks the base and overlay identities, their visible names, and wrapper argument routing. It does not launch the application or inspect user data.

## Risks / Trade-offs

- [Direct `pnpm exec tauri dev` bypasses the wrapper] → Document it as unsupported and validate the supported command.
- [A future config edit makes identities equal] → Fail focused tests and the deterministic configuration validator.
- [Developers mistake old production data for lost data] → Document both identifier-derived locations and state that no automatic migration occurs.

## Migration Plan

No data migration is performed. Existing production data remains under `com.personal.timesheet`; the first supported development launch creates a fresh database under `com.personal.timesheet.dev`. Rollback removes the wrapper and overlay and restores the prior package script.
