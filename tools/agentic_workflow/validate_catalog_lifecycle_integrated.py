#!/usr/bin/env python3
"""Run the complete catalog lifecycle integration command set."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


CHANGE_TASKS = Path("openspec/changes/manage-catalog-archive-lifecycle/tasks.md")
RECOVERY_COMMANDS = [
    ["python3", "tools/agentic_workflow/validate_catalog_lifecycle_recovery.py"],
]
COMMANDS = [
    ["pnpm", "test"],
    ["pnpm", "build"],
    ["cargo", "test", "--manifest-path", "src-tauri/Cargo.toml"],
    ["cargo", "check", "--manifest-path", "src-tauri/Cargo.toml"],
    [
        "pnpm",
        "exec",
        "openspec",
        "validate",
        "manage-catalog-archive-lifecycle",
        "--strict",
    ],
    ["git", "diff", "--check"],
]


def execute(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def is_recovery_pending(tasks_text: str) -> bool:
    return bool(re.search(r"^- \[ \] 10\.1\b", tasks_text, re.MULTILINE))


def commands_for_phase(tasks_text: str) -> list[list[str]]:
    return RECOVERY_COMMANDS if is_recovery_pending(tasks_text) else COMMANDS


def run_commands(
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = execute,
    commands: list[list[str]] = COMMANDS,
) -> int:
    for command in commands:
        completed = runner(command)
        sys.stdout.write(completed.stdout or "")
        sys.stderr.write(completed.stderr or "")
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    try:
        tasks_text = CHANGE_TASKS.read_text(encoding="utf-8")
    except OSError as error:
        print(f"catalog lifecycle tasks are unavailable: {error}", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(run_commands(commands=commands_for_phase(tasks_text)))
