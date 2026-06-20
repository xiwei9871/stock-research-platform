import json
from pathlib import Path

from stock_research.reports.daily_review_contract import ACTION_VALUES, REVIEW_PRIORITY_VALUES
from stock_research.reports.daily_review_report_workflow import build_daily_review, write_daily_review_package


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "daily_review_v1"


def _read_json(name: str):
    return json.loads((FIXTURE_ROOT / "source_payloads" / name).read_text(encoding="utf-8"))


def test_build_daily_review_matches_golden_fixture():
    result = build_daily_review(
        trade_date="2026-06-20",
        run_id="daily_review_v1_20260620_2200",
        data_readiness=_read_json("data_readiness.json"),
        market_review=_read_json("market_review.json"),
        lhb_review=_read_json("lhb_review.json"),
        mid_trend_review=_read_json("mid_trend_review.json"),
        technical_bottleneck_review=_read_json("technical_bottleneck_review.json"),
        holding_reviews=_read_json("holding_reviews.json"),
    )

    expected = json.loads((FIXTURE_ROOT / "expected_daily_review.json").read_text(encoding="utf-8"))

    assert result["trade_date"] == expected["trade_date"]
    assert result["report_type"] == expected["report_type"]
    assert result["schema_version"] == expected["schema_version"]
    assert result["status"] == expected["status"]
    assert result["warnings"] == expected["warnings"]


def test_build_daily_review_keeps_same_asset_under_multiple_strategies():
    result = build_daily_review(
        trade_date="2026-06-20",
        run_id="daily_review_v1_20260620_2200",
        data_readiness=_read_json("data_readiness.json"),
        market_review=_read_json("market_review.json"),
        lhb_review=_read_json("lhb_review.json"),
        mid_trend_review=_read_json("mid_trend_review.json"),
        technical_bottleneck_review=_read_json("technical_bottleneck_review.json"),
        holding_reviews=_read_json("holding_reviews.json"),
    )

    matching = [row for row in result["holding_reviews"] if row["asset_id"] == "CN:SH:600000"]
    assert len(matching) == 2
    assert {row["strategy_id"] for row in matching} == {"lhb", "mid_trend"}


def test_write_daily_review_package_writes_golden_markdown(tmp_path):
    result = build_daily_review(
        trade_date="2026-06-20",
        run_id="daily_review_v1_20260620_2200",
        data_readiness=_read_json("data_readiness.json"),
        market_review=_read_json("market_review.json"),
        lhb_review=_read_json("lhb_review.json"),
        mid_trend_review=_read_json("mid_trend_review.json"),
        technical_bottleneck_review=_read_json("technical_bottleneck_review.json"),
        holding_reviews=_read_json("holding_reviews.json"),
    )

    paths = write_daily_review_package(result, output_root=tmp_path)
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    expected_prefix = (FIXTURE_ROOT / "expected_daily_review.md").read_text(encoding="utf-8").strip()

    assert markdown.startswith(expected_prefix)


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
