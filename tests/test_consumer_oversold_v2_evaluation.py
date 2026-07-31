from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from stock_research.consumer_oversold import loaders
from stock_research.consumer_oversold.v2_evaluation import evaluate_v2_snapshot


SNAPSHOT_DATE = "2026-07-27"
OUTCOME_DATES = (
    "2026-07-28",
    "2026-07-29",
    "2026-07-30",
    "2026-07-31",
    "2026-08-03",
)


def _ranked_snapshot(count: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": [SNAPSHOT_DATE] * count,
            "asset_id": [f"A{rank:02d}" for rank in range(1, count + 1)],
            "final_rank": list(range(1, count + 1)),
            "final_rank_score_v2": [101.0 - rank for rank in range(1, count + 1)],
        }
    )


def _qualified_pool_snapshot(count: int) -> pd.DataFrame:
    return _ranked_snapshot(count)


def _target_return(rank: int, horizon: int) -> float:
    if rank <= 4:
        return 0.08 if horizon == 3 else 0.10
    if rank <= 18:
        return 0.01 if horizon == 3 else 0.02
    if rank <= 30:
        return -0.01 if horizon == 3 else -0.005
    return 0.0


def _daily_bars(count: int, *, include_fifth_day: bool = True) -> pd.DataFrame:
    dates = (SNAPSHOT_DATE, *OUTCOME_DATES)
    if not include_fifth_day:
        dates = dates[:4]
    rows: list[dict[str, object]] = []
    for rank in range(1, count + 1):
        asset_id = f"A{rank:02d}"
        return_3d = _target_return(rank, 3)
        return_5d = _target_return(rank, 5)
        for offset, trade_date in enumerate(dates):
            if offset <= 3:
                cumulative_return = return_3d * offset / 3.0
            else:
                cumulative_return = return_3d + (return_5d - return_3d) * (offset - 3) / 2.0
            close = 100.0 * (1.0 + cumulative_return)
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": trade_date,
                    "hfq_close": close,
                    "raw_open": close,
                    "raw_high": close * (1.02 if offset else 1.0),
                    "raw_low": close * (0.99 if offset else 1.0),
                    "raw_close": close,
                }
            )
    frame = pd.DataFrame(rows)
    frame.attrs["outcome_dates"] = list(OUTCOME_DATES)
    return frame


def _minute_bars(asset_ids: list[str], outcome_dates: tuple[str, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    morning = pd.date_range("2026-07-30 09:35", "2026-07-30 11:30", freq="5min")
    afternoon = pd.date_range("2026-07-30 13:05", "2026-07-30 15:00", freq="5min")
    base_times = (*morning, *afternoon)
    assert len(base_times) == 48
    for asset_id in asset_ids:
        for outcome_date in outcome_dates:
            day = pd.Timestamp(outcome_date)
            for position, base_time in enumerate(base_times):
                trade_time = day + (base_time - base_time.normalize())
                close = 100.0 + position / 10.0
                rows.append(
                    {
                        "asset_id": asset_id,
                        "trade_date": outcome_date,
                        "trade_time": trade_time,
                        "open": close - 0.05,
                        "high": close + (5.0 if position == 12 else 0.1),
                        "low": close - 0.1,
                        "close": close,
                        "limit_up_price": 104.7,
                    }
                )
    return pd.DataFrame(rows)


def test_v2_evaluation_reports_top20_top30_and_three_rank_segments():
    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(30),
        qualified_pool=_qualified_pool_snapshot(45),
        daily_bars=_daily_bars(45),
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    summary = result["summary"].set_index("group")
    assert set(summary.index) == {"top20", "top30", "01-10", "11-20", "21-30"}
    assert summary.loc["top30", "member_count"] == 30
    assert summary.loc["top30", "completed_count"] == 30
    assert summary.loc["top30", "rising_count"] == 18
    assert summary.loc["top30", "rising_ratio"] == pytest.approx(0.60)
    assert summary.loc["top30", "gte_5pct_count"] == 4
    assert summary.loc["top30", "mean_return"] == pytest.approx(0.0113333333)
    assert summary.loc["top30", "positive_mean_return"] == pytest.approx(0.0255555556)
    assert summary.loc["top30", "spearman_rank_correlation"] > 0.0
    assert 0.0 <= summary.loc["top30", "balanced_evaluation"] <= 100.0
    assert "qualified_pool_excess_return" in summary.columns


def test_three_and_five_day_horizons_use_explicit_trading_outcome_dates():
    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(2),
        qualified_pool=_qualified_pool_snapshot(2),
        daily_bars=_daily_bars(2),
        minute_bars=pd.DataFrame(),
    )

    detail = result["detail"].set_index(["asset_id", "horizon"])
    assert detail.loc[("A01", 3), "horizon_trade_date"] == "2026-07-30"
    assert detail.loc[("A01", 5), "horizon_trade_date"] == "2026-08-03"
    assert detail.loc[("A01", 3), "forward_return"] == pytest.approx(0.08)
    assert detail.loc[("A01", 5), "forward_return"] == pytest.approx(0.10)
    summary = result["summary"].set_index(["group", "horizon"])
    expected_overall = (
        0.30 * summary.loc[("top20", 3), "balanced_evaluation"]
        + 0.70 * summary.loc[("top20", 5), "balanced_evaluation"]
    )
    assert summary.loc[("top20", 3), "overall_evaluation"] == pytest.approx(
        expected_overall
    )
    assert summary.loc[("top20", 5), "overall_evaluation"] == pytest.approx(
        expected_overall
    )


def test_ambiguous_observed_bar_calendar_is_rejected():
    bars = _daily_bars(1)
    bars.attrs.clear()

    with pytest.raises(ValueError, match="authoritative outcome calendar"):
        evaluate_v2_snapshot(
            snapshot=_ranked_snapshot(1),
            qualified_pool=_qualified_pool_snapshot(1),
            daily_bars=bars,
            minute_bars=pd.DataFrame(),
            horizons=(3,),
        )


def test_authoritative_calendar_does_not_shift_target_when_a_market_day_is_missing():
    bars = _daily_bars(1).loc[
        ~_daily_bars(1)["trade_date"].eq("2026-07-29")
    ].copy()
    bars.attrs["outcome_dates"] = list(OUTCOME_DATES)

    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(1),
        qualified_pool=_qualified_pool_snapshot(1),
        daily_bars=bars,
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    row = result["detail"].iloc[0]
    assert row["horizon_trade_date"] == "2026-07-30"
    assert row["evaluation_status"] == "missing_outcome_bar"
    assert result["coverage"]["daily_complete"] is False


def test_partial_selected_group_does_not_publish_comparable_scores():
    bars = _daily_bars(3)
    bars = bars.loc[
        ~(
            bars["asset_id"].eq("A02")
            & bars["trade_date"].eq("2026-07-30")
        )
    ]

    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(3),
        qualified_pool=_qualified_pool_snapshot(3),
        daily_bars=bars,
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    top20 = result["summary"].set_index("group").loc["top20"]
    assert top20["member_count"] == 3
    assert top20["completed_count"] == 2
    assert top20["pending_count"] == 1
    assert top20["group_evaluation_status"] == "partial"
    assert pd.isna(top20["mean_return"])
    assert pd.isna(top20["balanced_evaluation"])
    assert pd.isna(top20["overall_evaluation"])


def test_daily_evaluation_accepts_conventional_ohlc_aliases():
    bars = _daily_bars(2).rename(
        columns={
            "hfq_close": "close",
            "raw_open": "open",
            "raw_high": "high",
            "raw_low": "low",
        }
    ).drop(columns="raw_close")

    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(2),
        qualified_pool=_qualified_pool_snapshot(2),
        daily_bars=bars,
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    assert result["detail"]["evaluation_status"].eq("completed").all()


def test_daily_evaluation_does_not_invent_raw_ohl_from_hfq_close():
    bars = _daily_bars(2).loc[:, ["asset_id", "trade_date", "hfq_close"]].rename(
        columns={"hfq_close": "close"}
    )

    with pytest.raises(ValueError, match="raw_open, raw_high, raw_low"):
        evaluate_v2_snapshot(
            snapshot=_ranked_snapshot(2),
            qualified_pool=_qualified_pool_snapshot(2),
            daily_bars=bars,
            minute_bars=pd.DataFrame(),
            horizons=(3,),
        )


def test_partial_pool_keeps_all_five_groups_with_actual_available_counts():
    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(12),
        qualified_pool=_qualified_pool_snapshot(12),
        daily_bars=_daily_bars(12),
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    summary = result["summary"].set_index("group")
    assert summary["member_count"].to_dict() == {
        "top20": 12,
        "top30": 12,
        "01-10": 10,
        "11-20": 2,
        "21-30": 0,
    }


def test_balanced_evaluation_remains_finite_when_every_member_falls():
    bars = _daily_bars(3)
    outcome_mask = bars["trade_date"].ne(SNAPSHOT_DATE)
    steps = bars.loc[outcome_mask].groupby("asset_id").cumcount() + 1
    falling_close = 100.0 * (1.0 - 0.01 * steps)
    bars.loc[outcome_mask, "hfq_close"] = falling_close.to_numpy()
    bars.loc[outcome_mask, "raw_open"] = falling_close.to_numpy()
    bars.loc[outcome_mask, "raw_high"] = falling_close.to_numpy()
    bars.loc[outcome_mask, "raw_low"] = falling_close.to_numpy()
    bars.loc[outcome_mask, "raw_close"] = falling_close.to_numpy()

    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(3),
        qualified_pool=_qualified_pool_snapshot(3),
        daily_bars=bars,
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    top20 = result["summary"].set_index("group").loc["top20"]
    assert top20["rising_count"] == 0
    assert np.isfinite(top20["balanced_evaluation"])


def test_bars_after_requested_horizon_cannot_change_evaluation():
    base = _daily_bars(3)
    future = pd.DataFrame(
        [
            {
                "asset_id": f"A{rank:02d}",
                "trade_date": "2026-08-04",
                "hfq_close": 9999.0,
                "raw_open": 9999.0,
                "raw_high": 9999.0,
                "raw_low": 1.0,
                "raw_close": 9999.0,
            }
            for rank in range(1, 4)
        ]
    )
    kwargs = {
        "snapshot": _ranked_snapshot(3),
        "qualified_pool": _qualified_pool_snapshot(3),
        "minute_bars": pd.DataFrame(),
        "outcome_dates": OUTCOME_DATES,
        "horizons": (3,),
    }

    first = evaluate_v2_snapshot(daily_bars=base, **kwargs)
    second = evaluate_v2_snapshot(daily_bars=pd.concat([base, future]), **kwargs)

    pdt.assert_frame_equal(first["detail"], second["detail"])
    pdt.assert_frame_equal(first["summary"], second["summary"])


def test_daily_detail_reports_path_drawdown_maximum_high_and_close_fade():
    bars = pd.DataFrame(
        [
            ["A01", "2026-07-27", 100.0, 100.0, 100.0, 100.0, 100.0],
            ["A01", "2026-07-28", 110.0, 105.0, 120.0, 104.0, 110.0],
            ["A01", "2026-07-29", 88.0, 90.0, 92.0, 85.0, 88.0],
            ["A01", "2026-07-30", 99.0, 95.0, 102.0, 94.0, 99.0],
        ],
        columns=[
            "asset_id",
            "trade_date",
            "hfq_close",
            "raw_open",
            "raw_high",
            "raw_low",
            "raw_close",
        ],
    )
    bars.attrs["outcome_dates"] = list(OUTCOME_DATES)

    row = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(1),
        qualified_pool=_qualified_pool_snapshot(1),
        daily_bars=bars,
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )["detail"].iloc[0]

    assert row["forward_return"] == pytest.approx(-0.01)
    assert row["path_max_drawdown"] == pytest.approx(-0.20)
    assert row["max_high_return"] == pytest.approx(0.20)
    assert row["high_to_close_fade"] == pytest.approx((120.0 - 99.0) / 120.0)
    assert row["retention_ratio"] == 0.0


def test_forward_high_metrics_exclude_the_frozen_snapshot_day_high():
    bars = pd.DataFrame(
        [
            ["A01", "2026-07-27", 100.0, 100.0, 120.0, 100.0, 100.0],
            ["A01", "2026-07-28", 100.5, 100.0, 101.0, 99.5, 100.5],
            ["A01", "2026-07-29", 100.5, 100.5, 100.8, 100.0, 100.5],
            ["A01", "2026-07-30", 100.5, 100.5, 100.9, 100.0, 100.5],
        ],
        columns=[
            "asset_id",
            "trade_date",
            "hfq_close",
            "raw_open",
            "raw_high",
            "raw_low",
            "raw_close",
        ],
    )
    bars.attrs["outcome_dates"] = list(OUTCOME_DATES)

    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(1),
        qualified_pool=_qualified_pool_snapshot(1),
        daily_bars=bars,
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    row = result["detail"].iloc[0]
    assert row["max_high_return"] == pytest.approx(0.01)
    assert row["high_to_close_fade"] == pytest.approx((101.0 - 100.5) / 101.0)
    summary = result["summary"].set_index("group").loc["top20"]
    assert summary["reached_3pct_not_retained_count"] == 0


def test_forward_high_metrics_use_hfq_scale_when_raw_close_scale_changes():
    bars = pd.DataFrame(
        [
            ["A01", "2026-07-27", 100.0, 1000.0, 1000.0, 1000.0, 1000.0],
            ["A01", "2026-07-28", 110.0, 550.0, 605.0, 545.0, 550.0],
            ["A01", "2026-07-29", 110.0, 550.0, 600.0, 545.0, 550.0],
            ["A01", "2026-07-30", 110.0, 550.0, 600.0, 545.0, 550.0],
        ],
        columns=[
            "asset_id",
            "trade_date",
            "hfq_close",
            "raw_open",
            "raw_high",
            "raw_low",
            "raw_close",
        ],
    )
    bars.attrs["outcome_dates"] = list(OUTCOME_DATES)

    row = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(1),
        qualified_pool=_qualified_pool_snapshot(1),
        daily_bars=bars,
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )["detail"].iloc[0]

    assert row["max_high_return"] == pytest.approx(0.21)


def test_missing_daily_outcome_bar_marks_incomplete_without_dropping_member():
    bars = _daily_bars(3)
    bars = bars.loc[
        ~(
            bars["asset_id"].eq("A02")
            & bars["trade_date"].eq("2026-07-30")
        )
    ]

    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(3),
        qualified_pool=_qualified_pool_snapshot(3),
        daily_bars=bars,
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    detail = result["detail"].set_index("asset_id")
    assert detail.loc["A02", "evaluation_status"] == "missing_outcome_bar"
    assert result["coverage"]["daily_complete"] is False
    assert result["coverage"]["evaluation_status"] == "daily_incomplete"
    top20 = result["summary"].set_index("group").loc["top20"]
    assert top20["member_count"] == 3
    assert top20["completed_count"] == 2


def test_missing_qualified_pool_member_invalidates_excess_benchmark_and_coverage():
    snapshot = _ranked_snapshot(1)
    qualified = _qualified_pool_snapshot(2)
    bars = _daily_bars(1)

    result = evaluate_v2_snapshot(
        snapshot=snapshot,
        qualified_pool=qualified,
        daily_bars=bars,
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    assert result["detail"]["evaluation_status"].eq("completed").all()
    assert result["coverage"]["selected_daily_complete"] is True
    assert result["coverage"]["qualified_pool_daily_complete"] is False
    assert result["coverage"]["daily_complete"] is False
    assert result["coverage"]["evaluation_status"] == "daily_incomplete"
    assert "qualified_pool_daily_incomplete" in result["coverage"]["warnings"]
    assert result["coverage"]["qualified_pool_daily_expected_rows"] == 2
    assert result["coverage"]["qualified_pool_daily_completed_rows"] == 1
    top20 = result["summary"].set_index("group").loc["top20"]
    assert top20["qualified_pool_benchmark_status"] == "incomplete"
    assert top20["qualified_pool_member_count"] == 2
    assert top20["qualified_pool_completed_count"] == 1
    assert pd.isna(top20["qualified_pool_mean_return"])
    assert pd.isna(top20["qualified_pool_excess_return"])


def test_minute_diagnostics_degrade_without_blocking_daily_evaluation():
    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(3),
        qualified_pool=_qualified_pool_snapshot(3),
        daily_bars=_daily_bars(3),
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    assert result["coverage"]["daily_complete"] is True
    assert result["coverage"]["minute_complete"] is False
    assert result["coverage"]["evaluation_status"] == "daily_complete_minute_degraded"
    assert result["minute_detail"].empty


def test_complete_forty_eight_bar_days_publish_intraday_diagnostics():
    snapshot = _ranked_snapshot(2)
    minute = _minute_bars(snapshot["asset_id"].tolist(), ("2026-07-30",))

    result = evaluate_v2_snapshot(
        snapshot=snapshot,
        qualified_pool=_qualified_pool_snapshot(2),
        daily_bars=_daily_bars(2),
        minute_bars=minute,
        horizons=(3,),
    )

    assert result["coverage"]["minute_complete"] is True
    assert result["coverage"]["evaluation_status"] == "complete"
    detail = result["minute_detail"]
    assert len(detail) == 2
    assert detail["bar_count"].eq(48).all()
    assert detail["first_high_time"].str.endswith("10:35:00").all()
    assert detail["above_entry_bar_ratio"].between(0.0, 1.0).all()
    assert detail["morning_retention"].between(0.0, 1.0).all()
    assert detail["afternoon_retention"].between(0.0, 1.0).all()
    assert detail["limit_up_reached"].all()
    assert detail["limit_up_held_to_close"].all()
    assert detail["first_limit_up_time"].str.endswith("10:35:00").all()


def test_forty_seven_minute_bars_degrade_while_daily_evaluation_stays_complete():
    minute = _minute_bars(["A01"], ("2026-07-30",)).iloc[:-1]

    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(1),
        qualified_pool=_qualified_pool_snapshot(1),
        daily_bars=_daily_bars(1),
        minute_bars=minute,
        horizons=(3,),
    )

    assert result["coverage"]["daily_complete"] is True
    assert result["coverage"]["minute_complete"] is False
    assert result["coverage"]["evaluation_status"] == "daily_complete_minute_degraded"


def test_fake_midnight_or_missing_limit_price_minute_bars_degrade():
    minute = _minute_bars(["A01"], ("2026-07-30",))
    minute.loc[minute.index[0], "trade_time"] = "2026-07-30 00:00:00"
    minute.loc[minute.index[1], "limit_up_price"] = np.nan

    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(1),
        qualified_pool=_qualified_pool_snapshot(1),
        daily_bars=_daily_bars(1),
        minute_bars=minute,
        horizons=(3,),
    )

    assert result["coverage"]["minute_complete"] is False
    assert result["coverage"]["evaluation_status"] == "daily_complete_minute_degraded"


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (
            lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True),
            "unique asset_id",
        ),
        (
            lambda frame: frame.assign(final_rank=[1, 3, *range(3, len(frame) + 1)]),
            "consecutive positive final_rank",
        ),
    ],
)
def test_malformed_snapshot_is_rejected(mutator, match):
    with pytest.raises(ValueError, match=match):
        evaluate_v2_snapshot(
            snapshot=mutator(_ranked_snapshot(3)),
            qualified_pool=_qualified_pool_snapshot(3),
            daily_bars=_daily_bars(3),
            minute_bars=pd.DataFrame(),
            horizons=(3,),
        )


def test_boolean_snapshot_rank_is_rejected():
    snapshot = _ranked_snapshot(1).assign(final_rank=True)
    with pytest.raises(ValueError, match="consecutive positive final_rank"):
        evaluate_v2_snapshot(
            snapshot=snapshot,
            qualified_pool=_qualified_pool_snapshot(1),
            daily_bars=_daily_bars(1),
            minute_bars=pd.DataFrame(),
            horizons=(3,),
        )


def test_snapshot_asset_outside_qualified_pool_is_rejected():
    qualified = _qualified_pool_snapshot(3).iloc[:2]
    with pytest.raises(ValueError, match="snapshot assets must be present"):
        evaluate_v2_snapshot(
            snapshot=_ranked_snapshot(3),
            qualified_pool=qualified,
            daily_bars=_daily_bars(3),
            minute_bars=pd.DataFrame(),
            horizons=(3,),
        )


def test_duplicate_qualified_pool_assets_are_rejected():
    qualified = pd.concat(
        [_qualified_pool_snapshot(3), _qualified_pool_snapshot(3).iloc[[0]]],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="qualified_pool must contain unique asset_id"):
        evaluate_v2_snapshot(
            snapshot=_ranked_snapshot(3),
            qualified_pool=qualified,
            daily_bars=_daily_bars(3),
            minute_bars=pd.DataFrame(),
            horizons=(3,),
        )


def test_evaluation_is_immutable_and_deterministic_under_input_shuffle():
    snapshot = _ranked_snapshot(8)
    qualified = _qualified_pool_snapshot(10)
    bars = _daily_bars(10)
    minute = _minute_bars(snapshot["asset_id"].tolist(), ("2026-07-30",))
    originals = tuple(frame.copy(deep=True) for frame in (snapshot, qualified, bars, minute))

    first = evaluate_v2_snapshot(
        snapshot=snapshot,
        qualified_pool=qualified,
        daily_bars=bars,
        minute_bars=minute,
        horizons=(3,),
    )
    second = evaluate_v2_snapshot(
        snapshot=snapshot.sample(frac=1.0, random_state=1),
        qualified_pool=qualified.sample(frac=1.0, random_state=2),
        daily_bars=bars.sample(frac=1.0, random_state=3),
        minute_bars=minute.sample(frac=1.0, random_state=4),
        horizons=(3,),
    )

    pdt.assert_frame_equal(first["detail"], second["detail"])
    pdt.assert_frame_equal(first["summary"], second["summary"])
    pdt.assert_frame_equal(first["minute_detail"], second["minute_detail"])
    for frame, original in zip((snapshot, qualified, bars, minute), originals, strict=True):
        pdt.assert_frame_equal(frame, original)


def test_evaluator_has_no_stock_name_or_code_specific_branches():
    source = Path(
        "src/stock_research/consumer_oversold/v2_evaluation.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("北汽蓝谷", "赛力斯", "舍得酒业", "江淮汽车", "600733", "601127"):
        assert forbidden not in source


def test_ranking_pipeline_never_imports_the_minute_outcome_loader():
    source = Path("src/stock_research/consumer_oversold/pipeline.py").read_text(
        encoding="utf-8"
    )
    assert "load_consumer_v2_minute_outcome_bars" not in source


def _install_db(monkeypatch, responses):
    calls: list[tuple[str, list[object]]] = []
    iterator = iter(responses)

    @contextmanager
    def fake_connect(service):
        yield object()

    def fake_fetch_all(conn, sql, params=None):
        calls.append((" ".join(sql.split()), list(params or [])))
        return next(iterator)

    monkeypatch.setattr(loaders, "connect", fake_connect)
    monkeypatch.setattr(loaders, "fetch_all", fake_fetch_all)
    return calls


def test_outcome_loaders_use_explicit_date_predicates_and_stable_schemas(monkeypatch):
    calls = _install_db(
        monkeypatch,
        [
            [
                {"asset_id": "A", "trade_date": date(2026, 7, 27), "hfq_close": 10.0},
                {"asset_id": "A", "trade_date": date(2026, 8, 1), "hfq_close": 999.0},
                {"asset_id": "B", "trade_date": date(2026, 7, 28), "hfq_close": 777.0},
            ],
            [
                {
                    "asset_id": "A",
                    "trade_date": date(2026, 7, 30),
                    "raw_open": 10.0,
                    "raw_high": 11.0,
                    "raw_low": 9.0,
                    "raw_close": 10.5,
                }
            ],
            [
                {
                    "asset_id": "A",
                    "trade_date": date(2026, 7, 30),
                    "trade_time": "2026-07-30 09:35:00",
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.9,
                    "close": 10.2,
                    "limit_up_price": 11.0,
                }
            ],
        ],
    )

    hfq = loaders.load_consumer_v2_hfq_daily_closes(
        ["A"], "2026-07-27", "2026-07-30", service="test"
    )
    raw = loaders.load_consumer_v2_raw_daily_bars(
        ["A"], "2026-07-27", "2026-07-30", service="test"
    )
    minute = loaders.load_consumer_v2_minute_outcome_bars(
        ["A"], "2026-07-28", "2026-07-30", service="test"
    )

    assert hfq["trade_date"].tolist() == ["2026-07-27"]
    assert raw.columns.tolist() == [
        "asset_id",
        "trade_date",
        "raw_open",
        "raw_high",
        "raw_low",
        "raw_close",
    ]
    assert minute.columns.tolist() == [
        "asset_id",
        "trade_date",
        "trade_time",
        "open",
        "high",
        "low",
        "close",
        "limit_up_price",
    ]
    for sql, params in calls:
        assert "BETWEEN %s AND %s" in sql
        assert params[1:3] == ["2026-07-27", "2026-07-30"] or params[1:3] == [
            "2026-07-28",
            "2026-07-30",
        ]
    assert "adjust_type = 'hfq'" in calls[0][0]
    assert "adjust_type = 'raw'" in calls[1][0]
    assert "FROM market.stock_minute_bar" in calls[2][0]
    assert "freq = '5min'" in calls[2][0]
    assert "adjust_type = 'raw'" in calls[2][0]
    assert "AS limit_up_price" in calls[2][0]
    assert "LEFT JOIN LATERAL" in calls[2][0]


def test_outcome_calendar_loader_returns_authoritative_open_dates(monkeypatch):
    calls = _install_db(
        monkeypatch,
        [[
            {"trade_date": date(2026, 7, 28)},
            {"trade_date": date(2026, 7, 29)},
            {"trade_date": date(2026, 7, 30)},
        ]],
    )

    dates = loaders.load_consumer_v2_outcome_calendar(
        "2026-07-28", "2026-07-30", service="test"
    )

    assert dates == ["2026-07-28", "2026-07-29", "2026-07-30"]
    sql, params = calls[0]
    assert "FROM market.trading_calendar" in sql
    assert "is_open = TRUE" in sql
    assert "trade_date BETWEEN %s AND %s" in sql
    assert params == ["2026-07-28", "2026-07-30"]


@pytest.mark.parametrize(
    "loader",
    [
        loaders.load_consumer_v2_hfq_daily_closes,
        loaders.load_consumer_v2_raw_daily_bars,
        loaders.load_consumer_v2_minute_outcome_bars,
    ],
)
def test_outcome_loaders_reject_reversed_date_range(loader):
    with pytest.raises(ValueError, match="start_date must be on or before end_date"):
        loader(["A"], "2026-07-30", "2026-07-27", service="test")
