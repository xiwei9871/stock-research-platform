from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from stock_research.eod_auto_repair_models import RepairActionResult, RepairStatus


def repair_minute5_bars(
    trade_date: str,
    *,
    workers: int = 1,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    if int(workers) != 1:
        raise ValueError("Baostock minute backfill must use workers=1")
    result = runner(
        start_date=trade_date,
        end_date=trade_date,
        freq="5min",
        adjust_types=["raw", "qfq"],
        workers=1,
    )
    return RepairActionResult(
        name="repair_minute5_bars",
        status=RepairStatus.SUCCESS,
        message="minute5 repair submitted",
        metrics=dict(result or {}),
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
