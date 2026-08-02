"""Contract tests for resolving a Git repository's primary checkout."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "resolve_primary_checkout.py"


def git(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )


class ResolvePrimaryCheckoutCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.primary = self.root / "primary"
        self.linked = self.root / "linked"
        self.primary.mkdir()

        git("init", cwd=self.primary)
        git("config", "user.email", "tests@example.invalid", cwd=self.primary)
        git("config", "user.name", "Resolver tests", cwd=self.primary)
        (self.primary / "README.md").write_text("initial\n", encoding="utf-8")
        git("add", "README.md", cwd=self.primary)
        git("commit", "-m", "initial", cwd=self.primary)
        git("worktree", "add", "-b", "linked", str(self.linked), cwd=self.primary)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_prints_primary_checkout_for_primary_and_linked_worktree(self) -> None:
        for repository in (self.primary, self.linked):
            with self.subTest(repository=repository):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--repository",
                        str(repository),
                    ],
                    text=True,
                    capture_output=True,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"{self.primary.resolve()}\n")

    def test_prints_primary_checkout_when_path_contains_a_newline(self) -> None:
        primary = self.root / "newline-primary\ncheckout"
        linked = self.root / "linked-from-newline-path"
        primary.mkdir()

        git("init", cwd=primary)
        git("config", "user.email", "tests@example.invalid", cwd=primary)
        git("config", "user.name", "Resolver tests", cwd=primary)
        (primary / "README.md").write_text("initial\n", encoding="utf-8")
        git("add", "README.md", cwd=primary)
        git("commit", "-m", "initial", cwd=primary)
        git("worktree", "add", "-b", "linked-newline", str(linked), cwd=primary)

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repository",
                str(linked),
            ],
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, f"{primary.resolve()}\n")

    def test_rejects_a_path_outside_git(self) -> None:
        outside_git = self.root / "outside-git"
        outside_git.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repository",
                str(outside_git),
            ],
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("unable to resolve primary checkout", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class ResolvePrimaryCheckoutValidationTests(unittest.TestCase):
    def test_rejects_worktree_list_without_primary_candidate(self) -> None:
        specification = importlib.util.spec_from_file_location(
            "resolve_primary_checkout", SCRIPT
        )
        assert specification is not None
        assert specification.loader is not None
        resolver = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(resolver)

        porcelain = (
            "worktree /example/primary\0"
            "HEAD 0123456789012345678901234567890123456789\0\0"
            "worktree /example/linked\0"
            "HEAD 0123456789012345678901234567890123456789\0\0"
        )
        git_outputs = [
            porcelain,
            "/git/common/worktrees/primary\n",
            "/git/common\n",
            "/git/common/worktrees/linked\n",
            "/git/common\n",
        ]

        with patch.object(resolver, "_git_output", side_effect=git_outputs):
            with self.assertRaises(resolver.ValidationError):
                resolver.resolve_primary_checkout(Path("/example/linked"))


if __name__ == "__main__":
    unittest.main()
