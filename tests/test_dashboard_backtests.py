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
