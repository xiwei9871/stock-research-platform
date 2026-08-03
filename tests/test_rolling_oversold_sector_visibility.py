from datetime import date, timedelta

import pandas as pd

from stock_research.rolling_oversold.contracts import RollingOversoldConfig
from stock_research.rolling_oversold.pipeline import _gated_sector_rows
from stock_research.rolling_oversold.sector_scoring import score_sector_states
from stock_research.rolling_oversold.stock_scoring import score_rolling_stock_candidates


ANCHOR = date(2026, 7, 31)


def _config() -> RollingOversoldConfig:
    return RollingOversoldConfig(anchor_start_date=ANCHOR, stock_top_n=10)


def _nuclear_membership() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset_id": [f"CN:SH:{index:06d}" for index in range(1, 26)],
            "concept_system": ["ths"] * 25,
            "concept_code": ["300238"] * 25,
            "concept_name": ["核电"] * 25,
            "start_date": [date(2020, 1, 1)] * 25,
            "end_date": [pd.NaT] * 25,
        }
    )


def _nuclear_bars() -> pd.DataFrame:
    closes = [100.0] * 19 + [80.0, 75.0, 76.0, 78.0, 80.0, 82.0]
    start = ANCHOR - timedelta(days=len(closes) - 1)
    return pd.DataFrame(
        {
            "concept_system": ["ths"] * len(closes),
            "concept_code": ["300238"] * len(closes),
            "concept_name": ["核电"] * len(closes),
            "trade_date": [start + timedelta(days=index) for index in range(len(closes))],
            "close": closes,
            "volume": [100.0] * 20 + [150.0, 170.0, 180.0, 220.0, 260.0],
            "amount": [1000.0] * 20 + [1500.0, 1700.0, 1800.0, 2200.0, 2600.0],
        }
    )


def _nuclear_state() -> pd.DataFrame:
    result = score_sector_states(
        _nuclear_bars(),
        membership=_nuclear_membership(),
        market_regime={"market_regime": "risk_off"},
        anchor_date=ANCHOR,
    )
    nuclear = result.loc[result["sector_code"].eq("300238")].copy()
    assert len(nuclear) == 1
    return nuclear


def _stock_features() -> pd.DataFrame:
    rows = []
    for sector_code, sector_name, prefix in (
        ("300238", "核电", "CN:SH"),
        ("I2", "Other", "CN:SZ"),
        ("I3", "Blocked data", "CN:BJ"),
    ):
        for index in range(2):
            rows.append(
                {
                    "asset_id": f"{prefix}:{index + 1:06d}",
                    "sector_system": "ths" if sector_code == "300238" else "sw",
                    "sector_code": sector_code,
                    "sector_name": sector_name,
                    "anchor_return": 0.03 + index * 0.01,
                    "distance_to_252d_high": 0.25 + index * 0.03,
                    "oversold_depth": 0.30 + index * 0.02,
                    "stock_excess_return": 0.05 + index * 0.01,
                    "activity": 100.0 + index,
                    "quality": 70.0 + index,
                    "valuation": 75.0 + index,
                    "size_elasticity": 10.0 + index,
                    "anchor_close": 10.0 + index,
                    "adjusted_close_source": "qfq",
                }
            )
    return pd.DataFrame(rows)


def _sector_states_for_stock_scoring() -> pd.DataFrame:
    nuclear = _nuclear_state()
    nuclear.loc[:, "sector_gate_status"] = "blocked"
    nuclear.loc[:, "sector_research_eligibility"] = "eligible"

    other = nuclear.copy()
    other.loc[:, "sector_system"] = "sw"
    other.loc[:, "sector_code"] = "I2"
    other.loc[:, "sector_name"] = "Other"
    other.loc[:, "sector_gate_status"] = "blocked"
    other.loc[:, "sector_research_eligibility"] = "watch"

    blocked_data = nuclear.copy()
    blocked_data.loc[:, "sector_system"] = "sw"
    blocked_data.loc[:, "sector_code"] = "I3"
    blocked_data.loc[:, "sector_name"] = "Blocked data"
    blocked_data.loc[:, "sector_gate_status"] = "blocked"
    blocked_data.loc[:, "sector_research_eligibility"] = "blocked_data"
    return pd.concat([nuclear, other, blocked_data], ignore_index=True)


def test_eligible_sector_is_retained_when_legacy_gate_is_blocked_and_data_is_complete():
    sectors = _nuclear_state()
    sectors.loc[:, "sector_gate_status"] = "blocked"

    selected = _gated_sector_rows(sectors, top_n=10)

    assert selected["sector_code"].tolist() == ["300238"]
    assert selected.iloc[0]["sector_gate_status"] == "blocked"
    assert selected.iloc[0]["sector_research_eligibility"] in {"eligible", "watch"}


def test_blocked_data_sector_is_not_selected_but_research_visible_blocked_sector_scores_stocks():
    sectors = _sector_states_for_stock_scoring()
    selected = _gated_sector_rows(sectors, top_n=10)
    result = score_rolling_stock_candidates(
        _stock_features(),
        sectors,
        top_n=10,
        config=_config(),
        sector_selection=selected,
    )

    assert set(result["sector_code"]) == {"300238", "I2"}
    assert "I3" not in set(result["sector_code"])
    assert result.loc[result["sector_code"].eq("300238"), "sector_gate_status"].eq("blocked").all()
    assert result.loc[result["sector_code"].eq("300238"), "sector_research_eligibility"].eq("eligible").all()
    assert result.loc[result["sector_code"].eq("I2"), "score_status"].eq("sector_watch").all()


def test_sector_stock_rank_restarts_per_sector_and_legacy_stock_rank_remains_global():
    sectors = _sector_states_for_stock_scoring().iloc[:2].copy()
    result = score_rolling_stock_candidates(
        _stock_features().loc[lambda frame: frame["sector_code"].isin(["300238", "I2"])],
        sectors,
        top_n=10,
        config=_config(),
        sector_selection=sectors,
    )

    assert result.groupby(["sector_system", "sector_code"])["sector_stock_rank"].min().eq(1).all()
    assert result.groupby(["sector_system", "sector_code"])["sector_stock_rank"].apply(list).to_dict() == {
        ("sw", "I2"): [1, 2],
        ("ths", "300238"): [1, 2],
    }
    assert result["stock_rank"].tolist() == [1, 2, 3, 4]
    assert result["sector_gate_status"].eq("blocked").all()
    assert result["sector_research_eligibility"].isin({"eligible", "watch"}).all()
