import pytest

from stock_research.agents.contracts import (
    AgentObservation,
    AgentReport,
    EvidenceReference,
    list_agent_role_specs,
    validate_agent_report,
)


def test_agent_report_allows_only_research_decision_labels():
    report = AgentReport(
        trade_date="2026-05-28",
        mode="topn",
        observations=[
            AgentObservation(
                agent_role="watchlist",
                subject="000001.SZ",
                decision_label="must_buy",
                data_facts=["score rank is 1"],
                factor_results=[],
                backtest_findings=[],
                agent_reasoning=["momentum looks strong"],
                unverified_hypotheses=["news catalyst not checked"],
                evidence=[
                    EvidenceReference(
                        artifact_id="topn:000001",
                        evidence_type="report_artifact",
                        path="outputs/topn.json",
                        summary="TopN score artifact",
                    )
                ],
            )
        ],
    )

    issues = validate_agent_report(report)

    assert [issue.code for issue in issues] == ["invalid_decision_label"]
    assert issues[0].severity == "blocker"


def test_agent_report_requires_evidence_for_each_observation():
    report = AgentReport(
        trade_date="2026-05-28",
        mode="watchlist",
        observations=[
            AgentObservation(
                agent_role="risk",
                subject="000002.SZ",
                decision_label="谨慎",
                data_facts=["risk alert severity is high"],
                factor_results=[],
                backtest_findings=[],
                agent_reasoning=["risk should be reviewed before adding"],
                unverified_hypotheses=[],
                evidence=[],
            )
        ],
    )

    issues = validate_agent_report(report)

    assert [issue.code for issue in issues] == ["missing_evidence"]


def test_agent_report_serializes_layered_research_output():
    report = AgentReport(
        trade_date="2026-05-28",
        mode="topn",
        observations=[
            AgentObservation(
                agent_role="factor_research",
                subject="TopN Daily Score",
                decision_label="候选",
                data_facts=["artifact severity is info"],
                factor_results=["score summary is present"],
                backtest_findings=["run card available"],
                agent_reasoning=["candidate needs human review"],
                unverified_hypotheses=["intraday liquidity not checked"],
                evidence=[
                    EvidenceReference(
                        artifact_id="run_card:daily",
                        evidence_type="run_card",
                        path="outputs/run_card.json",
                        summary="Daily research run card",
                    )
                ],
            )
        ],
    )

    payload = report.to_dict()

    assert payload["trade_date"] == "2026-05-28"
    assert payload["observations"][0]["decision_label"] == "候选"
    assert payload["observations"][0]["evidence"][0]["artifact_id"] == "run_card:daily"


def test_agent_role_catalog_covers_p1_roles_and_blocks_auto_trade():
    specs = list_agent_role_specs()

    assert set(specs) == {
        "data_quality",
        "factor_research",
        "backtest",
        "watchlist",
        "risk",
        "review",
    }
    assert all(spec.requires_evidence for spec in specs.values())
    assert all(not spec.allows_auto_trade for spec in specs.values())
