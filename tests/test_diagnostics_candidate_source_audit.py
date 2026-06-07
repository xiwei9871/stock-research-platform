from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.diagnostics_candidate_source_audit import build_diagnostics_candidate_source_audit


def _gap_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "winner_id": "W1",
                "winner_type": "double_60d",
                "asset_id": "A",
                "window_start": "2025-01-01",
                "window_end": "2025-01-31",
                "primary_gap_category": "diagnostics_coverage_gap",
                "diagnostics_seen": False,
            },
            {
                "winner_id": "W2",
                "winner_type": "burst_20d",
                "asset_id": "B",
                "window_start": "2025-01-01",
                "window_end": "2025-01-31",
                "primary_gap_category": "diagnostics_coverage_gap",
                "diagnostics_seen": False,
            },
            {
                "winner_id": "W3",
                "winner_type": "stable_trend_60d",
                "asset_id": "C",
                "window_start": "2025-01-01",
                "window_end": "2025-01-31",
                "primary_gap_category": "diagnostics_coverage_gap",
                "diagnostics_seen": False,
            },
        ]
    )


def _v2_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "Z"},
            {"trade_date": "2025-01-03", "asset_id": "Z"},
        ]
    )


def _score_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "rank": 80, "score_total": 55},
            {"trade_date": "2025-01-03", "asset_id": "B", "rank": 20, "score_total": 88},
        ]
    )


def test_candidate_source_audit_classifies_score_entry_reasons(tmp_path: Path):
    result = build_diagnostics_candidate_source_audit(
        gap_detail=_gap_detail(),
        v2_detail=_v2_detail(),
        score_rows=_score_rows(),
        diagnostics_top_n=50,
        output_dir=tmp_path,
    )

    detail = result["detail"].set_index("winner_id")
    assert detail.loc["W1", "source_gap_reason"] == "score_rank_below_diagnostics_topn"
    assert detail.loc["W2", "source_gap_reason"] == "score_available_but_missing_diagnostics"
    assert detail.loc["W3", "source_gap_reason"] == "no_score_in_window"
    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_candidate_source_audit_summarizes_by_winner_type():
    result = build_diagnostics_candidate_source_audit(
        gap_detail=_gap_detail(),
        v2_detail=_v2_detail(),
        score_rows=_score_rows(),
        diagnostics_top_n=50,
    )

    by_type = result["by_type"]
    assert {"winner_type", "source_gap_reason", "winner_count"} <= set(by_type.columns)
    assert "score_available_but_missing_diagnostics" in set(by_type["source_gap_reason"])


def test_cli_dispatches_candidate_source_audit(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "summary": str(tmp_path / "summary.csv"),
                "by_type": str(tmp_path / "by_type.csv"),
                "report": str(tmp_path / "report.md"),
            },
            "warnings": [],
            "detail": pd.DataFrame([{"winner_id": "W1"}]),
        }

    monkeypatch.setattr(cli, "run_diagnostics_candidate_source_audit", fake_run)
    cli.main_for_args(
        [
            "audit-diagnostics-candidate-source",
            "--gap-detail-path",
            "outputs/research/strong_winner_capture_gap_detail.csv",
            "--v2-detail-path",
            "outputs/research/trend_discovery_v2_2_replay_detail.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["gap_detail_path"] == "outputs/research/strong_winner_capture_gap_detail.csv"
    out = capsys.readouterr().out
    assert "diagnostics_candidate_source_audit|detail|" in out
