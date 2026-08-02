import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .lifecycle import BRIEF_TRANSITIONS


ROUTING_STATUSES = {"planned", "active", "suspended", "retired"}


class RegistryError(ValueError):
    pass


class RepositoryTopology(str, Enum):
    REPOSITORY = "repository"
    MONOREPO = "monorepo"
    SUBMODULE = "submodule"


class StoreRole(str, Enum):
    DOCUMENTATION_INTAKE = "documentation-intake"


@dataclass(frozen=True)
class TargetConfig:
    key: str
    provider: str
    repository: str
    routing_status: str
    owns: tuple[str, ...]
    excludes: tuple[str, ...]
    repository_url: str | None = None
    scoped_path: str | None = None
    tracker_reference: str | None = None
    source_references: tuple[str, ...] = ()
    topology: RepositoryTopology = RepositoryTopology.REPOSITORY
    superproject_target: str | None = None
    submodule_path: str | None = None
    adoption_reference: str | None = None
    adoption_state: str | None = None


@dataclass(frozen=True)
class StoreConfig:
    key: str
    role: StoreRole
    provider: str
    repository: str
    routing_status: str
    tracker_reference: str | None = None


@dataclass(frozen=True)
class RegistryConfig:
    targets: tuple[TargetConfig, ...]
    stores: tuple[StoreConfig, ...]


ProviderEndpointConfig = TargetConfig | StoreConfig


def _require_string(record, field):
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{field} must be a non-empty string")
    return value.strip()


def _string_tuple(record, field):
    value = record.get(field, [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise RegistryError(f"{field} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _optional_string(record, field):
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{field} must be a non-empty string when present")
    return value.strip()


def _validate_relative_path(value: str | None, field: str) -> None:
    if value is None:
        return
    parts = value.split("/")
    if (
        value.startswith("/")
        or "\\" in value
        or value in {".", ".."}
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise RegistryError(f"{field} must be a relative POSIX path")


def _validate_target(target: TargetConfig) -> None:
    _validate_relative_path(target.scoped_path, "scoped_path")
    _validate_relative_path(target.submodule_path, "submodule_path")

    overlap = sorted(set(target.owns) & set(target.excludes))
    if overlap:
        raise RegistryError(
            f"owns and excludes overlap for {target.key}: {', '.join(overlap)}"
        )

    if (
        target.topology is RepositoryTopology.MONOREPO
        and target.scoped_path is None
    ):
        raise RegistryError(
            f"monorepo target {target.key} requires scoped_path"
        )
    if target.topology is RepositoryTopology.SUBMODULE:
        if target.superproject_target is None:
            raise RegistryError(
                f"submodule target {target.key} requires superproject_target"
            )
        if target.submodule_path is None:
            raise RegistryError(
                f"submodule target {target.key} requires submodule_path"
            )
    elif (
        target.superproject_target is not None
        or target.submodule_path is not None
    ):
        raise RegistryError(
            f"target {target.key} has submodule fields without submodule topology"
        )

    if (target.adoption_reference is None) != (target.adoption_state is None):
        raise RegistryError(
            "adoption_reference and adoption_state must appear together"
        )
    if (
        target.adoption_state is not None
        and target.adoption_state not in BRIEF_TRANSITIONS
    ):
        raise RegistryError(
            "adoption_state must be a canonical lifecycle value"
        )


def _validate_superproject_relationships(
    targets: tuple[TargetConfig, ...],
) -> None:
    by_key = {target.key: target for target in targets}
    for target in targets:
        superproject = target.superproject_target
        if superproject is None:
            continue
        if superproject == target.key:
            raise RegistryError(
                f"target {target.key} cannot be its own superproject"
            )
        if superproject not in by_key:
            raise RegistryError(
                f"unknown superproject target for {target.key}: {superproject}"
            )

    for target in targets:
        seen = set()
        current = target
        while current.superproject_target is not None:
            if current.key in seen:
                raise RegistryError(
                    f"superproject relationship cycle at {current.key}"
                )
            seen.add(current.key)
            current = by_key[current.superproject_target]


def _validate_distinct_physical_scopes(
    targets: tuple[TargetConfig, ...],
) -> None:
    seen = {}
    for target in targets:
        scope_keys = []
        if target.topology in {
            RepositoryTopology.REPOSITORY,
            RepositoryTopology.MONOREPO,
        }:
            scope_keys.append(
                (
                    "provider-repository",
                    target.provider,
                    target.repository,
                    target.scoped_path,
                )
            )
            if target.repository_url is not None:
                scope_keys.append(
                    (
                        "repository-url",
                        target.repository_url,
                        target.scoped_path,
                    )
                )
        elif target.topology is RepositoryTopology.SUBMODULE:
            scope_keys.append(
                (
                    "submodule",
                    target.superproject_target,
                    target.submodule_path,
                    target.scoped_path,
                )
            )

        for scope_key in scope_keys:
            previous = seen.get(scope_key)
            if previous is not None:
                keys = ", ".join(sorted((previous, target.key)))
                raise RegistryError(f"duplicate physical target scope: {keys}")
            seen[scope_key] = target.key


def _load_targets(path: Path) -> tuple[TargetConfig, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"cannot read target registry: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("targets"), list):
        raise RegistryError("registry must contain a targets list")

    targets = []
    keys = set()
    for record in payload["targets"]:
        if not isinstance(record, dict):
            raise RegistryError("each target must be an object")
        key = _require_string(record, "key")
        if key in keys:
            raise RegistryError(f"duplicate target key: {key}")
        keys.add(key)
        routing_status = _require_string(record, "routing_status")
        if routing_status not in ROUTING_STATUSES:
            allowed = ", ".join(sorted(ROUTING_STATUSES))
            raise RegistryError(f"routing_status must be one of: {allowed}")
        topology_value = _optional_string(record, "topology") or "repository"
        try:
            topology = RepositoryTopology(topology_value)
        except ValueError as error:
            allowed = ", ".join(topology.value for topology in RepositoryTopology)
            raise RegistryError(f"topology must be one of: {allowed}") from error
        target = TargetConfig(
            key=key,
            provider=_require_string(record, "provider"),
            repository=_require_string(record, "repository"),
            routing_status=routing_status,
            owns=_string_tuple(record, "owns"),
            excludes=_string_tuple(record, "excludes"),
            repository_url=_optional_string(record, "repository_url"),
            scoped_path=_optional_string(record, "scoped_path"),
            tracker_reference=_optional_string(record, "tracker_reference"),
            source_references=_string_tuple(record, "source_references"),
            topology=topology,
            superproject_target=_optional_string(
                record, "superproject_target"
            ),
            submodule_path=_optional_string(record, "submodule_path"),
            adoption_reference=_optional_string(
                record, "adoption_reference"
            ),
            adoption_state=_optional_string(record, "adoption_state"),
        )
        _validate_target(target)
        targets.append(target)
    result = tuple(targets)
    _validate_superproject_relationships(result)
    _validate_distinct_physical_scopes(result)
    return result


def _load_store_records(path: Path) -> tuple[dict[str, object], ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(
            f"cannot read target registry: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise RegistryError("registry must contain a targets list")
    records = payload.get("stores", [])
    if not isinstance(records, list):
        raise RegistryError("stores must be a list when present")
    if any(not isinstance(record, dict) for record in records):
        raise RegistryError("each store must be an object")
    return tuple(records)


def load_registry_config(path: Path) -> RegistryConfig:
    targets = _load_targets(path)
    stores = []
    store_keys = set()
    target_keys = {target.key for target in targets}
    for record in _load_store_records(path):
        key = _require_string(record, "key")
        if key in store_keys:
            raise RegistryError(f"duplicate store key: {key}")
        if key in target_keys:
            raise RegistryError(
                f"registry key is used by target and store: {key}"
            )
        store_keys.add(key)
        role_value = _require_string(record, "role")
        try:
            role = StoreRole(role_value)
        except ValueError as error:
            allowed = ", ".join(role.value for role in StoreRole)
            raise RegistryError(
                f"store role must be one of: {allowed}"
            ) from error
        routing_status = _require_string(record, "routing_status")
        if routing_status not in ROUTING_STATUSES:
            allowed = ", ".join(sorted(ROUTING_STATUSES))
            raise RegistryError(
                f"routing_status must be one of: {allowed}"
            )
        stores.append(
            StoreConfig(
                key=key,
                role=role,
                provider=_require_string(record, "provider"),
                repository=_require_string(record, "repository"),
                routing_status=routing_status,
                tracker_reference=_optional_string(
                    record,
                    "tracker_reference",
                ),
            )
        )
    return RegistryConfig(
        targets=targets,
        stores=tuple(stores),
    )


def load_registry(path: Path) -> tuple[TargetConfig, ...]:
    return load_registry_config(path).targets


def resolve_active_target(
    targets: tuple[TargetConfig, ...], key: str
) -> TargetConfig:
    matches = [target for target in targets if target.key == key]
    if not matches:
        raise RegistryError(f"target not found: {key}")
    target = matches[0]
    if target.routing_status != "active":
        raise RegistryError(
            f"target {key} is not active: {target.routing_status}"
        )
    return target


def resolve_active_store(
    stores: tuple[StoreConfig, ...],
    key: str,
    required_role: StoreRole,
) -> StoreConfig:
    if not isinstance(required_role, StoreRole):
        raise RegistryError("required_role must be a StoreRole")
    matches = [store for store in stores if store.key == key]
    if not matches:
        raise RegistryError(f"store not found: {key}")
    store = matches[0]
    if store.role is not required_role:
        raise RegistryError(
            f"store {key} does not have required role: "
            f"{required_role.value}"
        )
    if store.routing_status != "active":
        raise RegistryError(
            f"store {key} is not active: {store.routing_status}"
        )
    return store
