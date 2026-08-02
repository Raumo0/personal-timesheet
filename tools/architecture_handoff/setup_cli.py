"""Prepare or execute approval-gated provider endpoint provisioning."""

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Callable, Mapping, TextIO

from .github import AdapterError, GitHubRestTransport
from .github_provisioning import GitHubProvisioningAdapter
from .provisioning import (
    ProvisioningCoordinator,
    ProvisioningError,
    ProvisioningExecutionError,
)
from .provisioning_attempts import (
    FileProvisioningAttemptStore,
    ProvisioningAttemptStore,
    default_attempt_ledger_path,
)
from .provisioning_models import (
    PreparedProvisioning,
    ProvisioningAuthorization,
    ProvisioningObservation,
    ProvisioningReceipt,
    ProvisioningResourceState,
)
from .registry import (
    ProviderEndpointConfig,
    RegistryError,
    StoreRole,
    load_registry_config,
    resolve_active_store,
    resolve_active_target,
)
from .runtime_config import (
    GitHubRuntimeConfig,
    RuntimeConfigError,
    load_runtime_config,
)


TransportFactory = Callable[[str | None, GitHubRuntimeConfig], object]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or execute controlled endpoint provisioning."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "execute"):
        command = commands.add_parser(name)
        command.add_argument("--registry", required=True, type=Path)
        command.add_argument("--runtime", required=True, type=Path)
        endpoint = command.add_mutually_exclusive_group(required=True)
        endpoint.add_argument("--target")
        endpoint.add_argument("--store")
        if name == "execute":
            command.add_argument("--expected-fingerprint", required=True)
            command.add_argument("--preparation-id", required=True)
            command.add_argument("--approval-reference", required=True)
    return parser


def _default_transport(
    token: str | None,
    github: GitHubRuntimeConfig,
) -> GitHubRestTransport:
    return GitHubRestTransport(
        token=token,
        timeout_seconds=github.request_timeout_seconds,
    )


def _resolve_endpoint(args, registry) -> ProviderEndpointConfig:
    if args.target is not None:
        endpoint = resolve_active_target(registry.targets, args.target)
    else:
        endpoint = resolve_active_store(
            registry.stores,
            args.store,
            StoreRole.DOCUMENTATION_INTAKE,
        )
    if endpoint.provider != "github":
        raise ValueError(
            "endpoint provisioning is currently supported only for GitHub"
        )
    return endpoint


def _endpoint_payload(endpoint: ProviderEndpointConfig) -> dict[str, object]:
    payload = {
        "key": endpoint.key,
        "provider": endpoint.provider,
        "repository": endpoint.repository,
    }
    if hasattr(endpoint, "role"):
        payload["role"] = endpoint.role.value
    return payload


def _requirement_payload(requirement) -> dict[str, str]:
    return {
        "family": requirement.family,
        "name": requirement.name,
    }


def _resource_payload(resource) -> dict[str, object]:
    return {
        "resource_type": resource.resource_type,
        "stable_id": resource.stable_id,
        "create_payload": json.loads(resource.create_payload_json),
        "presentation": json.loads(resource.presentation_json),
    }


def _observation_payload(
    observation: ProvisioningObservation,
) -> dict[str, object]:
    return {
        "requirement": _requirement_payload(observation.requirement),
        "resource": _resource_payload(observation.resource),
        "state": observation.state.value,
        "observed_identity": observation.observed_identity,
        "observed_presentation": (
            json.loads(observation.observed_presentation_json)
            if observation.observed_presentation_json is not None
            else None
        ),
        "limitation": observation.limitation,
    }


def _call_payload(call) -> dict[str, str]:
    return {
        "operation": call.operation,
        "resource_type": call.resource_type,
        "stable_id": call.stable_id,
    }


def _action_payload(action) -> dict[str, object]:
    return {
        "requirement": _requirement_payload(action.requirement),
        "resource": _resource_payload(action.resource),
    }


def _prepared_payload(
    prepared: PreparedProvisioning,
) -> dict[str, object]:
    check = prepared.check
    return {
        "endpoint": _endpoint_payload(check.endpoint),
        "requirements": [
            _requirement_payload(requirement)
            for requirement in check.requirements
        ],
        "observations": [
            _observation_payload(observation)
            for observation in check.observations
        ],
        "style_drift": [
            observation.requirement.name
            for observation in check.observations
            if observation.state is ProvisioningResourceState.STYLE_DRIFT
        ],
        "provider_calls": [
            _call_payload(call) for call in check.calls
        ],
        "actions": [
            _action_payload(action) for action in prepared.actions
        ],
        "limitations": list(check.limitations),
        "fingerprint": prepared.fingerprint,
        "preparation_id": prepared.preparation_id,
    }


def _receipt_payload(receipt: ProvisioningReceipt) -> dict[str, object]:
    payload = _prepared_payload(receipt.prepared)
    payload["approval_reference"] = receipt.authorization.approval_reference
    payload["action_receipts"] = [
        {"stable_id": action_receipt.stable_id}
        for action_receipt in receipt.action_receipts
    ]
    payload["readback"] = [
        _observation_payload(observation)
        for observation in receipt.readback.observations
    ]
    payload["provider_calls"] = [
        _call_payload(call) for call in receipt.calls
    ]
    return payload


def _error_payload(error: Exception) -> dict[str, object]:
    payload: dict[str, object] = {"error": str(error)}
    provider_calls = getattr(error, "provider_calls", ())
    if provider_calls:
        payload["provider_calls"] = [
            _call_payload(call) for call in provider_calls
        ]
    failed_stable_id = getattr(error, "failed_stable_id", None)
    if failed_stable_id is not None:
        payload["failed_stable_id"] = failed_stable_id
    if isinstance(error, ProvisioningExecutionError):
        payload["successful_stable_ids"] = list(
            error.successful_stable_ids
        )
        payload["failed_stable_id"] = error.failed_stable_id
    return payload


def run(
    argv,
    *,
    transport_factory: TransportFactory | None = None,
    environ: Mapping[str, str] = os.environ,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    attempt_store: ProvisioningAttemptStore | None = None,
) -> int:
    with contextlib.redirect_stderr(stderr):
        try:
            args = _parser().parse_args(argv)
        except SystemExit as error:
            return int(error.code)
    try:
        registry = load_registry_config(args.registry)
        runtime = load_runtime_config(args.runtime)
        endpoint = _resolve_endpoint(args, registry)
        token = environ.get("GITHUB_TOKEN")
        factory = transport_factory or _default_transport
        transport = factory(token, runtime.github)
        coordinator = ProvisioningCoordinator(
            endpoint,
            GitHubProvisioningAdapter(
                endpoint,
                transport,
                create_enabled=bool(token),
            ),
            attempt_store=(
                attempt_store
                or FileProvisioningAttemptStore(
                    default_attempt_ledger_path(environ)
                )
            ),
        )
        if args.command == "prepare":
            payload = _prepared_payload(coordinator.prepare())
        else:
            authorization = ProvisioningAuthorization(
                fingerprint=args.expected_fingerprint,
                preparation_id=args.preparation_id,
                approval_reference=args.approval_reference,
            )
            preflight = coordinator.check()
            receipt = coordinator.execute(
                authorization,
                preflight_calls=preflight.calls,
            )
            payload = _receipt_payload(receipt)
    except (
        AdapterError,
        ProvisioningError,
        ProvisioningExecutionError,
        RegistryError,
        RuntimeConfigError,
        ValueError,
    ) as error:
        json.dump(_error_payload(error), stderr, indent=2, sort_keys=True)
        stderr.write("\n")
        return 2
    json.dump(payload, stdout, indent=2, sort_keys=True)
    stdout.write("\n")
    return 0


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
