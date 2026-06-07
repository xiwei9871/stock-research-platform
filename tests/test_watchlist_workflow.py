from decimal import Decimal

import pandas as pd

from stock_research.watchlist.workflow import (
    _load_market_frame,
    _load_dragon_frame,
    _load_watchlist_factor_frame,
    build_watchlist_diagnostics_snapshot,
    build_watchlist_snapshot,
    load_feature_snapshot,
    load_industry_memberships,
)


class _Context:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_build_watchlist_snapshot_loads_context_and_persists_signal_rows(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_watchlist_items",
        lambda *args, **kwargs: pd.DataFrame(
            [
                {"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10},
                {"watchlist_id": "core", "asset_id": "B", "stock_code": "000002.SZ", "stock_name": "B", "priority": 20},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"asset_id": "A", "rank": 1, "score_total": Decimal("88.0")}],
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(
            [
                {"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.04},
                {"asset_id": "A", "feature_name": "ret_20d", "feature_value": 0.12},
                {"asset_id": "B", "feature_name": "ret_5d", "feature_value": -0.02},
                {"asset_id": "B", "feature_name": "ret_20d", "feature_value": -0.05},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_industry_memberships",
        lambda **kwargs: {
            "A": {"industry_code": "BANK", "industry_name": "Bank"},
            "B": {"industry_code": "TECH", "industry_name": "Tech"},
        },
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_market_state",
        lambda **kwargs: {"market_state": "bullish", "entry_allowed": True},
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_sector_strength",
        lambda **kwargs: pd.DataFrame(
            [
                {"industry_code": "BANK", "strength_rank": 1, "strength_score": 80.0},
                {"industry_code": "TECH", "strength_rank": 20, "strength_score": 20.0},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.store_watchlist_daily_signals",
        lambda frame, **kwargs: calls.append(frame) or len(frame),
    )

    frame = build_watchlist_snapshot(
        trade_date="2026-05-20",
        watchlist_id="core",
        score_version="manual_v1",
    )

    assert len(frame) == 2
    assert len(calls) == 1
    assert calls[0].iloc[0]["reason_json"]["score_total"] == 88.0
    assert isinstance(calls[0].iloc[0]["reason_json"]["score_total"], float)


def test_build_watchlist_snapshot_uses_full_sector_universe_for_sector_risk(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_watchlist_items",
        lambda *args, **kwargs: pd.DataFrame(
            [{"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10}]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"asset_id": "A", "rank": 1, "score_total": Decimal("88.0")}],
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(
            [
                {"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.04},
                {"asset_id": "A", "feature_name": "ret_20d", "feature_value": 0.12},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_industry_memberships",
        lambda **kwargs: {"A": {"industry_code": "TECH", "industry_name": "Tech"}},
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_market_state",
        lambda **kwargs: {"market_state": "bullish", "entry_allowed": True},
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_sector_strength_bars",
        lambda **kwargs: pd.DataFrame(
            [
                {"trade_date": "2026-05-20", "industry_system": "csrc", "industry_code": f"S{i}", "industry_name": f"S{i}", "close": 100 + i, "amount": 1000 + i}
                for i in range(1, 11)
            ]
        ),
    )

    def fake_calc_sector_strength(bars, trade_date, top_n=20):
        captured["top_n"] = top_n
        return pd.DataFrame(
            [{"industry_code": "TECH", "strength_rank": 6, "strength_score": 50.0}]
            if top_n >= 6
            else []
        )

    monkeypatch.setattr("stock_research.watchlist.workflow.calc_sector_strength", fake_calc_sector_strength)
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.store_watchlist_daily_signals",
        lambda frame, **kwargs: frame,
    )

    frame = build_watchlist_snapshot(
        trade_date="2026-05-20",
        watchlist_id="core",
        score_version="manual_v1",
        top_n=3,
    )

    assert captured["top_n"] == 10
    assert "sector_weakness" in frame.iloc[0]["risk_tags"]


def test_build_watchlist_diagnostics_snapshot_returns_empty_outputs_for_empty_score_day(monkeypatch):
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [],
    )

    result = build_watchlist_diagnostics_snapshot(
        trade_date="2026-05-20",
        score_version="manual_v1",
        top_n=5,
    )

    assert set(result) == {"full", "must_watch"}
    assert result["full"].empty
    assert result["must_watch"].empty


def test_load_watchlist_factor_frame_falls_back_to_stock_technical_features(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_factor_daily",
        lambda **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr("stock_research.watchlist.workflow.connect", lambda service: _Context(object()))

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "asset_id": "A",
                "amount_vs_20d": 2.5,
                "high_to_close_drawdown": 0.03,
                "volatility_5d": 0.06,
            }
        ]

    monkeypatch.setattr("stock_research.watchlist.workflow.fetch_all", fake_fetch_all)

    frame = _load_watchlist_factor_frame(
        trade_date="2025-02-07",
        asset_ids=["A", "B"],
    )

    assert "factor.stock_technical_features_daily" in captured["sql"]
    assert captured["params"] == ["2025-02-07", "A", "B"]
    row = frame.set_index("asset_id").loc["A"]
    assert row["amount_vs_20d"] == 2.5
    assert row["high_to_close_drawdown"] == 0.03
    assert row["volatility_5d"] == 0.06


def test_build_watchlist_diagnostics_snapshot_sets_watchlist_identity(monkeypatch):
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"trade_date": "2026-05-20", "asset_id": "A", "rank": 1, "score_total": 91.0}],
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.build_watchlist_diagnostics",
        lambda **kwargs: {
            "full": pd.DataFrame([{"asset_id": "A", "watch_group": "opportunity_watch"}]),
            "must_watch": pd.DataFrame([{"asset_id": "A", "watch_group": "opportunity_watch"}]),
        },
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_asset_identity_map",
        lambda asset_ids: pd.DataFrame([{"asset_id": "A", "ts_code": "000001.SZ", "stock_name": "Alpha"}]),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_watchlist_factor_frame",
        lambda **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr("stock_research.watchlist.workflow._load_dragon_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_lhb_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_event_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_market_frame", lambda **kwargs: pd.DataFrame())

    result = build_watchlist_diagnostics_snapshot(
        trade_date="2026-05-20",
        score_version="manual_v1",
        top_n=5,
    )

    assert list(result["full"]["watchlist_id"]) == ["diagnostics"]
    assert list(result["must_watch"]["watchlist_id"]) == ["diagnostics"]
    assert list(result["full"]["trade_date"]) == ["2026-05-20"]
    assert list(result["must_watch"]["trade_date"]) == ["2026-05-20"]


def test_build_watchlist_diagnostics_snapshot_maps_asset_identity_into_diagnostics_inputs(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        assert "FROM core.asset_master" in sql
        assert params == ["CN:SZ:000017"]
        return [{"asset_id": "CN:SZ:000017", "ts_code": "000017.SZ", "name": "深中华A"}]

    def fake_build_watchlist_diagnostics(**kwargs):
        top_scores = kwargs["top_scores"]
        row = top_scores.iloc[0]
        assert row["ts_code"] == "000017.SZ"
        assert row["stock_name"] == "深中华A"
        return {
            "full": pd.DataFrame([{"asset_id": row["asset_id"], "watch_group": "candidate"}]),
            "must_watch": pd.DataFrame(),
        }

    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"trade_date": "2026-05-20", "asset_id": "CN:SZ:000017", "rank": 1, "score_total": 91.0}],
    )
    monkeypatch.setattr("stock_research.watchlist.workflow.connect", lambda service: _Context(object()))
    monkeypatch.setattr("stock_research.watchlist.workflow.fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr("stock_research.watchlist.workflow._load_watchlist_factor_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_dragon_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_lhb_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_event_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_market_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.build_watchlist_diagnostics",
        fake_build_watchlist_diagnostics,
    )

    build_watchlist_diagnostics_snapshot(
        trade_date="2026-05-20",
        score_version="manual_v1",
        top_n=5,
    )


def test_build_watchlist_diagnostics_snapshot_selects_latest_recent_event_for_diagnostics_inputs(monkeypatch):
    case_events = pd.DataFrame(
        [
            {
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "event_date": "2026-04-10",
                "verified_case_type_v2_1": "failed_breakout",
                "success_or_failure": "failure",
                "event_type": "breakout",
                "confidence": 0.5,
            },
            {
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "event_date": "2026-05-06",
                "verified_case_type_v2_1": "failed_second_wave",
                "success_or_failure": "failure",
                "event_type": "peak",
                "confidence": 0.8,
            },
            {
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "event_date": "2026-05-19",
                "verified_case_type_v2_1": "failed_reversal",
                "success_or_failure": "failure",
                "event_type": "reversal",
                "confidence": 0.9,
            },
        ]
    )

    def fake_fetch_all(conn, sql, params):
        assert "FROM core.asset_master" in sql
        return [{"asset_id": "CN:SZ:000017", "ts_code": "000017.SZ", "name": "深中华A"}]

    def fake_read_csv(path, *args, **kwargs):
        path = str(path)
        if path.endswith("dragon_case_curated_library_failure_v2_1.csv"):
            return case_events.copy()
        if path.endswith("lhb_risk_feature_case_detail_v2_1.csv"):
            return pd.DataFrame()
        raise AssertionError(f"unexpected read_csv path: {path}")

    def fake_build_watchlist_diagnostics(**kwargs):
        event_frame = kwargs["event_frame"]
        assert len(event_frame) == 1
        row = event_frame.iloc[0]
        assert row["asset_id"] == "CN:SZ:000017"
        assert row["event_structure"] == "failed_reversal"
        assert bool(row["failure_flag"]) is True
        assert row["case_event_type"] == "reversal"
        return {
            "full": pd.DataFrame([{"asset_id": row["asset_id"], "watch_group": "risk_watch"}]),
            "must_watch": pd.DataFrame([{"asset_id": row["asset_id"], "watch_group": "risk_watch"}]),
        }

    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"trade_date": "2026-05-20", "asset_id": "CN:SZ:000017", "rank": 1, "score_total": 91.0}],
    )
    monkeypatch.setattr("stock_research.watchlist.workflow.connect", lambda service: _Context(object()))
    monkeypatch.setattr("stock_research.watchlist.workflow.fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr("stock_research.watchlist.workflow._load_watchlist_factor_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow.pd.read_csv", fake_read_csv)
    monkeypatch.setattr("stock_research.watchlist.workflow._load_dragon_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_market_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.build_watchlist_diagnostics",
        fake_build_watchlist_diagnostics,
    )

    build_watchlist_diagnostics_snapshot(
        trade_date="2026-05-20",
        score_version="manual_v1",
        top_n=5,
    )


def test_build_watchlist_diagnostics_snapshot_selects_latest_recent_lhb_event_for_diagnostics_inputs(
    monkeypatch,
):
    lhb_events = pd.DataFrame(
        [
            {
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "event_date": "2026-04-15",
                "lhb_risk_score": 0.2,
                "lhb_negative_net_buy": False,
                "lhb_institution_selling": False,
            },
            {
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "event_date": "2026-05-07",
                "lhb_risk_score": 0.4,
                "lhb_negative_net_buy": False,
                "lhb_institution_selling": False,
            },
            {
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "event_date": "2026-05-18",
                "lhb_risk_score": 0.85,
                "lhb_negative_net_buy": True,
                "lhb_institution_selling": True,
            },
        ]
    )

    def fake_fetch_all(conn, sql, params):
        assert "FROM core.asset_master" in sql
        return [{"asset_id": "CN:SZ:000017", "ts_code": "000017.SZ", "name": "深中华A"}]

    def fake_read_csv(path, *args, **kwargs):
        path = str(path)
        if path.endswith("dragon_case_curated_library_failure_v2_1.csv"):
            return pd.DataFrame()
        if path.endswith("lhb_risk_feature_case_detail_v2_1.csv"):
            return lhb_events.copy()
        raise AssertionError(f"unexpected read_csv path: {path}")

    def fake_build_watchlist_diagnostics(**kwargs):
        lhb_frame = kwargs["lhb_frame"]
        assert len(lhb_frame) == 1
        row = lhb_frame.iloc[0]
        assert row["asset_id"] == "CN:SZ:000017"
        assert row["lhb_risk_score"] == 0.85
        assert bool(row["lhb_negative_net_buy"]) is True
        assert bool(row["lhb_institution_selling"]) is True
        return {
            "full": pd.DataFrame([{"asset_id": row["asset_id"], "watch_group": "risk_watch"}]),
            "must_watch": pd.DataFrame([{"asset_id": row["asset_id"], "watch_group": "risk_watch"}]),
        }

    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"trade_date": "2026-05-20", "asset_id": "CN:SZ:000017", "rank": 1, "score_total": 91.0}],
    )
    monkeypatch.setattr("stock_research.watchlist.workflow.connect", lambda service: _Context(object()))
    monkeypatch.setattr("stock_research.watchlist.workflow.fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr("stock_research.watchlist.workflow._load_watchlist_factor_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow.pd.read_csv", fake_read_csv)
    monkeypatch.setattr("stock_research.watchlist.workflow._load_dragon_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr("stock_research.watchlist.workflow._load_market_frame", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.build_watchlist_diagnostics",
        fake_build_watchlist_diagnostics,
    )

    build_watchlist_diagnostics_snapshot(
        trade_date="2026-05-20",
        score_version="manual_v1",
        top_n=5,
    )


def test_load_feature_snapshot_queries_watchlist_owned_snapshot_sql(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((conn, sql, params))
        return [
            {"asset_id": "A", "feature_name": "amount_vs_20d", "feature_value": 4.2},
            {"asset_id": "A", "feature_name": "high_to_close_drawdown", "feature_value": 0.02},
        ]

    monkeypatch.setattr("stock_research.watchlist.workflow.connect", lambda service: _Context(object()))
    monkeypatch.setattr("stock_research.watchlist.workflow.fetch_all", fake_fetch_all)

    frame = load_feature_snapshot(trade_date="2026-05-20", asset_ids=["A", "B"])

    assert list(frame["feature_name"]) == ["amount_vs_20d", "high_to_close_drawdown"]
    assert "FROM feature_snapshot" in calls[0][1]
    assert "feature_set = 'p0_daily'" in calls[0][1]
    assert "feature_version = 'v1'" in calls[0][1]
    assert calls[0][2] == ["2026-05-20", "A", "B"]


def test_load_industry_memberships_queries_watchlist_owned_membership_sql(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((conn, sql, params))
        return [
            {
                "asset_id": "A",
                "industry_code": "BANK",
                "industry_name": "Bank",
                "level": 1,
            },
            {
                "asset_id": "A",
                "industry_code": "BANK2",
                "industry_name": "Bank 2",
                "level": 2,
            },
            {
                "asset_id": "B",
                "industry_code": "TECH",
                "industry_name": "Tech",
                "level": 1,
            },
        ]

    monkeypatch.setattr("stock_research.watchlist.workflow.connect", lambda service: _Context(object()))
    monkeypatch.setattr("stock_research.watchlist.workflow.fetch_all", fake_fetch_all)

    memberships = load_industry_memberships(
        trade_date="2026-05-20",
        asset_ids=["A", "B"],
        industry_system="csrc",
    )

    assert memberships == {
        "A": {"industry_code": "BANK", "industry_name": "Bank", "industry_level": 1},
        "B": {"industry_code": "TECH", "industry_name": "Tech", "industry_level": 1},
    }
    assert "FROM core.industry_membership" in calls[0][1]
    assert "start_date <= %s" in calls[0][1]
    assert "(end_date IS NULL OR end_date >= %s)" in calls[0][1]
    assert calls[0][2] == ["csrc", "2026-05-20", "2026-05-20", "A", "B"]


def test_load_watchlist_factor_frame_carries_volatility_5d_through(monkeypatch):
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(
            [
                {"asset_id": "CN:SZ:000017", "feature_name": "amount_vs_20d", "feature_value": 4.5},
                {"asset_id": "CN:SZ:000017", "feature_name": "high_to_close_drawdown", "feature_value": 0.10},
                {"asset_id": "CN:SZ:000017", "feature_name": "volatility_5d", "feature_value": 0.12},
                {"asset_id": "CN:SH:600118", "feature_name": "amount_vs_20d", "feature_value": 1.2},
                {"asset_id": "CN:SH:600118", "feature_name": "high_to_close_drawdown", "feature_value": 0.02},
                {"asset_id": "CN:SH:600118", "feature_name": "volatility_5d", "feature_value": 0.04},
                {"asset_id": "CN:SH:600118", "feature_name": "ret_5d", "feature_value": 0.18},
            ]
        ),
    )

    frame = _load_watchlist_factor_frame(
        trade_date="2026-05-20",
        asset_ids=["CN:SZ:000017", "CN:SH:600118"],
    ).set_index("asset_id")

    assert list(frame.columns) == ["amount_vs_20d", "high_to_close_drawdown", "volatility_5d"]
    assert frame.loc["CN:SZ:000017", "volatility_5d"] == 0.12
    assert frame.loc["CN:SH:600118", "volatility_5d"] == 0.04


def test_load_dragon_frame_prefers_latest_recent_trade_date_and_real_dragon_fields(monkeypatch):
    dragon_snapshot = pd.DataFrame(
        [
            {
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "trade_date": "2026-04-20",
                "dragon_risk_score": 0.25,
                "overheat_avoid": False,
                "crowded_late_entry": False,
            },
            {
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "trade_date": "2026-05-06",
                "dragon_risk_score": 0.55,
                "overheat_avoid": False,
                "crowded_late_entry": False,
            },
            {
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "trade_date": "2026-05-19",
                "dragon_risk_score": 0.81,
                "overheat_avoid": True,
                "crowded_late_entry": True,
            },
            {
                "ts_code": "000017.SZ",
                "stock_name": "深中华A",
                "trade_date": "2026-05-21",
                "dragon_risk_score": 0.10,
                "overheat_avoid": False,
                "crowded_late_entry": False,
            },
            {
                "ts_code": "600118.SH",
                "stock_name": "中国卫星",
                "trade_date": "2026-05-18",
                "dragon_risk_score": 0.22,
                "overheat_avoid": False,
                "crowded_late_entry": False,
            },
        ]
    )

    def fake_fetch_all(conn, sql, params):
        assert "FROM core.asset_master" in sql
        assert params == ["CN:SZ:000017", "CN:SH:600118"]
        return [
            {"asset_id": "CN:SZ:000017", "ts_code": "000017.SZ", "name": "深中华A"},
            {"asset_id": "CN:SH:600118", "ts_code": "600118.SH", "name": "中国卫星"},
        ]

    def fake_read_csv(path, *args, **kwargs):
        assert str(path).endswith("dragon_case_factor_snapshot_2024_2026.csv")
        return dragon_snapshot.copy()

    monkeypatch.setattr("stock_research.watchlist.workflow.connect", lambda service: _Context(object()))
    monkeypatch.setattr("stock_research.watchlist.workflow.fetch_all", fake_fetch_all)
    monkeypatch.setattr("stock_research.watchlist.workflow.pd.read_csv", fake_read_csv)
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_current_day_dragon_frame",
        lambda **kwargs: pd.DataFrame(),
    )

    frame = _load_dragon_frame(
        trade_date="2026-05-20",
        asset_ids=["CN:SZ:000017", "CN:SH:600118"],
    ).set_index("asset_id")

    assert frame.loc["CN:SZ:000017", "dragon_risk_score"] == 0.81
    assert bool(frame.loc["CN:SZ:000017", "overheat_avoid"]) is True
    assert bool(frame.loc["CN:SZ:000017", "crowded_late_entry"]) is True
    assert frame.loc["CN:SH:600118", "dragon_risk_score"] == 0.22


def test_load_dragon_frame_prefers_current_day_diagnostics_before_recent_csv(monkeypatch):
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_current_day_dragon_frame",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "asset_id": "CN:SZ:000017",
                    "dragon_risk_score": 0.76,
                    "overheat_avoid": True,
                    "crowded_late_entry": False,
                    "dragon_trade_date": "2026-05-20",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.pd.read_csv",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("recent csv fallback should not run")),
    )

    frame = _load_dragon_frame(
        trade_date="2026-05-20",
        asset_ids=["CN:SZ:000017"],
    ).set_index("asset_id")

    assert frame.loc["CN:SZ:000017", "dragon_risk_score"] == 0.76
    assert bool(frame.loc["CN:SZ:000017", "overheat_avoid"]) is True
    assert bool(frame.loc["CN:SZ:000017", "crowded_late_entry"]) is False


def test_load_market_frame_enriches_market_regime_and_mainline_flags(monkeypatch):
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_industry_memberships",
        lambda **kwargs: {
            "A": {"industry_code": "TECH", "industry_name": "Tech"},
            "B": {"industry_code": "BANK", "industry_name": "Bank"},
        },
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_market_state",
        lambda **kwargs: {"market_state": "bullish", "risk_level": "low", "entry_allowed": True},
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_sector_strength",
        lambda **kwargs: pd.DataFrame(
            [
                {"industry_code": "TECH", "strength_rank": 1, "strength_score": 88.0},
                {"industry_code": "AUTO", "strength_rank": 2, "strength_score": 77.0},
            ]
        ),
    )

    frame = _load_market_frame(
        trade_date="2026-05-20",
        asset_ids=["A", "B"],
    ).set_index("asset_id")

    assert frame.loc["A", "industry_name"] == "Tech"
    assert bool(frame.loc["A", "mainline_flag"]) is True
    assert frame.loc["A", "sector_strength_rank"] == 1
    assert frame.loc["A", "market_regime"] == "bullish"
    assert frame.loc["B", "industry_name"] == "Bank"
    assert bool(frame.loc["B", "mainline_flag"]) is False
    assert pd.isna(frame.loc["B", "sector_strength_rank"])
