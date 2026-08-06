#!/usr/bin/env python3
"""Print the real React invoice preview and validate representative A4 PDFs."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path("tmp/invoice-pdf-validation")
MANIFEST = OUTPUT_ROOT / "validation.json"
BROWSER_COMMAND_TEXT = "node tools/agentic_workflow/invoice_preview/render.mjs --pdf"
NATIVE_TEST_COMMANDS = (
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
SOURCE_PATHS = (
    Path("src/features/invoices/InvoicePreview.tsx"),
    Path("src/features/invoices/DailyActivityChart.tsx"),
    Path("src/features/invoices/WorkCategoryChart.tsx"),
    Path("src/features/invoices/invoice.css"),
    Path("src/features/invoices/validation-preview/index.html"),
    Path("src/features/invoices/validation-preview/main.tsx"),
    Path("src/features/invoices/validation-preview/documents.ts"),
    Path("src/features/invoices/validation-preview/preview.css"),
    Path("tools/agentic_workflow/invoice_preview/render.mjs"),
)
CASE_SPECIFICATIONS = {
    "both-charts": {
        "required_text": (
            "Invoice",
            "Northstar Studio",
            "Atlas Labs Europe",
            "INV-2026-002",
            "Total due",
            "Daily activity",
            "Work category breakdown",
        ),
        "forbidden_text": ("Personal Timesheet",),
        "pdf_required_text": (
            "Invoice",
            "Northstar Studio",
            "Atlas Labs Europe",
            "INV-2026-002",
            "8 Feb 2026",
            "1 Feb 2026 – 7 Feb 2026",
            "International Atlas launch",
            "Total due",
            "€2,029.00",
            "PAYMENT NOTE",
            "Work summary",
            "Daily activity",
            "Work category breakdown",
        ),
        "pdf_forbidden_text": ("Personal Timesheet",),
        "figures": 2,
    },
    "long-label": {
        "required_text": (
            "Invoice",
            "Discovery, multilingual information architecture",
            "Total due",
            "Daily activity",
            "Work category breakdown",
        ),
        "forbidden_text": ("Personal Timesheet",),
        "pdf_required_text": (
            "Invoice",
            "Northstar Studio",
            "Atlas Labs Europe",
            "INV-2026-002",
            "8 Feb 2026",
            "1 Feb 2026 – 7 Feb 2026",
            "International Atlas launch",
            "Discovery, multilingual information architecture",
            "Total due",
            "€2,029.00",
            "PAYMENT NOTE",
            "Work summary",
            "Daily activity",
            "Work category breakdown",
        ),
        "pdf_forbidden_text": ("Personal Timesheet",),
        "figures": 2,
    },
    "single-chart": {
        "required_text": ("Invoice", "Total due", "Daily activity"),
        "forbidden_text": ("Work category breakdown", "Personal Timesheet"),
        "pdf_required_text": (
            "Invoice",
            "Northstar Studio",
            "Atlas Labs Europe",
            "INV-2026-002",
            "8 Feb 2026",
            "1 Feb 2026 – 7 Feb 2026",
            "International Atlas launch",
            "Total due",
            "€2,029.00",
            "PAYMENT NOTE",
            "Work summary",
            "Daily activity",
        ),
        "pdf_forbidden_text": ("Work category breakdown", "Personal Timesheet"),
        "figures": 1,
    },
    "no-optional": {
        "required_text": ("Invoice", "Northstar Studio", "Total due"),
        "forbidden_text": (
            "Invoice no.",
            "Payment note",
            "Work summary",
            "Daily activity",
            "Work category breakdown",
            "Personal Timesheet",
        ),
        "pdf_required_text": (
            "Invoice",
            "Northstar Studio",
            "Atlas Labs Europe",
            "8 Feb 2026",
            "1 Feb 2026 – 7 Feb 2026",
            "International Atlas launch",
            "Total due",
            "€2,029.00",
        ),
        "pdf_forbidden_text": (
            "Invoice no.",
            "INV-2026-002",
            "PAYMENT NOTE",
            "Work summary",
            "Daily activity",
            "Work category breakdown",
            "Personal Timesheet",
        ),
        "figures": 0,
    },
    "multi-project": {
        "required_text": (
            "Invoice",
            "International Atlas launch",
            "Operations portal",
            "Service operations",
            "Work category breakdown",
            "Total due",
        ),
        "forbidden_text": ("Personal Timesheet",),
        "pdf_required_text": (
            "Invoice",
            "Northstar Studio",
            "Atlas Labs Europe",
            "INV-2026-002",
            "8 Feb 2026",
            "1 Feb 2026 – 7 Feb 2026",
            "International Atlas launch",
            "Operations portal",
            "Service operations",
            "Total due",
            "€2,509.00",
            "PAYMENT NOTE",
            "Work summary",
            "Daily activity",
            "Work category breakdown",
        ),
        "pdf_forbidden_text": ("Personal Timesheet",),
        "figures": 2,
    },
    "long-table": {
        "required_text": (
            "Invoice",
            "Generated work category 01",
            "Generated work category 48",
            "Total due",
        ),
        "forbidden_text": (
            "Payment note",
            "Work summary",
            "Daily activity",
            "Work category breakdown",
            "Personal Timesheet",
        ),
        "pdf_required_text": (
            "Invoice",
            "Northstar Studio",
            "Atlas Labs Europe",
            "INV-2026-002",
            "8 Feb 2026",
            "1 Feb 2026 – 7 Feb 2026",
            "International Atlas launch",
            "Generated work category 01",
            "Generated work category 48",
            "Total due",
            "€3,069.00",
        ),
        "pdf_forbidden_text": (
            "PAYMENT NOTE",
            "Work summary",
            "Daily activity",
            "Work category breakdown",
            "Personal Timesheet",
        ),
        "figures": 0,
    },
}


def browser_command(run_token: str) -> tuple[str, ...]:
    return (
        "node",
        "tools/agentic_workflow/invoice_preview/render.mjs",
        "--pdf",
        "--run-token",
        run_token,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_digest(root: Path, paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        candidate = root / relative
        if not candidate.is_file():
            raise ValueError(f"source path is absent: {relative.as_posix()}")
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(candidate.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run(command: tuple[str, ...], *, cwd: Path = ROOT) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise ValueError(f"required executable is unavailable: {command[0]}") from error
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise ValueError(f"command failed ({' '.join(command)}):\n{output.strip()}")
    return output.strip()


def validate_native_tests(*, run=subprocess.run) -> list[dict[str, object]]:
    evidence = []
    for command in NATIVE_TEST_COMMANDS:
        try:
            completed = run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            raise ValueError(
                f"native invoice test command could not start ({' '.join(command)}): {error}"
            ) from error
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        command_text = " ".join(command)
        if completed.returncode != 0:
            raise ValueError(
                f"native invoice test command failed ({command_text}):\n{output}"
            )
        if re.search(r"test result:\s+FAILED\.|\b[1-9]\d* failed\b", output):
            raise ValueError(
                f"native invoice test command reported failed tests ({command_text})"
            )
        summaries = re.findall(
            r"test result:\s+ok\.\s+(\d+) passed;\s+(\d+) failed;",
            output,
        )
        if not summaries:
            raise ValueError(
                f"native invoice test command lacks a passing test summary ({command_text})"
            )
        passing_tests = sum(int(passed) for passed, _ in summaries)
        if passing_tests == 0:
            raise ValueError(
                f"native invoice test command reports zero passing tests ({command_text})"
            )
        evidence.append(
            {
                "command": command_text,
                "status": "pass",
                "exit_code": completed.returncode,
                "passing_tests": passing_tests,
                "output": output,
            }
        )
    return evidence


def tool_version(command: tuple[str, ...]) -> str:
    output = run(command)
    return output.splitlines()[0] if output else "unknown"


def pdf_text_executable() -> Path:
    executable = shutil.which("pdftotext")
    if executable:
        return Path(executable)
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        bundled = (
            Path(pdfinfo).resolve().parents[2]
            / "native/poppler/poppler/bin/pdftotext"
        )
        if bundled.is_file():
            return bundled
    raise ValueError("required executable is unavailable: pdftotext")


def extract_pdf_text(pdf_path: Path, executable: Path) -> tuple[str, tuple[str, ...]]:
    command = (str(executable), "-layout", str(pdf_path), "-")
    extracted = re.sub(r"\s+", " ", run(command)).strip()
    return extracted, command


def extract_pdf_layout(pdf_path: Path, executable: Path) -> tuple[str, tuple[str, ...]]:
    command = (str(executable), "-bbox-layout", str(pdf_path), "-")
    return run(command), command


def validate_pdf_layout(
    layout_xml: str,
    *,
    expected_rows: tuple[str, ...],
    expected_subtotal_count: int,
    required_same_page_groups: tuple[tuple[str, ...], ...] = (),
) -> dict[str, int]:
    try:
        document = ET.fromstring(layout_xml)
    except ET.ParseError as error:
        raise ValueError("PDF text layout XML is invalid") from error
    pages = document.findall(".//{*}page")
    if not pages:
        raise ValueError("PDF text layout has no pages")
    page_texts: list[str] = []
    for page_number, page in enumerate(pages, start=1):
        width = float(page.attrib["width"])
        height = float(page.attrib["height"])
        words = page.findall(".//{*}word")
        for word in words:
            x_min = float(word.attrib["xMin"])
            y_min = float(word.attrib["yMin"])
            x_max = float(word.attrib["xMax"])
            y_max = float(word.attrib["yMax"])
            if x_min < 0 or y_min < 0 or x_max > width or y_max > height:
                raise ValueError(
                    f"PDF text enters page bounds on page {page_number}: "
                    f"{word.text!r} ({x_min}, {y_min}, {x_max}, {y_max})"
                )
        page_texts.append(
            re.sub(r"\s+", " ", " ".join(word.text or "" for word in words)).strip()
        )
    first_page = page_texts[0]
    if "Invoice" not in first_page or "Northstar Studio" not in first_page:
        raise ValueError("invoice header is absent or clipped on the first PDF page")
    for group in required_same_page_groups:
        anchor = group[0]
        anchor_pages = [index for index, text in enumerate(page_texts) if anchor in text]
        if len(anchor_pages) != 1 or any(
            item not in page_texts[anchor_pages[0]] for item in group[1:]
        ):
            raise ValueError(
                f"{anchor} heading is orphaned from required content: {group[1:]}"
            )
    subtotal_count = sum(text.count("Work performed subtotal") for text in page_texts)
    if subtotal_count != expected_subtotal_count:
        raise ValueError(
            "work performed subtotal count is invalid: "
            f"expected {expected_subtotal_count}, found {subtotal_count}"
        )
    for page_number, text in enumerate(page_texts, start=1):
        markers = sum(
            text.count(f"Generated work category {row}")
            for row in expected_rows
        )
        descriptions = text.count("descriptive label")
        if markers != descriptions:
            raise ValueError(
                f"invoice rows are split or clipped on page {page_number}: "
                f"{markers} row starts, {descriptions} row endings"
            )
    for row in expected_rows:
        marker = f"Generated work category {row}"
        if sum(text.count(marker) for text in page_texts) != 1:
            raise ValueError(f"invoice row {row} is split or clipped")
    return {
        "pages": len(pages),
        "rows": len(expected_rows),
        "subtotal_count": subtotal_count,
    }


def parse_pdfinfo(output: str) -> dict[str, object]:
    page_match = re.search(r"^Pages:\s+(\d+)\s*$", output, re.MULTILINE)
    size_match = re.search(
        r"^Page size:\s+([0-9.]+)\s+x\s+([0-9.]+)\s+pts(?:\s+\(A4\))?\s*$",
        output,
        re.MULTILINE,
    )
    encrypted_match = re.search(r"^Encrypted:\s+(\S+)\s*$", output, re.MULTILINE)
    if not page_match or not size_match or not encrypted_match:
        raise ValueError("pdfinfo output is incomplete")
    width, height = (float(size_match.group(1)), float(size_match.group(2)))
    if abs(width - 595.276) > 0.5 or abs(height - 841.89) > 0.5:
        raise ValueError(f"PDF page size is not A4: {width} x {height} pts")
    if encrypted_match.group(1).lower() != "no":
        raise ValueError("representative PDF must not be encrypted")
    pages = int(page_match.group(1))
    if pages < 1:
        raise ValueError("representative PDF has no pages")
    return {"pages": pages, "width_points": width, "height_points": height}


def validate_selectable_pdf(
    data: bytes,
    extracted_text: str,
    required_text: tuple[str, ...],
    forbidden_text: tuple[str, ...],
) -> None:
    selectable_tokens = (b"%PDF-", b"/ToUnicode", b"/StructTreeRoot")
    if not all(token in data for token in selectable_tokens) or not any(
        token in data for token in (b"/FontFile2", b"/FontFile3")
    ):
        raise ValueError("browser PDF lacks selectable tagged font structure")
    missing = [text for text in required_text if text not in extracted_text]
    if missing:
        raise ValueError(f"browser PDF extracted PDF text lacks expected text: {missing}")
    present = [text for text in forbidden_text if text in extracted_text]
    if present:
        raise ValueError(f"browser PDF contains forbidden extracted PDF text: {present}")


def validate_dom_evidence(
    name: str,
    evidence: dict[str, object],
    *,
    required_text: tuple[str, ...],
    forbidden_text: tuple[str, ...],
    expected_figures: int,
) -> None:
    screen = evidence.get("screen")
    printed = evidence.get("print")
    if not isinstance(screen, dict) or not isinstance(printed, dict):
        raise ValueError(f"{name} lacks screen/print DOM evidence")
    for label, state in (("screen", screen), ("print", printed)):
        if state.get("document_count") != 1:
            raise ValueError(f"{name} {label} does not contain one invoice document")
        if state.get("figures") != expected_figures:
            raise ValueError(f"{name} {label} has an unexpected optional chart count")
        bounds = state.get("printable_bounds")
        if (
            not isinstance(bounds, dict)
            or bounds.get("within_horizontal_bounds") is not True
            or bounds.get("clipped_elements") != []
        ):
            raise ValueError(f"{name} {label} content is outside printable bounds")
        text = state.get("text")
        if not isinstance(text, str):
            raise ValueError(f"{name} {label} text evidence is missing")
        missing = [required for required in required_text if required not in text]
        if missing:
            raise ValueError(f"{name} {label} lacks expected text: {missing}")
        present = [forbidden for forbidden in forbidden_text if forbidden in text]
        if present:
            raise ValueError(f"{name} {label} contains forbidden text: {present}")
    if screen.get("text") != printed.get("text"):
        raise ValueError(f"{name} print text differs from the preview DOM")
    if screen.get("chart_structure_sha256") != printed.get("chart_structure_sha256"):
        raise ValueError(f"{name} print SVG structure differs from preview")
    if screen.get("chart_styles") != printed.get("chart_styles"):
        raise ValueError(f"{name} print chart styles differ from preview")


def validate_browser_manifest(
    payload: dict[str, object],
    *,
    root: Path,
    run_token: str,
    source_sha256: str,
    specifications: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    if payload.get("schema") != 2 or payload.get("command") != BROWSER_COMMAND_TEXT:
        raise ValueError("browser renderer manifest schema or command is invalid")
    if payload.get("run_token") != run_token:
        raise ValueError("browser renderer run token is stale")
    if payload.get("source_sha256") != source_sha256:
        raise ValueError("browser renderer source provenance is stale")
    renderer = payload.get("renderer")
    if not isinstance(renderer, dict) or renderer.get("name") != "playwright-chromium":
        raise ValueError("browser renderer identity is missing")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("browser renderer artifacts are missing")
    by_name = {
        artifact.get("case"): artifact
        for artifact in artifacts
        if isinstance(artifact, dict) and isinstance(artifact.get("case"), str)
    }
    if set(by_name) != set(specifications) or len(by_name) != len(artifacts):
        raise ValueError("browser renderer cases are stale or incomplete")
    validated = []
    resolved_root = root.resolve()
    for name, specification in specifications.items():
        artifact = by_name[name]
        relative_pdf = artifact.get("pdf")
        if not isinstance(relative_pdf, str):
            raise ValueError(f"{name} PDF path is missing")
        pdf_path = (root / relative_pdf).resolve()
        if not pdf_path.is_relative_to(resolved_root) or not pdf_path.is_file():
            raise ValueError(f"{name} PDF artifact is absent or outside the repository")
        if artifact.get("sha256") != sha256(pdf_path):
            raise ValueError(f"{name} PDF artifact hash is stale")
        validate_dom_evidence(
            name,
            artifact,
            required_text=specification["required_text"],
            forbidden_text=specification["forbidden_text"],
            expected_figures=specification["figures"],
        )
        validated.append({"name": name, "path": pdf_path, "artifact": artifact})
    return validated


def _paeth(left: int, above: int, upper_left: int) -> int:
    prediction = left + above - upper_left
    distances = (
        abs(prediction - left),
        abs(prediction - above),
        abs(prediction - upper_left),
    )
    return (left, above, upper_left)[distances.index(min(distances))]


def decode_png(data: bytes) -> tuple[int, int, int, bytes]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("rendered page is not a PNG")
    offset = 8
    ihdr = None
    compressed = bytearray()
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("PNG chunk is truncated")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        checksum = struct.unpack(">I", data[offset + 8 + length : offset + 12 + length])[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != checksum:
            raise ValueError("PNG chunk checksum is invalid")
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
        offset += 12 + length
    if ihdr is None:
        raise ValueError("PNG has no IHDR")
    width, height, depth, color_type, compression, filtering, interlace = ihdr
    if depth != 8 or color_type not in (2, 6) or compression or filtering or interlace:
        raise ValueError("PNG format is unsupported for deterministic bounds validation")
    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    if len(raw) != height * (stride + 1):
        raise ValueError("PNG pixel data has an unexpected size")
    decoded = bytearray(height * stride)
    previous = bytearray(stride)
    source_offset = 0
    for row_index in range(height):
        filter_type = raw[source_offset]
        source_offset += 1
        source = raw[source_offset : source_offset + stride]
        source_offset += stride
        row = bytearray(stride)
        for index, value in enumerate(source):
            left = row[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                reconstructed = value
            elif filter_type == 1:
                reconstructed = value + left
            elif filter_type == 2:
                reconstructed = value + above
            elif filter_type == 3:
                reconstructed = value + ((left + above) // 2)
            elif filter_type == 4:
                reconstructed = value + _paeth(left, above, upper_left)
            else:
                raise ValueError(f"PNG uses unsupported filter {filter_type}")
            row[index] = reconstructed & 0xFF
        decoded[row_index * stride : (row_index + 1) * stride] = row
        previous = row
    return width, height, channels, bytes(decoded)


def validate_png_bounds(data: bytes) -> dict[str, int]:
    width, height, channels, pixels = decode_png(data)
    margin = max(2, round(min(width / 210.0, height / 297.0) * 4.0))
    for y in range(height):
        for x in range(width):
            if margin <= x < width - margin and margin <= y < height - margin:
                continue
            offset = (y * width + x) * channels
            if any(channel < 245 for channel in pixels[offset : offset + 3]):
                raise ValueError(f"rendered content enters the outer margin at {x}, {y}")
    return {"width": width, "height": height, "outer_margin_pixels": margin}


def validate_png_dimensions(metadata: dict[str, int]) -> None:
    width, height = metadata["width"], metadata["height"]
    if not (990 <= width <= 995 and 1401 <= height <= 1406):
        raise ValueError(f"rendered page is not 120 dpi A4: {width} x {height}")


def validate() -> dict[str, object]:
    native_tests = validate_native_tests()
    provenance = source_digest(ROOT, SOURCE_PATHS)
    run_token = secrets.token_hex(16)
    payload = json.loads(run(browser_command(run_token)))
    validated = validate_browser_manifest(
        payload,
        root=ROOT,
        run_token=run_token,
        source_sha256=provenance,
        specifications=CASE_SPECIFICATIONS,
    )
    versions = {
        "pdfinfo": tool_version(("pdfinfo", "-v")),
        "pdftoppm": tool_version(("pdftoppm", "-v")),
    }
    text_executable = pdf_text_executable()
    versions["pdftotext"] = tool_version((str(text_executable), "-v"))
    evidence: dict[str, object] = {
        "schema": 2,
        "overall_status": "pass",
        "repository": str(ROOT),
        "command": BROWSER_COMMAND_TEXT,
        "run_token": run_token,
        "source_sha256": provenance,
        "renderer": payload["renderer"],
        "tools": versions,
        "native_tests": native_tests,
        "artifacts": {},
    }
    for validated_artifact in validated:
        name = validated_artifact["name"]
        pdf_path = validated_artifact["path"]
        artifact = validated_artifact["artifact"]
        specification = CASE_SPECIFICATIONS[name]
        pdf_data = pdf_path.read_bytes()
        extracted_text, text_command = extract_pdf_text(pdf_path, text_executable)
        layout_xml, layout_command = extract_pdf_layout(pdf_path, text_executable)
        expected_rows = (
            tuple(f"{index:02d}" for index in range(1, 49))
            if name == "long-table"
            else ()
        )
        layout_evidence = validate_pdf_layout(
            layout_xml,
            expected_rows=expected_rows,
            expected_subtotal_count=1,
            required_same_page_groups=(("Expenses", "DATE", "3 Feb 2026"),),
        )
        validate_selectable_pdf(
            pdf_data,
            extracted_text,
            specification["pdf_required_text"],
            specification["pdf_forbidden_text"],
        )
        pdfinfo = parse_pdfinfo(run(("pdfinfo", str(pdf_path))))
        pages_dir = ROOT / OUTPUT_ROOT / f"{name}-pages"
        if pages_dir.exists():
            shutil.rmtree(pages_dir)
        pages_dir.mkdir(parents=True)
        prefix = pages_dir / "page"
        render_command = (
            "pdftoppm",
            "-png",
            "-r",
            "120",
            str(pdf_path),
            str(prefix),
        )
        run(render_command)
        pngs = sorted(pages_dir.glob("page-*.png"))
        if len(pngs) != pdfinfo["pages"]:
            raise ValueError(f"{name} rendered page count is stale or incomplete")
        page_evidence = []
        for png in pngs:
            metadata = validate_png_bounds(png.read_bytes())
            validate_png_dimensions(metadata)
            page_evidence.append(
                {
                    "path": png.relative_to(ROOT).as_posix(),
                    "sha256": sha256(png),
                    **metadata,
                }
            )
        evidence["artifacts"][name] = {
            "pdf": pdf_path.relative_to(ROOT).as_posix(),
            "pdf_sha256": sha256(pdf_path),
            "pdfinfo": pdfinfo,
            "screen": artifact["screen"],
            "print": artifact["print"],
            "extracted_text": extracted_text,
            "text_command": " ".join(text_command),
            "layout": layout_evidence,
            "layout_command": " ".join(layout_command),
            "render_command": " ".join(render_command),
            "pngs": page_evidence,
        }
    manifest_path = ROOT / MANIFEST
    manifest_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return evidence


def main() -> int:
    try:
        evidence = validate()
    except (json.JSONDecodeError, OSError, TypeError, ValueError, zlib.error) as error:
        print(f"invoice-pdf validation failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
