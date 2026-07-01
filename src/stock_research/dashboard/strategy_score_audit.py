from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

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

    payload = dict(summary)
    payload["trade_date"] = str(payload.get("trade_date") or trade_date)
    payload["status"] = str(payload.get("status") or "success")
    payload["summary_path"] = str(payload.get("summary_path") or "")
    payload["detail_path"] = str(payload.get("detail_path") or "")
    payload["total_rows"] = int(payload.get("total_rows") or 0)
    payload["selected_rows"] = int(payload.get("selected_rows") or 0)
    payload["anomaly_row_count"] = int(payload.get("anomaly_row_count") or 0)
    payload["anomaly_counts_by_type"] = _dict_of_ints(payload.get("anomaly_counts_by_type"))
    payload["strategies"] = _strategy_summaries(payload.get("strategies"))
    payload["warnings"] = _warnings(payload)
    payload["sample_rows"] = _sample_rows(payload)
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
        "sample_rows": [],
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
    existing = summary.get("warnings")
    if isinstance(existing, list):
        return [str(item) for item in existing]
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


def _sample_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    existing = summary.get("sample_rows")
    if isinstance(existing, list):
        return [item for item in existing if isinstance(item, dict)]
    detail_path_text = str(summary.get("detail_path") or "")
    if not detail_path_text:
        return []
    detail_path = Path(detail_path_text)
    if not detail_path.exists():
        return []
    frame = pd.read_csv(detail_path, low_memory=False)
    if frame.empty:
        return []
    return [_normalize_sample_row(row) for row in frame.head(5).to_dict("records")]


def _normalize_sample_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if pd.isna(value):
            normalized[str(key)] = None
            continue
        if key == "anomaly_flags":
            normalized[str(key)] = _parse_json_list(value)
            continue
        normalized[str(key)] = value
    return normalized


def _parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None or pd.isna(value):
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
        return parsed if isinstance(parsed, list) else [parsed]
    return [value]
