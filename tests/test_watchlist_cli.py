import pandas as pd

import stock_research.cli as cli
from stock_research.cli import build_parser


def test_cli_accepts_watchlist_commands():
    build_args = build_parser().parse_args(
        [
            "watchlist-build",
            "--trade-date",
            "2026-05-20",
            "--watchlist-id",
            "core",
            "--score-version",
            "custom_v2",
            "--top-n",
            "17",
            "--output-dir",
            "outputs/watchlist",
        ]
    )
    report_args = build_parser().parse_args(
        ["watchlist-report", "--trade-date", "2026-05-20", "--watchlist-id", "core", "--output-dir", "outputs/watchlist"]
    )
    explain_args = build_parser().parse_args(
        ["watchlist-explain", "--trade-date", "2026-05-20", "--watchlist-id", "core", "--asset-id", "CN:SH:600000"]
    )

    assert build_args.command == "watchlist-build"
    assert build_args.score_version == "custom_v2"
    assert build_args.top_n == 17
    assert report_args.command == "watchlist-report"
    assert explain_args.command == "watchlist-explain"


def test_watchlist_build_cli_prints_summary_and_run_card(monkeypatch, capsys):
    calls = {}
    build_frame = pd.DataFrame(
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
    )

    def fake_build_watchlist_snapshot(**kwargs):
        calls["build"] = kwargs
        return build_frame

    def fake_write_watchlist_report(*args, **kwargs):
        calls["report"] = kwargs
        return {
            "markdown_path": "/tmp/watchlist.md",
            "json_path": "/tmp/watchlist.json",
            "signals_csv_path": "/tmp/signals.csv",
            "must_watch_csv_path": "/tmp/must_watch.csv",
        }

    def fake_write_run_card(**kwargs):
        calls["run_card"] = kwargs
        return {"run_card_json_path": "/tmp/run_card.json"}

    monkeypatch.setattr(
        "stock_research.cli.build_watchlist_snapshot",
        fake_build_watchlist_snapshot,
    )
    monkeypatch.setattr(
        "stock_research.cli.write_watchlist_report",
        fake_write_watchlist_report,
    )
    monkeypatch.setattr("stock_research.cli.write_run_card", fake_write_run_card)

    cli.main_for_args(
        [
            "watchlist-build",
            "--trade-date",
            "2026-05-20",
            "--watchlist-id",
            "core",
            "--score-version",
            "custom_v2",
            "--top-n",
            "17",
            "--output-dir",
            "/tmp/watchlist",
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert "watchlist_build|watchlist_id|core" in lines
    assert "watchlist_build|members|2" in lines
    assert "watchlist_build|must_watch|1" in lines
    assert "watchlist_build|report|/tmp/watchlist.md" in lines
    assert "watchlist_build|run_card|/tmp/run_card.json" in lines
    assert calls["build"]["score_version"] == "custom_v2"
    assert calls["build"]["top_n"] == 17
    assert calls["run_card"]["config"]["score_version"] == "custom_v2"
    assert calls["run_card"]["config"]["top_n"] == 17
    assert calls["report"]["output_dir"] == "/tmp/watchlist"


def test_watchlist_report_cli_loads_persisted_rows_and_writes_report(monkeypatch):
    calls = {}

    def fake_load_watchlist_daily_signals(watchlist_id, trade_date):
        calls["load"] = (watchlist_id, trade_date)
        return pd.DataFrame([{"watchlist_id": watchlist_id, "trade_date": trade_date, "must_watch": True}])

    def fake_write_watchlist_report(rows, output_dir):
        calls["write"] = (rows.copy(), output_dir)
        return {
            "markdown_path": "/tmp/watchlist.md",
            "json_path": "/tmp/watchlist.json",
            "signals_csv_path": "/tmp/signals.csv",
            "must_watch_csv_path": "/tmp/must_watch.csv",
        }

    monkeypatch.setattr(
        "stock_research.cli.load_watchlist_daily_signals",
        fake_load_watchlist_daily_signals,
    )
    monkeypatch.setattr(
        "stock_research.cli.write_watchlist_report",
        fake_write_watchlist_report,
    )
    monkeypatch.setattr(
        "stock_research.cli.build_watchlist_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not build")),
    )

    cli.main_for_args(
        [
            "watchlist-report",
            "--trade-date",
            "2026-05-20",
            "--watchlist-id",
            "core",
            "--output-dir",
            "/tmp/watchlist",
        ]
    )

    assert calls["load"] == ("core", "2026-05-20")
    assert calls["write"][1] == "/tmp/watchlist"
    assert list(calls["write"][0]["must_watch"]) == [True]


def test_watchlist_explain_cli_delegates_to_workflow(monkeypatch, capsys):
    calls = {}

    def fake_explain_watchlist_asset(**kwargs):
        calls["explain"] = kwargs
        return {"asset_id": kwargs["asset_id"], "trade_date": kwargs["trade_date"], "watchlist_id": kwargs["watchlist_id"]}

    monkeypatch.setattr(
        "stock_research.cli.explain_watchlist_asset",
        fake_explain_watchlist_asset,
    )

    cli.main_for_args(
        [
            "watchlist-explain",
            "--trade-date",
            "2026-05-20",
            "--watchlist-id",
            "core",
            "--asset-id",
            "CN:SH:600000",
        ]
    )

    assert calls["explain"] == {
        "trade_date": "2026-05-20",
        "watchlist_id": "core",
        "asset_id": "CN:SH:600000",
    }
    assert (
        capsys.readouterr().out.strip()
        == '{"asset_id": "CN:SH:600000", "trade_date": "2026-05-20", "watchlist_id": "core"}'
    )
