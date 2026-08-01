from datetime import datetime, timezone

import stock_research.strategy_eod_publish as strategy_eod_publish
from stock_research.strategy_eod_publish import _review_rows_from_result
import pytest
from stock_research.strategy_publication_contracts import (
    build_publication_identity,
    get_publication_contract,
)


def _lhb_result_for_review_test():
    candidates = []
    for rank, (asset_id, score) in enumerate(
        [
            ("CN:SZ:002463", 77.0),
            ("CN:SZ:000636", 76.3),
            ("CN:SZ:002384", 75.5),
            ("CN:SZ:001399", 69.3698),
            ("CN:SZ:000078", 66.0),
            ("CN:SZ:000001", 65.0),
        ],
        start=1,
    ):
        candidates.append(
            {
                "trade_date": "2026-07-14",
                "asset_id": asset_id,
                "rank": rank,
                "auction_enhanced_score": score,
                "phase12a_rule_layer": "pending_intraday",
                "stock_name": "候选原名" if rank == 1 else "",
            }
        )
    return {
        "strategy_id": "lhb_shortline",
        "strategy_name": "LHB Shortline Combo",
        "positions": [],
        "candidates": candidates,
    }


def _official_mid_result(identity: dict | None = None) -> dict:
    contract = get_publication_contract("mid_trend")
    return {
        "strategy_id": "mid_trend",
        "strategy_name": "Mid Trend Combo",
        "publication_identity": identity,
        "config": dict(contract.normalized_run_config),
        "summary": {
            "engine_version": contract.engine_version,
            "benchmark_variant": contract.variant,
            "top_n": 5,
            "transaction_cost_bps": 10.0,
            "adjust_type": "hfq",
            "frequency": "weekly",
        },
        "equity_curve": [],
        "positions": [],
        "trades": [],
    }


def test_write_strategy_artifacts_persists_validated_identity_at_metadata_top_level(tmp_path):
    identity = build_publication_identity(get_publication_contract("mid_trend"))
    entry, _review = strategy_eod_publish._write_strategy_artifacts(
        run_id="run-1",
        trade_date="2026-07-24",
        strategy_id="mid_trend",
        result=_official_mid_result(identity),
        output_dir=tmp_path,
        started_at=datetime.now(timezone.utc),
    )
    assert entry["metadata"]["publication_identity"] == identity
    assert entry["metadata"]["summary"]["publication_identity"] == identity


def test_write_strategy_artifacts_derives_contract_frequency_from_run_config(tmp_path):
    identity = build_publication_identity(get_publication_contract("mid_trend"))
    result = _official_mid_result(identity)
    result["summary"].pop("frequency")

    entry, _review = strategy_eod_publish._write_strategy_artifacts(
        run_id="run-1",
        trade_date="2026-07-24",
        strategy_id="mid_trend",
        result=result,
        output_dir=tmp_path,
        started_at=datetime.now(timezone.utc),
    )

    assert entry["metadata"]["summary"]["frequency"] == "weekly"


@pytest.mark.parametrize("identity", [None, {"strategy_id": "mid_trend"}])
def test_write_strategy_artifacts_rejects_missing_or_tampered_identity(tmp_path, identity):
    with pytest.raises(ValueError, match="publication identity"):
        strategy_eod_publish._write_strategy_artifacts(
            run_id="run-1",
            trade_date="2026-07-24",
            strategy_id="mid_trend",
            result=_official_mid_result(identity),
            output_dir=tmp_path,
            started_at=datetime.now(timezone.utc),
        )


def test_attach_tech_identity_validates_manifest_execution_config():
    contract = get_publication_contract("tech_bottleneck")
    entry = {
        "module": "strategy_tech_bottleneck",
        "metadata": {
            "summary": {
                "engine_version": contract.engine_version,
                "top_n": 5,
                "transaction_cost_bps": 10.0,
                "adjust_type": "hfq",
                "frequency": "biweekly",
                "universe": "strict_153_st_only_financial_state",
                "protection_name": "rank_exit_top10_1d",
            },
            "config": dict(contract.normalized_run_config),
        },
    }
    strategy_eod_publish._attach_tech_publication_identity([entry])
    assert entry["metadata"]["publication_identity"] == build_publication_identity(contract)

    entry["metadata"]["config"]["protection_name"] = "legacy"
    with pytest.raises(ValueError, match="protection_name"):
        strategy_eod_publish._attach_tech_publication_identity([entry])


def test_attach_tech_identity_rejects_tampered_predeclared_identity():
    contract = get_publication_contract("tech_bottleneck")
    identity = build_publication_identity(contract)
    entry = {
        "module": "strategy_tech_bottleneck",
        "metadata": {
            "publication_identity": {**identity, "variant": "legacy"},
            "summary": {
                "engine_version": contract.engine_version,
                "top_n": 5,
                "transaction_cost_bps": 10.0,
                "max_position_weight": 0.2,
                "adjust_type": "hfq",
                "frequency": "biweekly",
                "universe": "strict_153_st_only_financial_state",
                "protection_name": "rank_exit_top10_1d",
            },
            "config": dict(contract.normalized_run_config),
        },
    }

    with pytest.raises(ValueError, match="publication identity mismatch"):
        strategy_eod_publish._attach_tech_publication_identity([entry])


def test_lhb_review_publishes_original_top5_after_gate_without_refill(monkeypatch):
    lookup = {
        "CN:SZ:002463": {"score_total": 77.0, "stock_name": "沪电股份", "pct_chg": 2.0},
        "CN:SZ:000636": {"score_total": 76.3, "stock_name": "风华高科", "pct_chg": 1.0},
        "CN:SZ:002384": {"score_total": 75.5, "stock_name": "东山精密", "pct_chg": 0.5},
        "CN:SZ:001399": {
            "score_total": 69.3698,
            "stock_name": "惠科股份",
            "stock_name_source": "lhb_top_list_daily",
            "pct_chg": -9.991,
        },
        "CN:SZ:000078": {"score_total": 66.0, "stock_name": "ST海王", "pct_chg": 1.0},
        "CN:SZ:000001": {"score_total": 65.0, "stock_name": "平安银行", "pct_chg": 1.0},
    }
    monkeypatch.setattr(strategy_eod_publish, "_lhb_base_score_lookup_for_trade_date", lambda trade_date: lookup)

    review = _review_rows_from_result(_lhb_result_for_review_test(), trade_date="2026-07-14")

    first = review.loc[review["asset_id"].eq("CN:SZ:002463")].iloc[0]
    assert first["stock_name"] == "候选原名"
    assert first["stock_name_source"] == "strategy_candidate"
    assert review["rank"].tolist() == [1, 2, 3, 5]
    assert "CN:SZ:001399" not in set(review["asset_id"])
    assert "CN:SZ:000001" not in set(review["asset_id"])
    assert review["review_tier"].eq("top5_focus").all()
    assert review.loc[review["review_tier"].eq("top5_focus"), "confirmation_state"].eq("pending_confirmation").all()
    st_row = review.loc[review["asset_id"].eq("CN:SZ:000078")].iloc[0]
    assert st_row["buy_signal_status"] == "tradable"
    assert "st_high_risk" in st_row["eligibility_warning_codes"]


@pytest.mark.parametrize(
    ("layer", "action", "fill_status", "eligibility_status", "expected"),
    [
        ("pending_intraday", "pending", "not_follow_allowed", "eligible", "pending_confirmation"),
        ("follow_pool_core", "follow_allowed", "filled", "eligible", "confirmed_follow"),
        ("watch_pool", "watch_only", "not_follow_allowed", "eligible", "watch_only"),
        ("retreat_hard", "retreat", "not_follow_allowed", "eligible", "retreat"),
        ("pending_intraday", "pending", "not_follow_allowed", "risk_watch", "risk_watch"),
    ],
)
def test_lhb_confirmation_state_mapping(layer, action, fill_status, eligibility_status, expected):
    assert strategy_eod_publish._lhb_confirmation_state(
        phase12a_rule_layer=layer,
        phase12a_rule_action=action,
        fill_status=fill_status,
        eligibility_status=eligibility_status,
    ) == expected


def test_lhb_review_excludes_upstream_risk_watch_from_official_rows(monkeypatch):
    result = _lhb_result_for_review_test()
    candidate = result["candidates"][3]
    candidate.pop("auction_enhanced_score")
    candidate.update(
        {
            "auction_enhanced_score": 20.0,
            "selection_score": 618.3,
            "phase12a_rule_layer": "risk_watch",
            "eligibility_status": "risk_watch",
            "top5_eligible": False,
            "backtest_entry_eligible": False,
            "eligibility_reason_codes": ["near_limit_down_followthrough_risk"],
            "eligibility_reason_texts": ["接近跌停，禁止进入跟随和回测交易"],
            "eligibility_warning_codes": ["institution_activity_unknown"],
            "eligibility_contract_version": "lhb_eligibility_v2",
            "price_limit_regime": "main_board",
            "near_limit_down_threshold": -9.5,
            "data_quality_status": "complete",
            "pct_chg": 2.0,
        }
    )
    monkeypatch.setattr(
        strategy_eod_publish,
        "_lhb_base_score_lookup_for_trade_date",
        lambda trade_date: {
            "CN:SZ:001399": {
                "score_total": 69.3698,
                "stock_name": "惠科股份",
                "pct_chg": 2.0,
            }
        },
    )

    review = _review_rows_from_result(result, trade_date="2026-07-14")

    assert "CN:SZ:001399" not in set(review["asset_id"])
    assert review["eligibility_status"].eq("eligible").all()
    assert review["backtest_entry_eligible"].astype(bool).all()


def test_lhb_review_rejects_contradictory_upstream_eligibility(monkeypatch):
    result = _lhb_result_for_review_test()
    result["candidates"][0].update(
        {
            "eligibility_status": "eligible",
            "top5_eligible": False,
            "backtest_entry_eligible": True,
            "eligibility_reason_codes": [],
            "eligibility_warning_codes": [],
            "eligibility_contract_version": "lhb_eligibility_v2",
        }
    )
    monkeypatch.setattr(strategy_eod_publish, "_lhb_base_score_lookup_for_trade_date", lambda trade_date: {})

    with pytest.raises(ValueError, match="LHB eligibility parity violation"):
        _review_rows_from_result(result, trade_date="2026-07-14")


def test_load_lhb_base_score_source_prefers_master_name_then_lhb_name(monkeypatch):
    queries = []

    class DummyConnection:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_fetch_all(conn, sql, params):
        queries.append(sql)
        return []

    monkeypatch.setattr(strategy_eod_publish, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(strategy_eod_publish, "fetch_all", fake_fetch_all)

    strategy_eod_publish._load_lhb_base_score_source_frames("2026-07-14")

    lhb_sql = queries[0]
    assert "COALESCE(NULLIF(a.name, ''), NULLIF(t.name, '')) AS stock_name" in lhb_sql
    assert "AS stock_name_source" in lhb_sql
    assert "market.lhb_top_list_daily" in lhb_sql
    assert "pct_chg" in lhb_sql


def test_mid_trend_review_uses_latest_signal_score_for_continued_holdings():
    result = {
        "strategy_id": "mid_trend",
        "strategy_name": "Mid Trend Combo",
        "positions": [
            {"rebalance_date": "2026-06-22", "asset_id": "CN:SH:603733", "weight": 0.2},
        ],
        "trades": [
            {
                "trade_date": "2026-06-22",
                "asset_id": "CN:SH:603733",
                "target_weight": 0.2,
            }
        ],
        "signals": [
            {
                "trade_date": "2026-06-15",
                "asset_id": "CN:SH:603733",
                "mid_trend_funnel_score": 81.639212,
            }
        ],
    }

    review = _review_rows_from_result(result, trade_date="2026-06-29")

    assert review.loc[0, "asset_id"] == "CN:SH:603733"
    assert review.loc[0, "score_total"] == 81.639212
    assert review.loc[0, "score_source"] == "mid_trend_funnel_score"


def test_mid_trend_review_uses_current_daily_score_for_holding_missing_signal(monkeypatch):
    class DummyConnection:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_connect(service):
        return DummyConnection()

    def fake_fetch_all(conn, sql, params):
        assert params == ["manual_v1", "2026-06-30", ["CN:SH:603690"]]
        return [{"asset_id": "CN:SH:603690", "score_total": 75.4086865826214}]

    monkeypatch.setattr(strategy_eod_publish, "connect", fake_connect)
    monkeypatch.setattr(strategy_eod_publish, "fetch_all", fake_fetch_all)
    result = {
        "strategy_id": "mid_trend",
        "strategy_name": "Mid Trend Combo",
        "positions": [
            {"rebalance_date": "2026-06-29", "asset_id": "CN:SH:603690", "weight": 0.2},
        ],
        "trades": [
            {
                "trade_date": "2026-06-29",
                "asset_id": "CN:SH:603690",
                "target_weight": 0.2,
            }
        ],
        "signals": [],
    }

    review = _review_rows_from_result(result, trade_date="2026-06-30")

    assert review.loc[0, "asset_id"] == "CN:SH:603690"
    assert review.loc[0, "score_total"] == 75.4086865826214
    assert review.loc[0, "score_source"] == "mid_trend_funnel_score"


def test_base_manifest_entries_marks_small_daily_gap_degraded_publishable(monkeypatch):
    def fake_load_base_check_rows(trade_date):
        return {
            "daily_bars": {
                "row_count": 15561,
                "asset_count": 5187,
                "latest_trade_date": trade_date,
                "missing_count": 66,
                "expected_count": 15627,
            },
            "technical_features": {
                "row_count": 5187,
                "asset_count": 5187,
                "latest_trade_date": trade_date,
            },
            "score_topn": {
                "row_count": 5187,
                "asset_count": 5187,
                "latest_trade_date": trade_date,
            },
            "lhb_features": {
                "row_count": 104,
                "asset_count": 104,
                "latest_trade_date": trade_date,
            },
        }

    monkeypatch.setattr(strategy_eod_publish, "_load_base_check_rows", fake_load_base_check_rows)

    entries = strategy_eod_publish._build_base_manifest_entries(
        run_id="run-1",
        trade_date="2026-07-01",
        started_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    daily = next(entry for entry in entries if entry["module"] == "daily_bars")
    assert daily["status"] == "partial"
    assert "degraded" in " ".join(daily["warnings"])
    assert strategy_eod_publish._base_entries_publishable(entries) is True


def test_base_manifest_entries_blocks_missing_score_topn(monkeypatch):
    def fake_load_base_check_rows(trade_date):
        return {
            "daily_bars": {"row_count": 5187, "asset_count": 5187, "latest_trade_date": trade_date},
            "technical_features": {"row_count": 5187, "asset_count": 5187, "latest_trade_date": trade_date},
            "score_topn": {"row_count": 0, "asset_count": 0, "latest_trade_date": ""},
            "lhb_features": {"row_count": 104, "asset_count": 104, "latest_trade_date": trade_date},
        }

    monkeypatch.setattr(strategy_eod_publish, "_load_base_check_rows", fake_load_base_check_rows)

    entries = strategy_eod_publish._build_base_manifest_entries(
        run_id="run-1",
        trade_date="2026-07-01",
        started_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    assert strategy_eod_publish._base_entries_publishable(entries) is False


def test_base_manifest_entries_blocks_daily_gap_above_tolerance(monkeypatch):
    def fake_load_base_check_rows(trade_date):
        return {
            "daily_bars": {
                "row_count": 98,
                "asset_count": 98,
                "latest_trade_date": trade_date,
                "missing_count": 2,
                "expected_count": 100,
            },
            "technical_features": {"row_count": 100, "asset_count": 100, "latest_trade_date": trade_date},
            "score_topn": {"row_count": 100, "asset_count": 100, "latest_trade_date": trade_date},
            "lhb_features": {"row_count": 10, "asset_count": 10, "latest_trade_date": trade_date},
        }

    monkeypatch.setattr(strategy_eod_publish, "_load_base_check_rows", fake_load_base_check_rows)

    entries = strategy_eod_publish._build_base_manifest_entries(
        run_id="run-1",
        trade_date="2026-07-01",
        started_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    daily = next(entry for entry in entries if entry["module"] == "daily_bars")
    assert daily["status"] == "unavailable"
    assert "exceeds tolerance" in " ".join(daily["warnings"])
    assert strategy_eod_publish._base_entries_publishable(entries) is False


def test_daily_bars_base_check_sql_loads_quality_gap_fields():
    sql = strategy_eod_publish.BASE_CHECKS["daily_bars"]["sql"]
    outer_select = sql.split("FROM bars", maxsplit=1)[0]

    assert "ops.daily_pipeline_quality" in sql
    assert "quality.expected_count" in outer_select
    assert "quality.missing_count" in outer_select
    assert "quality.abnormal_count" in outer_select


def test_load_base_check_rows_preserves_daily_quality_gap_fields(monkeypatch):
    queries = []

    class DummyConnection:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_fetch_all(conn, sql, params):
        queries.append(sql)
        if "ops.daily_pipeline_quality" in sql:
            return [
                {
                    "row_count": 15561,
                    "asset_count": 5187,
                    "latest_trade_date": "2026-07-01",
                    "expected_count": 15627,
                    "missing_count": 66,
                    "abnormal_count": 0,
                }
            ]
        return [{"row_count": 1, "asset_count": 1, "latest_trade_date": "2026-07-01"}]

    monkeypatch.setattr(strategy_eod_publish, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(strategy_eod_publish, "fetch_all", fake_fetch_all)

    rows = strategy_eod_publish._load_base_check_rows("2026-07-01")

    assert rows["daily_bars"]["expected_count"] == 15627
    assert rows["daily_bars"]["missing_count"] == 66
    assert any("ops.daily_pipeline_quality" in query for query in queries)


def test_publish_strategy_eod_upserts_failure_manifest_when_base_not_publishable(monkeypatch, tmp_path):
    upserts = []

    def fake_base_entries(**kwargs):
        return [
            {
                "run_id": kwargs["run_id"],
                "run_date": "2026-07-01",
                "trade_date": kwargs["trade_date"],
                "module": "score_topn",
                "source": "factor.stock_score_daily",
                "tier": "tier1",
                "status": "unavailable",
            }
        ]

    monkeypatch.setattr(strategy_eod_publish, "_ensure_strategy_dependencies", lambda *args, **kwargs: None)
    monkeypatch.setattr(strategy_eod_publish, "_build_base_manifest_entries", fake_base_entries)

    with pytest.raises(RuntimeError, match="base data checks did not all pass"):
        strategy_eod_publish.publish_strategy_eod(
            trade_date="2026-07-01",
            output_root=tmp_path,
            manifest_upsert=lambda entry: upserts.append(entry),
        )

    assert [entry["module"] for entry in upserts] == ["score_topn", "review_queue_strategy_manifest"]
    assert upserts[-1]["status"] == "failed"


def _install_publish_contract_fakes(
    monkeypatch,
    tmp_path,
    *,
    strategy_assets,
    extra_rows=(),
    review_mutator=lambda strategy_id, frame: frame,
):
    monkeypatch.setattr(strategy_eod_publish, "_ensure_strategy_dependencies", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        strategy_eod_publish,
        "_build_base_manifest_entries",
        lambda **kwargs: [{"module": "daily_bars", "status": "success"}],
    )

    def fake_write_strategy_artifacts(*, strategy_id, **kwargs):
        frame = strategy_eod_publish.pd.DataFrame(
            {
                "trade_date": [kwargs["trade_date"]] * len(strategy_assets[strategy_id]),
                "strategy_id": [strategy_id] * len(strategy_assets[strategy_id]),
                "asset_id": strategy_assets[strategy_id],
                "rank": list(range(1, len(strategy_assets[strategy_id]) + 1)),
                "review_tier": ["top5_focus"] * len(strategy_assets[strategy_id]),
            }
        )
        frame = review_mutator(strategy_id, frame)
        return {
            "module": strategy_eod_publish.STRATEGY_EOD_MODULES[strategy_id],
            "status": "success",
            "metadata": {
                "publication_identity": build_publication_identity(
                    get_publication_contract(strategy_id)
                )
            },
        }, frame

    monkeypatch.setattr(strategy_eod_publish, "_write_strategy_artifacts", fake_write_strategy_artifacts)
    monkeypatch.setattr(
        strategy_eod_publish,
        "_prepare_tech_bottleneck_base_candidate_source",
        lambda **kwargs: tmp_path / "tech-base.csv",
    )

    def fake_tech_publish(*, end_date, output_dir, manifest_upsert, **kwargs):
        contract = get_publication_contract("tech_bottleneck")
        review_path = output_dir / "strategy_tech_bottleneck_review.csv"
        tech_review = strategy_eod_publish.pd.DataFrame(
            {
                "trade_date": [end_date] * len(strategy_assets["tech_bottleneck"]),
                "strategy_id": ["tech_bottleneck"] * len(strategy_assets["tech_bottleneck"]),
                "asset_id": strategy_assets["tech_bottleneck"],
                "rank": list(range(1, len(strategy_assets["tech_bottleneck"]) + 1)),
                "review_tier": ["top5_focus"] * len(strategy_assets["tech_bottleneck"]),
            }
        )
        tech_review = review_mutator("tech_bottleneck", tech_review)
        if extra_rows:
            tech_review = strategy_eod_publish.pd.concat(
                [tech_review, strategy_eod_publish.pd.DataFrame(extra_rows)],
                ignore_index=True,
            )
        tech_review.to_csv(review_path, index=False)
        manifest_upsert(
            {
                "module": "strategy_tech_bottleneck",
                "status": "success",
                "metadata": {
                    "config": dict(contract.normalized_run_config),
                    "summary": {
                        "engine_version": contract.engine_version,
                        "top_n": 5,
                        "transaction_cost_bps": 10.0,
                        "max_position_weight": 0.2,
                        "adjust_type": "hfq",
                        "frequency": "biweekly",
                        "universe": "strict_153_st_only_financial_state",
                        "protection_name": "rank_exit_top10_1d",
                    },
                },
            }
        )
        return {"review_path": str(review_path)}

    monkeypatch.setattr(strategy_eod_publish, "run_tech_bottleneck_eod", fake_tech_publish)
    monkeypatch.setattr(strategy_eod_publish, "_write_strategy_score_audit_artifacts", lambda **kwargs: {"status": "success"})
    monkeypatch.setattr(strategy_eod_publish, "_write_eod_news_artifacts", lambda **kwargs: [])
    monkeypatch.setattr(strategy_eod_publish, "_write_report_content_manifest_entries", lambda **kwargs: [])
    monkeypatch.setattr(
        strategy_eod_publish,
        "_write_review_evidence_snapshot_entry",
        lambda **kwargs: {"module": "review_evidence_snapshots", "status": "success"},
    )


def test_publish_strategy_eod_returns_exact_review_counts_and_collected_entries(monkeypatch, tmp_path):
    strategy_assets = {
        strategy_id: [f"CN:SH:{index:06d}" for index in range(offset, offset + 5)]
        for strategy_id, offset in (("lhb_shortline", 1), ("mid_trend", 101), ("tech_bottleneck", 201))
    }
    _install_publish_contract_fakes(monkeypatch, tmp_path, strategy_assets=strategy_assets)
    collected = []

    summary = strategy_eod_publish.publish_strategy_eod(
        trade_date="2026-07-24",
        output_root=tmp_path,
        runner=lambda payload: {"strategy_id": payload["strategy_id"]},
        manifest_upsert=collected.append,
    )

    assert summary["strategy_counts"] == {
        "lhb_shortline": 5,
        "mid_trend": 5,
        "tech_bottleneck": 5,
    }
    assert summary["review_rows"] == 15
    assert summary["publishable"] is True
    assert {entry["module"] for entry in collected} >= {
        "strategy_lhb_shortline",
        "strategy_mid_trend",
        "strategy_tech_bottleneck",
        "review_queue_strategy_manifest",
    }
    assert "manifest_entries" not in summary


def test_publish_strategy_eod_accepts_four_safe_lhb_rows_as_degraded(monkeypatch, tmp_path):
    strategy_assets = {
        "lhb_shortline": [f"CN:SH:{index:06d}" for index in range(1, 5)],
        "mid_trend": [f"CN:SH:{index:06d}" for index in range(101, 106)],
        "tech_bottleneck": [f"CN:SH:{index:06d}" for index in range(201, 206)],
    }
    _install_publish_contract_fakes(monkeypatch, tmp_path, strategy_assets=strategy_assets)

    summary = strategy_eod_publish.publish_strategy_eod(
        trade_date="2026-07-30",
        output_root=tmp_path,
        runner=lambda payload: {"strategy_id": payload["strategy_id"]},
        manifest_upsert=lambda entry: None,
    )

    assert summary["status"] == "degraded"
    assert summary["publishable"] is True
    assert summary["review_rows"] == 14
    assert summary["strategy_counts"]["lhb_shortline"] == 4
    assert summary["degraded_strategies"] == ["lhb_shortline"]
    assert any("lhb_shortline" in warning for warning in summary["warnings"])


@pytest.mark.parametrize(
    "lhb_assets",
    [
        [],
        ["CN:SH:000001"] * 5,
        [f"CN:SH:{index:06d}" for index in range(1, 6)] + ["CN:SH:000005"],
    ],
)
def test_publish_strategy_eod_rejects_invalid_unique_asset_count(monkeypatch, tmp_path, lhb_assets):
    strategy_assets = {
        "lhb_shortline": lhb_assets,
        "mid_trend": [f"CN:SH:{index:06d}" for index in range(101, 106)],
        "tech_bottleneck": [f"CN:SH:{index:06d}" for index in range(201, 206)],
    }
    _install_publish_contract_fakes(monkeypatch, tmp_path, strategy_assets=strategy_assets)
    collected = []

    with pytest.raises(RuntimeError, match="strategy review contract requires exactly 5 rows per strategy"):
        strategy_eod_publish.publish_strategy_eod(
            trade_date="2026-07-24",
            output_root=tmp_path,
            runner=lambda payload: {"strategy_id": payload["strategy_id"]},
            manifest_upsert=collected.append,
        )

    assert not any(
        entry.get("module") == "review_queue_strategy_manifest" and entry.get("status") == "success"
        for entry in collected
    )


@pytest.mark.parametrize(
    "extra_row",
    [
        {"trade_date": "2026-07-24", "strategy_id": "", "asset_id": ""},
        {
            "trade_date": "2026-07-24",
            "strategy_id": "unknown_strategy",
            "asset_id": "CN:SH:999999",
            "rank": 1,
            "review_tier": "top5_focus",
        },
    ],
)
def test_publish_strategy_eod_rejects_extra_malformed_or_unknown_review_row(monkeypatch, tmp_path, extra_row):
    strategy_assets = {
        "lhb_shortline": [f"CN:SH:{index:06d}" for index in range(1, 6)],
        "mid_trend": [f"CN:SH:{index:06d}" for index in range(101, 106)],
        "tech_bottleneck": [f"CN:SH:{index:06d}" for index in range(201, 206)],
    }
    _install_publish_contract_fakes(
        monkeypatch,
        tmp_path,
        strategy_assets=strategy_assets,
        extra_rows=[extra_row],
    )
    collected = []

    with pytest.raises(RuntimeError, match="strategy review contract requires exactly 5 rows per strategy"):
        strategy_eod_publish.publish_strategy_eod(
            trade_date="2026-07-24",
            output_root=tmp_path,
            runner=lambda payload: {"strategy_id": payload["strategy_id"]},
            manifest_upsert=collected.append,
        )

    aggregate_entries = [
        entry for entry in collected if entry.get("module") == "review_queue_strategy_manifest"
    ]
    assert [entry.get("status") for entry in aggregate_entries] == ["failed"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trade_date", "2026-07-23"),
        ("rank", 99),
        ("rank", 1),
        ("review_tier", "watch"),
    ],
)
def test_publish_strategy_eod_rejects_invalid_review_row_contract(monkeypatch, tmp_path, field, value):
    strategy_assets = {
        "lhb_shortline": [f"CN:SH:{index:06d}" for index in range(1, 6)],
        "mid_trend": [f"CN:SH:{index:06d}" for index in range(101, 106)],
        "tech_bottleneck": [f"CN:SH:{index:06d}" for index in range(201, 206)],
    }

    def mutate(strategy_id, frame):
        if strategy_id == "lhb_shortline":
            frame = frame.copy()
            frame.loc[4, field] = value
        return frame

    _install_publish_contract_fakes(
        monkeypatch,
        tmp_path,
        strategy_assets=strategy_assets,
        review_mutator=mutate,
    )
    collected = []

    with pytest.raises(RuntimeError, match="strategy review contract requires exactly 5 rows per strategy"):
        strategy_eod_publish.publish_strategy_eod(
            trade_date="2026-07-24",
            output_root=tmp_path,
            runner=lambda payload: {"strategy_id": payload["strategy_id"]},
            manifest_upsert=collected.append,
        )

    aggregate_entries = [
        entry for entry in collected if entry.get("module") == "review_queue_strategy_manifest"
    ]
    assert [entry.get("status") for entry in aggregate_entries] == ["failed"]
    assert not any(
        entry.get("module") == "strategy_lhb_shortline" and entry.get("status") == "success"
        for entry in collected
    )
    assert any(
        entry.get("module") == "strategy_lhb_shortline" and entry.get("status") == "failed"
        for entry in collected
    )


def test_publish_strategy_eod_replaces_duplicate_asset_strategy_success_with_failure(monkeypatch, tmp_path):
    strategy_assets = {
        "lhb_shortline": ["CN:SH:000001"] * 5,
        "mid_trend": [f"CN:SH:{index:06d}" for index in range(101, 106)],
        "tech_bottleneck": [f"CN:SH:{index:06d}" for index in range(201, 206)],
    }
    _install_publish_contract_fakes(monkeypatch, tmp_path, strategy_assets=strategy_assets)
    collected = []

    with pytest.raises(RuntimeError, match="strategy review contract requires exactly 5 rows per strategy"):
        strategy_eod_publish.publish_strategy_eod(
            trade_date="2026-07-24",
            output_root=tmp_path,
            runner=lambda payload: {"strategy_id": payload["strategy_id"]},
            manifest_upsert=collected.append,
        )

    lhb_entries = [entry for entry in collected if entry.get("module") == "strategy_lhb_shortline"]
    assert not any(entry.get("status") == "success" for entry in lhb_entries)
    assert any(entry.get("status") == "failed" for entry in lhb_entries)


@pytest.mark.parametrize(
    "lhb_assets",
    [
        ["CN:SH:000001", "000001.SH", "CN:SH:000002", "CN:SH:000003", "CN:SH:000004"],
        ["CN:SH:000001", "CN:SH:000002", "CN:SH:000003", "CN:SH:000004", "nan"],
    ],
)
def test_publish_strategy_eod_rejects_noncanonical_or_equivalent_duplicate_assets(monkeypatch, tmp_path, lhb_assets):
    strategy_assets = {
        "lhb_shortline": lhb_assets,
        "mid_trend": [f"CN:SH:{index:06d}" for index in range(101, 106)],
        "tech_bottleneck": [f"CN:SH:{index:06d}" for index in range(201, 206)],
    }
    _install_publish_contract_fakes(monkeypatch, tmp_path, strategy_assets=strategy_assets)
    collected = []

    with pytest.raises(RuntimeError, match="strategy review contract requires exactly 5 rows per strategy"):
        strategy_eod_publish.publish_strategy_eod(
            trade_date="2026-07-24",
            output_root=tmp_path,
            runner=lambda payload: {"strategy_id": payload["strategy_id"]},
            manifest_upsert=collected.append,
        )

    lhb_entries = [entry for entry in collected if entry.get("module") == "strategy_lhb_shortline"]
    assert not any(entry.get("status") == "success" for entry in lhb_entries)
    assert any(entry.get("status") == "failed" for entry in lhb_entries)


def test_publish_strategy_eod_rejects_boolean_rank(monkeypatch, tmp_path):
    strategy_assets = {
        "lhb_shortline": [f"CN:SH:{index:06d}" for index in range(1, 6)],
        "mid_trend": [f"CN:SH:{index:06d}" for index in range(101, 106)],
        "tech_bottleneck": [f"CN:SH:{index:06d}" for index in range(201, 206)],
    }

    def mutate(strategy_id, frame):
        if strategy_id == "lhb_shortline":
            frame = frame.astype({"rank": object})
            frame.loc[0, "rank"] = True
        return frame

    _install_publish_contract_fakes(
        monkeypatch,
        tmp_path,
        strategy_assets=strategy_assets,
        review_mutator=mutate,
    )

    with pytest.raises(RuntimeError, match="strategy review contract requires exactly 5 rows per strategy"):
        strategy_eod_publish.publish_strategy_eod(
            trade_date="2026-07-24",
            output_root=tmp_path,
            runner=lambda payload: {"strategy_id": payload["strategy_id"]},
            manifest_upsert=lambda entry: None,
        )
