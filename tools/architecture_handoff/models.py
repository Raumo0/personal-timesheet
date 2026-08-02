from dataclasses import dataclass
from enum import Enum


class WorkRoute(str, Enum):
    ARCHITECTURE_SLICE_HANDOFF = "architecture-slice-handoff"
    IMPLEMENTATION_CONFORMANCE_REFERRAL = "implementation-conformance-referral"
    SPIKE_EVIDENCE = "spike-evidence"
    TARGET_NATIVE_INTERNAL = "target-native-internal"


class ResultCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


class CapabilityStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class WorkItemSummary:
    provider_id: str
    provider_qualified_id: str
    title: str
    status: str
    work_route: WorkRoute
    updated: str
    url: str
    priority: str | None = None
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryResult:
    items: tuple[WorkItemSummary, ...]
    completeness: ResultCompleteness
    searched_scopes: tuple[str, ...]
    next_cursor: str | None = None
    limitations: tuple[str, ...] = ()
