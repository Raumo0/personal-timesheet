## Context

The frontend is the generated React and Vite demo with no routing, design
system, reusable UI primitives, or tests. The Tauri window is a bundled
single-page desktop application with a minimum width of 960 pixels. See
`proposal.md` for motivation and scope.

## Goals / Non-Goals

**Goals:**

- Create a small application shell that future product slices extend instead
  of replace.
- Keep navigation, theme, and density decisions in one discoverable place.
- Own generated UI component code while relying on accessible headless
  primitives.
- Test behavior through user-visible interfaces.

**Non-Goals:**

- Introduce product data, backend calls, forms, charts, or persistent domain
  storage.
- Create speculative state-management, repository, or form abstractions.
- Optimize for mobile navigation before mobile becomes an approved target.

## Decisions

### Tailwind CSS 4 through the Vite plugin

Use `tailwindcss` with `@tailwindcss/vite` and a single global stylesheet.
Define semantic color, spacing, radius, and density tokens with CSS variables.
Use a platform-native sans-serif font stack for a desktop-native feel without
adding a font-loading dependency.

Alternative considered: CSS Modules. They avoid utility classes but would
require rebuilding the token and component conventions supplied by shadcn/ui.

### shadcn/ui with Base UI primitives

Initialize shadcn/ui for an existing Vite project using Base UI, the `new-york`
style, neutral foundations, and one restrained blue accent. Add only primitives
required by the shell, such as Button, Tooltip, and Dropdown Menu. Generated
components live under `src/components/ui/` and become project-owned code.

Alternative considered: a packaged component system such as MUI or Mantine.
Those systems accelerate broad component coverage but impose a larger runtime
and stronger visual abstraction than this application currently needs.

### Declarative React Router with hash history

Use React Router in Declarative Mode. Hash-based history avoids requiring a
server fallback for bundled Tauri routes. Define Timesheet, Reports, Expenses,
and Settings once in a typed navigation registry; both routes and sidebar items
consume that registry.

Alternative considered: TanStack Router. Its stronger type system is valuable
for complex parameterized applications, but the current four static
destinations do not justify its additional concepts.

### A deep application-shell module

Expose one `AppShell` interface around sidebar state, navigation presentation,
page framing, and contextual workspace density. Keep primitive components,
route pages, and theme mechanics behind focused internal seams. Do not expose a
generic layout framework for hypothetical callers.

The Timesheet route selects compact density. Reports, Expenses, and Settings
select comfortable density. The sidebar starts expanded and its collapse state
is session-local; persistence can be added only if real usage demonstrates a
need.

### A small theme module

Use a `ThemeProvider` with the public values `system`, `light`, and `dark`.
Persist only the explicit preference in local storage. Resolve `system` through
`prefers-color-scheme`, subscribe to operating-system changes, and apply the
resolved theme at the document root before rendering visible content where
practical.

Alternative considered: a global client-state library. Theme state is a single
cross-cutting concern with a small interface, so React context is sufficient.

### Vitest and Testing Library

Use Vitest with jsdom, React Testing Library, `user-event`, and jest-dom
matchers. Test observable navigation, collapse, and theme behavior. Keep tests
beside the modules they exercise and place shared setup in `src/test/setup.ts`.

Alternative considered: browser end-to-end testing in this slice. It would add
native-window orchestration before any product workflow exists; add it when the
first complete business workflow requires it.

## Risks / Trade-offs

- **Base UI is newer than Radix-based shadcn/ui components** → Keep generated
  primitives project-owned, add only what is needed, and cover shell behavior
  with tests.
- **Hash routes are less attractive as web URLs** → Prefer reliable bundled
  desktop navigation now; reconsider only if a hosted web target is approved.
- **Tailwind utilities can scatter visual decisions** → Require semantic tokens
  and shared primitives for repeated patterns.
- **Theme initialization can briefly flash the wrong appearance** → Resolve the
  stored preference before the main interface becomes visible.
- **Placeholder screens can accidentally become product design** → Keep them
  intentionally minimal and replace them through later capability changes.

## Migration Plan

1. Add and configure styling, routing, component, and test dependencies.
2. Establish failing tests for the agreed shell behavior.
3. Replace the generated demo with the shell and placeholder routes.
4. Verify tests, frontend production build, Rust checks, and the native Tauri
   launch.

Rollback is a normal Git revert because this slice adds no persisted domain
data or migration.
