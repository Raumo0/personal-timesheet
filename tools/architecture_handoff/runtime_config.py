import json
from dataclasses import dataclass
from pathlib import Path


class RuntimeConfigError(ValueError):
    pass


def _positive_integer(value: object, field: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
    ):
        raise RuntimeConfigError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class QueryBudget:
    page_size: int
    max_pages: int
    max_items: int

    def __post_init__(self) -> None:
        page_size = _positive_integer(self.page_size, "page_size")
        if page_size > 100:
            raise RuntimeConfigError(
                "page_size must be between 1 and 100"
            )
        _positive_integer(self.max_pages, "max_pages")
        _positive_integer(self.max_items, "max_items")


@dataclass(frozen=True)
class QueryBudgetCeiling:
    max_pages: int
    max_items: int

    def __post_init__(self) -> None:
        _positive_integer(self.max_pages, "ceiling.max_pages")
        _positive_integer(self.max_items, "ceiling.max_items")


@dataclass(frozen=True)
class GitHubRuntimeConfig:
    request_timeout_seconds: int

    def __post_init__(self) -> None:
        _positive_integer(
            self.request_timeout_seconds,
            "providers.github.request_timeout_seconds",
        )


@dataclass(frozen=True)
class RuntimeConfig:
    default_budget: QueryBudget
    return_correlation_fallback_budget: QueryBudget
    ceiling: QueryBudgetCeiling
    github: GitHubRuntimeConfig

    def __post_init__(self) -> None:
        for name, budget in (
            ("default", self.default_budget),
            (
                "return_correlation_fallback",
                self.return_correlation_fallback_budget,
            ),
        ):
            if budget.max_pages > self.ceiling.max_pages:
                raise RuntimeConfigError(
                    f"{name}.max_pages exceeds configured ceiling"
                )
            if budget.max_items > self.ceiling.max_items:
                raise RuntimeConfigError(
                    f"{name}.max_items exceeds configured ceiling"
                )


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeConfigError(f"{field} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise RuntimeConfigError(f"{field} keys must be strings")
    return value


def _exact_keys(
    value: dict[str, object],
    expected: frozenset[str],
    field: str,
) -> None:
    actual = frozenset(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    parts = []
    if missing:
        parts.append(f"missing: {', '.join(missing)}")
    if unknown:
        parts.append(f"unknown: {', '.join(unknown)}")
    raise RuntimeConfigError(
        f"{field} keys are invalid ({'; '.join(parts)})"
    )


def _query_budget(value: object, field: str) -> QueryBudget:
    record = _object(value, field)
    _exact_keys(
        record,
        frozenset({"page_size", "max_pages", "max_items"}),
        field,
    )
    return QueryBudget(
        page_size=record["page_size"],
        max_pages=record["max_pages"],
        max_items=record["max_items"],
    )


def load_runtime_config(path: Path) -> RuntimeConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeConfigError(
            f"cannot read runtime config: {error}"
        ) from error
    root = _object(payload, "runtime config")
    _exact_keys(
        root,
        frozenset({"query_budgets", "providers"}),
        "runtime config",
    )
    budgets = _object(root["query_budgets"], "query_budgets")
    _exact_keys(
        budgets,
        frozenset(
            {
                "default",
                "return_correlation_fallback",
                "ceiling",
            }
        ),
        "query_budgets",
    )
    ceiling_record = _object(
        budgets["ceiling"],
        "query_budgets.ceiling",
    )
    _exact_keys(
        ceiling_record,
        frozenset({"max_pages", "max_items"}),
        "query_budgets.ceiling",
    )
    providers = _object(root["providers"], "providers")
    _exact_keys(providers, frozenset({"github"}), "providers")
    github = _object(providers["github"], "providers.github")
    _exact_keys(
        github,
        frozenset({"request_timeout_seconds"}),
        "providers.github",
    )
    return RuntimeConfig(
        default_budget=_query_budget(
            budgets["default"],
            "query_budgets.default",
        ),
        return_correlation_fallback_budget=_query_budget(
            budgets["return_correlation_fallback"],
            "query_budgets.return_correlation_fallback",
        ),
        ceiling=QueryBudgetCeiling(
            max_pages=ceiling_record["max_pages"],
            max_items=ceiling_record["max_items"],
        ),
        github=GitHubRuntimeConfig(
            request_timeout_seconds=github["request_timeout_seconds"],
        ),
    )


def resolve_query_budget(
    config: RuntimeConfig,
    profile: str,
    *,
    page_size: int | None = None,
    max_pages: int | None = None,
    max_items: int | None = None,
) -> QueryBudget:
    profiles = {
        "default": config.default_budget,
        "return_correlation_fallback": (
            config.return_correlation_fallback_budget
        ),
    }
    if profile not in profiles:
        raise RuntimeConfigError(
            f"unknown query budget profile: {profile}"
        )
    base = profiles[profile]
    resolved = QueryBudget(
        page_size=(
            page_size if page_size is not None else base.page_size
        ),
        max_pages=(
            max_pages if max_pages is not None else base.max_pages
        ),
        max_items=(
            max_items if max_items is not None else base.max_items
        ),
    )
    if resolved.max_pages > config.ceiling.max_pages:
        raise RuntimeConfigError(
            "max_pages exceeds configured ceiling"
        )
    if resolved.max_items > config.ceiling.max_items:
        raise RuntimeConfigError(
            "max_items exceeds configured ceiling"
        )
    return resolved
