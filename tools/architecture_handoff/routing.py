from .registry import RegistryError, TargetConfig


def _criteria(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise RegistryError(f"{field} must be a tuple of non-empty strings")
    return tuple(value.strip() for value in values)


def _optional_criterion(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{field} must be a non-empty string when present")
    return value.strip()


def _routing_path(value: str | None) -> str | None:
    value = _optional_criterion(value, "path")
    if value is None:
        return None
    parts = value.split("/")
    if (
        value.startswith("/")
        or "\\" in value
        or value in {".", ".."}
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise RegistryError("path must be a relative POSIX path")
    return value


def _join_path(*parts: str | None) -> str:
    return "/".join(part for part in parts if part)


def _repository_matches(target: TargetConfig, repository: str) -> bool:
    return repository in {target.repository, target.repository_url}


def _repository_scopes(
    target: TargetConfig,
    targets_by_key: dict[str, TargetConfig],
    repository: str,
) -> tuple[str, ...]:
    scopes = []
    if _repository_matches(target, repository):
        scopes.append(target.scoped_path or "")

    current = target
    path_from_parent = target.submodule_path
    while (
        current.superproject_target is not None
        and path_from_parent is not None
    ):
        parent = targets_by_key.get(current.superproject_target)
        if parent is None:
            break
        if _repository_matches(parent, repository):
            scopes.append(
                _join_path(
                    parent.scoped_path,
                    path_from_parent,
                    target.scoped_path,
                )
            )
        path_from_parent = _join_path(
            parent.submodule_path,
            parent.scoped_path,
            path_from_parent,
        )
        current = parent
    return tuple(dict.fromkeys(scopes))


def _contains(scope: str, path: str) -> bool:
    return not scope or path == scope or path.startswith(f"{scope}/")


def resolve_routed_target(
    targets: tuple[TargetConfig, ...],
    *,
    ownership: tuple[str, ...] = (),
    source_references: tuple[str, ...] = (),
    repository: str | None = None,
    path: str | None = None,
) -> TargetConfig:
    ownership = _criteria(ownership, "ownership")
    source_references = _criteria(source_references, "source_references")
    repository = _optional_criterion(repository, "repository")
    path = _routing_path(path)

    if path is not None and repository is None:
        raise RegistryError("path requires repository routing criteria")
    if not ownership and not source_references and repository is None:
        raise RegistryError("routing criteria are required")

    targets_by_key = {target.key: target for target in targets}
    requested_selectors = set(ownership) | set(source_references)
    requested_ownership = set(ownership)
    candidates = []
    for target in targets:
        if target.routing_status != "active":
            continue

        ownership_matches = requested_ownership & set(target.owns)
        source_matches = set(source_references) & set(
            target.source_references
        )
        if source_references and not source_matches:
            continue

        scopes = ("",)
        if repository is not None:
            scopes = _repository_scopes(
                target,
                targets_by_key,
                repository,
            )
            if not scopes:
                continue
            if path is not None:
                scopes = tuple(scope for scope in scopes if _contains(scope, path))
                if not scopes:
                    continue

        excluded = requested_selectors & set(target.excludes)
        if excluded:
            if ownership_matches or source_matches:
                names = ", ".join(sorted(excluded))
                raise RegistryError(
                    f"target {target.key} both owns and excludes "
                    f"requested work: {names}"
                )
            continue
        if ownership and ownership_matches != requested_ownership:
            continue

        specificity = max((len(scope.split("/")) if scope else 0) for scope in scopes)
        candidates.append((specificity, target))

    if repository is not None and path is not None and candidates:
        highest_specificity = max(specificity for specificity, _ in candidates)
        candidates = [
            candidate
            for candidate in candidates
            if candidate[0] == highest_specificity
        ]

    if not candidates:
        raise RegistryError("no active target matches routing criteria")
    if len(candidates) > 1:
        keys = ", ".join(sorted(target.key for _, target in candidates))
        raise RegistryError(f"ambiguous target match: {keys}")
    return candidates[0][1]
