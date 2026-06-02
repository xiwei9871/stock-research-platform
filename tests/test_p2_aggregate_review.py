import json
from pathlib import Path

from stock_research.p2.aggregate_review import (
    build_p2_aggregate_review,
    load_aggregate_artifact_payloads,
    write_p2_aggregate_review,
)


def _artifact(path: Path, group: str, name: str, *, required: bool = True) -> dict:
    return {
        "group": group,
        "name": name,
        "path": str(path),
        "required": required,
        "exists": path.exists(),
    }


def test_build_p2_aggregate_review_summarizes_sections_and_manual_review_status(tmp_path):
    delivery_path = tmp_path / "feishu_preview.json"
    delivery_path.write_text(json.dumps({"item_count": 3}), encoding="utf-8")
    agent_path = tmp_path / "agent_report.json"
    agent_path.write_text(
        json.dumps(
            {
                "review": {"status": "passed", "blocker_count": 0},
                "observations": [{}, {}],
            }
        ),
        encoding="utf-8",
    )
    simulation_path = tmp_path / "virtual_portfolio_review.json"
    simulation_path.write_text(
        json.dumps(
            {
                "status": "manual_review_required",
                "risk_summary": {"latest_risk_level": "warning", "max_drawdown": -0.12},
                "advice_summary": {"issue_count": 0, "advice_count": 1},
            }
        ),
        encoding="utf-8",
    )
    factor_path = tmp_path / "factor_validation.json"
    factor_path.write_text(
        json.dumps({"approval": {"status": "approved_candidate"}}),
        encoding="utf-8",
    )
    technical_path = tmp_path / "technical_performance.json"
    technical_path.write_text(
        json.dumps({"gate": {"status": "passed"}}),
        encoding="utf-8",
    )
    watchlist_path = tmp_path / "watchlist.md"
    watchlist_path.write_text("# Watchlist\n", encoding="utf-8")
    rollup = {
        "trade_date": "2026-05-28",
        "run_id": "p2-rollup-2026-05-28",
        "status": "ready",
        "artifacts": [
            _artifact(delivery_path, "delivery", "feishu_preview"),
            _artifact(agent_path, "agent", "agent_report"),
            _artifact(simulation_path, "simulation", "virtual_portfolio"),
            _artifact(factor_path, "factor_validation", "factor_validation"),
            _artifact(technical_path, "technical_performance", "technical_performance"),
            _artifact(watchlist_path, "watchlist", "watchlist_diagnostics", required=False),
        ],
    }

    payloads = load_aggregate_artifact_payloads(rollup)
    review = build_p2_aggregate_review(
        trade_date="2026-05-28",
        rollup=rollup,
        artifact_payloads=payloads,
    )

    assert review["status"] == "review_required"
    assert review["blocker_count"] == 0
    assert [section["group"] for section in review["sections"]] == [
        "delivery",
        "agent",
        "simulation",
        "factor_validation",
        "technical_performance",
        "watchlist",
    ]
    simulation = next(
        section for section in review["sections"] if section["group"] == "simulation"
    )
    assert simulation["status"] == "manual_review_required"
    assert simulation["summary"]["latest_risk_level"] == "warning"


def test_build_p2_aggregate_review_surfaces_missing_required_artifact_as_blocker(tmp_path):
    missing_path = tmp_path / "missing_agent_report.json"
    rollup = {
        "trade_date": "2026-05-28",
        "run_id": "p2-rollup-2026-05-28",
        "status": "blocked",
        "artifacts": [_artifact(missing_path, "agent", "agent_report")],
    }

    review = build_p2_aggregate_review(
        trade_date="2026-05-28",
        rollup=rollup,
        artifact_payloads={},
    )

    assert review["status"] == "blocked"
    assert review["blocker_count"] == 1
    assert review["blockers"][0]["code"] == "missing_required_artifact"
    assert review["sections"][0]["status"] == "missing_required"


def test_write_p2_aggregate_review_outputs_json_and_markdown_with_blockers(tmp_path):
    missing_path = tmp_path / "missing_technical.json"
    rollup = {
        "trade_date": "2026-05-28",
        "run_id": "p2-rollup-2026-05-28",
        "status": "blocked",
        "artifacts": [
            _artifact(missing_path, "technical_performance", "technical_performance")
        ],
    }
    review = build_p2_aggregate_review(
        trade_date="2026-05-28",
        rollup=rollup,
        artifact_payloads={},
    )

    paths = write_p2_aggregate_review(review, output_dir=tmp_path / "out")

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert payload["status"] == "blocked"
    assert "P2 Aggregate Review" in markdown
    assert "Review Blockers" in markdown
    assert "Technical Performance" in markdown
