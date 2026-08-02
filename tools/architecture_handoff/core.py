from dataclasses import dataclass
from typing import Mapping

from .models import QueryResult, ResultCompleteness, WorkRoute


CATEGORY_HINTS = {
    WorkRoute.ARCHITECTURE_SLICE_HANDOFF: (
        "Implements one bounded outcome from accepted product or architecture "
        "sources through the OpenSpec workflow."
    ),
    WorkRoute.IMPLEMENTATION_CONFORMANCE_REFERRAL: (
        "Corrects a target that conflicts with an accepted source or earlier "
        "Brief without introducing new product or architecture meaning."
    ),
    WorkRoute.SPIKE_EVIDENCE: (
        "Answers one bounded question and returns durable Evidence before "
        "dependent work continues."
    ),
    WorkRoute.TARGET_NATIVE_INTERNAL: (
        "Covers work owned and managed by the target under its local workflow."
    ),
}


@dataclass(frozen=True)
class TaskInventory:
    counts: Mapping[WorkRoute, int]
    completeness: ResultCompleteness
    next_cursor: str | None
    limitations: tuple[str, ...]


def build_inventory(result: QueryResult) -> TaskInventory:
    counts = {route: 0 for route in WorkRoute}
    for item in result.items:
        counts[item.work_route] += 1
    return TaskInventory(
        counts=counts,
        completeness=result.completeness,
        next_cursor=result.next_cursor,
        limitations=result.limitations,
    )
