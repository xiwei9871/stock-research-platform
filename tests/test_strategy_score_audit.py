import pandas as pd

from stock_research.strategy_score_audit import (
    build_strategy_score_audit,
    summarize_strategy_score_audit,
)


def test_lhb_audit_flags_mapped_score_without_raw_score() -> None:
    review_rows = [
        {
            "trade_date": "2026-06-22",
            "asset_id": "000960.SZ",
            "rank": 1,
            "score_total": 20.0,
            "score_source": "auction_enhanced_score",
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "strategy_run_id": "strategy-eod-2026-06-22-local",
            "source_type": "strategy_manifest",
            "source_name": "strategy_lhb_shortline",
            "source_rank": 1,
            "review_tier": "top5_focus",
        }
    ]
    strategy_results = {
        "lhb_shortline": {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "candidates": [
                {
                    "trade_date": "2026-06-22",
                    "ts_code": "000960.SZ",
                    "phase12a_rule_layer": "pending_intraday",
                    "candidate_reason": "lhb_capital_plus_structure",
                    "auction_enhanced_score": 20.0,
                }
            ],
        }
    }

    detail = build_strategy_score_audit(
        trade_date="2026-06-22",
        review_rows=review_rows,
        strategy_results=strategy_results,
        display_rows=review_rows,
    )

    row = detail.iloc[0].to_dict()
    assert row["raw_candidate_score"] is None
    assert "mapped_score_without_raw_score" in row["anomaly_flags"]
    assert row["eligibility_layer"] == "pending_intraday"


def test_lhb_audit_treats_published_score_total_as_raw_candidate_score() -> None:
    review_rows = [
        {
            "trade_date": "2026-06-25",
            "asset_id": "600667.SH",
            "rank": 1,
            "score_total": 66.378613,
            "score_source": "score_total",
            "score_components": {"lhb_net_buy_ratio": 0.13938337902073},
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "strategy_run_id": "strategy-eod-2026-06-25-local",
            "source_type": "strategy_manifest",
            "source_name": "strategy_lhb_shortline",
            "source_rank": 1,
            "review_tier": "top5_focus",
        }
    ]

    detail = build_strategy_score_audit(
        trade_date="2026-06-25",
        review_rows=review_rows,
        strategy_results={"lhb_shortline": {}},
        display_rows=review_rows,
    )

    row = detail.iloc[0].to_dict()
    assert row["raw_candidate_score"] == 66.378613
    assert row["raw_candidate_score_source"] == "score_total"
    assert row["published_score"] == 66.378613
    assert row["anomaly_flags"] == []


def test_tech_audit_tracks_raw_and_scaled_published_scores() -> None:
    review_rows = [
        {
            "trade_date": "2026-06-22",
            "asset_id": "CN:SZ:300408",
            "rank": 1,
            "score_total": 63.46,
            "score_source": "bottleneck_score",
            "strategy_id": "tech_bottleneck",
            "strategy_name": "Tech Bottleneck Discovery",
            "strategy_run_id": "strategy-eod-2026-06-22-local",
            "source_type": "strategy_manifest",
            "source_name": "strategy_tech_bottleneck",
            "source_rank": 1,
            "review_tier": "top5_focus",
        }
    ]
    strategy_results = {
        "tech_bottleneck": {
            "review_rows": [
                {
                    "trade_date": "2026-06-22",
                    "asset_id": "CN:SZ:300408",
                    "rank": 1,
                    "bottleneck_score": 0.6346,
                    "stock_name": "三环集团",
                }
            ]
        }
    }

    detail = build_strategy_score_audit(
        trade_date="2026-06-22",
        review_rows=review_rows,
        strategy_results=strategy_results,
        display_rows=review_rows,
    )

    row = detail.iloc[0].to_dict()
    assert row["raw_candidate_score"] == 0.6346
    assert row["raw_candidate_score_source"] == "bottleneck_score"
    assert row["published_score"] == 63.46
    assert row["published_score_source"] == "bottleneck_score_x100"
    assert row["display_score_source"] == "bottleneck_score_x100"
    assert row["anomaly_flags"] == []


def test_mid_trend_audit_resolves_latest_eligible_stale_lineage_row() -> None:
    review_rows = [
        {
            "trade_date": "2026-06-22",
            "asset_id": "CN:SZ:002080",
            "rank": 1,
            "score_total": 87.6,
            "score_source": "mid_trend_funnel_score",
            "strategy_id": "mid_trend",
            "strategy_name": "Mid Trend",
            "strategy_run_id": "strategy-eod-2026-06-22-local",
            "source_type": "strategy_manifest",
            "source_name": "strategy_mid_trend",
            "source_rank": 1,
            "review_tier": "top5_focus",
        }
    ]
    strategy_results = {
        "mid_trend": {
            "signals": [
                {
                    "rebalance_date": "2026-06-20",
                    "asset_id": "CN:SZ:002080",
                    "mid_trend_funnel_score": 87.6,
                    "selection_reason": "trend_support",
                },
                {
                    "rebalance_date": "2026-06-24",
                    "asset_id": "CN:SZ:002080",
                    "mid_trend_funnel_score": 91.2,
                    "selection_reason": "future_row",
                },
            ]
        }
    }

    detail = build_strategy_score_audit(
        trade_date="2026-06-22",
        review_rows=review_rows,
        strategy_results=strategy_results,
        display_rows=[],
    )

    row = detail.iloc[0].to_dict()
    assert row["raw_candidate_score"] == 87.6
    assert row["raw_candidate_score_source"] == "mid_trend_funnel_score"
    assert row["data_date_used"] == "2026-06-20"
    assert "stale_source" in row["anomaly_flags"]
    assert "missing_candidate_source" not in row["anomaly_flags"]


def test_tech_display_score_fallback_uses_normalized_published_provenance() -> None:
    detail = build_strategy_score_audit(
        trade_date="2026-06-22",
        review_rows=[
            {
                "trade_date": "2026-06-22",
                "asset_id": "CN:SZ:300408",
                "rank": 1,
                "score_total": 63.46,
                "score_source": "bottleneck_score",
                "strategy_id": "tech_bottleneck",
                "strategy_name": "Tech Bottleneck Discovery",
                "strategy_run_id": "strategy-eod-2026-06-22-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_tech_bottleneck",
                "source_rank": 1,
                "review_tier": "top5_focus",
            }
        ],
        strategy_results={
            "tech_bottleneck": {
                "review_rows": [
                    {
                        "trade_date": "2026-06-22",
                        "asset_id": "CN:SZ:300408",
                        "bottleneck_score": 0.6346,
                    }
                ]
            }
        },
        display_rows=[
            {
                "trade_date": "2026-06-22",
                "asset_id": "CN:SZ:300408",
                "strategy_id": "tech_bottleneck",
            }
        ],
    )

    row = detail.iloc[0].to_dict()
    assert row["display_score"] == 63.46
    assert row["published_score_source"] == "bottleneck_score_x100"
    assert row["display_score_source"] == "bottleneck_score_x100"


def test_display_rows_are_scoped_by_strategy_id_for_same_asset_same_date() -> None:
    detail = build_strategy_score_audit(
        trade_date="2026-06-22",
        review_rows=[
            {
                "trade_date": "2026-06-22",
                "asset_id": "CN:SZ:300408",
                "rank": 1,
                "score_total": 63.46,
                "score_source": "bottleneck_score",
                "strategy_id": "tech_bottleneck",
                "strategy_name": "Tech Bottleneck Discovery",
                "strategy_run_id": "strategy-eod-2026-06-22-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_tech_bottleneck",
                "source_rank": 1,
                "review_tier": "top5_focus",
            },
            {
                "trade_date": "2026-06-22",
                "asset_id": "CN:SZ:300408",
                "rank": 1,
                "score_total": 91.2,
                "score_source": "mid_trend_funnel_score",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend",
                "strategy_run_id": "strategy-eod-2026-06-22-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_mid_trend",
                "source_rank": 1,
                "review_tier": "top5_focus",
            },
        ],
        strategy_results={
            "tech_bottleneck": {
                "review_rows": [
                    {
                        "trade_date": "2026-06-22",
                        "asset_id": "CN:SZ:300408",
                        "bottleneck_score": 0.6346,
                    }
                ]
            },
            "mid_trend": {
                "signals": [
                    {
                        "trade_date": "2026-06-22",
                        "asset_id": "CN:SZ:300408",
                        "mid_trend_funnel_score": 91.2,
                        "selection_reason": "trend_support",
                    }
                ]
            },
        },
        display_rows=[
            {
                "trade_date": "2026-06-22",
                "asset_id": "CN:SZ:300408",
                "strategy_id": "mid_trend",
                "score_total": 88.8,
                "score_source": "mid_trend_dashboard_score",
            },
            {
                "trade_date": "2026-06-22",
                "asset_id": "CN:SZ:300408",
                "strategy_id": "tech_bottleneck",
                "score_total": 63.46,
                "score_source": "bottleneck_score",
            },
        ],
    )

    by_strategy = {row["strategy_id"]: row for row in detail.to_dict("records")}
    assert by_strategy["tech_bottleneck"]["display_score"] == 63.46
    assert by_strategy["tech_bottleneck"]["display_score_source"] == "bottleneck_score_x100"
    assert by_strategy["mid_trend"]["display_score"] == 88.8
    assert by_strategy["mid_trend"]["display_score_source"] == "mid_trend_dashboard_score"


def test_lineage_resolution_accepts_dataframe_backed_strategy_results() -> None:
    detail = build_strategy_score_audit(
        trade_date="2026-06-22",
        review_rows=[
            {
                "trade_date": "2026-06-22",
                "asset_id": "CN:SZ:300408",
                "rank": 1,
                "score_total": 63.46,
                "score_source": "bottleneck_score",
                "strategy_id": "tech_bottleneck",
                "strategy_name": "Tech Bottleneck Discovery",
                "strategy_run_id": "strategy-eod-2026-06-22-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_tech_bottleneck",
                "source_rank": 1,
                "review_tier": "top5_focus",
            }
        ],
        strategy_results={
            "tech_bottleneck": {
                "review_rows": pd.DataFrame(
                    [
                        {
                            "trade_date": "2026-06-22",
                            "asset_id": "CN:SZ:300408",
                            "bottleneck_score": 0.6346,
                            "stock_name": "三环集团",
                        }
                    ]
                )
            }
        },
        display_rows=[],
    )

    row = detail.iloc[0].to_dict()
    assert row["raw_candidate_score"] == 0.6346
    assert row["stock_name"] == "三环集团"
    assert "missing_candidate_source" not in row["anomaly_flags"]


def test_strategy_score_audit_summary_counts_anomalies_by_type() -> None:
    detail = build_strategy_score_audit(
        trade_date="2026-06-22",
        review_rows=[
            {
                "trade_date": "2026-06-22",
                "asset_id": "000960.SZ",
                "rank": 1,
                "score_total": 20.0,
                "score_source": "auction_enhanced_score",
                "strategy_id": "lhb_shortline",
                "strategy_name": "LHB Shortline Combo",
                "strategy_run_id": "strategy-eod-2026-06-22-local",
                "source_type": "strategy_manifest",
                "source_name": "strategy_lhb_shortline",
                "source_rank": 1,
                "review_tier": "top5_focus",
            }
        ],
        strategy_results={
            "lhb_shortline": {
                "strategy_id": "lhb_shortline",
                "strategy_name": "LHB Shortline Combo",
                "candidates": [
                    {
                        "trade_date": "2026-06-22",
                        "ts_code": "000960.SZ",
                        "phase12a_rule_layer": "pending_intraday",
                        "auction_enhanced_score": 20.0,
                    }
                ],
            }
        },
        display_rows=[
            {
                "trade_date": "2026-06-22",
                "asset_id": "000960.SZ",
                "score_total": 20.0,
                "score_source": "auction_enhanced_score",
                "strategy_id": "lhb_shortline",
            }
        ],
    )

    summary = summarize_strategy_score_audit(detail, trade_date="2026-06-22")

    assert summary["total_rows"] == 1
    assert summary["selected_rows"] == 1
    assert summary["anomaly_row_count"] == 1
    assert summary["anomaly_counts_by_type"] == {"mapped_score_without_raw_score": 1}
    assert summary["strategy_counts"] == {"lhb_shortline": 1}
