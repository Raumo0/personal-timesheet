import hashlib
import subprocess
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from tools.agentic_workflow import validate_invoice_pdf


def rgb_png(width: int, height: int, pixels: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = b"".join(
        b"\x00" + pixels[y * width * 3 : (y + 1) * width * 3]
        for y in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def dom_evidence(text: str, *, figures: int = 2) -> dict[str, object]:
    return {
        "document_count": 1,
        "text": text,
        "figures": figures,
        "printable_bounds": {
            "within_horizontal_bounds": True,
            "clipped_elements": [],
        },
        "chart_structure_sha256": "chart-structure",
        "chart_styles": [
            {
                "selector": ".invoice-daily-chart__bar",
                "fill": "rgb(36, 87, 214)",
            }
        ],
    }


class InvoicePdfValidatorTests(unittest.TestCase):
    def test_native_invoice_commands_pass_and_record_exact_evidence(self):
        if not hasattr(validate_invoice_pdf, "validate_native_tests"):
            self.fail("native invoice validation is not implemented")
        expected_commands = (
            (
                "cargo",
                "test",
                "--manifest-path",
                "src-tauri/Cargo.toml",
                "invoice::tests",
            ),
            (
                "cargo",
                "test",
                "--manifest-path",
                "src-tauri/Cargo.toml",
                "--test",
                "invoice_source",
            ),
        )
        outputs = iter(
            (
                "running 12 tests\ntest result: ok. 12 passed; 0 failed; 0 ignored; 0 measured",
                "running 6 tests\ntest result: ok. 6 passed; 0 failed; 0 ignored; 0 measured",
            )
        )
        invoked = []

        def successful_run(command, **kwargs):
            invoked.append((tuple(command), kwargs))
            return subprocess.CompletedProcess(command, 0, next(outputs), "")

        evidence = validate_invoice_pdf.validate_native_tests(run=successful_run)

        self.assertEqual(tuple(command for command, _ in invoked), expected_commands)
        self.assertTrue(
            all(
                kwargs
                == {
                    "cwd": validate_invoice_pdf.ROOT,
                    "capture_output": True,
                    "text": True,
                    "check": False,
                }
                for _, kwargs in invoked
            )
        )
        self.assertEqual(
            evidence,
            [
                {
                    "command": "cargo test --manifest-path src-tauri/Cargo.toml invoice::tests",
                    "status": "pass",
                    "exit_code": 0,
                    "passing_tests": 12,
                    "output": "running 12 tests\ntest result: ok. 12 passed; 0 failed; 0 ignored; 0 measured",
                },
                {
                    "command": "cargo test --manifest-path src-tauri/Cargo.toml --test invoice_source",
                    "status": "pass",
                    "exit_code": 0,
                    "passing_tests": 6,
                    "output": "running 6 tests\ntest result: ok. 6 passed; 0 failed; 0 ignored; 0 measured",
                },
            ],
        )

    def test_native_invoice_failure_stops_before_browser_pdf_checks(self):
        if not hasattr(validate_invoice_pdf, "validate_native_tests"):
            self.fail("native invoice validation is not implemented")
        invoked = []

        def failed_run(command, **kwargs):
            invoked.append(tuple(command))
            return subprocess.CompletedProcess(command, 2, "", "native test failure")

        with self.assertRaisesRegex(
            ValueError,
            "(?s)cargo test --manifest-path src-tauri/Cargo.toml invoice::tests.*native test failure",
        ):
            validate_invoice_pdf.validate_native_tests(run=failed_run)
        self.assertEqual(
            invoked,
            [
                (
                    "cargo",
                    "test",
                    "--manifest-path",
                    "src-tauri/Cargo.toml",
                    "invoice::tests",
                )
            ],
        )

        with (
            mock.patch.object(
                validate_invoice_pdf,
                "validate_native_tests",
                side_effect=ValueError("native invoice test command failed"),
            ),
            mock.patch.object(validate_invoice_pdf, "run") as browser_run,
        ):
            with self.assertRaisesRegex(ValueError, "native invoice test command failed"):
                validate_invoice_pdf.validate()
        browser_run.assert_not_called()

    def test_native_invoice_commands_reject_false_success_and_zero_tests(self):
        if not hasattr(validate_invoice_pdf, "validate_native_tests"):
            self.fail("native invoice validation is not implemented")
        false_green_outputs = (
            "running 1 test\ntest result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured",
            "running 0 tests\ntest result: ok. 0 passed; 0 failed; 0 ignored; 0 measured",
        )
        for output in false_green_outputs:
            with self.subTest(output=output):
                def false_green_run(command, **kwargs):
                    return subprocess.CompletedProcess(command, 0, output, "")

                with self.assertRaisesRegex(ValueError, "failed|zero passing"):
                    validate_invoice_pdf.validate_native_tests(run=false_green_run)

    def test_pdf_layout_rejects_orphaned_expenses_heading(self):
        orphaned = """<?xml version="1.0"?>
<doc xmlns="http://www.w3.org/1999/xhtml">
  <page width="595" height="842">
    <word xMin="42" yMin="42" xMax="90" yMax="52">Invoice</word>
    <word xMin="42" yMin="62" xMax="110" yMax="72">Northstar</word>
    <word xMin="112" yMin="62" xMax="150" yMax="72">Studio</word>
    <word xMin="42" yMin="760" xMax="90" yMax="770">Expenses</word>
  </page>
  <page width="595" height="842">
    <word xMin="42" yMin="42" xMax="70" yMax="52">DATE</word>
    <word xMin="42" yMin="62" xMax="48" yMax="72">3</word>
    <word xMin="50" yMin="62" xMax="68" yMax="72">Feb</word>
    <word xMin="70" yMin="62" xMax="94" yMax="72">2026</word>
  </page>
</doc>"""
        with self.assertRaisesRegex(ValueError, "Expenses.*orphaned"):
            validate_invoice_pdf.validate_pdf_layout(
                orphaned,
                expected_rows=(),
                expected_subtotal_count=0,
                required_same_page_groups=(("Expenses", "DATE", "3 Feb 2026"),),
            )

        together = orphaned.replace(
            '<word xMin="42" yMin="760" xMax="90" yMax="770">Expenses</word>',
            "",
        ).replace(
            '<word xMin="42" yMin="42" xMax="70" yMax="52">DATE</word>',
            '<word xMin="42" yMin="30" xMax="90" yMax="40">Expenses</word>\n'
            '    <word xMin="42" yMin="42" xMax="70" yMax="52">DATE</word>',
        )
        evidence = validate_invoice_pdf.validate_pdf_layout(
            together,
            expected_rows=(),
            expected_subtotal_count=0,
            required_same_page_groups=(("Expenses", "DATE", "3 Feb 2026"),),
        )
        self.assertEqual(evidence["pages"], 2)

    def test_pdf_layout_rejects_clipped_header_split_rows_and_repeated_subtotal(self):
        valid = """<?xml version="1.0"?>
<doc xmlns="http://www.w3.org/1999/xhtml">
  <page width="595" height="842">
    <word xMin="42" yMin="42" xMax="90" yMax="52">Invoice</word>
    <word xMin="42" yMin="62" xMax="110" yMax="72">Northstar</word>
    <word xMin="112" yMin="62" xMax="150" yMax="72">Studio</word>
    <word xMin="42" yMin="100" xMax="92" yMax="110">Generated</word>
    <word xMin="94" yMin="100" xMax="118" yMax="110">work</word>
    <word xMin="120" yMin="100" xMax="170" yMax="110">category</word>
    <word xMin="172" yMin="100" xMax="184" yMax="110">01</word>
    <word xMin="42" yMin="114" xMax="100" yMax="124">descriptive</word>
    <word xMin="102" yMin="114" xMax="130" yMax="124">label</word>
    <word xMin="350" yMin="760" xMax="380" yMax="770">Work</word>
    <word xMin="382" yMin="760" xMax="440" yMax="770">performed</word>
    <word xMin="442" yMin="760" xMax="490" yMax="770">subtotal</word>
  </page>
</doc>"""
        evidence = validate_invoice_pdf.validate_pdf_layout(
            valid,
            expected_rows=("01",),
            expected_subtotal_count=1,
        )
        self.assertEqual(evidence["pages"], 1)

        clipped = valid.replace(
            'xMin="42" yMin="42" xMax="90" yMax="52">Invoice',
            'xMin="42" yMin="-2" xMax="90" yMax="8">Invoice',
            1,
        )
        with self.assertRaisesRegex(ValueError, "page bounds"):
            validate_invoice_pdf.validate_pdf_layout(
                clipped,
                expected_rows=("01",),
                expected_subtotal_count=1,
            )

        split = valid.replace(
            "<word xMin=\"42\" yMin=\"114\" xMax=\"100\" yMax=\"124\">descriptive</word>",
            "</page><page width=\"595\" height=\"842\"><word xMin=\"42\" yMin=\"42\" xMax=\"100\" yMax=\"52\">descriptive</word>",
        )
        with self.assertRaisesRegex(ValueError, "split or clipped"):
            validate_invoice_pdf.validate_pdf_layout(
                split,
                expected_rows=("01",),
                expected_subtotal_count=1,
            )

        repeated = valid.replace("</page>", valid[valid.index("<word xMin=\"350\"") : valid.index("</page>")] + "</page>")
        with self.assertRaisesRegex(ValueError, "subtotal"):
            validate_invoice_pdf.validate_pdf_layout(
                repeated,
                expected_rows=("01",),
                expected_subtotal_count=1,
            )

    def test_browser_command_preserves_contract_entrypoint_and_binds_run_token(self):
        self.assertEqual(
            validate_invoice_pdf.browser_command("fresh-token"),
            (
                "node",
                "tools/agentic_workflow/invoice_preview/render.mjs",
                "--pdf",
                "--run-token",
                "fresh-token",
            ),
        )

    def test_source_digest_binds_relative_paths_names_and_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "first.tsx").write_text("first", encoding="utf-8")
            (root / "second.css").write_text("second", encoding="utf-8")
            paths = (Path("first.tsx"), Path("second.css"))
            first = validate_invoice_pdf.source_digest(root, paths)
            (root / "second.css").write_text("changed", encoding="utf-8")
            second = validate_invoice_pdf.source_digest(root, paths)
        self.assertNotEqual(first, second)

    def test_pdfinfo_requires_unencrypted_exact_a4_pages(self):
        valid = "Pages: 3\nEncrypted: no\nPage size: 595.276 x 841.89 pts (A4)\n"
        self.assertEqual(validate_invoice_pdf.parse_pdfinfo(valid)["pages"], 3)
        chromium = "Pages: 3\nEncrypted: no\nPage size: 594.96 x 841.92 pts (A4)\n"
        self.assertEqual(validate_invoice_pdf.parse_pdfinfo(chromium)["pages"], 3)
        with self.assertRaisesRegex(ValueError, "A4"):
            validate_invoice_pdf.parse_pdfinfo(
                "Pages: 3\nEncrypted: no\nPage size: 612 x 792 pts\n"
            )
        with self.assertRaisesRegex(ValueError, "encrypted"):
            validate_invoice_pdf.parse_pdfinfo(
                "Pages: 3\nEncrypted: yes\nPage size: 595.276 x 841.89 pts (A4)\n"
            )

    def test_selectable_pdf_requires_extracted_identity_exact_total_and_optional_text(self):
        data = b"%PDF-1.7\n/FontFile2 1 0 R\n/ToUnicode 2 0 R\n/StructTreeRoot 3 0 R\n"
        extracted_text = (
            "Invoice Northstar Studio Atlas Labs Europe 8 Feb 2026 "
            "1 Feb 2026 – 7 Feb 2026 International Atlas launch "
            "Total due €2,029.00 PAYMENT NOTE Work summary"
        )
        required_identity = (
            "Invoice",
            "Northstar Studio",
            "Atlas Labs Europe",
            "8 Feb 2026",
            "1 Feb 2026 – 7 Feb 2026",
            "International Atlas launch",
            "Total due",
            "€2,029.00",
            "PAYMENT NOTE",
            "Work summary",
        )
        validate_invoice_pdf.validate_selectable_pdf(
            data,
            extracted_text,
            required_identity,
            ("Personal Timesheet",),
        )
        for missing_identity in (
            "8 Feb 2026",
            "1 Feb 2026",
            "7 Feb 2026",
            "International Atlas launch",
        ):
            with self.subTest(missing_identity=missing_identity):
                with self.assertRaisesRegex(ValueError, "extracted PDF text"):
                    validate_invoice_pdf.validate_selectable_pdf(
                        data,
                        extracted_text.replace(missing_identity, ""),
                        required_identity,
                        ("Personal Timesheet",),
                    )
        with self.assertRaisesRegex(ValueError, "selectable"):
            validate_invoice_pdf.validate_selectable_pdf(
                data.replace(b"/ToUnicode", b"/NoUnicode"),
                "Invoice Northstar Studio Atlas Labs Europe Total due €2,029.00",
                ("Invoice",),
                (),
            )
        with self.assertRaisesRegex(ValueError, "extracted PDF text"):
            validate_invoice_pdf.validate_selectable_pdf(
                data,
                "",
                ("Invoice", "Northstar Studio", "Atlas Labs Europe", "€2,029.00"),
                (),
            )
        with self.assertRaisesRegex(ValueError, "€2,029.00"):
            validate_invoice_pdf.validate_selectable_pdf(
                data,
                "Invoice Northstar Studio Atlas Labs Europe Total due €2,039.00",
                ("Invoice", "Northstar Studio", "Atlas Labs Europe", "€2,029.00"),
                (),
            )
        with self.assertRaisesRegex(ValueError, "forbidden extracted PDF text"):
            validate_invoice_pdf.validate_selectable_pdf(
                data,
                "Invoice Northstar Studio Atlas Labs Europe Total due €2,029.00 PAYMENT NOTE",
                ("Invoice", "€2,029.00"),
                ("PAYMENT NOTE",),
            )

    def test_case_specifications_bind_identity_exact_totals_and_optional_sections(self):
        expected_totals = {
            "both-charts": "€2,029.00",
            "long-label": "€2,029.00",
            "single-chart": "€2,029.00",
            "no-optional": "€2,029.00",
            "multi-project": "€2,509.00",
            "long-table": "€3,069.00",
        }
        for name, expected_total in expected_totals.items():
            specification = validate_invoice_pdf.CASE_SPECIFICATIONS[name]
            self.assertIn("Northstar Studio", specification["pdf_required_text"])
            self.assertIn("Atlas Labs Europe", specification["pdf_required_text"])
            self.assertIn("8 Feb 2026", specification["pdf_required_text"])
            self.assertIn(
                "1 Feb 2026 – 7 Feb 2026", specification["pdf_required_text"]
            )
            self.assertIn(
                "International Atlas launch", specification["pdf_required_text"]
            )
            self.assertIn(expected_total, specification["pdf_required_text"])
        self.assertIn(
            "PAYMENT NOTE",
            validate_invoice_pdf.CASE_SPECIFICATIONS["both-charts"]["pdf_required_text"],
        )
        self.assertIn(
            "PAYMENT NOTE",
            validate_invoice_pdf.CASE_SPECIFICATIONS["no-optional"]["pdf_forbidden_text"],
        )

    def test_case_evidence_requires_single_bounded_dom_and_screen_print_chart_parity(self):
        text = "Invoice Northstar Studio Atlas Labs Total due Daily activity"
        evidence = {
            "screen": dom_evidence(text),
            "print": dom_evidence(text),
        }
        validate_invoice_pdf.validate_dom_evidence(
            "both-charts",
            evidence,
            required_text=("Invoice", "Total due", "Daily activity"),
            forbidden_text=("Personal Timesheet",),
            expected_figures=2,
        )

        evidence["print"]["chart_styles"] = []
        with self.assertRaisesRegex(ValueError, "chart styles"):
            validate_invoice_pdf.validate_dom_evidence(
                "both-charts",
                evidence,
                required_text=("Invoice",),
                forbidden_text=(),
                expected_figures=2,
            )

    def test_case_evidence_rejects_optional_content_and_printable_overflow(self):
        text = "Invoice Northstar Studio Atlas Labs Total due"
        screen = dom_evidence(text, figures=0)
        printed = dom_evidence(text, figures=0)
        printed["printable_bounds"] = {
            "within_horizontal_bounds": False,
            "clipped_elements": ["Expense amount"],
        }
        with self.assertRaisesRegex(ValueError, "printable bounds"):
            validate_invoice_pdf.validate_dom_evidence(
                "no-optional",
                {"screen": screen, "print": printed},
                required_text=("Invoice", "Total due"),
                forbidden_text=("Invoice no.", "Payment note", "Work summary"),
                expected_figures=0,
            )

        printed = dom_evidence(f"{text} Payment note", figures=0)
        with self.assertRaisesRegex(ValueError, "forbidden text"):
            validate_invoice_pdf.validate_dom_evidence(
                "no-optional",
                {"screen": screen, "print": printed},
                required_text=("Invoice",),
                forbidden_text=("Payment note",),
                expected_figures=0,
            )

    def test_manifest_requires_fresh_token_source_hash_cases_and_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "both-charts.pdf"
            pdf.write_bytes(b"%PDF-1.7 browser print")
            digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
            text = "Invoice Northstar Studio Atlas Labs Total due Daily activity Work category breakdown"
            payload = {
                "schema": 2,
                "command": validate_invoice_pdf.BROWSER_COMMAND_TEXT,
                "run_token": "fresh-token",
                "source_sha256": "source-hash",
                "renderer": {"name": "playwright-chromium", "version": "1", "browser_version": "2"},
                "artifacts": [
                    {
                        "case": "both-charts",
                        "pdf": "both-charts.pdf",
                        "sha256": digest,
                        "screen": dom_evidence(text),
                        "print": dom_evidence(text),
                    }
                ],
            }
            specifications = {
                "both-charts": {
                    "required_text": ("Invoice", "Daily activity", "Work category breakdown"),
                    "forbidden_text": ("Personal Timesheet",),
                    "figures": 2,
                }
            }
            validated = validate_invoice_pdf.validate_browser_manifest(
                payload,
                root=root,
                run_token="fresh-token",
                source_sha256="source-hash",
                specifications=specifications,
            )
            self.assertEqual(validated[0]["path"], pdf.resolve())

            payload["run_token"] = "stale-token"
            with self.assertRaisesRegex(ValueError, "run token"):
                validate_invoice_pdf.validate_browser_manifest(
                    payload,
                    root=root,
                    run_token="fresh-token",
                    source_sha256="source-hash",
                    specifications=specifications,
                )

    def test_rendered_png_rejects_nonwhite_outer_margin(self):
        white = bytearray([255] * 60 * 60 * 3)
        validate_invoice_pdf.validate_png_bounds(rgb_png(60, 60, bytes(white)))
        white[0:3] = b"\x00\x00\x00"
        with self.assertRaisesRegex(ValueError, "outer margin"):
            validate_invoice_pdf.validate_png_bounds(rgb_png(60, 60, bytes(white)))


if __name__ == "__main__":
    unittest.main()
