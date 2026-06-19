from stock_research import strategy_eod_publish


def test_review_rows_use_lhb_candidate_final_score_when_positions_have_no_score() -> None:
    review = strategy_eod_publish._review_rows_from_result(
        {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "positions": [
                {"trade_date": "2026-06-18", "ts_code": "002080.SZ"},
            ],
            "candidates": [
                {
                    "trade_date": "2026-06-18",
                    "ts_code": "002080.SZ",
                    "rank": 1,
                    "final_score": 87.6,
                }
            ],
        },
        trade_date="2026-06-18",
    )

    assert review.iloc[0]["score_total"] == 87.6
    assert review.iloc[0]["score_source"] == "final_score"


def test_review_rows_use_lhb_auction_enhanced_score_when_positions_have_no_score() -> None:
    review = strategy_eod_publish._review_rows_from_result(
        {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "positions": [
                {"trade_date": "2026-06-18", "ts_code": "002080.SZ"},
            ],
            "candidates": [
                {
                    "trade_date": "2026-06-18",
                    "ts_code": "002080.SZ",
                    "auction_enhanced_score": 110.0,
                }
            ],
        },
        trade_date="2026-06-18",
    )

    assert review.iloc[0]["score_total"] == 110.0
    assert review.iloc[0]["score_source"] == "auction_enhanced_score"


def test_review_rows_use_mid_trend_signal_score_when_positions_have_no_score() -> None:
    review = strategy_eod_publish._review_rows_from_result(
        {
            "strategy_id": "mid_trend",
            "strategy_name": "Mid Trend Combo",
            "positions": [
                {"rebalance_date": "2026-06-15", "asset_id": "CN:SZ:300951", "weight": 0.25},
            ],
            "signals": [
                {
                    "trade_date": "2026-06-15",
                    "asset_id": "CN:SZ:300951",
                    "shadow_top10_rank": 1,
                    "mid_trend_funnel_score": 91.2,
                }
            ],
        },
        trade_date="2026-06-18",
    )

    assert review.iloc[0]["score_total"] == 91.2
    assert review.iloc[0]["score_source"] == "mid_trend_funnel_score"


def test_prepare_tech_bottleneck_source_converts_legacy_seed_to_fresh_daily_source(monkeypatch, tmp_path):
    legacy_source = tmp_path / "legacy_strict_candidates.csv"
    legacy_source.write_text(
        "\n".join(
            [
                "asset_id,stock_name,first_hit_date,hit_count,primary_chain_id,primary_chain_name,matched_bottleneck_dimensions,fundamental_trade_date,filter_decision,filter_reason",
                "CN:SH:600183,生益科技,2026-05-22,3,ai_server_pcb,AI服务器PCB,delivery|materials,2026-05-19,keep,tradable_for_bottleneck_research",
                "CN:SZ:002001,新和成,2026-04-01,1,chemicals,化工,materials,,keep,tradable_for_bottleneck_research",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(strategy_eod_publish, "TECH_BOTTLENECK_V1_CANDIDATES_PATH", legacy_source)

    prepared = strategy_eod_publish._prepare_tech_bottleneck_base_candidate_source(
        trade_date="2026-06-18",
        output_dir=tmp_path / "eod",
    )

    frame = strategy_eod_publish.pd.read_csv(prepared)
    row = frame.iloc[0].to_dict()
    assert row["asset_id"] == "CN:SH:600183"
    assert row["candidate_trade_date"] == "2026-05-22"
    assert row["filter_decision"] == "pass"
    assert row["source_latest_trade_date"] == "2026-06-18"
    assert row["data_as_of_date"] == "2026-06-18"
    assert row["generated_trade_date"] == "2026-06-18"
    assert row["candidate_source_mode"] == "legacy_static_seed_daily_pit"
    fallback_row = frame[frame["asset_id"].eq("CN:SZ:002001")].iloc[0].to_dict()
    assert fallback_row["financial_as_of_date"] == "2026-04-01"


def test_strategy_eod_publish_backfills_hfq_technical_and_lhb_features(monkeypatch, tmp_path):
    calls = []
    row_checks = iter([False, False])

    monkeypatch.setattr(
        strategy_eod_publish,
        "_has_rows",
        lambda sql, trade_date: next(row_checks),
    )
    monkeypatch.setattr(
        strategy_eod_publish,
        "build_and_store_stock_technical_features_daily",
        lambda **kwargs: calls.append(("technical", kwargs)) or 5188,
    )
    monkeypatch.setattr(
        strategy_eod_publish,
        "run_lhb_event_features_build",
        lambda **kwargs: calls.append(("lhb", kwargs)) or {"lhb_event_features": [], "paths": {}},
    )

    strategy_eod_publish._ensure_strategy_dependencies(
        "2026-06-18",
        output_dir=tmp_path,
    )

    assert calls == [
        (
            "technical",
            {
                "trade_date": "2026-06-18",
                "lookback_bars": 260,
                "adjust_type": "hfq",
                "build_strategy": "latest_only",
            },
        ),
        (
            "lhb",
            {
                "start_date": "2026-06-18",
                "end_date": "2026-06-18",
                "ts_codes": None,
                "output_dir": tmp_path,
            },
        ),
    ]


def test_strategy_eod_publish_skips_existing_dependencies(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(strategy_eod_publish, "_has_rows", lambda sql, trade_date: True)
    monkeypatch.setattr(
        strategy_eod_publish,
        "build_and_store_stock_technical_features_daily",
        lambda **kwargs: calls.append(("technical", kwargs)),
    )
    monkeypatch.setattr(
        strategy_eod_publish,
        "run_lhb_event_features_build",
        lambda **kwargs: calls.append(("lhb", kwargs)),
    )

    strategy_eod_publish._ensure_strategy_dependencies(
        "2026-06-18",
        output_dir=tmp_path,
    )

    assert calls == []
