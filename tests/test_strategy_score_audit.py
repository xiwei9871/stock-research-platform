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


def test_lhb_audit_preserves_published_name_and_risk_gate_fields():
    review_rows = [
        {
            "trade_date": "2026-07-14",
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "asset_id": "CN:SZ:001399",
            "stock_name": "惠科股份",
            "stock_name_source": "lhb_top_list_daily",
            "rank": 4,
            "source_rank": 4,
            "score_total": 69.3698,
            "raw_score": 69.3698,
            "score_source": "score_total",
            "source_type": "strategy_manifest",
            "review_tier": "risk_watch",
            "confirmation_state": "risk_watch",
            "phase12a_rule_layer": "pending_intraday",
            "phase12a_rule_action": "pending",
            "fill_status": "not_follow_allowed",
            "eligibility_status": "risk_watch",
            "top5_eligible": False,
            "backtest_entry_eligible": False,
            "eligibility_reason_codes": ["near_limit_down_followthrough_risk"],
            "eligibility_warning_codes": ["institution_activity_unknown"],
            "eligibility_contract_version": "lhb_eligibility_v2",
            "risk_gate_code": "near_limit_down_followthrough_risk",
            "risk_gate_reason": "当日涨跌幅 -9.99% 触及 main_board 接近跌停阈值 -9.50%",
            "price_limit_regime": "main_board",
            "near_limit_down_threshold": -9.5,
            "data_quality_status": "complete",
            "pct_chg": -9.991,
        }
    ]
    strategy_results = {
        "lhb_shortline": {
            "candidates": [
                {
                    "trade_date": "2026-07-14",
                    "asset_id": "CN:SZ:001399",
                    "stock_name": "",
                    "auction_enhanced_score": 69.3698,
                    "phase12a_rule_layer": "pending_intraday",
                }
            ]
        }
    }

    detail = build_strategy_score_audit(
        trade_date="2026-07-14",
        review_rows=review_rows,
        strategy_results=strategy_results,
        display_rows=review_rows,
    )

    row = detail.iloc[0]
    assert row["stock_name"] == "惠科股份"
    assert row["stock_name_source"] == "lhb_top_list_daily"
    assert bool(row["top5_eligible"]) is False
    assert row["confirmation_state"] == "risk_watch"
    assert row["phase12a_rule_layer"] == "pending_intraday"
    assert row["eligibility_status"] == "risk_watch"
    assert bool(row["backtest_entry_eligible"]) is False
    assert row["eligibility_reason_codes"] == ["near_limit_down_followthrough_risk"]
    assert row["eligibility_contract_version"] == "lhb_eligibility_v2"
    assert row["risk_gate_code"] == "near_limit_down_followthrough_risk"
    assert row["price_limit_regime"] == "main_board"
    assert row["near_limit_down_threshold"] == -9.5
    assert row["data_quality_status"] == "complete"
    assert row["pct_chg"] == -9.991


def test_lhb_audit_uses_auction_enhanced_lineage_as_raw_score():
    review_rows = [
        {
            "trade_date": "2026-07-13",
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "asset_id": "000920.SZ",
            "rank": 2,
            "score_total": 10.0,
            "score_source": "auction_enhanced_score",
            "source_type": "strategy_manifest",
            "review_tier": "top5_focus",
            "confirmation_state": "watch_only",
        }
    ]
    strategy_results = {
        "lhb_shortline": {
            "candidates": [
                {
                    "trade_date": "2026-07-13",
                    "ts_code": "000920.SZ",
                    "auction_enhanced_score": 10.0,
                    "phase12a_rule_layer": "watch_pool",
                }
            ]
        }
    }

    detail = build_strategy_score_audit(
        trade_date="2026-07-13",
        review_rows=review_rows,
        strategy_results=strategy_results,
        display_rows=review_rows,
    )

    row = detail.iloc[0]
    assert row["raw_candidate_score"] == 10.0
    assert row["raw_candidate_score_source"] == "auction_enhanced_score"
    assert row["anomaly_flags"] == []
