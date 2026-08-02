import json
import re
from datetime import date
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .adapter import AdapterBinding, QueryRequest
from .models import (
    CapabilityStatus,
    QueryResult,
    ResultCompleteness,
    WorkItemSummary,
    WorkRoute,
)
from .protocol_metadata import (
    MetadataState,
    ProtocolMetadata,
    parse_protocol_block,
    validate_protocol_labels,
)
from .query_models import (
    AdvancedQuery,
    QueryPurpose,
    SearchHit,
    SearchPage,
)
from .write_models import ProtocolItemKind


_GITHUB_ERROR_BODY_MAX_BYTES = 4096
_GITHUB_ERROR_BODY_READ_BYTES = _GITHUB_ERROR_BODY_MAX_BYTES + 1


class AdapterError(RuntimeError):
    pass


class GitHubNotFoundError(AdapterError):
    def __init__(self):
        super().__init__("GitHub resource was not found")


class GitHubRateLimitError(AdapterError):
    def __init__(self, retry_after: str | None):
        super().__init__("GitHub request was rate limited")
        self.retry_after = retry_after


def _is_github_secondary_rate_limit(error: HTTPError) -> bool:
    try:
        body = error.read(_GITHUB_ERROR_BODY_READ_BYTES)
    except (AttributeError, OSError, ValueError):
        return False
    if (
        not isinstance(body, bytes)
        or len(body) > _GITHUB_ERROR_BODY_MAX_BYTES
    ):
        return False
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    message = payload.get("message")
    if not isinstance(message, str):
        return False
    normalized = message.lower()
    return (
        "secondary rate limit" in normalized
        or "abuse detection mechanism" in normalized
    )


class SameOriginRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        source = urlparse(req.full_url)
        destination = urlparse(newurl)
        if (
            source.scheme.lower(),
            source.netloc.lower(),
        ) != (
            destination.scheme.lower(),
            destination.netloc.lower(),
        ):
            raise HTTPError(
                newurl,
                code,
                "cross-origin redirect rejected",
                headers,
                fp,
            )
        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            newurl,
        )


class GitHubTransport(Protocol):
    def get(
        self, path: str, params: Mapping[str, str]
    ) -> tuple[object, str | None]:
        ...


def next_page_cursor(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        url_part, *metadata = part.split(";")
        if any('rel="next"' in value for value in metadata):
            url = url_part.strip().strip("<>")
            values = parse_qs(urlparse(url).query).get("page")
            return values[0] if values else None
    return None


class GitHubRestTransport:
    def __init__(
        self,
        token: str | None = None,
        api_url: str = "https://api.github.com",
        opener=None,
        *,
        api_version: str = "2026-03-10",
        timeout_seconds: int = 15,
    ):
        parsed_url = urlparse(api_url)
        if (
            parsed_url.scheme != "https"
            or not parsed_url.netloc
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise AdapterError("GitHub API URL must use https")
        if token is not None and (
            not isinstance(token, str)
            or any(
                ord(character) < 33 or ord(character) > 126
                for character in token
            )
        ):
            raise AdapterError(
                "GitHub token contains unsupported characters"
            )
        if not isinstance(api_version, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            api_version,
        ):
            raise AdapterError(
                "GitHub API version must use YYYY-MM-DD"
            )
        try:
            date.fromisoformat(api_version)
        except ValueError as error:
            raise AdapterError(
                "GitHub API version must use YYYY-MM-DD"
            ) from error
        if (
            not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or timeout_seconds < 1
        ):
            raise AdapterError(
                "timeout_seconds must be a positive integer"
            )
        self._token = token or None
        self._api_url = api_url.rstrip("/")
        self._api_version = api_version
        self._opener = (
            opener
            if opener is not None
            else build_opener(SameOriginRedirectHandler()).open
        )
        self._timeout_seconds = timeout_seconds

    def get(
        self, path: str, params: Mapping[str, str]
    ) -> tuple[object, str | None]:
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        payload: Mapping[str, object],
    ) -> tuple[object, str | None]:
        return self._request("POST", path, payload=payload)

    def patch(
        self,
        path: str,
        payload: Mapping[str, object],
    ) -> tuple[object, str | None]:
        return self._request("PATCH", path, payload=payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> tuple[object, str | None]:
        query = urlencode(params or {})
        url = f"{self._api_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "architecture-handoff",
            "X-GitHub-Api-Version": self._api_version,
        }
        data = None
        if payload is not None:
            try:
                data = json.dumps(
                    payload,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            except (TypeError, ValueError) as error:
                raise AdapterError(
                    "GitHub request payload must be JSON-compatible"
                ) from error
            headers["Content-Type"] = "application/json"
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = Request(
            url,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self._opener(
                request,
                timeout=self._timeout_seconds,
            ) as response:
                try:
                    payload = json.loads(response.read().decode("utf-8"))
                except (
                    OSError,
                    UnicodeError,
                    json.JSONDecodeError,
                ) as error:
                    raise AdapterError(
                        "GitHub response was not valid UTF-8 JSON"
                    ) from error
                cursor = next_page_cursor(response.headers.get("Link"))
        except HTTPError as error:
            response_headers = error.headers or {}
            retry_after = response_headers.get("Retry-After")
            is_rate_limit = error.code == 429 or (
                error.code == 403
                and (
                    retry_after is not None
                    or response_headers.get("X-RateLimit-Remaining") == "0"
                    or _is_github_secondary_rate_limit(error)
                )
            )
            if is_rate_limit:
                error.close()
                raise GitHubRateLimitError(retry_after) from error
            if error.code == 404:
                error.close()
                raise GitHubNotFoundError() from None
            message = f"GitHub request failed: {error}"
            error.close()
            raise AdapterError(message) from error
        except (URLError, TimeoutError) as error:
            raise AdapterError(f"GitHub request failed: {error}") from error
        except ValueError as error:
            raise AdapterError("GitHub request failed") from error
        return payload, cursor


def validate_repository_name(repository: str) -> str:
    if not isinstance(repository, str):
        raise AdapterError("GitHub repository must use owner/name")
    parts = repository.split("/")
    if len(parts) != 2:
        raise AdapterError("GitHub repository must use owner/name")
    owner, name = parts
    if (
        owner in {".", ".."}
        or name in {".", ".."}
        or not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?",
            owner,
        )
        or not re.fullmatch(r"[A-Za-z0-9_.-]+", name)
    ):
        raise AdapterError("GitHub repository must use owner/name")
    return repository


class GitHubReadAdapter:
    def __init__(
        self,
        repository: str,
        transport: GitHubTransport,
        *,
        logical_target: str | None = None,
        semantic_search_enabled: bool = False,
    ):
        self._repository = validate_repository_name(repository)
        self._transport = transport
        if logical_target is not None and (
            not isinstance(logical_target, str)
            or not logical_target.strip()
        ):
            raise AdapterError(
                "logical_target must be a non-empty string"
            )
        if not isinstance(semantic_search_enabled, bool):
            raise AdapterError("semantic_search_enabled must be a bool")
        self._logical_target = logical_target
        self._semantic_search_enabled = semantic_search_enabled
        self._binding = (
            AdapterBinding(
                provider="github",
                provider_scope=self._repository,
                logical_target=logical_target,
            )
            if logical_target is not None
            else None
        )

    @property
    def binding(self) -> AdapterBinding | None:
        return self._binding

    def capabilities(self) -> Mapping[str, CapabilityStatus]:
        return {
            "task-discovery": CapabilityStatus.SUPPORTED,
            "item-inspection": CapabilityStatus.SUPPORTED,
            "source-lookup": CapabilityStatus.PARTIAL,
            "correlation-lookup": CapabilityStatus.PARTIAL,
            "controlled-write": CapabilityStatus.UNSUPPORTED,
            "duplicate-preflight": CapabilityStatus.UNSUPPORTED,
            "return-round-trip": CapabilityStatus.UNSUPPORTED,
        }

    def list_items(self, request: QueryRequest) -> QueryResult:
        cursor = request.cursor or "1"
        lookup = request.source_reference or request.correlation_id
        limitations = []
        if request.route is WorkRoute.TARGET_NATIVE_INTERNAL:
            return QueryResult(
                items=(),
                completeness=ResultCompleteness.UNSUPPORTED,
                searched_scopes=(),
                limitations=(
                    "GitHub cannot filter for the absence of a work-route "
                    "label through the required native request",
                ),
            )
        if lookup is not None:
            escaped_lookup = lookup.replace("\\", "\\\\").replace('"', '\\"')
            path = "search/issues"
            state_filter = " is:open" if request.active_only else ""
            route_filter = (
                f' label:"work-route:{request.route.value}"'
                if request.route is not None
                else ""
            )
            params = {
                "q": (
                    f"repo:{self._repository} is:issue{state_filter}"
                    f"{route_filter} in:body \"{escaped_lookup}\""
                ),
                "per_page": str(request.limit),
                "page": cursor,
            }
            payload, next_cursor = self._transport.get(path, params)
            if not isinstance(payload, dict) or not isinstance(
                payload.get("items"), list
            ):
                raise AdapterError("GitHub search response must contain items")
            records = payload["items"]
            completeness = ResultCompleteness.PARTIAL
            limitations.append(
                "GitHub full-text lookup is candidate retrieval, not exact "
                "or read-after-write-complete matching"
            )
            searched_scope = f"github:{self._repository}:issue-search"
        else:
            path = f"repos/{self._repository}/issues"
            params = {
                "state": "open" if request.active_only else "all",
                "per_page": str(request.limit),
                "page": cursor,
            }
            if request.route is not None:
                params["labels"] = f"work-route:{request.route.value}"
            payload, next_cursor = self._transport.get(path, params)
            if not isinstance(payload, list):
                raise AdapterError("GitHub Issues response must be a list")
            records = payload
            completeness = ResultCompleteness.COMPLETE
            searched_scope = (
                f"github:{self._repository}:"
                f"{'open' if request.active_only else 'all'}-issues"
            )

        normalized = []
        for record in records:
            if not isinstance(record, dict):
                raise AdapterError("GitHub Issue record must be an object")
            if "pull_request" in record:
                continue
            item = self._normalize(record)
            if (
                request.route is not None
                and item.work_route is not request.route
            ):
                raise AdapterError(
                    "GitHub Issue route does not match native route "
                    "predicate"
                )
            normalized.append(item)
        items = tuple(normalized)
        if next_cursor is not None:
            completeness = ResultCompleteness.PARTIAL
            limitations.append("additional provider page is available")
        return QueryResult(
            items=items,
            completeness=completeness,
            searched_scopes=(searched_scope,),
            next_cursor=next_cursor,
            limitations=tuple(limitations),
        )

    def query_page(self, query: AdvancedQuery) -> SearchPage:
        if not isinstance(query, AdvancedQuery):
            raise AdapterError("query must be an AdvancedQuery")
        if (
            self._logical_target is not None
            and query.logical_target != self._logical_target
        ):
            raise AdapterError(
                "query logical target does not match the bound target"
            )
        if query.purpose in {
            QueryPurpose.STALE_REVISION,
            QueryPurpose.DUPLICATE_PREFLIGHT,
        }:
            return self._unsupported_page(
                query,
                "GitHub has no single native request for this query purpose",
            )
        if (
            query.purpose is QueryPurpose.SIMILARITY
            and not self._semantic_search_enabled
        ):
            return self._unsupported_page(
                query,
                "GitHub semantic and hybrid Issue search is not enabled",
            )
        if (
            query.purpose is QueryPurpose.INVENTORY
            and len(query.routes) > 1
        ):
            return self._unsupported_page(
                query,
                "GitHub cannot express multiple alternative work routes "
                "in one native request",
            )
        if WorkRoute.TARGET_NATIVE_INTERNAL in query.routes:
            return self._unsupported_page(
                query,
                "GitHub cannot filter for the absence of a work-route label "
                "through the required native request",
            )
        if query.purpose in {
            QueryPurpose.INVENTORY,
            QueryPurpose.RETURN_INTAKE,
            QueryPurpose.RETURN_CORRELATION,
        }:
            records, next_cursor, incomplete, searched_scope = (
                self._query_repository_issues(query)
            )
            capability = CapabilityStatus.SUPPORTED
            completeness = ResultCompleteness.COMPLETE
            limitations: list[str] = []
        else:
            records, next_cursor, incomplete, searched_scope = (
                self._query_issue_search(query)
            )
            capability = (
                CapabilityStatus.SUPPORTED
                if query.purpose is QueryPurpose.SIMILARITY
                else CapabilityStatus.PARTIAL
            )
            completeness = (
                ResultCompleteness.COMPLETE
                if query.purpose is QueryPurpose.SIMILARITY
                else ResultCompleteness.PARTIAL
            )
            limitations = []
            if query.purpose is not QueryPurpose.SIMILARITY:
                limitations.append(
                    "GitHub full-text lookup is approximate candidate "
                    "retrieval, not exact or read-after-write-complete matching"
                )

        if incomplete:
            completeness = ResultCompleteness.PARTIAL
            limitations.append(
                "GitHub reported incomplete search results"
            )
        if next_cursor is not None:
            completeness = ResultCompleteness.PARTIAL
            limitations.append("additional provider page is available")

        hits = []
        for provider_rank, record in enumerate(records, start=1):
            if not isinstance(record, dict):
                raise AdapterError("GitHub Issue record must be an object")
            if "pull_request" in record:
                continue
            parsed = parse_protocol_block(record.get("body"))
            if (
                parsed.limitation is not None
                and parsed.limitation not in limitations
            ):
                limitations.append(parsed.limitation)
            if (
                query.purpose is QueryPurpose.RETURN_CORRELATION
                and parsed.state is not MetadataState.VERIFIED
            ):
                completeness = ResultCompleteness.PARTIAL
            hits.append(
                SearchHit(
                    item=self._normalize(record),
                    matched_signals=self._matched_signals(
                        query,
                        parsed.state,
                        parsed.metadata,
                    ),
                    provider_rank=provider_rank,
                    metadata_state=parsed.state,
                    protocol_metadata=parsed.metadata,
                    metadata_limitation=parsed.limitation,
                )
            )

        return SearchPage(
            purpose=query.purpose,
            capability=capability,
            completeness=completeness,
            searched_scopes=(searched_scope,),
            hits=tuple(hits),
            next_cursor=next_cursor,
            limitations=tuple(limitations),
            provider_record_count=len(records),
        )

    def _query_repository_issues(
        self,
        query: AdvancedQuery,
    ) -> tuple[list[object], str | None, bool, str]:
        params = {
            "state": "open" if query.active_only else "all",
            "per_page": str(query.limit),
            "page": query.cursor or "1",
        }
        labels = []
        if query.purpose in {
            QueryPurpose.RETURN_INTAKE,
            QueryPurpose.RETURN_CORRELATION,
        }:
            if query.return_kind is not None:
                labels.append(f"return-kind:{query.return_kind.value}")
            labels.append(f"intake-state:{query.intake_state.value}")
        elif query.routes:
            labels.append(f"work-route:{query.routes[0].value}")
        if labels:
            params["labels"] = ",".join(labels)
        payload, next_cursor = self._transport.get(
            f"repos/{self._repository}/issues",
            params,
        )
        if not isinstance(payload, list):
            raise AdapterError("GitHub Issues response must be a list")
        return (
            payload,
            next_cursor,
            False,
            f"github:{self._repository}:repository-issues",
        )

    def _query_issue_search(
        self,
        query: AdvancedQuery,
    ) -> tuple[list[object], str | None, bool, str]:
        qualifiers = [
            f"repo:{self._repository}",
            "is:issue",
        ]
        if query.active_only:
            qualifiers.append("is:open")
        if query.routes:
            route_values = '","'.join(
                f"work-route:{route.value}"
                for route in query.routes
            )
            qualifiers.append(f'label:"{route_values}"')
        if query.purpose is QueryPurpose.SOURCE_TRACEABILITY:
            qualifiers.extend(
                (
                    "in:body",
                    self._quote_search_term(query.source_reference),
                )
            )
        elif query.purpose is QueryPurpose.LOGICAL_TARGET:
            qualifiers.extend(
                (
                    "in:body",
                    self._quote_search_term(query.logical_target),
                )
            )
        elif query.purpose is QueryPurpose.CORRELATION:
            qualifiers.extend(
                (
                    "in:body",
                    self._quote_search_term(query.correlation_id),
                )
            )
        elif query.purpose is QueryPurpose.SIMILARITY:
            qualifiers.extend(
                self._quote_search_term(term)
                for term in (
                    query.capability,
                    query.expected_outcome,
                )
                if term is not None
            )
        else:
            raise AdapterError(
                f"unsupported GitHub query purpose: {query.purpose.value}"
            )
        params = {
            "q": " ".join(qualifiers),
            "per_page": str(query.limit),
            "page": query.cursor or "1",
        }
        if query.purpose is QueryPurpose.SIMILARITY:
            params["advanced_search"] = "true"
            params["search_type"] = query.similarity_mode.value
        payload, next_cursor = self._transport.get(
            "search/issues",
            params,
        )
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("items"), list)
            or not isinstance(payload.get("incomplete_results"), bool)
        ):
            raise AdapterError(
                "GitHub search response must contain items and "
                "incomplete_results"
            )
        return (
            payload["items"],
            next_cursor,
            payload["incomplete_results"],
            f"github:{self._repository}:issue-search",
        )

    @staticmethod
    def _quote_search_term(value: str | None) -> str:
        if value is None:
            raise AdapterError("GitHub search term is missing")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _matched_signals(
        query: AdvancedQuery,
        metadata_state: MetadataState,
        metadata: ProtocolMetadata | None,
    ) -> tuple[str, ...]:
        if metadata_state is not MetadataState.VERIFIED or metadata is None:
            return ()
        if (
            query.purpose is QueryPurpose.SOURCE_TRACEABILITY
            and any(
                relation.target == query.source_reference
                for relation in metadata.relations
            )
        ):
            return ("source-reference",)
        if (
            query.purpose is QueryPurpose.LOGICAL_TARGET
            and metadata.logical_target == query.logical_target
        ):
            return ("logical-target",)
        if (
            query.purpose in {
                QueryPurpose.CORRELATION,
                QueryPurpose.RETURN_CORRELATION,
            }
            and metadata.correlation_id == query.correlation_id
        ):
            return ("correlation-id",)
        return ()

    @staticmethod
    def _unsupported_page(
        query: AdvancedQuery,
        limitation: str,
    ) -> SearchPage:
        return SearchPage(
            purpose=query.purpose,
            capability=CapabilityStatus.UNSUPPORTED,
            completeness=ResultCompleteness.UNSUPPORTED,
            searched_scopes=(),
            limitations=(limitation,),
            provider_record_count=0,
        )

    def get_item(self, provider_id: str) -> Mapping[str, object]:
        if (
            not isinstance(provider_id, str)
            or not provider_id.isdigit()
            or int(provider_id) < 1
        ):
            raise AdapterError(
                "provider_id must be a positive integer string"
            )
        payload, _ = self._transport.get(
            f"repos/{self._repository}/issues/{provider_id}",
            {},
        )
        if not isinstance(payload, dict):
            raise AdapterError("GitHub Issue response must be an object")
        if "pull_request" in payload:
            raise AdapterError(
                "selected GitHub item is a pull request, not an Issue"
            )
        item = self._normalize(payload)
        if item.provider_id != provider_id:
            raise AdapterError(
                "GitHub Issue identity does not match selected provider_id"
            )
        return payload

    def _normalize(self, record: Mapping[str, object]) -> WorkItemSummary:
        try:
            number = record["number"]
        except KeyError as error:
            raise AdapterError(
                f"GitHub Issue is missing {error.args[0]}"
            ) from error
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or number <= 0
        ):
            raise AdapterError(
                "GitHub Issue number must be a positive integer"
            )
        provider_id = str(number)
        title = self._required_issue_string(record, "title")
        updated = self._required_issue_string(record, "updated_at")
        url = self._required_issue_string(record, "html_url")
        expected_url = (
            f"https://github.com/{self._repository}/issues/{provider_id}"
        )
        if url != expected_url:
            raise AdapterError(
                "GitHub Issue URL does not match bound repository and number"
            )
        native_state = self._required_issue_string(record, "state")
        labels = self._label_names(record.get("labels", []))
        item_kind = self._protocol_item_kind(labels)
        try:
            validate_protocol_labels(labels, item_kind=item_kind)
        except ValueError as error:
            raise AdapterError(str(error)) from error
        route = self._route(labels)
        status = self._status(labels, native_state)
        priorities = [
            label.removeprefix("priority:")
            for label in labels
            if label.startswith("priority:")
        ]
        return WorkItemSummary(
            provider_id=provider_id,
            provider_qualified_id=(
                f"github:{self._repository}#{provider_id}"
            ),
            title=title,
            status=status,
            work_route=route,
            updated=updated,
            url=url,
            priority=priorities[0] if priorities else None,
            labels=labels,
        )

    @staticmethod
    def _required_issue_string(
        record: Mapping[str, object],
        field: str,
    ) -> str:
        value = record.get(field)
        if not isinstance(value, str) or not value:
            raise AdapterError(
                f"GitHub Issue {field} must be a non-empty string"
            )
        return value

    @staticmethod
    def _protocol_item_kind(
        labels: tuple[str, ...],
    ) -> ProtocolItemKind | None:
        has_work_route = any(
            label.startswith("work-route:") for label in labels
        )
        has_return = any(
            label.startswith(("return-kind:", "intake-state:"))
            for label in labels
        )
        has_status = any(
            label.startswith("status:") for label in labels
        )
        if has_work_route:
            return ProtocolItemKind.WORK_ITEM
        if has_return:
            return ProtocolItemKind.RETURN_ITEM
        if has_status:
            return ProtocolItemKind.WORK_ITEM
        return None

    @staticmethod
    def _label_names(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise AdapterError("GitHub Issue labels must be a list")
        names = []
        for label in value:
            if isinstance(label, str):
                names.append(label)
            elif isinstance(label, dict) and isinstance(label.get("name"), str):
                names.append(label["name"])
            else:
                raise AdapterError("GitHub Issue label is invalid")
        return tuple(names)

    @staticmethod
    def _route(labels: tuple[str, ...]) -> WorkRoute:
        values = [
            label.removeprefix("work-route:")
            for label in labels
            if label.startswith("work-route:")
        ]
        if len(values) > 1:
            raise AdapterError("GitHub Issue has multiple work-route labels")
        if not values:
            return WorkRoute.TARGET_NATIVE_INTERNAL
        if values[0] == WorkRoute.TARGET_NATIVE_INTERNAL.value:
            raise AdapterError(
                "target-native internal work must omit work-route"
            )
        try:
            return WorkRoute(values[0])
        except ValueError as error:
            raise AdapterError(
                f"unsupported work-route label: {values[0]}"
            ) from error

    @staticmethod
    def _status(labels: tuple[str, ...], native_state: str) -> str:
        values = [
            label.removeprefix("status:")
            for label in labels
            if label.startswith("status:")
        ]
        if len(values) > 1:
            raise AdapterError("GitHub Issue has multiple status labels")
        return values[0] if values else native_state
