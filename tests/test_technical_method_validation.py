from pathlib import Path

import numpy as np
import pandas as pd

from stock_research import cli
import stock_research.technical_method_validation as technical_method_validation


def test_build_technical_method_validation_outputs_generates_all_core_artifacts(tmp_path):
    result = technical_method_validation.build_technical_method_validation_from_frames(
        bars=_sample_validation_bars(),
        output_dir=tmp_path,
        case_view=_sample_case_view(),
        lhb_case_detail=_sample_lhb_case_detail(),
        regime_frame=_sample_market_regime(),
    )

    expected = {
        "feature_bucket_effectiveness",
        "combo_effectiveness",
        "regime_effectiveness",
        "case_event_effectiveness",
        "lhb_cross_effectiveness",
        "feature_correlation",
        "redundancy_report",
        "recommendation",
        "report",
    }
    assert expected.issubset(result["paths"])
    for path in result["paths"].values():
        assert Path(path).exists()
    assert "feature_name" in result["feature_bucket_effectiveness"].columns
    assert "combo_name" in result["combo_effectiveness"].columns
    assert "market_regime" in result["regime_effectiveness"].columns
    assert "verified_case_type" in result["case_event_effectiveness"].columns
    assert "feature_a" in result["feature_correlation"].columns
    assert "feature_or_method" in result["recommendation"].columns


def test_technical_method_validation_handles_missing_lhb_inputs(tmp_path):
    result = technical_method_validation.build_technical_method_validation_from_frames(
        bars=_sample_validation_bars(),
        output_dir=tmp_path,
        case_view=_sample_case_view(),
        lhb_case_detail=pd.DataFrame(),
        regime_frame=_sample_market_regime(),
    )

    assert Path(result["paths"]["lhb_cross_effectiveness"]).exists()
    assert result["lhb_cross_effectiveness"].empty
    assert result["warnings"]


def test_market_regime_input_accepts_rebalance_date_without_fallback(tmp_path):
    regime = pd.DataFrame(
        [
            {"rebalance_date": "2024-04-15", "market_regime": "mainline"},
            {"rebalance_date": "2024-04-16", "market_regime": "rotation"},
        ]
    )
    result = technical_method_validation.build_technical_method_validation_from_frames(
        bars=_sample_validation_bars(),
        output_dir=tmp_path,
        case_view=_sample_case_view(),
        lhb_case_detail=pd.DataFrame(),
        regime_frame=regime,
    )

    assert "market_regime_diagnostics.csv was not available; used fallback regime classification" not in result["warnings"]
    assert set(result["dataset"]["market_regime"].dropna().astype(str)) >= {"mainline", "rotation"}


def test_compute_validation_features_ignores_future_like_input_columns():
    bars = _sample_validation_bars()
    dirty = bars.copy()
    dirty["future_5d_return"] = 999.0
    clean_result = technical_method_validation.compute_validation_features(_sample_validation_bars())
    dirty_result = technical_method_validation.compute_validation_features(dirty)

    compare_cols = ["close_vs_ma5", "macd_dif", "rsi6", "amount_vs_20d", "high_to_close_drawdown"]
    pd.testing.assert_frame_equal(
        clean_result[compare_cols].reset_index(drop=True),
        dirty_result[compare_cols].reset_index(drop=True),
        check_dtype=False,
    )


def test_redundancy_report_and_recommendation_are_generated(tmp_path):
    result = technical_method_validation.build_technical_method_validation_from_frames(
        bars=_sample_validation_bars(),
        output_dir=tmp_path,
        case_view=_sample_case_view(),
        lhb_case_detail=_sample_lhb_case_detail(),
        regime_frame=_sample_market_regime(),
    )

    redundancy = result["redundancy_report"]
    recommendation = result["recommendation"]
    assert "recommended_keep" in redundancy.columns
    assert "recommended_usage" in recommendation.columns


def test_combo_and_lhb_outputs_keep_zero_sample_definitions(tmp_path):
    result = technical_method_validation.build_technical_method_validation_from_frames(
        bars=_sample_validation_bars(),
        output_dir=tmp_path,
        case_view=_sample_case_view(),
        lhb_case_detail=_sample_lhb_case_detail(),
        regime_frame=_sample_market_regime(),
    )

    combo = result["combo_effectiveness"]
    lhb = result["lhb_cross_effectiveness"]
    assert "second_wave_supportive_setup" in set(combo["combo_name"])
    assert set(lhb["combo_name"]) == {
        "lhb_high_risk_plus_rsi_overheat",
        "lhb_high_risk_plus_extreme_volume",
        "lhb_high_risk_plus_high_intraday_fade",
        "lhb_negative_net_buy_plus_low_close_position",
        "lhb_positive_net_buy_plus_not_overheated",
        "lhb_after_event_attention_plus_technical_weakening",
    }


def test_validate_technical_methods_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_validate_technical_methods",
        lambda **kwargs: {
            "paths": {
                "feature_bucket_effectiveness": "/tmp/feature.csv",
                "combo_effectiveness": "/tmp/combo.csv",
                "regime_effectiveness": "/tmp/regime.csv",
                "case_event_effectiveness": "/tmp/case.csv",
                "lhb_cross_effectiveness": "/tmp/lhb.csv",
                "feature_correlation": "/tmp/corr.csv",
                "redundancy_report": "/tmp/redundancy.csv",
                "recommendation": "/tmp/recommend.csv",
                "report": "/tmp/report.md",
            },
            "dataset": pd.DataFrame([1]),
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "validate-technical-methods",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2026-05-13",
            "--output-dir",
            "/tmp",
        ],
    )
    cli.main()
    out = capsys.readouterr().out
    assert "technical_method_validation|feature_bucket_effectiveness|/tmp/feature.csv" in out
    assert "technical_method_validation|report|/tmp/report.md" in out


def _sample_validation_bars() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=90)
    rows = []
    for asset_id, base, drift in [("CN:SZ:000001", 10.0, 0.08), ("CN:SH:600001", 18.0, 0.03)]:
        prev_close = base
        for idx, trade_date in enumerate(dates):
            close = base + drift * idx + np.sin(idx / 5.0)
            open_ = close * (0.99 + (idx % 3) * 0.002)
            high = max(open_, close) * (1.01 + (idx % 5) * 0.001)
            low = min(open_, close) * (0.99 - (idx % 4) * 0.001)
            volume = 1_000_000 + idx * 10_000 + (50_000 if asset_id.endswith("1") else 0)
            amount = volume * close
            turnover = 1.2 + (idx % 10) * 0.1
            pct_chg = close / prev_close - 1.0 if idx else 0.0
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "preclose": prev_close,
                    "volume": volume,
                    "amount": amount,
                    "turnover_rate": turnover,
                    "pct_chg": pct_chg,
                    "trade_status": "1",
                    "is_st": False,
                }
            )
            prev_close = close
    return pd.DataFrame(rows)


def _sample_case_view() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": "c1",
                "ts_code": "000001.SZ",
                "stock_name": "A",
                "case_year": 2024,
                "verified_case_type": "second_wave",
                "success_or_failure": "success",
                "event_type": "second_wave_start",
                "event_date": "2024-04-15",
            },
            {
                "case_id": "c2",
                "ts_code": "600001.SH",
                "stock_name": "B",
                "case_year": 2024,
                "verified_case_type": "a_kill_failure",
                "success_or_failure": "failure",
                "event_type": "break_limit",
                "event_date": "2024-04-18",
            },
        ]
    )


def _sample_lhb_case_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "case_id": "c1",
                "ts_code": "000001.SZ",
                "stock_name": "A",
                "case_year": 2024,
                "verified_case_type": "second_wave",
                "success_or_failure": "success",
                "event_type": "second_wave_start",
                "event_date": "2024-04-15",
                "lhb_negative_net_buy": False,
                "lhb_institution_selling": False,
                "lhb_high_pump_risk": False,
                "lhb_after_event_attention": False,
                "lhb_risk_score": 0.2,
                "lhb_net_buy_amount_event": 1000000.0,
                "institution_net_buy_event": 400000.0,
                "future_3d_return": 0.03,
                "future_5d_return": 0.05,
                "future_10d_return": 0.08,
                "future_5d_max_drawdown": -0.02,
                "future_10d_max_drawdown": -0.04,
            },
            {
                "case_id": "c2",
                "ts_code": "600001.SH",
                "stock_name": "B",
                "case_year": 2024,
                "verified_case_type": "a_kill_failure",
                "success_or_failure": "failure",
                "event_type": "break_limit",
                "event_date": "2024-04-18",
                "lhb_negative_net_buy": True,
                "lhb_institution_selling": True,
                "lhb_high_pump_risk": True,
                "lhb_after_event_attention": True,
                "lhb_risk_score": 0.8,
                "lhb_net_buy_amount_event": -2000000.0,
                "institution_net_buy_event": -600000.0,
                "future_3d_return": -0.04,
                "future_5d_return": -0.08,
                "future_10d_return": -0.12,
                "future_5d_max_drawdown": -0.09,
                "future_10d_max_drawdown": -0.15,
            },
        ]
    )


def _sample_market_regime() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2024-04-15", "market_regime": "mainline"},
            {"trade_date": "2024-04-16", "market_regime": "mainline"},
            {"trade_date": "2024-04-17", "market_regime": "rotation"},
            {"trade_date": "2024-04-18", "market_regime": "retreat"},
            {"trade_date": "2024-04-19", "market_regime": "retreat"},
        ]
    )
