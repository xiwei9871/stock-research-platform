import pytest

from stock_research import cli


def test_cli_accepts_run_strategy_daily_eod_command():
    args = cli.build_parser().parse_args(["run-strategy-daily-eod", "--trade-date", "2026-06-24"])
    assert args.command == "run-strategy-daily-eod"
    assert args.trade_date == "2026-06-24"


def test_cli_run_strategy_daily_eod_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_strategy_daily_eod",
        lambda **_kwargs: {
            "status": "success",
            "trade_date": "2026-06-24",
            "output_dir": "/tmp/out",
            "review_rows": 15,
            "summary_path": "/tmp/out/strategy_eod_publish_summary.json",
            "dependency_reason": None,
            "dependency_check": {
                "common": {"status": "success"},
                "intraday": {"status": "success"},
            },
            "strategy_status": {
                "lhb_shortline": "success",
                "mid_trend": "success",
                "midtrend_artifacts": "success",
                "tech_bottleneck": "success",
            },
        },
    )

    rc = cli.main(["run-strategy-daily-eod", "--trade-date", "2026-06-24"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "strategy_daily_eod|status|success" in out
    assert "strategy_daily_eod|lhb_shortline_status|success" in out
    assert "strategy_daily_eod|mid_trend_status|success" in out
    assert "strategy_daily_eod|strategy_midtrend_artifacts_status|success" in out
    assert "strategy_daily_eod|tech_bottleneck_status|success" in out
    assert "strategy_daily_eod|dependency_common_status|success" in out
    assert "strategy_daily_eod|dependency_intraday_status|success" in out


@pytest.mark.parametrize(
    ("status", "expected_rc"),
    [("success", 0), ("partial", 1), ("failed", 1)],
)
def test_cli_run_strategy_daily_eod_returns_business_status_exit_code(
    monkeypatch, status, expected_rc
):
    monkeypatch.setattr(
        cli,
        "run_strategy_daily_eod",
        lambda **_kwargs: {
            "status": status,
            "trade_date": "2026-06-24",
            "output_dir": "/tmp/out",
            "review_rows": 0,
            "summary_path": "/tmp/out/summary.json",
            "dependency_reason": "dependency failed" if status != "success" else None,
            "dependency_check": {
                "common": {"status": "success"},
                "intraday": {"status": "failed" if status != "success" else "success"},
            },
            "strategy_status": {
                "lhb_shortline": "blocked" if status != "success" else "success",
                "mid_trend": "success",
                "midtrend_artifacts": "success",
                "tech_bottleneck": "success",
            },
        },
    )

    assert cli.main(["run-strategy-daily-eod", "--trade-date", "2026-06-24"]) == expected_rc
