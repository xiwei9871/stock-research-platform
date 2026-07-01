from pathlib import Path

import pandas as pd


def _holdings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "industry_name": "Tech", "final_slot_rank": 1, "target_weight": 0.1, "volatility_20_score": 80, "forward_return": 0.4},
            {"trade_date": "2025-01-02", "asset_id": "B", "industry_name": "Tech", "final_slot_rank": 8, "target_weight": 0.1, "volatility_20_score": 20, "forward_return": -0.2},
            {"trade_date": "2025-01-02", "asset_id": "C", "industry_name": "Auto", "final_slot_rank": 10, "target_weight": 0.1, "volatility_20_score": 60, "forward_return": 0.1},
        ]
    )


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "industry_name": "Tech", "score_rank": 1, "target_weight": 0.1, "forward_return": 0.4},
            {"trade_date": "2025-01-02", "asset_id": "B", "industry_name": "Tech", "score_rank": 8, "target_weight": 0.1, "forward_return": -0.2},
            {"trade_date": "2025-01-02", "asset_id": "C", "industry_name": "Auto", "score_rank": 10, "target_weight": 0.1, "forward_return": 0.1},
        ]
    )


def test_build_position_sizing_proxy_comparison_contains_research_variants() -> None:
    from stock_research.midtrend_position_sizing_industry_research_v1 import (
        build_position_sizing_proxy_comparison,
    )

    result = build_position_sizing_proxy_comparison(_holdings())

    assert set(result["proxy_name"]) == {"top10_equal_weight", "top10_rank_decay", "top10_volatility_cap"}
    rank_decay = result[result["proxy_name"].eq("top10_rank_decay")].iloc[0]
    assert rank_decay["research_only"] is True


def test_build_industry_concentration_diagnostics_counts_crowding() -> None:
    from stock_research.midtrend_position_sizing_industry_research_v1 import (
        build_industry_concentration_diagnostics,
    )

    result = build_industry_concentration_diagnostics(_holdings(), _trades())
    tech = result[result["industry_name"].eq("Tech")].iloc[0]

    assert tech["holding_count"] == 2
    assert tech["industry_weight"] == 0.2
    assert tech["industry_contribution"] == 0.02


def test_runner_writes_position_sizing_industry_outputs(tmp_path: Path) -> None:
    from stock_research.midtrend_position_sizing_industry_research_v1 import (
        run_midtrend_position_sizing_industry_research_from_frames,
    )

    result = run_midtrend_position_sizing_industry_research_from_frames(
        holdings=_holdings(),
        trades=_trades(),
        industry_exposure=pd.DataFrame(),
        output_dir=tmp_path,
    )

    assert result["paths"]["output_dir"] == str(tmp_path)
    for filename in [
        "position_sizing_proxy_comparison.csv",
        "rank_decay_weight_diagnostics.csv",
        "volatility_cap_weight_diagnostics.csv",
        "industry_concentration_diagnostics.csv",
        "industry_contribution_summary.csv",
        "industry_concentration_rule_candidates_research_only.md",
        "final_interpretation.md",
    ]:
        assert (tmp_path / filename).exists(), filename
    assert "RESEARCH_ONLY" in (tmp_path / "industry_concentration_rule_candidates_research_only.md").read_text(encoding="utf-8")
