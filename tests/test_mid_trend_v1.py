from __future__ import annotations

import pandas as pd

from stock_research import mid_trend_v1
from stock_research.mid_trend_v1 import (
    MID_TREND_V1_BENCHMARK_VARIANT,
    MidTrendV1Config,
    _report_mild_bonus_score,
    load_mid_trend_v1_funnel_detail,
    build_mid_trend_v1_from_frames,
)


def test_mid_trend_v1_uses_weekly_control_benchmark_variant() -> None:
    funnel = pd.DataFrame(
        [
            _candidate("2026-01-05", "A", 1, 95),
            _candidate("2026-01-05", "B", 2, 94),
            _candidate("2026-01-05", "C", 3, 93),
            _candidate("2026-01-12", "A", 3, 90),
            _candidate("2026-01-12", "B", 1, 96),
            _candidate("2026-01-12", "C", 2, 95),
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "close": 10.0},
            {"trade_date": "2026-01-05", "asset_id": "B", "close": 20.0},
            {"trade_date": "2026-01-05", "asset_id": "C", "close": 30.0},
            {"trade_date": "2026-01-06", "asset_id": "A", "close": 11.0},
            {"trade_date": "2026-01-06", "asset_id": "B", "close": 20.0},
            {"trade_date": "2026-01-06", "asset_id": "C", "close": 30.0},
            {"trade_date": "2026-01-12", "asset_id": "A", "close": 11.0},
            {"trade_date": "2026-01-12", "asset_id": "B", "close": 22.0},
            {"trade_date": "2026-01-12", "asset_id": "C", "close": 33.0},
            {"trade_date": "2026-01-13", "asset_id": "A", "close": 11.0},
            {"trade_date": "2026-01-13", "asset_id": "B", "close": 23.0},
            {"trade_date": "2026-01-13", "asset_id": "C", "close": 34.0},
        ]
    )

    result = build_mid_trend_v1_from_frames(
        funnel_detail=funnel,
        prices=prices,
        start_date="2026-01-05",
        end_date="2026-01-13",
        top_n=2,
        buffer_rank=3,
        transaction_cost_bps=20,
    )

    assert result["summary"]["engine_version"] == "mid_trend_v1"
    assert result["summary"]["variant_name"] == MID_TREND_V1_BENCHMARK_VARIANT
    assert result["summary"]["fresh_engine_note"] == "Mid Trend V1 DB lifecycle recompute via weekly control benchmark engine"
    assert result["summary"]["overlay_name"] == "report_mild_bonus"
    assert result["config"]["top_n"] == 2
    assert result["config"]["max_weekly_replacements"] == 2
    assert result["source_kind"] == "mid_trend_v1"
    assert result["read_only"] is False
    assert result["equity_curve"]
    assert result["positions"]
    assert result["trades"]
    assert result["summary"]["final_equity"] > 1.0
    assert {row["variant_name"] for row in result["trades"]} == {MID_TREND_V1_BENCHMARK_VARIANT}


def test_mid_trend_v1_accepts_contract_benchmark_variant() -> None:
    funnel = pd.DataFrame(
        [
            _candidate("2026-01-05", "A", 1, 95),
            _candidate("2026-01-05", "B", 2, 94),
            _candidate("2026-01-12", "B", 1, 96),
            _candidate("2026-01-12", "A", 2, 90),
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "close": 10.0},
            {"trade_date": "2026-01-05", "asset_id": "B", "close": 20.0},
            {"trade_date": "2026-01-06", "asset_id": "A", "close": 11.0},
            {"trade_date": "2026-01-06", "asset_id": "B", "close": 20.0},
            {"trade_date": "2026-01-12", "asset_id": "A", "close": 11.0},
            {"trade_date": "2026-01-12", "asset_id": "B", "close": 22.0},
            {"trade_date": "2026-01-13", "asset_id": "A", "close": 11.0},
            {"trade_date": "2026-01-13", "asset_id": "B", "close": 23.0},
        ]
    )

    result = build_mid_trend_v1_from_frames(
        funnel_detail=funnel,
        prices=prices,
        start_date="2026-01-05",
        end_date="2026-01-13",
        top_n=2,
        buffer_rank=2,
        benchmark_variant="top5_weekly_max_2_replacements",
    )

    assert result["summary"]["variant_name"] == "top5_weekly_max_2_replacements"
    assert result["summary"]["benchmark_variant"] == "top5_weekly_max_2_replacements"
    assert result["config"]["benchmark_variant"] == "top5_weekly_max_2_replacements"
    assert {row["variant_name"] for row in result["trades"]} == {"top5_weekly_max_2_replacements"}


def test_report_mild_bonus_score_caps_research_support_bonus() -> None:
    frame = pd.DataFrame(
        [
            {"mid_trend_funnel_score": 90.0, "research_support_score": 0},
            {"mid_trend_funnel_score": 90.0, "research_support_score": 40},
            {"mid_trend_funnel_score": 90.0, "research_support_score": 100},
        ]
    )

    assert _report_mild_bonus_score(frame).round(4).tolist() == [90.0, 92.0, 93.0]


def test_load_mid_trend_funnel_falls_back_to_db_when_overlay_csv_is_stale(monkeypatch, tmp_path) -> None:
    stale_csv = tmp_path / "mid_trend_overlay.csv"
    pd.DataFrame([_candidate("2026-05-19", "A", 1, 95)]).to_csv(stale_csv, index=False)
    db_frame = pd.DataFrame([_candidate("2026-06-16", "B", 1, 96)])
    calls: list[MidTrendV1Config] = []

    def fake_db_loader(config: MidTrendV1Config, *, service: str):
        calls.append(config)
        result = db_frame.copy()
        result.attrs["source"] = "db_base_tables"
        return result

    monkeypatch.setattr(mid_trend_v1, "MID_TREND_V1_FEATURE_FUNNEL_PATH", stale_csv)
    monkeypatch.setattr(mid_trend_v1, "_load_mid_trend_v1_funnel_detail_from_db", fake_db_loader)

    loaded = load_mid_trend_v1_funnel_detail(
        MidTrendV1Config(start_date="2026-01-01", end_date="2026-06-16"),
        service="test-service",
    )

    assert calls and calls[0].end_date == "2026-06-16"
    assert loaded["asset_id"].tolist() == ["B"]
    assert loaded.attrs["source"] == "db_base_tables"
    assert loaded.attrs["stale_overlay_path"] == str(stale_csv)
    assert loaded.attrs["stale_overlay_max_date"] == "2026-05-19"


def test_load_mid_trend_funnel_uses_overlay_csv_when_fresh(monkeypatch, tmp_path) -> None:
    fresh_csv = tmp_path / "mid_trend_overlay.csv"
    pd.DataFrame([_candidate("2026-06-16", "A", 1, 95)]).to_csv(fresh_csv, index=False)

    monkeypatch.setattr(mid_trend_v1, "MID_TREND_V1_FEATURE_FUNNEL_PATH", fresh_csv)
    monkeypatch.setattr(
        mid_trend_v1,
        "_load_mid_trend_v1_funnel_detail_from_db",
        lambda config, *, service: (_ for _ in ()).throw(AssertionError("DB fallback should not run")),
    )

    loaded = load_mid_trend_v1_funnel_detail(
        MidTrendV1Config(start_date="2026-01-01", end_date="2026-06-16"),
        service="test-service",
    )

    assert loaded["asset_id"].tolist() == ["A"]
    assert loaded.attrs["source"] == "research_overlay_feature_input"


def _candidate(trade_date: str, asset_id: str, score_rank: int, score: float) -> dict[str, object]:
    return {
        "trade_date": trade_date,
        "asset_id": asset_id,
        "ts_code": f"{asset_id}.TEST",
        "stock_name": asset_id,
        "industry_name": "Tech",
        "market_regime": "mainline",
        "mainline_status": "sustained_mainline",
        "mainline_context": "mainline",
        "industry_mainline_score_v1": 0.65,
        "mid_trend_layer": "stable_trend_watch",
        "structure_slot": "preferred_mainline_core",
        "mid_trend_funnel_score": score,
        "research_support_score": 0,
        "score_rank": score_rank,
        "volatility_20_score": 50,
        "trend_r2_20_score": 90,
        "ret_20_score": 85,
        "max_drawdown_20_score": 80,
    }
