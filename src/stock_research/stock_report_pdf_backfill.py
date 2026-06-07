from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import re
import time
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import pandas as pd
import requests

from stock_research.config import SETTINGS
from stock_research.backfill_watchdog import (
    BackfillSummary,
    run_watchdog_once,
    should_send_watchdog_message,
)
from stock_research.db import connect, fetch_all
from stock_research.feishu_notify import send_openclaw_feishu_message

try:  # pragma: no cover - optional runtime dependency, covered through text fetcher tests
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


FIELDS_FILE = "stock_report_pdf_field_backfill.csv"
PDF_STATUS_FILE = "stock_report_pdf_field_backfill_status.csv"
SUMMARY_FILE = "stock_report_pdf_field_backfill_summary.csv"
REPORT_FILE = "stock_report_pdf_field_backfill_report.md"


def run_stock_report_pdf_field_backfill(
    *,
    source_path: str | Path | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    offset: int = 0,
    limit: int | None = None,
    sample_size: int | None = None,
    sleep_seconds: float = 0.05,
    output_dir: str | Path = "outputs/research",
    resume: bool = True,
    write_db: bool = False,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    sources = load_stock_report_pdf_sources(
        source_path=source_path,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=limit,
        sample_size=sample_size,
        service=service,
    )
    result = build_stock_report_pdf_field_backfill(
        sources=sources,
        sleep_seconds=sleep_seconds,
        output_dir=output_dir,
        resume=resume,
    )
    if write_db:
        result["db"] = upsert_stock_report_pdf_fields(result["fields"], service=service)
    return result


def load_stock_report_pdf_sources(
    *,
    source_path: str | Path | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    offset: int = 0,
    limit: int | None = None,
    sample_size: int | None = None,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if source_path:
        frame = pd.read_csv(source_path, low_memory=False)
    else:
        where = ["source_url IS NOT NULL", "source_url LIKE '%%.pdf%%'"]
        params: list[Any] = []
        if start_date:
            where.append("publish_date >= %s")
            params.append(start_date)
        if end_date:
            where.append("publish_date <= %s")
            params.append(end_date)
        sql = f"""
            SELECT report_id, source_url, broker, analyst, report_title, publish_date::text AS publish_date
            FROM research.stock_report_source
            WHERE {" AND ".join(where)}
            ORDER BY publish_date DESC, report_id
        """
        if limit is not None:
            sql += " LIMIT %s"
            params.append(int(limit))
        if offset:
            sql += " OFFSET %s"
            params.append(int(offset))
        with connect(service) as conn:
            rows = fetch_all(conn, sql, params)
        frame = pd.DataFrame(rows)
    if frame.empty:
        return _empty_sources()
    for column in ["report_id", "source_url", "broker", "analyst", "report_title", "publish_date"]:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[frame["source_url"].fillna("").astype(str).str.contains(".pdf", regex=False)].copy()
    frame = frame.drop_duplicates(subset=["source_url"], keep="first")
    if start_date:
        frame = frame[pd.to_datetime(frame["publish_date"], errors="coerce").ge(pd.to_datetime(start_date))].copy()
    if end_date:
        frame = frame[pd.to_datetime(frame["publish_date"], errors="coerce").le(pd.to_datetime(end_date))].copy()
    if offset and source_path:
        frame = frame.iloc[int(offset) :].copy()
    if sample_size is not None:
        frame = frame.head(int(sample_size)).copy()
    elif limit is not None and source_path:
        frame = frame.head(int(limit)).copy()
    return frame.reset_index(drop=True)


def build_stock_report_pdf_field_backfill(
    *,
    sources: pd.DataFrame,
    fetcher: Callable[[str], str] | None = None,
    sleep_seconds: float = 0.0,
    output_dir: str | Path | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    fetch = fetcher or fetch_pdf_text
    output = Path(output_dir) if output_dir is not None else None
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
    status_path = output / PDF_STATUS_FILE if output is not None else None
    status_frame = _initial_pdf_status_frame(sources)
    if resume and status_path is not None and status_path.exists():
        status_frame = _merge_existing_pdf_status(status_frame, pd.read_csv(status_path, low_memory=False))
    _write_pdf_status(status_frame, status_path)

    rows_by_report = {
        _safe_text(row.get("report_id")): dict(row)
        for row in status_frame.fillna("").to_dict("records")
        if _safe_text(row.get("report_id"))
    }
    for idx, source in status_frame.reset_index(drop=True).iterrows():
        report_id = _safe_text(source.get("report_id"))
        row = dict(rows_by_report.get(report_id, {}))
        if _safe_text(row.get("status")) in {"parsed", "empty_text"}:
            continue
        row.update(
            {
                "sample_id": idx + 1,
                "report_id": report_id,
                "source_url": _safe_text(source.get("source_url")),
                "broker": _safe_text(source.get("broker")),
                "analyst": _safe_text(source.get("analyst")),
                "report_title": _safe_text(source.get("report_title")),
                "publish_date": _safe_text(source.get("publish_date")),
                "status": "pending",
                "error_type": "",
                "error_message": "",
            }
        )
        try:
            text = fetch(row["source_url"])
            fields = extract_stock_report_pdf_fields(text)
            row.update(fields)
            row["status"] = "parsed" if fields["pdf_text_extract_chars"] > 0 else "empty_text"
        except Exception as exc:  # pragma: no cover - exercised by real network conditions
            row["status"] = "parse_error"
            row["error_type"] = type(exc).__name__
            row["error_message"] = str(exc)[:240]
        rows_by_report[report_id] = row
        status_frame = _status_frame_from_rows(status_frame, rows_by_report)
        _write_pdf_status(status_frame, status_path)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    fields_frame = _status_frame_from_rows(status_frame, rows_by_report)
    summary = summarize_pdf_field_backfill(fields_frame)
    report = render_pdf_field_backfill_report(fields_frame, summary)
    result: dict[str, Any] = {"fields": fields_frame, "summary": summary, "report": report, "paths": {}}
    if output_dir is not None:
        paths = {
            "fields": output / FIELDS_FILE,
            "status": output / PDF_STATUS_FILE,
            "summary": output / SUMMARY_FILE,
            "report": output / REPORT_FILE,
        }
        fields_frame.to_csv(paths["fields"], index=False)
        fields_frame.to_csv(paths["status"], index=False)
        summary.to_csv(paths["summary"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


class StockReportPdfBackfillWatchdogAdapter:
    def __init__(
        self,
        *,
        output_dir: str | Path,
        task_name: str = "stock_report_pdf_field_backfill",
        dataset: str = "research.stock_report_event.metadata.pdf_extract",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.task_name = task_name
        self.dataset = dataset

    @property
    def status_path(self) -> Path:
        return self.output_dir / PDF_STATUS_FILE

    def load_scope(self) -> dict[str, str]:
        return {
            "task": self.task_name,
            "task_name": self.task_name,
            "dataset": self.dataset,
            "run_id": f"stock-report-pdf-field-backfill:{self.output_dir}",
            "window": str(self.output_dir),
        }

    def load_status_rows(self) -> list[dict[str, Any]]:
        if not self.status_path.exists():
            return []
        return pd.read_csv(self.status_path, low_memory=False).fillna("").to_dict("records")

    def summarize_status(self, rows: list[dict[str, Any]]) -> BackfillSummary:
        statuses = [str(row.get("status") or "pending") for row in rows]
        pending = sum(1 for status in statuses if status in {"pending", ""})
        return BackfillSummary(
            total_tasks=len(rows),
            pending_tasks=pending,
            running_tasks=1 if pending > 0 else 0,
            success_tasks=sum(1 for status in statuses if status in {"parsed", "empty_text"}),
            failed_tasks=sum(1 for status in statuses if status == "parse_error"),
            skipped_tasks=0,
            total_rows_written=sum(1 for row in rows if _has_value(row.get("target_price"))),
        )

    def compute_frontier(self, rows: list[dict[str, Any]]) -> dict[str, str | None]:
        completed_through = None
        currently_working_on = None
        for row in rows:
            label = str(row.get("report_id") or row.get("source_url") or "")
            status = str(row.get("status") or "pending")
            if status in {"parsed", "empty_text", "parse_error"}:
                completed_through = label
                continue
            currently_working_on = label
            break
        return {"completed_through": completed_through, "currently_working_on": currently_working_on}

    def reset_stale_tasks(self, stale_after_minutes: int) -> int:
        del stale_after_minutes
        return 0

    def run_once(
        self,
        *,
        scope: dict[str, str],
        max_jobs: int,
        workers: int,
        run_timeout_seconds: int,
    ) -> dict[str, Any]:
        del scope, max_jobs, workers, run_timeout_seconds
        summary = self.summarize_status(self.load_status_rows())
        return {
            "attempted": 0,
            "success": 0,
            "failed": 0,
            "rows": 0,
            "status": "observe_only",
            "timed_out": False,
            "lock_busy": summary.pending_tasks > 0,
        }

    def format_extra_status_lines(
        self,
        *,
        rows: list[dict[str, Any]],
        summary: BackfillSummary,
        scope: dict[str, str],
        run_result: dict[str, Any],
        status: Any,
    ) -> list[str]:
        del rows, scope, status
        return [
            f"status_path={self.status_path}",
            f"run_status={run_result.get('status', '')}",
            f"parsed_or_empty={summary.success_tasks}",
            f"parse_error={summary.failed_tasks}",
            f"pending={summary.pending_tasks}",
            f"target_price_rows={summary.total_rows_written}",
        ]


def run_stock_report_pdf_backfill_watchdog(
    *,
    output_dir: str | Path,
    stale_after_minutes: int = 30,
    run_timeout_seconds: int = 60,
    max_jobs: int = 0,
    workers: int = 0,
    report_target: str,
    report_account: str = "jarvis",
    openclaw_bin: str = "openclaw",
    report_dry_run: bool = False,
) -> dict[str, Any]:
    adapter = StockReportPdfBackfillWatchdogAdapter(output_dir=output_dir)
    result = run_watchdog_once(
        adapter=adapter,
        stale_after_minutes=stale_after_minutes,
        run_timeout_seconds=run_timeout_seconds,
        max_jobs=max_jobs,
        workers=workers,
        send_message=None,
    )
    if should_send_watchdog_message(result["status"]) and not report_dry_run:
        send_openclaw_feishu_message(
            message=result["message"],
            target=report_target,
            account=report_account,
            openclaw_bin=openclaw_bin,
            dry_run=report_dry_run,
        )
    return result


def fetch_pdf_text(url: str, *, timeout: int = 20, max_pages: int = 8) -> str:
    if PdfReader is None:
        raise RuntimeError("pypdf is required for PDF text extraction")
    parsed = urlparse(str(url))
    if parsed.scheme == "file" or (not parsed.scheme and Path(str(url)).exists()):
        local_path = Path(unquote(parsed.path)) if parsed.scheme == "file" else Path(str(url))
        reader = PdfReader(str(local_path))
        parts = []
        for page in reader.pages[:max_pages]:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise ValueError("response is not a PDF")
    reader = PdfReader(BytesIO(response.content))
    parts = []
    for page in reader.pages[:max_pages]:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def extract_stock_report_pdf_fields(text: str) -> dict[str, Any]:
    compact = _compact(text)
    target_price, method, confidence = _extract_target_price(compact)
    rating_change_type, rating_pdf = _extract_rating(compact)
    eps_values = _extract_number_sequence(compact, [r"(?:EPS|每股收益)(?:分别为|为|：|:)?([0-9]+(?:\.[0-9]+)?(?:[/、,，][0-9]+(?:\.[0-9]+)?){1,4})"])
    pe_values = _extract_number_sequence(compact, [r"(?:PE|市盈率)(?:分别为|为|：|:)?([0-9]+(?:\.[0-9]+)?(?:[/、,，][0-9]+(?:\.[0-9]+)?){1,4})"])
    risk_summary = _extract_risk_summary(compact)
    analyst = _extract_first(compact, [r"(?:分析师|研究员)[:：]?([\u4e00-\u9fa5]{2,4})"])
    return {
        "pdf_text_extract_chars": len(compact),
        "has_target_keyword": any(word in compact for word in ["目标价", "目标价格", "目标价位", "合理价值", "合理价格", "合理估值"]),
        "target_price": target_price,
        "target_price_confidence": confidence,
        "target_price_extract_method": method,
        "rating_pdf": rating_pdf,
        "rating_change_type": rating_change_type,
        "forecast_eps_values": eps_values,
        "forecast_pe_values": pe_values,
        "has_profit_forecast": any(word in compact for word in ["盈利预测", "归母净利润", "营业收入", "每股收益", "EPS"]),
        "has_risk_section": bool(risk_summary),
        "risk_summary": risk_summary,
        "analyst_pdf": analyst,
        "pdf_extract_version": "pdf_field_v1",
    }


def upsert_stock_report_pdf_fields(
    fields: pd.DataFrame,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    parsed = fields[fields.get("status", "").astype(str).eq("parsed")].copy() if not fields.empty else fields
    rows = []
    for row in parsed.to_dict("records"):
        report_id = _safe_text(row.get("report_id"))
        if not report_id:
            continue
        metadata = {
            "status": row.get("status"),
            "pdf_extract_version": row.get("pdf_extract_version"),
            "pdf_text_extract_chars": _safe_int(row.get("pdf_text_extract_chars")),
            "target_price_confidence": _safe_float(row.get("target_price_confidence")),
            "target_price_extract_method": row.get("target_price_extract_method") or "",
            "rating_pdf": row.get("rating_pdf") or "",
            "forecast_eps_values": _json_list(row.get("forecast_eps_values")),
            "forecast_pe_values": _json_list(row.get("forecast_pe_values")),
            "has_profit_forecast": bool(row.get("has_profit_forecast", False)),
            "has_risk_section": bool(row.get("has_risk_section", False)),
            "analyst_pdf": row.get("analyst_pdf") or "",
        }
        rows.append(
            (
                _blank_to_none(row.get("target_price")),
                _blank_to_none(row.get("target_upside")),
                row.get("rating_change_type") or "",
                row.get("risk_summary") or "",
                json.dumps({"pdf_extract": metadata}, ensure_ascii=False),
                report_id,
            )
        )
    with connect(service) as conn:
        for params in rows:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE research.stock_report_event
                    SET
                        target_price = COALESCE(%s, target_price),
                        target_upside = COALESCE(%s, target_upside),
                        rating_change = CASE WHEN %s <> '' THEN %s ELSE rating_change END,
                        risk_summary = CASE WHEN %s <> '' THEN %s ELSE risk_summary END,
                        metadata = research.stock_report_event.metadata || %s::jsonb,
                        updated_at = now()
                    WHERE report_id = %s
                    """,
                    (params[0], params[1], params[2], params[2], params[3], params[3], params[4], params[5]),
                )
    return {"updated_rows": len(rows)}


def summarize_pdf_field_backfill(fields: pd.DataFrame) -> pd.DataFrame:
    parsed = fields[fields.get("status", "").astype(str).eq("parsed")].copy() if not fields.empty else fields
    rows = []
    for field in [
        "has_target_keyword",
        "target_price",
        "rating_pdf",
        "rating_change_type",
        "forecast_eps_values",
        "forecast_pe_values",
        "has_profit_forecast",
        "has_risk_section",
        "risk_summary",
        "analyst_pdf",
    ]:
        if field not in fields.columns:
            count = 0
        elif field.startswith("has_"):
            count = int(parsed[field].fillna(False).astype(bool).sum())
        else:
            count = int(parsed[field].map(_has_value).sum())
        rows.append(
            {
                "field": field,
                "parsed_count": int(len(parsed)),
                "hit_count": count,
                "hit_rate": count / len(parsed) if len(parsed) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def render_pdf_field_backfill_report(fields: pd.DataFrame, summary: pd.DataFrame) -> str:
    status_summary = fields["status"].value_counts().rename_axis("status").reset_index(name="count") if "status" in fields else pd.DataFrame()
    lines = [
        "# Stock Report PDF Field Backfill",
        "",
        "## Status",
        status_summary.to_markdown(index=False) if not status_summary.empty else "No rows.",
        "",
        "## Field Hit Summary",
        summary.to_markdown(index=False) if not summary.empty else "No rows.",
        "",
        "## Notes",
        "- PDF text is not stored.",
        "- Extracted fields are structural metadata only.",
        "- target_upside is only populated when a separate PIT price layer provides it.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _initial_pdf_status_frame(sources: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for idx, row in sources.reset_index(drop=True).iterrows():
        rows.append(
            {
                "sample_id": idx + 1,
                "report_id": _safe_text(row.get("report_id")),
                "source_url": _safe_text(row.get("source_url")),
                "broker": _safe_text(row.get("broker")),
                "analyst": _safe_text(row.get("analyst")),
                "report_title": _safe_text(row.get("report_title")),
                "publish_date": _safe_text(row.get("publish_date")),
                "status": "pending",
                "error_type": "",
                "error_message": "",
            }
        )
    return pd.DataFrame(rows)


def _merge_existing_pdf_status(base: pd.DataFrame, existing: pd.DataFrame) -> pd.DataFrame:
    if base.empty or existing.empty or "report_id" not in base.columns or "report_id" not in existing.columns:
        return base
    result = pd.DataFrame(base.fillna("").to_dict("records"), dtype=object)
    existing_latest = existing.dropna(subset=["report_id"]).drop_duplicates(subset=["report_id"], keep="last")
    existing_by_report = existing_latest.set_index("report_id").to_dict("index")
    for idx, row in result.iterrows():
        report_id = _safe_text(row.get("report_id"))
        if report_id not in existing_by_report:
            continue
        existing_row = existing_by_report[report_id]
        for column, value in existing_row.items():
            if column not in result.columns:
                result[column] = pd.Series([""] * len(result), index=result.index, dtype=object)
            result.at[idx, column] = value
    return result.fillna("")


def _status_frame_from_rows(status_frame: pd.DataFrame, rows_by_report: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    columns = list(status_frame.columns)
    for column in [
        "pdf_text_extract_chars",
        "has_target_keyword",
        "target_price",
        "target_price_confidence",
        "target_price_extract_method",
        "rating_pdf",
        "rating_change_type",
        "forecast_eps_values",
        "forecast_pe_values",
        "has_profit_forecast",
        "has_risk_section",
        "risk_summary",
        "analyst_pdf",
        "pdf_extract_version",
    ]:
        if column not in columns:
            columns.append(column)
    for _, row in status_frame.iterrows():
        report_id = _safe_text(row.get("report_id"))
        merged = dict(row)
        merged.update(rows_by_report.get(report_id, {}))
        rows.append(merged)
    return pd.DataFrame(rows, columns=columns).fillna("")


def _write_pdf_status(status_frame: pd.DataFrame, status_path: Path | None) -> None:
    if status_path is None:
        return
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_frame.to_csv(status_path, index=False)


def _extract_target_price(text: str) -> tuple[float | None, str, float]:
    range_patterns = [
        ("reasonable_value_range_regex", 0.70, r"合理(?:估值|价值|价格)([0-9]{1,4}(?:\.[0-9]{1,2})?)[-~－—至]([0-9]{1,4}(?:\.[0-9]{1,2})?)元"),
        ("target_price_range_regex", 0.75, r"目标价(?:格|位)?(?:为|至|：|:)?([0-9]{1,4}(?:\.[0-9]{1,2})?)[-~－—至]([0-9]{1,4}(?:\.[0-9]{1,2})?)元"),
    ]
    for method, confidence, pattern in range_patterns:
        match = re.search(pattern, text)
        if match:
            low = float(match.group(1))
            high = float(match.group(2))
            return round((low + high) / 2, 4), method, confidence
    patterns = [
        ("target_price_table_regex", 0.80, r"目标价[（(]元[）)]([0-9]{1,4}(?:\.[0-9]{1,2})?)"),
        ("target_price_regex", 0.80, r"目标价(?:格|位)?(?:为|至|：|:)?([0-9]{1,4}(?:\.[0-9]{1,2})?)元"),
        ("target_price_regex", 0.75, r"目标价(?:格|位)?([0-9]{1,4}(?:\.[0-9]{1,2})?)"),
        ("reasonable_value_regex", 0.70, r"合理(?:估值|价值|价格)(?:为|至|：|:)?([0-9]{1,4}(?:\.[0-9]{1,2})?)元"),
        ("reasonable_value_regex", 0.65, r"合理(?:价值|价格)(?:为|至|：|:)?([0-9]{1,4}(?:\.[0-9]{1,2})?)元"),
    ]
    for method, confidence, pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1)), method, confidence
    return None, "", 0.0


def _extract_rating(text: str) -> tuple[str, str]:
    rating_words = "强烈推荐|买入|增持|推荐|持有|中性|减持|卖出"
    change_match = re.search(r"(首次覆盖|首次|维持|上调|下调|调高|调低).{0,12}?(" + rating_words + ")", text)
    if change_match:
        change = "首次覆盖" if change_match.group(1) == "首次" else change_match.group(1)
        return change, change_match.group(2)
    rating_match = re.search(r"(" + rating_words + ")评级?", text)
    return "", rating_match.group(1) if rating_match else ""


def _extract_number_sequence(text: str, patterns: list[str]) -> list[float]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        values = re.split(r"[/、,，]", match.group(1))
        return [float(value) for value in values if value]
    return []


def _extract_risk_summary(text: str) -> str:
    match = re.search(r"风险提示[:：]?(.{8,120})", text)
    if not match:
        return ""
    summary = match.group(1)
    stop = re.search(r"(公司基本情况|盈利预测|投资建议|免责声明|评级说明)", summary)
    if stop:
        summary = summary[: stop.start()]
    return summary[:120]


def _extract_first(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _has_value(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value)
    if value is None:
        return False
    if pd.isna(value):
        return False
    return str(value).strip() not in {"", "[]", "nan", "None"}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None or pd.isna(value):
        return []
    if isinstance(value, str) and value.startswith("["):
        try:
            loaded = json.loads(value)
            return loaded if isinstance(loaded, list) else []
        except Exception:
            return []
    return []


def _safe_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _safe_float(value: Any) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def _safe_int(value: Any) -> int:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return 0 if pd.isna(parsed) else int(parsed)


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if pd.isna(value):
        return None
    return value


def _empty_sources() -> pd.DataFrame:
    return pd.DataFrame(columns=["report_id", "source_url", "broker", "analyst", "report_title", "publish_date"])
