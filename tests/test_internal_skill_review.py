from __future__ import annotations

import json
from pathlib import Path

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
