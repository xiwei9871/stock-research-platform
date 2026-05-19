import json
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

    normalized = signal_rows.copy()
    normalized["signal_tags"] = normalized["signal_tags"].map(
        lambda value: json.dumps(value or [], ensure_ascii=False, sort_keys=True)
    )
    normalized["risk_tags"] = normalized["risk_tags"].map(
        lambda value: json.dumps(value or [], ensure_ascii=False, sort_keys=True)
    )
    normalized["reason_json"] = normalized["reason_json"].map(
        lambda value: json.dumps(value or {}, ensure_ascii=False, sort_keys=True)
    )

    trade_date = _report_value(signal_rows, "trade_date")
    watchlist_id = _report_value(signal_rows, "watchlist_id")
    base = f"watchlist_report_{trade_date}_{watchlist_id}"

    markdown_path = path / f"{base}.md"
    json_path = path / f"{base}.json"
    signals_csv_path = path / f"watchlist_signals_{trade_date}_{watchlist_id}.csv"
    must_watch_csv_path = path / f"must_watch_{trade_date}_{watchlist_id}.csv"

    normalized.to_csv(signals_csv_path, index=False)
    normalized[normalized["must_watch"]].to_csv(must_watch_csv_path, index=False)
    json_path.write_text(normalized.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_watchlist_markdown(signal_rows), encoding="utf-8")

    return {
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "signals_csv_path": str(signals_csv_path),
        "must_watch_csv_path": str(must_watch_csv_path),
    }


def _watchlist_markdown(signal_rows: pd.DataFrame) -> str:
    trade_date = _report_value(signal_rows, "trade_date")
    watchlist_id = _report_value(signal_rows, "watchlist_id")
    lines = [
        f"# Watchlist Report {trade_date}",
        "",
        f"- Watchlist: `{watchlist_id}`",
        f"- Trade date: `{trade_date}`",
        "",
    ]

    sections = [
        ("Must Watch", lambda row: bool(row.get("must_watch"))),
        ("Candidate", lambda row: _primary_signal(row) == "candidate" and not bool(row.get("must_watch"))),
        ("Risk Excluded", lambda row: _is_risk_excluded(row)),
    ]

    records = signal_rows.to_dict("records")
    for title, predicate in sections:
        rows = [row for row in records if predicate(row)]
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


def _is_risk_excluded(row: dict[str, Any]) -> bool:
    risk_tags = row.get("risk_tags") or []
    return "risk_excluded" in risk_tags or (not bool(row.get("must_watch")) and _primary_signal(row) != "candidate")


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
    if frame.empty or column not in frame.columns:
        return "unknown"
    value = frame.iloc[0].get(column)
    if value is None:
        return "unknown"
    return str(value)
