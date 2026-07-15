from pathlib import Path

import pandas as pd
import pytest

from stock_research import lhb_ranking_calibration


def _calibration_frame(*, date_count: int = 30, candidates_per_date: int = 10) -> pd.DataFrame:
    rows = []
    dates = pd.bdate_range("2026-01-05", periods=date_count)
    for date_index, trade_date in enumerate(dates):
        for rank in range(1, candidates_per_date + 1):
            quality = candidates_per_date - rank + 1
            rows.append(
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "ts_code": f"{date_index:03d}{rank:03d}.SZ",
                    "backtest_entry_eligible": True,
                    "eligibility_contract_version": "lhb_eligibility_v2",
                    "selection_score": float(quality),
                    "lhb_net_buy_amount": float(quality * 1_000_000),
                    "lhb_net_buy_ratio": quality / 100.0,
                    "institution_net_buy": float(quality * 100_000),
                    "top_seat_concentration": rank / 20.0,
                    "repeat_on_list_count_3d": rank % 3,
                    "lhb_after_limit_up": rank <= 2,
                    "lhb_after_break_limit": rank >= 9,
                    "lhb_after_reversal": False,
                    "lhb_one_day_pump_risk": rank / 20.0,
                    "high_to_close_drawdown": rank / 100.0,
                    "future_1d_return": 0.01 if rank <= 5 else -0.005,
                    "future_5d_return": quality / 100.0,
                    "future_5d_max_drawdown": -rank / 100.0,
                }
            )
    return pd.DataFrame(rows)


def test_calibration_rejects_future_or_execution_features():
    with pytest.raises(ValueError, match="future/outcome feature"):
        lhb_ranking_calibration.validate_lhb_calibration_features(
            ["lhb_net_buy_ratio", "future_5d_return"]
        )
    with pytest.raises(ValueError, match="future/outcome feature"):
        lhb_ranking_calibration.validate_lhb_calibration_features(
            ["lhb_net_buy_ratio", "entry_price"]
        )


def test_calibration_split_is_chronological_and_non_overlapping():
    split = lhb_ranking_calibration.chronological_lhb_calibration_split(
        _calibration_frame(),
        holdout_fraction=0.20,
        min_holdout_dates=5,
        fold_count=3,
    )

    assert split["preholdout_dates"][-1] < split["holdout_dates"][0]
    for train_dates, validation_dates in split["folds"]:
        assert train_dates[-1] < validation_dates[0]
        assert not set(train_dates).intersection(validation_dates)
    assert not set(split["preholdout_dates"]).intersection(split["holdout_dates"])


def test_failed_holdout_gate_prevents_promotion():
    gates = lhb_ranking_calibration.evaluate_lhb_holdout_gates(
        baseline={"mean_future_5d_return": 0.03, "up_rate_1d": 0.60, "mean_future_5d_max_drawdown": -0.04},
        candidate={"mean_future_5d_return": 0.04, "up_rate_1d": 0.57, "mean_future_5d_max_drawdown": -0.04},
        candidate_rank6_10={"mean_future_5d_return": 0.02, "up_rate_1d": 0.55},
        monthly_excess_concentration=0.30,
    )

    assert gates["up_rate_gate"] is False
    assert gates["promote"] is False


def test_calibration_outputs_shadow_scores_on_identical_eligible_universe(tmp_path):
    frame = _calibration_frame()

    result = lhb_ranking_calibration.build_lhb_ranking_calibration_v2(
        eligible_candidates=frame,
        output_dir=tmp_path,
        holdout_fraction=0.20,
        min_holdout_dates=5,
    )

    shadow = result["shadow_scores"]
    assert len(shadow) == len(frame)
    assert set(zip(shadow["trade_date"], shadow["ts_code"])) == set(
        zip(frame["trade_date"], frame["ts_code"])
    )
    assert shadow["score_version"].eq("lhb_selection_score_v2").all()
    assert Path(result["paths"]["shadow_scores"]).exists()
    assert Path(result["paths"]["holdout_report"]).exists()


def test_calibration_refuses_zero_holdout_outcome_coverage(tmp_path):
    frame = _calibration_frame()
    frame[["future_1d_return", "future_5d_return", "future_5d_max_drawdown"]] = pd.NA

    with pytest.raises(ValueError, match="holdout outcome coverage"):
        lhb_ranking_calibration.build_lhb_ranking_calibration_v2(
            eligible_candidates=frame,
            output_dir=tmp_path,
            holdout_fraction=0.20,
            min_holdout_dates=5,
        )
