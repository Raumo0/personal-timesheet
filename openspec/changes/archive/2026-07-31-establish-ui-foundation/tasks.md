## 1. Frontend Foundation

- [x] 1.1 Add Tailwind CSS 4, React Router, shadcn/ui Base UI dependencies, and Vitest/Testing Library dependencies in `package.json` and `pnpm-lock.yaml`; configure aliases, Tailwind, and jsdom in `tsconfig.json`, `tsconfig.node.json`, `vite.config.ts`, `components.json`, and `src/test/setup.ts`; verify with `pnpm build` and `pnpm test`.
- [x] 1.2 Initialize only the Button, Tooltip, and Dropdown Menu shadcn/ui primitives under `src/components/ui/`, add shared class helpers in `src/lib/utils.ts`, and establish semantic light/dark tokens in `src/styles/globals.css`; verify with `pnpm build`.

## 2. Theme Behavior

- [x] 2.1 RED: add failing observable tests beside `src/app/theme/ThemeProvider.tsx` for the default system preference, operating-system changes, explicit Light/Dark selection, and restored local-storage preference; run `pnpm test -- ThemeProvider` and confirm the expected failures.
- [x] 2.2 GREEN: implement `src/app/theme/ThemeProvider.tsx` and `src/app/theme/ThemeMenu.tsx` so System, Light, and Dark preferences satisfy the tests and accessible control requirements; run `pnpm test -- ThemeProvider`.
- [x] 2.3 REFACTOR: remove duplication inside `src/app/theme/` without changing its public three-value interface; rerun `pnpm test -- ThemeProvider` and `pnpm build`.

## 3. Application Shell Behavior

- [x] 3.1 RED: add failing user-visible tests beside `src/app/AppShell.tsx` for default Timesheet routing, four active navigation destinations, collapsed access, and compact versus comfortable page density; run `pnpm test -- AppShell` and confirm the expected failures.
- [x] 3.2 GREEN: add the typed route registry in `src/app/navigation.tsx`, minimal route pages in `src/app/pages/`, the shell in `src/app/AppShell.tsx`, and root composition in `src/App.tsx` using `HashRouter`; run `pnpm test -- AppShell`.
- [x] 3.3 REFACTOR: consolidate repeated navigation and page-frame markup behind the existing shell interface while retaining accessible names and focus styles; rerun `pnpm test -- AppShell` and `pnpm build`.

## 4. Verification and Handoff

- [x] 4.1 Remove generated demo assets and styles from `src/` and `public/`, then run the complete frontend checks with `pnpm test` and `pnpm build`.
- [x] 4.2 Run `cargo check --manifest-path src-tauri/Cargo.toml` and launch `pnpm tauri dev` to confirm the native shell opens and primary interactions work.
- [x] 4.3 Validate the completed change with `openspec validate establish-ui-foundation --strict --no-interactive` and update every completed checkbox in `openspec/changes/establish-ui-foundation/tasks.md`.
