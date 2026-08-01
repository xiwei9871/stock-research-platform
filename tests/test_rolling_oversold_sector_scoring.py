from datetime import date, timedelta

import pandas as pd
import pytest

from stock_research.rolling_oversold.sector_scoring import _activity_scores, score_sector_states


def _bars_for(closes, *, anchor, code="I1", system="sw", name="Industry one"):
    start = anchor - timedelta(days=len(closes) - 1)
    return pd.DataFrame(
        {
            "industry_system": [system] * len(closes),
            "industry_code": [code] * len(closes),
            "industry_name": [name] * len(closes),
            "trade_date": [start + timedelta(days=index) for index in range(len(closes))],
            "close": closes,
            "amount": [100.0] * len(closes),
        }
    )


def _membership(*codes):
    return pd.DataFrame(
        [
            {
                "asset_id": f"{code}_A",
                "industry_system": "sw",
                "industry_code": code,
                "industry_name": "Industry one" if code == "I1" else "Industry two",
            }
            for code in codes
        ]
    )


def test_sector_score_marks_deep_drawdown_with_positive_repairability_as_confirmed():
    anchor = date(2026, 7, 3)
    bars = _bars_for(([100.0] * 246) + [100.0, 96.0, 92.0, 88.0, 84.0, 86.0], anchor=anchor)

    result = score_sector_states(
        bars,
        membership=_membership("I1"),
        market_regime={"market_regime": "neutral"},
        anchor_date=anchor,
    )

    row = result.iloc[0]
    assert row["sector_oversold_score"] >= 70.0
    assert row["sector_repairability_score"] >= 60.0
    assert row["sector_gate_status"] == "confirmed"
    assert row["sector_recovery_state"] == "repairing"


def test_sector_near_high_is_repaired_not_fresh_oversold():
    anchor = date(2026, 7, 3)
    result = score_sector_states(
        _bars_for([100.0, 101.0, 102.0, 103.0, 104.0, 105.0], anchor=anchor),
        membership=_membership("I1"),
        market_regime={"market_regime": "risk_on"},
        anchor_date=anchor,
    )

    row = result.iloc[0]
    assert row["sector_recovery_state"] == "repaired"
    assert row["sector_gate_status"] != "confirmed"


def test_sector_membership_without_bars_is_preserved_as_blocked():
    anchor = date(2026, 7, 3)
    result = score_sector_states(
        _bars_for([100.0] * 6, anchor=anchor),
        membership=_membership("I1", "I2"),
        market_regime={"market_regime": "neutral"},
        anchor_date=anchor,
    )

    missing_row = result.loc[result["sector_code"] == "I2"].iloc[0]
    assert missing_row["sector_gate_status"] == "blocked"
    assert missing_row["sector_recovery_state"] == "unknown"


def test_sector_scoring_does_not_use_future_bars():
    anchor = date(2026, 7, 3)
    bars = _bars_for([100.0, 96.0, 92.0, 88.0, 84.0, 86.0], anchor=anchor)
    future = bars.iloc[[-1]].copy()
    future["trade_date"] = anchor + timedelta(days=1)
    future["close"] = 200.0

    result = score_sector_states(
        pd.concat([bars, future], ignore_index=True),
        membership=_membership("I1"),
        market_regime={"market_regime": "neutral"},
        anchor_date=anchor,
    )

    assert result.iloc[0]["data_cutoff_date"] == anchor
    assert result.iloc[0]["ret_5d"] < 0.0


def test_sector_scoring_maps_concept_schema_to_canonical_identity():
    anchor = date(2026, 7, 3)
    bars = _bars_for(
        [100.0, 101.0, 102.0, 103.0, 104.0, 105.0], anchor=anchor
    ).rename(
        columns={
            "industry_system": "concept_system",
            "industry_code": "concept_code",
            "industry_name": "concept_name",
        }
    )
    membership = _membership("I1").rename(
        columns={
            "industry_system": "concept_system",
            "industry_code": "concept_code",
            "industry_name": "concept_name",
        }
    )

    result = score_sector_states(
        bars,
        membership=membership,
        market_regime={"market_regime": "neutral"},
        anchor_date=anchor,
    )

    assert result.iloc[0]["sector_system"] == "sw"
    assert result.iloc[0]["sector_code"] == "I1"


def test_sector_with_missing_canonical_mapping_is_retained_but_blocked():
    anchor = date(2026, 7, 3)
    bars = pd.DataFrame(
        {
            "trade_date": [anchor - timedelta(days=index) for index in range(6)],
            "close": [100.0] * 6,
            "amount": [100.0] * 6,
        }
    )

    result = score_sector_states(
        bars,
        membership=pd.DataFrame(),
        market_regime={"market_regime": "neutral"},
        anchor_date=anchor,
    )

    row = result.iloc[0]
    assert pd.isna(row["sector_system"])
    assert pd.isna(row["sector_code"])
    assert pd.isna(row["sector_name"])
    assert not row["sector_mapping_valid"]
    assert row["sector_mapping_reason"] == (
        "missing_sector_system|missing_sector_code|missing_sector_name"
    )
    assert row["sector_recovery_state"] == "unknown"
    assert row["sector_gate_status"] == "blocked"


def test_activity_score_percentile_clips_ratio_and_keeps_one_row_neutral():
    many = _activity_scores(
        pd.DataFrame(
            {
                "amount_20d": [100.0, 100.0, 100.0],
                "amount_ratio_5_20": [0.1, 1.0, 10.0],
            }
        )
    )
    one = _activity_scores(
        pd.DataFrame({"amount_20d": [100.0], "amount_ratio_5_20": [10.0]})
    )

    assert many.tolist() == pytest.approx([53.333333, 66.666667, 80.0])
    assert one.iloc[0] == pytest.approx(50.0)


def test_future_only_sector_bar_key_is_retained_as_blocked_unknown():
    anchor = date(2026, 7, 3)
    result = score_sector_states(
        _bars_for(
            [100.0] * 6, anchor=anchor + timedelta(days=6), code="FUT", name="Future sector"
        ),
        membership=pd.DataFrame(),
        market_regime={"market_regime": "neutral"},
        anchor_date=anchor,
    )

    row = result.iloc[0]
    assert row["sector_code"] == "FUT"
    assert row["data_cutoff_date"] is pd.NaT
    assert row["sector_recovery_state"] == "unknown"
    assert row["sector_gate_status"] == "blocked"
