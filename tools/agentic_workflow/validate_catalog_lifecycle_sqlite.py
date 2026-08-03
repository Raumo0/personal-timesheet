#!/usr/bin/env python3
"""Validate the SQLite lifecycle suite in its RED or GREEN phase."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


CHANGE_TASKS = Path("openspec/changes/manage-catalog-archive-lifecycle/tasks.md")
TEST_PATH = "src/features/catalog-lifecycle/sqlite-catalog-lifecycle.test.ts"
EXPECTED_IMPORT = 'Failed to resolve import "./sqlite-catalog-lifecycle"'
FAILED_SUITE = re.compile(r"^\s*FAIL\s+(\S+)", re.MULTILINE)


def expects_red(tasks_text: str) -> bool:
    return bool(re.search(r"^- \[ \] 4\.1\b", tasks_text, re.MULTILINE))


def validate_result(returncode: int, output: str, *, red: bool) -> str | None:
    if not red:
        return None if returncode == 0 else "SQLite lifecycle suite failed after task 4.1"
    if returncode == 0:
        return "SQLite lifecycle suite was expected to fail before the adapter exists"
    if output.count(EXPECTED_IMPORT) != 1:
        return "RED evidence must contain exactly the expected missing-adapter import"
    if FAILED_SUITE.findall(output) != [TEST_PATH]:
        return "RED evidence must contain exactly the expected failed suite"
    if not re.search(r"Test Files\s+1 failed\s+\|\s+\d+ passed", output):
        return "RED evidence has no exact one-file failure summary"
    if re.search(r"Tests\s+[^\n]*\bfailed\b", output):
        return "RED evidence contains a failing executed test"
    if not re.search(r"Tests\s+\d+ passed", output):
        return "RED evidence does not show the existing tests passing"
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
    error = validate_result(completed.returncode, output, red=expects_red(tasks_text))
    if error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
