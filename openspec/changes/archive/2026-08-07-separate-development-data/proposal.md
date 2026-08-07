## Why

Development launches currently share the production application identifier and SQLite location, so testing can silently read or modify real user data. Development and installed production runs need visibly distinct identities and independent local storage before real data is entered.

## What Changes

- Keep the installed production application on `com.personal.timesheet` and its existing application-data directory.
- Run the normal development command with `com.personal.timesheet.dev`, a visibly development-specific product/window name, and therefore a separate SQLite database.
- Add deterministic checks that prevent the development command from regressing to the production identifier.
- Document the exact development and production commands and storage locations.
- Do not migrate, copy, synchronize, or remotely store data between environments.

## Capabilities

### New Capabilities

- `development-data-isolation`: Defines distinct development and production identities, launch commands, and local data locations.

### Modified Capabilities

None.

## Impact

- Affects Tauri configuration, package scripts, configuration validation, and developer documentation.
- Production users and the production database path remain unchanged.
- Development starts with a separate database and cannot see production data unless data is explicitly imported there.
