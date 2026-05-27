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


def write_watchlist_diagnostics_report(
    *,
    full_rows: pd.DataFrame,
    must_watch_rows: pd.DataFrame,
    output_dir: str | Path,
    output_version: str = "v1",
    trade_date: str | None = None,
    watchlist_id: str | None = None,
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    trade_date, watchlist_id = _resolve_diagnostics_identity(
        full_rows=full_rows,
        must_watch_rows=must_watch_rows,
        trade_date=trade_date,
        watchlist_id=watchlist_id,
    )
    base = f"watchlist_diagnostics_{trade_date}_{watchlist_id}_{output_version}"

    full_csv_path = path / f"{base}.csv"
    markdown_path = path / f"{base}.md"
    must_watch_csv_path = path / f"watchlist_diagnostics_must_watch_{trade_date}_{watchlist_id}_{output_version}.csv"

    full_rows.to_csv(full_csv_path, index=False)
    must_watch_rows.to_csv(must_watch_csv_path, index=False)
    markdown_path.write_text(
        _watchlist_diagnostics_markdown(
            full_rows,
            must_watch_rows,
            trade_date=trade_date,
            watchlist_id=watchlist_id,
        ),
        encoding="utf-8",
    )

    return {
        "markdown_path": str(markdown_path),
        "full_csv_path": str(full_csv_path),
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
                        _markdown_cell(row.get("asset_id")),
                        _markdown_cell(row.get("stock_code")),
                        _markdown_cell(row.get("stock_name")),
                        _markdown_cell(row.get("priority")),
                        _markdown_cell(_format_score(row.get("signal_score"))),
                        _markdown_cell(row.get("primary_signal")),
                        _markdown_cell(_format_list(row.get("signal_tags"))),
                        _markdown_cell(_format_list(row.get("risk_tags"))),
                    ]
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _watchlist_diagnostics_markdown(
    diagnostics_rows: pd.DataFrame,
    must_watch_rows: pd.DataFrame,
    *,
    trade_date: str,
    watchlist_id: str,
) -> str:
    lines = [
        f"# Watchlist Diagnostics {trade_date}",
        "",
        f"- Watchlist: `{watchlist_id}`",
        f"- Trade date: `{trade_date}`",
        "",
    ]

    grouped_rows = {
        "Risk Watch": [],
        "Opportunity Watch": [],
    }
    for row in must_watch_rows.to_dict("records"):
        grouped_rows[_diagnostic_group(row)].append(row)

    for title in ("Risk Watch", "Opportunity Watch"):
        rows = grouped_rows[title]
        lines.extend([f"## {title}", ""])
        if not rows:
            lines.append("No rows.")
            lines.append("")
            continue
        lines.append("| Asset | Name | Priority | Structure | Dragon | Case | LHB | Regime | Industry | Reason | Risk | Opportunity |")
        lines.append("| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_cell(row.get("asset_id")),
                        _markdown_cell(row.get("stock_name") or row.get("asset_id")),
                        _markdown_cell(row.get("watch_priority")),
                        _markdown_cell(row.get("event_structure")),
                        _markdown_cell(_format_dragon_context(row)),
                        _markdown_cell(_format_case_context(row)),
                        _markdown_cell(_format_lhb_context(row)),
                        _markdown_cell(_format_regime_context(row)),
                        _markdown_cell(_format_industry_context(row)),
                        _markdown_cell(row.get("diagnostic_reason")),
                        _markdown_cell(row.get("risk_note")),
                        _markdown_cell(row.get("opportunity_note")),
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


def _diagnostic_group(row: dict[str, Any]) -> str:
    if row.get("watch_group") == "opportunity_watch":
        return "Opportunity Watch"
    return "Risk Watch"


def _format_dragon_context(row: dict[str, Any]) -> str:
    parts: list[str] = []
    if row.get("dragon_trade_date"):
        parts.append(_display_date(row.get("dragon_trade_date")))
    if row.get("entry_window_v2"):
        parts.append(_string_value(row.get("entry_window_v2")))
    elif row.get("entry_window"):
        parts.append(_string_value(row.get("entry_window")))
    return " / ".join(parts)


def _format_case_context(row: dict[str, Any]) -> str:
    parts: list[str] = []
    if row.get("case_event_date"):
        parts.append(_display_date(row.get("case_event_date")))
    if row.get("case_event_type"):
        parts.append(_string_value(row.get("case_event_type")))
    return " / ".join(parts)


def _format_lhb_context(row: dict[str, Any]) -> str:
    parts: list[str] = []
    if row.get("lhb_event_date"):
        parts.append(_display_date(row.get("lhb_event_date")))
    if row.get("lhb_risk_level"):
        parts.append(_string_value(row.get("lhb_risk_level")))
    return " / ".join(parts)


def _format_regime_context(row: dict[str, Any]) -> str:
    parts: list[str] = []
    if row.get("market_regime"):
        parts.append(_string_value(row.get("market_regime")))
    if row.get("market_risk_level"):
        parts.append(_string_value(row.get("market_risk_level")))
    return " / ".join(parts)


def _format_industry_context(row: dict[str, Any]) -> str:
    parts: list[str] = []
    if row.get("industry_name"):
        parts.append(_string_value(row.get("industry_name")))
    if row.get("mainline_flag") in {True, False}:
        parts.append("mainline" if bool(row.get("mainline_flag")) else "non-mainline")
    return " / ".join(parts)


def _validate_matching_report_identity(diagnostics_rows: pd.DataFrame, must_watch_rows: pd.DataFrame) -> None:
    if must_watch_rows.empty:
        return
    mismatches: list[str] = []
    for column in ("trade_date", "watchlist_id"):
        diagnostics_values = _report_identity_values(diagnostics_rows, column, keep_missing=True)
        must_watch_values = _report_identity_values(must_watch_rows, column, keep_missing=True)
        if diagnostics_values != must_watch_values:
            mismatches.append(
                f"{column}: diagnostics={diagnostics_values or ['<missing>']} "
                f"must_watch={must_watch_values or ['<missing>']}"
            )
    if mismatches:
        raise ValueError(
            "watchlist diagnostics report requires matching trade_date and watchlist_id; "
            + "; ".join(mismatches)
        )


def _resolve_diagnostics_identity(
    *,
    full_rows: pd.DataFrame,
    must_watch_rows: pd.DataFrame,
    trade_date: str | None,
    watchlist_id: str | None,
) -> tuple[str, str]:
    if not full_rows.empty:
        _validate_matching_report_identity(full_rows, must_watch_rows)
        return _report_value(full_rows, "trade_date"), _report_value(full_rows, "watchlist_id")
    if not trade_date or not watchlist_id:
        raise ValueError(
            "watchlist diagnostics report requires non-empty full_rows or explicit trade_date and watchlist_id"
        )
    return trade_date, watchlist_id


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
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value)


def _display_date(value: Any) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if value is None:
        return ""
    try:
        return pd.Timestamp(value).date().isoformat()
    except Exception:
        return _string_value(value)


def _markdown_cell(value: Any) -> str:
    return _string_value(value).replace("|", r"\|").replace("\n", "<br>")


def _report_value(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        raise ValueError(f"watchlist report requires a non-empty {column}")
    if any(not _identity_string(value) for value in frame[column].tolist()):
        raise ValueError(f"watchlist report requires a non-empty {column}")
    values = _report_identity_values(frame, column)
    if not values:
        raise ValueError(f"watchlist report requires a non-empty {column}")
    if len(values) > 1:
        raise ValueError(f"watchlist report requires a single {column}")
    return values[0]


def _report_identity_values(frame: pd.DataFrame, column: str, *, keep_missing: bool = False) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    values: list[str] = []
    for value in frame[column].tolist():
        normalized = _identity_string(value)
        token = normalized if normalized else ("<missing>" if keep_missing else "")
        if not token:
            continue
        if token not in values:
            values.append(token)
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
    if isinstance(normalized, pd.Timestamp):
        return normalized.date().isoformat()
    if isinstance(normalized, datetime):
        return normalized.date().isoformat()
    if isinstance(normalized, date):
        return normalized.isoformat()
    return str(normalized)
