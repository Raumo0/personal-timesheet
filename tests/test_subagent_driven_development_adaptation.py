import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
SKILL_ROOT = REPOSITORY_ROOT / ".agents/skills/subagent-driven-development"


def read_skill_file(relative_path):
    return (SKILL_ROOT / relative_path).read_text(encoding="utf-8")


class SubagentDrivenDevelopmentAdaptationTests(unittest.TestCase):
    def test_task_brief_extracts_one_decimal_checkbox_item(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            plan = temporary_path / "tasks.md"
            brief = temporary_path / "brief.md"
            plan.write_text(
                "## 2. Skills\n\n"
                "- [x] 2.2 Previous task.\n"
                "- [ ] 2.3 Adapt the skill.\n"
                "  Preserve this continuation.\n"
                "- [ ] 2.4 Next task.\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    str(SKILL_ROOT / "scripts/task-brief"),
                    str(plan),
                    "2.3",
                    str(brief),
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                brief.read_text(encoding="utf-8"),
                "- [ ] 2.3 Adapt the skill.\n"
                "  Preserve this continuation.\n",
            )

    def test_task_brief_rejects_missing_decimal_id(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            plan = temporary_path / "tasks.md"
            brief = temporary_path / "brief.md"
            plan.write_text("- [ ] 2.3 Adapt the skill.\n", encoding="utf-8")

            result = subprocess.run(
                [
                    str(SKILL_ROOT / "scripts/task-brief"),
                    str(plan),
                    "9.9",
                    str(brief),
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 3)
            self.assertIn("task 9.9 not found", result.stderr)

    def test_workspaces_are_scoped_by_openspec_change(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            subprocess.run(
                ["git", "init", "--quiet"], cwd=repository, check=True
            )
            workspaces = []
            for change_id in ("change-a", "change-b"):
                plan = repository / "openspec/changes" / change_id / "tasks.md"
                plan.parent.mkdir(parents=True)
                plan.write_text("- [ ] 1.1 Example.\n", encoding="utf-8")
                result = subprocess.run(
                    [str(SKILL_ROOT / "scripts/sdd-workspace"), str(plan)],
                    cwd=repository,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                workspaces.append(Path(result.stdout.strip()))

            self.assertNotEqual(workspaces[0], workspaces[1])
            self.assertEqual(workspaces[0].name, "change-a")
            self.assertEqual(workspaces[1].name, "change-b")

    def test_openspec_is_the_only_task_authority(self):
        skill = read_skill_file("SKILL.md")
        for required in (
            "approved OpenSpec change",
            "decimal checkbox ID",
            "[x]",
            "$openspec-explore",
            "$openspec-update-change",
            "never\nread or create a `docs/superpowers` plan",
        ):
            self.assertIn(required, skill)
        self.assertIn("Do not create a parallel discovery or planning flow", skill)
        self.assertIn("`brainstorming`", skill)
        self.assertIn("`writing-plans`", skill)
        self.assertNotIn("executing-plans", skill)

    def test_named_profiles_and_human_gates_are_required(self):
        skill = read_skill_file("SKILL.md")
        implementer = read_skill_file("implementer-prompt.md")
        reviewer = read_skill_file("task-reviewer-prompt.md")
        re_reviewer = read_skill_file("re-review-prompt.md")

        self.assertIn("every Human Gate", skill)
        self.assertIn("Agent profile: implementer", implementer)
        self.assertIn("Agent profile: reviewer", reviewer)
        self.assertIn("Agent profile: reviewer", re_reviewer)

    def test_validator_evidence_precedes_contextual_review(self):
        skill = read_skill_file("SKILL.md")
        reviewer = read_skill_file("task-reviewer-prompt.md")

        for required in (
            "Deterministic validation runs before contextual review",
            "missing, stale, failed, or unauthorized-skipped",
            "Validation Contract",
        ):
            self.assertIn(required, skill)
        for required in (
            "[OPENSPEC_ARTIFACTS]",
            "[REPOSITORY_RULES]",
            "[VALIDATOR_EVIDENCE]",
            "You may not waive deterministic evidence",
        ):
            self.assertIn(required, reviewer)

    def test_controlled_completion_replaces_autonomous_commit_review_and_cleanup(self):
        """Catches SDD instructions that bypass repository-local completion controls."""
        skill = read_skill_file("SKILL.md")

        self.assertIn("Do not commit", skill)
        self.assertIn("repository-local reviewer dispatch", skill)
        self.assertIn("Stop before controlled completion", skill)
        self.assertNotIn("superpowers:requesting-code-review", skill)
        self.assertNotIn("superpowers:finishing-a-development-branch", skill)
        self.assertNotIn("rm -rf <workspace>", skill)

    def test_review_package_captures_uncommitted_task_and_fix_round_content(self):
        """Catches review packages that omit index, worktree, or untracked fixes."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "SDD tests"], cwd=repository, check=True)
            plan = repository / "openspec/changes/example/tasks.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("- [ ] 1.1 Example.\n", encoding="utf-8")
            tracked = repository / "tracked.txt"
            tracked.write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "--quiet", "-m", "test: base"], cwd=repository, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
            tracked.write_text("unstaged\n", encoding="utf-8")
            staged = repository / "staged.txt"
            staged.write_text("staged\n", encoding="utf-8")
            subprocess.run(["git", "add", "staged.txt"], cwd=repository, check=True)
            untracked = repository / "untracked.txt"
            untracked.write_text("untracked\n", encoding="utf-8")
            output = repository / "review.diff"

            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(output)],
                cwd=repository, capture_output=True, text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            package = output.read_text(encoding="utf-8")
            for expected in ("## Staged changes", "## Unstaged changes", "## Untracked files", "staged.txt", "tracked.txt", "untracked.txt"):
                self.assertIn(expected, package)
            untracked.write_text("fix-round untracked\n", encoding="utf-8")
            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(output)],
                cwd=repository, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("fix-round untracked", output.read_text(encoding="utf-8"))

    def test_review_package_has_no_staged_diff_for_clean_multi_commit_task(self):
        """Catches committed task changes being repeated as staged changes."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "SDD tests"], cwd=repository, check=True)
            plan = repository / "openspec/changes/example/tasks.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("- [ ] 1.1 Example.\n", encoding="utf-8")
            tracked = repository / "tracked.txt"
            tracked.write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "--quiet", "-m", "test: base"], cwd=repository, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
            tracked.write_text("first committed change\n", encoding="utf-8")
            subprocess.run(["git", "commit", "--quiet", "-am", "test: first task change"], cwd=repository, check=True)
            tracked.write_text("second committed change\n", encoding="utf-8")
            subprocess.run(["git", "commit", "--quiet", "-am", "test: second task change"], cwd=repository, check=True)
            output = repository / "review.diff"

            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(output)],
                cwd=repository, capture_output=True, text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            staged = output.read_text(encoding="utf-8").split("## Staged changes\n", 1)[1].split(
                "## Unstaged changes\n", 1
            )[0]
            self.assertEqual(staged.strip(), "")

    def test_review_package_staged_diff_excludes_committed_task_changes(self):
        """Catches staged output that includes committed changes before HEAD."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "SDD tests"], cwd=repository, check=True)
            plan = repository / "openspec/changes/example/tasks.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("- [ ] 1.1 Example.\n", encoding="utf-8")
            tracked = repository / "tracked.txt"
            tracked.write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "--quiet", "-m", "test: base"], cwd=repository, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
            tracked.write_text("committed task change\n", encoding="utf-8")
            subprocess.run(["git", "commit", "--quiet", "-am", "test: committed task change"], cwd=repository, check=True)
            staged = repository / "staged.txt"
            staged.write_text("index-only change\n", encoding="utf-8")
            subprocess.run(["git", "add", "staged.txt"], cwd=repository, check=True)
            output = repository / "review.diff"

            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(output)],
                cwd=repository, capture_output=True, text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            staged_section = output.read_text(encoding="utf-8").split("## Staged changes\n", 1)[1].split(
                "## Unstaged changes\n", 1
            )[0]
            self.assertIn("staged.txt", staged_section)
            self.assertIn("index-only change", staged_section)
            self.assertNotIn("tracked.txt", staged_section)
            self.assertNotIn("committed task change", staged_section)

    def test_rereview_package_uses_only_the_receipt_bound_uncommitted_fix_delta(self):
        """Catches re-reviews that repeat all dirty content from before the review."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "SDD tests"], cwd=repository, check=True)
            plan = repository / "openspec/changes/example/tasks.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("- [ ] 1.1 Example.\n", encoding="utf-8")
            tracked = repository / "tracked.txt"
            tracked.write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "--quiet", "-m", "test: base"], cwd=repository, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
            prior = repository / "prior-review.txt"
            prior.write_text("pre-review dirty content\n", encoding="utf-8")
            ignored = repository / "secret.txt"
            (repository / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
            ignored.write_text("must not enter snapshot\n", encoding="utf-8")
            receipt = repository / "receipt.json"
            receipt.write_text(json.dumps({"dispatch_id": "a" * 32, "diff_identity": "b" * 64}), encoding="utf-8")
            initial = repository / "initial.diff"
            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(initial), "--snapshot", str(receipt)],
                cwd=repository, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("pre-review dirty content", initial.read_text(encoding="utf-8"))
            (repository / ".gitignore").write_text(
                "secret.txt\nprior-review.txt\n", encoding="utf-8"
            )
            prior.write_text("ignored after snapshot\n", encoding="utf-8")
            fix = repository / "fix.txt"
            fix.write_text("uncommitted fix\n", encoding="utf-8")
            rereview = repository / "rereview.diff"
            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(rereview), "--re-review", str(receipt)],
                cwd=repository, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            package = rereview.read_text(encoding="utf-8")
            self.assertIn("uncommitted fix", package)
            self.assertNotIn("must not enter snapshot", package)
            self.assertNotIn("ignored after snapshot", package)
            missing = repository / "missing.json"
            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(rereview), "--re-review", str(missing)],
                cwd=repository, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            receipt.write_text(json.dumps({"dispatch_id": "a" * 32, "diff_identity": "c" * 64}), encoding="utf-8")
            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(rereview), "--re-review", str(receipt)],
                cwd=repository, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_review_packages_never_dereference_an_untracked_external_symlink(self):
        """Catches review-package reads that escape the assigned worktree via symlinks."""
        with tempfile.TemporaryDirectory() as temporary_directory, tempfile.TemporaryDirectory() as outside_directory:
            repository = Path(temporary_directory)
            sentinel = Path(outside_directory) / "outside-sentinel.txt"
            sentinel.write_text("outside worktree sentinel\n", encoding="utf-8")
            subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repository, check=True)
            subprocess.run(["git", "config", "user.name", "SDD tests"], cwd=repository, check=True)
            plan = repository / "openspec/changes/example/tasks.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("- [ ] 1.1 Example.\n", encoding="utf-8")
            (repository / "tracked.txt").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(["git", "commit", "--quiet", "-m", "test: base"], cwd=repository, check=True)
            base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
            receipt = repository / "receipt.json"
            receipt.write_text(json.dumps({"dispatch_id": "b" * 32, "diff_identity": "c" * 64}), encoding="utf-8")
            link = repository / "outside-link"
            link.symlink_to(sentinel)
            initial = repository / "initial.diff"
            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(initial)],
                cwd=repository, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("outside worktree sentinel", initial.read_text(encoding="utf-8") if initial.exists() else "")
            snapshot = repository / "snapshot.diff"
            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(snapshot), "--snapshot", str(receipt)],
                cwd=repository, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("outside worktree sentinel", snapshot.read_text(encoding="utf-8") if snapshot.exists() else "")

            link.unlink()
            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(snapshot), "--snapshot", str(receipt)],
                cwd=repository, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            link.symlink_to(sentinel)
            rereview = repository / "rereview.diff"
            result = subprocess.run(
                [str(SKILL_ROOT / "scripts/review-package"), str(plan), base, "HEAD", str(rereview), "--re-review", str(receipt)],
                cwd=repository, capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("outside worktree sentinel", rereview.read_text(encoding="utf-8") if rereview.exists() else "")

    def test_sdd_prompts_use_receipts_json_verdicts_and_bounded_commit_authority(self):
        """Catches an SDD route that cannot produce repository-local review evidence."""
        skill = read_skill_file("SKILL.md")
        implementer = read_skill_file("implementer-prompt.md")
        reviewer = read_skill_file("task-reviewer-prompt.md")
        re_reviewer = read_skill_file("re-review-prompt.md")

        self.assertNotIn("Commit your work", implementer)
        self.assertIn("[COMMIT_AUTHORITY]", implementer)
        self.assertIn("issued `prepare_dispatch` receipt", skill)
        self.assertIn("persist_reviewer_result", skill)
        self.assertIn("hand off to `implementation-loop`", skill)
        self.assertIn("real unresolved Important or Critical", skill)
        for prompt in (reviewer, re_reviewer):
            for required in (
                "[REVIEW_DISPATCH_RECEIPT]",
                "[REVIEW_REPORT_PATH]",
                '"verdict"',
                "APPROVED",
                "NEEDS_FIXES",
                "BLOCKED",
                "unresolved_important_or_critical_findings",
                ):
                self.assertIn(required, prompt)
            self.assertIn("Return exactly one JSON object", prompt)
            self.assertIn("The controller persists that exact result", prompt)
        self.assertNotIn("Write exactly one JSON object to [REVIEW_REPORT_PATH]", prompt)

    def test_rereview_prompt_allows_addressed_material_findings_in_an_approved_result(self):
        """Catches prompt guidance that contradicts the compact result parser."""
        prompt = read_skill_file("re-review-prompt.md")
        self.assertIn("ADDRESSED finding of any severity", prompt)

    def test_sdd_requires_receipt_bound_snapshots_for_scoped_rereviews(self):
        """Catches instructions that scope a re-review from HEAD instead of prior review state."""
        skill = read_skill_file("SKILL.md")
        prompt = read_skill_file("re-review-prompt.md")
        self.assertIn("--snapshot REVIEW_DISPATCH_RECEIPT", skill)
        self.assertIn("--re-review PRIOR_REVIEW_DISPATCH_RECEIPT", skill)
        self.assertIn("[PRIOR_REVIEW_DISPATCH_RECEIPT]", prompt)
        self.assertIn("receipt-bound snapshot", prompt)

    def test_breaker_diagram_blocks_real_findings_and_inventory_records_local_adaptation(self):
        """Catches obsolete parking paths and missing current documentation."""
        skill = read_skill_file("SKILL.md")
        comparison = (REPOSITORY_ROOT / "docs/agentic-workflow/skill-comparison.md").read_text(
            encoding="utf-8"
        )

        self.assertIn('"Real unresolved Important or Critical finding?"', skill)
        self.assertIn('"STOP: report BLOCKED to human partner"', skill)
        self.assertNotIn('"Any load-bearing finding?"', skill)
        self.assertNotIn('"Park findings in ledger with rulings"', skill)
        self.assertNotIn('"Park findings in ledger with rulings" -> "Append completion', skill)
        self.assertIn("Locally adapted skills", comparison)
        self.assertIn("`subagent-driven-development`", comparison)
        self.assertIn("registered implementer and reviewer profiles", comparison)
        self.assertNotIn("Five separate Human Gates", comparison)


if __name__ == "__main__":
    unittest.main()
