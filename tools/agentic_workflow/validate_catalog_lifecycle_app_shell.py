#!/usr/bin/env python3
"""Validate the AppShell lifecycle suite in its RED or GREEN phase."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


CHANGE_TASKS = Path("openspec/changes/manage-catalog-archive-lifecycle/tasks.md")
TEST_PATH = "src/app/AppShell.test.tsx"
EXPECTED_RED_TESTS = [
    "injects lifecycle archive planning into the Client screen",
    "injects lifecycle archive planning into the Project screen",
    "injects lifecycle archive planning into the Task screen",
    "navigates from an archived Client into its retained Project workspace",
    "preserves archived Client and Project context for Task restore",
]
FAILED_TEST = re.compile(
    rf"^\s*FAIL\s+{re.escape(TEST_PATH)}\s+>\s+application shell\s+>\s+(.+)$",
    re.MULTILINE,
)


def expects_red(tasks_text: str) -> bool:
    return bool(re.search(r"^- \[ \] 8\.1\b", tasks_text, re.MULTILINE))


def allows_recovery_coverage(tasks_text: str) -> bool:
    return bool(re.search(r"^- \[ \] 10\.1\b", tasks_text, re.MULTILINE))


def validate_result(
    returncode: int,
    output: str,
    *,
    red: bool,
    recovery_coverage: bool = False,
) -> str | None:
    if returncode == 0:
        return None
    if recovery_coverage:
        return None
    if not red:
        return "AppShell lifecycle suite failed after task 8.1"
    failures = FAILED_TEST.findall(output)
    if failures != EXPECTED_RED_TESTS:
        return f"RED evidence must contain exactly the expected AppShell failures; observed {failures!r}"
    if not re.search(r"Test Files\s+1 failed\s+\(1\)", output):
        return "RED evidence has no exact one-file failure summary"
    if not re.search(r"Tests\s+5 failed\s+\|\s+\d+ passed", output):
        return "RED evidence has no exact five-test failure summary"
    return None


def main() -> int:
    try:
        tasks_text = CHANGE_TASKS.read_text(encoding="utf-8")
    except OSError as error:
        print(f"catalog lifecycle tasks are unavailable: {error}", file=sys.stderr)
        return 2

    completed = subprocess.run(
        ["pnpm", "exec", "vitest", "run", TEST_PATH],
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
        recovery_coverage=allows_recovery_coverage(tasks_text),
    )
    if error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
