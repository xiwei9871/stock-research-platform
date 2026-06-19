from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.dashboard.backtests import run_fresh_backtest
from stock_research.dashboard.platform import load_platform_summary
from stock_research.data_run_manifest import build_manifest_entry, upsert_data_run_manifest
from stock_research.db import connect, fetch_all
from stock_research.lhb_data import run_lhb_event_features_build
from stock_research.tech_bottleneck_eod import run_tech_bottleneck_eod
from stock_research.tech_bottleneck_v1 import TECH_BOTTLENECK_V1_CANDIDATES_PATH
from stock_research.technical_feature_store import build_and_store_stock_technical_features_daily


STRATEGY_EOD_START_DATE = "2026-01-01"
DEFAULT_OUTPUT_ROOT = Path(getattr(SETTINGS, "output_root", "/Users/xiwei/stock_research/outputs"))
STRATEGY_EOD_MODULES = {
    "lhb_shortline": "strategy_lhb_shortline",
    "mid_trend": "strategy_mid_trend",
    "tech_bottleneck": "strategy_tech_bottleneck",
}
STRATEGY_EOD_NAMES = {
    "lhb_shortline": "LHB Shortline Combo",
    "mid_trend": "Mid Trend Combo",
    "tech_bottleneck": "Tech Bottleneck Combo",
}
BASE_CHECKS = {
    "daily_bars": {
        "source": "market_daily_bar",
        "sql": """
            SELECT max(trade_date)::text AS latest_trade_date,
                   count(*) AS row_count,
                   count(DISTINCT asset_id) AS asset_count
            FROM market_daily_bar
            WHERE adjust_type = 'hfq'
              AND trade_date = %s
        """,
    },
    "technical_features": {
        "source": "factor.stock_technical_features_daily",
        "sql": """
            SELECT max(trade_date)::text AS latest_trade_date,
                   count(*) AS row_count,
                   count(DISTINCT asset_id) AS asset_count
            FROM factor.stock_technical_features_daily
            WHERE adjust_type = 'hfq'
              AND trade_date = %s
        """,
    },
    "score_topn": {
        "source": "factor.stock_score_daily",
        "sql": """
            SELECT max(trade_date)::text AS latest_trade_date,
                   count(*) AS row_count,
                   count(DISTINCT asset_id) AS asset_count
            FROM factor.stock_score_daily
            WHERE score_version = 'manual_v1'
              AND trade_date = %s
        """,
    },
    "lhb_features": {
        "source": "factor.lhb_event_features_daily",
        "sql": """
            SELECT max(trade_date)::text AS latest_trade_date,
                   count(*) AS row_count,
                   count(DISTINCT ts_code) AS asset_count
            FROM factor.lhb_event_features_daily
            WHERE trade_date = %s
        """,
    },
}


def publish_strategy_eod(
    *,
    trade_date: str | None = None,
    output_root: str | Path | None = None,
    runner: Callable[[dict[str, Any]], dict[str, Any]] = run_fresh_backtest,
    manifest_upsert: Callable[[dict[str, Any]], Any] = upsert_data_run_manifest,
) -> dict[str, Any]:
    selected_trade_date = trade_date or _latest_market_date()
    if not selected_trade_date:
        raise ValueError("trade_date is required because latest market date is unavailable")

    output_dir = Path(output_root or DEFAULT_OUTPUT_ROOT) / "research" / "strategy_daily_eod" / selected_trade_date
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"strategy-eod-{selected_trade_date}-local"
    started_at = datetime.now(timezone.utc)

    _ensure_strategy_dependencies(selected_trade_date, output_dir=output_dir)

    entries: list[dict[str, Any]] = []
    entries.extend(
        _build_base_manifest_entries(
            run_id=run_id,
            trade_date=selected_trade_date,
            started_at=started_at,
        )
    )
    if any(entry["status"] != "success" for entry in entries):
        entries.append(
            _failure_entry(
                run_id=run_id,
                trade_date=selected_trade_date,
                module="review_queue_strategy_manifest",
                source="strategy_daily_eod",
                started_at=started_at,
                error="base data checks did not all pass",
            )
        )
        for entry in entries:
            manifest_upsert(entry)
        raise RuntimeError("base data checks did not all pass")

    review_frames: list[pd.DataFrame] = []
    try:
        for strategy_id in ("lhb_shortline", "mid_trend"):
            result = runner(_strategy_payload(strategy_id, selected_trade_date))
            entry, review = _write_strategy_artifacts(
                run_id=run_id,
                trade_date=selected_trade_date,
                strategy_id=strategy_id,
                result=result,
                output_dir=output_dir,
                started_at=started_at,
            )
            entries.append(entry)
            review_frames.append(review)
    except Exception as exc:
        module = STRATEGY_EOD_MODULES.get(strategy_id, f"strategy_{strategy_id}")
        entries.append(
            _failure_entry(
                run_id=run_id,
                trade_date=selected_trade_date,
                module=module,
                source="strategy_daily_eod",
                started_at=started_at,
                error=str(exc),
            )
        )
        entries.append(
            _failure_entry(
                run_id=run_id,
                trade_date=selected_trade_date,
                module="review_queue_strategy_manifest",
                source="strategy_daily_eod",
                started_at=started_at,
                error=f"{module} failed",
            )
        )
        for entry in entries:
            manifest_upsert(entry)
        raise

    tech_entries: list[dict[str, Any]] = []
    try:
        tech_base_candidates_path = _prepare_tech_bottleneck_base_candidate_source(
            trade_date=selected_trade_date,
            output_dir=output_dir,
        )
        tech_result = run_tech_bottleneck_eod(
            start_date=STRATEGY_EOD_START_DATE,
            end_date=selected_trade_date,
            output_dir=output_dir,
            base_candidates_path=tech_base_candidates_path,
            manifest_upsert=lambda entry: tech_entries.append(entry),
        )
    except Exception as exc:
        entries.extend(tech_entries)
        entries.append(
            _failure_entry(
                run_id=run_id,
                trade_date=selected_trade_date,
                module="tech_bottleneck_candidates",
                source="point_in_time_daily_candidates",
                started_at=started_at,
                error=str(exc),
            )
        )
        entries.append(
            _failure_entry(
                run_id=run_id,
                trade_date=selected_trade_date,
                module="strategy_tech_bottleneck",
                source="strategy_daily_eod",
                started_at=started_at,
                error=str(exc),
            )
        )
        entries.append(
            _failure_entry(
                run_id=run_id,
                trade_date=selected_trade_date,
                module="review_queue_strategy_manifest",
                source="strategy_daily_eod",
                started_at=started_at,
                error="strategy_tech_bottleneck failed",
            )
        )
        for entry in entries:
            manifest_upsert(entry)
        raise
    entries.extend(tech_entries)
    tech_review_path = Path(str(tech_result.get("review_path") or ""))
    if tech_review_path.exists():
        review_frames.append(pd.read_csv(tech_review_path))

    review_path, review_rows = _write_review_queue(review_frames, output_dir)
    entries.append(
        build_manifest_entry(
            run_id=run_id,
            run_date=_today(),
            trade_date=selected_trade_date,
            module="review_queue_strategy_manifest",
            source="strategy_daily_eod",
            tier="tier1",
            status="success",
            started_at=started_at,
            ended_at=datetime.now(timezone.utc),
            row_count=len(review_rows),
            asset_count=_asset_count(pd.DataFrame(review_rows)),
            latest_trade_date=selected_trade_date,
            artifact_path=review_path,
            config_version="balanced_strategy_contracts",
            metadata={
                "strategy_modules": list(STRATEGY_EOD_MODULES.values()),
                "review_path": str(review_path),
            },
        )
    )

    for entry in entries:
        manifest_upsert(entry)

    summary_path = output_dir / "strategy_eod_publish_summary.json"
    summary = {
        "run_id": run_id,
        "trade_date": selected_trade_date,
        "output_dir": str(output_dir),
        "manifest_modules": [entry["module"] for entry in entries],
        "review_rows": len(review_rows),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _latest_market_date() -> str:
    return str(load_platform_summary().get("latest_market_date") or "")


def _strategy_payload(strategy_id: str, trade_date: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "strategy_id": strategy_id,
        "start_date": STRATEGY_EOD_START_DATE,
        "end_date": trade_date,
        "score_version": "manual_v1",
        "top_n": 5,
        "adjust_type": "hfq",
    }
    if strategy_id == "lhb_shortline":
        payload.update(
            {
                "rebalance_frequency": "daily",
                "transaction_cost_bps": 10.0,
                "risk_profile": "balanced",
            }
        )
    else:
        payload.update(
            {
                "rebalance_frequency": "weekly",
                "transaction_cost_bps": 20.0,
            }
        )
    return payload


def _ensure_strategy_dependencies(trade_date: str, *, output_dir: Path) -> None:
    if not _has_rows(
        """
        SELECT count(*) AS row_count
        FROM factor.stock_technical_features_daily
        WHERE trade_date = %s
          AND adjust_type = 'hfq'
        """,
        trade_date,
    ):
        build_and_store_stock_technical_features_daily(
            trade_date=trade_date,
            lookback_bars=260,
            adjust_type="hfq",
            build_strategy="latest_only",
        )

    if not _has_rows(
        """
        SELECT count(*) AS row_count
        FROM factor.lhb_event_features_daily
        WHERE trade_date = %s
        """,
        trade_date,
    ):
        run_lhb_event_features_build(
            start_date=trade_date,
            end_date=trade_date,
            ts_codes=None,
            output_dir=output_dir,
        )


def _prepare_tech_bottleneck_base_candidate_source(*, trade_date: str, output_dir: Path) -> Path:
    legacy = pd.read_csv(TECH_BOTTLENECK_V1_CANDIDATES_PATH, low_memory=False)
    if legacy.empty:
        raise ValueError("tech bottleneck legacy candidate seed is empty")
    missing = [column for column in ["asset_id", "first_hit_date"] if column not in legacy.columns]
    if missing:
        raise ValueError(f"tech bottleneck legacy candidate seed missing columns: {missing}")

    source = legacy.copy()
    source["candidate_trade_date"] = source["first_hit_date"]
    source["filter_decision"] = "pass"
    if "fundamental_trade_date" in source.columns:
        fundamental_dates = pd.to_datetime(source["fundamental_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        source["financial_as_of_date"] = fundamental_dates.fillna(source["first_hit_date"].astype(str))
    else:
        source["financial_as_of_date"] = source["first_hit_date"]
    if "technical_as_of_date" not in source.columns:
        source["technical_as_of_date"] = source["first_hit_date"]
    source["source_latest_trade_date"] = trade_date
    source["data_as_of_date"] = trade_date
    source["generated_trade_date"] = trade_date
    source["candidate_source_mode"] = "legacy_static_seed_daily_pit"

    output = output_dir / "tech_bottleneck_candidate_source" / "strict_153_st_only_financial_state_candidates.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    source.to_csv(output, index=False)
    return output


def _has_rows(sql: str, trade_date: str) -> bool:
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [trade_date])
    return bool(rows and int(rows[0].get("row_count") or 0) > 0)


def _build_base_manifest_entries(
    *,
    run_id: str,
    trade_date: str,
    started_at: datetime,
) -> list[dict[str, Any]]:
    rows = _load_base_check_rows(trade_date)
    entries = []
    for module, config in BASE_CHECKS.items():
        row = rows.get(module, {})
        row_count = int(row.get("row_count") or 0)
        latest_trade_date = str(row.get("latest_trade_date") or "")
        status = "success" if row_count > 0 and latest_trade_date == trade_date else "unavailable"
        warnings = [] if status == "success" else [f"{module} missing for {trade_date}"]
        entries.append(
            build_manifest_entry(
                run_id=run_id,
                run_date=_today(),
                trade_date=trade_date,
                module=module,
                source=str(config["source"]),
                tier="tier1",
                status=status,
                started_at=started_at,
                ended_at=datetime.now(timezone.utc),
                row_count=row_count,
                asset_count=_optional_int(row.get("asset_count")),
                latest_trade_date=latest_trade_date if status == "success" else None,
                warnings=warnings,
            )
        )
    return entries


def _load_base_check_rows(trade_date: str) -> dict[str, dict[str, Any]]:
    result = {}
    with connect(SETTINGS.research_service) as conn:
        for module, config in BASE_CHECKS.items():
            rows = fetch_all(conn, str(config["sql"]), [trade_date])
            result[module] = dict(rows[0]) if rows else {}
    return result


def _failure_entry(
    *,
    run_id: str,
    trade_date: str,
    module: str,
    source: str,
    started_at: datetime,
    error: str,
) -> dict[str, Any]:
    return build_manifest_entry(
        run_id=run_id,
        run_date=_today(),
        trade_date=trade_date,
        module=module,
        source=source,
        tier="tier1",
        status="failed",
        started_at=started_at,
        ended_at=datetime.now(timezone.utc),
        row_count=0,
        asset_count=0,
        warnings=[error],
        error_message=error,
    )


def _write_strategy_artifacts(
    *,
    run_id: str,
    trade_date: str,
    strategy_id: str,
    result: dict[str, Any],
    output_dir: Path,
    started_at: datetime,
) -> tuple[dict[str, Any], pd.DataFrame]:
    module = STRATEGY_EOD_MODULES[strategy_id]
    prefix = module
    equity_path = output_dir / f"{prefix}_equity.csv"
    positions_path = output_dir / f"{prefix}_positions.csv"
    trades_path = output_dir / f"{prefix}_trades.csv"
    review_path = output_dir / f"{prefix}_review.csv"

    _records_frame(result.get("equity_curve")).to_csv(equity_path, index=False)
    positions = _records_frame(result.get("positions"))
    positions.to_csv(positions_path, index=False)
    _records_frame(result.get("trades")).to_csv(trades_path, index=False)
    review = _review_rows_from_result(result, trade_date=trade_date)
    review.to_csv(review_path, index=False)

    summary = dict(result.get("summary") or {})
    summary.setdefault("engine_version", result.get("source_kind") or result.get("result_source") or "")
    summary.setdefault("requested_end_date", trade_date)
    summary.setdefault("actual_end_date", trade_date)
    metadata = {
        "summary": summary,
        "config": dict(result.get("config") or {}),
        "equity_path": str(equity_path),
        "positions_path": str(positions_path),
        "trades_path": str(trades_path),
        "review_path": str(review_path),
        "output_paths": {
            "equity_path": str(equity_path),
            "positions_path": str(positions_path),
            "trades_path": str(trades_path),
            "review_path": str(review_path),
        },
    }
    data_coverage = summary.get("data_coverage")
    if isinstance(data_coverage, dict) and data_coverage.get("candidate_snapshot_latest_date"):
        metadata["candidate_snapshot_latest_date"] = data_coverage.get("candidate_snapshot_latest_date")

    entry = build_manifest_entry(
        run_id=run_id,
        run_date=_today(),
        trade_date=trade_date,
        module=module,
        source="strategy_daily_eod",
        tier="tier1",
        status="success",
        started_at=started_at,
        ended_at=datetime.now(timezone.utc),
        row_count=int(len(review)),
        asset_count=_asset_count(review),
        latest_trade_date=trade_date,
        artifact_path=review_path,
        code_version=str(result.get("source_kind") or result.get("result_source") or ""),
        config_version=_strategy_config_version(strategy_id, result),
        metadata=metadata,
    )
    return entry, review


def _review_rows_from_result(result: dict[str, Any], *, trade_date: str) -> pd.DataFrame:
    positions = _records_frame(result.get("positions"))
    strategy_id = str(result.get("strategy_id") or "")
    strategy_name = str(result.get("strategy_name") or STRATEGY_EOD_NAMES.get(strategy_id, strategy_id))
    source_name = STRATEGY_EOD_MODULES.get(strategy_id, strategy_id)
    columns = [
        "trade_date",
        "asset_id",
        "rank",
        "score_total",
        "score_source",
        "score_explanation",
        "strategy_id",
        "strategy_name",
        "strategy_run_id",
        "source_type",
        "source_name",
        "source_rank",
        "review_tier",
    ]
    if positions.empty:
        return pd.DataFrame(columns=columns)

    frame = positions.copy()
    date_col = _first_existing_column(frame, ["trade_date", "date", "rebalance_date"])
    if date_col:
        frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        eligible = frame[frame[date_col].le(trade_date)].copy()
        if not eligible.empty:
            latest_date = str(eligible[date_col].max())
            frame = eligible[eligible[date_col].eq(latest_date)].copy()
    asset_col = _first_existing_column(frame, ["asset_id", "symbol", "ts_code", "stock_code"])
    if not asset_col:
        return pd.DataFrame(columns=columns)
    rank_col = _first_existing_column(frame, ["rank", "score_rank", "source_rank", "position_rank"])
    score_col = _first_existing_column(
        frame,
        [
            "score_total",
            "mid_trend_funnel_score",
            "lhb_shortline_score",
            "auction_enhanced_score",
            "bottleneck_score",
        ],
    )
    score_lookup = _strategy_score_lookup_from_result(result)
    rows = []
    for index, row in frame.reset_index(drop=True).iterrows():
        rank = _optional_int(row.get(rank_col)) if rank_col else index + 1
        score = _score_value(row.get(score_col), score_col)
        resolved_score_col = score_col
        if score is None:
            lookup_score, lookup_source = _score_from_lookup(
                score_lookup,
                trade_date=str(row.get(date_col) or trade_date)[:10] if date_col else trade_date,
                asset_id=str(row.get(asset_col) or ""),
            )
            score = lookup_score
            resolved_score_col = lookup_source or score_col
        rows.append(
            {
                "trade_date": trade_date,
                "asset_id": str(row.get(asset_col) or ""),
                "rank": rank or index + 1,
                "score_total": score,
                "score_source": resolved_score_col or "",
                "score_explanation": "真实策略输出分；无策略分字段时留空，不使用排名占位分",
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "strategy_run_id": f"strategy-eod-{trade_date}-local",
                "source_type": "strategy_manifest",
                "source_name": source_name,
                "source_rank": rank or index + 1,
                "review_tier": "top5_focus" if (rank or index + 1) <= 5 else "watch",
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(["rank", "asset_id"], kind="stable").reset_index(drop=True)


def _strategy_score_lookup_from_result(result: dict[str, Any]) -> dict[tuple[str, str], tuple[float, str]]:
    frames = [
        _records_frame(result.get("signals")),
        _records_frame(result.get("candidates")),
    ]
    lookup: dict[tuple[str, str], tuple[float, str]] = {}
    for frame in frames:
        if frame.empty:
            continue
        date_col = _first_existing_column(frame, ["trade_date", "date", "rebalance_date"])
        asset_col = _first_existing_column(frame, ["asset_id", "ts_code", "symbol", "stock_code"])
        score_col = _first_existing_column(
            frame,
            [
                "final_score",
                "score_total",
                "mid_trend_funnel_score",
                "lhb_shortline_score",
                "auction_enhanced_score",
                "bottleneck_score",
            ],
        )
        if not date_col or not asset_col or not score_col:
            continue
        source = frame.copy()
        source[date_col] = pd.to_datetime(source[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        for row in source.to_dict("records"):
            score = _score_value(row.get(score_col), score_col)
            if score is None:
                continue
            raw_asset_id = str(row.get(asset_col) or "")
            keys = {(str(row.get(date_col) or "")[:10], raw_asset_id)}
            normalized_asset_id = _asset_id_from_review_code(raw_asset_id)
            if normalized_asset_id:
                keys.add((str(row.get(date_col) or "")[:10], normalized_asset_id))
            for key in keys:
                if key[0] and key[1]:
                    lookup[key] = (score, score_col)
    return lookup


def _score_from_lookup(
    lookup: dict[tuple[str, str], tuple[float, str]],
    *,
    trade_date: str,
    asset_id: str,
) -> tuple[float | None, str | None]:
    keys = [(trade_date, asset_id)]
    normalized_asset_id = _asset_id_from_review_code(asset_id)
    if normalized_asset_id:
        keys.append((trade_date, normalized_asset_id))
    for key in keys:
        if key in lookup:
            return lookup[key]
    return None, None


def _asset_id_from_review_code(value: Any) -> str:
    text = str(value or "").upper().strip()
    if not text:
        return ""
    parts = text.split(":")
    if len(parts) == 3 and parts[0] == "CN":
        return text
    if "." in text:
        symbol, exchange = text.split(".", 1)
        if exchange in {"SH", "SZ", "BJ"}:
            return f"CN:{exchange}:{symbol}"
    return ""


def _write_review_queue(
    review_frames: list[pd.DataFrame],
    output_dir: Path,
) -> tuple[Path, list[dict[str, Any]]]:
    frames = [frame for frame in review_frames if frame is not None and not frame.empty]
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    path = output_dir / "review_queue_strategy_manifest.csv"
    frame.to_csv(path, index=False)
    return path, frame.to_dict("records")


def _records_frame(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list):
        return pd.DataFrame(value)
    return pd.DataFrame()


def _first_existing_column(frame: pd.DataFrame, names: list[str]) -> str:
    for name in names:
        if name in frame.columns:
            return name
    return ""


def _score_value(value: Any, source: str | None) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(score):
        return None
    if source == "bottleneck_score" and score <= 1.0:
        return score * 100.0
    return score


def _strategy_config_version(strategy_id: str, result: dict[str, Any]) -> str:
    summary = dict(result.get("summary") or {})
    config = dict(result.get("config") or {})
    parts = [
        strategy_id,
        str(summary.get("engine_version") or result.get("source_kind") or ""),
        str(summary.get("benchmark_variant") or summary.get("baseline_name") or ""),
        str(config.get("top_n") or summary.get("top_n") or ""),
    ]
    return ":".join(part for part in parts if part)


def _asset_count(frame: pd.DataFrame) -> int:
    if frame.empty or "asset_id" not in frame.columns:
        return 0
    return int(frame["asset_id"].dropna().astype(str).nunique())


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _today() -> str:
    return date.today().isoformat()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish official strategy EOD artifacts and manifest rows.")
    parser.add_argument("--trade-date", default="")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    args = parser.parse_args(argv)
    summary = publish_strategy_eod(
        trade_date=args.trade_date or None,
        output_root=args.output_root,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
