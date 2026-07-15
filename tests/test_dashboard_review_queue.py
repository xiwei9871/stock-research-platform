from stock_research.dashboard import review_queue


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


def test_manifest_strategy_reader_preserves_lhb_risk_gate_fields(tmp_path):
    artifact = tmp_path / "strategy_lhb_shortline_review.csv"
    artifact.write_text(
        "trade_date,asset_id,stock_name,rank,score_total,strategy_id,strategy_name,review_tier,"
        "stock_name_source,top5_eligible,risk_gate_code,risk_gate_reason,price_limit_regime,"
        "near_limit_down_threshold,pct_chg\n"
        "2026-07-14,CN:SZ:001399,惠科股份,4,69.3698,lhb_shortline,LHB Shortline Combo,"
        "risk_watch,lhb_top_list_daily,False,near_limit_down_followthrough_risk,接近跌停,main_board,-9.5,-9.991\n",
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
