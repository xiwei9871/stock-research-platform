from __future__ import annotations

from pathlib import Path
from typing import Any

from stock_research.strategy_eod_publish import load_strategy_score_audit_summary


def load_strategy_score_audit_payload(
    *,
    trade_date: str,
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    try:
        summary = load_strategy_score_audit_summary(trade_date=trade_date, output_root=output_root)
    except FileNotFoundError:
        return _missing_payload(trade_date)

    payload = {
        "trade_date": str(summary.get("trade_date") or trade_date),
        "status": str(summary.get("status") or "success"),
        "summary_path": str(summary.get("summary_path") or ""),
        "detail_path": str(summary.get("detail_path") or ""),
        "total_rows": int(summary.get("total_rows") or 0),
        "selected_rows": int(summary.get("selected_rows") or 0),
        "anomaly_row_count": int(summary.get("anomaly_row_count") or 0),
        "anomaly_counts_by_type": _dict_of_ints(summary.get("anomaly_counts_by_type")),
        "strategies": _strategy_summaries(summary.get("strategies")),
        "warnings": _warnings(summary),
    }
    if summary.get("error"):
        payload["error"] = str(summary.get("error") or "")
    payload["overall_status"] = _overall_status(payload)
    return payload


def _missing_payload(trade_date: str) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "status": "missing",
        "overall_status": "missing",
        "summary_path": "",
        "detail_path": "",
        "total_rows": 0,
        "selected_rows": 0,
        "anomaly_row_count": 0,
        "anomaly_counts_by_type": {},
        "strategies": [],
        "warnings": [f"strategy score audit artifact not found for trade_date {trade_date}"],
    }


def _overall_status(payload: dict[str, Any]) -> str:
    if payload["status"] == "missing":
        return "missing"
    if payload["status"] == "failed":
        return "warning"
    if payload["anomaly_row_count"] > 0:
        return "warning"
    return "ok"


def _warnings(summary: dict[str, Any]) -> list[str]:
    error = str(summary.get("error") or "")
    if error:
        return [error]
    anomaly_row_count = int(summary.get("anomaly_row_count") or 0)
    if anomaly_row_count > 0:
        return [f"{anomaly_row_count} audited rows have anomalies"]
    return []


def _dict_of_ints(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(count or 0) for key, count in value.items()}


def _strategy_summaries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
