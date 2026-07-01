from pathlib import Path

import pandas as pd
from stock_research import cli


def _pit() -> pd.DataFrame:
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
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "report_disclosure_date": "2025-01-04",
                "data_available_asof_date": "2025-01-04",
                "pit_valid_flag": True,
                "lookahead_violation_flag": True,
                "fundamental_quality_bucket": "quality_weak",
                "fundamental_momentum_bucket": "deteriorating",
                "fundamental_risk_flag": True,
            },
        ]
    )


def _bad_buy_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_strategy": "v2",
                "source_file": "trades.csv",
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "stock_name": "A",
                "industry_name": "Tech",
                "audit_label": "bad_buy",
                "action": "buy",
                "fundamental_quality_bucket": "quality_unknown",
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "midtrend_confirmation_state": "T1_M1_UNKNOWN_F",
                "mid_trend_layer": "high_elasticity_watch",
                "forward_return": -0.1,
                "weighted_bad_buy_loss": -0.1,
            },
            {
                "source_strategy": "v2",
                "source_file": "trades.csv",
                "trade_date": "2025-01-03",
                "asset_id": "C",
                "stock_name": "C",
                "industry_name": "Tech",
                "audit_label": "bad_buy",
                "action": "buy",
                "fundamental_quality_bucket": "quality_neutral",
                "technical_confirmed": False,
                "mainline_confirmed": True,
                "midtrend_confirmation_state": "T0_M1_UNKNOWN_F",
                "mid_trend_layer": "stable_trend_watch",
                "forward_return": -0.2,
                "weighted_bad_buy_loss": -0.2,
            },
        ]
    )


def _watch_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "stock_name": "A",
                "industry_name": "Tech",
                "enhanced_review_priority": "HIGH_FUNDAMENTAL",
                "review_priority": "HIGH",
                "fundamental_priority_tag": "FUNDAMENTAL_STRONG_AND_IMPROVING",
                "enhanced_review_reason": "review_strong_improving_post_exit_name",
                "suggested_review_action": "review_strong_improving_post_exit_name",
                "event_date": "2025-01-01",
                "days_since_exit": 2,
                "event_type": "ranking_churn_sell",
                "rank_on_exit_date": 8,
                "current_rank": 9,
                "mid_trend_funnel_score_on_exit": 101,
                "current_score": 106,
                "score_delta_since_exit": 5,
                "current_mid_trend_layer": "stable_trend_watch",
                "current_mainline_status": "sustained_mainline",
                "technical_confirmed": True,
                "mainline_confirmed": True,
                "midtrend_confirmation_state": "T1_M1_F1",
                "current_fundamental_quality_bucket": "quality_strong",
                "current_fundamental_momentum_bucket": "improving",
                "current_fundamental_risk_flag": False,
                "forward_return_since_exit": 0.1,
                "max_return_since_exit": 0.2,
                "max_drawdown_since_exit": -0.03,
                "reentered_top5": False,
                "reentered_top10": True,
                "reentered_top20": True,
                "reconfirmed_T1_M1": True,
                "path_class_so_far": "immediate_continuation",
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "stock_name": "B",
                "industry_name": "Tech",
                "enhanced_review_priority": "RISK_DOWNGRADE",
                "review_priority": "MEDIUM",
                "fundamental_priority_tag": "FUNDAMENTAL_WEAK",
                "enhanced_review_reason": "downgrade_fundamental_weak_or_deteriorating",
                "suggested_review_action": "downgrade_fundamental_weak_or_deteriorating",
                "event_date": "2025-01-01",
                "days_since_exit": 2,
                "event_type": "hard_damage_sell",
                "rank_on_exit_date": 40,
                "current_rank": 50,
                "mid_trend_funnel_score_on_exit": 99,
                "current_score": 92,
                "score_delta_since_exit": -7,
                "current_mid_trend_layer": "risk_exclusion_watch",
                "current_mainline_status": "non_mainline",
                "technical_confirmed": False,
                "mainline_confirmed": False,
                "midtrend_confirmation_state": "T0_M0_F0",
                "current_fundamental_quality_bucket": "quality_weak",
                "current_fundamental_momentum_bucket": "deteriorating",
                "current_fundamental_risk_flag": True,
                "forward_return_since_exit": -0.1,
                "max_return_since_exit": 0.0,
                "max_drawdown_since_exit": -0.2,
                "reentered_top5": False,
                "reentered_top10": False,
                "reentered_top20": False,
                "reconfirmed_T1_M1": False,
                "path_class_so_far": "true_exit",
            },
        ]
    )


def test_join_pit_fundamental_bucket_canonical_prefers_pit_and_flags_fallback() -> None:
    from stock_research.midtrend_pit_attribution_canonical_and_daily_review_lite_v1 import (
        join_pit_fundamental_bucket_canonical,
    )

    joined = join_pit_fundamental_bucket_canonical(
        _bad_buy_rows(),
        date_col="trade_date",
        asset_col="asset_id",
        pit_features=_pit(),
    )
    row_a = joined[joined["asset_id"].eq("A")].iloc[0]
    row_c = joined[joined["asset_id"].eq("C")].iloc[0]
    assert row_a["source_fundamental_quality_bucket"] == "quality_unknown"
    assert row_a["pit_fundamental_quality_bucket"] == "quality_strong"
    assert row_a["fundamental_quality_bucket"] == "quality_strong"
    assert row_a["fundamental_bucket_source"] == "pit"
    assert row_c["fundamental_quality_bucket"] == "quality_neutral"
    assert row_c["fundamental_bucket_source"] == "pit_missing_fallback_source"


def test_join_pit_fundamental_bucket_canonical_rejects_lookahead() -> None:
    from stock_research.midtrend_pit_attribution_canonical_and_daily_review_lite_v1 import (
        join_pit_fundamental_bucket_canonical,
    )

    rows = pd.DataFrame(
        [{"trade_date": "2025-01-03", "asset_id": "B", "fundamental_quality_bucket": "quality_neutral"}]
    )
    joined = join_pit_fundamental_bucket_canonical(rows, date_col="trade_date", asset_col="asset_id", pit_features=_pit())
    row = joined.iloc[0]
    assert row["fundamental_bucket_source"] == "invalid_lookahead_rejected"
    assert row["fundamental_quality_bucket"] == "quality_unknown"


def test_bucket_source_audit_detects_source_domain_mismatch() -> None:
    from stock_research.midtrend_pit_attribution_canonical_and_daily_review_lite_v1 import (
        build_bucket_source_audit,
        join_pit_fundamental_bucket_canonical,
    )

    joined = join_pit_fundamental_bucket_canonical(_bad_buy_rows(), date_col="trade_date", asset_col="asset_id", pit_features=_pit())
    audit = build_bucket_source_audit(joined, attribution_type="bad_buy")
    assert audit.iloc[0]["canonical_pit_rows"] == 1
    assert audit.iloc[0]["fallback_source_rows"] == 1
    assert audit.iloc[0]["source_domain_mismatch_rows"] == 0


def test_daily_review_lite_artifact_schema_and_non_trading_language() -> None:
    from stock_research.midtrend_pit_attribution_canonical_and_daily_review_lite_v1 import (
        build_daily_review_lite_artifacts,
    )

    csv_rows, json_payload = build_daily_review_lite_artifacts(_watch_rows())
    assert set(json_payload["sections"]) == {
        "HIGH_FUNDAMENTAL",
        "HIGH_TECH_MAINLINE",
        "MEDIUM_FUNDAMENTAL_WATCH",
        "RISK_DOWNGRADE",
        "LOW_OR_EXPIRED",
    }
    first = json_payload["sections"]["HIGH_FUNDAMENTAL"]["items"][0]
    assert first["asset_id"] == "A"
    forbidden = {"buy", "sell", "买", "卖"}
    text = " ".join(str(item.get("suggested_review_action", "")) for item in csv_rows.to_dict(orient="records"))
    assert not any(word in text.lower() for word in forbidden)


def test_run_outputs_and_cli_dispatch(tmp_path: Path, monkeypatch) -> None:
    from stock_research.midtrend_pit_attribution_canonical_and_daily_review_lite_v1 import (
        run_midtrend_pit_attribution_canonical_from_frames,
    )

    result = run_midtrend_pit_attribution_canonical_from_frames(
        pit_features=_pit(),
        bad_buy_rows=_bad_buy_rows(),
        bad_sell_rows=pd.DataFrame(),
        post_exit_rows=pd.DataFrame(),
        reentry_rows=pd.DataFrame(),
        enhanced_watch_rows=_watch_rows(),
        output_dir=tmp_path,
    )
    for name in [
        "bad_buy_fundamental_attribution_pit_canonical.csv",
        "bad_buy_bucket_source_audit.csv",
        "bad_sell_fundamental_attribution_pit_canonical.csv",
        "post_exit_fundamental_attribution_pit_canonical.csv",
        "reentry_left_tail_fundamental_attribution_pit_canonical.csv",
        "attribution_bucket_source_audit.csv",
        "midtrend_post_exit_watch_daily_review_lite.json",
        "midtrend_post_exit_watch_daily_review_lite.csv",
        "daily_review_lite_integration_contract.md",
        "run_params.csv",
        "code_audit.md",
        "final_interpretation.md",
    ]:
        assert (tmp_path / name).exists(), name
    assert result["paths"]["output_dir"] == str(tmp_path)

    args = cli.build_parser().parse_args(
        [
            "midtrend-pit-attribution-canonical-and-daily-review-lite",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert args.command == "midtrend-pit-attribution-canonical-and-daily-review-lite"

    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"output_dir": str(tmp_path)}}

    monkeypatch.setattr(
        "stock_research.midtrend_pit_attribution_canonical_and_daily_review_lite_v1.run_midtrend_pit_attribution_canonical_cli",
        _fake_runner,
    )
    rc = cli.main(
        [
            "midtrend-pit-attribution-canonical-and-daily-review-lite",
            "--output-dir",
            str(tmp_path),
        ]
    )
    assert rc in {0, None}
    assert called["output_dir"] == str(tmp_path)
