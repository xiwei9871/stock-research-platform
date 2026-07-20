from __future__ import annotations

from stock_research.research_project_v2_1.diff import diff_industry_versions
from stock_research.research_project_v2_1.loader import load_industry_version


PROJECT = "ai_compute_pcb_industry_bottleneck"


def test_ai_pcb_v0_2_0_is_an_immutable_industry_design_snapshot() -> None:
    version = load_industry_version(PROJECT, "0.2.0")
    snapshot = version["snapshot"]

    assert version["schema_version"] == "2.2.0"
    assert version["parent_version_id"] == f"research_version:{PROJECT}:0.1.0"
    assert version["creation_stage"] == "research_design"
    assert version["incorporated_event_ids"] == []
    assert len(snapshot["questions"]) == 27
    assert len(snapshot["bottleneck_hypotheses"]) == 8
    assert len(snapshot["industry_model_nodes"]) == 7
    assert len(snapshot["validation_metrics"]) >= 9
    assert len(snapshot["invalidation_conditions"]) >= 8
    assert any(
        requirement["open_discovery"]
        and requirement["lifecycle_status"] == "active"
        for requirement in snapshot["evidence_requirements"]
    )
    assert snapshot["industry_evidence_assessments"] == []
    assert snapshot["conclusion_status"] == "unavailable"
    assert snapshot["investment_status"] == "not_assessed"


def test_ai_pcb_v0_1_to_v0_2_diff_reports_r2b_design_objects() -> None:
    before = load_industry_version(PROJECT, "0.1.0")
    after = load_industry_version(PROJECT, "0.2.0")

    result = diff_industry_versions(before, after)

    assert len(result["changes"]["industry_model_nodes"]["added"]) == 7
    assert len(result["changes"]["bottleneck_hypotheses"]["added"]) == 8
    assert result["changes"]["industry_evidence_assessments"]["added"] == []
