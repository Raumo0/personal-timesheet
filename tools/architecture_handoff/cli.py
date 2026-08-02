import argparse
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Callable, TextIO

from .adapter import AdvancedReadAdapter, ReadAdapter, QueryRequest
from .core import CATEGORY_HINTS, build_inventory
from .github import AdapterError, GitHubReadAdapter, GitHubRestTransport
from .models import WorkItemSummary, WorkRoute
from .query_coordinator import (
    QueryCoordinator,
    build_correlation_view,
    classify_stale_revisions,
)
from .query_models import (
    AdvancedQuery,
    ContinuationPlan,
    QueryCoverage,
    QueryPurpose,
    SimilarityMode,
)
from .registry import (
    ProviderEndpointConfig,
    RegistryError,
    StoreConfig,
    StoreRole,
    TargetConfig,
    load_registry_config,
    resolve_active_store,
    resolve_active_target,
)
from .runtime_config import (
    GitHubRuntimeConfig,
    load_runtime_config,
    resolve_query_budget,
)
from .write_models import IntakeState, ReturnKind


AdapterFactory = Callable[[ProviderEndpointConfig], ReadAdapter]


def _parser():
    parser = argparse.ArgumentParser(
        description="Inspect Architecture-to-OpenSpec work without writing."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "search"):
        command = subparsers.add_parser(name)
        _add_target_arguments(command)
        if name in {"list", "search"}:
            command.add_argument(
                "--limit",
                type=_bounded_integer(1, 100),
            )
            command.add_argument("--cursor")
        if name == "search":
            lookup = command.add_mutually_exclusive_group(required=True)
            lookup.add_argument("--source-reference")
            lookup.add_argument("--correlation-id")

    get = subparsers.add_parser("get")
    _add_config_arguments(get)
    endpoint = get.add_mutually_exclusive_group(required=True)
    endpoint.add_argument("--target")
    endpoint.add_argument("--store")
    get.add_argument("--id", required=True)

    returns = subparsers.add_parser("returns")
    _add_store_arguments(returns)
    _add_budget_arguments(returns)
    returns.add_argument(
        "--return-kind",
        choices=tuple(value.value for value in ReturnKind),
    )
    returns.add_argument(
        "--intake-state",
        required=True,
        choices=tuple(value.value for value in IntakeState),
    )

    trace = subparsers.add_parser("trace")
    _add_advanced_arguments(trace)
    trace_lookup = trace.add_mutually_exclusive_group(required=True)
    trace_lookup.add_argument("--source-reference")
    trace_lookup.add_argument("--correlation-id")

    stale = subparsers.add_parser("stale")
    _add_advanced_arguments(stale)
    stale.add_argument("--source-reference", required=True)
    stale.add_argument("--current-revision", required=True)

    similarity = subparsers.add_parser("similarity")
    _add_advanced_arguments(similarity)
    similarity.add_argument("--capability")
    similarity.add_argument("--expected-outcome")
    similarity.add_argument(
        "--mode",
        choices=tuple(value.value for value in SimilarityMode),
        default=SimilarityMode.HYBRID.value,
    )

    preflight = subparsers.add_parser("preflight")
    _add_advanced_arguments(preflight)
    preflight.add_argument("--source-reference", required=True)
    preflight.add_argument(
        "--route",
        choices=tuple(
            route.value
            for route in WorkRoute
            if route is not WorkRoute.TARGET_NATIVE_INTERNAL
        ),
    )
    preflight.add_argument("--capability")
    preflight.add_argument("--expected-outcome")
    preflight.add_argument(
        "--mode",
        choices=tuple(value.value for value in SimilarityMode),
        default=SimilarityMode.HYBRID.value,
    )
    return parser


def _add_target_arguments(parser: argparse.ArgumentParser) -> None:
    _add_config_arguments(parser)
    parser.add_argument("--target", required=True)


def _add_store_arguments(parser: argparse.ArgumentParser) -> None:
    _add_config_arguments(parser)
    parser.add_argument("--store", required=True)


def _add_config_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)


def _bounded_integer(minimum: int, maximum: int):
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError(
                f"must be an integer from {minimum} to {maximum}"
            ) from error
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(
                f"must be between {minimum} and {maximum}"
            )
        return number

    return parse


def _add_advanced_arguments(parser: argparse.ArgumentParser) -> None:
    _add_target_arguments(parser)
    _add_budget_arguments(parser)


def _add_budget_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--limit",
        type=_bounded_integer(1, 100),
    )
    parser.add_argument(
        "--max-pages",
        type=_bounded_integer(1, sys.maxsize),
    )
    parser.add_argument(
        "--max-items",
        type=_bounded_integer(1, sys.maxsize),
    )


def _default_adapter_factory(
    endpoint: ProviderEndpointConfig,
    github_runtime: GitHubRuntimeConfig,
) -> ReadAdapter:
    token = os.environ.get("GITHUB_TOKEN")
    return GitHubReadAdapter(
        endpoint.repository,
        GitHubRestTransport(
            token=token,
            timeout_seconds=github_runtime.request_timeout_seconds,
        ),
        logical_target=endpoint.key,
        semantic_search_enabled=bool(token),
    )


def _summary_payload(item: WorkItemSummary):
    return {
        "id": item.provider_id,
        "provider_qualified_id": item.provider_qualified_id,
        "title": item.title,
        "status": item.status,
        "work_route": item.work_route.value,
        "updated": item.updated,
        "url": item.url,
        "priority": item.priority,
        "labels": list(item.labels),
    }


def _query_for_command(args) -> AdvancedQuery:
    limit = min(args.limit, args.max_items)
    if args.command == "returns":
        return AdvancedQuery(
            purpose=QueryPurpose.RETURN_INTAKE,
            logical_target=args.store,
            intake_state=IntakeState(args.intake_state),
            return_kind=(
                ReturnKind(args.return_kind)
                if args.return_kind is not None
                else None
            ),
            limit=limit,
        )
    if args.command == "trace":
        return AdvancedQuery(
            purpose=(
                QueryPurpose.SOURCE_TRACEABILITY
                if args.source_reference is not None
                else QueryPurpose.CORRELATION
            ),
            logical_target=args.target,
            source_reference=args.source_reference,
            correlation_id=args.correlation_id,
            limit=limit,
        )
    if args.command == "stale":
        return AdvancedQuery(
            purpose=QueryPurpose.SOURCE_TRACEABILITY,
            logical_target=args.target,
            source_reference=args.source_reference,
            limit=limit,
        )
    if args.command == "similarity":
        return AdvancedQuery.similarity(
            logical_target=args.target,
            capability=args.capability,
            expected_outcome=args.expected_outcome,
            similarity_mode=SimilarityMode(args.mode),
            limit=limit,
        )
    raise ValueError(f"unsupported advanced command: {args.command}")


def _enum_value(value):
    return value.value if hasattr(value, "value") else value


def _query_payload(query: AdvancedQuery):
    payload = {
        "purpose": query.purpose.value,
        "logical_target": query.logical_target,
        "requirement": query.requirement.value,
        "active_only": query.active_only,
        "routes": [route.value for route in query.routes],
        "limit": query.limit,
    }
    for field in (
        "source_reference",
        "current_revision",
        "correlation_id",
        "intake_state",
        "return_kind",
        "capability",
        "expected_outcome",
    ):
        value = getattr(query, field)
        if value is not None:
            payload[field] = _enum_value(value)
    if query.purpose is QueryPurpose.SIMILARITY:
        payload["similarity_mode"] = query.similarity_mode.value
    return payload


def _hit_payload(hit):
    payload = _summary_payload(hit.item)
    payload.update(
        {
            "matched_signals": list(hit.matched_signals),
            "provider_rank": hit.provider_rank,
            "metadata_state": hit.metadata_state.value,
        }
    )
    return payload


def _report_payload(args, coverage: QueryCoverage):
    if args.command == "trace" and args.correlation_id is not None:
        report = build_correlation_view(
            coverage,
            args.correlation_id,
        )
        return {
            "correlation_id": report.correlation_id,
            "nodes": [
                {
                    "provider_qualified_id": node.provider_qualified_id,
                    "relation_targets": list(node.relation_targets),
                }
                for node in report.nodes
            ],
            "unresolved_targets": list(report.unresolved_targets),
            "completeness": report.completeness.value,
            "limitations": list(report.limitations),
        }
    if args.command == "stale":
        report = classify_stale_revisions(
            coverage,
            args.source_reference,
            args.current_revision,
        )
        return {
            "source_reference": report.source_reference,
            "current_revision": report.current_revision,
            "entries": [
                {
                    "provider_qualified_id": entry.provider_qualified_id,
                    "observed_revision": entry.observed_revision,
                    "classification": entry.classification,
                }
                for entry in report.entries
            ],
            "completeness": report.completeness.value,
            "limitations": list(report.limitations),
        }
    return None


def _advanced_payload(
    args,
    endpoint: ProviderEndpointConfig,
    adapter: AdvancedReadAdapter,
):
    query = _query_for_command(args)
    plan = ContinuationPlan(
        query=query,
        max_pages=args.max_pages,
        max_items=args.max_items,
    )
    coverage = QueryCoordinator(adapter).execute(plan)
    provider_calls = tuple(
        call
        for call in coverage.calls
        if call.searched_scopes
    )
    searched_scopes = []
    for call in provider_calls:
        for scope in call.searched_scopes:
            if scope not in searched_scopes:
                searched_scopes.append(scope)
    payload = {
        "endpoint_kind": (
            "store" if isinstance(endpoint, StoreConfig) else "target"
        ),
        (
            "store" if isinstance(endpoint, StoreConfig) else "target"
        ): endpoint.key,
        "provider": endpoint.provider,
        "query": _query_payload(query),
        "plan": {
            "max_pages": plan.max_pages,
            "max_items": plan.max_items,
        },
        "requirement": query.requirement.value,
        "capability": coverage.capability.value,
        "completeness": coverage.completeness.value,
        "searched_scopes": searched_scopes,
        "scopes": searched_scopes,
        "provider_call_count": len(provider_calls),
        "provider_calls": [
            {
                "purpose": call.purpose.value,
                "cursor": call.cursor,
                "searched_scopes": list(call.searched_scopes),
                "provider_record_count": call.provider_record_count,
            }
            for call in provider_calls
        ],
        "cursor": {
            "next": coverage.next_cursor,
            "continuation_required": coverage.next_cursor is not None,
        },
        "limitations": list(coverage.limitations),
        "hits": [_hit_payload(hit) for hit in coverage.hits],
    }
    report = _report_payload(args, coverage)
    if report is not None:
        payload["report"] = report
    return payload


def _preflight_payload(
    args,
    target: TargetConfig,
    adapter: AdvancedReadAdapter,
):
    limit = min(args.limit, args.max_items)
    routes = (
        (WorkRoute(args.route),)
        if args.route is not None
        else ()
    )
    queries = [
        AdvancedQuery(
            purpose=QueryPurpose.SOURCE_TRACEABILITY,
            logical_target=args.target,
            active_only=False,
            routes=routes,
            source_reference=args.source_reference,
            limit=limit,
        )
    ]
    if args.capability is not None or args.expected_outcome is not None:
        queries.append(
            AdvancedQuery.similarity(
                logical_target=args.target,
                capability=args.capability,
                expected_outcome=args.expected_outcome,
                similarity_mode=SimilarityMode(args.mode),
                limit=limit,
            )
        )

    coordinator = QueryCoordinator(adapter)
    lanes = []
    for query in queries:
        plan = ContinuationPlan(
            query=query,
            max_pages=args.max_pages,
            max_items=args.max_items,
        )
        coverage = coordinator.execute(plan)
        provider_calls = tuple(
            call
            for call in coverage.calls
            if call.searched_scopes
        )
        searched_scopes = []
        for call in provider_calls:
            for scope in call.searched_scopes:
                if scope not in searched_scopes:
                    searched_scopes.append(scope)
        lanes.append(
            {
                "name": (
                    "exact-source"
                    if query.purpose
                    is QueryPurpose.SOURCE_TRACEABILITY
                    else "similarity"
                ),
                "query": _query_payload(query),
                "plan": {
                    "max_pages": plan.max_pages,
                    "max_items": plan.max_items,
                },
                "requirement": query.requirement.value,
                "capability": coverage.capability.value,
                "completeness": coverage.completeness.value,
                "searched_scopes": searched_scopes,
                "scopes": searched_scopes,
                "provider_call_count": len(provider_calls),
                "provider_calls": [
                    {
                        "purpose": call.purpose.value,
                        "cursor": call.cursor,
                        "searched_scopes": list(call.searched_scopes),
                        "provider_record_count": (
                            call.provider_record_count
                        ),
                    }
                    for call in provider_calls
                ],
                "cursor": {
                    "next": coverage.next_cursor,
                    "continuation_required": (
                        coverage.next_cursor is not None
                    ),
                },
                "limitations": list(coverage.limitations),
                "candidates": [
                    _hit_payload(hit) for hit in coverage.hits
                ],
            }
        )
    return {
        "target": target.key,
        "provider": target.provider,
        "lanes": lanes,
    }


def _validate_command_arguments(args) -> None:
    if (
        args.command == "stale"
        and not args.current_revision.strip()
    ):
        raise ValueError("current_revision must be a non-empty string")


def _apply_runtime_budget(args, runtime) -> None:
    if args.command in {"list", "search"}:
        budget = resolve_query_budget(
            runtime,
            "default",
            page_size=args.limit,
        )
        args.limit = budget.page_size
        return
    if args.command in {
        "returns",
        "trace",
        "stale",
        "similarity",
        "preflight",
    }:
        budget = resolve_query_budget(
            runtime,
            "default",
            page_size=args.limit,
            max_pages=args.max_pages,
            max_items=args.max_items,
        )
        args.limit = budget.page_size
        args.max_pages = budget.max_pages
        args.max_items = budget.max_items


def run(
    argv,
    *,
    adapter_factory: AdapterFactory | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
):
    with contextlib.redirect_stderr(stderr):
        try:
            args = _parser().parse_args(argv)
        except SystemExit as error:
            return int(error.code)
    try:
        _validate_command_arguments(args)
        runtime = load_runtime_config(args.runtime)
        _apply_runtime_budget(args, runtime)
        registry = load_registry_config(args.registry)
        use_store = args.command == "returns" or (
            args.command == "get" and args.store is not None
        )
        endpoint = (
            resolve_active_store(
                registry.stores,
                args.store,
                StoreRole.DOCUMENTATION_INTAKE,
            )
            if use_store
            else resolve_active_target(registry.targets, args.target)
        )
        if endpoint.provider != "github":
            raise RegistryError(
                f"provider is not enabled in P0: {endpoint.provider}"
            )
        adapter = (
            adapter_factory(endpoint)
            if adapter_factory is not None
            else _default_adapter_factory(endpoint, runtime.github)
        )
        if args.command in {
            "returns",
            "trace",
            "stale",
            "similarity",
        }:
            payload = _advanced_payload(args, endpoint, adapter)
        elif args.command == "preflight":
            payload = _preflight_payload(args, endpoint, adapter)
        elif args.command == "get":
            endpoint_kind = (
                "store" if isinstance(endpoint, StoreConfig) else "target"
            )
            payload = {
                "endpoint_kind": endpoint_kind,
                endpoint_kind: endpoint.key,
                "provider": endpoint.provider,
                "item": adapter.get_item(args.id),
            }
        else:
            result = adapter.list_items(
                QueryRequest(
                    source_reference=(
                        args.source_reference
                        if args.command == "search"
                        else None
                    ),
                    correlation_id=(
                        args.correlation_id
                        if args.command == "search"
                        else None
                    ),
                    cursor=args.cursor,
                    limit=args.limit,
                )
            )
            inventory = build_inventory(result)
            payload = {
                "target": endpoint.key,
                "provider": endpoint.provider,
                "capabilities": {
                    key: value.value
                    for key, value in adapter.capabilities().items()
                },
                "completeness": inventory.completeness.value,
                "searched_scopes": list(result.searched_scopes),
                "next_cursor": inventory.next_cursor,
                "limitations": list(inventory.limitations),
                "categories": [
                    {
                        "work_route": route.value,
                        "count": inventory.counts[route],
                        "hint": CATEGORY_HINTS[route],
                    }
                    for route in WorkRoute
                ],
                "items": [_summary_payload(item) for item in result.items],
            }
    except (AdapterError, RegistryError, ValueError) as error:
        print(f"error: {error}", file=stderr)
        return 2
    json.dump(payload, stdout, indent=2, sort_keys=True)
    stdout.write("\n")
    return 0


def main():
    raise SystemExit(run(sys.argv[1:]))
