#!/usr/bin/env python3
"""Validate catalog lifecycle recovery coverage in its RED or GREEN phase."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


CHANGE_TASKS = Path("openspec/changes/manage-catalog-archive-lifecycle/tasks.md")
COMMAND = [
    "pnpm",
    "test",
    "--",
    "src/features/catalog-lifecycle/sqlite-catalog-lifecycle.test.ts",
    "src/app/AppShell.test.tsx",
]
EXPECTED_RED_TESTS = [
    "exposes the original apply failure when rollback also fails",
    "recovers a failed Project context load on Retry",
]
FAILED_TEST = re.compile(r"^\s*[×x]\s+(.+?)(?:\s+\d+ms)?$", re.MULTILINE)


def expects_red(tasks_text: str) -> bool:
    return bool(re.search(r"^- \[ \] 10\.1\b", tasks_text, re.MULTILINE))


def validate_result(returncode: int, output: str, *, red: bool) -> str | None:
    if returncode == 0:
        return None
    if not red:
        return "Catalog lifecycle recovery suite failed after task 10.1"
    failures = FAILED_TEST.findall(output)
    if failures != EXPECTED_RED_TESTS:
        return f"RED evidence must contain exactly the expected recovery failures; observed {failures!r}"
    if not re.search(r"Test Files\s+2 failed\s+\|\s+\d+ passed", output):
        return "RED evidence has no exact two-file failure summary"
    if not re.search(r"Tests\s+2 failed\s+\|\s+\d+ passed", output):
        return "RED evidence has no exact two-test failure summary"
    return None


def main() -> int:
    try:
        tasks_text = CHANGE_TASKS.read_text(encoding="utf-8")
    except OSError as error:
        print(f"catalog lifecycle tasks are unavailable: {error}", file=sys.stderr)
        return 2

    completed = subprocess.run(COMMAND, capture_output=True, text=True, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    print(output, end="")
    error = validate_result(completed.returncode, output, red=expects_red(tasks_text))
    if error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
