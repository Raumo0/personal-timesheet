import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Callable, Mapping, TextIO

from .github import AdapterError, GitHubRestTransport
from .registry import RegistryError, load_registry_config
from .return_runtime import (
    ReturnPreparation,
    ReturnRequest,
    execute_return,
    prepare_return,
)
from .runtime_config import (
    GitHubRuntimeConfig,
    RuntimeConfigError,
    load_runtime_config,
)
from .write_coordinator import CandidateDisposition
from .write_models import (
    RelationKind,
    ReturnKind,
    TypedRelation,
    WriteOperation,
)


TransportFactory = Callable[
    [str | None, GitHubRuntimeConfig],
    object,
]


_REQUIRED_INPUT_FIELDS = frozenset(
    {
        "store_key",
        "operation",
        "title",
        "return_kind",
        "correlation_id",
        "source_relation",
        "origin",
        "evidence_links",
        "outcome",
        "method",
        "observations",
        "verification",
        "produced_artifacts",
        "limitations",
        "remaining_unknowns",
        "requested_return_route",
        "disposition",
    }
)
_OPTIONAL_INPUT_FIELDS = frozenset(
    {
        "disposition_reason",
        "provider_id",
        "expected_provider_state",
    }
)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip()
        for item in value
    ):
        raise ValueError(
            f"{field} must be a list of non-empty strings"
        )
    return tuple(item.strip() for item in value)


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field)


def load_return_request(path: Path) -> ReturnRequest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read Return input: {error}") from error
    if not isinstance(payload, dict) or any(
        not isinstance(key, str) for key in payload
    ):
        raise ValueError("Return input must be a JSON object")
    fields = frozenset(payload)
    unknown = sorted(
        fields - _REQUIRED_INPUT_FIELDS - _OPTIONAL_INPUT_FIELDS
    )
    if unknown:
        raise ValueError(
            "unknown Return input fields: " + ", ".join(unknown)
        )
    missing = sorted(_REQUIRED_INPUT_FIELDS - fields)
    if missing:
        raise ValueError(
            "missing Return input fields: " + ", ".join(missing)
        )
    relation = payload["source_relation"]
    if not isinstance(relation, dict):
        raise ValueError("source_relation must be an object")
    relation_fields = frozenset(relation)
    if not {"kind", "target"}.issubset(relation_fields):
        raise ValueError(
            "source_relation requires kind and target"
        )
    unknown_relation = sorted(
        relation_fields - {"kind", "target", "revision"}
    )
    if unknown_relation:
        raise ValueError(
            "unknown source_relation fields: "
            + ", ".join(unknown_relation)
        )
    try:
        operation = WriteOperation(payload["operation"])
        return_kind = ReturnKind(payload["return_kind"])
        disposition = CandidateDisposition(payload["disposition"])
        relation_kind = RelationKind(relation["kind"])
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Return input contains an unsupported enum value"
        ) from error
    request = ReturnRequest(
        store_key=_string(payload["store_key"], "store_key"),
        operation=operation,
        title=_string(payload["title"], "title"),
        return_kind=return_kind,
        correlation_id=_string(
            payload["correlation_id"],
            "correlation_id",
        ),
        source_relation=TypedRelation(
            kind=relation_kind,
            target=_string(
                relation["target"],
                "source_relation.target",
            ),
            revision=_optional_string(
                relation.get("revision"),
                "source_relation.revision",
            ),
        ),
        origin=_string(payload["origin"], "origin"),
        evidence_links=_string_tuple(
            payload["evidence_links"],
            "evidence_links",
        ),
        outcome=_string(payload["outcome"], "outcome"),
        method=_string(payload["method"], "method"),
        observations=_string(
            payload["observations"],
            "observations",
        ),
        verification=_string(
            payload["verification"],
            "verification",
        ),
        produced_artifacts=_string_tuple(
            payload["produced_artifacts"],
            "produced_artifacts",
        ),
        limitations=_string_tuple(
            payload["limitations"],
            "limitations",
        ),
        remaining_unknowns=_string_tuple(
            payload["remaining_unknowns"],
            "remaining_unknowns",
        ),
        requested_return_route=_string(
            payload["requested_return_route"],
            "requested_return_route",
        ),
        disposition=disposition,
        disposition_reason=_optional_string(
            payload.get("disposition_reason"),
            "disposition_reason",
        ),
        provider_id=_optional_string(
            payload.get("provider_id"),
            "provider_id",
        ),
        expected_provider_state=_optional_string(
            payload.get("expected_provider_state"),
            "expected_provider_state",
        ),
    )
    return request


def _positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "must be a positive integer"
        ) from error
    if number < 1:
        raise argparse.ArgumentTypeError(
            "must be a positive integer"
        )
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or execute one controlled Return Item write."
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )
    for name in ("prepare", "execute"):
        command = subparsers.add_parser(name)
        command.add_argument("--registry", required=True, type=Path)
        command.add_argument("--runtime", required=True, type=Path)
        command.add_argument("--input", required=True, type=Path)
        command.add_argument(
            "--limit",
            type=_positive_integer,
        )
        command.add_argument(
            "--max-pages",
            type=_positive_integer,
        )
        command.add_argument(
            "--max-items",
            type=_positive_integer,
        )
        if name == "execute":
            command.add_argument(
                "--expected-fingerprint",
                required=True,
            )
            command.add_argument(
                "--approval-reference",
                required=True,
            )
    return parser


def _default_transport(
    token: str | None,
    github: GitHubRuntimeConfig,
):
    return GitHubRestTransport(
        token=token,
        timeout_seconds=github.request_timeout_seconds,
    )


def _candidate_payload(candidate):
    return {
        "provider_qualified_id": candidate.provider_qualified_id,
        "title": candidate.title,
        "status": candidate.status,
        "updated": candidate.updated,
        "url": candidate.url,
    }


def _call_payload(call):
    return {
        "purpose": call.purpose.value,
        "cursor": call.cursor,
        "searched_scopes": list(call.searched_scopes),
        "provider_record_count": call.provider_record_count,
    }


def _preparation_payload(
    preparation: ReturnPreparation,
) -> dict[str, object]:
    calls = []
    for result in (
        preparation.fast_search,
        preparation.fallback,
    ):
        if result is not None:
            calls.extend(_call_payload(call) for call in result.calls)
    prepared = preparation.prepared
    return {
        "status": (
            "blocked" if prepared is None else "prepared"
        ),
        "store": {
            "key": preparation.store.key,
            "role": preparation.store.role.value,
            "provider": preparation.store.provider,
            "repository": preparation.store.repository,
        },
        "budget": {
            "page_size": preparation.budget.page_size,
            "max_pages": preparation.budget.max_pages,
            "max_items": preparation.budget.max_items,
        },
        "provider_calls": calls,
        "provider_write_calls": list(
            preparation.provider_write_calls
        ),
        "candidates": [
            _candidate_payload(candidate)
            for candidate in preparation.candidates
        ],
        "limitations": list(preparation.limitations),
        "blocked_reason": preparation.blocked_reason,
        "provider_payload": (
            json.loads(prepared.provider_payload_json)
            if prepared is not None
            else None
        ),
        "fingerprint": (
            prepared.fingerprint
            if prepared is not None
            else None
        ),
    }


def _receipt_payload(receipt) -> dict[str, object]:
    return {
        "operation": receipt.operation.value,
        "store": receipt.target_key,
        "provider": receipt.provider,
        "provider_id": receipt.provider_id,
        "provider_qualified_id": receipt.provider_qualified_id,
        "url": receipt.url,
        "intake_state": receipt.intake_state.value,
        "correlation_id": receipt.correlation_id,
        "verified_payload_fingerprint": (
            receipt.verified_payload_fingerprint
        ),
    }


def run(
    argv,
    *,
    transport_factory: TransportFactory | None = None,
    environ: Mapping[str, str] = os.environ,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    with contextlib.redirect_stderr(stderr):
        try:
            args = _parser().parse_args(argv)
        except SystemExit as error:
            return int(error.code)
    try:
        request = load_return_request(args.input)
        registry = load_registry_config(args.registry)
        runtime = load_runtime_config(args.runtime)
        token = environ.get("GITHUB_TOKEN")
        if args.command == "execute" and not token:
            raise ValueError(
                "GITHUB_TOKEN is required for Return execution"
            )
        factory = transport_factory or _default_transport
        transport = factory(token, runtime.github)
        common = {
            "request": request,
            "registry": registry,
            "runtime": runtime,
            "transport": transport,
            "page_size": args.limit,
            "max_pages": args.max_pages,
            "max_items": args.max_items,
        }
        if args.command == "prepare":
            payload = _preparation_payload(
                prepare_return(**common)
            )
        else:
            payload = _receipt_payload(
                execute_return(
                    **common,
                    expected_fingerprint=(
                        args.expected_fingerprint
                    ),
                    approval_reference=args.approval_reference,
                )
            )
    except (
        AdapterError,
        RegistryError,
        RuntimeConfigError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=stderr)
        return 2
    json.dump(payload, stdout, indent=2, sort_keys=True)
    stdout.write("\n")
    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
