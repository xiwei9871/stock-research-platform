from pathlib import Path

import pandas as pd
import pytest

from stock_research.intraday_factor_eval import (
    classify_intraday_factor_signal,
    evaluate_intraday_factor_frames,
    format_intraday_factor_markdown,
    load_industry_intraday_factor_frame,
    write_intraday_factor_eval_report,
)


def test_evaluate_intraday_factor_frames_summarizes_multi_horizon_metrics():
    factors_by_feature = {
        "tail_strength": pd.DataFrame(
            [
                {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
                {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
                {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 3.0},
                {"trade_date": "2026-01-01", "asset_id": "D", "factor_value": 4.0},
                {"trade_date": "2026-01-02", "asset_id": "A", "factor_value": 1.0},
                {"trade_date": "2026-01-02", "asset_id": "B", "factor_value": 2.0},
                {"trade_date": "2026-01-02", "asset_id": "C", "factor_value": 3.0},
                {"trade_date": "2026-01-02", "asset_id": "D", "factor_value": 4.0},
            ]
        )
    }
    returns = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "C", "forward_return_5d": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "D", "forward_return_5d": 0.04},
            {"trade_date": "2026-01-02", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-02", "asset_id": "B", "forward_return_5d": 0.02},
            {"trade_date": "2026-01-02", "asset_id": "C", "forward_return_5d": 0.03},
            {"trade_date": "2026-01-02", "asset_id": "D", "forward_return_5d": 0.04},
        ]
    )

    summary = evaluate_intraday_factor_frames(
        factors_by_feature=factors_by_feature,
        returns=returns,
        horizons=[5],
        quantiles=2,
        top_n=2,
        min_ic_count=2,
    )

    row = summary.iloc[0]
    assert row["feature_name"] == "tail_strength"
    assert row["horizon"] == 5
    assert row["mean_ic"] == pytest.approx(1.0)
    assert row["mean_rank_ic"] == pytest.approx(1.0)
    assert row["ic_count"] == 2
    assert row["mean_top_bottom_spread"] == pytest.approx(0.02)
    assert row["recommendation"] == "candidate_long"


def test_classify_intraday_factor_signal_separates_long_short_filter_and_reject():
    assert (
        classify_intraday_factor_signal(
            mean_rank_ic=0.035,
            rank_icir=0.4,
            mean_top_bottom_spread=0.01,
            ic_count=50,
        )
        == "candidate_long"
    )
    assert (
        classify_intraday_factor_signal(
            mean_rank_ic=-0.04,
            rank_icir=-0.5,
            mean_top_bottom_spread=-0.02,
            ic_count=50,
        )
        == "candidate_short_or_risk_filter"
    )
    assert (
        classify_intraday_factor_signal(
            mean_rank_ic=0.04,
            rank_icir=0.5,
            mean_top_bottom_spread=0.02,
            ic_count=5,
        )
        == "insufficient_sample"
    )
    assert (
        classify_intraday_factor_signal(
            mean_rank_ic=0.005,
            rank_icir=0.1,
            mean_top_bottom_spread=0.0,
            ic_count=50,
        )
        == "reject"
    )


def test_write_intraday_factor_eval_report_outputs_markdown_and_csv(tmp_path: Path):
    summary = pd.DataFrame(
        [
            {
                "feature_name": "tail_strength",
                "horizon": 5,
                "sample_rows": 8,
                "date_count": 2,
                "mean_ic": 0.03,
                "icir": 0.5,
                "mean_rank_ic": 0.04,
                "rank_icir": 0.6,
                "mean_top_bottom_spread": 0.01,
                "mean_turnover": 0.7,
                "recommendation": "candidate_long",
            }
        ]
    )

    paths = write_intraday_factor_eval_report(
        summary=summary,
        output_dir=tmp_path,
        start_date="2026-01-01",
        end_date="2026-01-02",
        horizons=[5],
    )

    assert Path(paths["summary_csv_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "# Intraday Factor Evaluation" in markdown
    assert "tail_strength" in markdown
    assert "candidate_long" in markdown


def test_format_intraday_factor_markdown_handles_empty_summary():
    markdown = format_intraday_factor_markdown(
        summary=pd.DataFrame(),
        start_date="2026-01-01",
        end_date="2026-01-02",
        horizons=[5, 10],
    )

    assert "No evaluable intraday factor rows" in markdown


def test_load_industry_intraday_factor_frame_uses_asof_membership_snapshot(monkeypatch):
    import stock_research.intraday_factor_eval as intraday_factor_eval

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append({"sql": sql, "params": params})
        return [
            {
                "trade_date": "2026-01-02",
                "asset_id": "CN:SH:600000",
                "factor_value": "0.12",
            }
        ]

    monkeypatch.setattr(intraday_factor_eval, "connect", lambda service: Conn())
    monkeypatch.setattr(intraday_factor_eval, "fetch_all", fake_fetch_all)

    result = load_industry_intraday_factor_frame(
        feature_name="industry_up_ratio",
        start_date="2025-01-02",
        end_date="2026-06-05",
        industry_system="csrc",
    )

    sql = calls[0]["sql"]
    assert "DISTINCT ON (asset_id)" in sql
    assert "m.start_date <= f.trade_date" not in sql
    assert calls[0]["params"][:3] == ["csrc", "2026-06-05", "2026-06-05"]
    assert result.loc[0, "factor_value"] == pytest.approx(0.12)
