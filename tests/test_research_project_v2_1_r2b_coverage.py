from __future__ import annotations

from stock_research.research_project_v2_1.coverage import summarize_evidence_coverage


def test_coverage_summary_reports_requirements_sources_failures_and_bottlenecks() -> None:
    version = {
        "project_id": "research_project:fixture",
        "semantic_version": "0.2.1",
        "snapshot": {
            "evidence_requirements": [
                {
                    "requirement_id": "requirement:one",
                    "primary_source_required": True,
                    "collection_status": "covered",
                    "satisfaction_status": "satisfied",
                },
                {
                    "requirement_id": "requirement:two",
                    "primary_source_required": True,
                    "collection_status": "blocked",
                    "satisfaction_status": "blocked",
                },
            ],
            "source_candidates": [
                {
                    "candidate_id": "candidate:one",
                    "acquisition_status": "acquired",
                    "source_class": "technical_standard",
                },
                {
                    "candidate_id": "candidate:two",
                    "acquisition_status": "paywalled",
                    "source_class": "market_data",
                    "failure_reason": "subscription required",
                },
            ],
            "source_relationships": [],
            "industry_evidence_assessments": [
                {
                    "assessment_id": "assessment:one",
                    "requirement_id": "requirement:one",
                    "target_type": "bottleneck_hypothesis",
                    "target_id": "bottleneck:one",
                    "evidence_stance": "supports",
                    "evidence_functions": ["mechanism", "supply"],
                    "strength": "high",
                    "independence": "primary_source",
                    "review_status": "reviewed",
                }
            ],
            "bottleneck_hypotheses": [
                {
                    "bottleneck_hypothesis_id": "bottleneck:one",
                    "evidence_requirement_ids": ["requirement:one"],
                }
            ],
        },
    }

    result = summarize_evidence_coverage(version)

    assert result["requirements"]["total"] == 2
    assert result["requirements"]["blocked"] == ["requirement:two"]
    assert result["primary_source_coverage"]["reviewed_assessment_count"] == 1
    assert result["acquisition_status"]["paywalled"] == 1
    assert result["inaccessible_evidence"][0]["failure_reason"] == "subscription required"
    assert result["evidence_quality_distribution"] == {"high": 1}
    assert result["bottleneck_coverage"]["bottleneck:one"]["assessment_count"] == 1
