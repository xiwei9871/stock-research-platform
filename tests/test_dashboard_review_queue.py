from stock_research.dashboard import review_queue


def _patch_stale_strategy_fallback(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {
            "latest_market_date": "2026-07-24",
            "latest_score_date": "2026-07-24",
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(review_queue, "_load_manifest_strategy_rows", lambda **kwargs: [])
    monkeypatch.setattr(review_queue, "_load_strategy_snapshot_rows", lambda **kwargs: [])
    monkeypatch.setattr(
        review_queue,
        "load_active_strategy_topn_rows",
        lambda **kwargs: [
            {
                "trade_date": "2026-06-01",
                "asset_id": "CN:SZ:000001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
                "score_total": 88.0,
            }
        ],
    )
    monkeypatch.setattr(
        review_queue,
        "_active_strategy_names",
        lambda: {
            "lhb_shortline": "LHB Shortline Combo",
            "mid_trend": "Mid Trend Combo",
            "tech_bottleneck": "Tech Bottleneck Combo",
        },
    )
    monkeypatch.setattr(
        review_queue,
        "load_top_scores_for_dashboard",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not fall through to score Top-N")),
    )


def _assert_strategy_queue_failed_closed(result):
    assert result["requested_trade_date"] == "2026-07-24"
    assert result["trade_date"] == "2026-07-24"
    assert result["review_mode"] == "strategy_topn"
    assert all(group["count"] == 0 for group in result["groups"])
    assert all(group["freshness_status"] == "missing" for group in result["groups"])
    assert all(group["items"] == [] for group in result["groups"])
    assert "exact-date official strategy manifest unavailable for 2026-07-24" in result["warnings"]


def test_default_strategy_review_queue_rejects_stale_fallback_rows(monkeypatch):
    _patch_stale_strategy_fallback(monkeypatch)

    result = review_queue.build_review_queue()

    _assert_strategy_queue_failed_closed(result)


def test_explicit_strategy_review_queue_rejects_stale_fallback_rows(monkeypatch):
    _patch_stale_strategy_fallback(monkeypatch)

    result = review_queue.build_review_queue(trade_date="2026-07-24")

    _assert_strategy_queue_failed_closed(result)


def test_strategy_review_queue_rejects_row_with_stale_underlying_data_date(monkeypatch):
    _patch_stale_strategy_fallback(monkeypatch)
    monkeypatch.setattr(
        review_queue,
        "load_active_strategy_topn_rows",
        lambda **kwargs: [
            {
                "trade_date": "2026-07-24",
                "latest_trade_date": "2026-06-01",
                "asset_id": "CN:SZ:000001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
                "score_total": 88.0,
            }
        ],
    )

    result = review_queue.build_review_queue(trade_date="2026-07-24")

    _assert_strategy_queue_failed_closed(result)


def test_strategy_review_queue_preserves_requested_date_and_reports_group_data_date(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "_active_strategy_names",
        lambda: {
            "lhb_shortline": "LHB Shortline Combo",
            "mid_trend": "Mid Trend Combo",
            "tech_bottleneck": "Tech Bottleneck Combo",
        },
    )

    result = review_queue._strategy_review_queue(
        rows=[
            {
                "trade_date": "2026-06-01",
                "asset_id": "CN:SZ:000001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
                "score_total": 88.0,
            }
        ],
        selected_trade_date="2026-07-24",
        platform_market_date="2026-07-24",
        score_version="strategy_topn",
        lookback_days=90,
    )

    assert result["requested_trade_date"] == "2026-07-24"
    assert result["trade_date"] == "2026-07-24"
    mid_trend = next(group for group in result["groups"] if group["strategy_id"] == "mid_trend")
    assert mid_trend["strategy_id"] == "mid_trend"
    assert mid_trend["requested_trade_date"] == "2026-07-24"
    assert mid_trend["data_trade_date"] == "2026-06-01"
    assert mid_trend["freshness_status"] == "stale"


def test_strategy_review_queue_marks_empty_official_groups_missing(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "_active_strategy_names",
        lambda: {
            "lhb_shortline": "LHB Shortline Combo",
            "mid_trend": "Mid Trend Combo",
            "tech_bottleneck": "Tech Bottleneck Combo",
        },
    )

    result = review_queue._strategy_review_queue(
        rows=[],
        selected_trade_date="2026-07-24",
        platform_market_date="2026-07-24",
        score_version="strategy_topn",
        lookback_days=90,
    )

    assert result["requested_trade_date"] == "2026-07-24"
    assert result["trade_date"] == "2026-07-24"
    assert all(group["freshness_status"] == "missing" for group in result["groups"])
    assert all(group["data_trade_date"] == "" for group in result["groups"])


def test_strategy_review_queue_uses_underlying_latest_trade_date_for_freshness(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "_active_strategy_names",
        lambda: {"mid_trend": "Mid Trend Combo"},
    )

    result = review_queue._strategy_review_queue(
        rows=[
            {
                "trade_date": "2026-07-24",
                "latest_trade_date": "2026-06-01",
                "asset_id": "CN:SZ:000001",
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "rank": 1,
                "score_total": 88.0,
            }
        ],
        selected_trade_date="2026-07-24",
        platform_market_date="2026-07-24",
        score_version="strategy_topn",
        lookback_days=90,
    )

    group = result["groups"][0]
    assert group["data_trade_date"] == "2026-06-01"
    assert group["freshness_status"] == "stale"


def test_review_queue_defaults_to_latest_market_date_when_display_gate_lags(monkeypatch):
    monkeypatch.setattr(review_queue, "load_recent_data_run_manifest", lambda: [{"trade_date": "2026-06-30"}])
    monkeypatch.setattr(
        review_queue,
        "select_display_date",
        lambda modules, latest_market_date: {
            "display_trade_date": "2026-06-30",
            "candidate_trade_date": latest_market_date,
            "display_status": "ready",
        },
    )

    selected = review_queue._default_display_trade_date(
        {
            "latest_market_date": "2026-07-03",
            "latest_score_date": "2026-07-03",
        }
    )

    assert selected == "2026-07-03"


def test_attach_asset_names_keeps_published_lhb_name_when_master_missing(monkeypatch):
    monkeypatch.setattr(review_queue, "_load_asset_names", lambda asset_ids: {})

    rows = review_queue._attach_asset_names(
        [{"asset_id": "CN:SZ:001399", "stock_name": "惠科股份"}]
    )

    assert rows[0]["stock_name"] == "惠科股份"


def test_strategy_lightweight_digest_labels_lhb_risk_watch_and_exposes_reason():
    digest = review_queue._strategy_lightweight_digest(
        {
            "asset_id": "CN:SZ:001399",
            "stock_name": "惠科股份",
            "strategy_name": "LHB Shortline Combo",
            "rank": 4,
            "score_total": 69.3698,
            "review_tier": "risk_watch",
            "risk_gate_code": "near_limit_down_followthrough_risk",
            "risk_gate_reason": "当日涨跌幅 -9.99% 触及 main_board 接近跌停阈值 -9.50%",
        },
        "CN:SZ:001399",
        "2026-07-14",
    )

    assert "跌停风险观察" in digest["title"]
    assert digest["risk_flags"] == [
        {
            "code": "near_limit_down_followthrough_risk",
            "message": "当日涨跌幅 -9.99% 触及 main_board 接近跌停阈值 -9.50%",
            "severity": "warning",
        }
    ]


def test_strategy_lightweight_digest_exposes_st_high_risk_warning():
    digest = review_queue._strategy_lightweight_digest(
        {
            "asset_id": "CN:SZ:000078",
            "stock_name": "ST海王",
            "strategy_name": "LHB Shortline Combo",
            "rank": 5,
            "score_total": 66.0,
            "review_tier": "top5_focus",
            "buy_signal_status": "tradable",
            "eligibility_warning_codes": ["st_high_risk"],
        },
        "CN:SZ:000078",
        "2026-07-14",
    )

    assert {
        "code": "st_high_risk",
        "message": "ST高风险",
        "severity": "warning",
    } in digest["risk_flags"]


def test_strategy_lightweight_digest_distinguishes_pending_and_confirmed_lhb_states():
    pending = review_queue._strategy_lightweight_digest(
        {
            "asset_id": "CN:SZ:002463",
            "strategy_name": "LHB Shortline Combo",
            "rank": 1,
            "score_total": 77.0,
            "review_tier": "top5_focus",
            "confirmation_state": "pending_confirmation",
            "phase12a_rule_layer": "pending_intraday",
        },
        "CN:SZ:002463",
        "2026-07-14",
    )
    confirmed = review_queue._strategy_lightweight_digest(
        {
            "asset_id": "CN:SZ:002463",
            "strategy_name": "LHB Shortline Combo",
            "rank": 1,
            "score_total": 77.0,
            "review_tier": "top5_focus",
            "confirmation_state": "confirmed_follow",
            "phase12a_rule_layer": "follow_pool_core",
        },
        "CN:SZ:002463",
        "2026-07-15",
    )

    assert "Top5 次日确认待定" in pending["title"]
    assert "Top5 重点复盘" not in pending["title"]
    assert "已确认可跟踪" in confirmed["title"]


def test_manifest_strategy_reader_preserves_lhb_risk_gate_fields(tmp_path):
    artifact = tmp_path / "strategy_lhb_shortline_review.csv"
    artifact.write_text(
        "trade_date,asset_id,stock_name,rank,score_total,strategy_id,strategy_name,review_tier,"
        "stock_name_source,top5_eligible,risk_gate_code,risk_gate_reason,price_limit_regime,"
        "near_limit_down_threshold,pct_chg,confirmation_state,phase12a_rule_layer,phase12a_rule_action,fill_status\n"
        "2026-07-14,CN:SZ:001399,惠科股份,4,69.3698,lhb_shortline,LHB Shortline Combo,"
        "risk_watch,lhb_top_list_daily,False,near_limit_down_followthrough_risk,接近跌停,main_board,-9.5,-9.991,"
        "risk_watch,pending_intraday,pending,not_follow_allowed\n",
        encoding="utf-8",
    )

    rows = review_queue._read_manifest_strategy_artifact(
        artifact,
        trade_date="2026-07-14",
        limit=50,
        manifest={"run_id": "strategy-eod-2026-07-14-local", "module": "strategy_lhb_shortline"},
    )

    assert rows[0]["stock_name"] == "惠科股份"
    assert rows[0]["stock_name_source"] == "lhb_top_list_daily"
    assert rows[0]["top5_eligible"] is False
    assert rows[0]["risk_gate_code"] == "near_limit_down_followthrough_risk"
    assert rows[0]["risk_gate_reason"] == "接近跌停"
    assert rows[0]["confirmation_state"] == "risk_watch"
    assert rows[0]["phase12a_rule_layer"] == "pending_intraday"
