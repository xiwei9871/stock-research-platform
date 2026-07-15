from datetime import datetime, timezone

import stock_research.strategy_eod_publish as strategy_eod_publish
from stock_research.strategy_eod_publish import _review_rows_from_result
import pytest


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


def test_lhb_review_resolves_names_and_downgrades_limit_down_candidate(monkeypatch):
    lookup = {
        "CN:SZ:002463": {"score_total": 77.0, "stock_name": "沪电股份", "pct_chg": 2.0},
        "CN:SZ:000636": {"score_total": 76.3, "stock_name": "风华高科", "pct_chg": 1.0},
        "CN:SZ:002384": {"score_total": 75.5, "stock_name": "东山精密", "pct_chg": 0.5},
        "CN:SZ:001399": {"score_total": 69.3698, "stock_name": "惠科股份", "pct_chg": -9.991},
        "CN:SZ:000078": {"score_total": 66.0, "stock_name": "ST海王", "pct_chg": 1.0},
        "CN:SZ:000001": {"score_total": 65.0, "stock_name": "平安银行", "pct_chg": 1.0},
    }
    monkeypatch.setattr(strategy_eod_publish, "_lhb_base_score_lookup_for_trade_date", lambda trade_date: lookup)

    review = _review_rows_from_result(_lhb_result_for_review_test(), trade_date="2026-07-14")

    first = review.loc[review["asset_id"].eq("CN:SZ:002463")].iloc[0]
    gated = review.loc[review["asset_id"].eq("CN:SZ:001399")].iloc[0]
    assert first["stock_name"] == "候选原名"
    assert gated["stock_name"] == "惠科股份"
    assert gated["score_total"] == pytest.approx(69.3698)
    assert gated["raw_score"] == pytest.approx(69.3698)
    assert gated["review_tier"] == "risk_watch"
    assert gated["risk_gate_code"] == "near_limit_down_followthrough_risk"
    assert review.loc[review["review_tier"].eq("top5_focus"), "asset_id"].nunique() == 5
    assert "CN:SZ:000001" in set(review.loc[review["review_tier"].eq("top5_focus"), "asset_id"])


def test_lhb_review_adds_base_score_candidate_when_original_top5_is_gated(monkeypatch):
    result = _lhb_result_for_review_test()
    result["candidates"] = result["candidates"][:5]
    lookup = {
        "CN:SZ:002463": {
            "asset_id": "CN:SZ:002463",
            "score_total": 77.0,
            "stock_name": "沪电股份",
            "pct_chg": 2.0,
            "eligibility": True,
        },
        "CN:SZ:000636": {
            "asset_id": "CN:SZ:000636",
            "score_total": 76.3,
            "stock_name": "风华高科",
            "pct_chg": 1.0,
            "eligibility": True,
        },
        "CN:SZ:002384": {
            "asset_id": "CN:SZ:002384",
            "score_total": 75.5,
            "stock_name": "东山精密",
            "pct_chg": 0.5,
            "eligibility": True,
        },
        "CN:SZ:001399": {
            "asset_id": "CN:SZ:001399",
            "score_total": 69.3698,
            "stock_name": "惠科股份",
            "pct_chg": -9.991,
            "eligibility": True,
        },
        "CN:SZ:000078": {
            "asset_id": "CN:SZ:000078",
            "score_total": 66.0,
            "stock_name": "ST海王",
            "pct_chg": 1.0,
            "eligibility": True,
        },
        "CN:SZ:000001": {
            "asset_id": "CN:SZ:000001",
            "score_total": 65.0,
            "stock_name": "平安银行",
            "pct_chg": 1.0,
            "eligibility": True,
        },
    }
    monkeypatch.setattr(strategy_eod_publish, "_lhb_base_score_lookup_for_trade_date", lambda trade_date: lookup)

    review = _review_rows_from_result(result, trade_date="2026-07-14")

    assert "CN:SZ:000001" in set(review["asset_id"])
    assert len(review.loc[review["review_tier"].eq("top5_focus")]) == 5


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
