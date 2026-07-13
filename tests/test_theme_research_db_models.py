from __future__ import annotations

import pytest

from stock_research.theme_research_db_models import (
    ThemeResearchDomainError,
    require_admin,
    validate_claim_transition,
    validate_node_transition,
    validate_source_transition,
)


def test_s4_source_cannot_transition_to_accepted() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        validate_source_transition(
            reliability_level="S4",
            from_status="needs_full_text",
            to_status="accepted",
        )

    assert exc_info.value.code == "S4_SOURCE_CANNOT_BE_ACCEPTED"


def test_source_transition_must_follow_state_machine() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        validate_source_transition(
            reliability_level="S1",
            from_status="unknown",
            to_status="accepted",
        )

    assert exc_info.value.code == "INVALID_SOURCE_REVIEW_TRANSITION"
    assert exc_info.value.details == {"from_status": "unknown", "to_status": "accepted"}


def test_valid_source_transition_returns_target_status() -> None:
    assert (
        validate_source_transition(
            reliability_level="S1",
            from_status="needs_full_text",
            to_status="accepted",
        )
        == "accepted"
    )


def test_reviewed_claim_requires_accepted_non_s4_source() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        validate_claim_transition(
            from_status="draft",
            to_status="reviewed",
            evidence_sources=[{"review_status": "lead_only", "reliability_level": "S4"}],
        )

    assert exc_info.value.code == "REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE"


def test_reviewed_claim_rejects_rejected_supporting_source() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        validate_claim_transition(
            from_status="draft",
            to_status="reviewed",
            evidence_sources=[
                {"review_status": "accepted", "reliability_level": "S1"},
                {"review_status": "rejected", "reliability_level": "S2"},
            ],
        )

    assert exc_info.value.code == "REVIEWED_CLAIM_USES_REJECTED_SOURCE"


def test_valid_reviewed_claim_transition() -> None:
    assert (
        validate_claim_transition(
            from_status="draft",
            to_status="reviewed",
            evidence_sources=[{"review_status": "accepted", "reliability_level": "S1"}],
        )
        == "reviewed"
    )


def test_claim_transition_must_follow_state_machine() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        validate_claim_transition(
            from_status="research_lead",
            to_status="reviewed",
            evidence_sources=[{"review_status": "accepted", "reliability_level": "S1"}],
        )

    assert exc_info.value.code == "INVALID_CLAIM_REVIEW_TRANSITION"


def test_node_review_requires_evidence_strength_three() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        validate_node_transition(
            from_status="needs_evidence",
            to_status="reviewed",
            evidence_strength=2,
        )

    assert exc_info.value.code == "REVIEWED_NODE_REQUIRES_STRONG_EVIDENCE"


def test_valid_node_review_transition() -> None:
    assert (
        validate_node_transition(
            from_status="needs_evidence",
            to_status="reviewed",
            evidence_strength=3,
        )
        == "reviewed"
    )


def test_admin_operation_rejects_user_role() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        require_admin("user")

    assert exc_info.value.code == "THEME_RESEARCH_ADMIN_REQUIRED"


def test_admin_operation_accepts_admin_role() -> None:
    require_admin("admin")

