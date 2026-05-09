import json
from pathlib import Path

import pandas as pd
import pytest

import stock_research.v31_cache as v31_cache


def _features_for(asset_id: str, trade_date: str, values: dict[str, float]):
    return [
        {
            "asset_id": asset_id,
            "trade_date": trade_date,
            "feature_name": feature_name,
            "feature_value": feature_value,
        }
        for feature_name, feature_value in values.items()
    ]


def test_build_v31_cache_writes_expected_local_files(tmp_path):
    features = pd.DataFrame(
        _features_for(
            "CN:SH:600001",
            "2026-01-02",
            {
                "ret_5d": 0.05,
                "ret_20d": 0.20,
                "ret_60d": 0.10,
                "amount_20d_avg": 100000000.0,
                "volatility_20d": 0.02,
                "ma20_deviation": 0.08,
                "max_drawdown_20d": -0.03,
            },
        )
    )
    bars = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600001",
                "trade_date": "2026-01-02",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "preclose": 10.0,
                "amount": 100000000.0,
                "turnover_rate": 1.0,
                "pct_chg": 2.0,
                "trade_status": "1",
                "is_st": False,
            }
        ]
    )

    result = v31_cache.build_v31_cache_from_frames(
        features,
        bars,
        start_date="2026-01-02",
        end_date="2026-01-02",
        cache_dir=tmp_path,
        prefer_parquet=False,
    )

    assert set(result["paths"]) == {
        "asset_features",
        "market_regime",
        "board_regime",
        "retention_candidates",
        "manifest",
    }
    for path in result["paths"].values():
        assert Path(path).exists()
    assert result["counts"]["asset_features"] == 1
    assert result["counts"]["market_regime"] == 1
    assert result["counts"]["board_regime"] == 1
    assert result["counts"]["retention_candidates"] == 1
    manifest = json.loads(Path(result["paths"]["manifest"]).read_text())
    assert manifest["paths"] == result["paths"]

    candidates = pd.read_csv(result["paths"]["retention_candidates"])
    assert list(candidates["asset_id"]) == ["CN:SH:600001"]
    assert candidates.iloc[0]["rank"] == 1
    assert bool(candidates.iloc[0]["hard_filter_pass"]) is True


def test_v31_cache_candidates_rank_after_hard_filters(tmp_path):
    features = pd.DataFrame(
        _features_for(
            "HOT",
            "2026-01-02",
            {
                "ret_5d": 0.30,
                "ret_20d": 0.50,
                "ret_60d": 0.25,
                "amount_20d_avg": 100000000.0,
                "volatility_20d": 0.02,
                "ma20_deviation": 0.25,
                "max_drawdown_20d": -0.03,
            },
        )
        + _features_for(
            "STEADY",
            "2026-01-02",
            {
                "ret_5d": 0.06,
                "ret_20d": 0.20,
                "ret_60d": 0.10,
                "amount_20d_avg": 100000000.0,
                "volatility_20d": 0.02,
                "ma20_deviation": 0.08,
                "max_drawdown_20d": -0.03,
            },
        )
    )
    bars = pd.DataFrame(
        [
            {
                "asset_id": asset_id,
                "trade_date": "2026-01-02",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "preclose": 10.0,
                "amount": 100000000.0,
                "turnover_rate": 1.0,
                "pct_chg": 2.0,
                "trade_status": "1",
                "is_st": False,
            }
            for asset_id in ("HOT", "STEADY")
        ]
    )

    result = v31_cache.build_v31_cache_from_frames(
        features,
        bars,
        start_date="2026-01-02",
        end_date="2026-01-02",
        cache_dir=tmp_path,
        prefer_parquet=False,
    )

    candidates = pd.read_csv(result["paths"]["retention_candidates"])
    assert list(candidates["asset_id"]) == ["STEADY"]
    assert list(candidates["rank"]) == [1]


def test_build_v31_cache_board_filter_uses_close_preclose_without_pct_chg(tmp_path):
    features = pd.DataFrame(
        _features_for(
            "CN:SH:600001",
            "2026-01-02",
            {
                "ret_5d": 0.02,
                "ret_20d": 0.08,
                "ret_60d": 0.04,
                "amount_20d_avg": 100000000.0,
                "volatility_20d": 0.02,
                "ma20_deviation": 0.08,
                "max_drawdown_20d": -0.03,
            },
        )
        + _features_for(
            "CN:SH:600002",
            "2026-01-02",
            {
                "ret_5d": 0.03,
                "ret_20d": 0.10,
                "ret_60d": 0.05,
                "amount_20d_avg": 100000000.0,
                "volatility_20d": 0.02,
                "ma20_deviation": 0.08,
                "max_drawdown_20d": -0.03,
            },
        )
        + _features_for(
            "CN:SH:600003",
            "2026-01-02",
            {
                "ret_5d": 0.01,
                "ret_20d": 0.06,
                "ret_60d": 0.03,
                "amount_20d_avg": 100000000.0,
                "volatility_20d": 0.02,
                "ma20_deviation": 0.08,
                "max_drawdown_20d": -0.03,
            },
        )
    )
    bars = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600001",
                "trade_date": "2026-01-02",
                "open": 10.0,
                "preclose": 10.0,
                "close": 10.5,
                "amount": 100000000.0,
                "turnover_rate": 1.0,
                "trade_status": "1",
                "is_st": False,
            },
            {
                "asset_id": "CN:SH:600002",
                "trade_date": "2026-01-02",
                "open": 10.0,
                "preclose": 10.0,
                "close": 10.4,
                "amount": 100000000.0,
                "turnover_rate": 1.0,
                "trade_status": "1",
                "is_st": False,
            },
            {
                "asset_id": "CN:SH:600003",
                "trade_date": "2026-01-02",
                "open": 10.0,
                "preclose": 10.0,
                "close": 9.8,
                "amount": 100000000.0,
                "turnover_rate": 1.0,
                "trade_status": "1",
                "is_st": False,
            },
        ]
    )

    result = v31_cache.build_v31_cache_from_frames(
        features,
        bars,
        start_date="2026-01-02",
        end_date="2026-01-02",
        cache_dir=tmp_path,
        prefer_parquet=False,
    )

    board = pd.read_csv(result["paths"]["board_regime"])
    candidates = pd.read_csv(result["paths"]["retention_candidates"])
    assert board.iloc[0]["up_ratio"] == pytest.approx(2 / 3)
    assert bool(board.iloc[0]["board_allows_entry"]) is True
    assert candidates["board_filter_pass"].tolist() == [True, True, True]


def test_build_v31_cache_cli_prints_paths(monkeypatch, tmp_path, capsys):
    import stock_research.cli as cli

    def fake_build_v31_cache(**kwargs):
        return {
            "paths": {"manifest": str(tmp_path / "manifest.json")},
            "counts": {"retention_candidates": 3},
        }

    monkeypatch.setattr(cli, "build_v31_cache", fake_build_v31_cache)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "build-v31-cache",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-05-09",
            "--cache-dir",
            str(tmp_path),
            "--format",
            "csv",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        f"v31_cache_manifest|{tmp_path / 'manifest.json'}",
        "v31_cache_candidates|3",
    ]
