import pandas as pd

from stock_research.technical_feature_promotion_audit import (
    PROMOTION_AUDIT_COLUMNS,
    WATCHLIST_READINESS_COLUMNS,
    build_promotion_audit_from_frames,
    build_promotion_audit_report,
)


def _sample_dataset() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "ts_code": "000001.SZ",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0,
                "preclose": 9.8,
                "volume": 1000.0,
                "amount": 10000.0,
                "turnover_rate": 1.0,
                "amount_vs_20d": 1.5,
                "volatility_5d": 0.03,
                "volatility_20d": 0.05,
                "high_to_close_drawdown": 0.09,
                "close_position_in_day": 0.50,
                "atr_pct14": 0.08,
                "future_5d_return": -0.02,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "ts_code": "000001.SZ",
                "open": 10.5,
                "high": 12.0,
                "low": 10.0,
                "close": 11.0,
                "preclose": 10.0,
                "volume": 1100.0,
                "amount": 11000.0,
                "turnover_rate": 1.1,
                "amount_vs_20d": 1.7,
                "volatility_5d": 0.02,
                "volatility_20d": 0.04,
                "high_to_close_drawdown": 0.08,
                "close_position_in_day": 0.50,
                "atr_pct14": 0.07,
                "future_5d_return": 0.01,
            },
        ]
    )


def _sample_recommendation() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "feature_or_method": "amount_vs_20d",
                "category": "technical_feature",
                "signal_type": "weak_signal",
                "recommended_usage": "discard",
                "evidence_summary": "sample=2 null_rate=0.00%",
                "sample_count": 2,
                "confidence_level": "low",
                "next_action": "deprioritize",
            },
            {
                "feature_or_method": "volatility_5d",
                "category": "technical_feature",
                "signal_type": "useful_signal",
                "recommended_usage": "risk_filter",
                "evidence_summary": "sample=2 null_rate=0.00%",
                "sample_count": 2,
                "confidence_level": "low",
                "next_action": "keep_for_watchlist_validation",
            },
            {
                "feature_or_method": "high_to_close_drawdown",
                "category": "technical_feature",
                "signal_type": "weak_signal",
                "recommended_usage": "discard",
                "evidence_summary": "sample=2 null_rate=0.00%",
                "sample_count": 2,
                "confidence_level": "low",
                "next_action": "deprioritize",
            },
        ]
    )


def _sample_promotion_matrix() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "field_name": "amount_vs_20d",
                "field_type": "atomic_feature",
                "current_layer": "not_persisted",
                "target_layer": "stock_technical_features_daily",
                "priority": "high",
                "promotion_decision": "promote_now",
                "evidence_strength": "strong",
                "redundancy_status": "representative_of_group",
                "recommended_usage": "risk_filter",
                "rationale": "promote atomic",
            },
            {
                "field_name": "amount_vs_20d",
                "field_type": "factor_candidate",
                "current_layer": "not_in_factor_daily",
                "target_layer": "factor_daily",
                "priority": "high",
                "promotion_decision": "promote_now",
                "evidence_strength": "strong",
                "redundancy_status": "representative_of_group",
                "recommended_usage": "risk_filter",
                "rationale": "promote factor",
            },
            {
                "field_name": "volatility_5d",
                "field_type": "factor_candidate",
                "current_layer": "not_in_factor_daily",
                "target_layer": "factor_daily",
                "priority": "high",
                "promotion_decision": "promote_now",
                "evidence_strength": "strong",
                "redundancy_status": "non_redundant",
                "recommended_usage": "risk_filter",
                "rationale": "promote factor",
            },
            {
                "field_name": "high_to_close_drawdown",
                "field_type": "factor_candidate",
                "current_layer": "not_in_factor_daily",
                "target_layer": "factor_daily",
                "priority": "high",
                "promotion_decision": "promote_now",
                "evidence_strength": "strong",
                "redundancy_status": "non_redundant",
                "recommended_usage": "risk_filter",
                "rationale": "promote factor",
            },
            {
                "field_name": "rsi6_above_90",
                "field_type": "derived_combo",
                "current_layer": "not_persisted",
                "target_layer": "derived_only",
                "priority": "low",
                "promotion_decision": "do_not_promote",
                "evidence_strength": "strong_as_combo",
                "redundancy_status": "threshold_rule",
                "recommended_usage": "risk_filter",
                "rationale": "derived only",
            },
        ]
    )


def test_build_promotion_audit_from_frames_emits_expected_rows():
    result = build_promotion_audit_from_frames(
        dataset=_sample_dataset(),
        recommendation=_sample_recommendation(),
        promotion_matrix=_sample_promotion_matrix(),
        feature_source="computed_on_fly",
        warnings=["technical_table had no matching rows in requested window; fell back to computed_on_fly"],
    )

    audit = result["promotion_audit"]
    watchlist = result["watchlist_readiness"]

    assert list(audit.columns) == PROMOTION_AUDIT_COLUMNS
    assert list(watchlist.columns) == WATCHLIST_READINESS_COLUMNS
    assert {"amount_vs_20d", "volatility_5d", "high_to_close_drawdown", "rsi6_above_90"} <= set(audit["field_name"])

    factor_row = audit[
        (audit["field_name"] == "amount_vs_20d") & (audit["target_layer"] == "factor_daily")
    ].iloc[0]
    assert factor_row["code_state"] == "implemented"
    assert factor_row["storage_verification"] == "config_and_pipeline_ready"
    assert factor_row["readiness_status"] == "ready_for_watchlist_validation"

    derived_row = audit[audit["field_name"] == "rsi6_above_90"].iloc[0]
    assert derived_row["readiness_status"] == "keep_derived_only"


def test_build_promotion_audit_report_mentions_backfill_pending():
    result = build_promotion_audit_from_frames(
        dataset=_sample_dataset(),
        recommendation=_sample_recommendation(),
        promotion_matrix=_sample_promotion_matrix(),
        feature_source="computed_on_fly",
        warnings=["technical_table had no matching rows in requested window; fell back to computed_on_fly"],
    )

    report = build_promotion_audit_report(
        promotion_audit=result["promotion_audit"],
        watchlist_readiness=result["watchlist_readiness"],
        start_date="2026-01-01",
        end_date="2026-01-02",
        adjust_type="qfq",
        feature_source="computed_on_fly",
        warnings=result["warnings"],
    )

    assert "Technical Feature Promotion Audit" in report
    assert "backfill" in report.lower()
    assert "computed_on_fly" in report


def test_build_promotion_audit_from_frames_handles_duplicate_recommendation_keys():
    recommendation = pd.concat(
        [
            _sample_recommendation(),
            pd.DataFrame(
                [
                    {
                        "feature_or_method": "amount_vs_20d",
                        "category": "technical_combo",
                        "signal_type": "risk_signal",
                        "recommended_usage": "risk_filter",
                        "evidence_summary": "duplicate",
                        "sample_count": 1,
                        "confidence_level": "low",
                        "next_action": "keep_for_risk_filter_validation",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    result = build_promotion_audit_from_frames(
        dataset=_sample_dataset(),
        recommendation=recommendation,
        promotion_matrix=_sample_promotion_matrix(),
        feature_source="computed_on_fly",
        warnings=[],
    )

    audit = result["promotion_audit"]
    amount_row = audit[
        (audit["field_name"] == "amount_vs_20d") & (audit["target_layer"] == "factor_daily")
    ].iloc[0]
    assert amount_row["signal_type"] == "weak_signal"
