import hashlib
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tools.agentic_workflow.validate_invoice_frontend import (
    BUILD_COMMAND,
    PREVIEW_CASES,
    PREVIEW_COMMAND,
    PREVIEW_WIDTHS,
    TEST_COMMAND,
    preview_source_sha256,
    run_validation,
)


PASSING_OUTPUTS = {
    tuple(TEST_COMMAND): "Test Files  7 passed (7)\nTests  61 passed (61)\n",
    tuple(BUILD_COMMAND): "$ tsc && vite build\n✓ built in 2.8s\n",
}


def png_header(width: int, height: int, marker: str) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
        + marker.encode()
    )


def renderer_output(
    artifact_root: Path,
    *,
    omit: tuple[str, int] | None = None,
    source_sha256: str | None = None,
    corrupt_hash: tuple[str, int] | None = None,
    stale: tuple[str, int] | None = None,
    renderer_version: str = "1.62.1",
) -> str:
    artifacts = []
    for case_name in PREVIEW_CASES:
        for label, width in PREVIEW_WIDTHS:
            if omit == (case_name, width):
                continue
            path = artifact_root / f"{case_name}-{label}.png"
            data = png_header(width, 640, f"{case_name}-{label}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if stale == (case_name, width):
                os.utime(path, ns=(1, 1))
            digest = hashlib.sha256(data).hexdigest()
            if corrupt_hash == (case_name, width):
                digest = "0" * 64
            artifacts.append(
                {
                    "case": case_name,
                    "width": width,
                    "height": 640,
                    "path": str(path),
                    "bytes": len(data),
                    "sha256": digest,
                }
            )
    return json.dumps(
        {
            "schema": 1,
            "command": " ".join(PREVIEW_COMMAND),
            "renderer": {
                "name": "playwright-chromium",
                "version": renderer_version,
                "browser_version": "151.0.7922.34",
            },
            "source_sha256": source_sha256 or preview_source_sha256(),
            "artifacts": artifacts,
        }
    )


class InvoiceFrontendValidatorTests(unittest.TestCase):
    def test_runs_exact_seven_frontend_suites_preview_renderer_then_build(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)
            calls = []

            def run(command, **kwargs):
                calls.append((command, kwargs))
                output = (
                    renderer_output(artifact_root)
                    if command == PREVIEW_COMMAND
                    else PASSING_OUTPUTS[tuple(command)]
                )
                return SimpleNamespace(returncode=0, stdout=output, stderr="")

            evidence = run_validation(run=run, artifact_root=artifact_root)

        expected_test_command = [
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
        self.assertEqual(
            [call[0] for call in calls],
            [expected_test_command, PREVIEW_COMMAND, ["pnpm", "build"]],
        )
        self.assertTrue(all(call[1]["capture_output"] for call in calls))
        self.assertEqual(evidence["overall_status"], "pass")
        self.assertEqual(PREVIEW_CASES, ("long-label", "both-charts", "single-chart", "no-optional"))
        self.assertEqual(PREVIEW_WIDTHS, (("wide", 1120), ("narrow", 360)))
        self.assertEqual(
            [(result["id"], result["status"]) for result in evidence["results"]],
            [
                ("frontend-tests", "pass"),
                ("preview-render", "pass"),
                ("frontend-build", "pass"),
            ],
        )
        preview = evidence["results"][1]["evidence"]
        self.assertEqual(preview["renderer"]["version"], "1.62.1")
        self.assertEqual(len(preview["artifacts"]), 8)

    def test_fails_on_nonzero_test_renderer_or_build_results(self):
        for failed_command in (
            tuple(TEST_COMMAND),
            tuple(PREVIEW_COMMAND),
            tuple(BUILD_COMMAND),
        ):
            with self.subTest(command=failed_command), tempfile.TemporaryDirectory() as directory:
                artifact_root = Path(directory)

                def run(command, **_kwargs):
                    output = (
                        renderer_output(artifact_root)
                        if command == PREVIEW_COMMAND
                        else PASSING_OUTPUTS[tuple(command)]
                    )
                    return SimpleNamespace(
                        returncode=1 if tuple(command) == failed_command else 0,
                        stdout=output,
                        stderr="command failed" if tuple(command) == failed_command else "",
                    )

                evidence = run_validation(run=run, artifact_root=artifact_root)
                self.assertEqual(evidence["overall_status"], "fail")

    def test_rejects_missing_or_hash_mismatched_preview_artifacts(self):
        variants = (
            {"omit": ("long-label", 1120)},
            {"corrupt_hash": ("both-charts", 360)},
            {"stale": ("single-chart", 1120)},
        )
        for variant in variants:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                artifact_root = Path(directory)

                def run(command, **_kwargs):
                    output = (
                        renderer_output(artifact_root, **variant)
                        if command == PREVIEW_COMMAND
                        else PASSING_OUTPUTS[tuple(command)]
                    )
                    return SimpleNamespace(returncode=0, stdout=output, stderr="")

                evidence = run_validation(run=run, artifact_root=artifact_root)
                self.assertEqual(evidence["overall_status"], "fail")
                self.assertEqual(evidence["results"][1]["status"], "fail")

    def test_rejects_preview_evidence_for_stale_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)

            def run(command, **_kwargs):
                output = (
                    renderer_output(artifact_root, source_sha256="0" * 64)
                    if command == PREVIEW_COMMAND
                    else PASSING_OUTPUTS[tuple(command)]
                )
                return SimpleNamespace(returncode=0, stdout=output, stderr="")

            evidence = run_validation(run=run, artifact_root=artifact_root)

        self.assertEqual(evidence["overall_status"], "fail")
        self.assertIn("source", evidence["results"][1]["reason"].lower())

    def test_rejects_renderer_version_not_pinned_by_package(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory)

            def run(command, **_kwargs):
                output = (
                    renderer_output(artifact_root, renderer_version="1.61.0")
                    if command == PREVIEW_COMMAND
                    else PASSING_OUTPUTS[tuple(command)]
                )
                return SimpleNamespace(returncode=0, stdout=output, stderr="")

            evidence = run_validation(run=run, artifact_root=artifact_root)

        self.assertEqual(evidence["overall_status"], "fail")
        self.assertIn("version", evidence["results"][1]["reason"].lower())

    def test_rejects_vitest_or_build_failure_text_even_with_zero_exit(self):
        variants = (
            (TEST_COMMAND, "FAIL src/features/invoices/InvoicePreview.test.tsx\nTest Files 1 failed (1)\n"),
            (BUILD_COMMAND, "src/file.ts(1,1): error TS2322: invalid type\n"),
        )
        for failed_command, failed_output in variants:
            with self.subTest(command=failed_command), tempfile.TemporaryDirectory() as directory:
                artifact_root = Path(directory)

                def run(command, **_kwargs):
                    if command == failed_command:
                        output = failed_output
                    elif command == PREVIEW_COMMAND:
                        output = renderer_output(artifact_root)
                    else:
                        output = PASSING_OUTPUTS[tuple(command)]
                    return SimpleNamespace(returncode=0, stdout=output, stderr="")

                evidence = run_validation(run=run, artifact_root=artifact_root)
                self.assertEqual(evidence["overall_status"], "fail")

    def test_rejects_vitest_zero_or_incomplete_false_green_summaries(self):
        variants = (
            "Test Files  0 passed (0)\nTests  0 passed (0)\n",
            "Test Files  7 passed (7)\nTests  0 passed (0)\n",
            "Test Files  6 passed (6)\nTests  61 passed (61)\n",
        )
        for failed_output in variants:
            with self.subTest(output=failed_output), tempfile.TemporaryDirectory() as directory:
                artifact_root = Path(directory)

                def run(command, **_kwargs):
                    if command == TEST_COMMAND:
                        output = failed_output
                    elif command == PREVIEW_COMMAND:
                        output = renderer_output(artifact_root)
                    else:
                        output = PASSING_OUTPUTS[tuple(command)]
                    return SimpleNamespace(returncode=0, stdout=output, stderr="")

                evidence = run_validation(run=run, artifact_root=artifact_root)
                self.assertEqual(evidence["overall_status"], "fail")
                self.assertEqual(evidence["results"][0]["status"], "fail")


if __name__ == "__main__":
    unittest.main()
