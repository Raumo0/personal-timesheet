"""Bounded conformance checks for the GitHub architecture-handoff adapter."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Iterable, Sequence

from .protocol_metadata import ALL_PROTOCOL_LABELS

MAX_PROTOCOL_FILE_BYTES = 1_048_576
MAX_PACKAGE_ENTRIES = 512
MAX_PACKAGE_VISITED_ENTRIES = 4_096
MAX_PACKAGE_TOTAL_BYTES = 16_777_216
PACKAGE_MANIFEST_FORMAT = (
    "architecture-handoff-package-manifest-v1"
)
SCOPE = "bounded-github-contract"
LIMITATIONS = (
    "Checks declared source contracts; it does not prove runtime agent behavior.",
    "Checks the GitHub adapter mapping; it does not certify another provider adapter.",
    "Does not replace package tests, target tests, OpenSpec validation, or review.",
)


class PackageManifestError(ValueError):
    """A package tree cannot be represented safely within declared bounds."""

    def __init__(
        self,
        message: str,
        *,
        relative_path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.relative_path = relative_path


def _canonical_manifest_bytes(manifest: dict[str, object]) -> bytes:
    return json.dumps(
        manifest,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def package_tree_manifest(
    package_root: Path,
    *,
    max_entries: int = MAX_PACKAGE_ENTRIES,
    max_visited_entries: int = MAX_PACKAGE_VISITED_ENTRIES,
    max_total_bytes: int = MAX_PACKAGE_TOTAL_BYTES,
    max_file_bytes: int = MAX_PROTOCOL_FILE_BYTES,
) -> dict[str, object]:
    package_root = Path(package_root)
    for value, name in (
        (max_entries, "max_entries"),
        (max_visited_entries, "max_visited_entries"),
        (max_total_bytes, "max_total_bytes"),
        (max_file_bytes, "max_file_bytes"),
    ):
        if type(value) is not int or value < 1:
            raise PackageManifestError(f"{name} must be positive")
    if not package_root.is_dir() or package_root.is_symlink():
        raise PackageManifestError("package root is missing or unsafe")

    paths: list[Path] = []
    directories = [package_root]
    visited_entries = 0
    try:
        while directories:
            directory = directories.pop()
            with os.scandir(directory) as candidates:
                for candidate in candidates:
                    visited_entries += 1
                    if visited_entries > max_visited_entries:
                        raise PackageManifestError(
                            "package traversal entry limit exceeded "
                            f"({max_visited_entries})"
                        )
                    path = Path(candidate.path)
                    relative = path.relative_to(package_root)
                    if candidate.is_symlink():
                        raise PackageManifestError(
                            "package entry must not be a symlink",
                            relative_path=relative.as_posix(),
                        )
                    if candidate.is_dir(follow_symlinks=False):
                        if candidate.name == "__pycache__":
                            continue
                        directories.append(path)
                        continue
                    if candidate.is_file(follow_symlinks=False):
                        if path.suffix == ".pyc":
                            continue
                        paths.append(path)
                        if len(paths) > max_entries:
                            raise PackageManifestError(
                                f"package entry limit exceeded ({max_entries})"
                            )
                        continue
                    raise PackageManifestError(
                        "package entry must be a regular file or directory",
                        relative_path=relative.as_posix(),
                    )
    except PackageManifestError:
        raise
    except OSError as error:
        raise PackageManifestError(
            "package tree could not be enumerated safely"
        ) from error

    entries = []
    total_bytes = 0
    for path in sorted(
        paths,
        key=lambda candidate: (
            candidate.relative_to(package_root).as_posix()
        ),
    ):
        relative = path.relative_to(package_root).as_posix()
        try:
            metadata = path.stat(follow_symlinks=False)
        except OSError as error:
            raise PackageManifestError(
                "package file could not be inspected",
                relative_path=relative,
            ) from error
        if not stat.S_ISREG(metadata.st_mode):
            raise PackageManifestError(
                "package entry must be a regular file",
                relative_path=relative,
            )
        if metadata.st_size > max_file_bytes:
            raise PackageManifestError(
                f"package file exceeds byte limit ({max_file_bytes})",
                relative_path=relative,
            )
        total_bytes += metadata.st_size
        if total_bytes > max_total_bytes:
            raise PackageManifestError(
                f"package total byte limit exceeded ({max_total_bytes})"
            )

        file_digest = hashlib.sha256()
        observed_bytes = 0
        try:
            with path.open("rb") as source:
                while True:
                    chunk = source.read(65_536)
                    if not chunk:
                        break
                    observed_bytes += len(chunk)
                    if (
                        observed_bytes > max_file_bytes
                        or total_bytes - metadata.st_size + observed_bytes
                        > max_total_bytes
                    ):
                        raise PackageManifestError(
                            "package byte limit exceeded while hashing",
                            relative_path=relative,
                        )
                    file_digest.update(chunk)
        except OSError as error:
            raise PackageManifestError(
                "package file could not be read",
                relative_path=relative,
            ) from error
        if observed_bytes != metadata.st_size:
            raise PackageManifestError(
                "package file changed while hashing",
                relative_path=relative,
            )
        entries.append(
            {
                "path": relative,
                "byte_length": observed_bytes,
                "sha256": file_digest.hexdigest(),
            }
        )

    return {
        "format": PACKAGE_MANIFEST_FORMAT,
        "files": entries,
    }


def package_tree_sha256(
    package_root: Path,
    *,
    max_entries: int = MAX_PACKAGE_ENTRIES,
    max_visited_entries: int = MAX_PACKAGE_VISITED_ENTRIES,
    max_total_bytes: int = MAX_PACKAGE_TOTAL_BYTES,
    max_file_bytes: int = MAX_PROTOCOL_FILE_BYTES,
) -> str:
    manifest = package_tree_manifest(
        package_root,
        max_entries=max_entries,
        max_visited_entries=max_visited_entries,
        max_total_bytes=max_total_bytes,
        max_file_bytes=max_file_bytes,
    )
    return hashlib.sha256(_canonical_manifest_bytes(manifest)).hexdigest()


def _safe_package_tree_sha256(
    audit: "_Audit",
    side: str,
    relative_root: str,
) -> str | None:
    audit.checks += 1
    repository_root = (
        audit.documentation_root
        if side == "documentation"
        else audit.target_root
    )
    package_root = repository_root / relative_root
    if (
        not package_root.is_dir()
        or package_root.is_symlink()
    ):
        audit.fail(
            f"{side}.package-root",
            relative_root,
            "Architecture handoff package directory is missing or unsafe.",
        )
        return None

    try:
        manifest = package_tree_manifest(package_root)
    except PackageManifestError as error:
        relative = (
            f"{relative_root}/{error.relative_path}"
            if error.relative_path is not None
            else relative_root
        )
        audit.fail(
            f"{side}.package-manifest",
            relative,
            str(error),
        )
        return None
    manifest_bytes = _canonical_manifest_bytes(manifest)
    audit.hasher.update(f"{side}:{relative_root}\0".encode())
    audit.hasher.update(manifest_bytes)
    return hashlib.sha256(manifest_bytes).hexdigest()


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    message: str


@dataclass(frozen=True)
class GitState:
    revision: str
    dirty: bool | None


@dataclass(frozen=True)
class AuditResult:
    documentation_root: Path
    target_root: Path
    working_note: Path | None
    documentation_git: GitState
    target_git: GitState
    content_sha256: str
    working_note_sha256: str | None
    checks: int
    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": SCOPE,
            "status": "pass" if self.ok else "fail",
            "limitations": list(LIMITATIONS),
            "roots": {
                "documentation": str(self.documentation_root),
                "target": str(self.target_root),
            },
            "working_note": (
                {
                    "path": str(self.working_note),
                    "sha256": self.working_note_sha256,
                }
                if self.working_note is not None
                else None
            ),
            "git": {
                "documentation": asdict(self.documentation_git),
                "target": asdict(self.target_git),
            },
            "content_sha256": self.content_sha256,
            "checks": self.checks,
            "findings": [asdict(finding) for finding in self.findings],
        }


class _Audit:
    def __init__(self, documentation_root: Path, target_root: Path):
        self.documentation_root = documentation_root
        self.target_root = target_root
        self.checks = 0
        self.findings: list[Finding] = []
        self.hasher = hashlib.sha256()

    def fail(self, rule: str, path: str, message: str) -> None:
        self.findings.append(Finding(rule=rule, path=path, message=message))

    def required_file(self, side: str, relative_path: str) -> str | None:
        self.checks += 1
        root = self.documentation_root if side == "documentation" else self.target_root
        path = root / relative_path
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            self.fail(
                f"{side}.unsafe-path",
                relative_path,
                "Protocol surface resolves outside the declared root.",
            )
            return None
        if path.is_symlink():
            self.fail(
                f"{side}.unsafe-path",
                relative_path,
                "Protocol surface must not be a symlink.",
            )
            return None
        if not path.is_file():
            self.fail(
                f"{side}.required-file",
                relative_path,
                "Required protocol surface is missing.",
            )
            return None
        try:
            if path.stat().st_size > MAX_PROTOCOL_FILE_BYTES:
                self.fail(
                    f"{side}.oversized-file",
                    relative_path,
                    f"Protocol surface exceeds {MAX_PROTOCOL_FILE_BYTES} bytes.",
                )
                return None
            payload = path.read_bytes()
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            self.fail(
                f"{side}.invalid-text",
                relative_path,
                "Protocol surface is not valid UTF-8 text.",
            )
            return None
        except OSError:
            self.fail(
                f"{side}.unreadable-file",
                relative_path,
                "Protocol surface could not be read.",
            )
            return None
        self.hasher.update(f"{side}:{relative_path}\0".encode())
        self.hasher.update(payload)
        return text

    def require_all(
        self,
        rule: str,
        path: str,
        text: str | None,
        required_fragments: Iterable[str],
    ) -> None:
        self.checks += 1
        if text is None:
            return
        normalized = _normalize(text)
        missing = [
            fragment
            for fragment in required_fragments
            if _normalize(fragment) not in normalized
        ]
        if missing:
            self.findings.append(
                Finding(
                    rule=rule,
                    path=path,
                    message="Missing required contract text: "
                    + ", ".join(repr(fragment) for fragment in missing),
                )
            )

    def forbid_any(
        self,
        rule: str,
        path: str,
        text: str | None,
        forbidden_fragments: Iterable[str],
    ) -> None:
        self.checks += 1
        if text is None:
            return
        normalized = _normalize(text)
        present = [
            fragment
            for fragment in forbidden_fragments
            if _normalize(fragment) in normalized
        ]
        if present:
            self.findings.append(
                Finding(
                    rule=rule,
                    path=path,
                    message="Forbidden contract text is present: "
                    + ", ".join(repr(fragment) for fragment in present),
                )
            )


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _read_json_contract(
    audit: _Audit,
    side: str,
    relative_path: str,
) -> object | None:
    text = audit.required_file(side, relative_path)
    if text is None:
        return None
    audit.checks += 1
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        audit.fail(
            f"{side}.invalid-json",
            relative_path,
            "Required configuration is not valid JSON.",
        )
        return None


def _difference_paths(
    left: object,
    right: object,
    prefix: str = "",
) -> tuple[str, ...]:
    if type(left) is not type(right):
        return (prefix or "<root>",)
    if isinstance(left, dict):
        paths: list[str] = []
        for key in sorted(set(left) | set(right)):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in left or key not in right:
                paths.append(child)
            else:
                paths.extend(
                    _difference_paths(left[key], right[key], child)
                )
        return tuple(paths)
    if isinstance(left, list):
        paths = []
        if len(left) != len(right):
            paths.append(f"{prefix}.length")
        for index, (left_item, right_item) in enumerate(
            zip(left, right)
        ):
            paths.extend(
                _difference_paths(
                    left_item,
                    right_item,
                    f"{prefix}[{index}]",
                )
            )
        return tuple(paths)
    return () if left == right else (prefix or "<root>",)


def _walk_json(
    value: object,
    prefix: str = "",
) -> Iterable[tuple[str, object]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else str(key)
            yield child_path, child
            yield from _walk_json(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{prefix}[{index}]"
            yield child_path, child
            yield from _walk_json(child, child_path)


def _audit_config_safety(
    audit: _Audit,
    side: str,
    relative_path: str,
    value: object | None,
) -> None:
    if value is None:
        return
    sensitive_names = {
        "credential",
        "credentials",
        "password",
        "private_key",
        "secret",
        "token",
    }
    for field_path, field_value in _walk_json(value):
        field_name = re.sub(r"[^a-z0-9]+", "_", field_path.rsplit(".", 1)[-1].lower())
        if any(
            field_name == name or field_name.endswith(f"_{name}")
            for name in sensitive_names
        ):
            audit.fail(
                f"{side}.config-sensitive-key",
                relative_path,
                f"Configuration contains a sensitive field at {field_path}.",
            )
        if (
            isinstance(field_value, str)
            and (
                Path(field_value).is_absolute()
                or PureWindowsPath(field_value).is_absolute()
                or field_value.startswith("~/")
            )
        ):
            audit.fail(
                f"{side}.config-local-path",
                relative_path,
                f"Configuration contains a local path at {field_path}.",
            )


def _audit_github_label_manifest(
    audit: _Audit,
    relative_path: str,
    source: str | None,
) -> None:
    audit.checks += 1
    if source is None:
        return
    try:
        tree = ast.parse(source, filename=relative_path)
    except SyntaxError:
        audit.fail(
            "documentation.github-label-manifest",
            relative_path,
            "GitHub provisioning source is not valid Python.",
        )
        return

    assignments = [
        node.value
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (
            node.targets
            if isinstance(node, ast.Assign)
            else (node.target,)
        )
        if (
            isinstance(target, ast.Name)
            and target.id == "GITHUB_PROTOCOL_LABEL_MANIFEST"
        )
    ]
    if len(assignments) != 1:
        audit.fail(
            "documentation.github-label-manifest",
            relative_path,
            "Expected one literal GITHUB_PROTOCOL_LABEL_MANIFEST assignment.",
        )
        return
    try:
        manifest = ast.literal_eval(assignments[0])
    except (TypeError, ValueError):
        manifest = None
    if (
        not isinstance(manifest, dict)
        or any(not isinstance(name, str) for name in manifest)
    ):
        audit.fail(
            "documentation.github-label-manifest",
            relative_path,
            "GitHub protocol label manifest must be a literal string-keyed mapping.",
        )
        return

    actual = set(manifest)
    expected = set(ALL_PROTOCOL_LABELS)
    if actual != expected:
        details = []
        if expected - actual:
            details.append(
                "missing " + ", ".join(sorted(expected - actual))
            )
        if actual - expected:
            details.append(
                "unexpected " + ", ".join(sorted(actual - expected))
            )
        audit.fail(
            "documentation.github-label-manifest",
            relative_path,
            "Manifest must exactly cover the protocol label vocabulary: "
            + "; ".join(details),
        )


def _documentation_intake_store(
    audit: _Audit,
    side: str,
    registry: object | None,
) -> dict[str, object] | None:
    audit.checks += 1
    if not isinstance(registry, dict):
        return None
    stores = registry.get("stores")
    if not isinstance(stores, list):
        audit.fail(
            f"{side}.documentation-intake-store",
            "architecture-handoff.registry.json",
            "Registry must contain a stores list.",
        )
        return None
    matches = [
        store
        for store in stores
        if isinstance(store, dict)
        and store.get("role") == "documentation-intake"
    ]
    if (
        len(matches) != 1
        or matches[0].get("role") != "documentation-intake"
        or matches[0].get("routing_status") != "active"
    ):
        audit.fail(
            f"{side}.documentation-intake-store",
            "architecture-handoff.registry.json",
            (
                "Registry must contain exactly one active store with the "
                "documentation-intake role."
            ),
        )
        return None
    return matches[0]


def _without_html_comments(value: str) -> str:
    return re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)


def _markdown_section(value: str, heading: str, *, level: int = 2) -> str:
    clean = _without_html_comments(value)
    marker = "#" * level
    match = re.search(
        rf"^{marker} {re.escape(heading)}\s*$\n(.*?)(?=^{marker} |\Z)",
        clean,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def _frontmatter_and_body(value: str) -> tuple[dict[str, str], str]:
    clean = _without_html_comments(value)
    lines = clean.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, clean
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return {}, clean
    fields: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        fields[key.strip()] = raw_value.strip().strip("\"'")
    return fields, "\n".join(lines[end + 1 :])


def _yaml_rule_items(value: str, rule_name: str) -> tuple[str, ...]:
    items: list[str] = []
    in_rules = False
    in_rule = False
    for line in value.splitlines():
        if re.match(r"^rules:\s*$", line):
            in_rules = True
            continue
        if not in_rules:
            continue
        rule_match = re.match(r"^  ([a-z][a-z0-9_-]*):\s*$", line)
        if rule_match:
            in_rule = rule_match.group(1) == rule_name
            continue
        if in_rule:
            item_match = re.match(r"^    -\s+(.*)$", line)
            if item_match:
                items.append(item_match.group(1).strip())
                continue
            continuation = re.match(r"^      (.+)$", line)
            if continuation and items:
                items[-1] += " " + continuation.group(1).strip()
                continue
            if line and not line.startswith("    "):
                in_rule = False
    return tuple(items)


def _git_state(root: Path) -> GitState:
    try:
        revision_result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return GitState(revision="unavailable", dirty=None)
    revision = revision_result.stdout.strip()
    if not revision:
        return GitState(revision="unavailable", dirty=None)
    try:
        status_result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return GitState(revision=revision, dirty=None)
    return GitState(revision=revision, dirty=bool(status_result.stdout.strip()))


def _git_revision_preserves_path(
    root: Path,
    revision: str,
    relative_path: str,
) -> bool:
    try:
        revision_result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "cat-file",
                "-e",
                f"{revision}^{{commit}}",
            ],
            check=False,
            capture_output=True,
            timeout=5,
        )
        if revision_result.returncode != 0:
            return False
        difference_result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "diff",
                "--quiet",
                revision,
                "HEAD",
                "--",
                relative_path,
            ],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return difference_result.returncode == 0


def _markdown_table(value: str, heading: str) -> list[dict[str, str]]:
    section = _markdown_section(value, heading, level=3)
    table_lines = [line for line in section.splitlines() if line.startswith("|")]
    if len(table_lines) < 2:
        return []
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells, strict=True)))
    return rows


def _audit_reconciliation(audit: _Audit, path: Path) -> tuple[str | None, str | None]:
    audit.checks += 1
    resolved = path.expanduser().resolve()
    if path.is_symlink():
        audit.fail(
            "reconciliation.unsafe-path",
            str(path),
            "Working Note must not be a symlink.",
        )
        return str(resolved), None
    try:
        if resolved.stat().st_size > MAX_PROTOCOL_FILE_BYTES:
            audit.fail(
                "reconciliation.oversized-file",
                str(path),
                f"Working Note exceeds {MAX_PROTOCOL_FILE_BYTES} bytes.",
            )
            return str(resolved), None
        payload = resolved.read_bytes()
    except OSError:
        audit.fail(
            "reconciliation.required-file",
            str(path),
            "Working Note could not be read.",
        )
        return str(resolved), None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        audit.fail(
            "reconciliation.invalid-text",
            str(path),
            "Working Note is not valid UTF-8 text.",
        )
        return str(resolved), None

    digest = hashlib.sha256(payload).hexdigest()
    ledger = _markdown_table(text, "Agreement Ledger")
    actions = _markdown_table(text, "Action Register")
    coverage = _markdown_table(text, "Coverage Matrix")
    audit.checks += 3
    if not ledger:
        audit.fail("reconciliation.ledger", str(path), "Agreement Ledger is missing.")
    if not actions:
        audit.fail("reconciliation.actions", str(path), "Action Register is missing.")
    if not coverage:
        audit.fail("reconciliation.coverage", str(path), "Coverage Matrix is missing.")
    if not ledger or not actions or not coverage:
        return str(resolved), digest

    action_states = {row.get("Action"): row.get("State") for row in actions}
    audit.checks += 1
    if action_states.get("ACT-0008") != "done":
        audit.fail(
            "reconciliation.p1-action",
            str(path),
            "ACT-0008 must be done for the completion run.",
        )
    for deferred in ("ACT-0007", "ACT-0011"):
        if action_states.get(deferred) != "planned":
            audit.fail(
                "reconciliation.deferred-action",
                str(path),
                f"{deferred} must remain planned.",
            )

    act8_rows = [row for row in coverage if row.get("Action") == "ACT-0008"]
    audit.checks += 1
    expected_act8 = {
        row.get("Agreement")
        for row in ledger
        if "ACT-0008" in row.get("Action refs", "")
    }
    actual_act8 = {row.get("Agreement") for row in act8_rows}
    if (
        not act8_rows
        or expected_act8 != actual_act8
        or len(act8_rows) != len(actual_act8)
        or any(row.get("State") != "verified" for row in act8_rows)
    ):
        audit.fail(
            "reconciliation.p1-coverage",
            str(path),
            "ACT-0008 coverage must exactly match its Ledger references and be verified.",
        )

    audit.checks += 1
    for row in ledger:
        state = row.get("State")
        action_refs = row.get("Action refs", "")
        agreement = row.get("Agreement", "unknown")
        deferred = "ACT-0007" in action_refs or "ACT-0011" in action_refs
        if state == "pending":
            audit.fail(
                "reconciliation.pending-agreement",
                str(path),
                f"{agreement} remains pending.",
            )
        if state == "mapped" and not deferred:
            audit.fail(
                "reconciliation.hidden-incomplete",
                str(path),
                f"{agreement} is mapped without a deferred P2 action.",
            )
        if "ACT-0008" in action_refs and not deferred and state != "verified":
            audit.fail(
                "reconciliation.p1-ledger",
                str(path),
                f"{agreement} should be verified after ACT-0008.",
            )
    return str(resolved), digest


def audit_roots(
    documentation_root: Path | str,
    target_root: Path | str,
    *,
    require_clean_revisions: bool = True,
    working_note: Path | str | None = None,
) -> AuditResult:
    """Audit declared documentation and GitHub target protocol surfaces."""

    documentation = Path(documentation_root).expanduser().resolve()
    target = Path(target_root).expanduser().resolve()
    audit = _Audit(documentation, target)
    documentation_git = _git_state(documentation)
    target_git = _git_state(target)

    registry_path = "architecture-handoff.registry.json"
    documentation_registry = _read_json_contract(
        audit,
        "documentation",
        registry_path,
    )
    target_registry = _read_json_contract(
        audit,
        "target",
        registry_path,
    )
    _audit_config_safety(
        audit,
        "documentation",
        registry_path,
        documentation_registry,
    )
    _audit_config_safety(
        audit,
        "target",
        registry_path,
        target_registry,
    )
    documentation_store = _documentation_intake_store(
        audit,
        "documentation",
        documentation_registry,
    )
    target_store = _documentation_intake_store(
        audit,
        "target",
        target_registry,
    )
    if documentation_store is not None and target_store is not None:
        store_differences = _difference_paths(
            documentation_store,
            target_store,
        )
        audit.checks += 1
        if store_differences:
            audit.fail(
                "target.documentation-intake-store",
                registry_path,
                "Documentation intake store differs at: "
                + ", ".join(store_differences),
            )

    runtime_path = "architecture-handoff.runtime.json"
    documentation_runtime = _read_json_contract(
        audit,
        "documentation",
        runtime_path,
    )
    target_runtime = _read_json_contract(
        audit,
        "target",
        runtime_path,
    )
    _audit_config_safety(
        audit,
        "documentation",
        runtime_path,
        documentation_runtime,
    )
    _audit_config_safety(
        audit,
        "target",
        runtime_path,
        target_runtime,
    )
    if documentation_runtime is not None and target_runtime is not None:
        runtime_differences = _difference_paths(
            documentation_runtime,
            target_runtime,
        )
        audit.checks += 1
        if runtime_differences:
            audit.fail(
                "target.runtime-policy",
                runtime_path,
                "Runtime policy differs at: "
                + ", ".join(runtime_differences),
            )

    vendor_path = "architecture-handoff.vendor.json"
    vendor = _read_json_contract(audit, "target", vendor_path)
    _audit_config_safety(audit, "target", vendor_path, vendor)
    documentation_package_digest = _safe_package_tree_sha256(
        audit,
        "documentation",
        "tools/architecture_handoff",
    )
    target_package_digest = _safe_package_tree_sha256(
        audit,
        "target",
        "tools/architecture_handoff",
    )
    audit.checks += 1
    if (
        documentation_package_digest is not None
        and target_package_digest is not None
        and documentation_package_digest != target_package_digest
    ):
        audit.fail(
            "target.package-digest",
            "tools/architecture_handoff",
            "Target package digest differs from the documentation package.",
        )
    if isinstance(vendor, dict):
        source_repository = vendor.get("source_repository")
        source_revision = vendor.get("source_revision")
        recorded_digest = vendor.get("package_sha256")
        template_values = (
            source_repository,
            source_revision,
            recorded_digest,
        ) == (
            "EXAMPLE_SOURCE_REPOSITORY",
            "EXAMPLE_SOURCE_REVISION",
            "EXAMPLE_PACKAGE_SHA256",
        )
        if template_values:
            endpoint_groups = (
                target_registry.get("targets"),
                target_registry.get("stores"),
            ) if isinstance(target_registry, dict) else (None, None)
            endpoints = []
            for group in endpoint_groups:
                if isinstance(group, list):
                    endpoints.extend(group)
            if not endpoints or any(
                not isinstance(endpoint, dict)
                or endpoint.get("routing_status") != "suspended"
                for endpoint in endpoints
            ):
                audit.fail(
                    "target.package-provenance",
                    vendor_path,
                    "Template vendor values are allowed only when every "
                    "target and store is suspended.",
                )
        elif (
            not isinstance(source_repository, str)
            or not source_repository.startswith("https://")
            or not isinstance(source_revision, str)
            or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source_revision)
            is None
            or not isinstance(recorded_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", recorded_digest) is None
        ):
            audit.fail(
                "target.package-provenance",
                vendor_path,
                (
                    "Vendor provenance requires an HTTPS source repository, "
                    "full lowercase Git revision, and lowercase SHA-256."
                ),
            )
        else:
            if (
                target_package_digest is not None
                and recorded_digest != target_package_digest
            ):
                audit.fail(
                    "target.package-digest",
                    vendor_path,
                    "Recorded package digest does not match the target package.",
                )
            if (
                documentation_git.revision != "unavailable"
                and not _git_revision_preserves_path(
                    documentation,
                    source_revision,
                    "tools/architecture_handoff",
                )
            ):
                audit.fail(
                    "target.package-source-revision",
                    vendor_path,
                    (
                        "Vendor source revision does not identify a commit "
                        "with the current documentation package tree."
                    ),
                )
    elif vendor is not None:
        audit.fail(
            "target.package-provenance",
            vendor_path,
            "Vendor provenance must be a JSON object.",
        )

    process_path = "processes/architecture-to-openspec-handoff.md"
    process = audit.required_file("documentation", process_path)
    audit.require_all(
        "documentation.route-contract",
        process_path,
        _markdown_section(process or "", "Work Routing"),
        (
            "architecture-slice-handoff",
            "implementation-conformance-referral",
            "spike-evidence",
            "target-native internal work",
        ),
    )
    audit.require_all(
        "documentation.source-contract",
        process_path,
        _markdown_section(process or "", "Accepted Driving Sources"),
        (
            "Product Requirement recorded as not applicable",
        ),
    )
    audit.require_all(
        "documentation.return-contract",
        process_path,
        _markdown_section(process or "", "Return Channel"),
        (
            "Return Item",
        ),
    )
    audit.require_all(
        "documentation.discovery-contract",
        process_path,
        _markdown_section(process or "", "On-Demand Task Discovery"),
        (
            "Load the full payload and linked sources only after the user selects one record",
        ),
    )
    audit.require_all(
        "documentation.endpoint-setup-contract",
        process_path,
        _markdown_section(process or "", "Provider Endpoint Setup"),
        (
            "explicit and on demand",
            "Implementation target",
            "work-route:*",
            "status:*",
            "Documentation intake store",
            "return-kind:*",
            "intake-state:*",
            "exact provisioning preview",
            "Endpoint Setup Human Gate",
            "does not retry",
            "style drift is advisory",
        ),
    )

    package_readme_path = "tools/architecture_handoff/README.md"
    package_readme = audit.required_file(
        "documentation",
        package_readme_path,
    )
    audit.require_all(
        "documentation.endpoint-setup-reference",
        package_readme_path,
        _markdown_section(
            package_readme or "",
            "Provision a Provider Endpoint",
        ),
        (
            "setup_cli prepare",
            "exact preview",
            "preparation_id",
            "Endpoint Setup Human Gate",
            "setup_cli execute",
            "--preparation-id",
            "provider readback",
            "ordered provider call ledger",
        ),
    )
    audit.required_file(
        "documentation",
        "tools/architecture_handoff/design/endpoint-provisioning.md",
    )
    github_design_path = (
        "tools/architecture_handoff/design/github-adapter.md"
    )
    github_design = audit.required_file(
        "documentation",
        github_design_path,
    )
    audit.require_all(
        "documentation.github-setup-mapping",
        github_design_path,
        _markdown_section(
            github_design or "",
            "GitHub Label Provisioning",
        ),
        (
            "GitHub-only rollout",
        ),
    )
    github_provisioning_path = (
        "tools/architecture_handoff/github_provisioning.py"
    )
    github_provisioning = audit.required_file(
        "documentation",
        github_provisioning_path,
    )
    _audit_github_label_manifest(
        audit,
        github_provisioning_path,
        github_provisioning,
    )

    documentation_agents_path = "AGENTS.md"
    documentation_agents = audit.required_file(
        "documentation", documentation_agents_path
    )
    audit.require_all(
        "documentation.on-demand-contract",
        documentation_agents_path,
        _markdown_section(
            documentation_agents or "", "Architecture-to-OpenSpec Handoff Operations"
        ),
        (
            "semantic on-demand trigger",
            "Do not poll at session start",
            "current session language",
            "Selection starts inspection, not implementation",
        ),
    )
    audit.require_all(
        "documentation.endpoint-setup-guidance",
        documentation_agents_path,
        _markdown_section(
            documentation_agents or "",
            "Architecture-to-OpenSpec Handoff Operations",
        ),
        (
            "local setup",
            "setup_cli prepare",
            "exact preview",
            "preparation_id",
            "Endpoint Setup Human Gate",
            "setup_cli execute",
            "--preparation-id",
            "provider readback",
            "ordered provider call ledger",
        ),
    )

    target_agents_path = "AGENTS.md"
    target_agents = audit.required_file("target", target_agents_path)
    audit.require_all(
        "target.on-demand-no-polling",
        target_agents_path,
        _markdown_section(target_agents or "", "On-Demand Work Discovery"),
        (
            "query the entire configured target task store",
            "Do not poll at session start",
        ),
    )
    audit.require_all(
        "target.discovery-and-selection",
        target_agents_path,
        _markdown_section(target_agents or "", "On-Demand Work Discovery"),
        (
            "Architecture Slice Handoff",
            "Implementation Conformance Referral",
            "Spike / Evidence",
            "Target-native internal tasks",
            "current session language",
            "Load the full payload and linked sources only after the user selects one record",
        ),
    )
    audit.require_all(
        "target.inspection-before-implementation",
        target_agents_path,
        _markdown_section(target_agents or "", "Inspect and Process One Item"),
        (
            "Selection starts inspection, not implementation",
            "Starting work requires separate human authorization",
        ),
    )
    audit.require_all(
        "target.authority-and-return",
        target_agents_path,
        (
            _markdown_section(target_agents or "", "Protocol Authority")
            + _markdown_section(target_agents or "", "Evidence and Returns")
        ),
        (
            "Product Requirement as not applicable with a reason",
            "Return Item",
        ),
    )
    audit.require_all(
        "target.return-runner-guidance",
        target_agents_path,
        _markdown_section(
            target_agents or "",
            "Return Item Delivery",
        ),
        (
            "return_cli prepare",
            "exact preview",
            "fingerprint",
            "external-write Human Gate",
            "return_cli execute",
            "provider readback",
        ),
    )
    audit.require_all(
        "target.adoption-contract",
        target_agents_path,
        _markdown_section(target_agents or "", "Target Adoption"),
        (
            "not a routine `work-route`",
            "status:draft",
            "status:ready",
            "all three `work-route:*` labels",
        ),
    )
    audit.require_all(
        "target.endpoint-setup-guidance",
        target_agents_path,
        _markdown_section(target_agents or "", "Target Adoption"),
        (
            "local setup",
            "setup_cli prepare",
            "exact preview",
            "preparation_id",
            "Endpoint Setup Human Gate",
            "setup_cli execute",
            "--preparation-id",
            "provider readback",
            "ordered provider call ledger",
        ),
    )

    target_readme_path = "README.md"
    target_readme = audit.required_file("target", target_readme_path)
    audit.require_all(
        "target.human-entry-point",
        target_readme_path,
        _without_html_comments(target_readme or ""),
        (
            "Target Adoption",
            "Architecture Slice Brief",
            "Implementation Conformance Referral",
            "Spike / Evidence",
            "target-native internal work",
            "On-Demand Discovery",
            "OpenSpec",
        ),
    )

    brief_path = ".github/ISSUE_TEMPLATE/architecture-slice-brief.md"
    brief = audit.required_file("target", brief_path)
    brief_frontmatter, brief_body = _frontmatter_and_body(brief or "")
    audit.checks += 1
    brief_labels = {
        label.strip() for label in brief_frontmatter.get("labels", "").split(",") if label.strip()
    }
    expected_brief_labels = {
        "work-route:architecture-slice-handoff",
        "status:draft",
    }
    if brief_labels != expected_brief_labels:
        audit.fail(
            "target.brief-labels",
            brief_path,
            f"Expected exact labels {sorted(expected_brief_labels)}.",
        )
    audit.require_all(
        "target.brief-contract",
        brief_path,
        brief_body,
        (
            "Work route: `work-route: architecture-slice-handoff`",
            "Product Requirement applicability: accepted | not-applicable",
            "Profile: skeleton | behavior",
            "Correlation ID:",
            "Pinned documentation revision:",
        ),
    )

    referral_path = ".github/ISSUE_TEMPLATE/implementation-conformance-referral.md"
    referral = audit.required_file("target", referral_path)
    referral_frontmatter, referral_body = _frontmatter_and_body(referral or "")
    audit.checks += 1
    referral_labels = {
        label.strip()
        for label in referral_frontmatter.get("labels", "").split(",")
        if label.strip()
    }
    if referral_labels != {"work-route:implementation-conformance-referral"}:
        audit.fail(
            "target.referral-labels",
            referral_path,
            "Expected exactly the implementation-conformance-referral route label.",
        )
    audit.require_all(
        "target.referral-contract",
        referral_path,
        referral_body,
        (
            "Work route: `work-route: implementation-conformance-referral`",
            "Observed contradiction:",
            "Typed direct source relation:",
            "Pinned source revision:",
            "Correlation ID:",
            "Return Item:",
        ),
    )
    audit.forbid_any(
        "target.referral-no-profile",
        referral_path,
        referral_body,
        ("Profile:",),
    )

    spike_path = ".github/ISSUE_TEMPLATE/spike-evidence.md"
    spike = audit.required_file("target", spike_path)
    spike_frontmatter, spike_body = _frontmatter_and_body(spike or "")
    audit.checks += 1
    spike_labels = {
        label.strip() for label in spike_frontmatter.get("labels", "").split(",") if label.strip()
    }
    if spike_labels != {"work-route:spike-evidence"}:
        audit.fail(
            "target.spike-labels",
            spike_path,
            "Expected exactly the spike-evidence route label.",
        )
    audit.require_all(
        "target.spike-contract",
        spike_path,
        spike_body,
        (
            "Work route: `work-route: spike-evidence`",
            "Question:",
            "Timebox or stop condition:",
            "Required Evidence:",
            "Correlation ID:",
            "Typed source relation:",
            "Pinned source revision or not-applicable reason:",
            "Return Item:",
        ),
    )
    audit.forbid_any(
        "target.spike-no-profile",
        spike_path,
        spike_body,
        ("Profile:",),
    )

    openspec_path = "openspec/config.yaml"
    openspec = audit.required_file("target", openspec_path)
    audit.checks += 1
    if not re.search(r"^schema:\s*spec-driven\s*$", openspec or "", re.MULTILINE):
        audit.fail(
            "target.openspec-schema",
            openspec_path,
            "OpenSpec must preserve the spec-driven schema.",
        )
    proposal_rules = "\n".join(_yaml_rule_items(openspec or "", "proposal"))
    audit.require_all(
        "target.openspec-route-conditioning",
        openspec_path,
        proposal_rules,
        (
            "initiating native work item",
            "For an Architecture Slice Handoff, cite the Brief, immutable profile",
            "Product Requirement when product behavior or acceptance applies",
            "otherwise preserve the Brief's justified not-applicable result",
            "For an Implementation Conformance Referral",
            "observed contradiction",
            "expected verification",
            "For target-native work",
            "must not invent an upstream parent",
            "For Spike / Evidence",
            "separately authorized native work item",
            "pinned arc42 source references when architecture applies",
        ),
    )

    if require_clean_revisions:
        for side, state in (
            ("documentation", documentation_git),
            ("target", target_git),
        ):
            audit.checks += 1
            if state.revision == "unavailable":
                audit.fail(
                    f"{side}.git-revision",
                    ".",
                    "A reproducible completion run requires a Git revision.",
                )
            elif state.dirty is not False:
                audit.fail(
                    f"{side}.git-dirty",
                    ".",
                    "A reproducible completion run requires a clean worktree.",
                )

    working_note_path: Path | None = None
    working_note_sha256: str | None = None
    if working_note is not None:
        note_path, working_note_sha256 = _audit_reconciliation(
            audit, Path(working_note)
        )
        working_note_path = Path(note_path) if note_path is not None else None

    return AuditResult(
        documentation_root=documentation,
        target_root=target,
        working_note=working_note_path,
        documentation_git=documentation_git,
        target_git=target_git,
        content_sha256=audit.hasher.hexdigest(),
        working_note_sha256=working_note_sha256,
        checks=audit.checks,
        findings=tuple(audit.findings),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit architecture-handoff documentation and target surfaces."
    )
    parser.add_argument("--documentation-root", required=True, type=Path)
    parser.add_argument("--target-root", required=True, type=Path)
    parser.add_argument("--working-note", type=Path)
    parser.add_argument(
        "--allow-dirty-or-unversioned",
        action="store_true",
        help="Skip clean Git revision requirements outside a completion run.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    result = audit_roots(
        arguments.documentation_root,
        arguments.target_root,
        require_clean_revisions=not arguments.allow_dirty_or_unversioned,
        working_note=arguments.working_note,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
