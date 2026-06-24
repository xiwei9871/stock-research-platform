import stock_research.cli as cli


def test_cli_run_baostock_minute_daily_prints_summary(monkeypatch, capsys):
    calls = []

    def fake_runner(**kwargs):
        calls.append(kwargs)
        return {
            "status": "partial",
            "trade_date": "2026-06-23",
            "symbol_count": 3,
            "success_count": 2,
            "empty_count": 0,
            "failed_count": 1,
            "retry_count": 4,
            "relogin_count": 1,
            "rows_written": 240,
            "failed_symbols": ["sh.600000", "sz.000001"],
            "last_error": "timeout",
        }

    monkeypatch.setattr(cli, "run_baostock_minute_daily", fake_runner)

    rc = cli.main(
        [
            "run-baostock-minute-daily",
            "--trade-date",
            "2026-06-23",
            "--sleep-seconds",
            "1.5",
            "--retry-limit",
            "4",
            "--cooldown-seconds",
            "300",
            "--timeout-seconds",
            "30",
            "--output-dir",
            "outputs/custom",
            "--limit-assets",
            "20",
        ]
    )

    assert rc == 0
    assert calls == [
        {
            "trade_date": "2026-06-23",
            "sleep_seconds": 1.5,
            "retry_limit": 4,
            "cooldown_seconds": 300,
            "timeout_seconds": 30.0,
            "output_dir": "outputs/custom",
            "limit_assets": 20,
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        "minute_daily|status|partial",
        "minute_daily|trade_date|2026-06-23",
        "minute_daily|symbol_count|3",
        "minute_daily|success_count|2",
        "minute_daily|empty_count|0",
        "minute_daily|failed_count|1",
        "minute_daily|retry_count|4",
        "minute_daily|relogin_count|1",
        "minute_daily|rows_written|240",
        "minute_daily|failed_symbols|sh.600000,sz.000001",
        "minute_daily|last_error|timeout",
    ]
