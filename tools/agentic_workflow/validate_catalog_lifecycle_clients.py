#!/usr/bin/env python3
"""Validate the Client lifecycle UI suite in its RED or GREEN phase."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


CHANGE_TASKS = Path("openspec/changes/manage-catalog-archive-lifecycle/tasks.md")
TEST_PATH = "src/features/clients/ClientsPage.test.tsx"
EXPECTED_RED_TESTS = [
    "describes the complete Client archive scope before confirmation",
    "restores an archived Client while its descendants remain archived",
    "keeps a stale-plan error visible and Retry requests a fresh preview",
    "keeps a persistence error visible and Retry previews before applying again",
]
FAILED_TEST = re.compile(
    rf"^\s*FAIL\s+{re.escape(TEST_PATH)}\s+>\s+Clients page\s+>\s+(.+)$",
    re.MULTILINE,
)


def expects_red(tasks_text: str) -> bool:
    return bool(re.search(r"^- \[ \] 5\.1\b", tasks_text, re.MULTILINE))


def validate_result(returncode: int, output: str, *, red: bool) -> str | None:
    if returncode == 0:
        return None
    if not red:
        return "Client lifecycle UI suite failed after task 5.1"
    failures = FAILED_TEST.findall(output)
    if failures != EXPECTED_RED_TESTS:
        return f"RED evidence must contain exactly the expected Client UI failures; observed {failures!r}"
    if not re.search(r"Test Files\s+1 failed\s+\(1\)", output):
        return "RED evidence has no exact one-file failure summary"
    if not re.search(r"Tests\s+4 failed\s+\|\s+\d+ passed", output):
        return "RED evidence has no exact four-test failure summary"
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
