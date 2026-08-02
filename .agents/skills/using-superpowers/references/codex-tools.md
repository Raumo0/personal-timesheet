## Subagent dispatch

Use the multi-agent tools exposed by the current Codex runtime. Do not require
or edit user-global feature configuration from a project skill. If dispatch,
waiting, or follow-up tools are unavailable, do not fabricate them; execute
sequentially or report the limitation.

Keep each implementer available until its task review passes so the fix loop
can resume it. Release or interrupt agents only through tools the current
runtime actually exposes and only within the authorized task.

## Environment Detection

Skills that create worktrees or finish branches should detect their
environment with read-only git commands before proceeding:

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" 2>/dev/null && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" 2>/dev/null && pwd -P)
BRANCH=$(git branch --show-current)
```

- `GIT_DIR != GIT_COMMON` → already in a linked worktree (skip creation)
- `BRANCH` empty → detached HEAD (cannot branch/push/PR from sandbox)

See `using-git-worktrees` Step 0 and `finishing-a-development-branch`
Step 1 for how each skill uses these signals.

## Codex App Finishing

When the sandbox blocks branch or push operations in an externally managed
worktree, preserve the workspace and report the limitation. Use the App's
native controls only when the user selects that route:

- **"Create branch"** — names the branch, then commit/push/PR via App UI
- **"Hand off to local"** — transfers work to the user's local checkout

The agent may still run authorized checks and suggest branch names, commit
messages, or PR descriptions. Staging, committing, pushing, and creating a PR
still require explicit authority under the repository instructions.
