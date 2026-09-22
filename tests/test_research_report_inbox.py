from pathlib import Path

import pandas as pd

from stock_research.research_report_inbox import (
    build_research_inbox_sources_events,
    sync_research_report_inbox,
)


def test_build_research_inbox_sources_events_accepts_ts_code_filename(tmp_path: Path):
    pdf_path = tmp_path / "20260601-招商证券-深南电路-002916.SZ-mSAP放量_AI_PCB高增.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    result = build_research_inbox_sources_events([pdf_path])

    source = result["sources"].iloc[0]
    event = result["events"].iloc[0]
    assert source["source_type"] == "research_report_inbox"
    assert source["source_name"] == "本地研报收件箱"
    assert source["broker"] == "招商证券"
    assert source["report_title"] == "mSAP放量_AI_PCB高增"
    assert source["source_url"].startswith("file://")
    assert event["asset_id"] == "CN:SZ:002916"
    assert event["ts_code"] == "002916.SZ"
    assert event["stock_name"] == "深南电路"
    assert event["report_date"] == "2026-06-01"


def test_sync_research_report_inbox_imports_only_new_supported_pdfs(monkeypatch, tmp_path: Path):
    inbox = tmp_path / "inbox"
    output = tmp_path / "out"
    inbox.mkdir()
    first = inbox / "20260601-招商证券-深南电路-002916.SZ-mSAP放量_AI_PCB高增.pdf"
    first.write_bytes(b"%PDF-1.4 first")
    unsupported = inbox / "unmatched.pdf"
    unsupported.write_bytes(b"%PDF-1.4 unsupported")
    calls: dict[str, object] = {}

    def fake_upsert_sources_events(**kwargs):
        calls["sources"] = kwargs["sources"]
        calls["events"] = kwargs["events"]
        return {"source_rows": len(kwargs["sources"]), "event_rows": len(kwargs["events"])}

    def fake_pdf_backfill(**kwargs):
        calls["pdf_sources"] = kwargs["sources"]
        return {
            "fields": pd.DataFrame([{"report_id": kwargs["sources"].iloc[0]["report_id"], "status": "parsed"}]),
            "paths": {"fields": str(output / "fields.csv")},
        }

    def fake_upsert_pdf_fields(fields, service):
        calls["pdf_fields"] = fields
        return {"updated_rows": len(fields)}

    monkeypatch.setattr("stock_research.research_report_inbox.upsert_stock_report_sources_events", fake_upsert_sources_events)
    monkeypatch.setattr("stock_research.research_report_inbox.build_stock_report_pdf_field_backfill", fake_pdf_backfill)
    monkeypatch.setattr("stock_research.research_report_inbox.upsert_stock_report_pdf_fields", fake_upsert_pdf_fields)

    first_result = sync_research_report_inbox(input_dir=inbox, output_dir=output, write_db=True)
    second_result = sync_research_report_inbox(input_dir=inbox, output_dir=output, write_db=True)

    assert first_result["summary"]["scanned_pdf_count"] == 2
    assert first_result["summary"]["new_pdf_count"] == 2
    assert first_result["summary"]["imported_pdf_count"] == 1
    assert first_result["summary"]["unsupported_pdf_count"] == 1
    assert second_result["summary"]["new_pdf_count"] == 0
    assert second_result["summary"]["imported_pdf_count"] == 0
    assert calls["sources"].iloc[0]["report_title"] == "mSAP放量_AI_PCB高增"
