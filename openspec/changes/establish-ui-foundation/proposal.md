## Why

The generated Tauri screen does not provide a usable foundation for building
the Personal Timesheet product. A consistent application shell, visual system,
navigation model, and test harness are needed before product screens can be
implemented safely in small vertical slices.

## What Changes

- Replace the generated demo with a professional desktop application shell.
- Add primary navigation for Timesheet, Reports, Expenses, and Settings.
- Make the sidebar collapsible so data-heavy screens can reclaim horizontal
  space.
- Establish responsive light and dark themes that follow the system preference
  by default and allow an explicit user preference.
- Establish page-specific density: compact for time-entry surfaces and more
  spacious for analytical and configuration surfaces.
- Add a component-test harness and smoke coverage for navigation, sidebar, and
  theme behavior.
- Adopt Tailwind CSS 4, shadcn/ui with Base UI primitives, React Router in
  Declarative Mode, and Vitest with Testing Library.

Non-goals:

- Implementing timesheet entry, reports, expenses, settings, or domain data.
- Adding SQLite, Zod, cloud synchronization, or mobile-specific navigation.
- Adding a global client-state library or form framework before a concrete need
  exists.

## Capabilities

### New Capabilities

- `application-shell`: Desktop navigation, responsive layout, density rules,
  and light/dark theme behavior shared by product screens.

### Modified Capabilities

None.

## Impact

- Replaces the generated React demo under `src/`.
- Adds frontend styling, primitive-component, routing, icon, and testing
  dependencies.
- Adds reusable shell, navigation, theme, and placeholder-page modules.
- Adds frontend test configuration and scripts.
- Does not change the Tauri command surface, Rust backend, or persistent data.
