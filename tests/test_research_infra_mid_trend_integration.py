from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.research_infra.experiment_registry import read_experiment_registry
from stock_research.research_infra.mid_trend_integration import (
    build_mid_trend_review_with_research_infra,
    write_mid_trend_research_infra_artifacts,
)


def _toy_review_result(tmp_path: Path) -> dict:
    review_csv = tmp_path / "mid_trend_portfolio_review_2026-06-04.csv"
    review_md = tmp_path / "mid_trend_portfolio_review_2026-06-04.md"
    review_csv.write_text(
        "asset_id,final_label\nCN:SH:600183,高优先级持有\n",
        encoding="utf-8",
    )
    review_md.write_text("# Mid Trend Review\n", encoding="utf-8")
    return {
        "portfolio_summary": {
            "trade_date": "2026-06-04",
            "strategy_variant": "top5_weekly_max_2_replacements",
            "review_count": 2,
        },
        "review_rows": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:600183",
                    "ts_code": "600183.SH",
                    "trade_date": "2026-06-04",
                    "stock_name": "A",
                    "section": "top5",
                    "final_label": "高优先级持有",
                    "research_support_score_pit": 33,
                    "broker_report_count_90d": 3,
                    "pdf_risk_section_count_90d": 3,
                    "market_regime": "mainline",
                    "mainline_status": "sustained_mainline",
                    "why_hold_or_change": "高支持度且为核心持仓，继续持有。",
                },
                {
                    "asset_id": "CN:SZ:300201",
                    "ts_code": "300201.SZ",
                    "trade_date": "2026-06-04",
                    "stock_name": "B",
                    "section": "top5",
                    "final_label": "低优先级持有",
                    "research_support_score_pit": 0,
                    "broker_report_count_90d": 0,
                    "pdf_risk_section_count_90d": 0,
                    "market_regime": "mainline",
                    "mainline_status": "neutral",
                    "why_hold_or_change": "",
                },
            ]
        ),
        "markdown": "# Mid Trend Review\n",
        "paths": {"csv": str(review_csv), "md": str(review_md), "report": str(review_md)},
    }


def test_write_mid_trend_research_infra_artifacts_writes_sidecars(
    tmp_path: Path,
) -> None:
    result = write_mid_trend_research_infra_artifacts(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_result=_toy_review_result(tmp_path),
        output_dir=tmp_path,
    )

    sidecar_dir = tmp_path / "research_infra"
    assert Path(result["research_signals_json_path"]).exists()
    assert Path(result["attribution_cards_json_path"]).exists()
    assert Path(result["attribution_cards_md_path"]).exists()
    assert Path(result["experiment_registry_path"]).exists()
    assert Path(result["run_card"]["run_card_json_path"]).exists()
    assert Path(result["run_card"]["run_card_json_path"]).is_relative_to(sidecar_dir)
    assert result["research_signal_count"] == 6
    assert result["attribution_card_count"] == 1

    signals = json.loads(
        Path(result["research_signals_json_path"]).read_text(encoding="utf-8")
    )
    assert {row["signal_name"] for row in signals} == {
        "research_support_score",
        "coverage_freshness_score",
        "risk_disclosure_score",
    }


def test_mid_trend_integration_distinguishes_missing_coverage(
    tmp_path: Path,
) -> None:
    result = write_mid_trend_research_infra_artifacts(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_result=_toy_review_result(tmp_path),
        output_dir=tmp_path,
    )

    signals = json.loads(
        Path(result["research_signals_json_path"]).read_text(encoding="utf-8")
    )
    by_asset_signal = {(row["asset_id"], row["signal_name"]): row for row in signals}
    missing = by_asset_signal[("CN:SZ:300201", "coverage_freshness_score")]
    assert missing["signal_value"] is None
    assert missing["missingness_reason"] == "no_fresh_report"

    cards = json.loads(
        Path(result["attribution_cards_json_path"]).read_text(encoding="utf-8")
    )
    assert cards[0]["primary_cause"] == "research_coverage_gap"
    assert cards[0]["evidence"]["broker_report_count_90d"] == 0


def test_mid_trend_integration_keeps_repeated_run_registry_readable(
    tmp_path: Path,
) -> None:
    kwargs = {
        "trade_date": "2026-06-04",
        "strategy_variant": "top5_weekly_max_2_replacements",
        "review_result": _toy_review_result(tmp_path),
        "output_dir": tmp_path,
    }

    first = write_mid_trend_research_infra_artifacts(**kwargs)
    second = write_mid_trend_research_infra_artifacts(**kwargs)

    records = read_experiment_registry(second["experiment_registry_path"])
    assert len(records) == 1
    assert records[0].experiment_id == (
        "mid-trend-review-infra-2026-06-04-top5_weekly_max_2_replacements"
    )
    assert first["experiment_registry_path"] == second["experiment_registry_path"]


def test_mid_trend_integration_marks_no_risk_disclosure_with_fresh_report(
    tmp_path: Path,
) -> None:
    review_result = _toy_review_result(tmp_path)
    review_rows = review_result["review_rows"].copy()
    review_rows.loc[0, "pdf_risk_section_count_90d"] = 0
    review_result["review_rows"] = review_rows

    result = write_mid_trend_research_infra_artifacts(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_result=review_result,
        output_dir=tmp_path,
    )

    signals = json.loads(
        Path(result["research_signals_json_path"]).read_text(encoding="utf-8")
    )
    by_asset_signal = {(row["asset_id"], row["signal_name"]): row for row in signals}
    missing = by_asset_signal[("CN:SH:600183", "risk_disclosure_score")]
    assert missing["signal_value"] is None
    assert missing["missingness_reason"] == "no_risk_disclosure"


def test_mid_trend_integration_handles_empty_review_rows(tmp_path: Path) -> None:
    result = write_mid_trend_research_infra_artifacts(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_result={
            "portfolio_summary": {"trade_date": "2026-06-04"},
            "review_rows": pd.DataFrame(),
            "markdown": "",
            "paths": {},
        },
        output_dir=tmp_path,
    )

    assert result["research_signal_count"] == 0
    assert result["attribution_card_count"] == 0
    run_card = json.loads(
        Path(result["run_card"]["run_card_json_path"]).read_text(encoding="utf-8")
    )
    assert "empty_review_rows" in run_card["warnings"]


def test_mid_trend_review_wrapper_disabled_returns_original_without_sidecars(
    tmp_path: Path,
) -> None:
    review_result = _toy_review_result(tmp_path)
    calls = {"count": 0}

    def build_review() -> dict:
        calls["count"] += 1
        return review_result

    result = build_mid_trend_review_with_research_infra(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_builder=build_review,
        output_dir=tmp_path,
        write_research_infra=False,
    )

    assert result is review_result
    assert calls["count"] == 1
    assert not (tmp_path / "research_infra").exists()


def test_mid_trend_review_wrapper_enabled_writes_research_infra(
    tmp_path: Path,
) -> None:
    review_result = _toy_review_result(tmp_path)
    calls = {"count": 0}

    def build_review() -> dict:
        calls["count"] += 1
        return review_result

    result = build_mid_trend_review_with_research_infra(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        review_builder=build_review,
        output_dir=tmp_path,
        write_research_infra=True,
    )

    assert result is not review_result
    assert result["portfolio_summary"] == review_result["portfolio_summary"]
    assert result["markdown"] == review_result["markdown"]
    assert result["paths"] == review_result["paths"]
    assert result["review_rows"].equals(review_result["review_rows"])
    assert calls["count"] == 1

    research_infra = result["research_infra"]
    assert Path(research_infra["research_signals_json_path"]).exists()
    assert Path(research_infra["attribution_cards_json_path"]).exists()
    assert Path(research_infra["attribution_cards_md_path"]).exists()
    assert Path(research_infra["experiment_registry_path"]).exists()
    assert Path(research_infra["run_card"]["run_card_json_path"]).exists()
    assert research_infra["research_signal_count"] == 6
    assert research_infra["attribution_card_count"] == 1


def test_mid_trend_review_wrapper_rejects_non_dict_result(tmp_path: Path) -> None:
    def build_review() -> list[str]:
        return ["not", "a", "review", "result"]

    with pytest.raises(TypeError, match="review_builder must return a dict"):
        build_mid_trend_review_with_research_infra(
            trade_date="2026-06-04",
            strategy_variant="top5_weekly_max_2_replacements",
            review_builder=build_review,
            output_dir=tmp_path,
            write_research_infra=True,
        )
