import pandas as pd
from types import SimpleNamespace

from stock_research.dashboard import backtests


def test_latest_eod_strategy_module_uses_recent_manifest_by_module(monkeypatch):
    monkeypatch.setattr(
        backtests,
        "load_recent_data_run_manifest",
        lambda: [
            {"module": "generated_reports", "latest_trade_date": "2026-07-02", "status": "success"},
            {"module": "strategy_lhb_shortline", "latest_trade_date": "2026-06-05", "status": "success"},
            {"module": "strategy_lhb_shortline", "latest_trade_date": "2026-07-02", "status": "success"},
        ],
        raising=False,
    )

    module = backtests._latest_eod_strategy_module("lhb_shortline")

    assert module["latest_trade_date"] == "2026-07-02"


def test_lhb_stale_performance_does_not_publish_latest_day_zero_return(monkeypatch):
    monkeypatch.setattr(backtests, "_read_eod_strategy_rows", lambda module, latest_trade_date, strategy_id: [])
    monkeypatch.setattr(backtests, "_validate_eod_summary_contract", lambda strategy_id, summary: ("success", "ok"))
    monkeypatch.setattr(backtests, "_metrics_from_eod_equity_path", lambda module, strategy: {})
    monkeypatch.setattr(
        backtests,
        "_latest_eod_strategy_module",
        lambda strategy_id: {
            "module": "strategy_lhb_shortline",
            "status": "success",
            "row_count": 4,
            "latest_trade_date": "2026-06-29",
            "metadata": {
                "summary": {
                    "total_return": 1.6241,
                    "max_drawdown": -0.0842,
                    "latest_day_return": 0.0,
                    "latest_period_return": 0.0,
                    "latest_period_label": "最近交易日",
                    "performance_effective_date": "2026-06-26",
                }
            },
        },
    )

    strategy = backtests._with_latest_eod_strategy_metrics(
        {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline",
            "latest_metrics": {},
        }
    )

    metrics = strategy["latest_metrics"]
    assert metrics["as_of_date"] == "2026-06-26"
    assert metrics["signal_as_of_date"] == "2026-06-29"
    assert metrics["performance_status"] == "stale"
    assert "latest_day_return_pct" not in metrics
    assert "latest_period_return_pct" not in metrics
    assert metrics["latest_period_label"] == "收益估值截止 2026-06-26"


def test_eod_equity_path_relocates_synced_local_output_root(monkeypatch, tmp_path):
    output_root = tmp_path / "outputs"
    equity_path = (
        output_root
        / "research"
        / "strategy_daily_eod"
        / "2026-07-03"
        / "strategy_tech_bottleneck_equity.csv"
    )
    equity_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {"trade_date": "2026-07-02", "equity": 1.10, "drawdown": -0.02, "daily_return": 0.01},
            {"trade_date": "2026-07-03", "equity": 1.21, "drawdown": -0.01, "daily_return": 0.10},
        ]
    ).to_csv(equity_path, index=False)
    monkeypatch.setattr(backtests, "SETTINGS", SimpleNamespace(output_root=output_root), raising=False)

    metrics = backtests._metrics_from_eod_equity_path(
        {
            "metadata": {
                "output_paths": {
                    "equity_path": "/mnt/internal/stock_research/outputs/research/strategy_daily_eod/2026-07-03/strategy_tech_bottleneck_equity.csv"
                }
            }
        },
        {"strategy_id": "tech_bottleneck", "default_parameters": {"rebalance_frequency": "daily"}},
    )

    assert metrics["latest_day_return_pct"] == 10.0


def test_eod_summary_exposes_lhb_strategy_version_and_selection_policy():
    metrics = backtests._metrics_from_eod_summary(
        {
            "total_return": 1.23,
            "strategy_version": "lhb_v1_stable_safe_top5",
            "selection_policy": "phase18c_top5_then_eligibility_no_refill",
            "market_regime_policy": "disabled_for_stable_strategy",
            "cash_slot_count": 9,
        }
    )

    assert metrics["strategy_version"] == "lhb_v1_stable_safe_top5"
    assert metrics["selection_policy"] == "phase18c_top5_then_eligibility_no_refill"
    assert metrics["market_regime_policy"] == "disabled_for_stable_strategy"
    assert metrics["cash_slot_count"] == 9
