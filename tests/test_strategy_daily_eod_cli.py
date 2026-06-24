import sys
import types
from pathlib import Path

sys.modules.setdefault("tushare", types.ModuleType("tushare"))

import stock_research.cli as cli


def _ensure_cli_default_artifacts() -> None:
    output_root = Path(__file__).resolve().parents[1] / "outputs" / "research" / "test_defaults"
    output_root.mkdir(parents=True, exist_ok=True)
    for artifact_name in (
        "market_regime_confirmation_daily.csv",
        "mid_trend_watch_funnel_detail.csv",
        "mid_trend_shadow_top10.csv",
    ):
        path = output_root / artifact_name
        if not path.exists():
            path.write_text("trade_date\n2026-06-24\n")


def test_cli_accepts_run_strategy_daily_eod_command(monkeypatch) -> None:
    _ensure_cli_default_artifacts()
    args = cli.build_parser().parse_args(
        [
            "run-strategy-daily-eod",
            "--trade-date",
            "2026-06-24",
        ]
    )

    assert args.command == "run-strategy-daily-eod"
    assert args.trade_date == "2026-06-24"
    assert args.output_root == "/Users/xiwei/stock_research/outputs/research/strategy_daily_eod"


def test_cli_run_strategy_daily_eod_dispatches_and_prints_summary(monkeypatch, capsys) -> None:
    _ensure_cli_default_artifacts()
    calls = []

    monkeypatch.setattr(
        cli,
        "run_strategy_daily_eod",
        lambda **kwargs: calls.append(kwargs)
        or {
            "trade_date": "2026-06-24",
            "status": "success",
            "review_rows": 11,
            "output_dir": "/tmp/strategy_daily_eod/2026-06-24",
            "summary_path": "/tmp/strategy_daily_eod/2026-06-24/strategy_eod_publish_summary.json",
            "dependency_check": {"status": "success"},
            "strategy_status": {
                "lhb_shortline": {"status": "success"},
                "mid_trend": {"status": "success"},
                "tech_bottleneck": {"status": "success"},
            },
        },
    )

    exit_code = cli.main_for_args(
        [
            "run-strategy-daily-eod",
            "--trade-date",
            "2026-06-24",
            "--output-root",
            "/tmp/strategy_daily_eod",
        ]
    )

    assert exit_code == 0
    assert calls == [
        {
            "trade_date": "2026-06-24",
            "output_root": "/tmp/strategy_daily_eod",
        }
    ]
    assert capsys.readouterr().out.splitlines() == [
        "strategy_daily_eod|trade_date|2026-06-24",
        "strategy_daily_eod|status|success",
        "strategy_daily_eod|review_rows|11",
        "strategy_daily_eod|output_dir|/tmp/strategy_daily_eod/2026-06-24",
        "strategy_daily_eod|summary_path|/tmp/strategy_daily_eod/2026-06-24/strategy_eod_publish_summary.json",
    ]


def test_cli_run_strategy_daily_eod_returns_1_on_failed_status(monkeypatch, capsys) -> None:
    _ensure_cli_default_artifacts()
    monkeypatch.setattr(
        cli,
        "run_strategy_daily_eod",
        lambda **kwargs: {
            "trade_date": "2026-06-24",
            "status": "failed",
            "review_rows": 0,
            "output_dir": "/tmp/strategy_daily_eod/2026-06-24",
            "summary_path": "/tmp/strategy_daily_eod/2026-06-24/strategy_eod_publish_summary.json",
            "reason": "dependency_check_failed",
            "dependency_check": {"status": "failed"},
            "strategy_status": {},
        },
    )

    exit_code = cli.main_for_args(
        [
            "run-strategy-daily-eod",
            "--trade-date",
            "2026-06-24",
        ]
    )

    assert exit_code == 1
    assert capsys.readouterr().out.splitlines() == [
        "strategy_daily_eod|trade_date|2026-06-24",
        "strategy_daily_eod|status|failed",
        "strategy_daily_eod|review_rows|0",
        "strategy_daily_eod|output_dir|/tmp/strategy_daily_eod/2026-06-24",
        "strategy_daily_eod|summary_path|/tmp/strategy_daily_eod/2026-06-24/strategy_eod_publish_summary.json",
        "strategy_daily_eod|reason|dependency_check_failed",
    ]
