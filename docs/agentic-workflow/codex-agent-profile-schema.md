# Installed Codex Agent Profile Schema

Observed on 2026-07-31 with `codex-cli 0.146.0-alpha.3.1`.

## Supported project configuration

The installed Codex build exposes `multi_agent` as a stable feature and supports version-controlled named agent roles through the project configuration at `.codex/config.toml`:

```toml
[agents.implementer]
description = "Implements one bounded OpenSpec task"
config_file = "agents/implementer.toml"
nickname_candidates = ["Task Implementer"]
```

The table key is the stable runtime role ID. The installed `AgentRoleToml` registration accepts:

- `description`: non-empty selection guidance;
- `config_file`: path to an existing TOML role file, resolved from the project configuration;
- `nickname_candidates`: optional non-empty ASCII nickname candidates.

Repository role files therefore live under `.codex/agents/`, for example `.codex/agents/implementer.toml`. The installed parser requires the role file to be a TOML table containing:

```toml
name = "Task Implementer"
description = "Implements one bounded OpenSpec task"
developer_instructions = """
Follow the bounded assignment and repository rules.
"""
```

`name` is the portable human-facing role name. `developer_instructions` carries stable role authority and method. Task-specific scope remains outside the profile and is supplied when the orchestrator spawns an agent with the registered role ID.

## Verification evidence

The result is based on local, reproducible installation evidence:

- `codex --version` reported `codex-cli 0.146.0-alpha.3.1`;
- `codex features list` reported `multi_agent` as `stable` and enabled;
- generated experimental app-server JSON Schema exposes persisted `agent_role` on AgentControl-spawned subagents;
- installed parser diagnostics and `AgentRoleToml` field metadata identify the registration fields, require an existing `config_file`, and require non-empty `name`, `description`, and `developer_instructions` in the role file.

No project role was created during this check. Optional model, reasoning, sandbox, permission, and tool-boundary values remain subject to the exact Agent Profile preview and Human Gate in task 5.1; this evidence does not authorize them.
