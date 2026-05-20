import json
from pathlib import Path

from stock_research import daily_pipeline
from stock_research.services.universe_service import (
    UniverseConfig,
    UniverseMember,
    UniverseResult,
)


def _universe_result(
    included: list[tuple[str, str]],
    excluded: list[tuple[str, str]] | None = None,
) -> UniverseResult:
    config = UniverseConfig(as_of_date="2026-05-08")
    members: list[UniverseMember] = []
    for asset_id, stock_code in included:
        members.append(
            UniverseMember(
                trade_date="2026-05-08",
                asset_id=asset_id,
                stock_code=stock_code,
                stock_name=stock_code,
                board="main",
                listed_days=1000,
                is_st=False,
                is_suspended=False,
                avg_turnover_amount=100000000.0,
                avg_volume=10000000.0,
                industry="Bank",
                included=True,
                include_reasons=["board_allowed:main"],
                exclude_reasons=[],
            )
        )
    for asset_id, stock_code in excluded or []:
        members.append(
            UniverseMember(
                trade_date="2026-05-08",
                asset_id=asset_id,
                stock_code=stock_code,
                stock_name=stock_code,
                board="main",
                listed_days=1000,
                is_st=False,
                is_suspended=False,
                avg_turnover_amount=100000000.0,
                avg_volume=10000000.0,
                industry="Bank",
                included=False,
                include_reasons=[],
                exclude_reasons=["manual_exclude"],
            )
        )
    return UniverseResult(
        config=config,
        as_of_date="2026-05-08",
        total_candidates=len(members),
        included_count=sum(1 for member in members if member.included),
        excluded_count=sum(1 for member in members if not member.included),
        members=members,
        included_codes=[member.stock_code for member in members if member.included],
        excluded_codes=[member.stock_code for member in members if not member.included],
        summary_by_reason={"include": {"board_allowed:main": len(included)}, "exclude": {}},
        warnings=[],
    )


def test_run_daily_factor_pipeline_runs_build_score_topn_and_report(monkeypatch):
    build_calls = []
    score_calls = []
    top_score_calls = []
    report_calls = []

    monkeypatch.setattr(
        daily_pipeline,
        "build_and_store_factor_daily",
        lambda **kwargs: build_calls.append(kwargs) or 100,
    )
    monkeypatch.setattr(
        daily_pipeline,
        "score_stored_factor_daily",
        lambda **kwargs: score_calls.append(kwargs) or 20,
    )
    monkeypatch.setattr(
        daily_pipeline,
        "load_top_scores",
        lambda **kwargs: top_score_calls.append(kwargs)
        or [{"trade_date": "2026-05-08", "asset_id": "A", "rank": 1, "score_total": 88.5}],
    )
    monkeypatch.setattr(
        daily_pipeline,
        "write_daily_topn_report",
        lambda **kwargs: report_calls.append(kwargs)
        or {"markdown_path": "/tmp/report.md", "csv_path": "/tmp/report.csv"},
    )

    result = daily_pipeline.run_daily_factor_pipeline("2026-05-08", top_n=10)

    assert len(build_calls) == 1
    assert build_calls[0]["trade_date"] == "2026-05-08"
    assert build_calls[0]["lookback_bars"] == 130
    assert len(score_calls) == 1
    assert score_calls[0]["trade_date"] == "2026-05-08"
    assert score_calls[0]["score_version"] == "manual_v1"
    assert score_calls[0]["approved_only"] is True
    assert len(top_score_calls) == 1
    assert top_score_calls[0]["trade_date"] == "2026-05-08"
    assert top_score_calls[0]["score_version"] == "manual_v1"
    assert top_score_calls[0]["top_n"] == 10
    assert top_score_calls[0]["universe_result"] is None
    assert len(report_calls) == 1
    assert report_calls[0]["trade_date"] == "2026-05-08"
    assert report_calls[0]["score_version"] == "manual_v1"
    assert report_calls[0]["top_scores"] == result["top_scores"]
    assert report_calls[0]["output_dir"] == "/Users/xiwei/stock_research/reports"
    assert result["factor_rows"] == 100
    assert result["score_rows"] == 20
    assert result["top_scores"][0]["asset_id"] == "A"
    assert result["report_paths"]["markdown_path"] == "/tmp/report.md"


def test_run_daily_factor_pipeline_passes_universe_result_to_load_top_scores(monkeypatch):
    calls = []
    universe_result = _universe_result(included=[("A", "A")], excluded=[("B", "B")])

    monkeypatch.setattr(
        daily_pipeline,
        "build_and_store_factor_daily",
        lambda **kwargs: 100,
    )
    monkeypatch.setattr(
        daily_pipeline,
        "score_stored_factor_daily",
        lambda **kwargs: 20,
    )
    monkeypatch.setattr(
        daily_pipeline,
        "load_top_scores",
        lambda **kwargs: calls.append(kwargs)
        or [{"trade_date": "2026-05-08", "asset_id": "A", "rank": 1, "score_total": 88.5}],
    )
    monkeypatch.setattr(
        daily_pipeline,
        "write_daily_topn_report",
        lambda **kwargs: {"markdown_path": "/tmp/report.md", "csv_path": "/tmp/report.csv"},
    )

    result = daily_pipeline.run_daily_factor_pipeline(
        "2026-05-08",
        top_n=10,
        universe_result=universe_result,
    )

    assert calls[0]["universe_result"] is universe_result
    assert result["top_scores"][0]["asset_id"] == "A"


def test_run_daily_factor_pipeline_writes_run_card(monkeypatch, tmp_path):
    monkeypatch.setattr(
        daily_pipeline,
        "build_and_store_factor_daily",
        lambda **kwargs: 100,
    )
    monkeypatch.setattr(
        daily_pipeline,
        "score_stored_factor_daily",
        lambda **kwargs: 20,
    )
    monkeypatch.setattr(
        daily_pipeline,
        "load_top_scores",
        lambda **kwargs: [{"trade_date": "2026-05-08", "asset_id": "A", "rank": 1, "score_total": 88.5}],
    )
    monkeypatch.setattr(
        daily_pipeline,
        "write_daily_topn_report",
        lambda **kwargs: {"markdown_path": str(tmp_path / "report.md"), "csv_path": str(tmp_path / "report.csv")},
    )

    result = daily_pipeline.run_daily_factor_pipeline(
        "2026-05-08",
        top_n=10,
        reports_dir=str(tmp_path),
    )

    assert Path(result["run_card"]["run_card_json_path"]).exists()
    assert Path(result["run_card"]["run_card_md_path"]).exists()
    assert Path(result["run_card"]["metrics_json_path"]).exists()
    assert Path(result["run_card"]["config_snapshot_path"]).exists()
    assert Path(result["run_card"]["warnings_md_path"]).exists()
    assert Path(result["run_card"]["data_coverage_json_path"]).exists()
    coverage = json.loads(Path(result["run_card"]["data_coverage_json_path"]).read_text(encoding="utf-8"))
    assert coverage["coverage_ratio"] is None
    assert coverage["missing_dates"] is None
    assert coverage["missing_assets"] is None
