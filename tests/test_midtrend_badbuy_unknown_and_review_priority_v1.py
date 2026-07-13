from pathlib import Path

import pandas as pd
from stock_research import cli


def _pit_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "report_disclosure_date": "2025-01-02",
                "data_available_asof_date": "2025-01-02",
                "pit_valid_flag": True,
                "lookahead_violation_flag": False,
                "fundamental_quality_bucket": "quality_strong",
                "fundamental_momentum_bucket": "improving",
                "fundamental_risk_flag": False,
                "revenue_growth_yoy": 0.25,
                "profit_growth_yoy": 0.2,
                "deduct_profit_growth_yoy": 0.18,
                "roe": 0.15,
                "operating_cashflow_to_profit": 1.2,
                "debt_ratio": 0.3,
                "market_cap": 100.0,
                "valuation_percentile": pd.NA,
                "liquidity_score": pd.NA,
                "st_or_risk_flag": False,
                "financial_risk_flag": False,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "report_disclosure_date": "2025-01-02",
                "data_available_asof_date": "2025-01-02",
                "pit_valid_flag": True,
                "lookahead_violation_flag": False,
                "fundamental_quality_bucket": "quality_unknown",
                "fundamental_momentum_bucket": "unknown",
                "fundamental_risk_flag": False,
                "revenue_growth_yoy": pd.NA,
                "profit_growth_yoy": pd.NA,
                "deduct_profit_growth_yoy": pd.NA,
                "roe": pd.NA,
                "operating_cashflow_to_profit": pd.NA,
                "debt_ratio": pd.NA,
                "market_cap": 50.0,
                "valuation_percentile": pd.NA,
                "liquidity_score": pd.NA,
                "st_or_risk_flag": False,
                "financial_risk_flag": False,
            },
        ]
    )


def _bad_buy_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_strategy": "v1",
                "source_file": "baseline_diag",
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "stock_name": "A",
                "industry_name": "Tech",
                "action": "buy",
                "audit_label": "bad_buy",
                "forward_return": -0.12,
                "weighted_bad_buy_loss": -0.12,
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "mid_trend_layer": "stable_trend_watch",
                "mainline_status": "sustained_mainline",
                "fundamental_quality_bucket": "quality_unknown",
            },
            {
                "source_strategy": "v2",
                "source_file": "top10_trade_changes",
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "stock_name": "B",
                "industry_name": "Tech",
                "action": "buy",
                "audit_label": "bad_buy",
                "forward_return": -0.2,
                "weighted_bad_buy_loss": -0.2,
                "technical_confirmed": False,
                "mainline_confirmed": False,
                "mid_trend_layer": "high_elasticity_watch",
                "mainline_status": "neutral",
                "fundamental_quality_bucket": "quality_unknown",
            },
            {
                "source_strategy": "v2",
                "source_file": "top10_trade_changes",
                "trade_date": "2025-01-04",
                "asset_id": "C",
                "stock_name": "C",
                "industry_name": "Tech",
                "action": "buy",
                "audit_label": "bad_buy",
                "forward_return": -0.1,
                "weighted_bad_buy_loss": -0.1,
                "technical_confirmed": False,
                "mainline_confirmed": True,
                "mid_trend_layer": "mainline_momentum_watch",
                "mainline_status": "neutral",
                "fundamental_quality_bucket": "quality_unknown",
            },
        ]
    )


def _watch_daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "event_date": "2025-01-01",
                "exit_date": "2025-01-01",
                "asset_id": "A",
                "stock_name": "A",
                "industry_name": "Tech",
                "review_priority": "HIGH",
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "path_class_so_far": "immediate_continuation",
                "days_since_exit": 2,
                "current_rank": 12,
                "reconfirmed_T1_M1": True,
                "forward_return_since_exit": 0.1,
                "max_drawdown_since_exit": -0.02,
            },
            {
                "trade_date": "2025-01-03",
                "event_date": "2025-01-01",
                "exit_date": "2025-01-01",
                "asset_id": "B",
                "stock_name": "B",
                "industry_name": "Tech",
                "review_priority": "MEDIUM",
                "technical_confirmed": False,
                "mainline_confirmed": False,
                "path_class_so_far": "true_exit",
                "days_since_exit": 2,
                "current_rank": 35,
                "reconfirmed_T1_M1": False,
                "forward_return_since_exit": -0.08,
                "max_drawdown_since_exit": -0.18,
            },
        ]
    )


def test_classify_bad_buy_unknown_root_causes() -> None:
    from stock_research.midtrend_badbuy_unknown_and_review_priority_v1 import (
        audit_bad_buy_unknown_root_cause,
    )

    audited = audit_bad_buy_unknown_root_cause(_bad_buy_frame(), _pit_frame())
    root_map = dict(zip(audited["asset_id"], audited["root_cause"], strict=False))
    assert root_map["A"] == "source_domain_mismatch"
    assert root_map["B"] == "pit_row_found_but_all_core_fields_missing"
    assert root_map["C"] == "pit_join_failed_date"


def test_assign_fundamental_priority_and_enhanced_review() -> None:
    from stock_research.midtrend_badbuy_unknown_and_review_priority_v1 import (
        enhance_review_priority,
    )

    watch = _watch_daily_frame()
    pit = _pit_frame().rename(columns={"trade_date": "pit_trade_date"})
    enhanced = enhance_review_priority(watch, pit)
    row_a = enhanced[enhanced["asset_id"].eq("A")].iloc[0]
    row_b = enhanced[enhanced["asset_id"].eq("B")].iloc[0]
    assert row_a["fundamental_priority_tag"] == "FUNDAMENTAL_STRONG_AND_IMPROVING"
    assert row_a["enhanced_review_priority"] == "HIGH_FUNDAMENTAL"
    assert row_b["enhanced_review_priority"] == "RISK_DOWNGRADE"
    assert "buy" not in str(row_a["enhanced_review_reason"]).lower()
    assert "sell" not in str(row_a["enhanced_review_reason"]).lower()


def test_priority_effectiveness_diagnostic_generation() -> None:
    from stock_research.midtrend_badbuy_unknown_and_review_priority_v1 import (
        build_priority_effectiveness_diagnostic,
    )

    watch = pd.DataFrame(
        [
            {
                "enhanced_review_priority": "HIGH_FUNDAMENTAL",
                "path_class_so_far": "immediate_continuation",
                "forward_return_since_exit": 0.2,
                "forward_return_20d": 0.1,
                "forward_return_30d": 0.15,
                "forward_return_60d": 0.2,
                "max_drawdown_since_exit": -0.03,
                "asset_id": "A",
            },
            {
                "enhanced_review_priority": "RISK_DOWNGRADE",
                "path_class_so_far": "true_exit",
                "forward_return_since_exit": -0.1,
                "forward_return_20d": -0.08,
                "forward_return_30d": -0.09,
                "forward_return_60d": -0.1,
                "max_drawdown_since_exit": -0.2,
                "asset_id": "B",
            },
        ]
    )
    diagnostic = build_priority_effectiveness_diagnostic(watch)
    high = diagnostic[diagnostic["enhanced_review_priority"].eq("HIGH_FUNDAMENTAL")].iloc[0]
    assert high["continued_winner_count"] == 1
    assert high["continued_winner_rate"] == 1.0


def test_run_outputs_and_cli_dispatch(tmp_path: Path, monkeypatch) -> None:
    from stock_research.midtrend_badbuy_unknown_and_review_priority_v1 import (
        run_midtrend_badbuy_unknown_and_review_priority_from_frames,
    )

    result = run_midtrend_badbuy_unknown_and_review_priority_from_frames(
        pit_features=_pit_frame(),
        bad_buy_trades=_bad_buy_frame(),
        watch_daily=_watch_daily_frame(),
        output_dir=tmp_path,
    )
    for name in [
        "bad_buy_quality_unknown_root_cause.csv",
        "bad_buy_quality_unknown_root_cause_summary.csv",
        "bad_buy_pit_join_quality_report.md",
        "bad_buy_fundamental_attribution_pit_refined.csv",
        "midtrend_post_exit_watch_daily_fundamental_priority.csv",
        "midtrend_post_exit_watch_fundamental_priority_summary.csv",
        "midtrend_post_exit_watch_fundamental_priority_summary.md",
        "post_exit_priority_effectiveness_diagnostic.csv",
        "daily_review_integration_notes.md",
        "run_params.csv",
        "code_audit.md",
        "final_interpretation.md",
    ]:
        assert (tmp_path / name).exists(), name
    assert "paths" in result

    args = cli.build_parser().parse_args(
        [
            "midtrend-badbuy-unknown-and-review-priority",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert args.command == "midtrend-badbuy-unknown-and-review-priority"

    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"output_dir": str(tmp_path)}}

    monkeypatch.setattr(
        "stock_research.midtrend_badbuy_unknown_and_review_priority_v1.run_midtrend_badbuy_unknown_and_review_priority_cli",
        _fake_runner,
    )
    rc = cli.main(
        [
            "midtrend-badbuy-unknown-and-review-priority",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert rc in {0, None}
    assert called["output_dir"] == str(tmp_path)
