from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from stock_research.rolling_oversold.outcomes import (
    evaluate_snapshot,
    summarize_rolling_evaluation,
)
from stock_research.rolling_oversold.snapshots import build_rolling_snapshot


def _snapshot(
    *,
    anchor_date: str = "2026-07-21",
    anchor_close: object = 10.0,
    sector_code: str = "I1",
    market_regime: str = "risk_off",
    recovery_state: str = "repairing",
    gate_status: str = "confirmed",
    lifecycle: str = "expected_repair",
    rank: object = 1,
) -> dict[str, object]:
    return {
        "snapshot_id": f"rolling_oversold_v1|{anchor_date}",
        "anchor_date": anchor_date,
        "market_regime": {"market_regime": market_regime},
        "stock_candidates": pd.DataFrame(
            [
                {
                    "asset_id": "000001",
                    "anchor_close": anchor_close,
                    "adjusted_close_source": "qfq",
                    "sector_system": "sw",
                    "sector_code": sector_code,
                    "sector_name": "Industry one",
                    "sector_gate_status": gate_status,
                    "sector_recovery_state": recovery_state,
                    "stock_lifecycle": lifecycle,
                    "stock_rank": rank,
                }
            ]
        ),
    }


def _bars(rows: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "000001", "trade_date": trade_date, "qfq_close": close}
            for trade_date, close in rows
        ]
    )


def test_evaluate_snapshot_uses_strictly_future_trading_sessions():
    bars = _bars(
        [
            ("2026-07-21", 10.0),
            ("2026-07-22", 10.2),
            ("2026-07-23", 10.1),
            ("2026-07-24", 10.4),
            ("2026-07-27", 10.6),
            ("2026-07-28", 10.5),
        ]
    )

    result = evaluate_snapshot(
        _snapshot(), bars=bars, evaluation_cutoff=date(2026, 7, 28)
    )

    assert result["forward_horizon_days"].tolist() == [1, 3, 5]
    assert result["forward_Nd_return"].tolist() == pytest.approx([0.02, 0.04, 0.05])
    assert result["forward_Nd_status"].tolist() == ["complete", "complete", "complete"]
    assert result["forward_endpoint_date"].tolist() == [
        "2026-07-22",
        "2026-07-24",
        "2026-07-28",
    ]
    assert result["adjusted_close_source"].tolist() == ["qfq", "qfq", "qfq"]


def test_evaluate_snapshot_accepts_frozen_outcome_columns_from_built_snapshot():
    stocks = _snapshot()["stock_candidates"].assign(
        sector_oversold_score=80.0,
        sector_repairability_score=70.0,
        sector_direction_score=60.0,
        stock_score=90.0,
    )
    sectors = pd.DataFrame(
        [
            {
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
                "sector_oversold_score": 80.0,
                "sector_repairability_score": 70.0,
                "sector_direction_score": 60.0,
                "sector_recovery_state": "repairing",
                "sector_gate_status": "confirmed",
            }
        ]
    )
    snapshot = build_rolling_snapshot(
        anchor_date=date(2026, 7, 21),
        data_cutoff_date=date(2026, 7, 20),
        market_regime={"market_regime": "risk_off"},
        sector_states=sectors,
        stock_candidates=stocks,
        previous_snapshot=None,
        score_version="rolling_oversold_v1",
    )

    result = evaluate_snapshot(
        snapshot, bars=_bars([("2026-07-22", 10.2)]), evaluation_cutoff=date(2026, 7, 22), horizons=[1]
    )

    assert snapshot["stock_candidates"].loc[0, "anchor_close"] == 10.0
    assert snapshot["stock_candidates"].loc[0, "adjusted_close_source"] == "qfq"
    assert result.loc[0, "forward_Nd_return"] == pytest.approx(0.02)


def test_evaluate_snapshot_marks_unavailable_trading_horizons_pending_without_fill():
    result = evaluate_snapshot(
        _snapshot(anchor_date="2026-07-30"),
        bars=_bars([("2026-07-30", 10.0), ("2026-07-31", 10.2)]),
        evaluation_cutoff=date(2026, 7, 31),
    )

    assert result["forward_Nd_status"].tolist() == ["complete", "pending", "pending"]
    assert result.loc[result["forward_horizon_days"].eq(1), "forward_Nd_return"].iloc[0] == pytest.approx(0.02)
    assert result.loc[result["forward_horizon_days"].isin([3, 5]), "forward_Nd_return"].isna().all()
    assert result.loc[result["forward_horizon_days"].isin([3, 5]), "forward_endpoint_date"].isna().all()


def test_evaluate_snapshot_uses_sessions_not_calendar_dates_and_honors_cutoff_without_mutation():
    snapshot = _snapshot()
    bars = _bars(
        [
            ("2026-07-21", 10.0),
            ("2026-07-22", 10.2),
            ("2026-07-24", 10.4),
            ("2026-07-27", 10.6),
            ("2026-07-28", 99.0),
        ]
    )
    before = bars.copy(deep=True)

    result = evaluate_snapshot(
        snapshot, bars=bars, evaluation_cutoff=date(2026, 7, 27), horizons=(3,)
    )

    assert result.loc[0, "forward_endpoint_date"] == "2026-07-27"
    assert result.loc[0, "forward_Nd_return"] == pytest.approx(0.06)
    pd.testing.assert_frame_equal(bars, before)
    pd.testing.assert_frame_equal(snapshot["stock_candidates"], _snapshot()["stock_candidates"])


def test_evaluate_snapshot_keeps_auditable_rows_with_bad_anchor_close_and_rejects_ambiguous_input():
    missing = evaluate_snapshot(
        _snapshot(anchor_close=None),
        bars=_bars([("2026-07-22", 10.2)]),
        evaluation_cutoff=date(2026, 7, 22),
    )
    assert missing["data_status"].tolist() == ["missing_anchor_close"] * 3
    assert missing["forward_Nd_status"].tolist() == ["pending"] * 3
    assert missing["forward_Nd_return"].isna().all()
    invalid_close = evaluate_snapshot(
        _snapshot(anchor_close=0),
        bars=_bars([("2026-07-22", 10.2)]),
        evaluation_cutoff=date(2026, 7, 22),
    )
    assert invalid_close["data_status"].tolist() == ["invalid_anchor_close"] * 3

    duplicate_bars = pd.concat([_bars([("2026-07-22", 10.2)]), _bars([("2026-07-22", 10.3)])])
    with pytest.raises(ValueError, match="duplicate bar"):
        evaluate_snapshot(_snapshot(), bars=duplicate_bars, evaluation_cutoff=date(2026, 7, 22))
    with pytest.raises(ValueError, match="horizons must contain unique"):
        evaluate_snapshot(_snapshot(), bars=_bars([]), evaluation_cutoff=date(2026, 7, 22), horizons=(1, 1))
    with pytest.raises(ValueError, match="anchor_date"):
        evaluate_snapshot(
            _snapshot(anchor_date="not-a-date"),
            bars=_bars([]),
            evaluation_cutoff=date(2026, 7, 22),
        )
    with pytest.raises(ValueError, match="does not provide qfq"):
        evaluate_snapshot(
            _snapshot(),
            bars=pd.DataFrame(
                [{"asset_id": "000001", "trade_date": "2026-07-22", "hfq_close": 10.2}]
            ),
            evaluation_cutoff=date(2026, 7, 22),
        )


def test_evaluate_snapshot_excludes_blocked_and_invalidated_rows_from_calibration():
    blocked = evaluate_snapshot(
        _snapshot(gate_status="blocked"),
        bars=_bars([("2026-07-22", 10.2)]),
        evaluation_cutoff=date(2026, 7, 22),
        horizons=[1],
    )
    invalidated = evaluate_snapshot(
        _snapshot(lifecycle="invalidated"),
        bars=_bars([("2026-07-22", 10.2)]),
        evaluation_cutoff=date(2026, 7, 22),
        horizons=[1],
    )
    eligible = evaluate_snapshot(
        _snapshot(),
        bars=_bars([("2026-07-22", 10.2)]),
        evaluation_cutoff=date(2026, 7, 22),
        horizons=[1],
    )

    assert blocked.loc[0, "evaluation_status"] == "excluded_blocked"
    assert invalidated.loc[0, "evaluation_status"] == "excluded_invalidated"
    assert blocked["forward_Nd_return"].isna().all()
    assert invalidated[["hit_3pct", "hit_5pct", "hit_7pct"]].isna().all(axis=None)
    summary = summarize_rolling_evaluation(pd.concat([eligible, blocked, invalidated]))
    overall = summary.loc[summary["group_by"].eq("overall")].iloc[0]
    assert overall[["total_count", "complete_count", "pending_count", "excluded_count"]].tolist() == [3, 1, 0, 2]
    with pytest.raises(ValueError, match="bars trade_date"):
        evaluate_snapshot(
            _snapshot(),
            bars=_bars([("not-a-date", 10.2)]),
            evaluation_cutoff=date(2026, 7, 22),
        )


def test_summarize_evaluation_reports_completed_pending_and_contextual_hit_rates():
    first = evaluate_snapshot(
        _snapshot(),
        bars=_bars(
            [
                ("2026-07-22", 10.3),
                ("2026-07-23", 10.4),
                ("2026-07-24", 10.5),
                ("2026-07-27", 10.6),
                ("2026-07-28", 10.7),
            ]
        ),
        evaluation_cutoff=date(2026, 7, 28),
    )
    second = first.copy(deep=True)
    second.loc[:, "asset_id"] = "000002"
    second.loc[:, "sector_code"] = "I2"
    second.loc[:, "market_regime"] = "risk_on"
    second.loc[:, "sector_recovery_state"] = "fresh_oversold"
    second.loc[:, "stock_lifecycle"] = "new_oversold"
    second.loc[:, "stock_rank"] = 7
    second.loc[:, "forward_Nd_status"] = "pending"
    second.loc[:, "forward_Nd_return"] = float("nan")
    detail = pd.concat([first, second], ignore_index=True)

    summary = summarize_rolling_evaluation(detail)

    overall = summary.loc[
        summary["group_by"].eq("overall") & summary["forward_horizon_days"].eq(1)
    ].iloc[0]
    assert overall["total_count"] == 2
    assert overall["complete_count"] == 1
    assert overall["pending_count"] == 1
    assert overall["up_ratio"] == pytest.approx(1.0)
    assert overall["hit_3pct_rate"] == pytest.approx(1.0)
    sector = summary.loc[
        summary["group_by"].eq("sector") & summary["group_value"].eq("sw:I1")
        & summary["forward_horizon_days"].eq(1)
    ].iloc[0]
    assert sector["hit_3pct_rate"] == pytest.approx(1.0)
    assert {"market_regime", "sector_recovery_state", "stock_lifecycle", "rank_bucket"}.issubset(
        set(summary["group_by"])
    )
    empty = summarize_rolling_evaluation(detail.iloc[0:0])
    assert list(empty.columns) == list(summary.columns)
    assert empty.empty
