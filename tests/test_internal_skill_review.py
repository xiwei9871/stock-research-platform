from __future__ import annotations

import json
from pathlib import Path

from stock_research.agents.review import BANNED_TRADING_INSTRUCTIONS
from stock_research.internal_skill_review import run_internal_skill_review


def _write_artifact(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_run_internal_skill_review_writes_review_artifacts(tmp_path):
    topn = _write_artifact(
        tmp_path / "reports" / "topn" / "daily_topn_2026-06-08.md",
        "# Daily TopN\n000001.SZ rank 1\n",
    )
    risk = _write_artifact(
        tmp_path / "reports" / "risk" / "risk_alerts_2026-06-08.md",
        "# Risk Alerts\n000001.SZ concentration risk high\n",
    )
    market = _write_artifact(
        tmp_path / "reports" / "market" / "market_state_2026-06-08.md",
        "# Market State\nCSI300 neutral\n",
    )
    position = _write_artifact(
        tmp_path / "reports" / "position" / "position_review_2026-06-08.md",
        "# Position Review\nNo live position mutation\n",
    )
    run_card = _write_artifact(
        tmp_path / "run_card" / "run_card.json",
        json.dumps({"run_id": "daily-2026-06-08", "status": "ok"}) + "\n",
    )

    result = run_internal_skill_review(
        trade_date="2026-06-08",
        artifact_paths=[topn, risk, market, position, run_card],
        output_dir=tmp_path / "outputs",
    )

    assert result.status == "passed"
    assert result.review_agent_status == "passed"
    assert result.observation_count == 3
    assert Path(result.agent_report_json_path).exists()
    assert Path(result.markdown_path).exists()
    assert Path(result.review_agent_result_path).exists()

    payload = json.loads(Path(result.agent_report_json_path).read_text(encoding="utf-8"))
    assert payload["trade_date"] == "2026-06-08"
    assert {item["agent_role"] for item in payload["observations"]} == {
        "risk",
        "watchlist",
        "review",
    }


def test_run_internal_skill_review_writes_rejected_artifact_when_evidence_missing(tmp_path):
    result = run_internal_skill_review(
        trade_date="2026-06-08",
        artifact_paths=[],
        output_dir=tmp_path / "outputs",
    )

    assert result.status == "rejected"
    assert result.review_agent_status == "rejected"
    assert result.observation_count == 3

    review_payload = json.loads(Path(result.review_agent_result_path).read_text(encoding="utf-8"))
    issue_codes = {issue["code"] for issue in review_payload["issues"]}
    assert "missing_evidence" in issue_codes
    assert "missing_data_facts" not in issue_codes

    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    assert "missing_evidence" in markdown


def test_run_internal_skill_review_writes_internal_debate_review(tmp_path):
    topn = _write_artifact(
        tmp_path / "reports" / "topn" / "daily_topn_2026-06-08.md",
        "# Daily TopN\n000001.SZ rank 1 with strong factor evidence\n",
    )
    risk = _write_artifact(
        tmp_path / "reports" / "risk" / "risk_alerts_2026-06-08.md",
        "# Risk Alerts\n000001.SZ concentration risk high\n",
    )
    market = _write_artifact(
        tmp_path / "reports" / "market" / "market_state_2026-06-08.md",
        "# Market State\nCSI300 neutral\n",
    )
    position = _write_artifact(
        tmp_path / "reports" / "position" / "position_review_2026-06-08.md",
        "# Position Review\nNo live position mutation\n",
    )
    run_card = _write_artifact(
        tmp_path / "run_card" / "run_card.json",
        json.dumps({"run_id": "daily-2026-06-08", "status": "ok"}) + "\n",
    )

    result = run_internal_skill_review(
        trade_date="2026-06-08",
        artifact_paths=[topn, risk, market, position, run_card],
        output_dir=tmp_path / "outputs",
    )

    assert Path(result.debate_review_json_path).exists()
    debate = json.loads(Path(result.debate_review_json_path).read_text(encoding="utf-8"))
    assert debate["trade_date"] == "2026-06-08"
    assert debate["review_only"] is True
    assert debate["source"] == "internal_debate_review_v1"
    assert debate["bull_case"]["role"] == "bull_researcher"
    assert debate["bear_case"]["role"] == "bear_researcher"
    assert debate["risk_manager_review"]["role"] == "risk_manager"
    assert debate["portfolio_review_summary"]["role"] == "portfolio_reviewer"
    assert debate["bull_case"]["cited_evidence_ids"]
    assert debate["bear_case"]["cited_evidence_ids"]
    assert debate["risk_manager_review"]["cited_evidence_ids"]
    assert debate["portfolio_review_summary"]["cited_evidence_ids"]
    assert debate["missing_evidence"] == []
    assert isinstance(debate["operator_questions"], list)

    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    assert "## Internal Debate Review" in markdown
    assert "### Bull Case" in markdown
    assert "### Bear Case" in markdown
    assert "### Risk Manager Review" in markdown
    assert "### Portfolio Review Summary" in markdown

    debate_text = json.dumps(debate, ensure_ascii=False).lower()
    for phrase in BANNED_TRADING_INSTRUCTIONS:
        assert phrase.lower() not in debate_text


def test_run_internal_skill_review_debate_records_missing_evidence(tmp_path):
    result = run_internal_skill_review(
        trade_date="2026-06-08",
        artifact_paths=[],
        output_dir=tmp_path / "outputs",
    )

    debate = json.loads(Path(result.debate_review_json_path).read_text(encoding="utf-8"))
    assert result.status == "rejected"
    assert debate["review_agent_status"] == "rejected"
    assert "no_artifacts_provided" in debate["missing_evidence"]
    assert debate["bear_case"]["notes"]
    assert debate["risk_manager_review"]["notes"]

    markdown = Path(result.markdown_path).read_text(encoding="utf-8")
    assert "## Internal Debate Review" in markdown
    assert "no_artifacts_provided" in markdown
