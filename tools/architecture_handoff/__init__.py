"""Provider-neutral Architecture-to-OpenSpec handoff foundation."""

from .query_coordinator import (
    CorrelationNode,
    CorrelationView,
    QueryCoordinator,
    StaleRevisionEntry,
    StaleRevisionReport,
    build_correlation_view,
    classify_stale_revisions,
)
from .query_models import (
    AdvancedQuery,
    ContinuationPlan,
    LaneRequirement,
    ProviderCall,
    QueryCoverage,
    QueryPurpose,
    SearchHit,
    SearchPage,
    SimilarityMode,
)

__all__ = (
    "AdvancedQuery",
    "ContinuationPlan",
    "CorrelationNode",
    "CorrelationView",
    "LaneRequirement",
    "ProviderCall",
    "QueryCoverage",
    "QueryCoordinator",
    "QueryPurpose",
    "SearchHit",
    "SearchPage",
    "SimilarityMode",
    "StaleRevisionEntry",
    "StaleRevisionReport",
    "build_correlation_view",
    "classify_stale_revisions",
)
