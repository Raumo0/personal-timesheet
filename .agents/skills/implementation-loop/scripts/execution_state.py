"""Deterministic local execution state for the repository Implementation Loop."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import types
import uuid
from datetime import UTC, datetime
from pathlib import Path


SCHEMA_VERSION = 1
TASK = re.compile(r"^- \[([ xX])\] (\d+(?:\.\d+)+)(?:\s|$)")
CHANGE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
TASK_ID = re.compile(r"^\d+(?:\.\d+)+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PHASES = {
    "selected",
    "implementing",
    "validated",
    "review",
    "fixing",
    "approved",
    "blocked",
}
VALIDATOR_STATUSES = {"pass", "fail", "skipped", "unauthorized-skipped"}
REVIEWER_VERDICTS = {"NEEDS_FIXES", "APPROVED", "BLOCKED"}
REVIEW_DIMENSION_VERDICTS = {"APPROVED", "NEEDS_FIXES", "CANNOT_VERIFY"}
FINDING_SEVERITIES = {"Critical", "Important", "Minor", "Cannot Verify"}
FINDING_DISPOSITIONS = {"ADDRESSED", "NOT_ADDRESSED", "OUT_OF_SCOPE"}
REQUIRED_KEYS = {
    "schema",
    "change_id",
    "task_id",
    "phase",
    "worktree",
    "base_identity",
    "diff_identity",
    "validator_evidence_path",
    "validator_hash",
    "validator_worktree_digest",
    "validator_status",
    "implementer_report",
    "reviewer_report",
    "reviewer_verdict",
    "fix_round",
    "pending_gate",
    "created_at",
    "updated_at",
}
VALIDATION_FIELDS = {
    "diff_identity",
    "implementer_report",
    "validator_evidence_path",
    "validator_hash",
    "validator_worktree_digest",
    "validator_status",
}
VALIDATOR_RELATIVE_PATH = Path("tools/agentic_workflow/validate.py")
CONTRACT_RELATIVE_PATH = Path("docs/agentic-workflow/validation-contract.md")
EVIDENCE_RELATIVE_PATH = Path(".agentic-workflow/validation-evidence.json")
MAX_VALIDATION_RUNTIME_SECONDS = 3600.0
REVIEW_DISPATCHES_RELATIVE_PATH = Path(".agentic-workflow/review-dispatches")
REVIEW_EVIDENCE_RELATIVE_PATH = Path(".agentic-workflow/review-evidence")
REVIEW_RESULTS_RELATIVE_PATH = Path(".agentic-workflow/reviewer-results")
VALIDATOR_EVIDENCE_KEYS = {
    "repository", "contract_hash", "generated_at", "overall_status", "gates"
}
VALIDATOR_GATE_EVIDENCE_KEYS = {
    "id", "order", "applicability", "mandatory", "command", "status",
    "duration_seconds", "exit_code", "reason", "output",
}


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_nonempty_string(item) for item in value)
    )


def _parse_timestamp(value: object) -> datetime:
    if not _nonempty_string(value):
        raise ValueError("state timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("state timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("state timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _has_passing_validation(state: dict) -> bool:
    return (
        state["validator_status"] == "pass"
        and _nonempty_string(state["diff_identity"])
        and _nonempty_string(state["implementer_report"])
        and _nonempty_string(state["validator_evidence_path"])
        and isinstance(state["validator_hash"], str)
        and SHA256.fullmatch(state["validator_hash"]) is not None
        and isinstance(state["validator_worktree_digest"], str)
        and SHA256.fullmatch(state["validator_worktree_digest"]) is not None
    )


def _worktree_path(worktree: str) -> Path:
    if not _nonempty_string(worktree):
        raise PermissionError("assigned worktree is unavailable")
    resolved = Path(worktree).resolve()
    if not resolved.is_dir():
        raise PermissionError("assigned worktree is unavailable")
    return resolved


def _relative_worktree_path(worktree: Path, value: str) -> tuple[Path, str]:
    if not _nonempty_string(value):
        raise PermissionError("review report path is missing")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise PermissionError("review report path must stay inside the worktree")
    path = (worktree / relative).resolve()
    try:
        return path, path.relative_to(worktree).as_posix()
    except ValueError as error:
        raise PermissionError("review report path escapes the worktree") from error


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump(value, temporary, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PermissionError("review evidence is unavailable or malformed") from error
    if not isinstance(value, dict):
        raise PermissionError("review evidence is malformed")
    return value


def _review_result_truth_table_is_valid(report: dict) -> bool:
    """Validate the correlated reviewer verdict, dimensions, and findings."""
    verdict = report.get("verdict")
    spec_compliance = report.get("spec_compliance")
    quality = report.get("quality")
    unresolved_count = report.get("unresolved_important_or_critical_findings")
    if (
        verdict not in REVIEWER_VERDICTS
        or spec_compliance not in REVIEW_DIMENSION_VERDICTS
        or quality not in REVIEW_DIMENSION_VERDICTS
        or type(unresolved_count) is not int
        or unresolved_count < 0
    ):
        return False

    if verdict == "BLOCKED":
        coverage_gap = report.get("coverage_gap")
        return (
            "findings" not in report
            and unresolved_count == 0
            and "CANNOT_VERIFY" in {spec_compliance, quality}
            and "NEEDS_FIXES" not in {spec_compliance, quality}
            and isinstance(coverage_gap, dict)
            and set(coverage_gap) == {"material_risk", "recommended_contract_delta"}
            and _nonempty_string(coverage_gap["material_risk"])
            and _nonempty_string(coverage_gap["recommended_contract_delta"])
        )

    findings = report.get("findings", [])
    if not isinstance(findings, list):
        return False
    required = {"id", "severity", "location", "description"}
    valid = all(
        isinstance(finding, dict)
        and required <= set(finding) <= required | {"disposition"}
        and _nonempty_string(finding["id"])
        and finding["severity"] in FINDING_SEVERITIES
        and _nonempty_string(finding["location"])
        and _nonempty_string(finding["description"])
        and ("disposition" not in finding or finding["disposition"] in FINDING_DISPOSITIONS)
        for finding in findings
    )
    if not valid or "coverage_gap" in report:
        return False
    unresolved_findings = sum(
        finding["severity"] in {"Critical", "Important"}
        and finding.get("disposition") != "ADDRESSED"
        for finding in findings
    )
    if unresolved_count != unresolved_findings:
        return False
    if verdict == "APPROVED":
        return spec_compliance == quality == "APPROVED" and unresolved_count == 0
    return (
        verdict == "NEEDS_FIXES"
        and "NEEDS_FIXES" in {spec_compliance, quality}
        and unresolved_count > 0
    )


def _current_diff_identity(worktree: Path, excluded_path: Path | None = None) -> str:
    validator = _load_repository_validator(worktree)
    try:
        identity = validator.repository_identity(
            worktree, excluded_path or worktree / EVIDENCE_RELATIVE_PATH
        )
    except (OSError, ValueError) as error:
        raise PermissionError("current worktree identity is unavailable") from error
    revision = identity.get("git_revision")
    digest = identity.get("worktree_digest")
    if not _nonempty_string(revision) or not _nonempty_string(digest):
        raise PermissionError("current worktree identity is unavailable")
    return hashlib.sha256(f"{revision}\0{digest}".encode("utf-8")).hexdigest()


def _review_dispatch_path(worktree: Path, dispatch_id: str) -> Path:
    if not isinstance(dispatch_id, str) or not re.fullmatch(r"[0-9a-f]{32}", dispatch_id):
        raise PermissionError("review dispatch identity is invalid")
    return worktree / REVIEW_DISPATCHES_RELATIVE_PATH / f"{dispatch_id}.json"


def _receipt_result_path(worktree: Path, review_kind: str, dispatch_id: str) -> tuple[Path, str]:
    if review_kind not in {"task", "whole-change"}:
        raise PermissionError("review dispatch kind is invalid")
    if not isinstance(dispatch_id, str) or not re.fullmatch(r"[0-9a-f]{32}", dispatch_id):
        raise PermissionError("review dispatch identity is invalid")
    path = worktree / REVIEW_RESULTS_RELATIVE_PATH / f"{review_kind}-{dispatch_id}.json"
    return path, path.relative_to(worktree).as_posix()


def _issue_review_dispatch(
    worktree: Path,
    review_kind: str,
    report_path: str,
    diff_identity: str,
    task_id: str | None = None,
    validator_evidence: dict[str, str] | None = None,
) -> dict:
    _relative_worktree_path(worktree, report_path)
    dispatch_id = uuid.uuid4().hex
    result_path, canonical_report_path = _receipt_result_path(worktree, review_kind, dispatch_id)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "kind": review_kind,
        "profile": "reviewer",
        "dispatch_id": dispatch_id,
        "worktree": str(worktree),
        "diff_identity": diff_identity,
        "report_path": canonical_report_path,
    }
    if task_id is not None:
        receipt["task_id"] = task_id
    if validator_evidence is not None:
        receipt["validator_evidence"] = validator_evidence
    _write_json(_review_dispatch_path(worktree, dispatch_id), receipt)
    return receipt


def _validator_evidence_summary(verified: dict[str, str]) -> dict[str, str]:
    return {
        "path": verified["validator_evidence_path"],
        "sha256": verified["validator_hash"],
        "worktree_digest": verified["validator_worktree_digest"],
        "contract_sha256": verified["contract_sha256"],
        "status": verified["validator_status"],
    }


def _validator_evidence_summary_is_valid(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"path", "sha256", "worktree_digest", "contract_sha256", "status"}
        and _nonempty_string(value["path"])
        and all(SHA256.fullmatch(value[key]) is not None for key in ("sha256", "worktree_digest", "contract_sha256"))
        and value["status"] == "pass"
    )


def _validate_review_result(
    worktree: Path, receipt: dict, report: dict, expected_kind: str
) -> None:
    dispatch_id = report.get("dispatch_id")
    _, canonical_report_path = _receipt_result_path(worktree, expected_kind, dispatch_id)
    required_receipt = {
        "kind": expected_kind,
        "profile": "reviewer",
        "dispatch_id": dispatch_id,
        "worktree": str(worktree),
        "report_path": canonical_report_path,
    }
    if any(receipt.get(key) != value for key, value in required_receipt.items()):
        raise PermissionError("reviewer report does not match an issued dispatch")
    required_report = {
        "review_kind": expected_kind,
        "profile": "reviewer",
        "dispatch_id": dispatch_id,
        "diff_identity": receipt.get("diff_identity"),
        "verdict": report.get("verdict"),
        "unresolved_important_or_critical_findings": report.get(
            "unresolved_important_or_critical_findings"
        ),
    }
    if any(report.get(key) != value for key, value in required_report.items()):
        raise PermissionError("reviewer report provenance is invalid")
    if not _review_result_truth_table_is_valid(report):
        raise PermissionError("reviewer report verdict truth table is invalid")
    report_keys = {
        "review_kind", "profile", "dispatch_id", "diff_identity", "verdict",
        "unresolved_important_or_critical_findings", "spec_compliance", "quality",
    }
    if expected_kind == "task":
        report_keys.add("task_id")
        if set(receipt) != {
            "kind", "profile", "dispatch_id", "worktree", "diff_identity", "report_path", "task_id",
            "validator_evidence",
        } or not _validator_evidence_summary_is_valid(receipt.get("validator_evidence")) or report.get("task_id") != receipt.get("task_id"):
            raise PermissionError("task reviewer report provenance is invalid")
    elif set(receipt) != {
        "kind", "profile", "dispatch_id", "worktree", "diff_identity", "report_path",
        "validator_evidence",
    } or not _validator_evidence_summary_is_valid(receipt.get("validator_evidence")):
        raise PermissionError("whole-change reviewer report provenance is invalid")
    if report["verdict"] == "BLOCKED":
        report_keys.add("coverage_gap")
    elif "findings" in report:
        report_keys.add("findings")
    if set(report) != report_keys:
        raise PermissionError("whole-change reviewer report provenance is invalid")


def _verified_review_result(
    worktree: Path, report_path: str, expected_kind: str
) -> tuple[dict, dict, bytes]:
    report_file, supplied_path = _relative_worktree_path(worktree, report_path)
    try:
        report_bytes = report_file.read_bytes()
        report = json.loads(report_bytes)
    except (OSError, json.JSONDecodeError) as error:
        raise PermissionError("reviewer report is unavailable or malformed") from error
    if not isinstance(report, dict):
        raise PermissionError("reviewer report is malformed")
    receipt = _read_json(_review_dispatch_path(worktree, report.get("dispatch_id")))
    _validate_review_result(worktree, receipt, report, expected_kind)
    if supplied_path != receipt["report_path"]:
        raise PermissionError("reviewer report path is not receipt canonical")
    return receipt, report, report_bytes


def persist_reviewer_result(
    worktree: str, issued_receipt: dict, returned_result: str
) -> str:
    """Persist one receipt-bound reviewer result without granting reviewer write access."""
    resolved_worktree = _worktree_path(worktree)
    if not isinstance(issued_receipt, dict) or not isinstance(returned_result, str):
        raise PermissionError("reviewer result persistence inputs are invalid")
    dispatch_id = issued_receipt.get("dispatch_id")
    receipt = _read_json(_review_dispatch_path(resolved_worktree, dispatch_id))
    if receipt != issued_receipt:
        raise PermissionError("reviewer result does not use an issued receipt")
    try:
        result = json.loads(returned_result)
    except json.JSONDecodeError as error:
        raise PermissionError("reviewer result is malformed") from error
    if not isinstance(result, dict):
        raise PermissionError("reviewer result is malformed")
    _validate_review_result(resolved_worktree, receipt, result, receipt["kind"])
    report_file, canonical_report_path = _receipt_result_path(
        resolved_worktree, receipt["kind"], dispatch_id
    )
    if report_file.exists():
        raise PermissionError("reviewer receipt result was already persisted")
    _write_json(report_file, result)
    return canonical_report_path


def require_coverage_gap_human_gate(
    state: dict, reviewer_report: str, human_gate: str
) -> dict:
    """Persist a reviewer coverage gap and stop until its exact Human Gate approves."""
    validate_state(state)
    if state["phase"] != "review":
        raise PermissionError("coverage gap requires the review phase")
    if not _nonempty_string(human_gate):
        raise ValueError("coverage gap requires an exact Human Gate identity")
    worktree = _worktree_path(state["worktree"])
    _, canonical_report_path = _relative_worktree_path(worktree, reviewer_report)
    receipt, report, _ = _verified_review_result(worktree, reviewer_report, "task")
    verified = _verify_validator_evidence(state)
    if (
        report["verdict"] != "BLOCKED"
        or receipt["task_id"] != state["task_id"]
        or receipt["diff_identity"] != state["diff_identity"]
        or receipt["validator_evidence"] != _validator_evidence_summary(verified)
        or _current_diff_identity(worktree, worktree / canonical_report_path)
        != receipt["diff_identity"]
    ):
        raise PermissionError("reviewer coverage gap does not match current review evidence")
    result = dict(state)
    result.update(
        {
            "phase": "blocked",
            "pending_gate": human_gate,
            "reviewer_report": canonical_report_path,
            "reviewer_verdict": "BLOCKED",
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    validate_state(result)
    return result


def prepare_whole_change_review_dispatch(worktree: str, report_path: str) -> dict:
    """Issue a reviewer-only whole-change assignment bound to the current full diff."""
    resolved_worktree = _worktree_path(worktree)
    report = Path(report_path)
    if not report.parts or report.parts[0] != ".agentic-workflow":
        raise PermissionError("whole-change reviewer report must use local evidence storage")
    verified = _verify_validator_evidence_at_worktree(
        resolved_worktree, EVIDENCE_RELATIVE_PATH.as_posix()
    )
    receipt = _issue_review_dispatch(
        resolved_worktree,
        "whole-change",
        report_path,
        verified["diff_identity"],
        validator_evidence=_validator_evidence_summary(verified),
    )
    return {
        "profile": "reviewer",
        "worktree": str(resolved_worktree),
        "report_path": receipt["report_path"],
        "dispatch_id": receipt["dispatch_id"],
        "diff_identity": receipt["diff_identity"],
        "validator_evidence": receipt["validator_evidence"],
        "review_dispatch": receipt,
    }


def record_whole_change_review(worktree: str, report_path: str) -> str:
    """Persist a verified independent whole-change result for completion checks."""
    resolved_worktree = _worktree_path(worktree)
    receipt, report, report_bytes = _verified_review_result(
        resolved_worktree, report_path, "whole-change"
    )
    verified = _verify_validator_evidence_at_worktree(
        resolved_worktree,
        receipt["validator_evidence"]["path"],
        receipt["validator_evidence"]["sha256"],
    )
    if (
        receipt["diff_identity"] != verified["diff_identity"]
        or receipt["validator_evidence"] != _validator_evidence_summary(verified)
    ):
        raise PermissionError("whole-change review is stale")
    evidence = {
        "kind": "whole-change",
        "profile": "reviewer",
        "dispatch_id": receipt["dispatch_id"],
        "worktree": str(resolved_worktree),
        "diff_identity": receipt["diff_identity"],
        "report_path": receipt["report_path"],
        "report_hash": hashlib.sha256(report_bytes).hexdigest(),
        "verdict": report["verdict"],
        "unresolved_important_or_critical_findings": report[
            "unresolved_important_or_critical_findings"
        ],
        "validator_evidence": receipt["validator_evidence"],
    }
    path = resolved_worktree / REVIEW_EVIDENCE_RELATIVE_PATH / f"{receipt['dispatch_id']}.json"
    _write_json(path, evidence)
    return path.relative_to(resolved_worktree).as_posix()


def require_whole_change_coverage_gap_human_gate(
    worktree: str, review_evidence: str, human_gate: str
) -> dict:
    """Return the exact gate that blocks continuation after a final coverage gap."""
    resolved_worktree = _worktree_path(worktree)
    if not _nonempty_string(human_gate):
        raise ValueError("coverage gap requires an exact Human Gate identity")
    evidence_file, canonical_evidence_path = _relative_worktree_path(
        resolved_worktree, review_evidence
    )
    evidence = _read_json(evidence_file)
    if evidence.get("kind") != "whole-change" or evidence.get("verdict") != "BLOCKED":
        raise PermissionError("whole-change coverage gap evidence is invalid")
    receipt, report, _ = _verified_review_result(
        resolved_worktree, evidence.get("report_path"), "whole-change"
    )
    if (
        receipt.get("dispatch_id") != evidence.get("dispatch_id")
        or report.get("verdict") != "BLOCKED"
        or "coverage_gap" not in report
    ):
        raise PermissionError("whole-change coverage gap evidence is invalid")
    return {
        "phase": "blocked",
        "pending_gate": human_gate,
        "whole_change_review_evidence": canonical_evidence_path,
    }


def _whole_change_evidence_is_current(worktree: str, evidence_path: object) -> bool:
    try:
        resolved_worktree = _worktree_path(worktree)
        evidence_file, _ = _relative_worktree_path(resolved_worktree, evidence_path)
        evidence = _read_json(evidence_file)
        required_keys = {
            "kind", "profile", "dispatch_id", "worktree", "diff_identity", "report_path",
            "report_hash", "verdict", "unresolved_important_or_critical_findings",
            "validator_evidence",
        }
        if set(evidence) != required_keys or evidence["kind"] != "whole-change" or evidence[
            "profile"
        ] != "reviewer" or evidence["worktree"] != str(resolved_worktree) or evidence[
            "verdict"
        ] != "APPROVED" or type(evidence["unresolved_important_or_critical_findings"]) is not int or evidence[
            "unresolved_important_or_critical_findings"
        ] != 0:
            return False
        receipt, report, report_bytes = _verified_review_result(
            resolved_worktree, evidence["report_path"], "whole-change"
        )
        verified = _verify_validator_evidence_at_worktree(
            resolved_worktree,
            evidence["validator_evidence"]["path"],
            evidence["validator_evidence"]["sha256"],
        )
        return (
            evidence["dispatch_id"] == receipt["dispatch_id"]
            and evidence["diff_identity"] == receipt["diff_identity"] == verified["diff_identity"]
            and evidence["report_hash"] == hashlib.sha256(report_bytes).hexdigest()
            and evidence["verdict"] == report["verdict"]
            and evidence["unresolved_important_or_critical_findings"] == report[
                "unresolved_important_or_critical_findings"
            ]
            and evidence["validator_evidence"] == receipt["validator_evidence"]
            == _validator_evidence_summary(verified)
        )
    except (PermissionError, TypeError):
        return False


def _load_repository_validator(worktree: Path):
    validator_path = worktree / VALIDATOR_RELATIVE_PATH
    if not validator_path.is_file():
        raise PermissionError("canonical repository validator is unavailable")
    module_name = "implementation_loop_validator_" + hashlib.sha256(
        str(validator_path).encode("utf-8")
    ).hexdigest()
    module = types.ModuleType(module_name)
    module.__file__ = str(validator_path)
    try:
        source = validator_path.read_text(encoding="utf-8")
        exec(compile(source, str(validator_path), "exec"), module.__dict__)
    except Exception as error:
        raise PermissionError("canonical repository validator cannot be loaded") from error
    required_apis = ("repository_identity", "parse_contract", "redact", "is_applicable")
    if not all(callable(getattr(module, name, None)) for name in required_apis):
        raise PermissionError("canonical repository identity API is unavailable")
    return module


def _verify_validator_evidence_at_worktree(
    worktree: Path, evidence_value: object, expected_hash: str | None = None
) -> dict[str, str]:
    """Re-read evidence and bind it to the canonical current repository identity."""
    if not _nonempty_string(evidence_value):
        raise PermissionError("validator evidence path is missing")
    evidence_relative = Path(evidence_value)
    if evidence_relative.is_absolute() or ".." in evidence_relative.parts:
        raise PermissionError("validator evidence path must stay inside the worktree")
    evidence_path = (worktree / evidence_relative).resolve()
    try:
        canonical_relative = evidence_path.relative_to(worktree).as_posix()
    except ValueError as error:
        raise PermissionError("validator evidence path escapes the worktree") from error
    if not evidence_path.is_file():
        raise PermissionError("validator evidence file is missing")

    contract = worktree / CONTRACT_RELATIVE_PATH
    if not contract.is_file():
        raise PermissionError("Validation Contract is unavailable")
    validator = _load_repository_validator(worktree)
    try:
        evidence_bytes = evidence_path.read_bytes()
        evidence = json.loads(evidence_bytes)
        current_identity = validator.repository_identity(worktree, evidence_path)
        current_gates = validator.parse_contract(contract)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise PermissionError("validator evidence cannot be verified") from error
    if not isinstance(evidence, dict) or set(evidence) != VALIDATOR_EVIDENCE_KEYS or evidence.get("overall_status") != "pass":
        raise PermissionError("validator evidence does not report overall pass")
    try:
        _parse_timestamp(evidence["generated_at"])
    except ValueError as error:
        raise PermissionError("validator evidence timestamp is invalid") from error
    if expected_hash is not None and expected_hash != hashlib.sha256(evidence_bytes).hexdigest():
        raise PermissionError("validator evidence is stale or mutated")

    evidence_repository = evidence.get("repository")
    if not isinstance(evidence_repository, dict) or set(evidence_repository) != set(current_identity):
        raise PermissionError("validator repository identity is missing")
    for key, current_value in current_identity.items():
        if key in {"path", "git_revision", "worktree_digest"} and not _nonempty_string(current_value):
            raise PermissionError(f"current repository {key} is unavailable")
        if evidence_repository.get(key) != current_value:
            raise PermissionError(f"validator repository {key} is stale or mismatched")

    current_contract_hash = hashlib.sha256(contract.read_bytes()).hexdigest()
    if evidence.get("contract_hash") != current_contract_hash:
        raise PermissionError("validator evidence uses a different Validation Contract")

    evidence_gates = evidence.get("gates")
    if not isinstance(evidence_gates, list):
        raise PermissionError("validator gate evidence is missing")
    if len(evidence_gates) != len(current_gates):
        raise PermissionError("validator gate evidence does not match the current registry")
    known_statuses = {"pass", "fail", "skipped", "not-applicable"}
    for expected, observed in zip(current_gates, evidence_gates, strict=True):
        if not isinstance(observed, dict) or set(observed) != VALIDATOR_GATE_EVIDENCE_KEYS:
            raise PermissionError("validator gate evidence is malformed")
        if (
            isinstance(observed["duration_seconds"], bool)
            or not isinstance(observed["duration_seconds"], (int, float))
            or not math.isfinite(observed["duration_seconds"])
            or observed["duration_seconds"] < 0
            or (observed["exit_code"] is not None and (
                isinstance(observed["exit_code"], bool) or not isinstance(observed["exit_code"], int)
            ))
            or (observed["reason"] is not None and not isinstance(observed["reason"], str))
            or not isinstance(observed["output"], str)
        ):
            raise PermissionError("validator gate result fields are malformed")
        expected_metadata = {
            "id": expected["id"],
            "order": expected["order"],
            "applicability": expected["applicability"],
            "mandatory": expected["mandatory"],
            "command": validator.redact(str(expected["command"])),
        }
        if any(observed.get(key) != value for key, value in expected_metadata.items()):
            raise PermissionError("validator gate evidence metadata is stale or mismatched")
        status = observed.get("status")
        if status not in known_statuses:
            raise PermissionError("validator gate evidence status is invalid")
        try:
            applicable, _ = validator.is_applicable(
                str(expected["applicability"]), worktree
            )
        except (OSError, ValueError) as error:
            raise PermissionError("validator gate applicability cannot be verified") from error
        if applicable and status == "not-applicable":
            raise PermissionError("applicable validator gate is marked not applicable")
        if not applicable and status != "not-applicable":
            raise PermissionError("inapplicable validator gate has an execution result")
        if applicable and expected["mandatory"] is True and status != "pass":
            raise PermissionError("mandatory validator gate did not pass")

    revision = current_identity["git_revision"]
    worktree_digest = current_identity["worktree_digest"]
    diff_identity = hashlib.sha256(
        f"{revision}\0{worktree_digest}".encode("utf-8")
    ).hexdigest()
    return {
        "diff_identity": diff_identity,
        "validator_evidence_path": canonical_relative,
        "validator_hash": hashlib.sha256(evidence_bytes).hexdigest(),
        "validator_worktree_digest": worktree_digest,
        "contract_sha256": current_contract_hash,
        "validator_status": "pass",
    }


def _verify_validator_evidence(state: dict) -> dict[str, str]:
    expected_hash = state["validator_hash"] if state["phase"] in {"validated", "review"} else None
    return _verify_validator_evidence_at_worktree(
        _worktree_path(state["worktree"]), state["validator_evidence_path"], expected_hash
    )


def run_canonical_validation(state: dict, implementer_report: str) -> dict:
    """Invoke the assigned worktree validator and enter validated on fresh proof."""
    validate_state(state)
    if state["phase"] != "implementing":
        raise PermissionError("canonical validation requires implementing phase")
    if not _nonempty_string(implementer_report):
        raise ValueError("implementer report is required")

    worktree = Path(state["worktree"]).resolve()
    validator_path = worktree / VALIDATOR_RELATIVE_PATH
    contract_path = worktree / CONTRACT_RELATIVE_PATH
    if not worktree.is_dir() or not contract_path.is_file():
        raise PermissionError("assigned validation inputs are unavailable")
    validator = _load_repository_validator(worktree)
    try:
        gates = validator.parse_contract(contract_path)
        runtime = min(
            sum(float(gate["timeout"]) for gate in gates) + 10.0,
            MAX_VALIDATION_RUNTIME_SECONDS,
        )
    except (OSError, TypeError, ValueError) as error:
        raise PermissionError("Validation Contract cannot be executed") from error

    evidence_path = worktree / EVIDENCE_RELATIVE_PATH
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(validator_path),
                "--repository",
                str(worktree),
                "--contract",
                str(contract_path),
                "--output",
                str(evidence_path),
            ],
            cwd=worktree,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=runtime,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PermissionError("canonical repository validation could not complete") from error
    if completed.returncode != 0:
        raise PermissionError("canonical repository validation did not pass")

    result = dict(state)
    result["implementer_report"] = implementer_report
    result["validator_evidence_path"] = EVIDENCE_RELATIVE_PATH.as_posix()
    verified = _verify_validator_evidence(result)
    result.update(
        {
            key: verified[key]
            for key in (
                "diff_identity",
                "validator_evidence_path",
                "validator_hash",
                "validator_worktree_digest",
                "validator_status",
            )
        }
    )
    result["reviewer_report"] = None
    result["reviewer_verdict"] = None
    result["phase"] = "validated"
    result["updated_at"] = datetime.now(UTC).isoformat()
    validate_state(result)
    return result


def select_task(
    tasks_text: str,
    eligible: set[str] | None = None,
    state: dict | None = None,
    authorized_prerequisites: set[str] | None = None,
    *,
    expected_change_id: str,
) -> str | None:
    """Select by file order; persisted state still needs current caller authority."""
    _validate_change_id(expected_change_id)
    unchecked = [
        match.group(2)
        for line in tasks_text.splitlines()
        if (match := TASK.match(line)) and match.group(1).lower() != "x"
    ]
    normal_authority = eligible if eligible is not None else set()
    prerequisite_authority = (
        authorized_prerequisites if authorized_prerequisites is not None else set()
    )
    allowed = normal_authority | prerequisite_authority
    if state is not None:
        validate_state(state)
        if state["change_id"] != expected_change_id:
            raise PermissionError("persisted state belongs to another OpenSpec change")
        if state["task_id"] in unchecked and state["task_id"] in allowed:
            return state["task_id"]
    return next((task for task in unchecked if task in allowed), None)


def prepare_dispatch(
    profile: str,
    task_id: str,
    worktree: str,
    sources: list[str],
    acceptance: str,
    allowed_scope: list[str],
    required_tests: list[str],
    prohibited_actions: list[str],
    report_path: str,
    *,
    caller_authorized: bool = False,
    model: str | None = None,
    state: dict | None = None,
) -> dict:
    """Build a complete bounded assignment; reviewer evidence comes from state."""
    if profile not in {"implementer", "reviewer", "general-purpose"}:
        raise ValueError("unknown profile")
    if profile == "general-purpose" and caller_authorized is not True:
        raise PermissionError(
            "general-purpose dispatch requires explicit caller authorization"
        )
    if not (
        TASK_ID.fullmatch(task_id)
        and _nonempty_string(worktree)
        and _string_list(sources)
        and _nonempty_string(acceptance)
        and _string_list(allowed_scope)
        and _string_list(required_tests)
        and _string_list(prohibited_actions)
        and _nonempty_string(report_path)
    ):
        raise ValueError("bounded assignment fields are required")
    if model is not None and not _nonempty_string(model):
        raise ValueError("caller model must be a non-empty string")

    assignment = {
        "profile": profile,
        "task_id": task_id,
        "worktree": worktree,
        "sources": list(sources),
        "acceptance_evidence": acceptance,
        "allowed_scope": list(allowed_scope),
        "required_tests": list(required_tests),
        "prohibited_external_actions": list(prohibited_actions),
        "report_path": report_path,
    }
    if model is not None:
        assignment["model"] = model

    if profile == "reviewer":
        if state is None:
            raise PermissionError("reviewer dispatch requires persisted validated state")
        validate_state(state)
        if state["phase"] != "validated" or not _has_passing_validation(state):
            raise PermissionError("reviewer dispatch requires current validated evidence")
        if state["task_id"] != task_id or state["worktree"] != worktree:
            raise PermissionError("reviewer assignment does not match validated state")
        verified = _verify_validator_evidence(state)
        for key in (
            "diff_identity",
            "validator_evidence_path",
            "validator_hash",
            "validator_worktree_digest",
            "validator_status",
        ):
            value = verified[key]
            if state[key] != value:
                raise PermissionError("persisted validator evidence identity is stale")
        assignment["diff_identity"] = verified["diff_identity"]
        assignment["implementer_report"] = state["implementer_report"]
        assignment["validator_evidence"] = {
            "path": verified["validator_evidence_path"],
            "sha256": verified["validator_hash"],
            "worktree_digest": verified["validator_worktree_digest"],
            "contract_sha256": verified["contract_sha256"],
            "status": verified["validator_status"],
        }
        assignment["review_dispatch"] = _issue_review_dispatch(
            _worktree_path(worktree),
            "task",
            report_path,
            verified["diff_identity"],
            task_id,
            _validator_evidence_summary(verified),
        )
        assignment["report_path"] = assignment["review_dispatch"]["report_path"]
    return assignment


def support_allowed(name: str, context: dict) -> bool:
    """Return true only when every skill-specific compatibility gate passes."""
    if not isinstance(context, dict):
        return False
    if name == "requesting-code-review":
        return False
    if name == "subagent-driven-development":
        return (
            set(context) == {
                "caller_model", "runtime_compatible", "openspec_compatible", "profile_compatible",
                "unapproved_commits_prohibited", "repository_local_review", "automatic_cleanup_prohibited",
            }
            and _nonempty_string(context.get("caller_model"))
            and context.get("runtime_compatible") is True
            and context.get("openspec_compatible") is True
            and context.get("profile_compatible") is True
            and context.get("unapproved_commits_prohibited") is True
            and context.get("repository_local_review") is True
            and context.get("automatic_cleanup_prohibited") is True
        )
    if name == "dispatching-parallel-agents":
        return (
            _nonempty_string(context.get("caller_model"))
            and context.get("profile_compatible") is True
            and context.get("independent") is True
            and context.get("shared_state") is False
            and context.get("human_gate") is False
        )
    if name == "git-commit":
        return context.get("commit_authority") is True
    if name == "finishing-a-development-branch":
        return False
    if name == "capturing-working-agreements":
        return context.get("activation_trigger") is True
    if name == "using-git-worktrees":
        return context.get("isolation_present") is False
    if name == "test-driven-development":
        return True
    return False


def transition(state: dict, phase: str, **updates: object) -> dict:
    """Apply one authorized transition and reject caller-invented state changes."""
    validate_state(state)
    if phase not in PHASES:
        raise ValueError("unknown phase")

    current = state["phase"]
    allowed = {
        "selected": {"implementing", "blocked"},
        "implementing": {"validated", "blocked"},
        "validated": {"review", "blocked"},
        "review": {"fixing", "approved", "blocked"},
        "fixing": {"implementing", "blocked"},
        "approved": set(),
        "blocked": {"implementing", "validated", "review"},
    }
    if phase not in allowed[current]:
        raise PermissionError(f"invalid phase transition: {current} -> {phase}")
    if current == "implementing" and phase == "validated":
        raise PermissionError(
            "use run_canonical_validation to enter validated phase"
        )

    control_keys = {"approval", "resolution"}
    persisted_updates = {key: value for key, value in updates.items() if key not in control_keys}
    unknown = set(persisted_updates) - REQUIRED_KEYS
    if unknown:
        raise ValueError(f"unknown state update: {sorted(unknown)}")

    if current == "blocked":
        if not _nonempty_string(updates.get("resolution")):
            raise PermissionError("blocked resume requires an explicit resolution")
        pending_gate = state["pending_gate"]
        if pending_gate is not None and updates.get("approval") != pending_gate:
            raise PermissionError("exact Human Gate approval is required")
        permitted = {"base_identity"} if phase == "implementing" else set()
        if set(persisted_updates) - permitted:
            raise ValueError("blocked resume cannot replace persisted evidence")
    elif control_keys & set(updates):
        raise ValueError("approval and resolution apply only to blocked resume")

    result = dict(state)
    if phase == "blocked":
        if set(persisted_updates) - {"pending_gate"}:
            raise ValueError("blocked transition only accepts a pending gate")
        result.update(persisted_updates)
    elif current == "selected" and phase == "implementing":
        if set(persisted_updates) - {"base_identity"}:
            raise ValueError("implementation start only accepts base identity")
        result.update(persisted_updates)
        if not _nonempty_string(result["base_identity"]):
            raise PermissionError("implementation start requires base identity")
    elif current == "validated" and phase == "review":
        if persisted_updates:
            raise ValueError("review must use persisted validation evidence")
        if not _has_passing_validation(result):
            raise PermissionError("review requires persisted passing validation evidence")
    elif current == "review" and phase in {"fixing", "approved"}:
        if set(persisted_updates) - {"reviewer_report", "reviewer_verdict"}:
            raise ValueError("review transition accepts only verdict and report")
        result.update(persisted_updates)
        required_verdict = "NEEDS_FIXES" if phase == "fixing" else "APPROVED"
        if (
            result["reviewer_verdict"] != required_verdict
            or not _nonempty_string(result["reviewer_report"])
        ):
            raise PermissionError(f"{phase} requires {required_verdict} and reviewer report")
        worktree = _worktree_path(result["worktree"])
        report_path, _ = _relative_worktree_path(worktree, result["reviewer_report"])
        receipt, report, _ = _verified_review_result(
            worktree, result["reviewer_report"], "task"
        )
        verified = _verify_validator_evidence(result)
        if (
            receipt["task_id"] != result["task_id"]
            or receipt["diff_identity"] != result["diff_identity"]
            or receipt["validator_evidence"] != _validator_evidence_summary(verified)
            or _current_diff_identity(worktree, report_path) != receipt["diff_identity"]
            or report["verdict"] != required_verdict
            or (phase == "approved" and report["unresolved_important_or_critical_findings"] != 0)
        ):
            raise PermissionError("reviewer report does not permit this transition")
        if phase == "fixing":
            result["fix_round"] += 1
    elif current == "fixing" and phase == "implementing":
        if persisted_updates:
            raise ValueError("fix implementation resume accepts no state replacement")
    elif current == "blocked":
        result.update(persisted_updates)
        result["pending_gate"] = None
        if phase == "implementing" and not _nonempty_string(result["base_identity"]):
            raise PermissionError("implementation resume requires base identity")
        if phase in {"validated", "review"} and not _has_passing_validation(result):
            raise PermissionError("resume phase requires persisted passing validation evidence")
    else:
        raise PermissionError(f"unsupported phase transition: {current} -> {phase}")

    result["phase"] = phase
    result["updated_at"] = datetime.now(UTC).isoformat()
    validate_state(result)
    return result


def new_state(change_id: str, task_id: str, worktree: str) -> dict:
    """Create a selected state with the exact version-one schema."""
    now = datetime.now(UTC).isoformat()
    state = {key: None for key in REQUIRED_KEYS}
    state.update(
        {
            "schema": SCHEMA_VERSION,
            "change_id": change_id,
            "task_id": task_id,
            "phase": "selected",
            "worktree": worktree,
            "fix_round": 0,
            "created_at": now,
            "updated_at": now,
        }
    )
    validate_state(state)
    return state


def _validate_change_id(change_id: str) -> None:
    if not isinstance(change_id, str) or not CHANGE_ID.fullmatch(change_id):
        raise ValueError("change identifier is invalid")


def execution_state_path(repository_root: Path, expected_change_id: str) -> Path:
    """Return the only allowed state path for one validated OpenSpec change ID."""
    _validate_change_id(expected_change_id)
    root = Path(repository_root)
    if root.exists() and not root.is_dir():
        raise ValueError("repository root must be a directory")
    return root.resolve() / ".agentic-workflow" / "executions" / f"{expected_change_id}.json"


def write_state(repository_root: Path, expected_change_id: str, state: dict) -> None:
    """Validate and atomically replace one recoverable local state file."""
    validate_state(state)
    if state["change_id"] != expected_change_id:
        raise ValueError("state change identifier does not match the requested change")
    path = execution_state_path(repository_root, expected_change_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump(state, temporary, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def read_state(repository_root: Path, expected_change_id: str) -> dict:
    """Read one state file and fail closed on I/O, JSON, or schema corruption."""
    path = execution_state_path(repository_root, expected_change_id)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("state is corrupt") from error
    validate_state(state)
    if state["change_id"] != expected_change_id:
        raise ValueError("state change identifier does not match the requested change")
    return state


def validate_state(state: dict) -> None:
    """Validate exact keys, types, identifiers, timestamps, and phase invariants."""
    if not isinstance(state, dict) or set(state) != REQUIRED_KEYS:
        raise ValueError("state keys are invalid")
    if type(state["schema"]) is not int or state["schema"] != SCHEMA_VERSION:
        raise ValueError("state schema version is invalid")
    if not isinstance(state["change_id"], str) or not CHANGE_ID.fullmatch(
        state["change_id"]
    ):
        raise ValueError("change identifier is invalid")
    if not isinstance(state["task_id"], str) or not TASK_ID.fullmatch(state["task_id"]):
        raise ValueError("task identifier is invalid")
    if (
        not _nonempty_string(state["worktree"])
        or not Path(state["worktree"]).is_absolute()
    ):
        raise ValueError("worktree is invalid")
    if state["phase"] not in PHASES:
        raise ValueError("phase is invalid")
    if type(state["fix_round"]) is not int or state["fix_round"] < 0:
        raise ValueError("fix round is invalid")

    nullable_strings = {
        "base_identity",
        "diff_identity",
        "validator_evidence_path",
        "validator_hash",
        "validator_worktree_digest",
        "implementer_report",
        "reviewer_report",
        "pending_gate",
    }
    for key in nullable_strings:
        if state[key] is not None and not _nonempty_string(state[key]):
            raise ValueError(f"{key} must be null or a non-empty string")
    if state["validator_status"] is not None and state["validator_status"] not in VALIDATOR_STATUSES:
        raise ValueError("validator status is invalid")
    if state["reviewer_verdict"] is not None and state["reviewer_verdict"] not in REVIEWER_VERDICTS:
        raise ValueError("reviewer verdict is invalid")
    if state["validator_hash"] is not None and not SHA256.fullmatch(state["validator_hash"]):
        raise ValueError("validator hash is invalid")
    if state["validator_worktree_digest"] is not None and not SHA256.fullmatch(
        state["validator_worktree_digest"]
    ):
        raise ValueError("validator worktree digest is invalid")

    created = _parse_timestamp(state["created_at"])
    updated = _parse_timestamp(state["updated_at"])
    if updated < created:
        raise ValueError("updated timestamp precedes creation")

    evidence_values = [
        state["validator_evidence_path"],
        state["validator_hash"],
        state["validator_worktree_digest"],
        state["validator_status"],
    ]
    if any(value is not None for value in evidence_values) and not all(
        value is not None for value in evidence_values
    ):
        raise ValueError("validator evidence identity is incomplete")
    if any(value is not None for value in evidence_values) and not (
        _nonempty_string(state["diff_identity"])
        and _nonempty_string(state["implementer_report"])
    ):
        raise ValueError("validator evidence lacks diff or implementer report")
    if (state["reviewer_report"] is None) != (state["reviewer_verdict"] is None):
        raise ValueError("reviewer report and verdict must be paired")
    if state["reviewer_verdict"] is not None and not _has_passing_validation(state):
        raise ValueError("review verdict lacks passing validation evidence")
    if state["pending_gate"] is not None and state["phase"] != "blocked":
        raise ValueError("pending gate is valid only while blocked")

    phase = state["phase"]
    if phase == "selected" and (
        state["fix_round"] != 0
        or any(state[key] is not None for key in VALIDATION_FIELDS)
        or state["reviewer_report"] is not None
    ):
        raise ValueError("selected state contains impossible evidence")
    if phase in {"validated", "review"} and (
        not _has_passing_validation(state) or state["reviewer_report"] is not None
    ):
        raise ValueError(f"{phase} state invariant is invalid")
    if phase == "fixing" and (
        not _has_passing_validation(state)
        or state["reviewer_verdict"] != "NEEDS_FIXES"
        or state["fix_round"] < 1
    ):
        raise ValueError("fixing state invariant is invalid")
    if phase == "approved" and (
        not _has_passing_validation(state)
        or state["reviewer_verdict"] != "APPROVED"
    ):
        raise ValueError("approved state invariant is invalid")
