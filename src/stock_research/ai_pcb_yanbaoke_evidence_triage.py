from __future__ import annotations


PRIMARY_CLASSIFICATIONS = frozenset(
    {
        "primary_source_lead",
        "contextual_industry",
        "company_evidence_lead",
        "investment_opinion_non_evidence",
    }
)

ER_DISPOSITIONS = frozenset(
    {
        "source_discovery_only",
        "contextual_candidate",
        "not_relevant",
    }
)


def validate_primary_classification(value: str) -> None:
    if value not in PRIMARY_CLASSIFICATIONS:
        raise ValueError(f"unsupported primary classification: {value}")


def validate_er_disposition(value: str) -> None:
    if value not in ER_DISPOSITIONS:
        raise ValueError(f"unsupported ER disposition: {value}")
