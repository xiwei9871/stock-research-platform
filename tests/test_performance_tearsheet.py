import pandas as pd

from stock_research.performance_tearsheet import write_performance_tearsheet
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    VectorizedTopNResult,
)


def test_write_performance_tearsheet_writes_markdown_and_csv_outputs(tmp_path):
    equity_curve = pd.DataFrame(
        [
            {
                "date": "2026-01-02",
                "net_return": 0.10,
                "equity": 1.10,
                "drawdown": 0.0,
                "turnover": 1.0,
            },
            {
                "date": "2026-01-03",
                "net_return": -0.05,
                "equity": 1.045,
                "drawdown": -0.05,
                "turnover": 0.5,
            },
        ]
    )
    positions = pd.DataFrame(
        [
            {
                "rebalance_date": "2026-01-01",
                "asset_id": "A",
                "rank": 1,
                "score_total": 90.0,
                "weight": 0.5,
            }
        ]
    )
    trades = pd.DataFrame(
        [
            {
                "rebalance_date": "2026-01-01",
                "asset_id": "A",
                "side": "buy",
                "previous_weight": 0.0,
                "target_weight": 0.5,
                "delta_weight": 0.5,
                "turnover_contribution": 0.5,
                "transaction_cost": 0.0005,
            }
        ]
    )
    result = VectorizedTopNResult(
        config=VectorizedTopNConfig(
            start_date="2026-01-01",
            end_date="2026-01-03",
            top_n=2,
            rebalance_frequency="daily",
        ),
        equity_curve=equity_curve,
        positions=positions,
        trades=trades,
        summary={"total_return": 0.045, "periods": 2},
    )

    paths = write_performance_tearsheet(
        result,
        strategy_id="topn-test",
        reports_dir=tmp_path,
    )

    assert set(paths) == {
        "report_path",
        "metrics_path",
        "equity_curve_path",
        "positions_path",
        "trades_path",
    }
    report_text = (tmp_path / "topn-test_2026-01-01_2026-01-03_tearsheet.md").read_text(
        encoding="utf-8"
    )
    assert "# Performance Tear Sheet" in report_text
    assert "仅作为研究验证，不构成交易指令。" in report_text
    assert "| cumulative_return |" in report_text
    assert "topn-test" in report_text

    metrics = pd.read_csv(paths["metrics_path"])
    assert "cumulative_return" in set(metrics["metric"])
    assert "sharpe_ratio" in set(metrics["metric"])
    assert pd.read_csv(paths["equity_curve_path"]).shape[0] == 2
    assert pd.read_csv(paths["positions_path"]).shape[0] == 1
    assert pd.read_csv(paths["trades_path"]).shape[0] == 1
