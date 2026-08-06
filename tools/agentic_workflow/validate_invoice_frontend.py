#!/usr/bin/env python3
"""Validate the frontend invoice boundary, rendered preview, and production build."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import subprocess
import time
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
TEST_COMMAND = [
    "pnpm",
    "exec",
    "vitest",
    "run",
    "src/features/invoices/in-memory-invoice-service.test.ts",
    "src/features/invoices/tauri-invoice-service.test.ts",
    "src/features/invoices/InvoicePage.test.tsx",
    "src/features/invoices/InvoicePreview.test.tsx",
    "src/features/invoices/DailyActivityChart.test.tsx",
    "src/features/invoices/WorkCategoryChart.test.tsx",
    "src/app/AppShell.test.tsx",
]
REQUIRED_TEST_FILE_COUNT = 7
PREVIEW_COMMAND = ["node", "tools/agentic_workflow/invoice_preview/render.mjs"]
BUILD_COMMAND = ["pnpm", "build"]
COMMANDS = (
    ("frontend-tests", TEST_COMMAND),
    ("preview-render", PREVIEW_COMMAND),
    ("frontend-build", BUILD_COMMAND),
)
PREVIEW_CASES = ("long-label", "both-charts", "single-chart", "no-optional")
PREVIEW_WIDTHS = (("wide", 1120), ("narrow", 360))
PREVIEW_ARTIFACT_ROOT = ROOT / "tmp" / "invoice-preview-validation"
PREVIEW_SOURCES = (
    "src/features/invoices/InvoicePreview.tsx",
    "src/features/invoices/DailyActivityChart.tsx",
    "src/features/invoices/WorkCategoryChart.tsx",
    "src/features/invoices/invoice.css",
    "src/features/invoices/validation-preview/index.html",
    "src/features/invoices/validation-preview/main.tsx",
    "src/features/invoices/validation-preview/documents.ts",
    "src/features/invoices/validation-preview/preview.css",
    "tools/agentic_workflow/invoice_preview/render.mjs",
)

Runner = Callable[..., Any]


def preview_source_sha256() -> str:
    digest = hashlib.sha256()
    for relative_path in PREVIEW_SOURCES:
        path = ROOT / relative_path
        digest.update(relative_path.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def output_error(identifier: str, output: str) -> str | None:
    if identifier == "frontend-tests":
        if re.search(
            r"(?:^|\n)\s*(?:FAIL\b|Failed Suites\b)|Test Files[^\n]*\bfailed\b|Tests[^\n]*\bfailed\b",
            output,
            re.IGNORECASE,
        ):
            return "Vitest reported a failed suite or test"
        file_summary = re.search(r"Test Files\s+(\d+) passed", output)
        if not file_summary:
            return "Vitest output lacks a passing file summary"
        if int(file_summary.group(1)) != REQUIRED_TEST_FILE_COUNT:
            return "Vitest output does not report every required test file passing"
        test_summary = re.search(r"Tests\s+(\d+) passed", output)
        if not test_summary:
            return "Vitest output lacks a passing test summary"
        if int(test_summary.group(1)) == 0:
            return "Vitest output reports zero passing tests"
        return None

    if identifier == "frontend-build":
        if re.search(
            r"\berror TS\d+:|error during build|Rollup failed|Build failed|failed to load config",
            output,
            re.IGNORECASE,
        ):
            return "TypeScript or Vite reported a build error"
        if not re.search(r"\btsc\b\s*&&\s*\bvite build\b", output):
            return "build output lacks the exact TypeScript and Vite command"
        if not re.search(r"(?:✓|built)\s+built in", output, re.IGNORECASE):
            return "Vite output lacks a successful build summary"
    return None


def validate_preview_evidence(
    output: str,
    *,
    artifact_root: Path,
    started_ns: int,
) -> tuple[str | None, dict[str, object] | None]:
    try:
        evidence = json.loads(output)
    except json.JSONDecodeError:
        return "preview renderer output is not one JSON document", None
    if not isinstance(evidence, dict) or set(evidence) != {
        "schema",
        "command",
        "renderer",
        "source_sha256",
        "artifacts",
    }:
        return "preview evidence has an invalid top-level schema", None
    if evidence["schema"] != 1 or evidence["command"] != " ".join(PREVIEW_COMMAND):
        return "preview evidence command or schema is invalid", None

    renderer = evidence["renderer"]
    if not isinstance(renderer, dict) or set(renderer) != {
        "name",
        "version",
        "browser_version",
    }:
        return "preview renderer provenance is invalid", None
    if renderer["name"] != "playwright-chromium" or not all(
        isinstance(renderer[key], str) and re.fullmatch(r"\d+(?:\.\d+){2,3}", renderer[key])
        for key in ("version", "browser_version")
    ):
        return "preview renderer name or version is invalid", None
    try:
        package = json.loads((ROOT / "package.json").read_text())
        pinned_version = package["devDependencies"]["playwright"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        return f"pinned preview renderer version could not be read: {error}", None
    if (
        not isinstance(pinned_version, str)
        or not re.fullmatch(r"\d+\.\d+\.\d+", pinned_version)
        or renderer["version"] != pinned_version
    ):
        return "preview renderer version does not match the pinned package", None

    try:
        current_source_hash = preview_source_sha256()
    except OSError as error:
        return f"preview source could not be read: {error}", None
    if evidence["source_sha256"] != current_source_hash:
        return "preview evidence source hash is stale", None

    artifacts = evidence["artifacts"]
    expected = {
        (case_name, width): f"{case_name}-{label}.png"
        for case_name in PREVIEW_CASES
        for label, width in PREVIEW_WIDTHS
    }
    if not isinstance(artifacts, list) or len(artifacts) != len(expected):
        return "preview evidence does not contain every required artifact", None

    root = artifact_root.resolve()
    seen: set[tuple[str, int]] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {
            "case",
            "width",
            "height",
            "path",
            "bytes",
            "sha256",
        }:
            return "preview artifact metadata is invalid", None
        key = (artifact["case"], artifact["width"])
        if key not in expected or key in seen:
            return "preview artifact case or width is unexpected", None
        seen.add(key)
        path_value = artifact["path"]
        if not isinstance(path_value, str):
            return "preview artifact path is invalid", None
        path = Path(path_value).resolve()
        if path.parent != root or path.name != expected[key]:
            return "preview artifact path escaped its exact output directory", None
        try:
            stat = path.stat()
            data = path.read_bytes()
        except OSError:
            return "preview artifact is missing", None
        if stat.st_mtime_ns < started_ns:
            return "preview artifact is stale", None
        if artifact["bytes"] != len(data) or len(data) < 24:
            return "preview artifact byte count is invalid", None
        if artifact["sha256"] != hashlib.sha256(data).hexdigest():
            return "preview artifact hash is invalid", None
        if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            return "preview artifact is not a PNG", None
        png_width, png_height = struct.unpack(">II", data[16:24])
        if (
            png_width != artifact["width"]
            or png_height != artifact["height"]
            or png_width != key[1]
            or png_height < 200
        ):
            return "preview artifact dimensions are invalid", None
        if not isinstance(artifact["sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", artifact["sha256"]
        ):
            return "preview artifact SHA-256 is invalid", None

    if seen != set(expected):
        return "preview evidence is missing a required case and width", None
    return None, evidence


def run_validation(
    *,
    run: Runner = subprocess.run,
    artifact_root: Path = PREVIEW_ARTIFACT_ROOT,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    for identifier, command in COMMANDS:
        started_ns = time.time_ns()
        preview_evidence = None
        try:
            completed = run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            reason = (
                f"command exited with status {completed.returncode}"
                if completed.returncode != 0
                else output_error(identifier, output)
            )
            if not reason and identifier == "preview-render":
                reason, preview_evidence = validate_preview_evidence(
                    output,
                    artifact_root=artifact_root,
                    started_ns=started_ns,
                )
            result: dict[str, object] = {
                "id": identifier,
                "command": " ".join(command),
                "status": "fail" if reason else "pass",
                "exit_code": completed.returncode,
                "reason": reason,
                "output": output,
            }
            if preview_evidence is not None:
                result["evidence"] = preview_evidence
            results.append(result)
        except OSError as error:
            results.append(
                {
                    "id": identifier,
                    "command": " ".join(command),
                    "status": "fail",
                    "exit_code": None,
                    "reason": f"command could not start: {error}",
                    "output": "",
                }
            )
    return {
        "repository": str(ROOT),
        "overall_status": (
            "pass" if all(result["status"] == "pass" for result in results) else "fail"
        ),
        "results": results,
    }


def main() -> int:
    evidence = run_validation()
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["overall_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
