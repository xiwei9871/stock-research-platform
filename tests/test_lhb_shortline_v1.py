import pandas as pd

from stock_research import lhb_shortline_v1


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
