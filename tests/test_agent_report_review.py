import json
from pathlib import Path

from stock_research.agents.contracts import AgentObservation, AgentReport, EvidenceReference
from stock_research.agents.review import ReviewAgent
from stock_research.reports.agent_research_report import build_agent_research_report


def test_review_agent_blocks_trading_instructions_even_with_evidence():
    report = AgentReport(
        trade_date="2026-05-28",
        mode="watchlist",
        observations=[
            AgentObservation(
                agent_role="watchlist",
                subject="000001.SZ",
                decision_label="候选",
                data_facts=["must watch flag is true"],
                factor_results=["score is 9.1"],
                backtest_findings=[],
                agent_reasoning=["必须买入，不能错过"],
                unverified_hypotheses=[],
                evidence=[
                    EvidenceReference(
                        artifact_id="watchlist:000001",
                        evidence_type="report_artifact",
                        path="outputs/watchlist.json",
                        summary="Watchlist report",
                    )
                ],
            )
        ],
    )

    result = ReviewAgent().review(report)

    assert result.status == "rejected"
    assert "banned_trading_instruction" in [issue.code for issue in result.issues]


def test_review_agent_passes_layered_evidence_backed_report():
    report = AgentReport(
        trade_date="2026-05-28",
        mode="topn",
        observations=[
            AgentObservation(
                agent_role="backtest",
                subject="TopN retention",
                decision_label="观察",
                data_facts=["local report artifact exists"],
                factor_results=["score source is approved factors"],
                backtest_findings=["retention report included"],
                agent_reasoning=["observe until sample-out validation improves"],
                unverified_hypotheses=["next-day execution slippage not checked"],
                evidence=[
                    EvidenceReference(
                        artifact_id="run_card:topn",
                        evidence_type="run_card",
                        path="outputs/run_card.json",
                        summary="TopN run card",
                    )
                ],
            )
        ],
    )

    result = ReviewAgent().review(report)

    assert result.status == "passed"
    assert result.blocker_count == 0


def test_agent_research_report_builds_reviewed_markdown_and_json_from_delivery_manifest(tmp_path):
    artifact_json = tmp_path / "topn_report.json"
    artifact_json.write_text(
        json.dumps({"summary": "TopN candidates generated", "severity": "info"}),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "trade_date": "2026-05-28",
                "artifacts": [
                    {
                        "artifact_id": "topn:2026-05-28",
                        "report_type": "daily_topn_report",
                        "title": "Daily TopN",
                        "severity": "info",
                        "summary": "TopN candidates generated",
                        "json_path": str(artifact_json),
                        "markdown_path": None,
                        "csv_paths": [],
                        "run_card_path": None,
                        "evidence_dir": None,
                        "warnings": [],
                        "metadata": {"source_kind": "report"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = build_agent_research_report(
        trade_date="2026-05-28",
        mode="topn",
        manifest_path=manifest_path,
        output_dir=tmp_path / "agent",
    )

    payload = json.loads(Path(result.json_path).read_text(encoding="utf-8"))
    markdown = Path(result.markdown_path).read_text(encoding="utf-8")

    assert result.review_status == "passed"
    assert payload["review"]["status"] == "passed"
    assert payload["observations"][0]["evidence"][0]["artifact_id"] == "topn:2026-05-28"
    assert "## 数据事实" in markdown
    assert "## AI 推理" in markdown
    assert "topn:2026-05-28" in markdown
