from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


DEFAULT_REPORTS_DIR = Path("/Users/xiwei/stock_research/reports")
DEFAULT_MIN_DAILY_ROWS = 15000
DEFAULT_MAX_DAILY_MISSING = 100
DEFAULT_MIN_MINUTE_ROWS = 1
DEFAULT_MIN_SCORE_ROWS = 3
DEFAULT_MIN_WATCHLIST_ROWS = 1
DEFAULT_MIN_REPORTS = 1
DEFAULT_EXTERNAL_DATA_MAX_QUALITY_GAP_RATIO = 0.01


CHECK_SQL = {
    "daily_quality": """
        SELECT
          status,
          expected_count,
          actual_count,
          jsonb_array_length(missing_symbols) AS missing_count,
          jsonb_array_length(abnormal_symbols) AS abnormal_count
        FROM ops.daily_pipeline_quality
        WHERE trade_date = %s
          AND dataset_name = 'daily_bar'
        ORDER BY updated_at DESC
        LIMIT 1
    """,
    "minute5_quality": """
        SELECT
          status,
          expected_count,
          actual_count,
          jsonb_array_length(missing_symbols) AS missing_count,
          jsonb_array_length(abnormal_symbols) AS abnormal_count
        FROM ops.daily_pipeline_quality
        WHERE trade_date = %s
          AND dataset_name = 'minute5_bar'
        ORDER BY updated_at DESC
        LIMIT 1
    """,
    "deps_job": """
        SELECT status
        FROM ops.daily_pipeline_job
        WHERE trade_date = %s
          AND stage = 'deps'
        ORDER BY updated_at DESC
        LIMIT 1
    """,
    "health_status": """
        SELECT pipeline_status, latest_ready_trade_date::text AS latest_ready_trade_date
        FROM ops.daily_pipeline_status
        WHERE trade_date = %s
        ORDER BY updated_at DESC
        LIMIT 1
    """,
    "score_count": """
        SELECT count(*)::int AS count
        FROM factor.stock_score_daily
        WHERE trade_date = %s
          AND score_version = %(score_version)s
    """,
    "nonzero_score_count": """
        SELECT count(*)::int AS count
        FROM factor.stock_score_daily
        WHERE trade_date = %s
          AND score_version = %(score_version)s
          AND COALESCE(score_total, 0) <> 0
    """,
    "watchlist_count": """
        SELECT count(*)::int AS count
        FROM watchlist.watchlist_daily_signal
        WHERE trade_date = %s
          AND watchlist_id = %(watchlist_id)s
    """,
    "diagnostics_count": """
        SELECT count(*)::int AS count
        FROM watchlist.watchlist_daily_signal
        WHERE trade_date = %s
          AND watchlist_id = 'diagnostics'
    """,
}


def run_platform_ready_check(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
    score_version: str = "manual_v1",
    watchlist_id: str = "default",
    reports_dirs: list[str | Path] | None = None,
    min_daily_rows: int = DEFAULT_MIN_DAILY_ROWS,
    max_daily_missing: int = DEFAULT_MAX_DAILY_MISSING,
    min_minute_rows: int = DEFAULT_MIN_MINUTE_ROWS,
    min_score_rows: int = DEFAULT_MIN_SCORE_ROWS,
    min_watchlist_rows: int = DEFAULT_MIN_WATCHLIST_ROWS,
    min_reports: int = DEFAULT_MIN_REPORTS,
    allow_degraded_minute5: bool = False,
    external_data_max_quality_gap_ratio: float = DEFAULT_EXTERNAL_DATA_MAX_QUALITY_GAP_RATIO,
    daily_max_quality_gap_ratio: float | None = None,
    minute5_max_quality_gap_ratio: float | None = None,
) -> dict[str, Any]:
    daily_gap_ratio = external_data_max_quality_gap_ratio if daily_max_quality_gap_ratio is None else daily_max_quality_gap_ratio
    minute5_gap_ratio = (
        external_data_max_quality_gap_ratio
        if minute5_max_quality_gap_ratio is None
        else minute5_max_quality_gap_ratio
    )
    checks = [
        _check_daily_quality(service, trade_date, min_daily_rows, max_daily_missing, daily_gap_ratio),
        _check_minute5(service, trade_date, min_minute_rows, max_gap_ratio=minute5_gap_ratio),
        _check_deps(service, trade_date),
        _check_health(service, trade_date, allow_degraded=allow_degraded_minute5),
        _check_scores(service, trade_date, score_version, min_score_rows),
        _check_nonzero_scores(service, trade_date, score_version, min_score_rows),
        _check_watchlist(service, trade_date, watchlist_id, min_watchlist_rows),
        _check_diagnostics(service, trade_date, min_watchlist_rows),
        _check_reports(trade_date, reports_dirs or [DEFAULT_REPORTS_DIR], min_reports),
    ]
    status = "ready" if all(item["status"] == "pass" for item in checks) else "not_ready"
    if status == "ready" and any(item.get("degraded") for item in checks):
        status = "degraded_ready"
    return {"trade_date": trade_date, "status": status, "checks": checks}


def render_platform_ready_message(result: dict[str, Any]) -> str:
    lines = [
        f"平台数据状态：{result['status']}",
        f"交易日：{result['trade_date']}",
    ]
    for item in result.get("checks", []):
        lines.append(f"- {item['name']}: {item['status']} {item['detail']}")
    return "\n".join(lines)[:1800]


def _check_daily_quality(
    service: str,
    trade_date: str,
    min_rows: int,
    max_missing: int,
    max_gap_ratio: float,
) -> dict[str, Any]:
    rows = _fetch_check_rows(service, "daily_quality", trade_date)
    if not rows:
        return _fail("daily_bar", "missing daily quality row")
    return _check_external_quality_row(
        name="daily_bar",
        row=rows[0],
        min_rows=min_rows,
        max_gap_ratio=max_gap_ratio,
        max_missing=max_missing,
    )


def _check_minute5(service: str, trade_date: str, min_rows: int, *, max_gap_ratio: float) -> dict[str, Any]:
    rows = _fetch_check_rows(service, "minute5_quality", trade_date)
    if not rows:
        return _fail("minute5", "missing minute5 quality row")
    return _check_external_quality_row(
        name="minute5",
        row=rows[0],
        min_rows=min_rows,
        max_gap_ratio=max_gap_ratio,
    )


def _check_external_quality_row(
    *,
    name: str,
    row: dict[str, Any],
    min_rows: int,
    max_gap_ratio: float,
    max_missing: int | None = None,
) -> dict[str, Any]:
    actual = int(row.get("actual_count") or 0)
    expected = int(row.get("expected_count") or 0)
    missing = int(row.get("missing_count") or 0)
    abnormal = int(row.get("abnormal_count") or 0)
    gap = missing + abnormal
    gap_ratio = gap / expected if expected else 1.0
    ok = actual >= min_rows and expected > 0 and gap_ratio <= max_gap_ratio
    if max_missing is not None:
        ok = ok and missing <= max_missing
    detail = (
        f"status={row.get('status')} actual={actual} expected={expected} "
        f"missing={missing} abnormal={abnormal} gap_ratio={gap_ratio:.4f} "
        f"max_gap_ratio={max_gap_ratio:.4f}"
    )
    if max_missing is not None:
        detail += f" max_missing={max_missing}"
    if not ok:
        return _fail(name, detail)
    return _pass(name, detail, degraded=gap > 0)


def _check_deps(service: str, trade_date: str) -> dict[str, str]:
    rows = _fetch_check_rows(service, "deps_job", trade_date)
    status = str(rows[0].get("status") or "") if rows else ""
    return _pass("deps", f"status={status}") if status == "success" else _fail("deps", f"status={status or 'missing'}")


def _check_health(service: str, trade_date: str, *, allow_degraded: bool = False) -> dict[str, Any]:
    rows = _fetch_check_rows(service, "health_status", trade_date)
    if not rows:
        return _fail("health", "missing status row")
    row = rows[0]
    pipeline_status = str(row.get("pipeline_status") or "")
    latest_ready = str(row.get("latest_ready_trade_date") or "")
    ok = pipeline_status in {"READY", "DEGRADED_READY", "ready", "success"} and latest_ready == trade_date
    detail = f"pipeline_status={pipeline_status} latest_ready_trade_date={latest_ready}"
    if allow_degraded:
        return _pass("health", f"{detail} degraded_allowed=true", degraded=True)
    return _pass("health", detail) if ok else _fail("health", detail)


def _check_scores(service: str, trade_date: str, score_version: str, min_rows: int) -> dict[str, str]:
    rows = _fetch_check_rows(service, "score_count", trade_date, score_version=score_version)
    count = int(rows[0].get("count") or 0) if rows else 0
    detail = f"score_version={score_version} rows={count} required>={min_rows}"
    return _pass("scores", detail) if count >= min_rows else _fail("scores", detail)


def _check_nonzero_scores(service: str, trade_date: str, score_version: str, min_rows: int) -> dict[str, str]:
    rows = _fetch_check_rows(service, "nonzero_score_count", trade_date, score_version=score_version)
    count = int(rows[0].get("count") or 0) if rows else 0
    detail = f"score_version={score_version} nonzero_rows={count} required>={min_rows}"
    return _pass("nonzero_scores", detail) if count >= min_rows else _fail("nonzero_scores", detail)


def _check_watchlist(service: str, trade_date: str, watchlist_id: str, min_rows: int) -> dict[str, str]:
    rows = _fetch_check_rows(service, "watchlist_count", trade_date, watchlist_id=watchlist_id)
    count = int(rows[0].get("count") or 0) if rows else 0
    detail = f"watchlist_id={watchlist_id} rows={count} required>={min_rows}"
    return _pass("watchlist_default", detail) if count >= min_rows else _fail("watchlist_default", detail)


def _check_diagnostics(service: str, trade_date: str, min_rows: int) -> dict[str, str]:
    rows = _fetch_check_rows(service, "diagnostics_count", trade_date)
    count = int(rows[0].get("count") or 0) if rows else 0
    detail = f"watchlist_id=diagnostics rows={count} required>={min_rows}"
    return _pass("watchlist_diagnostics", detail) if count >= min_rows else _fail("watchlist_diagnostics", detail)


def _check_reports(trade_date: str, reports_dirs: list[str | Path], min_reports: int) -> dict[str, str]:
    count = 0
    for directory in reports_dirs:
        path = Path(directory)
        if not path.exists():
            continue
        count += sum(1 for item in path.rglob(f"*{trade_date}*") if item.is_file())
    detail = f"rows={count} required>={min_reports}"
    return _pass("reports", detail) if count >= min_reports else _fail("reports", detail)


def _fetch_check_rows(service: str, check_name: str, trade_date: str, **kwargs: Any) -> list[dict[str, Any]]:
    sql = CHECK_SQL[check_name]
    params: list[Any] | dict[str, Any]
    if "%(" in sql:
        params = {"score_version": kwargs.get("score_version"), "watchlist_id": kwargs.get("watchlist_id")}
        sql = sql.replace("%s", "%(trade_date)s")
        params["trade_date"] = trade_date
    else:
        params = [trade_date]
    with connect(service) as conn:
        return fetch_all(conn, sql, params)


def _pass(name: str, detail: str, *, degraded: bool = False) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "status": "pass", "detail": detail}
    if degraded:
        row["degraded"] = True
    return row


def _fail(name: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": "fail", "detail": detail}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--service", default=SETTINGS.research_service)
    parser.add_argument("--score-version", default="manual_v1")
    parser.add_argument("--watchlist-id", default="default")
    parser.add_argument("--reports-dir", action="append")
    parser.add_argument("--json-output")
    args = parser.parse_args(argv)

    result = run_platform_ready_check(
        args.trade_date,
        service=args.service,
        score_version=args.score_version,
        watchlist_id=args.watchlist_id,
        reports_dirs=args.reports_dir,
        min_daily_rows=int(os.getenv("PLATFORM_READY_MIN_DAILY_ROWS", DEFAULT_MIN_DAILY_ROWS)),
        max_daily_missing=int(os.getenv("PLATFORM_READY_MAX_DAILY_MISSING", DEFAULT_MAX_DAILY_MISSING)),
        min_minute_rows=int(os.getenv("PLATFORM_READY_MIN_MINUTE_ROWS", DEFAULT_MIN_MINUTE_ROWS)),
        min_score_rows=int(os.getenv("PLATFORM_READY_MIN_SCORE_ROWS", DEFAULT_MIN_SCORE_ROWS)),
        min_watchlist_rows=int(os.getenv("PLATFORM_READY_MIN_WATCHLIST_ROWS", DEFAULT_MIN_WATCHLIST_ROWS)),
        min_reports=int(os.getenv("PLATFORM_READY_MIN_REPORTS", DEFAULT_MIN_REPORTS)),
        allow_degraded_minute5=os.getenv("PLATFORM_READY_ALLOW_DEGRADED_MINUTE5", "").lower() in {"1", "true", "yes"},
        external_data_max_quality_gap_ratio=float(
            os.getenv("EXTERNAL_DATA_MAX_QUALITY_GAP_RATIO", str(DEFAULT_EXTERNAL_DATA_MAX_QUALITY_GAP_RATIO))
        ),
        daily_max_quality_gap_ratio=_optional_float_env("DAILY_MAX_QUALITY_GAP_RATIO"),
        minute5_max_quality_gap_ratio=_optional_float_env("MINUTE5_MAX_QUALITY_GAP_RATIO"),
    )
    if args.json_output:
        Path(args.json_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(render_platform_ready_message(result))
    return 0 if result["status"] in {"ready", "degraded_ready"} else 1


def _optional_float_env(name: str) -> float | None:
    value = os.getenv(name)
    return float(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
