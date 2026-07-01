from pathlib import Path

import pandas as pd


def _equity() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "equity": 1.00, "daily_return": 0.00},
            {"trade_date": "2025-01-31", "equity": 1.10, "daily_return": 0.10},
            {"trade_date": "2025-02-28", "equity": 1.05, "daily_return": -0.045},
        ]
    )


def _holdings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "industry_name": "Tech", "final_slot_rank": 1, "target_weight": 0.1, "confirmed_regime_state": "bull"},
            {"trade_date": "2025-01-02", "asset_id": "B", "industry_name": "Auto", "final_slot_rank": 8, "target_weight": 0.1, "confirmed_regime_state": "bull"},
            {"trade_date": "2025-02-28", "asset_id": "A", "industry_name": "Tech", "final_slot_rank": 1, "target_weight": 0.1, "confirmed_regime_state": "volatile"},
        ]
    )


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "industry_name": "Tech", "score_rank": 1, "target_weight": 0.1, "forward_return": 0.4, "action": "buy"},
            {"trade_date": "2025-01-02", "asset_id": "B", "industry_name": "Auto", "score_rank": 8, "target_weight": 0.1, "forward_return": -0.1, "action": "buy"},
            {"trade_date": "2025-02-28", "asset_id": "C", "industry_name": "Tech", "score_rank": 10, "target_weight": 0.1, "forward_return": 0.2, "action": "buy"},
        ]
    )


def test_build_top10_stability_tables_outputs_required_breakdowns() -> None:
    from stock_research.midtrend_top10_stability_validation_v1 import build_top10_stability_tables

    tables = build_top10_stability_tables(equity=_equity(), holdings=_holdings(), trades=_trades())

    assert set(tables) >= {
        "monthly",
        "quarterly",
        "regime",
        "industry",
        "slot",
        "winner_dependency",
    }
    assert tables["monthly"].iloc[0]["period"] == "2025-01"
    assert "slot_6_to_10" in set(tables["slot"]["slot_bucket"])
    assert tables["winner_dependency"].iloc[0]["top_1_winner_contribution"] > 0


def test_runner_writes_top10_stability_outputs(tmp_path: Path) -> None:
    from stock_research.midtrend_top10_stability_validation_v1 import (
        run_midtrend_top10_stability_validation_from_frames,
    )

    result = run_midtrend_top10_stability_validation_from_frames(
        equity=_equity(),
        holdings=_holdings(),
        trades=_trades(),
        v1_equity=pd.DataFrame(),
        output_dir=tmp_path,
    )

    assert result["paths"]["output_dir"] == str(tmp_path)
    for filename in [
        "top10_monthly_stability.csv",
        "top10_quarterly_stability.csv",
        "top10_regime_stability.csv",
        "top10_industry_stability.csv",
        "top10_slot_stability.csv",
        "top10_winner_dependency.csv",
        "top10_vs_v1_stability_summary.csv",
        "final_interpretation.md",
    ]:
        assert (tmp_path / filename).exists(), filename
