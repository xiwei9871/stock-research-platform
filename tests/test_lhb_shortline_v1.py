import pandas as pd
import pytest

from stock_research import lhb_shortline_v1
from stock_research.dashboard.strategy_backtest_adapters import build_lhb_shortline_scores_from_frames


def _candidate_frames(*, high_to_close_drawdown: float, pump_risk: float = 0.20):
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": "000001.SZ",
                "asset_id": "CN:SZ:000001",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.10,
                "lhb_net_buy_amount": 100_000_000.0,
                "institution_net_buy": 20_000_000.0,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": pump_risk,
            }
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": "000001.SZ",
                "asset_id": "CN:SZ:000001",
                "amount_vs_20d": 1.0,
                "high_to_close_drawdown": high_to_close_drawdown,
            }
        ]
    )
    return lhb, technical


def test_candidate_score_penalizes_positive_high_to_close_drawdown():
    base_lhb, base_tech = _candidate_frames(high_to_close_drawdown=0.0)
    faded_lhb, faded_tech = _candidate_frames(high_to_close_drawdown=0.10)

    base = lhb_shortline_v1.build_lhb_shortline_v1_candidates(base_lhb, base_tech, candidate_pool_n=10)
    faded = lhb_shortline_v1.build_lhb_shortline_v1_candidates(faded_lhb, faded_tech, candidate_pool_n=10)

    assert faded.iloc[0]["score_total"] == pytest.approx(base.iloc[0]["score_total"] - 4.0)


def test_pump_warning_band_is_not_rejected_by_candidate_or_dashboard_adapter():
    lhb, technical = _candidate_frames(high_to_close_drawdown=0.02, pump_risk=0.80)

    candidates = lhb_shortline_v1.build_lhb_shortline_v1_candidates(lhb, technical, candidate_pool_n=10)
    dashboard = build_lhb_shortline_scores_from_frames(lhb, technical)

    assert candidates["ts_code"].tolist() == ["000001.SZ"]
    assert dashboard.iloc[0]["eligibility"] is True


def test_cash_account_summary_uses_curve_end_as_performance_effective_date():
    account_trades = pd.DataFrame(
        [
            {
                "account_trade_status": "filled",
                "exit_trade_date": "2026-06-26",
                "realized_return": 0.1,
                "pnl": 0.02,
                "position_notional": 0.2,
            }
        ]
    )
    account_curve = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-26",
                "equity": 1.02,
                "drawdown": 0.0,
                "open_position_count": 0,
            },
            {
                "trade_date": "2026-06-29",
                "equity": 1.02,
                "drawdown": 0.0,
                "open_position_count": 0,
            },
        ]
    )

    summary = lhb_shortline_v1._summarize_lhb_shortline_market_regime_account(
        account_trades=account_trades,
        account_curve=account_curve,
    )

    assert summary["actual_end_date"] == "2026-06-29"
    assert summary["performance_effective_date"] == "2026-06-29"
    assert summary["latest_closed_trade_date"] == "2026-06-26"
