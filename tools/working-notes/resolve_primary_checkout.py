#!/usr/bin/env python3
"""Print the primary checkout for a Git repository or linked worktree."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


class ValidationError(Exception):
    """The repository has no uniquely identifiable accessible primary checkout."""


def _git_output(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def _worktree_paths(porcelain: str) -> list[Path]:
    return [
        Path(field.removeprefix("worktree "))
        for field in porcelain.split("\0")
        if field.startswith("worktree ")
    ]


def resolve_primary_checkout(repository: Path) -> Path:
    """Return the checkout whose Git directory is the common Git directory."""
    repository = repository.resolve()
    try:
        porcelain = _git_output(repository, "worktree", "list", "--porcelain", "-z")
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValidationError("unable to inspect Git worktrees") from error

    primary_candidates: list[Path] = []
    for candidate in _worktree_paths(porcelain):
        try:
            git_directory = _git_output(
                candidate,
                "rev-parse",
                "--path-format=absolute",
                "--git-dir",
            ).strip()
            common_directory = _git_output(
                candidate,
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            continue

        if git_directory == common_directory:
            primary_candidates.append(candidate.resolve())

    if len(primary_candidates) != 1:
        raise ValidationError("no unique accessible primary checkout")
    return primary_candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    arguments = parser.parse_args()

    try:
        print(resolve_primary_checkout(arguments.repository))
    except ValidationError as error:
        print(f"error: unable to resolve primary checkout: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
