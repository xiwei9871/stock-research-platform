from __future__ import annotations

ACTION_VALUES = {
    "no_action",
    "manual_review",
    "watch",
    "add_candidate",
    "hold",
    "warning",
    "reduce_review",
    "exit_review",
    "forbidden",
    "research_required",
}

REVIEW_PRIORITY_VALUES = {"P0", "P1", "P2", "P3"}


def normalize_action(value: object, default: str = "manual_review") -> str:
    normalized_default = _normalize_action_like(default)
    candidate = _normalize_action_like(value)
    if candidate in ACTION_VALUES:
        return candidate
    return normalized_default if normalized_default in ACTION_VALUES else "manual_review"


def normalize_review_priority(value: object, default: str = "P2") -> str:
    normalized_default = _normalize_priority_like(default)
    candidate = _normalize_priority_like(value)
    if candidate in REVIEW_PRIORITY_VALUES:
        return candidate
    return normalized_default if normalized_default in REVIEW_PRIORITY_VALUES else "P2"


def _normalize_action_like(value: object) -> str:
    return str(value or "").strip().lower()


def _normalize_priority_like(value: object) -> str:
    return str(value or "").strip().upper()
