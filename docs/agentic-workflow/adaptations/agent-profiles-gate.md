# Agent Profiles Adaptation

The repository registers two bounded profiles in `.codex/config.toml`:

- `implementer` uses workspace-write access for one authorized OpenSpec task;
- `reviewer` remains read-only and independently evaluates the supplied work.

Neither profile may broaden scope, modify governance, waive deterministic
evidence, or perform external writes. Changes to profile authority require an
explicit Human Gate. Coverage lives in `tests/test_agent_profiles.py`.
