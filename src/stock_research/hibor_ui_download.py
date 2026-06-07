from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2
from typing import Any, Protocol

import pandas as pd
from pandas.errors import EmptyDataError

from stock_research.config import SETTINGS
from stock_research.hibor_reports import import_hibor_report_pdfs


HIBOR_UI_REPORT = "hibor_ui_download_report.md"
HIBOR_UI_DOWNLOADS = "hibor_ui_downloaded_reports.csv"


@dataclass(frozen=True)
class HiborUiCoordinates:
    reference_width: int = 1920
    reference_height: int = 972
    home_huisou: tuple[int, int] = (455, 536)
    legacy_entry: tuple[int, int] = (1187, 558)
    title_tab: tuple[int, int] = (342, 124)
    search_input: tuple[int, int] = (500, 155)
    search_button: tuple[int, int] = (838, 155)
    one_year_filter: tuple[int, int] = (73, 895)
    first_download: tuple[int, int] = (1086, 438)

    def scaled(self, *, window_width: int, window_height: int) -> "HiborUiCoordinates":
        def scale(point: tuple[int, int]) -> tuple[int, int]:
            return (
                round(point[0] * window_width / self.reference_width),
                round(point[1] * window_height / self.reference_height),
            )

        return HiborUiCoordinates(
            reference_width=window_width,
            reference_height=window_height,
            home_huisou=scale(self.home_huisou),
            legacy_entry=scale(self.legacy_entry),
            title_tab=scale(self.title_tab),
            search_input=scale(self.search_input),
            search_button=scale(self.search_button),
            one_year_filter=scale(self.one_year_filter),
            first_download=scale(self.first_download),
        )


class HiborUiDriverProtocol(Protocol):
    def prepare(self) -> None:
        ...

    def search_and_download_first(self, query: str) -> None:
        ...


class HiborUiDriver:
    def __init__(
        self,
        *,
        app_name: str = "慧博智能策略终端",
        coordinates: HiborUiCoordinates | None = None,
        open_legacy_search: bool = True,
        time_filter: str = "all",
        action_delay_seconds: float = 0.4,
        search_delay_seconds: float = 3.0,
    ) -> None:
        self.app_name = app_name
        self.coordinates = coordinates or HiborUiCoordinates()
        self.open_legacy_search = open_legacy_search
        self.time_filter = time_filter
        self.action_delay_seconds = action_delay_seconds
        self.search_delay_seconds = search_delay_seconds

    def prepare(self) -> None:
        self._hide_process("Terminal")
        self._hide_process("Finder")
        self._activate_app()
        time.sleep(1.0)
        if self.open_legacy_search:
            self._click(*self.coordinates.home_huisou)
            time.sleep(3.0)
            self._click(*self.coordinates.legacy_entry)
            time.sleep(3.0)

    def search_and_download_first(self, query: str) -> None:
        self._hide_process("Finder")
        self._activate_app()
        time.sleep(self.action_delay_seconds)
        self._click(*self.coordinates.title_tab)
        time.sleep(self.action_delay_seconds)
        if self.time_filter == "one_year":
            self._click(*self.coordinates.one_year_filter)
            time.sleep(self.action_delay_seconds)
        self._click(*self.coordinates.search_input)
        time.sleep(self.action_delay_seconds)
        self._key_code(0, command=True)
        time.sleep(0.1)
        self._paste_text(query)
        time.sleep(self.action_delay_seconds)
        self._click(*self.coordinates.search_button)
        time.sleep(self.search_delay_seconds)
        self._key_code(126, command=True)
        time.sleep(self.action_delay_seconds)
        self._click(*self.coordinates.first_download)

    def _activate_app(self) -> None:
        _run_osascript(f'tell application "{self.app_name}" to activate')
        subprocess.run(
            ["osascript", "-e", f'tell application "System Events" to set frontmost of process "{self.app_name}" to true'],
            check=False,
            capture_output=True,
            text=True,
        )
        time.sleep(0.2)
        frontmost = _frontmost_process_name()
        if frontmost != self.app_name:
            raise RuntimeError(f"Hibor window is not frontmost; frontmost={frontmost!r}")

    def _hide_process(self, process_name: str) -> None:
        script = f'tell application "System Events" to set visible of process "{process_name}" to false'
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)

    def _keystroke(self, text: str, *, command: bool = False) -> None:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        if command:
            script = f'tell application "System Events" to keystroke "{escaped}" using command down'
        else:
            script = f'tell application "System Events" to keystroke "{escaped}"'
        _run_osascript(script)

    def _key_code(self, code: int, *, command: bool = False) -> None:
        _run_swift_key(code, command=command)

    def _paste_text(self, text: str) -> None:
        subprocess.run(["pbcopy"], input=text, check=True, text=True)
        _run_swift_key(9, command=True)

    def _click(self, x: int, y: int) -> None:
        _run_swift_click(x, y)


def build_hibor_ui_query(task: dict[str, Any]) -> str:
    stock_name = str(task.get("stock_name") or "").strip()
    symbol = str(task.get("symbol") or "").strip()
    if symbol:
        return f"{symbol} {stock_name}".strip()
    ts_code = str(task.get("ts_code") or "").strip()
    if "." in ts_code:
        return f"{ts_code.split('.', 1)[0]} {stock_name}".strip()
    if ts_code:
        return f"{ts_code} {stock_name}".strip()
    return stock_name


def run_hibor_ui_download_backfill(
    *,
    tasks_path: str | Path,
    output_dir: str | Path,
    download_dir: str | Path,
    staging_dir: str | Path | None = None,
    max_tasks: int | None = None,
    wait_timeout_seconds: float = 45.0,
    poll_seconds: float = 1.0,
    driver: HiborUiDriverProtocol | None = None,
    open_legacy_search: bool = True,
    time_filter: str = "all",
    import_pdfs: bool = True,
    write_db: bool = False,
    service: str = SETTINGS.research_service,
    run_pdf_backfill: bool = True,
    feature_trade_date: str | None = None,
) -> dict[str, Any]:
    task_file = Path(tasks_path)
    output = Path(output_dir)
    watch_dir = Path(download_dir)
    pdf_dir = Path(staging_dir) if staging_dir is not None else output / "pdfs"
    output.mkdir(parents=True, exist_ok=True)
    watch_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    tasks = pd.read_csv(task_file, dtype=object).fillna("")
    for column in ["downloaded_count", "downloaded_pdf_path", "error_type", "error_message", "started_at", "finished_at"]:
        if column not in tasks.columns:
            tasks[column] = ""

    ui_driver = driver or HiborUiDriver(open_legacy_search=open_legacy_search, time_filter=time_filter)
    ui_driver.prepare()
    processed = 0
    downloaded_rows = _load_existing_download_rows(output / HIBOR_UI_DOWNLOADS)

    for idx, task in tasks.iterrows():
        if str(task.get("status") or "") != "pending":
            continue
        if max_tasks is not None and processed >= max_tasks:
            break
        processed += 1
        query = build_hibor_ui_query(task.to_dict())
        before = _snapshot_pdfs(watch_dir)
        tasks.at[idx, "started_at"] = _utc_now_iso()
        try:
            ui_driver.search_and_download_first(query)
            new_pdfs = _wait_for_new_pdfs(watch_dir, before=before, timeout_seconds=wait_timeout_seconds, poll_seconds=poll_seconds)
            if new_pdfs:
                matched_sources = [path for path in new_pdfs if _pdf_matches_task(path, task.to_dict())]
                if matched_sources:
                    staged_pdfs = [_stage_pdf(path, pdf_dir) for path in matched_sources]
                    pdf_path = str(staged_pdfs[0])
                    tasks.at[idx, "status"] = "done"
                    tasks.at[idx, "downloaded_count"] = str(len(staged_pdfs))
                    tasks.at[idx, "downloaded_pdf_path"] = pdf_path
                    downloaded_rows.extend(
                        {
                            "task_id": str(task.get("task_id") or ""),
                            "ts_code": str(task.get("ts_code") or ""),
                            "stock_name": str(task.get("stock_name") or ""),
                            "query": query,
                            "pdf_path": str(path),
                            "status": "downloaded",
                        }
                        for path in staged_pdfs
                    )
                else:
                    tasks.at[idx, "status"] = "mismatched_report"
                    tasks.at[idx, "downloaded_count"] = "0"
                    tasks.at[idx, "downloaded_pdf_path"] = ""
                    tasks.at[idx, "error_type"] = "mismatched_report"
                    tasks.at[idx, "error_message"] = f"Downloaded PDF did not match task filename: {new_pdfs[0].name}"
            else:
                tasks.at[idx, "status"] = "download_timeout"
                tasks.at[idx, "downloaded_count"] = "0"
                tasks.at[idx, "error_type"] = "download_timeout"
                tasks.at[idx, "error_message"] = f"No new PDF appeared within {wait_timeout_seconds:g}s"
        except Exception as exc:
            tasks.at[idx, "status"] = "ui_error"
            tasks.at[idx, "downloaded_count"] = "0"
            tasks.at[idx, "error_type"] = type(exc).__name__
            tasks.at[idx, "error_message"] = str(exc)[:500]
        tasks.at[idx, "finished_at"] = _utc_now_iso()
        _persist(tasks, downloaded_rows, output, task_file)

    paths = _persist(tasks, downloaded_rows, output, task_file)
    import_result = None
    if import_pdfs:
        import_result = import_hibor_report_pdfs(
            input_dir=pdf_dir,
            output_dir=output / "import",
            write_db=write_db,
            service=service,
            run_pdf_backfill=run_pdf_backfill,
            feature_trade_date=feature_trade_date,
        )
        paths["import_report"] = import_result["paths"]["report"]

    return {
        "tasks": tasks,
        "downloads": pd.DataFrame(downloaded_rows),
        "import": import_result,
        "paths": paths,
        "summary": {
            "processed_tasks": processed,
            "downloaded_count": sum(1 for row in downloaded_rows if row.get("status") == "downloaded"),
            "done_tasks": int(tasks["status"].eq("done").sum()),
            "timeout_tasks": int(tasks["status"].eq("download_timeout").sum()),
            "ui_error_tasks": int(tasks["status"].eq("ui_error").sum()),
        },
    }


def _snapshot_pdfs(download_dir: Path) -> set[Path]:
    return {path.resolve() for path in download_dir.glob("*.pdf")}


def _wait_for_new_pdfs(download_dir: Path, *, before: set[Path], timeout_seconds: float, poll_seconds: float) -> list[Path]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() <= deadline:
        current = _snapshot_pdfs(download_dir)
        new_paths = sorted(current - before, key=lambda path: path.stat().st_mtime)
        ready = [path for path in new_paths if path.exists() and path.stat().st_size > 0]
        if ready:
            return ready
        time.sleep(poll_seconds)
    return []


def _stage_pdf(source: Path, staging_dir: Path) -> Path:
    target = staging_dir / source.name
    if source.resolve() != target.resolve():
        copy2(source, target)
    return target.resolve()


def _pdf_matches_task(path: Path, task: dict[str, Any]) -> bool:
    name = path.name
    stock_name = str(task.get("stock_name") or "").strip()
    symbol = str(task.get("symbol") or "").strip() or str(task.get("ts_code") or "").split(".", 1)[0]
    identity_match = bool((stock_name and stock_name in name) or (symbol and symbol in name))
    if not identity_match:
        return False
    report_date = _date_from_pdf_name(name)
    start_date = str(task.get("start_date") or "").strip()
    end_date = str(task.get("end_date") or "").strip()
    if report_date and start_date and pd.Timestamp(report_date) < pd.Timestamp(start_date):
        return False
    if report_date and end_date and pd.Timestamp(report_date) > pd.Timestamp(end_date):
        return False
    return True


def _date_from_pdf_name(name: str) -> str:
    prefix = name[:8]
    if len(prefix) == 8 and prefix.isdigit():
        return f"{prefix[:4]}-{prefix[4:6]}-{prefix[6:8]}"
    return ""


def _load_existing_download_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        return pd.read_csv(path, dtype=object).fillna("").to_dict("records")
    except EmptyDataError:
        return []


def _persist(tasks: pd.DataFrame, downloaded_rows: list[dict[str, Any]], output: Path, task_file: Path) -> dict[str, str]:
    tasks.to_csv(task_file, index=False)
    downloads_path = output / HIBOR_UI_DOWNLOADS
    pd.DataFrame(downloaded_rows, columns=["task_id", "ts_code", "stock_name", "query", "pdf_path", "status"]).to_csv(
        downloads_path,
        index=False,
    )
    report_path = output / HIBOR_UI_REPORT
    report_path.write_text(_render_report(tasks, downloaded_rows), encoding="utf-8")
    return {"tasks": str(task_file), "downloads": str(downloads_path), "report": str(report_path)}


def _render_report(tasks: pd.DataFrame, downloaded_rows: list[dict[str, Any]]) -> str:
    counts = tasks["status"].value_counts().to_dict() if "status" in tasks else {}
    lines = [
        "# Hibor UI Download Run",
        "",
        f"- tasks: {len(tasks)}",
        f"- downloaded_pdfs: {sum(1 for row in downloaded_rows if row.get('status') == 'downloaded')}",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"- {status}: {count}")
    return "\n".join(lines) + "\n"


def _run_osascript(script: str) -> None:
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)


def _run_swift_click(x: int, y: int) -> None:
    source = f"""
import Foundation
import CoreGraphics
let point = CGPoint(x: {float(x)}, y: {float(y)})
CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left)?.post(tap: .cghidEventTap)
usleep(80_000)
CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: point, mouseButton: .left)?.post(tap: .cghidEventTap)
usleep(80_000)
CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: point, mouseButton: .left)?.post(tap: .cghidEventTap)
"""
    subprocess.run(["swift", "-"], input=source, check=True, capture_output=True, text=True)


def _run_swift_key(code: int, *, command: bool = False) -> None:
    flags = "CGEventFlags.maskCommand" if command else "CGEventFlags()"
    source = f"""
import Foundation
import CoreGraphics
let source = CGEventSource(stateID: .hidSystemState)
let down = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode({code}), keyDown: true)
let up = CGEvent(keyboardEventSource: source, virtualKey: CGKeyCode({code}), keyDown: false)
down?.flags = {flags}
up?.flags = {flags}
down?.post(tap: .cghidEventTap)
usleep(80_000)
up?.post(tap: .cghidEventTap)
"""
    subprocess.run(["swift", "-"], input=source, check=True, capture_output=True, text=True)


def _frontmost_process_name() -> str:
    result = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _utc_now_iso() -> str:
    return pd.Timestamp.now("UTC").isoformat()
