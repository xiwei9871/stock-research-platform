from stock_research import strategy_eod_publish


def test_write_eod_news_artifacts_builds_features_enrichment_and_manifest(monkeypatch, tmp_path):
    calls = []
    review_rows = strategy_eod_publish.pd.DataFrame(
        [
            {
                "trade_date": "2026-06-18",
                "asset_id": "CN:SZ:002080",
                "rank": 1,
                "score_total": 87.6,
                "strategy_name": "LHB Shortline Combo",
            }
        ]
    )
    mentions = strategy_eod_publish.pd.DataFrame(
        [
            {
                "source_event_id": "n1",
                "asset_id": "CN:SZ:002080",
                "ts_code": "002080.SZ",
                "stock_name": "中材科技",
                "mapping_method": "stock_name_exact",
                "trade_date": "2026-06-18",
                "published_at": "2026-06-18 10:00:00+08:00",
                "source_name": "sina_finance",
                "event_family": "",
                "source_channel": "market",
                "title": "中材科技获得大单 主力资金流入",
                "content": "",
            }
        ]
    )
    source_events = strategy_eod_publish.pd.DataFrame(
        [
            {
                "source_event_id": "n1",
                "source_name": "sina_finance",
                "title": "中材科技获得大单 主力资金流入",
                "published_at": "2026-06-18 10:00:00+08:00",
                "quality_score": 82,
            }
        ]
    )
    monkeypatch.setattr(strategy_eod_publish, "_load_eod_public_news_events", lambda trade_date: source_events)
    monkeypatch.setattr(strategy_eod_publish, "_load_eod_news_mentions", lambda trade_date: mentions)
    monkeypatch.setattr(
        strategy_eod_publish,
        "_persist_news_features",
        lambda features, trade_date: calls.append(("persist_features", trade_date, len(features))),
    )

    entries = strategy_eod_publish._write_eod_news_artifacts(
        run_id="strategy-eod-2026-06-18-local",
        trade_date="2026-06-18",
        output_dir=tmp_path,
        review_rows=review_rows,
        started_at=strategy_eod_publish.datetime.now(strategy_eod_publish.timezone.utc),
    )

    modules = {entry["module"]: entry for entry in entries}
    assert modules["news"]["status"] == "success"
    assert modules["news"]["row_count"] == 1
    assert modules["news_features"]["status"] == "success"
    assert modules["news_features"]["asset_count"] == 1
    assert modules["news_enrichment"]["status"] == "success"
    assert modules["news_enrichment"]["row_count"] == 1
    assert calls == [("persist_features", "2026-06-18", 1)]
    assert (tmp_path / "public_news_events.csv").exists()
    assert (tmp_path / "news_feature_daily.csv").exists()
    assert (tmp_path / "topn_news_enrichment.csv").exists()


def test_write_review_evidence_snapshot_entry_uses_snapshot_runner(tmp_path):
    result = {
        "status": "success",
        "row_count": 4,
        "asset_count": 2,
        "review_item_snapshot_count": 2,
        "evidence_digest_snapshot_count": 2,
        "warnings": [],
        "errors": [],
        "artifact_path": str(tmp_path / "review_evidence_snapshots_summary.json"),
        "snapshot_status": "success",
    }
    calls = []

    entry = strategy_eod_publish._write_review_evidence_snapshot_entry(
        run_id="strategy-eod-2026-06-18-local",
        trade_date="2026-06-18",
        output_dir=tmp_path,
        started_at=strategy_eod_publish.datetime.now(strategy_eod_publish.timezone.utc),
        snapshot_runner=lambda **kwargs: calls.append(kwargs) or result,
    )

    assert calls == [
        {
            "run_id": "strategy-eod-2026-06-18-local",
            "trade_date": "2026-06-18",
            "output_dir": tmp_path,
            "limit": 30,
        }
    ]
    assert entry["module"] == "review_evidence_snapshots"
    assert entry["status"] == "success"
    assert entry["row_count"] == 4
    assert entry["asset_count"] == 2
    assert entry["metadata"]["review_item_snapshot_count"] == 2
    assert entry["metadata"]["evidence_digest_snapshot_count"] == 2


def test_write_report_content_manifest_entries_marks_reports_ready(monkeypatch, tmp_path):
    generated = tmp_path / "daily_report_2026-06-18.md"
    generated.write_text("report", encoding="utf-8")
    monkeypatch.setattr(
        strategy_eod_publish,
        "_load_research_report_manifest_stats",
        lambda trade_date: {
            "row_count": 42,
            "asset_count": 12,
            "latest_trade_date": "2026-06-18",
        },
    )
    monkeypatch.setattr(strategy_eod_publish, "DEFAULT_REPORTS_DIR", tmp_path)

    entries = strategy_eod_publish._write_report_content_manifest_entries(
        run_id="strategy-eod-2026-06-18-local",
        trade_date="2026-06-18",
        started_at=strategy_eod_publish.datetime.now(strategy_eod_publish.timezone.utc),
    )

    modules = {entry["module"]: entry for entry in entries}
    assert modules["research_reports"]["status"] == "success"
    assert modules["research_reports"]["row_count"] == 42
    assert modules["research_reports"]["asset_count"] == 12
    assert modules["generated_reports"]["status"] == "success"
    assert modules["generated_reports"]["row_count"] == 1
    assert modules["generated_reports"]["artifact_path"] == str(generated)


def test_strategy_payload_uses_official_10bps_and_20pct_position_cap() -> None:
    lhb = strategy_eod_publish._strategy_payload("lhb_shortline", "2026-06-18")
    mid = strategy_eod_publish._strategy_payload("mid_trend", "2026-06-18")

    assert lhb["transaction_cost_bps"] == 10.0
    assert lhb["max_position_weight"] == 0.2
    assert mid["transaction_cost_bps"] == 10.0
    assert mid["max_position_weight"] == 0.2


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


def test_review_rows_use_same_day_lhb_candidates_when_positions_are_stale() -> None:
    review = strategy_eod_publish._review_rows_from_result(
        {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "positions": [
                {"trade_date": "2026-06-16", "ts_code": "002080.SZ"},
                {"trade_date": "2026-06-16", "ts_code": "002436.SZ"},
            ],
            "candidates": [
                {
                    "trade_date": "2026-06-22",
                    "ts_code": "000960.SZ",
                    "phase12a_rule_layer": "pending_intraday",
                    "auction_enhanced_score": 20.0,
                },
                {
                    "trade_date": "2026-06-22",
                    "ts_code": "002691.SZ",
                    "phase12a_rule_layer": "pending_intraday",
                    "auction_enhanced_score": 18.0,
                },
            ],
        },
        trade_date="2026-06-22",
    )

    assert review["asset_id"].tolist() == ["000960.SZ", "002691.SZ"]
    assert review["score_total"].tolist() == [20.0, 18.0]
    assert review["trade_date"].tolist() == ["2026-06-22", "2026-06-22"]


def test_lhb_same_day_candidate_frame_preserves_lineage_fields_for_audit() -> None:
    frame = strategy_eod_publish._lhb_same_day_candidate_frame(
        {
            "candidates": [
                {
                    "trade_date": "2026-06-21",
                    "ts_code": "002080.SZ",
                    "phase12a_rule_layer": "follow_pool_core",
                    "candidate_reason": "stale_row",
                    "auction_enhanced_score": 12.0,
                },
                {
                    "trade_date": "2026-06-22",
                    "ts_code": "000960.SZ",
                    "phase12a_rule_layer": "pending_intraday",
                    "candidate_reason": "lhb_capital_plus_structure",
                    "auction_enhanced_score": 20.0,
                },
            ]
        },
        trade_date="2026-06-22",
    )

    assert frame["ts_code"].tolist() == ["000960.SZ"]
    assert frame["trade_date"].tolist() == ["2026-06-22"]
    assert frame.iloc[0]["phase12a_rule_layer"] == "pending_intraday"
    assert frame.iloc[0]["candidate_reason"] == "lhb_capital_plus_structure"
    assert frame.iloc[0]["auction_enhanced_score"] == 20.0


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
