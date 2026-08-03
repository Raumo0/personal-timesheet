#!/usr/bin/env python3
"""Validate the catalog-lifecycle database suite in its RED or GREEN phase."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


CHANGE_TASKS = Path(
    "openspec/changes/manage-catalog-archive-lifecycle/tasks.md"
)
EXPECTED_RED_TEST = (
    "database::tests::fourth_migration_atomically_normalizes_archived_ancestor_invariants"
)
FAILED_TEST = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+FAILED$", re.MULTILINE)


def expects_red(tasks_text: str) -> bool:
    return bool(re.search(r"^- \[ \] 3\.1\b", tasks_text, re.MULTILINE))


def validate_result(returncode: int, output: str, *, red: bool) -> str | None:
    if not red:
        return None if returncode == 0 else "database suite failed after task 3.1"
    if returncode == 0:
        return "database suite was expected to fail before migration 4"
    failures = FAILED_TEST.findall(output)
    if failures != [EXPECTED_RED_TEST]:
        return (
            "RED evidence must contain exactly the expected migration-4 failure; "
            f"observed {failures!r}"
        )
    if not re.search(r"test result: FAILED\.[^\n]*\b1 failed\b", output):
        return "RED evidence has no exact one-failure cargo summary"
    return None


def main() -> int:
    try:
        tasks_text = CHANGE_TASKS.read_text(encoding="utf-8")
    except OSError as error:
        print(f"catalog lifecycle tasks are unavailable: {error}", file=sys.stderr)
        return 2

    completed = subprocess.run(
        [
            "cargo",
            "test",
            "--manifest-path",
            "src-tauri/Cargo.toml",
            "database",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    print(output, end="")
    error = validate_result(
        completed.returncode,
        output,
        red=expects_red(tasks_text),
    )
    if error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
