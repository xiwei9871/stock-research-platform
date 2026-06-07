from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.hibor_ui_download import (
    HiborUiCoordinates,
    build_hibor_ui_query,
    run_hibor_ui_download_backfill,
)


class FakeHiborUiDriver:
    def __init__(self, download_dir: Path):
        self.download_dir = download_dir
        self.queries = []

    def prepare(self) -> None:
        pass

    def search_and_download_first(self, query: str) -> None:
        self.queries.append(query)
        if query == "600456 宝钛股份":
            (self.download_dir / "东吴证券-宝钛股份-600456-深度报告-260604.pdf").write_bytes(b"%PDF-1.4\nfake")


class MismatchHiborUiDriver:
    def __init__(self, download_dir: Path):
        self.download_dir = download_dir

    def prepare(self) -> None:
        pass

    def search_and_download_first(self, query: str) -> None:
        (self.download_dir / "东方证券-国防军工行业动态跟踪-260324.pdf").write_bytes(b"%PDF-1.4\nfake")


class OutOfWindowHiborUiDriver:
    def __init__(self, download_dir: Path):
        self.download_dir = download_dir

    def prepare(self) -> None:
        pass

    def search_and_download_first(self, query: str) -> None:
        (self.download_dir / "20221030-国盛证券-共达电声-002655-Q3利润同比高增长，车载业务进展顺利.pdf").write_bytes(b"%PDF-1.4\nfake")


def test_build_hibor_ui_query_prefers_symbol():
    assert build_hibor_ui_query({"symbol": "600456", "stock_name": "宝钛股份"}) == "600456 宝钛股份"
    assert build_hibor_ui_query({"ts_code": "300831.SZ", "stock_name": "派瑞股份"}) == "300831 派瑞股份"
    assert build_hibor_ui_query({"stock_name": "派瑞股份"}) == "派瑞股份"


def test_hibor_ui_coordinates_scale_from_reference_window():
    coords = HiborUiCoordinates().scaled(window_width=960, window_height=486)

    assert coords.search_input == (250, 78)
    assert coords.search_button == (419, 78)


def test_run_hibor_ui_download_backfill_marks_downloaded_and_imports(tmp_path: Path, monkeypatch):
    task_path = tmp_path / "tasks.csv"
    download_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staged"
    output_dir = tmp_path / "out"
    download_dir.mkdir()
    pd.DataFrame(
        [
            {
                "task_id": "hibor_ui_600456",
                "ts_code": "600456.SH",
                "symbol": "600456",
                "stock_name": "宝钛股份",
                "status": "pending",
            },
            {
                "task_id": "hibor_ui_300831",
                "ts_code": "300831.SZ",
                "symbol": "300831",
                "stock_name": "派瑞股份",
                "status": "pending",
            },
        ]
    ).to_csv(task_path, index=False)
    calls = {}

    def fake_import(**kwargs):
        calls.update(kwargs)
        return {"paths": {"report": str(output_dir / "import" / "report.md")}, "summary": {"pdf_count": 1}}

    monkeypatch.setattr("stock_research.hibor_ui_download.import_hibor_report_pdfs", fake_import)

    result = run_hibor_ui_download_backfill(
        tasks_path=task_path,
        output_dir=output_dir,
        download_dir=download_dir,
        staging_dir=staging_dir,
        max_tasks=1,
        driver=FakeHiborUiDriver(download_dir),
        wait_timeout_seconds=0.1,
        import_pdfs=True,
        write_db=True,
        feature_trade_date="2026-06-06",
    )

    refreshed = pd.read_csv(task_path, dtype=str).fillna("")
    assert refreshed.loc[0, "status"] == "done"
    assert refreshed.loc[0, "downloaded_count"] == "1"
    assert str(staging_dir) in refreshed.loc[0, "downloaded_pdf_path"]
    assert "东吴证券-宝钛股份-600456-深度报告-260604.pdf" in refreshed.loc[0, "downloaded_pdf_path"]
    assert refreshed.loc[1, "status"] == "pending"
    assert result["summary"]["processed_tasks"] == 1
    assert result["summary"]["downloaded_count"] == 1
    assert calls["input_dir"] == staging_dir
    assert calls["write_db"] is True
    assert calls["feature_trade_date"] == "2026-06-06"


def test_run_hibor_ui_download_backfill_rejects_mismatched_pdf(tmp_path: Path, monkeypatch):
    task_path = tmp_path / "tasks.csv"
    download_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staged"
    output_dir = tmp_path / "out"
    download_dir.mkdir()
    pd.DataFrame(
        [
            {
                "task_id": "hibor_ui_600456",
                "ts_code": "600456.SH",
                "symbol": "600456",
                "stock_name": "宝钛股份",
                "status": "pending",
            }
        ]
    ).to_csv(task_path, index=False)

    monkeypatch.setattr(
        "stock_research.hibor_ui_download.import_hibor_report_pdfs",
        lambda **kwargs: {"paths": {"report": str(output_dir / "import.md")}, "summary": {"pdf_count": 0}},
    )

    result = run_hibor_ui_download_backfill(
        tasks_path=task_path,
        output_dir=output_dir,
        download_dir=download_dir,
        staging_dir=staging_dir,
        max_tasks=1,
        driver=MismatchHiborUiDriver(download_dir),
        wait_timeout_seconds=0.1,
        import_pdfs=False,
    )

    refreshed = pd.read_csv(task_path, dtype=str).fillna("")
    assert refreshed.loc[0, "status"] == "mismatched_report"
    assert refreshed.loc[0, "downloaded_count"] == "0"
    assert "国防军工行业动态跟踪" in refreshed.loc[0, "error_message"]
    assert list(staging_dir.glob("*.pdf")) == []
    downloads = pd.read_csv(output_dir / "hibor_ui_downloaded_reports.csv", dtype=str).fillna("")
    assert downloads.empty
    assert result["summary"]["downloaded_count"] == 0


def test_run_hibor_ui_download_backfill_rejects_out_of_window_pdf(tmp_path: Path):
    task_path = tmp_path / "tasks.csv"
    download_dir = tmp_path / "downloads"
    staging_dir = tmp_path / "staged"
    output_dir = tmp_path / "out"
    download_dir.mkdir()
    pd.DataFrame(
        [
            {
                "task_id": "hibor_ui_002655",
                "ts_code": "002655.SZ",
                "symbol": "002655",
                "stock_name": "共达电声",
                "start_date": "2025-01-01",
                "end_date": "2026-06-06",
                "status": "pending",
            }
        ]
    ).to_csv(task_path, index=False)

    run_hibor_ui_download_backfill(
        tasks_path=task_path,
        output_dir=output_dir,
        download_dir=download_dir,
        staging_dir=staging_dir,
        max_tasks=1,
        driver=OutOfWindowHiborUiDriver(download_dir),
        wait_timeout_seconds=0.1,
        import_pdfs=False,
    )

    refreshed = pd.read_csv(task_path, dtype=str).fillna("")
    assert refreshed.loc[0, "status"] == "mismatched_report"
    assert list(staging_dir.glob("*.pdf")) == []
    downloads = pd.read_csv(output_dir / "hibor_ui_downloaded_reports.csv", dtype=str).fillna("")
    assert downloads.empty


def test_run_hibor_ui_download_backfill_tolerates_empty_existing_manifest(tmp_path: Path):
    task_path = tmp_path / "tasks.csv"
    download_dir = tmp_path / "downloads"
    output_dir = tmp_path / "out"
    download_dir.mkdir()
    output_dir.mkdir()
    (output_dir / "hibor_ui_downloaded_reports.csv").write_text("\n", encoding="utf-8")
    pd.DataFrame(
        [
            {
                "task_id": "hibor_ui_002655",
                "ts_code": "002655.SZ",
                "symbol": "002655",
                "stock_name": "共达电声",
                "status": "pending",
            }
        ]
    ).to_csv(task_path, index=False)

    result = run_hibor_ui_download_backfill(
        tasks_path=task_path,
        output_dir=output_dir,
        download_dir=download_dir,
        max_tasks=1,
        driver=MismatchHiborUiDriver(download_dir),
        wait_timeout_seconds=0.1,
        import_pdfs=False,
    )

    assert result["summary"]["processed_tasks"] == 1


def test_cli_dispatches_run_hibor_ui_download_backfill(monkeypatch, tmp_path: Path, capsys):
    task_path = tmp_path / "tasks.csv"
    task_path.write_text("task_id,status\nhibor_ui_600456,pending\n", encoding="utf-8")
    calls = {}

    def fake_run(**kwargs):
        calls.update(kwargs)
        return {
            "paths": {
                "tasks": str(task_path),
                "downloads": str(tmp_path / "downloads.csv"),
                "report": str(tmp_path / "report.md"),
                "import_report": str(tmp_path / "import.md"),
            },
            "summary": {
                "processed_tasks": 1,
                "downloaded_count": 1,
                "done_tasks": 1,
                "timeout_tasks": 0,
                "ui_error_tasks": 0,
            },
        }

    monkeypatch.setattr(cli, "run_hibor_ui_download_backfill", fake_run)

    cli.main(
        [
            "run-hibor-ui-download-backfill",
            "--tasks-path",
            str(task_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--download-dir",
            str(tmp_path / "pdfs"),
            "--max-tasks",
            "1",
            "--write-db",
            "--feature-trade-date",
            "2026-06-06",
            "--time-filter",
            "one_year",
        ]
    )

    out = capsys.readouterr().out
    assert calls["tasks_path"] == str(task_path)
    assert calls["max_tasks"] == 1
    assert calls["write_db"] is True
    assert calls["feature_trade_date"] == "2026-06-06"
    assert calls["time_filter"] == "one_year"
    assert "hibor_ui_download|processed_tasks|1" in out
    assert "hibor_ui_download|downloaded|1" in out
