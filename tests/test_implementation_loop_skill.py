import importlib.util
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from datetime import UTC, datetime
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
OPENAI_YAML_PATH = (
    REPOSITORY_ROOT / ".agents/skills/implementation-loop/agents/openai.yaml"
)
STATE_HELPER_PATH = REPOSITORY_ROOT / ".agents/skills/implementation-loop/scripts/execution_state.py"


def read_required(path):
    assert path.is_file(), f"required skill file is missing: {path.relative_to(REPOSITORY_ROOT)}"
    return path.read_text(encoding="utf-8")


def load_state_helper():
    assert STATE_HELPER_PATH.is_file(), "execution-state helper is missing"
    spec = importlib.util.spec_from_file_location("execution_state", STATE_HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capture(callable_, *args, **kwargs):
    try:
        return None, callable_(*args, **kwargs)
    except Exception as error:  # The asserted exception type is part of each test.
        return error, None


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GitEvidenceFixture:
    """A real local Git worktree with the canonical validator and contract."""

    def __enter__(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name) / "repository"
        self.repository.mkdir()
        self._git("init", "--quiet")
        self._git("config", "user.email", "tests@example.invalid")
        self._git("config", "user.name", "Implementation Loop Tests")
        validator_target = self.repository / "tools/agentic_workflow/validate.py"
        validator_target.parent.mkdir(parents=True)
        shutil.copy2(REPOSITORY_ROOT / "tools/agentic_workflow/validate.py", validator_target)
        contract_target = self.repository / "docs/agentic-workflow/validation-contract.md"
        contract_target.parent.mkdir(parents=True)
        contract_target.write_text(
            """# Validation Contract

## Gate registry

| Order | Gate ID | Applicability | Mandatory | Timeout | Command |
|---:|---|---|---|---:|---|
| 10 | always-pass | always | yes | 5 | `python3 -c \"from pathlib import Path; assert Path('tracked.txt').is_file()\"` |
| 20 | present-path | path:present | yes | 5 | `python3 -c \"print('present')\"` |
| 30 | absent-path | path:absent | yes | 5 | `python3 -c \"raise SystemExit(9)\"` |
""",
            encoding="utf-8",
        )
        (self.repository / ".gitignore").write_text(
            ".agentic-workflow/\n", encoding="utf-8"
        )
        (self.repository / "tracked.txt").write_text("base\n", encoding="utf-8")
        (self.repository / "present").mkdir()
        (self.repository / "present/.keep").write_text("present\n", encoding="utf-8")
        self._git("add", ".")
        self._git("commit", "--quiet", "-m", "test: initialize evidence repository")
        (self.repository / "tracked.txt").write_text("authorized change\n", encoding="utf-8")
        self.validator = load_module(
            validator_target,
            f"test_validator_{id(self)}",
        )
        bytecode = validator_target.parent / "__pycache__"
        if bytecode.exists():
            shutil.rmtree(bytecode)
        self.evidence_relative = Path(".agentic-workflow/validation-evidence.json")
        self.evidence_path = self.repository / self.evidence_relative
        self.invoke_validator()
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.temporary.cleanup()

    def _git(self, *arguments):
        completed = subprocess.run(
            ["git", "-C", str(self.repository), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr)
        return completed.stdout.strip()

    def evidence(self):
        return json.loads(self.evidence_path.read_text(encoding="utf-8"))

    def write_evidence(self, evidence):
        self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_path.write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )

    def invoke_validator(self):
        contract = self.repository / "docs/agentic-workflow/validation-contract.md"
        completed = subprocess.run(
            [
                sys.executable,
                str(self.repository / "tools/agentic_workflow/validate.py"),
                "--repository",
                str(self.repository),
                "--contract",
                str(contract),
                "--output",
                str(self.evidence_path),
            ],
            cwd=self.repository,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stdout + completed.stderr)

    def implementing_state(self, helper):
        state = helper.new_state("change", "5.4", str(self.repository.resolve()))
        return helper.transition(
            state,
            "implementing",
            base_identity=self._git("rev-parse", "HEAD"),
        )

    def validated_state(self, helper):
        return helper.run_canonical_validation(
            self.implementing_state(helper), "implementer.md"
        )

    def expected_diff_identity(self):
        revision = self._git("rev-parse", "HEAD")
        digest = self.validator.repository_identity(
            self.repository, self.evidence_path
        )["worktree_digest"]
        return hashlib.sha256(
            f"{revision}\0{digest}".encode("utf-8")
        ).hexdigest()

    def persisted_validated_state(self, helper):
        state = self.implementing_state(helper)
        evidence = self.evidence()
        state.update(
            {
                "phase": "validated",
                "diff_identity": self.expected_diff_identity(),
                "implementer_report": "implementer.md",
                "validator_evidence_path": str(self.evidence_relative),
                "validator_hash": hashlib.sha256(
                    self.evidence_path.read_bytes()
                ).hexdigest(),
                "validator_worktree_digest": evidence["repository"]["worktree_digest"],
                "validator_status": "pass",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        helper.validate_state(state)
        return state


def complete_assignment(helper, profile="implementer", **overrides):
    arguments = {
        "profile": profile,
        "task_id": "5.4",
        "worktree": "/worktree",
        "sources": ["proposal.md", "design.md", "spec.md"],
        "acceptance": "focused tests and validator pass",
        "allowed_scope": ["implementation-loop", "focused tests"],
        "required_tests": ["python3 -m unittest tests.test_implementation_loop_skill -v"],
        "prohibited_actions": ["no external writes", "no commit"],
        "report_path": ".superpowers/sdd/tasks/task-5-4-report.md",
    }
    arguments.update(overrides)
    return helper.prepare_dispatch(**arguments)


def state_fixture(helper, phase):
    state = helper.new_state("establish-agentic-implementation-workflow", "5.4", "/worktree")
    state["base_identity"] = "base-commit"
    if phase in {"validated", "review", "blocked", "fixing", "approved"}:
        state.update(
            {
                "diff_identity": "diff-sha256",
                "implementer_report": "task-5-4-report.md",
                "validator_evidence_path": ".agentic-workflow/validation-evidence.json",
                "validator_hash": "a" * 64,
                "validator_worktree_digest": "b" * 64,
                "validator_status": "pass",
            }
        )
    if phase == "blocked":
        state["pending_gate"] = "gate-approval-42"
    if phase == "fixing":
        state.update(
            {
                "reviewer_report": "review-task-5-4.md",
                "reviewer_verdict": "NEEDS_FIXES",
                "fix_round": 1,
            }
        )
    if phase == "approved":
        state.update(
            {
                "reviewer_report": "review-task-5-4.md",
                "reviewer_verdict": "APPROVED",
            }
        )
    state["phase"] = phase
    return state


class ImplementationLoopSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = load_state_helper()

    def prepare_fixture_review(self, fixture, state):
        return complete_assignment(
            self.helper,
            profile="reviewer",
            worktree=str(fixture.repository.resolve()),
            state=state,
        )

    def write_reviewer_report(self, fixture, assignment, verdict, findings=0):
        if verdict == "NEEDS_FIXES" and findings == 0:
            findings = 1
        result = {
                    "review_kind": assignment["review_dispatch"]["kind"],
                    "profile": "reviewer",
                    "dispatch_id": assignment["review_dispatch"]["dispatch_id"],
                    "task_id": assignment["task_id"],
                    "diff_identity": assignment["diff_identity"],
                    "verdict": verdict,
                    "unresolved_important_or_critical_findings": findings,
                    "spec_compliance": "APPROVED" if verdict == "APPROVED" else "NEEDS_FIXES",
                    "quality": "APPROVED",
                }
        if verdict == "NEEDS_FIXES":
            result["findings"] = [{"id": "I-1", "severity": "Important", "location": "test:1", "description": "test finding"}]
        return self.helper.persist_reviewer_result(
            str(fixture.repository), assignment["review_dispatch"], json.dumps(result)
        )

    def write_coverage_gap_report(self, fixture, assignment):
        """Write an independent report that recommends, but cannot apply, a delta."""
        return self.helper.persist_reviewer_result(
            str(fixture.repository), assignment["review_dispatch"], json.dumps({
                    "review_kind": assignment["review_dispatch"]["kind"],
                    "profile": "reviewer",
                    "dispatch_id": assignment["review_dispatch"]["dispatch_id"],
                    "task_id": assignment["task_id"],
                    "diff_identity": assignment["diff_identity"],
                    "verdict": "BLOCKED",
                    "unresolved_important_or_critical_findings": 0,
                    "spec_compliance": "CANNOT_VERIFY",
                    "quality": "APPROVED",
                    "coverage_gap": {
                        "material_risk": "The current registry does not run the security scan.",
                        "recommended_contract_delta": "Add a mandatory security-scan gate.",
                    },
                })
        )

    def test_native_metadata_keeps_the_implementation_loop_invocable(self):
        """Catches removal or misregistration of the native skill metadata."""
        metadata = read_required(OPENAI_YAML_PATH)
        self.assertIn('display_name: "Implementation Loop"', metadata)
        self.assertIn("short_description:", metadata)
        self.assertIn("$implementation-loop", metadata)

    def test_implementer_dispatch_preserves_each_bounded_assignment_field_and_omits_model(self):
        """Catches dropped scope/evidence/authority fields or an invented model override."""
        assignment = complete_assignment(self.helper)
        self.assertEqual(
            assignment,
            {
                "profile": "implementer",
                "task_id": "5.4",
                "worktree": "/worktree",
                "sources": ["proposal.md", "design.md", "spec.md"],
                "acceptance_evidence": "focused tests and validator pass",
                "allowed_scope": ["implementation-loop", "focused tests"],
                "required_tests": ["python3 -m unittest tests.test_implementation_loop_skill -v"],
                "prohibited_external_actions": ["no external writes", "no commit"],
                "report_path": ".superpowers/sdd/tasks/task-5-4-report.md",
            },
        )

    def test_general_purpose_dispatch_rejects_missing_authority_or_any_incomplete_assignment(self):
        """Catches an unapproved or unbounded general-purpose escape hatch."""
        with self.assertRaises(PermissionError):
            complete_assignment(self.helper, profile="general-purpose")
        for missing in (
            "sources",
            "acceptance",
            "allowed_scope",
            "required_tests",
            "prohibited_actions",
            "report_path",
        ):
            override = [] if missing not in {"acceptance", "report_path"} else ""
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                complete_assignment(
                    self.helper,
                    profile="general-purpose",
                    caller_authorized=True,
                    **{missing: override},
                )

    def test_reviewer_dispatch_derives_current_diff_and_validator_identity_from_validated_state(self):
        """Catches caller-supplied, stale, or omitted review evidence identity."""
        with GitEvidenceFixture() as fixture:
            state = fixture.persisted_validated_state(self.helper)
            error, assignment = capture(
                complete_assignment,
                self.helper,
                profile="reviewer",
                worktree=str(fixture.repository.resolve()),
                state=state,
            )
            self.assertIsNone(error)
            self.assertEqual(
                assignment.get("diff_identity"), fixture.expected_diff_identity()
            )
            self.assertEqual(
                assignment.get("implementer_report"), "implementer.md"
            )
            self.assertEqual(
                assignment.get("validator_evidence"),
                {
                    "path": str(fixture.evidence_relative),
                    "sha256": hashlib.sha256(
                        fixture.evidence_path.read_bytes()
                    ).hexdigest(),
                    "worktree_digest": fixture.evidence()["repository"][
                        "worktree_digest"
                    ],
                    "contract_sha256": hashlib.sha256(
                        (
                            fixture.repository
                            / "docs/agentic-workflow/validation-contract.md"
                        ).read_bytes()
                    ).hexdigest(),
                    "status": "pass",
                },
            )
            for mismatch in ({"task_id": "5.3"}, {"worktree": "/other"}):
                with self.subTest(mismatch=mismatch), self.assertRaises(PermissionError):
                    overrides = {
                        "worktree": str(fixture.repository.resolve()),
                        "state": state,
                    }
                    overrides.update(mismatch)
                    complete_assignment(self.helper, profile="reviewer", **overrides)

    def test_canonical_validation_precedes_review_and_hands_over_exact_contract_bound_evidence(self):
        """Catches contextual review before a real validation handoff or without its contract identity."""
        with GitEvidenceFixture() as fixture:
            implementing = fixture.implementing_state(self.helper)
            with self.assertRaises(PermissionError):
                self.prepare_fixture_review(fixture, implementing)

            validated = self.helper.run_canonical_validation(
                implementing, "implementer.md"
            )
            assignment = self.prepare_fixture_review(fixture, validated)
            evidence_bytes = fixture.evidence_path.read_bytes()
            self.assertEqual(
                assignment["validator_evidence"],
                {
                    "path": str(fixture.evidence_relative),
                    "sha256": hashlib.sha256(evidence_bytes).hexdigest(),
                    "worktree_digest": fixture.evidence()["repository"][
                        "worktree_digest"
                    ],
                    "contract_sha256": hashlib.sha256(
                        (
                            fixture.repository
                            / "docs/agentic-workflow/validation-contract.md"
                        ).read_bytes()
                    ).hexdigest(),
                    "status": "pass",
                },
            )

    def test_real_validation_evidence_rejects_missing_stale_skipped_or_failed_mandatory_gates(self):
        """Catches attempts to waive invalid evidence after the canonical validator has run."""
        for mutation in ("missing", "stale", "unauthorized-skip", "failed"):
            with self.subTest(mutation=mutation), GitEvidenceFixture() as fixture:
                validated = self.helper.run_canonical_validation(
                    fixture.implementing_state(self.helper), "implementer.md"
                )
                if mutation == "missing":
                    fixture.evidence_path.unlink()
                else:
                    evidence = fixture.evidence()
                    if mutation == "stale":
                        evidence["generated_at"] = "2099-01-01T00:00:00+00:00"
                    elif mutation == "unauthorized-skip":
                        evidence["gates"][0].update(
                            {
                                "status": "skipped",
                                "reason": "skipped without recorded authority",
                            }
                        )
                    else:
                        evidence["gates"][0]["status"] = "fail"
                    fixture.write_evidence(evidence)
                    if mutation in {"unauthorized-skip", "failed"}:
                        validated["validator_hash"] = hashlib.sha256(
                            fixture.evidence_path.read_bytes()
                        ).hexdigest()

                expected_error = {
                    "missing": "validator evidence file is missing",
                    "stale": "validator evidence is stale or mutated",
                    "unauthorized-skip": "mandatory validator gate did not pass",
                    "failed": "mandatory validator gate did not pass",
                }[mutation]
                with self.assertRaisesRegex(PermissionError, expected_error):
                    self.helper._verify_validator_evidence(validated)
                with self.assertRaisesRegex(PermissionError, expected_error):
                    self.prepare_fixture_review(fixture, validated)

    def test_reviewer_dispatch_blocks_missing_or_edited_evidence_file(self):
        """Catches reviewer dispatch after validator evidence disappears or changes."""
        for mutation in ("missing", "edited"):
            with self.subTest(mutation=mutation), GitEvidenceFixture() as fixture:
                state = fixture.persisted_validated_state(self.helper)
                if mutation == "missing":
                    fixture.evidence_path.unlink()
                else:
                    evidence = fixture.evidence()
                    evidence["generated_at"] = "2099-01-01T00:00:00+00:00"
                    fixture.write_evidence(evidence)
                with self.assertRaises(PermissionError):
                    self.prepare_fixture_review(fixture, state)

    def test_reviewer_dispatch_blocks_failed_or_missing_mandatory_gate(self):
        """Catches trusting overall pass when current mandatory gate evidence is bad."""
        for mutation in ("failed", "skipped", "missing"):
            with self.subTest(mutation=mutation), GitEvidenceFixture() as fixture:
                evidence = fixture.evidence()
                if mutation == "failed":
                    evidence["gates"][0]["status"] = "fail"
                elif mutation == "skipped":
                    evidence["gates"][0]["status"] = "skipped"
                else:
                    evidence["gates"] = evidence["gates"][1:]
                fixture.write_evidence(evidence)
                state = fixture.persisted_validated_state(self.helper)
                with self.assertRaises(PermissionError):
                    self.prepare_fixture_review(fixture, state)

    def test_reviewer_dispatch_rechecks_exact_gate_registry_and_applicability(self):
        """Catches forged N/A results or evidence that differs from the current contract."""
        mutations = (
            "always-not-applicable",
            "present-not-applicable",
            "absent-pass",
            "altered-command",
            "altered-order",
            "altered-applicability",
            "altered-mandatory",
            "extra-gate",
            "reordered-gates",
            "duplicate-gate",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), GitEvidenceFixture() as fixture:
                evidence = fixture.evidence()
                if mutation == "always-not-applicable":
                    evidence["gates"][0]["status"] = "not-applicable"
                elif mutation == "present-not-applicable":
                    evidence["gates"][1]["status"] = "not-applicable"
                elif mutation == "absent-pass":
                    evidence["gates"][2]["status"] = "pass"
                elif mutation == "altered-command":
                    evidence["gates"][0]["command"] += " --altered"
                elif mutation == "altered-order":
                    evidence["gates"][0]["order"] = 99
                elif mutation == "altered-applicability":
                    evidence["gates"][0]["applicability"] = "path:absent"
                elif mutation == "altered-mandatory":
                    evidence["gates"][0]["mandatory"] = False
                elif mutation == "extra-gate":
                    extra = dict(evidence["gates"][0])
                    extra.update({"id": "extra", "order": 40, "mandatory": False})
                    evidence["gates"].append(extra)
                elif mutation == "reordered-gates":
                    evidence["gates"][0], evidence["gates"][1] = (
                        evidence["gates"][1],
                        evidence["gates"][0],
                    )
                elif mutation == "duplicate-gate":
                    evidence["gates"].append(dict(evidence["gates"][0]))
                fixture.write_evidence(evidence)
                state = fixture.persisted_validated_state(self.helper)
                with self.assertRaises(PermissionError):
                    self.prepare_fixture_review(fixture, state)

    def test_reviewer_dispatch_blocks_changed_worktree_or_contract(self):
        """Catches review after dirty contents or the current contract changed."""
        for mutation in ("worktree", "contract"):
            with self.subTest(mutation=mutation), GitEvidenceFixture() as fixture:
                state = fixture.persisted_validated_state(self.helper)
                if mutation == "worktree":
                    (fixture.repository / "tracked.txt").write_text(
                        "changed after validation\n", encoding="utf-8"
                    )
                else:
                    contract = (
                        fixture.repository
                        / "docs/agentic-workflow/validation-contract.md"
                    )
                    contract.write_text(
                        contract.read_text(encoding="utf-8") + "\nChanged after validation.\n",
                        encoding="utf-8",
                    )
                with self.assertRaises(PermissionError):
                    self.prepare_fixture_review(fixture, state)

    def test_reviewer_dispatch_blocks_wrong_repository_path_or_revision(self):
        """Catches evidence copied from another repository or Git revision."""
        for field, value in (("path", "/another/repository"), ("git_revision", "f" * 40)):
            with self.subTest(field=field), GitEvidenceFixture() as fixture:
                evidence = fixture.evidence()
                evidence["repository"][field] = value
                fixture.write_evidence(evidence)
                state = fixture.persisted_validated_state(self.helper)
                with self.assertRaises(PermissionError):
                    self.prepare_fixture_review(fixture, state)

    def test_reviewer_dispatch_blocks_changed_contract_hash_inside_evidence(self):
        """Catches evidence bound to a different Validation Contract."""
        with GitEvidenceFixture() as fixture:
            evidence = fixture.evidence()
            evidence["contract_hash"] = "f" * 64
            fixture.write_evidence(evidence)
            state = fixture.persisted_validated_state(self.helper)
            with self.assertRaises(PermissionError):
                self.prepare_fixture_review(fixture, state)

    def test_reviewer_dispatch_rejects_structurally_incomplete_validator_evidence(self):
        """Catches fabricated pass evidence that omits canonical validator fields."""
        for location, field in (
            ("top-level", "generated_at"),
            ("gate", "duration_seconds"),
            ("gate", "exit_code"),
            ("gate", "reason"),
            ("gate", "output"),
        ):
            with self.subTest(location=location, field=field), GitEvidenceFixture() as fixture:
                evidence = fixture.evidence()
                target = evidence if location == "top-level" else evidence["gates"][0]
                del target[field]
                fixture.write_evidence(evidence)
                with self.assertRaises(PermissionError):
                    self.prepare_fixture_review(fixture, fixture.persisted_validated_state(self.helper))

    def test_reviewer_dispatch_blocks_arbitrary_diff_identity(self):
        """Catches a caller-selected diff identity unrelated to current Git state."""
        with GitEvidenceFixture() as fixture:
            state = fixture.persisted_validated_state(self.helper)
            state["diff_identity"] = "f" * 64
            with self.assertRaises(PermissionError):
                self.prepare_fixture_review(fixture, state)

    def test_selection_uses_file_order_and_separate_normal_and_prerequisite_authority(self):
        """Catches reordering or selection outside caller-supplied authority."""
        tasks = "- [ ] 5.2 prerequisite\n- [ ] 5.4 normal\n- [ ] 5.5 unauthorized\n"
        error, selected = capture(
            self.helper.select_task,
            tasks,
            {"5.4"},
            None,
            {"5.2"},
            expected_change_id="establish-agentic-implementation-workflow",
        )
        self.assertIsNone(error)
        self.assertEqual(
            selected,
            "5.2",
        )
        error, selected = capture(
            self.helper.select_task,
            tasks,
            {"5.4"},
            None,
            set(),
            expected_change_id="establish-agentic-implementation-workflow",
        )
        self.assertIsNone(error)
        self.assertEqual(selected, "5.4")
        error, selected = capture(
            self.helper.select_task,
            tasks,
            set(),
            None,
            set(),
            expected_change_id="establish-agentic-implementation-workflow",
        )
        self.assertIsNone(error)
        self.assertIsNone(selected)

    def test_persisted_task_resumes_only_with_current_authority_for_the_same_change(self):
        """Catches persisted state authorizing revoked work or crossing change boundaries."""
        tasks = "- [ ] 5.4 active\n- [ ] 5.5 next\n"
        state = state_fixture(self.helper, "selected")
        error, selected = capture(
            self.helper.select_task,
            tasks,
            {"5.4"},
            state,
            set(),
            expected_change_id="establish-agentic-implementation-workflow",
        )
        self.assertIsNone(error)
        self.assertEqual(selected, "5.4")
        self.assertIsNone(
            self.helper.select_task(
                tasks,
                set(),
                state,
                set(),
                expected_change_id="establish-agentic-implementation-workflow",
            )
        )
        self.assertEqual(
            self.helper.select_task(
                tasks,
                {"5.5"},
                state,
                set(),
                expected_change_id="establish-agentic-implementation-workflow",
            ),
            "5.5",
        )
        other_change = dict(state, change_id="another-change")
        with self.assertRaises(PermissionError):
            self.helper.select_task(
                tasks,
                {"5.4"},
                other_change,
                set(),
                expected_change_id="establish-agentic-implementation-workflow",
            )

    def test_execution_state_io_is_bound_to_canonical_change_path_and_identity(self):
        """Catches traversal, arbitrary state paths, or loading another change's state."""
        path_builder = getattr(self.helper, "execution_state_path", None)
        self.assertIsNotNone(path_builder, "canonical execution-state path constructor is absent")
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            expected = (
                repository.resolve()
                / ".agentic-workflow/executions/establish-agentic-implementation-workflow.json"
            )
            self.assertEqual(
                path_builder(repository, "establish-agentic-implementation-workflow"),
                expected,
            )
            with self.assertRaises(ValueError):
                path_builder(repository, "../another-change")

            state = state_fixture(self.helper, "selected")
            error, _ = capture(
                self.helper.write_state,
                repository,
                "establish-agentic-implementation-workflow",
                state,
            )
            self.assertIsNone(error)
            self.assertTrue(expected.is_file())
            self.assertEqual(
                self.helper.read_state(
                    repository, "establish-agentic-implementation-workflow"
                )["change_id"],
                "establish-agentic-implementation-workflow",
            )
            with self.assertRaises(ValueError):
                self.helper.write_state(repository, "another-change", state)
            expected.write_text(
                json.dumps(dict(state, change_id="another-change")), encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                self.helper.read_state(
                    repository, "establish-agentic-implementation-workflow"
                )

    def test_persisted_interruption_recovers_selected_validated_blocked_fixing_and_approved(self):
        """Catches loss of any resumable phase before its authoritative checkbox update."""
        tasks = "- [ ] 5.4 active\n- [ ] 5.5 next\n"
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            for phase in ("selected", "validated", "blocked", "fixing", "approved"):
                with self.subTest(phase=phase):
                    error, _ = capture(
                        self.helper.write_state,
                        repository,
                        "establish-agentic-implementation-workflow",
                        state_fixture(self.helper, phase),
                    )
                    self.assertIsNone(error)
                    recovered = self.helper.read_state(
                        repository, "establish-agentic-implementation-workflow"
                    )
                    self.assertEqual(
                        self.helper.select_task(
                            tasks,
                            {"5.4", "5.5"},
                            recovered,
                            set(),
                            expected_change_id="establish-agentic-implementation-workflow",
                        ),
                        "5.4",
                    )

    def test_checked_checkbox_overrides_approved_or_other_persisted_state(self):
        """Catches scratch state overriding the canonical checked task."""
        tasks = "- [x] 5.4 complete\n- [ ] 5.5 next\n"
        for phase in ("selected", "validated", "blocked", "fixing", "approved"):
            with self.subTest(phase=phase):
                error, selected = capture(
                    self.helper.select_task,
                    tasks,
                    {"5.5"},
                    state_fixture(self.helper, phase),
                    set(),
                    expected_change_id="establish-agentic-implementation-workflow",
                )
                self.assertIsNone(error)
                self.assertEqual(selected, "5.5")

    def test_state_schema_rejects_extra_wrong_typed_malformed_and_impossible_values(self):
        """Catches corrupt state being trusted on read or write."""
        valid = state_fixture(self.helper, "selected")
        invalid_states = []
        extra = dict(valid, unexpected=True)
        invalid_states.append(extra)
        wrong_schema_type = dict(valid, schema=True)
        invalid_states.append(wrong_schema_type)
        bad_task = dict(valid, task_id="task-five")
        invalid_states.append(bad_task)
        bad_nullable = dict(valid, diff_identity=7)
        invalid_states.append(bad_nullable)
        bad_timestamp = dict(valid, updated_at="yesterday")
        invalid_states.append(bad_timestamp)
        impossible_validated = dict(valid, phase="validated")
        invalid_states.append(impossible_validated)
        negative_time = dict(valid, updated_at="2000-01-01T00:00:00+00:00")
        invalid_states.append(negative_time)
        for index, state in enumerate(invalid_states):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as directory:
                repository = Path(directory)
                error, _ = capture(
                    self.helper.write_state,
                    repository,
                    "establish-agentic-implementation-workflow",
                    state,
                )
                self.assertIsInstance(error, ValueError)
                path_builder = getattr(self.helper, "execution_state_path", None)
                if path_builder is None:
                    continue
                path = path_builder(
                    repository, "establish-agentic-implementation-workflow"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.helper.read_state(
                        repository, "establish-agentic-implementation-workflow"
                    )

    def test_dedicated_validation_operation_runs_canonical_validator_and_persists_identity(self):
        """Catches accepting supplied JSON instead of invoking the assigned validator."""
        with GitEvidenceFixture() as fixture:
            state = fixture.implementing_state(self.helper)
            fixture.evidence_path.unlink()
            operation = getattr(self.helper, "run_canonical_validation", None)
            self.assertIsNotNone(operation, "dedicated validation operation is absent")
            error, result = capture(operation, state, "implementer.md")
            self.assertIsNone(error)
            self.assertEqual(result["phase"], "validated")
            self.assertEqual(result["diff_identity"], fixture.expected_diff_identity())
            self.assertEqual(result["implementer_report"], "implementer.md")
            self.assertEqual(
                result["validator_evidence_path"], str(fixture.evidence_relative)
            )
            self.assertEqual(
                result["validator_hash"],
                hashlib.sha256(fixture.evidence_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(result["validator_status"], "pass")
            self.assertEqual(
                [gate["status"] for gate in fixture.evidence()["gates"]],
                ["pass", "pass", "not-applicable"],
            )

    def test_ordinary_transition_rejects_preexisting_or_caller_shaped_validation_json(self):
        """Catches entering validated without the dedicated validator operation."""
        with GitEvidenceFixture() as fixture:
            state = fixture.implementing_state(self.helper)
            evidence = fixture.evidence()
            evidence["generated_at"] = "2099-01-01T00:00:00+00:00"
            fixture.write_evidence(evidence)
            with self.assertRaises(PermissionError):
                self.helper.transition(
                    state,
                    "validated",
                    implementer_report="implementer.md",
                    validator_evidence_path=str(fixture.evidence_relative),
                )

    def test_dedicated_validation_operation_rejects_validator_failure(self):
        """Catches entering validated when the invoked canonical entrypoint fails."""
        with GitEvidenceFixture() as fixture:
            state = fixture.implementing_state(self.helper)
            contract = fixture.repository / "docs/agentic-workflow/validation-contract.md"
            contract.write_text(
                contract.read_text(encoding="utf-8").replace(
                    "from pathlib import Path; assert Path('tracked.txt').is_file()",
                    "raise SystemExit(9)",
                ),
                encoding="utf-8",
            )
            with self.assertRaises(PermissionError):
                self.helper.run_canonical_validation(state, "implementer.md")
            self.assertEqual(state["phase"], "implementing")

    def test_validated_to_review_uses_persisted_evidence_and_rejects_caller_override(self):
        """Catches review entry based on caller-provided instead of persisted evidence."""
        state = state_fixture(self.helper, "validated")
        try:
            result = self.helper.transition(state, "review")
        except PermissionError:
            result = None
        self.assertIsNotNone(result, "persisted passing evidence did not permit review")
        if result is not None:
            self.assertEqual(result["validator_hash"], "a" * 64)
        with self.assertRaises(ValueError):
            self.helper.transition(state, "review", validator_status="pass")

    def test_review_to_fixing_requires_needs_fixes_report_and_increments_round(self):
        """Catches fix rounds entered without an independent NEEDS_FIXES report."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            state = self.helper.transition(validated, "review")
            with self.assertRaises(PermissionError):
                self.helper.transition(state, "fixing")
            report = self.write_reviewer_report(fixture, assignment, "NEEDS_FIXES")
            fixed = self.helper.transition(
                state,
                "fixing",
                reviewer_verdict="NEEDS_FIXES",
                reviewer_report=report,
            )
            self.assertEqual(fixed["fix_round"], 1)
            self.assertEqual(fixed["reviewer_verdict"], "NEEDS_FIXES")

    def test_fix_round_requires_fresh_validation_before_approved_checkbox_gate(self):
        """Catches approval after fixes without a fresh validator-bound review."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            first_review = self.prepare_fixture_review(fixture, validated)
            reviewing = self.helper.transition(validated, "review")
            needs_fixes = self.write_reviewer_report(
                fixture, first_review, "NEEDS_FIXES"
            )
            fixing = self.helper.transition(
                reviewing,
                "fixing",
                reviewer_verdict="NEEDS_FIXES",
                reviewer_report=needs_fixes,
            )
            implementing = self.helper.transition(fixing, "implementing")
            with self.assertRaises(PermissionError):
                self.helper.transition(
                    implementing,
                    "approved",
                    reviewer_verdict="APPROVED",
                    reviewer_report=needs_fixes,
                )

            refreshed = self.helper.run_canonical_validation(
                implementing, "implementer-round-two.md"
            )
            second_review = self.prepare_fixture_review(fixture, refreshed)
            reviewing = self.helper.transition(refreshed, "review")
            approved_report = self.write_reviewer_report(
                fixture, second_review, "APPROVED"
            )
            approved = self.helper.transition(
                reviewing,
                "approved",
                reviewer_verdict="APPROVED",
                reviewer_report=approved_report,
            )
            self.assertEqual(approved["phase"], "approved")
            self.assertEqual(
                self.helper.select_task(
                    "- [x] 5.4 complete\n- [ ] 5.5 next\n",
                    {"5.4", "5.5"},
                    approved,
                    set(),
                    expected_change_id="change",
                ),
                "5.5",
            )

    def test_checkbox_guard_permits_only_approved_state(self):
        """Catches a controller marking an OpenSpec task before APPROVED."""
        guard = getattr(self.helper, "may_mark_task_complete", None)
        self.assertIsNotNone(guard, "checkbox approval guard is absent")
        for phase in ("selected", "implementing", "validated", "review", "fixing"):
            with self.subTest(phase=phase):
                self.assertFalse(guard(state_fixture(self.helper, phase)))
        self.assertTrue(guard(state_fixture(self.helper, "approved")))

    def test_review_to_approved_requires_approved_report(self):
        """Catches completion approval without an independent APPROVED report."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            state = self.helper.transition(validated, "review")
            with self.assertRaises(PermissionError):
                self.helper.transition(state, "approved", reviewer_verdict="APPROVED")
            report = self.write_reviewer_report(fixture, assignment, "APPROVED")
            approved = self.helper.transition(
                state,
                "approved",
                reviewer_verdict="APPROVED",
                reviewer_report=report,
            )
            self.assertEqual(approved["phase"], "approved")

    def test_read_only_reviewer_result_is_persisted_only_by_the_controller(self):
        """Catches a reviewer path that requires write access to implementation files."""
        reviewer_profile = tomllib.loads(
            (REPOSITORY_ROOT / ".codex/agents/reviewer.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(reviewer_profile["sandbox_mode"], "read-only")
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            returned_result = json.dumps(
                {
                    "review_kind": "task",
                    "profile": "reviewer",
                    "dispatch_id": assignment["review_dispatch"]["dispatch_id"],
                    "task_id": assignment["task_id"],
                    "diff_identity": assignment["diff_identity"],
                    "verdict": "APPROVED",
                    "unresolved_important_or_critical_findings": 0,
                    "spec_compliance": "APPROVED",
                    "quality": "APPROVED",
                }
            )
            report = self.helper.persist_reviewer_result(
                str(fixture.repository.resolve()), assignment["review_dispatch"], returned_result
            )
            self.assertEqual(report, assignment["report_path"])
            reviewing = self.helper.transition(validated, "review")
            approved = self.helper.transition(
                reviewing,
                "approved",
                reviewer_verdict="APPROVED",
                reviewer_report=report,
            )
            self.assertEqual(approved["phase"], "approved")

    def test_reviewer_result_destination_is_receipt_derived_and_failed_replay_preserves_valid_evidence(self):
        """Catches arbitrary result paths and a failed replay deleting valid evidence."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            receipt = assignment["review_dispatch"]
            self.assertTrue(assignment["report_path"].startswith(".agentic-workflow/"))
            self.assertIn(receipt["dispatch_id"], assignment["report_path"])
            returned_result = json.dumps(
                {
                    "review_kind": "task",
                    "profile": "reviewer",
                    "dispatch_id": receipt["dispatch_id"],
                    "task_id": assignment["task_id"],
                    "diff_identity": assignment["diff_identity"],
                    "verdict": "APPROVED",
                    "unresolved_important_or_critical_findings": 0,
                    "spec_compliance": "APPROVED",
                    "quality": "APPROVED",
                }
            )
            report = self.helper.persist_reviewer_result(
                str(fixture.repository.resolve()), receipt, returned_result
            )
            before = (fixture.repository / report).read_bytes()
            forged = dict(receipt)
            forged["task_id"] = "7.3"
            with self.assertRaises(PermissionError):
                self.helper.persist_reviewer_result(
                    str(fixture.repository.resolve()), forged, returned_result
                )
            self.assertEqual((fixture.repository / report).read_bytes(), before)

    def test_reviewer_receipt_is_single_write_and_alternate_result_path_is_rejected(self):
        """Catches receipt replay and copied canonical JSON accepted from another path."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            receipt = assignment["review_dispatch"]
            result = json.dumps({
                "review_kind": "task", "profile": "reviewer", "dispatch_id": receipt["dispatch_id"],
                "task_id": assignment["task_id"], "diff_identity": receipt["diff_identity"],
                "verdict": "APPROVED", "unresolved_important_or_critical_findings": 0,
                "spec_compliance": "APPROVED", "quality": "APPROVED",
            })
            report = self.helper.persist_reviewer_result(str(fixture.repository), receipt, result)
            with self.assertRaises(PermissionError):
                self.helper.persist_reviewer_result(str(fixture.repository), receipt, result)
            alternate = ".agentic-workflow/other-valid-copy.json"
            (fixture.repository / alternate).write_bytes((fixture.repository / report).read_bytes())
            reviewing = self.helper.transition(validated, "review")
            with self.assertRaises(PermissionError):
                self.helper.transition(reviewing, "approved", reviewer_verdict="APPROVED", reviewer_report=alternate)

    def test_operational_reviewer_evidence_has_no_tamper_marker_but_revalidates_its_verdict(self):
        """Catches a V1 evidence marker falsely presented as an integrity control."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            receipt = assignment["review_dispatch"]
            direct = fixture.repository / assignment["report_path"]
            result = {
                "review_kind": "task", "profile": "reviewer", "dispatch_id": receipt["dispatch_id"],
                "task_id": assignment["task_id"], "diff_identity": receipt["diff_identity"],
                "verdict": "APPROVED", "unresolved_important_or_critical_findings": 0,
                "spec_compliance": "APPROVED", "quality": "APPROVED",
            }
            self.helper.persist_reviewer_result(
                str(fixture.repository), receipt, json.dumps(result)
            )
            self.assertFalse(direct.with_suffix(".accepted.json").exists())
            direct.write_text(json.dumps(result), encoding="utf-8")
            reviewing = self.helper.transition(validated, "review")
            self.assertEqual(
                self.helper.transition(
                    reviewing,
                    "approved",
                    reviewer_verdict="APPROVED",
                    reviewer_report=assignment["report_path"],
                )["phase"],
                "approved",
            )

    def test_reviewer_verdict_truth_table_rejects_contradictory_dimensions_and_counts(self):
        """Catches persisted verdicts that contradict dimensions, findings, or counts."""
        invalid_results = (
            ("APPROVED", 0, "NEEDS_FIXES", "APPROVED", []),
            ("APPROVED", 1, "APPROVED", "APPROVED", []),
            ("NEEDS_FIXES", 1, "NEEDS_FIXES", "APPROVED", [
                {"id": "M-1", "severity": "Minor", "location": "test:1", "description": "minor"}
            ]),
            ("BLOCKED", 0, "APPROVED", "APPROVED", []),
        )
        for verdict, unresolved, spec_compliance, quality, findings in invalid_results:
            with self.subTest(verdict=verdict), GitEvidenceFixture() as fixture:
                validated = fixture.validated_state(self.helper)
                assignment = self.prepare_fixture_review(fixture, validated)
                receipt = assignment["review_dispatch"]
                result = {
                    "review_kind": "task", "profile": "reviewer", "dispatch_id": receipt["dispatch_id"],
                    "task_id": assignment["task_id"], "diff_identity": receipt["diff_identity"],
                    "verdict": verdict,
                    "unresolved_important_or_critical_findings": unresolved,
                    "spec_compliance": spec_compliance,
                    "quality": quality,
                    "findings": findings,
                }
                if verdict == "BLOCKED":
                    result["coverage_gap"] = {
                        "material_risk": "The contract cannot verify a material control.",
                        "recommended_contract_delta": "Add the required control.",
                    }
                with self.assertRaises(PermissionError):
                    self.helper.persist_reviewer_result(
                        str(fixture.repository), receipt, json.dumps(result)
                    )

    def test_whole_change_blocked_coverage_gap_persists_and_requires_a_gate(self):
        """Catches a receipt-bound whole-change coverage gap rejected before its gate."""
        with GitEvidenceFixture() as fixture:
            worktree = str(fixture.repository.resolve())
            assignment = self.helper.prepare_whole_change_review_dispatch(
                worktree, ".agentic-workflow/ignored-caller-name.json"
            )
            receipt = assignment["review_dispatch"]
            report = self.helper.persist_reviewer_result(
                worktree,
                receipt,
                json.dumps(
                    {
                        "review_kind": "whole-change",
                        "profile": "reviewer",
                        "dispatch_id": receipt["dispatch_id"],
                        "diff_identity": receipt["diff_identity"],
                        "verdict": "BLOCKED",
                        "unresolved_important_or_critical_findings": 0,
                        "spec_compliance": "CANNOT_VERIFY",
                        "quality": "APPROVED",
                        "coverage_gap": {
                            "material_risk": "No mandatory threat-model gate.",
                            "recommended_contract_delta": "Add a threat-model gate.",
                        },
                    }
                ),
            )
            evidence = self.helper.record_whole_change_review(worktree, report)
            blocked = self.helper.require_whole_change_coverage_gap_human_gate(
                worktree, evidence, "validation-contract-delta-73"
            )
            self.assertEqual(blocked["phase"], "blocked")
            self.assertEqual(blocked["pending_gate"], "validation-contract-delta-73")

    def test_approved_rereview_can_persist_an_addressed_important_finding(self):
        """Catches a clean re-review JSON that cannot retain an addressed material finding."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            receipt = assignment["review_dispatch"]
            report = self.helper.persist_reviewer_result(
                str(fixture.repository.resolve()),
                receipt,
                json.dumps(
                    {
                        "review_kind": "task",
                        "profile": "reviewer",
                        "dispatch_id": receipt["dispatch_id"],
                        "task_id": assignment["task_id"],
                        "diff_identity": receipt["diff_identity"],
                        "verdict": "APPROVED",
                        "unresolved_important_or_critical_findings": 0,
                        "spec_compliance": "APPROVED",
                        "quality": "APPROVED",
                        "findings": [{
                            "id": "I-17",
                            "severity": "Important",
                            "location": "execution_state.py:1",
                            "description": "Prior defect is fixed.",
                            "disposition": "ADDRESSED",
                        }],
                    }
                ),
            )
            self.assertEqual(report, assignment["report_path"])

    def test_read_only_whole_change_reviewer_receipt_and_findings_use_controller_persistence(self):
        """Catches a whole-change review that cannot preserve its receipt or findings."""
        with GitEvidenceFixture() as fixture:
            worktree = str(fixture.repository.resolve())
            assignment = self.helper.prepare_whole_change_review_dispatch(
                worktree, ".agentic-workflow/whole-change-review.json"
            )
            receipt = assignment["review_dispatch"]
            returned_result = json.dumps(
                {
                    "review_kind": "whole-change",
                    "profile": "reviewer",
                    "dispatch_id": receipt["dispatch_id"],
                    "diff_identity": receipt["diff_identity"],
                    "verdict": "NEEDS_FIXES",
                    "unresolved_important_or_critical_findings": 1,
                    "spec_compliance": "NEEDS_FIXES",
                    "quality": "APPROVED",
                    "findings": [
                        {
                            "id": "I-20",
                            "severity": "Important",
                            "location": "example.py:10",
                            "description": "The exact bounded defect.",
                        }
                    ],
                }
            )
            report = self.helper.persist_reviewer_result(worktree, receipt, returned_result)
            self.assertEqual(report, assignment["report_path"])
            persisted = json.loads((fixture.repository / report).read_text(encoding="utf-8"))
            self.assertEqual(persisted["findings"][0]["id"], "I-20")
            evidence = self.helper.record_whole_change_review(worktree, report)
            self.assertTrue((fixture.repository / evidence).is_file())

    def test_task_verdict_and_coverage_gap_reverify_bound_validator_evidence(self):
        """Catches acceptance after dispatched validation evidence is removed or invalidated."""
        for route, verdict, findings in (
            ("approved", "APPROVED", 0),
            ("coverage-gap", "BLOCKED", 0),
        ):
            for mutation in ("missing", "failed", "changed-contract"):
                with self.subTest(route=route, mutation=mutation), GitEvidenceFixture() as fixture:
                    validated = fixture.validated_state(self.helper)
                    assignment = self.prepare_fixture_review(fixture, validated)
                    reviewing = self.helper.transition(validated, "review")
                    if mutation == "missing":
                        fixture.evidence_path.unlink()
                    elif mutation == "failed":
                        evidence = fixture.evidence()
                        evidence["overall_status"] = "fail"
                        fixture.write_evidence(evidence)
                    else:
                        contract = fixture.repository / "docs/agentic-workflow/validation-contract.md"
                        contract.write_text(
                            contract.read_text(encoding="utf-8") + "\nChanged after dispatch.\n",
                            encoding="utf-8",
                        )
                    if route == "approved":
                        report = self.write_reviewer_report(
                            fixture, assignment, verdict, findings
                        )
                        with self.assertRaises(PermissionError):
                            self.helper.transition(
                                reviewing,
                                "approved",
                                reviewer_verdict=verdict,
                                reviewer_report=report,
                            )
                    else:
                        report = self.write_coverage_gap_report(fixture, assignment)
                        with self.assertRaises(PermissionError):
                            self.helper.require_coverage_gap_human_gate(
                                reviewing, report, "validation-contract-delta-42"
                            )

    def test_reviewer_coverage_gap_recommends_a_contract_delta_and_stops_at_a_human_gate(self):
        """Catches a coverage recommendation that can continue without a Human Gate."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            reviewing = self.helper.transition(validated, "review")
            contract = fixture.repository / "docs/agentic-workflow/validation-contract.md"
            before = hashlib.sha256(contract.read_bytes()).hexdigest()
            blocked = self.helper.require_coverage_gap_human_gate(
                reviewing,
                self.write_coverage_gap_report(fixture, assignment),
                "validation-contract-delta-42",
            )
            self.assertEqual(blocked["phase"], "blocked")
            self.assertEqual(blocked["pending_gate"], "validation-contract-delta-42")
            self.assertEqual(blocked["reviewer_verdict"], "BLOCKED")
            self.assertEqual(
                hashlib.sha256(contract.read_bytes()).hexdigest(),
                before,
            )

    def test_coverage_gap_blocks_dependent_continuation_until_the_exact_human_gate_approves(self):
        """Catches a near-match approval that resumes work after a coverage-gap report."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            reviewing = self.helper.transition(validated, "review")
            blocked = self.helper.require_coverage_gap_human_gate(
                reviewing,
                self.write_coverage_gap_report(fixture, assignment),
                "validation-contract-delta-42",
            )
            with self.assertRaises(PermissionError):
                self.helper.transition(
                    blocked,
                    "implementing",
                    approval="validation-contract-delta-41",
                    resolution="delta approved",
                    base_identity="base",
                )
            resumed = self.helper.transition(
                blocked,
                "implementing",
                approval="validation-contract-delta-42",
                resolution="delta approved",
                base_identity="base",
            )
            self.assertEqual(resumed["phase"], "implementing")
            self.assertIsNone(resumed["pending_gate"])

    def test_coverage_gap_rejects_a_forged_blocked_report(self):
        """Catches a BLOCKED coverage-gap report whose exact receipt binding was forged."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            reviewing = self.helper.transition(validated, "review")
            report = fixture.repository / assignment["report_path"]
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                json.dumps(
                    {
                        "review_kind": "task",
                        "profile": "reviewer",
                        "dispatch_id": "0" * 32,
                        "task_id": assignment["task_id"],
                        "diff_identity": assignment["diff_identity"],
                        "verdict": "BLOCKED",
                        "unresolved_important_or_critical_findings": 1,
                        "coverage_gap": {
                            "material_risk": "missing coverage",
                            "recommended_contract_delta": "add a gate",
                        },
                    }
                ) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(PermissionError):
                self.helper.require_coverage_gap_human_gate(
                    reviewing, assignment["report_path"], "validation-contract-delta-42"
                )

    def test_coverage_gap_rejects_a_stale_blocked_report(self):
        """Catches a valid BLOCKED coverage-gap report after its reviewed worktree changes."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            reviewing = self.helper.transition(validated, "review")
            report = self.write_coverage_gap_report(fixture, assignment)
            (fixture.repository / "tracked.txt").write_text("changed after review\n", encoding="utf-8")
            with self.assertRaises(PermissionError):
                self.helper.require_coverage_gap_human_gate(
                    reviewing, report, "validation-contract-delta-42"
                )

    def test_task_verdict_rejects_worktree_mutation_after_reviewer_dispatch(self):
        """Catches accepting either verdict after the reviewer dispatch goes stale."""
        for phase, verdict, findings in (
            ("fixing", "NEEDS_FIXES", 1),
            ("approved", "APPROVED", 0),
        ):
            with self.subTest(phase=phase), GitEvidenceFixture() as fixture:
                validated = fixture.validated_state(self.helper)
                assignment = self.prepare_fixture_review(fixture, validated)
                reviewing = self.helper.transition(validated, "review")
                (fixture.repository / "tracked.txt").write_text(
                    "mutated after reviewer dispatch\n", encoding="utf-8"
                )
                report = self.write_reviewer_report(
                    fixture, assignment, verdict, findings
                )
                with self.assertRaises(PermissionError):
                    self.helper.transition(
                        reviewing,
                        phase,
                        reviewer_verdict=verdict,
                        reviewer_report=report,
                    )

    def test_implementer_self_review_cannot_replace_an_independent_reviewer_verdict(self):
        """Catches copied, renamed, or forged self-review used as a reviewer result."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            assignment = self.prepare_fixture_review(fixture, validated)
            state = self.helper.transition(validated, "review")
            report_path = fixture.repository / assignment["report_path"]
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(
                    {
                        "review_kind": "task",
                        "profile": "implementer",
                        "dispatch_id": assignment["review_dispatch"]["dispatch_id"],
                        "task_id": assignment["task_id"],
                        "diff_identity": assignment["diff_identity"],
                        "verdict": "APPROVED",
                        "unresolved_important_or_critical_findings": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            for copied_path in (
                assignment["report_path"],
                "copied-self-review.md",
                "renamed-self-review.md",
            ):
                if copied_path != assignment["report_path"]:
                    (fixture.repository / copied_path).write_bytes(report_path.read_bytes())
                with self.subTest(copied_path=copied_path), self.assertRaises(PermissionError):
                    self.helper.transition(
                        state,
                        "approved",
                        reviewer_verdict="APPROVED",
                        reviewer_report=copied_path,
                    )

    def test_fix_round_requires_fresh_validation_before_independent_rereview(self):
        """Catches re-review based on the validation identity from before a fix."""
        with GitEvidenceFixture() as fixture:
            validated = fixture.validated_state(self.helper)
            first_assignment = self.prepare_fixture_review(fixture, validated)
            reviewing = self.helper.transition(validated, "review")
            first_report = self.write_reviewer_report(
                fixture, first_assignment, "NEEDS_FIXES"
            )
            fixing = self.helper.transition(
                reviewing,
                "fixing",
                reviewer_verdict="NEEDS_FIXES",
                reviewer_report=first_report,
            )
            implementing = self.helper.transition(fixing, "implementing")
            old_identity = implementing["diff_identity"]
            (fixture.repository / "tracked.txt").write_text(
                "fixed change\n", encoding="utf-8"
            )
            with self.assertRaises(PermissionError):
                complete_assignment(
                    self.helper,
                    profile="reviewer",
                    worktree=str(fixture.repository.resolve()),
                    state=implementing,
                )
            revalidated = self.helper.run_canonical_validation(
                implementing, "implementer-fix-report.md"
            )
            self.assertNotEqual(revalidated["diff_identity"], old_identity)
            self.assertIsNone(revalidated["reviewer_report"])
            self.assertIsNone(revalidated["reviewer_verdict"])
            replacement_assignment = self.prepare_fixture_review(fixture, revalidated)
            self.assertNotEqual(
                replacement_assignment["review_dispatch"]["dispatch_id"],
                first_assignment["review_dispatch"]["dispatch_id"],
            )
            self.assertEqual(
                replacement_assignment["diff_identity"], revalidated["diff_identity"]
            )
            independent_review = self.helper.transition(revalidated, "review")
            self.assertEqual(independent_review["phase"], "review")
            replacement_report = self.write_reviewer_report(
                fixture, replacement_assignment, "APPROVED"
            )
            self.assertEqual(
                self.helper.transition(
                    independent_review,
                    "approved",
                    reviewer_verdict="APPROVED",
                    reviewer_report=replacement_report,
                )["phase"],
                "approved",
            )

    def test_branch_completion_skill_stays_inactive_after_whole_change_approval(self):
        """Catches caller-supplied completion claims that would activate branch completion."""
        with GitEvidenceFixture() as fixture:
            assignment = self.helper.prepare_whole_change_review_dispatch(
                str(fixture.repository.resolve()),
                ".agentic-workflow/whole-change-review.json",
            )
            report_path = fixture.repository / assignment["report_path"]
            self.helper.persist_reviewer_result(
                str(fixture.repository.resolve()), assignment["review_dispatch"], json.dumps({
                        "review_kind": "whole-change",
                        "profile": "reviewer",
                        "dispatch_id": assignment["dispatch_id"],
                        "diff_identity": assignment["diff_identity"],
                        "verdict": "APPROVED",
                        "unresolved_important_or_critical_findings": 0,
                        "spec_compliance": "APPROVED",
                        "quality": "APPROVED",
                    })
            )
            evidence = self.helper.record_whole_change_review(
                str(fixture.repository.resolve()), assignment["report_path"]
            )
            ready = {
                "all_tasks_complete": True,
                "completion_authority": True,
                "worktree": str(fixture.repository.resolve()),
                "whole_change_review_evidence": evidence,
            }
            self.assertFalse(
                self.helper.support_allowed("finishing-a-development-branch", ready)
            )
            for override in (
                {"whole_change_review_evidence": "missing.json"},
                {"whole_change_review_pass": True},
                {"worktree": "/other"},
            ):
                with self.subTest(override=override):
                    context = dict(ready)
                    context.update(override)
                    self.assertFalse(
                        self.helper.support_allowed("finishing-a-development-branch", context)
                    )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["unresolved_important_or_critical_findings"] = 1
            report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
            self.assertFalse(
                self.helper.support_allowed("finishing-a-development-branch", ready)
            )

    def test_whole_change_review_requires_and_rechecks_current_validator_evidence(self):
        """Catches whole-change approval without fresh, contract-bound canonical evidence."""
        with GitEvidenceFixture() as fixture:
            worktree = str(fixture.repository.resolve())
            fixture.evidence_path.unlink()
            with self.assertRaises(PermissionError):
                self.helper.prepare_whole_change_review_dispatch(
                    worktree, ".agentic-workflow/whole-change-review.json"
                )
            fixture.invoke_validator()
            assignment = self.helper.prepare_whole_change_review_dispatch(
                worktree, ".agentic-workflow/whole-change-review.json"
            )
            self.assertEqual(
                assignment["validator_evidence"]["sha256"],
                hashlib.sha256(fixture.evidence_path.read_bytes()).hexdigest(),
            )
            self.helper.persist_reviewer_result(
                worktree,
                assignment["review_dispatch"],
                json.dumps(
                    {
                        "review_kind": "whole-change",
                        "profile": "reviewer",
                        "dispatch_id": assignment["dispatch_id"],
                        "diff_identity": assignment["diff_identity"],
                        "verdict": "APPROVED",
                        "unresolved_important_or_critical_findings": 0,
                        "spec_compliance": "APPROVED",
                        "quality": "APPROVED",
                    }
                ),
            )
            evidence = fixture.evidence()
            evidence["gates"][0]["status"] = "skipped"
            fixture.write_evidence(evidence)
            with self.assertRaises(PermissionError):
                self.helper.record_whole_change_review(worktree, assignment["report_path"])

    def test_pending_gate_accepts_only_exact_approval_and_does_not_persist_control_arguments(self):
        """Catches truthy-but-wrong approval or schema pollution from gate controls."""
        state = self.helper.new_state("change", "5.4", "/worktree")
        state = self.helper.transition(state, "blocked", pending_gate="approval-123")
        with self.assertRaises(PermissionError):
            self.helper.transition(state, "implementing", approval="wrong", resolution="approved")
        resumed = self.helper.transition(
            state,
            "implementing",
            approval="approval-123",
            resolution="gate approved",
            base_identity="base",
        )
        self.assertIsNone(resumed["pending_gate"])
        self.assertNotIn("approval", resumed)
        self.assertNotIn("resolution", resumed)

    def test_blocked_resume_requires_resolution_and_an_allowed_return_phase(self):
        """Catches arbitrary or unexplained jumps out of blocked state."""
        state = self.helper.new_state("change", "5.4", "/worktree")
        state = self.helper.transition(state, "blocked")
        with self.assertRaises(PermissionError):
            self.helper.transition(state, "implementing", base_identity="base")
        with self.assertRaises(PermissionError):
            self.helper.transition(state, "approved", resolution="resolved")

    def test_support_compatibility_fails_closed_for_every_optional_skill(self):
        """Catches activation when any caller authority or compatibility prerequisite is absent."""
        allowed = {
            "subagent-driven-development": {
                "caller_model": "caller-choice",
                "runtime_compatible": True,
                "openspec_compatible": True,
                "profile_compatible": True,
                "unapproved_commits_prohibited": True,
                "repository_local_review": True,
                "automatic_cleanup_prohibited": True,
            },
            "dispatching-parallel-agents": {
                "caller_model": "caller-choice",
                "profile_compatible": True,
                "independent": True,
                "shared_state": False,
                "human_gate": False,
            },
            "git-commit": {"commit_authority": True},
            "capturing-working-agreements": {"activation_trigger": True},
            "using-git-worktrees": {"isolation_present": False},
            "test-driven-development": {},
        }
        self.assertFalse(self.helper.support_allowed("requesting-code-review", allowed))
        self.assertFalse(self.helper.support_allowed("unknown-skill", allowed))
        for name, context in allowed.items():
            with self.subTest(name=name):
                self.assertTrue(self.helper.support_allowed(name, context))
                for key in context:
                    denied = dict(context)
                    denied[key] = False if context[key] is True else True
                    self.assertFalse(
                        self.helper.support_allowed(name, denied),
                        f"{name} ignored incompatible {key}",
                    )

    def test_documented_sdd_and_branch_completion_contract_matches_support_gate(self):
        """Catches skill guidance that advertises a support route the helper rejects."""
        skill = read_required(REPOSITORY_ROOT / ".agents/skills/implementation-loop/SKILL.md")
        sdd_context = {
            "caller_model": "caller-choice",
            "runtime_compatible": True,
            "openspec_compatible": True,
            "profile_compatible": True,
            "unapproved_commits_prohibited": True,
            "repository_local_review": True,
            "automatic_cleanup_prohibited": True,
        }
        documented_contract = " ".join(skill.split())

        self.assertIn("exactly these seven keys and no others", documented_contract)
        self.assertIn("caller_model` is a non-empty string", documented_contract)
        self.assertIn("other six fields must each be literal `true`", documented_contract)
        self.assertIn(
            "inactive until a separate explicit Human Gate", documented_contract
        )
        self.assertNotIn("Task 7.4", skill)
        self.assertIn("No caller-supplied completion", documented_contract)
        self.assertTrue(self.helper.support_allowed("subagent-driven-development", sdd_context))
        self.assertFalse(
            self.helper.support_allowed(
                "subagent-driven-development", {**sdd_context, "task_id": "7.3"}
            )
        )
        self.assertFalse(
            self.helper.support_allowed(
                "subagent-driven-development", {**sdd_context, "caller_model": ""}
            )
        )
        self.assertFalse(
            self.helper.support_allowed(
                "finishing-a-development-branch",
                {
                    "all_tasks_complete": True,
                    "completion_authority": True,
                    "worktree": "/worktree",
                    "whole_change_review_evidence": "evidence.json",
                },
            )
        )


if __name__ == "__main__":
    unittest.main()
