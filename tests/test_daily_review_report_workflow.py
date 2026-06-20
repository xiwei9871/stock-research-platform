import json
from pathlib import Path

from stock_research.reports.daily_review_contract import (
    ACTION_VALUES,
    REVIEW_PRIORITY_VALUES,
    normalize_action,
    normalize_review_priority,
)
from stock_research.reports.daily_review_report_workflow import build_daily_review, write_daily_review_package


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "daily_review_v1"


def _read_json(name: str):
    return json.loads((FIXTURE_ROOT / "source_payloads" / name).read_text(encoding="utf-8"))


def _build_fixture_review(**overrides):
    payloads = {
        "trade_date": "2026-06-20",
        "run_id": "daily_review_v1_20260620_2200",
        "data_readiness": _read_json("data_readiness.json"),
        "market_review": _read_json("market_review.json"),
        "lhb_review": _read_json("lhb_review.json"),
        "mid_trend_review": _read_json("mid_trend_review.json"),
        "technical_bottleneck_review": _read_json("technical_bottleneck_review.json"),
        "holding_reviews": _read_json("holding_reviews.json"),
    }
    payloads.update(overrides)
    return build_daily_review(**payloads)


def test_build_daily_review_matches_golden_fixture():
    result = _build_fixture_review()
    expected = json.loads((FIXTURE_ROOT / "expected_daily_review.json").read_text(encoding="utf-8"))
    assert result == expected


def test_build_daily_review_keeps_same_asset_under_multiple_strategies():
    result = _build_fixture_review()
    matching = [row for row in result["holding_reviews"] if row["asset_id"] == "CN:SH:600000"]
    assert len(matching) == 2
    assert {row["strategy_id"] for row in matching} == {"lhb", "mid_trend"}


def test_write_daily_review_package_matches_contract_files(tmp_path):
    result = _build_fixture_review()
    expected_review = json.loads((FIXTURE_ROOT / "expected_daily_review.json").read_text(encoding="utf-8"))
    expected_markdown = (FIXTURE_ROOT / "expected_daily_review.md").read_text(encoding="utf-8")

    paths = write_daily_review_package(result, output_root=tmp_path)
    assert json.loads(Path(paths["json_path"]).read_text(encoding="utf-8")) == {
        **expected_review,
        "report_paths": paths,
    }
    assert Path(paths["markdown_path"]).read_text(encoding="utf-8") == expected_markdown
    assert json.loads(Path(paths["manifest_path"]).read_text(encoding="utf-8")) == {
        "trade_date": "2026-06-20",
        "run_id": "daily_review_v1_20260620_2200",
        "report_type": "daily_review_v1",
        "schema_version": "daily_review_v1",
        "status": "partial",
        "warnings": ["source_missing:lhb_feed"],
        "report_paths": paths,
        "data_readiness": _read_json("data_readiness.json"),
    }
    assert json.loads(Path(paths["operator_plan_template_path"]).read_text(encoding="utf-8")) == {
        "trade_date": "2026-06-20",
        "created_from_run_id": "daily_review_v1_20260620_2200",
        "decision_status": "pending",
        "operator_id": "",
        "overall_position_bias": "defensive",
        "must_check_before_open": ["CN:SH:600000"],
        "forbidden_actions": ["chase stale LHB names"],
        "manual_decisions": [],
    }

    evidence_paths = paths["evidence_paths"]
    assert json.loads(Path(evidence_paths["market_state"]).read_text(encoding="utf-8")) == _read_json("market_review.json")
    assert json.loads(Path(evidence_paths["lhb_review"]).read_text(encoding="utf-8")) == _read_json("lhb_review.json")
    assert json.loads(Path(evidence_paths["mid_trend_review"]).read_text(encoding="utf-8")) == _read_json("mid_trend_review.json")
    assert json.loads(Path(evidence_paths["technical_bottleneck_review"]).read_text(encoding="utf-8")) == _read_json("technical_bottleneck_review.json")


def test_action_and_priority_sets_are_stable():
    assert ACTION_VALUES == {
        "no_action",
        "manual_review",
        "watch",
        "add_candidate",
        "hold",
        "warning",
        "reduce_review",
        "exit_review",
        "forbidden",
        "research_required",
    }
    assert REVIEW_PRIORITY_VALUES == {"P0", "P1", "P2", "P3"}


def test_normalize_helpers_use_controlled_defaults():
    assert normalize_action("hold") == "hold"
    assert normalize_action("unexpected") == "manual_review"
    assert normalize_review_priority("P0") == "P0"
    assert normalize_review_priority("unexpected") == "P2"


def test_build_daily_review_normalizes_holding_actions():
    holding_reviews = _read_json("holding_reviews.json")
    holding_reviews[0]["action"] = "unexpected"

    result = _build_fixture_review(holding_reviews=holding_reviews)

    assert result["holding_reviews"][0]["action"] == "manual_review"


def test_build_daily_review_includes_non_lhb_p0_items_in_operator_plan():
    result = _build_fixture_review(
        lhb_review={"forbidden_actions": []},
        mid_trend_review={
            "portfolio_health": "stable",
            "rebalance_suggestion": "add selectively",
            "topn_relation": "aligned",
            "candidate_adds": [
                {
                    "asset_id": "CN:SZ:000001",
                    "ts_code": "000001.SZ",
                    "stock_name": "平安银行",
                    "bucket": "core_watch",
                    "state": "watch",
                    "action": "add_candidate",
                    "review_priority": "P0",
                    "reason": {"setup": "fresh mid-trend breakout"},
                    "source_refs": ["mid_trend_signal"],
                }
            ],
        },
    )

    assert result["operator_plan"]["must_check_before_open"] == ["CN:SZ:000001"]


def test_build_daily_review_marks_empty_readiness_as_partial():
    result = _build_fixture_review(data_readiness={})

    assert result["status"] == "partial"


def test_write_daily_review_package_keeps_evidence_payloads_faithful(tmp_path):
    lhb_review = _read_json("lhb_review.json")
    lhb_review["lhb_watchlist"][0]["action"] = "unexpected_nested_action"
    lhb_review["lhb_watchlist"][0]["review_priority"] = "bad_priority"
    technical_review = _read_json("technical_bottleneck_review.json")
    technical_review["upgraded_items"][0]["action"] = "unexpected_nested_action"

    result = _build_fixture_review(
        lhb_review=lhb_review,
        technical_bottleneck_review=technical_review,
    )
    paths = write_daily_review_package(result, output_root=tmp_path)

    assert result["strategy_items"][0]["action"] == "manual_review"
    assert result["strategy_items"][0]["review_priority"] == "P2"
    assert result["strategy_items"][1]["action"] == "watch"

    evidence_paths = paths["evidence_paths"]
    assert json.loads(Path(evidence_paths["lhb_review"]).read_text(encoding="utf-8")) == lhb_review
    assert json.loads(Path(evidence_paths["technical_bottleneck_review"]).read_text(encoding="utf-8")) == technical_review


def test_write_daily_review_package_records_report_run(tmp_path, monkeypatch):
    result = _build_fixture_review()
    recorded: dict[str, object] = {}

    def _fake_record_report_run(**kwargs):
        recorded.update(kwargs)
        return "stored-run-id"

    monkeypatch.setattr(
        "stock_research.reports.daily_review_report_workflow.record_report_run",
        _fake_record_report_run,
    )

    paths = write_daily_review_package(result, output_root=tmp_path, record_run=True)

    assert recorded["trade_date"] == "2026-06-20"
    assert recorded["report_type"] == "daily_review_v1"
    assert recorded["status"] == result["status"]
    assert recorded["report_paths"] == paths
    assert recorded["metadata"]["schema_version"] == "daily_review_v1"
    assert "warnings" in recorded["metadata"]
