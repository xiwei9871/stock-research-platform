import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd


def write_watchlist_report(
    signal_rows: pd.DataFrame,
    *,
    output_dir: str | Path,
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    trade_date = _report_value(signal_rows, "trade_date")
    watchlist_id = _report_value(signal_rows, "watchlist_id")
    base = f"watchlist_report_{trade_date}_{watchlist_id}"

    normalized = signal_rows.copy()
    normalized["signal_tags"] = normalized["signal_tags"].map(
        lambda value: json.dumps(_json_safe_value(value or []), ensure_ascii=False, sort_keys=True)
    )
    normalized["risk_tags"] = normalized["risk_tags"].map(
        lambda value: json.dumps(_json_safe_value(value or []), ensure_ascii=False, sort_keys=True)
    )
    normalized["reason_json"] = normalized["reason_json"].map(
        lambda value: json.dumps(_json_safe_value(value or {}), ensure_ascii=False, sort_keys=True)
    )

    markdown_path = path / f"{base}.md"
    json_path = path / f"{base}.json"
    signals_csv_path = path / f"watchlist_signals_{trade_date}_{watchlist_id}.csv"
    must_watch_csv_path = path / f"must_watch_{trade_date}_{watchlist_id}.csv"

    normalized.to_csv(signals_csv_path, index=False)
    normalized[normalized["must_watch"]].to_csv(must_watch_csv_path, index=False)
    json_rows = []
    for raw_record, normalized_record in zip(signal_rows.to_dict("records"), normalized.to_dict("records")):
        json_record = {
            key: _json_safe_value(value)
            for key, value in raw_record.items()
        }
        json_record["signal_tags"] = normalized_record.get("signal_tags")
        json_record["risk_tags"] = normalized_record.get("risk_tags")
        json_record["reason_json"] = normalized_record.get("reason_json")
        json_rows.append(json_record)
    json_path.write_text(
        json.dumps(json_rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_watchlist_markdown(signal_rows), encoding="utf-8")

    return {
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "signals_csv_path": str(signals_csv_path),
        "must_watch_csv_path": str(must_watch_csv_path),
    }


def _watchlist_markdown(signal_rows: pd.DataFrame) -> str:
    if signal_rows.empty:
        raise ValueError("watchlist report requires at least one row")

    trade_date = _report_value(signal_rows, "trade_date")
    watchlist_id = _report_value(signal_rows, "watchlist_id")
    lines = [
        f"# Watchlist Report {trade_date}",
        "",
        f"- Watchlist: `{watchlist_id}`",
        f"- Trade date: `{trade_date}`",
        "",
    ]

    records = signal_rows.to_dict("records")
    grouped_rows = {
        "Must Watch": [],
        "Candidate": [],
        "Risk Excluded": [],
    }
    for row in records:
        grouped_rows[_report_group(row)].append(row)

    for title in ("Must Watch", "Candidate", "Risk Excluded"):
        rows = grouped_rows[title]
        lines.extend([f"## {title}", ""])
        if not rows:
            lines.append("No rows.")
            lines.append("")
            continue
        lines.append("| Asset | Code | Name | Priority | Score | Primary | Tags | Risks |")
        lines.append("| --- | --- | --- | ---: | ---: | --- | --- | --- |")
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _string_value(row.get("asset_id")),
                        _string_value(row.get("stock_code")),
                        _string_value(row.get("stock_name")),
                        _string_value(row.get("priority")),
                        _format_score(row.get("signal_score")),
                        _string_value(row.get("primary_signal")),
                        _format_list(row.get("signal_tags")),
                        _format_list(row.get("risk_tags")),
                    ]
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _report_group(row: dict[str, Any]) -> str:
    if bool(row.get("must_watch")):
        return "Must Watch"
    risk_tags = row.get("risk_tags") or []
    if "risk_excluded" in risk_tags:
        return "Risk Excluded"
    return "Candidate"


def _primary_signal(row: dict[str, Any]) -> str:
    value = row.get("primary_signal")
    return str(value or "neutral")


def _format_list(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(_string_value(item) for item in value)
    return _string_value(value)


def _format_score(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return _string_value(value)


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _report_value(frame: pd.DataFrame, column: str) -> str:
    values = _report_identity_values(frame, column)
    if not values:
        raise ValueError(f"watchlist report requires a non-empty {column}")
    if len(values) > 1:
        raise ValueError(f"watchlist report requires a single {column}")
    return values[0]


def _report_identity_values(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    values: list[str] = []
    for value in frame[column].tolist():
        normalized = _identity_string(value)
        if normalized and normalized not in values:
            values.append(normalized)
    return values


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            item = value.item()
        except Exception:
            return value
        return _json_safe_value(item)
    return value


def _identity_string(value: Any) -> str:
    normalized = _json_safe_value(value)
    if normalized is None:
        return ""
    return str(normalized)
