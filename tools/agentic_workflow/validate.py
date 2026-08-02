#!/usr/bin/env python3
"""Execute the repository Validation Contract and write JSON evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


TABLE_ROW = re.compile(r"^\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$")
REDACTION_PATTERNS = (
    re.compile(r"(?i)([\"']?authorization[\"']?\s*:\s*[\"']?)(?:basic|bearer)\s+[^\s\"']+"),
    re.compile(r"(?i)(\bauthorization\b\s+)(?:basic|bearer)\s+\S+"),
    re.compile(r"(?i)\bauthorization\s*[:=]\s*(?:basic|bearer)\s+[^\s'\"`]+"),
    re.compile(r"(?i)(\b(?:token|password|secret)\b[\"']?\s*[:=]\s*[\"']?)[^\s,;}'\"]+"),
    re.compile(r"(?i)(\b(?:token|password|secret)\b\s+)[^\s,;}'\"]+"),
    re.compile(r"(?i)(\bauthorization\s*[:=]\s*)[^\s'\"`]+"),
    re.compile(r"(?i)\bgh[pousr]_[a-z0-9_]+\b"),
)
GATE_HEADER = ("Order", "Gate ID", "Applicability", "Mandatory", "Timeout", "Command")
LOCAL_WORKTREE_EXCLUSIONS = (".agentic-workflow/", ".superpowers/sdd/", "working-notes/")


def redact(value: str) -> str:
    """Remove common credential values while retaining useful diagnostics."""
    value = value.replace('\\"', '"')
    value = REDACTION_PATTERNS[0].sub(lambda match: f"{match.group(1)}[REDACTED]", value)
    value = REDACTION_PATTERNS[1].sub(lambda match: f"{match.group(1)}[REDACTED]", value)
    value = REDACTION_PATTERNS[2].sub("authorization: [REDACTED]", value)
    value = REDACTION_PATTERNS[3].sub(lambda match: f"{match.group(1)}[REDACTED]", value)
    value = REDACTION_PATTERNS[4].sub(lambda match: f"{match.group(1)}[REDACTED]", value)
    value = REDACTION_PATTERNS[5].sub(lambda match: f"{match.group(1)}[REDACTED]", value)
    value = REDACTION_PATTERNS[6].sub("[REDACTED]", value)
    return value


def parse_contract(contract: Path) -> list[dict[str, object]]:
    lines = contract.read_text(encoding="utf-8").splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == "## Gate registry")
    except StopIteration as error:
        raise ValueError("Validation Contract has no Gate registry section") from error
    table_lines = []
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        if line.strip():
            table_lines.append(line)
    if len(table_lines) < 3:
        raise ValueError("Gate registry table is incomplete")
    header = TABLE_ROW.match(table_lines[0])
    if not header or tuple(field.strip() for field in header.groups()) != GATE_HEADER:
        raise ValueError("Gate registry header is invalid")
    separator = TABLE_ROW.match(table_lines[1])
    if not separator or tuple(field.strip() for field in separator.groups()) != ("---:", "---", "---", "---", "---:", "---"):
        raise ValueError("Gate registry separator is invalid")
    gates: list[dict[str, object]] = []
    for line in table_lines[2:]:
        match = TABLE_ROW.match(line)
        if not match:
            raise ValueError(f"invalid Gate registry row: {line}")
        fields = [field.strip().strip("`") for field in match.groups()]
        try:
            timeout = float(fields[4])
            if not math.isfinite(timeout) or timeout <= 0:
                raise ValueError("timeout must be positive")
            if fields[3].lower() not in {"yes", "no"}:
                raise ValueError("mandatory must be yes or no")
            if not fields[1] or not re.fullmatch(r"[a-z][a-z0-9-]*", fields[1]):
                raise ValueError("gate ID is invalid")
            if not fields[5]:
                raise ValueError("command must not be empty")
            gate = {
                "order": int(fields[0]),
                "id": fields[1],
                "applicability": fields[2],
                "mandatory": fields[3].lower() == "yes",
                "timeout": timeout,
                "command": fields[5],
            }
        except ValueError as error:
            raise ValueError(f"invalid Gate registry row ({error}): {line}") from error
        gates.append(gate)
    if not gates:
        raise ValueError("Validation Contract has no gate rows")
    if len({gate["id"] for gate in gates}) != len(gates) or len({gate["order"] for gate in gates}) != len(gates):
        raise ValueError("duplicate gate ID or order")
    return sorted(gates, key=lambda gate: (gate["order"], gate["id"]))


def git_value(repository: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def git_bytes(repository: Path, *args: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            capture_output=True, check=False, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def worktree_state(repository: Path, exclusions: tuple[str, ...]) -> str | None:
    """Return porcelain state without validator-local evidence or review scratch paths."""
    status = git_bytes(repository, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    if status is None:
        return None
    entries = []
    for entry in status.split(b"\0"):
        if not entry:
            continue
        path = entry[3:].decode("utf-8", errors="surrogateescape")
        if any(path == excluded.rstrip("/") or path.startswith(excluded) for excluded in exclusions):
            continue
        entries.append(entry)
    return b"\0".join(entries).decode("utf-8", errors="surrogateescape")


def worktree_digest(repository: Path, exclusions: tuple[str, ...]) -> str | None:
    """Hash tracked diffs plus unignored untracked file bytes in path order.

    Local evidence and approved scratch paths are excluded so writing this
    validator's output cannot change the identity it records.
    """
    tracked_diff = git_bytes(repository, "diff", "--binary", "HEAD", "--")
    untracked = git_bytes(repository, "ls-files", "--others", "--exclude-standard", "-z")
    if tracked_diff is None or untracked is None:
        return None
    digest = hashlib.sha256(b"tracked-diff\0" + tracked_diff)
    for encoded_path in sorted(path for path in untracked.split(b"\0") if path):
        relative_path = encoded_path.decode("utf-8", errors="surrogateescape")
        if any(relative_path == excluded.rstrip("/") or relative_path.startswith(excluded) for excluded in exclusions):
            continue
        candidate = repository / relative_path
        if candidate.is_file():
            digest.update(b"\0untracked\0" + encoded_path + b"\0" + candidate.read_bytes())
    return digest.hexdigest()


def repository_identity(repository: Path, output_path: Path | None = None) -> dict[str, object]:
    exclusions = list(LOCAL_WORKTREE_EXCLUSIONS)
    if output_path is not None:
        try:
            exclusions.append(str(output_path.resolve().relative_to(repository.resolve())).replace("\\", "/"))
        except ValueError:
            pass
    return {
        "path": str(repository.resolve()),
        "git_revision": git_value(repository, "rev-parse", "HEAD"),
        "worktree_state": worktree_state(repository, tuple(exclusions)),
        "worktree_digest": worktree_digest(repository, tuple(exclusions)),
        "worktree_digest_exclusions": exclusions,
    }


def is_applicable(rule: str, repository: Path) -> tuple[bool, str | None]:
    if rule == "always":
        return True, None
    if rule.startswith("path:"):
        relative_path = rule.removeprefix("path:")
        if (repository / relative_path).exists():
            return True, None
        return False, f"repository path is absent: {relative_path}"
    raise ValueError(f"unsupported applicability rule: {rule}")


def run_gate(gate: dict[str, object], repository: Path, skip_ids: set[str]) -> dict[str, object]:
    command = str(gate["command"])
    result = {
        "id": gate["id"], "order": gate["order"], "applicability": gate["applicability"],
        "mandatory": gate["mandatory"], "command": redact(command), "status": "pass",
        "duration_seconds": 0.0, "exit_code": None, "reason": None, "output": "",
    }
    applicable, reason = is_applicable(str(gate["applicability"]), repository)
    if not applicable:
        result.update(status="not-applicable", reason=reason)
        return result
    if str(gate["id"]) in skip_ids:
        result.update(status="skipped", reason="skipped without recorded authority")
        return result
    try:
        arguments = shlex.split(command)
    except ValueError as error:
        result.update(status="fail", reason=f"invalid command: {error}")
        return result
    started = time.monotonic()
    try:
        completed = subprocess.run(
            arguments, cwd=repository, capture_output=True, text=True,
            timeout=float(gate["timeout"]), check=False,
        )
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        result["exit_code"] = completed.returncode
        result["output"] = redact((completed.stdout or "") + (completed.stderr or ""))
        if completed.returncode != 0:
            result.update(status="fail", reason=f"command exited with status {completed.returncode}")
    except FileNotFoundError:
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        result.update(status="skipped", reason="executable is unavailable")
    except subprocess.TimeoutExpired as error:
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        output = to_text(error.stdout) + to_text(error.stderr)
        result.update(status="fail", reason="command timed out", output=redact(output))
    return result


def to_text(value: str | bytes | None) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def run_validation(repository: Path, contract: Path, skip_ids: set[str] | None = None, output_path: Path | None = None) -> dict[str, object]:
    repository = repository.resolve()
    contract = contract.resolve()
    gates = [run_gate(gate, repository, skip_ids or set()) for gate in parse_contract(contract)]
    blocking_statuses = {"fail", "skipped"}
    overall_status = "fail" if any(gate["mandatory"] and gate["status"] in blocking_statuses for gate in gates) else "pass"
    return {
        "repository": repository_identity(repository, output_path),
        "contract_hash": hashlib.sha256(contract.read_bytes()).hexdigest(),
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_status": overall_status,
        "gates": gates,
    }


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--contract", type=Path, default=Path("docs/agentic-workflow/validation-contract.md"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-gate", action="append", default=[])
    args = parser.parse_args(arguments)
    repository = args.repository.resolve()
    contract = args.contract if args.contract.is_absolute() else repository / args.contract
    output = args.output if args.output.is_absolute() else repository / args.output
    evidence = run_validation(repository, contract, set(args.skip_gate), output)
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(evidence, indent=2) + "\n"
    output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if evidence["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
