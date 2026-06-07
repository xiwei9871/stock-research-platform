from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.watchlist.fundamental_pit_context import (
    build_watchlist_fundamental_pit_context_from_detail,
)


def test_build_watchlist_fundamental_pit_context_uses_each_trade_date(monkeypatch):
    calls = []

    def fake_snapshot(bars, trade_date, service=None):
        calls.append((trade_date, bars["asset_id"].tolist()))
        return pd.DataFrame(
            [
                {
                    "asset_id": asset_id,
                    "roe": 0.10 if trade_date == "2026-01-01" else 0.20,
                    "debt_ratio": 0.40,
                    "gross_margin": 0.30,
                    "net_margin": 0.08,
                    "ocf_to_np": 1.0,
                    "np_parent_ttm": 100,
                    "revenue_ttm": 1000,
                }
                for asset_id in bars["asset_id"]
            ]
        )

    monkeypatch.setattr(
        "stock_research.watchlist.fundamental_pit_context.load_point_in_time_fundamentals_snapshot",
        fake_snapshot,
    )

    detail = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A"},
            {"trade_date": "2026-01-02", "asset_id": "A"},
        ]
    )

    result = build_watchlist_fundamental_pit_context_from_detail(detail)

    context = result["context"].set_index("trade_date")
    assert context.loc["2026-01-01", "roe"] == 0.10
    assert context.loc["2026-01-02", "roe"] == 0.20
    assert calls == [("2026-01-01", ["A"]), ("2026-01-02", ["A"])]


def test_build_watchlist_fundamental_pit_context_writes_outputs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "stock_research.watchlist.fundamental_pit_context.load_point_in_time_fundamentals_snapshot",
        lambda bars, trade_date, service=None: pd.DataFrame(
            [{"asset_id": "A", "roe": 0.12, "debt_ratio": 0.5}]
        ),
    )

    result = build_watchlist_fundamental_pit_context_from_detail(
        pd.DataFrame([{"trade_date": "2026-01-01", "asset_id": "A"}]),
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["context"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_pit_fundamental_context(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "context": pd.DataFrame([{"asset_id": "A"}]),
            "paths": {
                "context": str(tmp_path / "context.csv"),
                "summary": str(tmp_path / "summary.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_watchlist_fundamental_pit_context_build", fake_run)

    cli.main_for_args(
        [
            "build-watchlist-fundamental-pit-context",
            "--detail-path",
            "outputs/research/watchlist_diagnostics_effectiveness_detail.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["detail_path"] == "outputs/research/watchlist_diagnostics_effectiveness_detail.csv"
    out = capsys.readouterr().out
    assert "watchlist_fundamental_pit_context|context|" in out
    assert "watchlist_fundamental_pit_context|rows|1" in out
