from stock_research.strategy_score_audit import build_strategy_score_audit, summarize_strategy_score_audit


def test_mid_trend_strategy_manifest_review_row_is_not_marked_stale_source():
    review_rows = [
        {
            "trade_date": "2026-06-29",
            "strategy_id": "mid_trend",
            "strategy_name": "Mid Trend Combo",
            "asset_id": "CN:SH:603733",
            "rank": 2,
            "score_total": 81.639212,
            "score_source": "mid_trend_funnel_score",
            "source_type": "strategy_manifest",
            "review_tier": "top5_focus",
        }
    ]
    strategy_results = {
        "mid_trend": {
            "signals": [
                {
                    "trade_date": "2026-06-15",
                    "asset_id": "CN:SH:603733",
                    "mid_trend_funnel_score": 81.639212,
                }
            ],
            "positions": [
                {
                    "rebalance_date": "2026-06-29",
                    "asset_id": "CN:SH:603733",
                    "weight": 0.2,
                }
            ],
        }
    }

    detail = build_strategy_score_audit(
        trade_date="2026-06-29",
        review_rows=review_rows,
        strategy_results=strategy_results,
        display_rows=review_rows,
    )
    summary = summarize_strategy_score_audit(detail, trade_date="2026-06-29")

    assert detail.iloc[0]["data_date_used"] == "2026-06-29"
    assert detail.iloc[0]["anomaly_flags"] == []
    assert summary["anomaly_counts_by_type"] == {}
