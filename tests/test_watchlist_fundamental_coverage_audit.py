from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.watchlist.fundamental_coverage import (
    build_fundamental_coverage_audit_from_frames,
)


def test_fundamental_coverage_audit_identifies_exact_date_gap_and_missing_factor():
    detail = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A"},
            {"trade_date": "2026-01-02", "asset_id": "B"},
        ]
    )
    factor_daily = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "B", "factor_name": "roe", "factor_value": 0.1},
            {"trade_date": "2026-01-02", "asset_id": "B", "factor_name": "debt_ratio", "factor_value": 0.3},
        ]
    )

    result = build_fundamental_coverage_audit_from_frames(
        detail=detail,
        factor_daily=factor_daily,
        required_factors=["roe", "debt_ratio", "np_yoy"],
    )

    metrics = result["summary"].set_index("metric")["value"].to_dict()
    assert metrics["detail_rows"] == 2
    assert metrics["rows_with_any_fundamental"] == 1
    assert metrics["missing_required_factors"] == "np_yoy"
    date_summary = result["date_summary"].set_index("trade_date")
    assert date_summary.loc["2026-01-01", "rows_with_any_fundamental"] == 0
    assert "exact_trade_date_factor_gap" in result["report"]


def test_fundamental_coverage_audit_writes_outputs(tmp_path: Path):
    result = build_fundamental_coverage_audit_from_frames(
        detail=pd.DataFrame([{"trade_date": "2026-01-01", "asset_id": "A"}]),
        factor_daily=pd.DataFrame(),
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["date_summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_fundamental_coverage_audit(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "paths": {
                "summary": str(tmp_path / "summary.csv"),
                "date_summary": str(tmp_path / "dates.csv"),
                "report": str(tmp_path / "report.md"),
            }
        }

    monkeypatch.setattr(cli, "run_watchlist_fundamental_coverage_audit", fake_run)

    cli.main_for_args(
        [
            "audit-watchlist-fundamental-coverage",
            "--detail-path",
            "outputs/research/watchlist_diagnostics_effectiveness_detail.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["detail_path"] == "outputs/research/watchlist_diagnostics_effectiveness_detail.csv"
    out = capsys.readouterr().out
    assert "watchlist_fundamental_coverage|summary|" in out
