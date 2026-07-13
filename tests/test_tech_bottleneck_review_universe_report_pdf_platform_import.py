import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_review_universe_report_pdf_platform_import import (
    build_platform_report_import_frames,
    run_tech_bottleneck_review_universe_report_pdf_platform_import,
)


def test_build_platform_report_import_frames_filters_real_pdfs_and_dedupes(tmp_path: Path) -> None:
    pdf_one = tmp_path / "20260102-中信证券-测试股份-000001.SZ-公司深度_20页.pdf"
    pdf_two = tmp_path / "20260103-国金证券-测试股份-000001.SZ-点评_3页.pdf"
    manifest = tmp_path / "yanbaoke_downloads.csv"
    pdf_one.write_bytes(b"%PDF-1.7\nfake")
    pdf_two.write_bytes(b"%PDF-1.7\nfake")
    manifest.write_text("not,pdf\n", encoding="utf-8")
    coverage = pd.DataFrame(
        [
            {
                "stock_code": "000001",
                "stock_name": "测试股份",
                "has_report_pdf": True,
                "report_pdf_count": 4,
                "report_pdf_paths": f"{pdf_one} | {pdf_one} | {manifest} | {tmp_path / 'missing.pdf'} | {pdf_two}",
                "report_titles": "ignored",
            }
        ]
    )

    built = build_platform_report_import_frames(coverage, existing_local_pdf_paths={str(pdf_two.resolve())})

    assert built.summary["coverage_stock_count"] == 1
    assert built.summary["candidate_pdf_path_count"] == 5
    assert built.summary["non_pdf_path_count"] == 1
    assert built.summary["missing_pdf_path_count"] == 1
    assert built.summary["duplicate_input_pdf_path_count"] == 1
    assert built.summary["already_indexed_pdf_path_count"] == 1
    assert built.summary["import_pdf_count"] == 1

    source = built.sources.iloc[0].to_dict()
    event = built.events.iloc[0].to_dict()
    metadata = json.loads(source["metadata"])
    assert source["source_name"] == "研报客 API"
    assert source["source_type"] == "yanbaoke_api"
    assert source["source_url"] == pdf_one.resolve().as_uri()
    assert metadata["yanbaoke"]["local_pdf_path"] == str(pdf_one.resolve())
    assert metadata["tech_bottleneck_review_universe_platform_import"]["stock_code"] == "000001"
    assert event["asset_id"] == "CN:SZ:000001"
    assert event["ts_code"] == "000001.SZ"
    assert event["auto_trade_enabled"] is False


def test_run_platform_import_writes_candidates_and_guardrails(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "20260102-中信证券-测试股份-600001.SH-公司深度_20页.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\nfake")
    coverage_path = tmp_path / "coverage.csv"
    pd.DataFrame(
        [
            {
                "stock_code": "600001",
                "stock_name": "测试股份",
                "has_report_pdf": True,
                "report_pdf_count": 1,
                "report_pdf_paths": str(pdf_path),
                "report_titles": pdf_path.name,
            }
        ]
    ).to_csv(coverage_path, index=False)

    captured = {}

    def fake_existing_paths(*, service: str) -> set[str]:
        assert service == "svc"
        return set()

    def fake_upsert(*, sources: pd.DataFrame, events: pd.DataFrame, service: str) -> dict[str, int]:
        captured["sources"] = sources.copy()
        captured["events"] = events.copy()
        captured["service"] = service
        return {"source_rows": len(sources), "event_rows": len(events)}

    monkeypatch.setattr(
        "stock_research.tech_bottleneck_review_universe_report_pdf_platform_import.load_existing_local_pdf_paths",
        fake_existing_paths,
    )
    monkeypatch.setattr(
        "stock_research.tech_bottleneck_review_universe_report_pdf_platform_import.upsert_stock_report_sources_events",
        fake_upsert,
    )

    result = run_tech_bottleneck_review_universe_report_pdf_platform_import(
        coverage_paths=[coverage_path],
        output_dir=tmp_path / "out",
        write_db=True,
        service="svc",
    )

    summary = result["summary"]
    guardrails = result["guardrails"]
    assert summary["import_pdf_count"] == 1
    assert summary["db_write_performed"] is True
    assert summary["db_result"] == {"source_rows": 1, "event_rows": 1}
    assert guardrails["platform_report_import_performed"] is True
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert captured["service"] == "svc"
    assert (tmp_path / "out" / "review_universe_report_pdf_platform_import_sources.csv").exists()
    assert (tmp_path / "out" / "review_universe_report_pdf_platform_import_events.csv").exists()
    assert json.loads(
        (tmp_path / "out" / "review_universe_report_pdf_platform_import_summary.json").read_text(encoding="utf-8")
    )["acceptance_decision"] == "review_universe_report_pdf_platform_import_ready"
