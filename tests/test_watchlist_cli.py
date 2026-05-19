import pandas as pd

import stock_research.cli as cli
from stock_research.cli import build_parser


def test_cli_accepts_watchlist_commands():
    build_args = build_parser().parse_args(
        ["watchlist-build", "--trade-date", "2026-05-20", "--watchlist-id", "core", "--output-dir", "outputs/watchlist"]
    )
    report_args = build_parser().parse_args(
        ["watchlist-report", "--trade-date", "2026-05-20", "--watchlist-id", "core", "--output-dir", "outputs/watchlist"]
    )
    explain_args = build_parser().parse_args(
        ["watchlist-explain", "--trade-date", "2026-05-20", "--watchlist-id", "core", "--asset-id", "CN:SH:600000"]
    )

    assert build_args.command == "watchlist-build"
    assert report_args.command == "watchlist-report"
    assert explain_args.command == "watchlist-explain"


def test_watchlist_build_cli_prints_summary_and_run_card(monkeypatch, capsys):
    monkeypatch.setattr(
        "stock_research.cli.build_watchlist_snapshot",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "watchlist_id": "core",
                    "trade_date": "2026-05-20",
                    "asset_id": "A",
                    "stock_code": "000001.SZ",
                    "stock_name": "A",
                    "priority": 10,
                    "signal_score": 88.0,
                    "primary_signal": "candidate",
                    "signal_tags": ["candidate", "must_watch"],
                    "risk_tags": [],
                    "must_watch": True,
                    "reason_json": {"score_rank": 1},
                    "output_version": "v1",
                },
                {
                    "watchlist_id": "core",
                    "trade_date": "2026-05-20",
                    "asset_id": "B",
                    "stock_code": "000002.SZ",
                    "stock_name": "B",
                    "priority": 20,
                    "signal_score": 55.0,
                    "primary_signal": "breakdown",
                    "signal_tags": ["breakdown"],
                    "risk_tags": ["sector_weakness"],
                    "must_watch": False,
                    "reason_json": {"score_rank": None},
                    "output_version": "v1",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.cli.write_watchlist_report",
        lambda *args, **kwargs: {
            "markdown_path": "/tmp/watchlist.md",
            "json_path": "/tmp/watchlist.json",
            "signals_csv_path": "/tmp/signals.csv",
            "must_watch_csv_path": "/tmp/must_watch.csv",
        },
    )
    monkeypatch.setattr("stock_research.cli.write_run_card", lambda **kwargs: {"run_card_json_path": "/tmp/run_card.json"})

    cli.main_for_args(
        [
            "watchlist-build",
            "--trade-date",
            "2026-05-20",
            "--watchlist-id",
            "core",
            "--output-dir",
            "/tmp/watchlist",
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert "watchlist_build|watchlist_id|core" in lines
    assert "watchlist_build|members|2" in lines
    assert "watchlist_build|must_watch|1" in lines
