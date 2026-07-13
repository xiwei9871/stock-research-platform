from __future__ import annotations

from typing import Any

from stock_research.theme_decomposition import (
    CLAIM_PLATFORM_USE_STATUSES,
    NODE_REVIEW_STATUSES,
    RELIABILITY_LEVELS,
    SOURCE_REVIEW_STATUSES,
)


SOURCE_TRANSITIONS = {
    "unknown": {"needs_full_text", "lead_only", "rejected"},
    "needs_full_text": {"accepted", "lead_only", "rejected"},
    "lead_only": {"needs_full_text", "rejected"},
    "accepted": {"needs_full_text", "rejected"},
    "rejected": {"needs_full_text"},
}

CLAIM_TRANSITIONS = {
    "research_lead": {"draft", "blocked"},
    "draft": {"research_lead", "reviewed", "blocked"},
    "reviewed": {"draft", "blocked"},
    "blocked": {"research_lead", "draft"},
}

NODE_TRANSITIONS = {
    "draft": {"needs_evidence", "reviewed", "blocked"},
    "needs_evidence": {"draft", "reviewed", "blocked"},
    "reviewed": {"draft", "needs_evidence", "blocked"},
    "blocked": {"draft", "needs_evidence"},
}


class ThemeResearchDomainError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def validate_source_transition(
    *,
    reliability_level: str,
    from_status: str,
    to_status: str,
) -> str:
    _require_enum(
        reliability_level,
        RELIABILITY_LEVELS,
        field="reliability_level",
        code="INVALID_SOURCE_RELIABILITY_LEVEL",
    )
    _require_enum(
        from_status,
        SOURCE_REVIEW_STATUSES,
        field="from_status",
        code="INVALID_SOURCE_REVIEW_STATUS",
    )
    _require_enum(
        to_status,
        SOURCE_REVIEW_STATUSES,
        field="to_status",
        code="INVALID_SOURCE_REVIEW_STATUS",
    )
    _require_transition(
        from_status,
        to_status,
        SOURCE_TRANSITIONS,
        code="INVALID_SOURCE_REVIEW_TRANSITION",
    )
    if reliability_level == "S4" and to_status == "accepted":
        raise ThemeResearchDomainError(
            "S4 source cannot be accepted",
            code="S4_SOURCE_CANNOT_BE_ACCEPTED",
            details={"reliability_level": reliability_level, "to_status": to_status},
        )
    return to_status


def validate_claim_transition(
    *,
    from_status: str,
    to_status: str,
    evidence_sources: list[dict[str, Any]],
) -> str:
    _require_enum(
        from_status,
        CLAIM_PLATFORM_USE_STATUSES,
        field="from_status",
        code="INVALID_CLAIM_REVIEW_STATUS",
    )
    _require_enum(
        to_status,
        CLAIM_PLATFORM_USE_STATUSES,
        field="to_status",
        code="INVALID_CLAIM_REVIEW_STATUS",
    )
    _require_transition(
        from_status,
        to_status,
        CLAIM_TRANSITIONS,
        code="INVALID_CLAIM_REVIEW_TRANSITION",
    )
    if to_status != "reviewed":
        return to_status
    if any(source.get("review_status") == "rejected" for source in evidence_sources):
        raise ThemeResearchDomainError(
            "reviewed claim cannot use rejected source",
            code="REVIEWED_CLAIM_USES_REJECTED_SOURCE",
        )
    accepted_sources = [
        source
        for source in evidence_sources
        if source.get("review_status") == "accepted"
        and source.get("reliability_level") != "S4"
    ]
    if not accepted_sources:
        raise ThemeResearchDomainError(
            "reviewed claim requires accepted non-S4 source",
            code="REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE",
        )
    return to_status


def validate_node_transition(
    *,
    from_status: str,
    to_status: str,
    evidence_strength: int,
) -> str:
    _require_enum(
        from_status,
        NODE_REVIEW_STATUSES,
        field="from_status",
        code="INVALID_NODE_REVIEW_STATUS",
    )
    _require_enum(
        to_status,
        NODE_REVIEW_STATUSES,
        field="to_status",
        code="INVALID_NODE_REVIEW_STATUS",
    )
    _require_transition(
        from_status,
        to_status,
        NODE_TRANSITIONS,
        code="INVALID_NODE_REVIEW_TRANSITION",
    )
    if to_status == "reviewed" and evidence_strength < 3:
        raise ThemeResearchDomainError(
            "reviewed node requires evidence_strength >= 3",
            code="REVIEWED_NODE_REQUIRES_STRONG_EVIDENCE",
            details={"evidence_strength": evidence_strength},
        )
    return to_status


def require_admin(role: str) -> None:
    if role != "admin":
        raise ThemeResearchDomainError(
            "administrator role is required",
            code="THEME_RESEARCH_ADMIN_REQUIRED",
            details={"role": role},
        )


def require_comment(comment: str) -> str:
    normalized = str(comment or "").strip()
    if not normalized:
        raise ThemeResearchDomainError(
            "review comment is required",
            code="THEME_RESEARCH_COMMENT_REQUIRED",
        )
    return normalized


def _require_enum(value: str, allowed: set[str], *, field: str, code: str) -> None:
    if value not in allowed:
        raise ThemeResearchDomainError(
            f"{field} is invalid: {value}",
            code=code,
            details={field: value},
        )


def _require_transition(
    from_status: str,
    to_status: str,
    transitions: dict[str, set[str]],
    *,
    code: str,
) -> None:
    if to_status not in transitions[from_status]:
        raise ThemeResearchDomainError(
            f"invalid transition: {from_status} -> {to_status}",
            code=code,
            details={"from_status": from_status, "to_status": to_status},
        )

