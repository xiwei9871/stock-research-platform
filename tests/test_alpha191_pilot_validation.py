from pathlib import Path

import pandas as pd

from stock_research.alpha191_pilot_validation import (
    build_alpha191_expanded_validation_from_frames,
    compute_alpha191_expanded_factors,
)


def _sample_bars(asset_id: str = "A", periods: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=periods, freq="D")
    base = pd.Series(range(periods), dtype="float64")
    close = 10 + base * 0.08 + (base % 7) * 0.03
    open_ = close.shift(1).fillna(close.iloc[0] * 0.99) * (1 + ((base % 5) - 2) * 0.003)
    high = pd.concat([open_, close], axis=1).max(axis=1) * (1.02 + (base % 3) * 0.002)
    low = pd.concat([open_, close], axis=1).min(axis=1) * (0.98 - (base % 4) * 0.001)
    return pd.DataFrame(
        {
            "asset_id": asset_id,
            "ts_code": f"{asset_id}.SZ",
            "trade_date": dates.strftime("%Y-%m-%d"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "preclose": close.shift(1),
            "volume": 1000 + base * 17 + (base % 6) * 80,
            "amount": 100000 + base * 2500 + (base % 5) * 20000,
            "turnover_rate": 1.0 + (base % 10) * 0.12,
            "pct_chg": close.pct_change() * 100,
            "is_st": False,
            "trade_status": "1",
        }
    )


def test_compute_alpha191_expanded_factors_adds_broader_gtja191_style_coverage_without_future_leakage():
    bars = _sample_bars(periods=90)
    result = compute_alpha191_expanded_factors(bars)
    alpha_cols = [col for col in result.columns if col.startswith("alpha191_")]

    assert len(alpha_cols) >= 50
    assert {
        "alpha191_gap_open",
        "alpha191_upper_shadow",
        "alpha191_amount_zscore_20",
        "alpha191_vol_adjusted_reversal_3",
        "alpha191_fade_with_amount",
    }.issubset(result.columns)

    changed = bars.copy()
    changed.loc[changed.index[-1], "amount"] = changed["amount"].max() * 100
    changed_result = compute_alpha191_expanded_factors(changed)

    pd.testing.assert_series_equal(
        result.loc[:-2, "alpha191_amount_zscore_20"],
        changed_result.loc[:-2, "alpha191_amount_zscore_20"],
        check_names=False,
    )


def test_alpha191_expanded_validation_writes_v2_diagnostics_and_candidates(tmp_path: Path):
    bars = pd.concat(
        [
            _sample_bars("A", periods=80),
            _sample_bars("B", periods=80).assign(close=lambda frame: frame["close"] * 1.1),
            _sample_bars("C", periods=80).assign(close=lambda frame: frame["close"] * 0.9),
        ],
        ignore_index=True,
    )

    result = build_alpha191_expanded_validation_from_frames(
        bars,
        start_date="2025-01-01",
        end_date="2025-03-31",
        adjust_type="qfq",
        strong_start_date="2025-01-01",
        strong_end_date="2025-03-31",
        output_dir=tmp_path,
    )

    expected = {
        "factor_effectiveness",
        "factor_bucket_effectiveness",
        "strong_winner_explanation",
        "drawdown_risk_effectiveness",
        "redundancy_report",
        "candidate_factors",
        "trend_overlay",
        "high_volatility_risk_split",
        "report",
    }
    assert expected.issubset(result["paths"])
    for key in expected:
        assert Path(result["paths"][key]).exists()
    assert "bucket" in result["factor_bucket_effectiveness"].columns
    assert "avg_future_5d_max_drawdown" in result["drawdown_risk_effectiveness"].columns
    assert "redundancy_group" in result["redundancy_report"].columns
    assert "formal_candidate_decision" in result["candidate_factors"].columns


def test_validate_alpha191_expanded_cli(monkeypatch, capsys, tmp_path: Path):
    from stock_research import cli

    def fake_runner(**kwargs):
        return {
            "paths": {
                "factor_effectiveness": tmp_path / "factor.csv",
                "factor_bucket_effectiveness": tmp_path / "bucket.csv",
                "strong_winner_explanation": tmp_path / "strong.csv",
                "drawdown_risk_effectiveness": tmp_path / "drawdown.csv",
                "redundancy_report": tmp_path / "redundancy.csv",
                "candidate_factors": tmp_path / "candidate.csv",
                "trend_overlay": tmp_path / "trend.csv",
                "high_volatility_risk_split": tmp_path / "vol.csv",
                "report": tmp_path / "report.md",
            },
            "dataset": pd.DataFrame({"x": [1, 2, 3]}),
        }

    monkeypatch.setattr(cli, "run_validate_alpha191_expanded", fake_runner)
    cli.main_for_args(
        [
            "validate-alpha191-expanded",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-01-10",
            "--output-dir",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out

    assert "alpha191_expanded_validation|factor_effectiveness|" in out
    assert "alpha191_expanded_validation|candidate_factors|" in out
    assert "alpha191_expanded_validation|rows|3" in out
