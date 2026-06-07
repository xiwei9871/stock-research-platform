from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.stock_report_pdf_backfill import (
    PDF_STATUS_FILE,
    StockReportPdfBackfillWatchdogAdapter,
    build_stock_report_pdf_field_backfill,
    extract_stock_report_pdf_fields,
    fetch_pdf_text,
    upsert_stock_report_pdf_fields,
)


def test_extract_stock_report_pdf_fields_finds_target_price_rating_eps_pe_and_risk():
    text = """
    投资建议：我们维持“买入”评级。基于 DCF 模型，维持公司目标价 512 元人民币。
    预计 2026-2028 年 EPS 分别为 21.11/26.31/30.87 元，PE 分别为 21.2/17.0/14.5 倍。
    风险提示：行业竞争加剧；原材料价格波动。
    """

    result = extract_stock_report_pdf_fields(text)

    assert result["target_price"] == 512.0
    assert result["rating_pdf"] == "买入"
    assert result["rating_change_type"] == "维持"
    assert result["forecast_eps_values"] == [21.11, 26.31, 30.87]
    assert result["forecast_pe_values"] == [21.2, 17.0, 14.5]
    assert result["has_risk_section"] is True
    assert "行业竞争" in result["risk_summary"]


def test_extract_stock_report_pdf_fields_handles_target_price_table_and_value_range():
    table_text = "目标价(元)141 公司基本信息 A股价(2026/6/1)117.35"
    range_text = "投资评级优于大市(首次) 合理估值87.80-93.90元 收盘价71.30元"
    blank_text = "公司点评 买入/维持 目标价: 昨收盘:49.92"

    table_result = extract_stock_report_pdf_fields(table_text)
    range_result = extract_stock_report_pdf_fields(range_text)
    blank_result = extract_stock_report_pdf_fields(blank_text)

    assert table_result["target_price"] == 141.0
    assert table_result["target_price_extract_method"] == "target_price_table_regex"
    assert range_result["target_price"] == 90.85
    assert range_result["target_price_extract_method"] == "reasonable_value_range_regex"
    assert blank_result["target_price"] is None


def test_fetch_pdf_text_reads_local_pdf_path(monkeypatch, tmp_path: Path):
    pdf_path = tmp_path / "local-report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 local test")

    class FakePage:
        def __init__(self, text: str):
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, source):
            assert source == str(pdf_path)
            self.pages = [FakePage("第一页文本"), FakePage("第二页文本")]

    monkeypatch.setattr("stock_research.stock_report_pdf_backfill.PdfReader", FakeReader)

    text = fetch_pdf_text(str(pdf_path))

    assert "第一页文本" in text
    assert "第二页文本" in text


def test_build_stock_report_pdf_field_backfill_outputs_structured_rows(tmp_path: Path):
    sources = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "source_url": "https://example.com/r1.pdf",
                "broker": "测试证券",
                "report_title": "测试报告",
                "publish_date": "2026-04-23",
            }
        ]
    )

    def fake_fetcher(url: str) -> str:
        assert url == "https://example.com/r1.pdf"
        return "首次覆盖，给予买入评级，目标价 88.5 元。EPS 分别为 1.2/1.5/1.8 元。风险提示：需求不及预期。"

    result = build_stock_report_pdf_field_backfill(
        sources=sources,
        fetcher=fake_fetcher,
        output_dir=tmp_path,
    )

    rows = result["fields"]
    assert rows.iloc[0]["status"] == "parsed"
    assert rows.iloc[0]["target_price"] == 88.5
    assert rows.iloc[0]["rating_pdf"] == "买入"
    assert rows.iloc[0]["rating_change_type"] == "首次覆盖"
    assert Path(result["paths"]["fields"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_pdf_backfill_writes_incremental_status(tmp_path: Path):
    sources = pd.DataFrame(
        [
            {"report_id": "r1", "source_url": "https://example.com/r1.pdf"},
            {"report_id": "r2", "source_url": "https://example.com/r2.pdf"},
        ]
    )
    status_path = tmp_path / PDF_STATUS_FILE

    def fake_fetcher(url: str) -> str:
        if url.endswith("r2.pdf"):
            status = pd.read_csv(status_path)
            assert status.loc[status["report_id"].eq("r1"), "status"].iloc[0] == "parsed"
        return "维持买入评级。风险提示：需求不及预期。"

    result = build_stock_report_pdf_field_backfill(
        sources=sources,
        fetcher=fake_fetcher,
        output_dir=tmp_path,
    )

    status = pd.read_csv(result["paths"]["status"])
    assert list(status["status"]) == ["parsed", "parsed"]


def test_pdf_backfill_resume_skips_successful_rows_and_retries_pending(tmp_path: Path):
    sources = pd.DataFrame(
        [
            {"report_id": "r1", "source_url": "https://example.com/r1.pdf"},
            {"report_id": "r2", "source_url": "https://example.com/r2.pdf"},
        ]
    )
    pd.DataFrame(
        [
            {"report_id": "r1", "source_url": "https://example.com/r1.pdf", "status": "parsed", "target_price": 88.5},
            {"report_id": "r2", "source_url": "https://example.com/r2.pdf", "status": "pending"},
        ]
    ).to_csv(tmp_path / PDF_STATUS_FILE, index=False)
    fetched = []

    def fake_fetcher(url: str) -> str:
        fetched.append(url)
        assert not url.endswith("r1.pdf")
        return "目标价(元)141 风险提示：需求不及预期。"

    result = build_stock_report_pdf_field_backfill(
        sources=sources,
        fetcher=fake_fetcher,
        output_dir=tmp_path,
        resume=True,
    )

    assert fetched == ["https://example.com/r2.pdf"]
    fields = result["fields"].sort_values("report_id").reset_index(drop=True)
    assert fields.loc[0, "target_price"] == 88.5
    assert fields.loc[1, "target_price"] == 141.0


def test_pdf_backfill_watchdog_summarizes_status(tmp_path: Path):
    pd.DataFrame(
        [
            {"report_id": "r1", "status": "parsed", "target_price": 88.5},
            {"report_id": "r2", "status": "parse_error"},
            {"report_id": "r3", "status": "pending"},
        ]
    ).to_csv(tmp_path / PDF_STATUS_FILE, index=False)

    adapter = StockReportPdfBackfillWatchdogAdapter(output_dir=tmp_path)
    rows = adapter.load_status_rows()
    summary = adapter.summarize_status(rows)

    assert summary.total_tasks == 3
    assert summary.success_tasks == 1
    assert summary.failed_tasks == 1
    assert summary.pending_tasks == 1
    assert summary.total_rows_written == 1


def test_upsert_stock_report_pdf_fields_updates_existing_columns_and_metadata(monkeypatch):
    captured = {}

    class FakeConn:
        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params

    class FakeConnect:
        def __init__(self, service):
            self.conn = FakeConn()

        def __enter__(self):
            return self.conn

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("stock_research.stock_report_pdf_backfill.connect", FakeConnect)

    fields = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "target_price": 88.5,
                "target_upside": 0.25,
                "rating_pdf": "买入",
                "rating_change_type": "首次覆盖",
                "risk_summary": "需求不及预期",
                "target_price_confidence": 0.8,
                "target_price_extract_method": "target_price_regex",
                "forecast_eps_values": [1.2, 1.5, 1.8],
                "forecast_pe_values": [20.0, 16.0, 13.0],
                "status": "parsed",
            }
        ]
    )

    result = upsert_stock_report_pdf_fields(fields, service="fake")

    assert result["updated_rows"] == 1
    assert "target_price = COALESCE" in captured["sql"]
    assert "metadata = research.stock_report_event.metadata" in captured["sql"]
    assert captured["params"][0] == 88.5
    assert captured["params"][-1] == "r1"


def test_cli_dispatches_stock_report_pdf_field_backfill(monkeypatch, tmp_path: Path, capsys):
    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)
        fields = pd.DataFrame([{"status": "parsed"}])
        return {
            "fields": fields,
            "paths": {
                "fields": str(tmp_path / "fields.csv"),
                "summary": str(tmp_path / "summary.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_stock_report_pdf_field_backfill", fake_run)

    cli.main(
        [
            "stock-report-pdf-field-backfill",
            "--source-path",
            "sources.csv",
            "--offset",
            "5",
            "--limit",
            "10",
            "--output-dir",
            str(tmp_path),
        ]
    )

    out = capsys.readouterr().out
    assert called["source_path"] == "sources.csv"
    assert called["offset"] == 5
    assert called["limit"] == 10
    assert "stock_report_pdf_field_backfill|fields|" in out


def test_cli_dispatches_stock_report_pdf_backfill_watchdog(monkeypatch, tmp_path: Path, capsys):
    called = {}

    def fake_watchdog(**kwargs):
        called.update(kwargs)

        class Status:
            watchdog_action = "healthy"
            work_remaining = False

        class Summary:
            success_tasks = 1
            failed_tasks = 0
            pending_tasks = 0
            total_rows_written = 1

        return {"status": Status(), "post_summary": Summary()}

    monkeypatch.setattr(cli, "run_stock_report_pdf_backfill_watchdog", fake_watchdog)

    cli.main(
        [
            "stock-report-pdf-backfill-watchdog",
            "--output-dir",
            str(tmp_path),
            "--report-target",
            "dry-run",
            "--report-dry-run",
        ]
    )

    out = capsys.readouterr().out
    assert called["output_dir"] == str(tmp_path)
    assert "stock_report_pdf_backfill_watchdog|action|healthy" in out
