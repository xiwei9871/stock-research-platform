from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any, Callable

from stock_research.eod_auto_repair_models import RepairActionResult, RepairStatus


def repair_minute5_bars(
    trade_date: str,
    *,
    workers: int = 1,
    max_jobs: int = 20_000,
    batch_size: int = 100,
    progress: Callable[[dict[str, Any]], None] | None = None,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    if int(workers) != 1:
        raise ValueError("Baostock minute backfill must use workers=1")
    remaining_budget = max(1, int(max_jobs))
    batch_limit = max(1, int(batch_size))
    totals = {"attempted": 0, "success": 0, "failed": 0, "rows": 0, "batches": 0}
    reset_stale_before_run = True
    while remaining_budget > 0:
        result = runner(
            start_date=trade_date,
            end_date=trade_date,
            freq="5min",
            adjust_types=["raw", "qfq"],
            workers=1,
            max_jobs=min(batch_limit, remaining_budget),
            retry_failed=True,
            reset_stale_before_run=reset_stale_before_run,
            progress=progress,
            progress_interval=100,
        )
        reset_stale_before_run = False
        totals["batches"] += 1
        attempted = int((result or {}).get("attempted") or 0)
        totals["attempted"] += attempted
        totals["success"] += int((result or {}).get("success") or 0)
        totals["failed"] += int((result or {}).get("failed") or 0)
        totals["rows"] += int((result or {}).get("rows") or 0)
        if attempted <= 0:
            break
        remaining_budget -= attempted
    return RepairActionResult(
        name="repair_minute5_bars",
        status=RepairStatus.SUCCESS,
        message="minute5 repair submitted",
        metrics=totals,
    )


def repair_minute5_raw_bars(
    trade_date: str,
    *,
    service: str,
    missing_symbols_loader: Callable[[str], list[str]],
    raw_fetcher: Callable[..., list[dict[str, Any]]],
    upserter: Callable[[str, list[dict[str, Any]]], int],
    qfq_deriver: Callable[[str, date], dict[str, int]],
    quality_refresher: Callable[[str, date], dict[str, Any]],
    timeout_seconds: int = 30,
    symbol_sleep_seconds: float = 0.0,
    progress: Callable[[dict[str, Any]], None] | None = None,
    quality_refresh_interval: int = 50,
) -> RepairActionResult:
    target_date = date.fromisoformat(trade_date)
    missing_symbols = list(missing_symbols_loader(trade_date))
    total = len(missing_symbols)

    def emit(event: str, completed: int, *, rows: int = 0, success: int = 0, failed: int = 0) -> None:
        if progress is None:
            return
        progress(
            {
                "event": event,
                "completed": completed,
                "total": total,
                "rows": rows,
                "success": success,
                "failed": failed,
            }
        )

    def refresh_quality_checkpoint(completed: int) -> None:
        if quality_refresh_interval <= 0 or completed % quality_refresh_interval != 0:
            return
        try:
            quality_refresher(service, target_date)
        except Exception:
            return

    emit("minute5_raw_repair_started", 0)
    rows_upserted = 0
    failed = 0
    success = 0
    for index, ts_code in enumerate(missing_symbols, start=1):
        try:
            rows = raw_fetcher(
                ts_code,
                start_date=target_date,
                end_date=target_date,
                timeout_seconds=timeout_seconds,
            )
        except Exception:  # noqa: BLE001 - repair action reports aggregate failures.
            failed += 1
            emit(
                "minute5_raw_repair_progress",
                index,
                rows=rows_upserted,
                success=success,
                failed=failed,
            )
            refresh_quality_checkpoint(index)
            continue
        raw_rows = [row for row in rows if row.get("adjust_type") == "raw"]
        if raw_rows:
            rows_upserted += int(upserter(service, raw_rows) or 0)
            success += 1
        else:
            failed += 1
        if symbol_sleep_seconds > 0:
            time.sleep(symbol_sleep_seconds)
        emit(
            "minute5_raw_repair_progress",
            index,
            rows=rows_upserted,
            success=success,
            failed=failed,
        )
        refresh_quality_checkpoint(index)

    qfq_result = qfq_deriver(service, target_date)
    quality = quality_refresher(service, target_date)
    raw_quality = quality.get("raw") if isinstance(quality.get("raw"), dict) else quality
    qfq_quality = quality.get("qfq") if isinstance(quality.get("qfq"), dict) else quality
    remaining_missing = len(raw_quality.get("missing_symbols") or [])
    remaining_abnormal = len(raw_quality.get("abnormal_symbols") or [])
    qfq_remaining_missing = len(qfq_quality.get("missing_symbols") or [])
    qfq_remaining_abnormal = len(qfq_quality.get("abnormal_symbols") or [])

    def quality_ready(value: dict[str, Any]) -> bool:
        quality_status = str(value.get("status") or "")
        if quality_status:
            return quality_status == "pass"
        expected_count = int(value.get("expected_count") or 0)
        actual_count = int(value.get("actual_count") or 0)
        return expected_count > 0 and actual_count > 0

    status = (
        RepairStatus.SUCCESS
        if quality_ready(raw_quality)
        and quality_ready(qfq_quality)
        and remaining_missing == 0
        and remaining_abnormal == 0
        and qfq_remaining_missing == 0
        and qfq_remaining_abnormal == 0
        else RepairStatus.FAILED
    )
    emit(
        "minute5_raw_repair_completed",
        total,
        rows=rows_upserted,
        success=success,
        failed=failed,
    )
    return RepairActionResult(
        name="repair_minute5_raw_bars",
        status=status,
        message=(
            "minute5 raw bars repaired"
            if status == RepairStatus.SUCCESS
            else "minute5 raw repair had no missing symbols to attempt"
            if not missing_symbols
            else "minute5 raw repair incomplete"
        ),
        metrics={
            "attempted": len(missing_symbols),
            "success": success,
            "failed": failed,
            "rows": int(rows_upserted or 0),
            "qfq_rows": int(qfq_result.get("inserted_rows") or 0),
            "remaining_missing": remaining_missing,
            "remaining_abnormal": remaining_abnormal,
        },
    )


def repair_lhb_source_and_features(
    trade_date: str,
    *,
    output_dir: str | Path,
    enrichment_runner: Callable[..., dict[str, Any]],
    feature_runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    out = Path(output_dir)
    enrichment_runner(
        dataset="lhb",
        start_date=trade_date,
        end_date=trade_date,
        output_dir=out / "free_enrichment_lhb",
        batch_size=1,
        sleep_seconds=0,
    )
    feature_result = feature_runner(
        start_date=trade_date,
        end_date=trade_date,
        ts_codes=None,
        output_dir=out,
    )
    paths = feature_result.get("paths") or {}
    artifact_paths = [str(value) for value in paths.values()]
    return RepairActionResult(
        name="repair_lhb_source_and_features",
        status=RepairStatus.SUCCESS,
        message="lhb source and features repaired",
        artifact_paths=artifact_paths,
    )


def repair_strategy_publish(
    trade_date: str,
    *,
    output_root: str | Path,
    publisher: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = publisher(trade_date=trade_date, output_root=output_root)
    output_dir = str(result.get("output_dir") or "")
    return RepairActionResult(
        name="repair_strategy_publish",
        status=RepairStatus.SUCCESS,
        message="strategy publish complete",
        metrics={"review_rows": int(result.get("review_rows") or 0)},
        artifact_paths=[output_dir] if output_dir else [],
    )


def repair_market_monitor(
    trade_date: str,
    *,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = runner(trade_date=trade_date)
    return RepairActionResult(
        name="repair_market_monitor",
        status=RepairStatus.SUCCESS,
        message="market monitor refreshed",
        metrics=dict(result or {}),
    )


def repair_technical_features(
    trade_date: str,
    *,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = runner(
        trade_date=trade_date,
        lookback_bars=260,
        adjust_type="hfq",
        build_strategy="latest_only",
    )
    return RepairActionResult(
        name="repair_technical_features",
        status=RepairStatus.SUCCESS,
        message="technical features rebuilt",
        metrics=dict(result or {}),
    )


def repair_score_topn(
    trade_date: str,
    *,
    output_dir: str | Path,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = runner(
        trade_date=trade_date,
        score_version="manual_v1",
        output_dir=output_dir,
    )
    return RepairActionResult(
        name="repair_score_topn",
        status=RepairStatus.SUCCESS,
        message="score topn rebuilt",
        metrics=dict(result or {}),
    )


def repair_factor_daily(
    trade_date: str,
    *,
    runner: Callable[..., Any],
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> RepairActionResult:
    result = runner(
        start_date=trade_date,
        end_date=trade_date,
        lookback_bars=130,
        industry_system="csrc",
        workers=1,
        skip_complete=False,
        progress=progress,
    )
    rows = 0
    if getattr(result, "empty", True) is False and "factor_rows" in result:
        rows = int(result["factor_rows"].sum())
    return RepairActionResult(
        name="repair_factor_daily",
        status=RepairStatus.SUCCESS,
        message="factor daily exact-window backfill complete",
        metrics={"factor_rows": rows},
    )


def repair_watchlist(
    trade_date: str,
    *,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    default_result = runner(trade_date=trade_date, watchlist_id="default")
    diagnostics_result = runner(trade_date=trade_date, watchlist_id="diagnostics")
    return RepairActionResult(
        name="repair_watchlist",
        status=RepairStatus.SUCCESS,
        message="watchlists rebuilt",
        metrics={
            "default_rows": _row_count(default_result),
            "diagnostics_rows": _row_count(diagnostics_result),
        },
    )


def repair_generated_reports(
    trade_date: str,
    *,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = runner(trade_date=trade_date)
    output_dir = str(result.get("output_dir") or "")
    return RepairActionResult(
        name="repair_generated_reports",
        status=RepairStatus.SUCCESS,
        message="generated reports refreshed",
        metrics=dict(result or {}),
        artifact_paths=[output_dir] if output_dir else [],
    )


def repair_review_evidence_snapshots(
    trade_date: str,
    *,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = runner(trade_date=trade_date)
    output_dir = str(result.get("output_dir") or "")
    return RepairActionResult(
        name="repair_review_evidence_snapshots",
        status=RepairStatus.SUCCESS,
        message="review evidence snapshots rebuilt",
        metrics=dict(result or {}),
        artifact_paths=[output_dir] if output_dir else [],
    )


def _row_count(result: dict[str, Any] | None) -> int:
    row_count = (result or {}).get("members")
    if row_count is None:
        row_count = (result or {}).get("row_count")
    return int(row_count or 0)
