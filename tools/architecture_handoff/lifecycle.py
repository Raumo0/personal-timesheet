BRIEF_TRANSITIONS = {
    "draft": {"backlog", "ready", "cancelled"},
    "backlog": {"ready", "cancelled"},
    "ready": {"in-progress", "backlog", "cancelled"},
    "in-progress": {"in-review", "backlog", "cancelled"},
    "in-review": {"done", "backlog", "cancelled"},
    "done": set(),
    "cancelled": set(),
}


def validate_brief_transition(before: str, after: str) -> None:
    if (
        before not in BRIEF_TRANSITIONS
        or after not in BRIEF_TRANSITIONS[before]
    ):
        raise ValueError(
            f"invalid Brief lifecycle transition: {before} -> {after}"
        )
