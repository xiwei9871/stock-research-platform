from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.strong_winner_taxonomy import build_strong_winner_taxonomy_v2_from_frames


def _bars() -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=70)
    rows = []
    for idx, date in enumerate(dates):
        # A: 60d double winner.
        close_a = 10 * (1 + min(idx, 60) / 60 * 1.10)
        rows.append(
            {
                "trade_date": date,
                "asset_id": "A",
                "ts_code": "000001.SZ",
                "stock_name": "Alpha",
                "open": close_a,
                "high": close_a * 1.01,
                "low": close_a * 0.99,
                "close": close_a,
            }
        )
        # B: 20d/30d burst but not 60d double.
        close_b = 10 * (1 + min(idx, 25) / 25 * 0.70)
        rows.append(
            {
                "trade_date": date,
                "asset_id": "B",
                "ts_code": "000002.SZ",
                "stock_name": "Beta",
                "open": close_b,
                "high": close_b * 1.02,
                "low": close_b * 0.98,
                "close": close_b,
            }
        )
        # C: smooth 60d stable trend.
        close_c = 10 * (1 + min(idx, 60) / 60 * 0.55)
        rows.append(
            {
                "trade_date": date,
                "asset_id": "C",
                "ts_code": "000003.SZ",
                "stock_name": "Gamma",
                "open": close_c,
                "high": close_c * 1.005,
                "low": close_c * 0.995,
                "close": close_c,
            }
        )
        # D: pullback then new high.
        close_d = 10
        if idx <= 15:
            close_d = 10 * (1 + idx / 15 * 0.35)
        elif idx <= 28:
            close_d = 13.5 * (1 - (idx - 15) / 13 * 0.16)
        else:
            close_d = 11.34 * (1 + (idx - 28) / 30 * 0.35)
        rows.append(
            {
                "trade_date": date,
                "asset_id": "D",
                "ts_code": "000004.SZ",
                "stock_name": "Delta",
                "open": close_d,
                "high": close_d * 1.01,
                "low": close_d * 0.99,
                "close": close_d,
            }
        )
    return pd.DataFrame(rows)


def _v2_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-10",
                "asset_id": "A",
                "industry_name": "电子",
                "market_regime": "mainline",
                "mainline_context": "mainline",
                "v2_2_growth_trend_core": True,
                "v2_2_high_elasticity_shadow": False,
            },
            {
                "trade_date": "2025-01-10",
                "asset_id": "B",
                "industry_name": "题材",
                "market_regime": "rotation",
                "mainline_context": "rotation",
                "v2_2_growth_trend_core": False,
                "v2_2_high_elasticity_shadow": True,
            },
        ]
    )


def test_taxonomy_v2_detects_multiple_winner_types_and_capture(tmp_path: Path):
    result = build_strong_winner_taxonomy_v2_from_frames(
        bars=_bars(),
        v2_detail=_v2_detail(),
        output_dir=tmp_path,
    )

    taxonomy = result["taxonomy"]
    assert {"double_60d", "burst_30d", "burst_20d", "stable_trend_60d", "pullback_new_high"} <= set(
        taxonomy["winner_type"]
    )
    assert {"window_start", "window_end", "max_return", "max_drawdown", "rise_smoothness", "volatility"} <= set(
        taxonomy.columns
    )
    capture = result["v2_2_capture"]
    assert {"winner_type", "candidate_set", "capture_rate"} <= set(capture.columns)
    assert Path(result["paths"]["taxonomy"]).exists()
    assert Path(result["paths"]["v2_2_capture"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_taxonomy_v2_summary_counts_by_type():
    result = build_strong_winner_taxonomy_v2_from_frames(bars=_bars(), v2_detail=_v2_detail())

    summary = result["summary"].set_index("winner_type")
    assert summary.loc["double_60d", "winner_count"] >= 1
    assert summary.loc["stable_trend_60d", "avg_max_drawdown"] > -0.25


def test_cli_dispatches_strong_winner_taxonomy_v2(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "paths": {
                "taxonomy": str(tmp_path / "taxonomy.csv"),
                "summary": str(tmp_path / "summary.csv"),
                "v2_2_capture": str(tmp_path / "capture.csv"),
                "report": str(tmp_path / "report.md"),
            },
            "warnings": [],
        }

    monkeypatch.setattr(cli, "run_strong_winner_taxonomy_v2", fake_run)
    cli.main_for_args(
        [
            "analyze-strong-winner-taxonomy-v2",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-05-19",
            "--v2-detail-path",
            "outputs/research/trend_discovery_v2_2_replay_detail.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["start_date"] == "2025-01-01"
    assert captured["v2_detail_path"] == "outputs/research/trend_discovery_v2_2_replay_detail.csv"
    out = capsys.readouterr().out
    assert "strong_winner_taxonomy_v2|taxonomy|" in out
    assert "strong_winner_taxonomy_v2|v2_2_capture|" in out
