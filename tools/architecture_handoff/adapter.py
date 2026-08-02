from dataclasses import dataclass
from typing import Mapping, Protocol

from .models import (
    CapabilityStatus,
    QueryResult,
    WorkRoute,
)
from .query_models import AdvancedQuery, SearchPage


@dataclass(frozen=True)
class AdapterBinding:
    provider: str
    provider_scope: str
    logical_target: str

    def __post_init__(self) -> None:
        for field in ("provider", "provider_scope", "logical_target"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")


@dataclass(frozen=True)
class QueryRequest:
    active_only: bool = True
    route: WorkRoute | None = None
    source_reference: str | None = None
    correlation_id: str | None = None
    cursor: str | None = None
    limit: int = 50

    def __post_init__(self):
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        for field in ("source_reference", "correlation_id"):
            value = getattr(self, field)
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(f"{field} must be a non-empty string")
        if self.source_reference is not None and self.correlation_id is not None:
            raise ValueError(
                "source_reference and correlation_id are mutually exclusive"
            )
        if self.cursor is not None and (
            not isinstance(self.cursor, str)
            or not self.cursor.isdigit()
            or int(self.cursor) < 1
        ):
            raise ValueError("cursor must be a positive integer string")


class ReadAdapter(Protocol):
    def capabilities(self) -> Mapping[str, CapabilityStatus]:
        ...

    def list_items(self, request: QueryRequest) -> QueryResult:
        ...

    def get_item(self, provider_id: str) -> Mapping[str, object]:
        ...


class AdvancedReadAdapter(ReadAdapter, Protocol):
    binding: AdapterBinding | None

    def query_page(self, query: AdvancedQuery) -> SearchPage:
        raise NotImplementedError
