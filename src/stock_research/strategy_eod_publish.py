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
from stock_research.dashboard.reports import DEFAULT_REPORTS_DIR
from stock_research.data_run_manifest import build_manifest_entry, upsert_data_run_manifest
from stock_research.db import connect, fetch_all
from stock_research.lhb_data import run_lhb_event_features_build
from stock_research.news_features import NEWS_FEATURE_COLUMNS, build_news_feature_daily
from stock_research.review_evidence_snapshots import run_eod_review_evidence_snapshots
from stock_research.strategy_contracts import OFFICIAL_MAX_POSITION_WEIGHT, OFFICIAL_TRANSACTION_COST_BPS
from stock_research.strategy_score_audit import build_strategy_score_audit, summarize_strategy_score_audit
from stock_research.tech_bottleneck_eod import run_tech_bottleneck_eod
from stock_research.tech_bottleneck_v1 import TECH_BOTTLENECK_V1_CANDIDATES_PATH
from stock_research.topn_news_enrichment import build_topn_news_enrichment
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
            WITH bars AS (
                SELECT max(trade_date)::text AS latest_trade_date,
                       count(*) AS row_count,
                       count(DISTINCT asset_id) AS asset_count
                FROM market_daily_bar
                WHERE adjust_type = 'hfq'
                  AND trade_date = %s
            ),
            quality AS (
                SELECT expected_count,
                       actual_count,
                       jsonb_array_length(missing_symbols) AS missing_count,
                       jsonb_array_length(abnormal_symbols) AS abnormal_count
                FROM ops.daily_pipeline_quality
                WHERE trade_date = %s
                  AND dataset_name = 'daily_bar'
                ORDER BY updated_at DESC
                LIMIT 1
            )
            SELECT bars.latest_trade_date,
                   bars.row_count,
                   bars.asset_count,
                   quality.expected_count,
                   quality.actual_count,
                   quality.missing_count,
                   quality.abnormal_count
            FROM bars
            LEFT JOIN quality ON true
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
PUBLISHABLE_BASE_STATUSES = {"success", "partial"}
NEWS_MIN_QUALITY_SCORE = 65
REPORT_SUFFIXES = {".html", ".md", ".json", ".csv"}
NEWS_FEATURE_DB_COLUMNS = [
    "trade_date",
    "asset_id",
    "ts_code",
    "news_count_1d",
    "news_count_3d",
    "news_count_5d",
    "major_news_count_3d",
    "source_diversity_3d",
    "overnight_news_count",
    "preopen_news_count",
    "headline_keyword_positive_count_3d",
    "headline_keyword_risk_count_3d",
    "theme_news_burst_flag",
    "news_first_seen_gap",
    "news_attention_level",
]


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

    output_dir = _strategy_eod_output_dir(selected_trade_date, output_root=output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"strategy-eod-{selected_trade_date}-local"
    started_at = datetime.now(timezone.utc)

    _ensure_strategy_dependencies(selected_trade_date, output_dir=output_dir)

    entries: list[dict[str, Any]] = []
    strategy_results: dict[str, dict[str, Any]] = {}
    entries.extend(
        _build_base_manifest_entries(
            run_id=run_id,
            trade_date=selected_trade_date,
            started_at=started_at,
        )
    )
    if not _base_entries_publishable(entries):
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
            strategy_results[strategy_id] = result
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
    tech_review_path = _optional_path(tech_result.get("review_path"))
    if tech_review_path is not None and tech_review_path.exists():
        review_frames.append(pd.read_csv(tech_review_path))
    strategy_results["tech_bottleneck"] = _strategy_score_audit_result(tech_result, tech_review_path=tech_review_path)

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
    score_audit: dict[str, Any]
    try:
        score_audit = _write_strategy_score_audit_artifacts(
            trade_date=selected_trade_date,
            output_dir=output_dir,
            review_rows=review_rows,
            strategy_results=strategy_results,
        )
    except Exception as exc:
        try:
            score_audit = _write_strategy_score_audit_failure_summary(
                trade_date=selected_trade_date,
                output_dir=output_dir,
                error=str(exc),
            )
        except Exception:
            score_audit = {
                "trade_date": selected_trade_date,
                "status": "failed",
                "error": str(exc),
            }

    entries.extend(
        _write_eod_news_artifacts(
            run_id=run_id,
            trade_date=selected_trade_date,
            output_dir=output_dir,
            review_rows=pd.DataFrame(review_rows),
            started_at=started_at,
        )
    )
    entries.extend(
        _write_report_content_manifest_entries(
            run_id=run_id,
            trade_date=selected_trade_date,
            started_at=started_at,
        )
    )

    for entry in entries:
        manifest_upsert(entry)
    snapshot_entry = _write_review_evidence_snapshot_entry(
        run_id=run_id,
        trade_date=selected_trade_date,
        output_dir=output_dir,
        started_at=started_at,
    )
    manifest_upsert(snapshot_entry)
    entries.append(snapshot_entry)

    summary_path = output_dir / "strategy_eod_publish_summary.json"
    summary = {
        "run_id": run_id,
        "trade_date": selected_trade_date,
        "output_dir": str(output_dir),
        "manifest_modules": [entry["module"] for entry in entries],
        "review_rows": len(review_rows),
        "score_audit": score_audit,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def load_strategy_score_audit_summary(
    *,
    trade_date: str,
    output_root: str | Path | None = None,
) -> dict[str, Any]:
    output_dir = _strategy_eod_output_dir(trade_date, output_root=output_root)
    summary_path = output_dir / "strategy_score_audit_summary.json"
    if not summary_path.exists():
        publish_summary_path = output_dir / "strategy_eod_publish_summary.json"
        if not publish_summary_path.exists():
            raise FileNotFoundError(f"strategy score audit summary not found: {summary_path}")
        publish_summary = json.loads(publish_summary_path.read_text(encoding="utf-8"))
        score_audit = dict(publish_summary.get("score_audit") or {})
        if not score_audit:
            raise FileNotFoundError(f"strategy score audit summary not found: {summary_path}")
        score_audit.setdefault("trade_date", trade_date)
        score_audit.pop("summary_path", None)
        detail_path = _relocated_output_file(
            score_audit.get("detail_path"),
            fallback=output_dir / "strategy_score_audit_detail.csv",
            expected_dir=output_dir,
        )
        if detail_path is None:
            score_audit.pop("detail_path", None)
        else:
            score_audit["detail_path"] = str(detail_path)
        return score_audit
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.setdefault("trade_date", trade_date)
    summary.setdefault("summary_path", str(summary_path))
    if summary.get("status") != "failed":
        detail_path = _relocated_output_file(
            summary.get("detail_path"),
            fallback=output_dir / "strategy_score_audit_detail.csv",
            expected_dir=output_dir,
        )
        if detail_path is None:
            summary.pop("detail_path", None)
        else:
            summary["detail_path"] = str(detail_path)
    return summary


def _strategy_eod_output_dir(trade_date: str, *, output_root: str | Path | None = None) -> Path:
    return Path(output_root or DEFAULT_OUTPUT_ROOT) / "research" / "strategy_daily_eod" / trade_date


def _path_belongs_to_dir(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _relocated_output_file(value: Any, *, fallback: Path, expected_dir: Path) -> Path | None:
    path = _optional_path(value)
    if path is not None and path.exists() and _path_belongs_to_dir(path, expected_dir):
        return path
    if fallback.exists():
        return fallback
    return None


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
                "transaction_cost_bps": OFFICIAL_TRANSACTION_COST_BPS,
                "max_position_weight": OFFICIAL_MAX_POSITION_WEIGHT,
                "risk_profile": "balanced",
            }
        )
    else:
        payload.update(
            {
                "rebalance_frequency": "weekly",
                "transaction_cost_bps": OFFICIAL_TRANSACTION_COST_BPS,
                "max_position_weight": OFFICIAL_MAX_POSITION_WEIGHT,
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


def _strategy_score_audit_result(tech_result: dict[str, Any], *, tech_review_path: Path | None) -> dict[str, Any]:
    audit_result = dict(tech_result)
    review_rows = audit_result.get("review_rows")
    if _is_row_data(review_rows):
        return audit_result
    if tech_review_path is not None and tech_review_path.exists():
        audit_result["review_rows"] = pd.read_csv(tech_review_path)
    return audit_result


def _write_strategy_score_audit_artifacts(
    *,
    trade_date: str,
    output_dir: Path,
    review_rows: list[dict[str, Any]],
    strategy_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    detail = build_strategy_score_audit(
        trade_date=trade_date,
        review_rows=review_rows,
        strategy_results=strategy_results,
        display_rows=review_rows,
    )
    detail_path = output_dir / "strategy_score_audit_detail.csv"
    summary_path = output_dir / "strategy_score_audit_summary.json"
    detail.to_csv(detail_path, index=False)
    summary = summarize_strategy_score_audit(detail, trade_date=trade_date)
    summary["status"] = "success"
    summary["detail_path"] = str(detail_path)
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _write_strategy_score_audit_failure_summary(
    *,
    trade_date: str,
    output_dir: Path,
    error: str,
) -> dict[str, Any]:
    summary_path = output_dir / "strategy_score_audit_summary.json"
    summary = {
        "trade_date": trade_date,
        "status": "failed",
        "error": error,
        "summary_path": str(summary_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _is_row_data(value: Any) -> bool:
    if isinstance(value, pd.DataFrame):
        return True
    if isinstance(value, list):
        return not value or isinstance(value[0], dict)
    return False


def _optional_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return Path(text)


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
        status, warnings = _base_status_and_warnings(module, row, trade_date)
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
                latest_trade_date=latest_trade_date if status in PUBLISHABLE_BASE_STATUSES else None,
                warnings=warnings,
            )
        )
    return entries


def _base_status_and_warnings(module: str, row: dict[str, Any], trade_date: str) -> tuple[str, list[str]]:
    row_count = int(row.get("row_count") or 0)
    latest_trade_date = str(row.get("latest_trade_date") or "")
    if row_count <= 0 or latest_trade_date != trade_date:
        return "unavailable", [f"{module} missing for {trade_date}"]

    expected_count = int(row.get("expected_count") or 0)
    missing_count = int(row.get("missing_count") or 0)
    abnormal_count = int(row.get("abnormal_count") or 0)
    if module == "daily_bars" and expected_count > 0 and (missing_count > 0 or abnormal_count > 0):
        gap_count = missing_count + abnormal_count
        if gap_count / expected_count <= 0.01:
            return "partial", [
                "daily_bars degraded within tolerance: "
                f"missing={missing_count} abnormal={abnormal_count} expected={expected_count}"
            ]
        return "unavailable", [
            "daily_bars gap exceeds tolerance: "
            f"missing={missing_count} abnormal={abnormal_count} expected={expected_count}"
        ]

    return "success", []


def _base_entries_publishable(entries: list[dict[str, Any]]) -> bool:
    return all(str(entry.get("status") or "") in PUBLISHABLE_BASE_STATUSES for entry in entries)


def _load_base_check_rows(trade_date: str) -> dict[str, dict[str, Any]]:
    result = {}
    with connect(SETTINGS.research_service) as conn:
        for module, config in BASE_CHECKS.items():
            sql = str(config["sql"])
            rows = fetch_all(conn, sql, [trade_date] * sql.count("%s"))
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
    excluded_lhb_assets = (
        _lhb_delisting_assets_for_trade_date(trade_date) if strategy_id == "lhb_shortline" else set()
    )
    review = _review_rows_from_result(
        result,
        trade_date=trade_date,
        excluded_lhb_assets=excluded_lhb_assets,
    )
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


def _review_rows_from_result(
    result: dict[str, Any],
    *,
    trade_date: str,
    excluded_lhb_assets: set[str] | None = None,
) -> pd.DataFrame:
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
        "score_components",
        "strategy_id",
        "strategy_name",
        "strategy_run_id",
        "source_type",
        "source_name",
        "source_rank",
        "review_tier",
    ]
    current_holdings = _current_holdings_from_trades(result, trade_date=trade_date)
    if strategy_id != "lhb_shortline" and not current_holdings.empty:
        positions = current_holdings
    if strategy_id == "mid_trend" and current_holdings.empty and _mid_trend_latest_equity_is_flat_cash(result, trade_date=trade_date):
        return pd.DataFrame(columns=columns)
    if positions.empty:
        if strategy_id != "lhb_shortline":
            return pd.DataFrame(columns=columns)
        candidate_frame = _lhb_same_day_candidate_frame(result, trade_date=trade_date)
        if candidate_frame.empty:
            return pd.DataFrame(columns=columns)
        frame = candidate_frame.copy()
    else:
        frame = positions.copy()

    date_col = _first_existing_column(frame, ["trade_date", "date", "rebalance_date"])
    if date_col:
        frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        eligible = frame[frame[date_col].le(trade_date)].copy()
        if not eligible.empty:
            latest_date = str(eligible[date_col].max())
            if strategy_id == "lhb_shortline" and latest_date < trade_date:
                candidate_frame = _lhb_same_day_candidate_frame(result, trade_date=trade_date)
                if not candidate_frame.empty:
                    frame = candidate_frame.copy()
                    date_col = _first_existing_column(frame, ["trade_date", "date", "rebalance_date"])
                else:
                    frame = eligible[eligible[date_col].eq(latest_date)].copy()
            else:
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
    mid_trend_daily_score_lookup = (
        _mid_trend_daily_score_lookup(trade_date, frame[asset_col].astype(str).tolist()) if strategy_id == "mid_trend" else {}
    )
    lhb_base_score_lookup = _lhb_base_score_lookup_for_trade_date(trade_date) if strategy_id == "lhb_shortline" else {}
    excluded_assets = set(excluded_lhb_assets or set())
    if strategy_id == "lhb_shortline":
        excluded_assets.update(_lhb_delisting_assets_from_result(result))
    rows = []
    for index, row in frame.reset_index(drop=True).iterrows():
        raw_asset_id = str(row.get(asset_col) or "")
        normalized_asset_id = _asset_id_from_review_code(raw_asset_id)
        if raw_asset_id in excluded_assets or normalized_asset_id in excluded_assets:
            continue
        rank = _optional_int(row.get(rank_col)) if rank_col else index + 1
        score = _score_value(row.get(score_col), score_col)
        resolved_score_col = score_col
        if score is None:
            lookup_score, lookup_source = _score_from_lookup(
                score_lookup,
                trade_date=str(row.get(date_col) or trade_date)[:10] if date_col else trade_date,
                asset_id=str(row.get(asset_col) or ""),
                allow_latest=False,
            )
            score = lookup_score
            resolved_score_col = lookup_source or score_col
        if score is None:
            lookup_score, lookup_source = _score_from_lookup(
                score_lookup,
                trade_date=str(row.get(date_col) or trade_date)[:10] if date_col else trade_date,
                asset_id=str(row.get(asset_col) or ""),
                allow_latest=True,
            )
            score = lookup_score
            resolved_score_col = lookup_source or resolved_score_col
        if score is None and strategy_id == "mid_trend":
            lookup_score, lookup_source = _score_from_lookup(
                mid_trend_daily_score_lookup,
                trade_date=trade_date,
                asset_id=str(row.get(asset_col) or ""),
                allow_latest=False,
            )
            score = lookup_score
            resolved_score_col = lookup_source or resolved_score_col
        score_components: dict[str, Any] = {}
        if strategy_id == "lhb_shortline" and _should_use_lhb_base_score(row=row, score_source=resolved_score_col):
            base_score_row = _lookup_lhb_base_score(
                lhb_base_score_lookup,
                asset_id=str(row.get(asset_col) or ""),
            )
            base_score = _score_value(base_score_row.get("score_total"), "score_total") if base_score_row else None
            if base_score is not None:
                score = base_score
                resolved_score_col = "score_total"
                score_components = _dict_or_empty(base_score_row.get("score_components"))
        rows.append(
            {
                "trade_date": trade_date,
                "asset_id": raw_asset_id,
                "rank": rank or index + 1,
                "score_total": score,
                "score_source": resolved_score_col or "",
                "score_explanation": "真实策略输出分；无策略分字段时留空，不使用排名占位分",
                "score_components": score_components,
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "strategy_run_id": f"strategy-eod-{trade_date}-local",
                "source_type": "strategy_manifest",
                "source_name": source_name,
                "source_rank": rank or index + 1,
                "review_tier": "top5_focus" if (rank or index + 1) <= 5 else "watch",
            }
        )
    review = pd.DataFrame(rows, columns=columns)
    if review.empty:
        return review
    if strategy_id == "lhb_shortline" and "score_total" in review.columns:
        review["_sort_score"] = pd.to_numeric(review["score_total"], errors="coerce")
        review = review.sort_values(["_sort_score", "asset_id"], ascending=[False, True], kind="stable").drop(columns=["_sort_score"])
        review["rank"] = range(1, len(review) + 1)
        review["source_rank"] = review["rank"]
        review["review_tier"] = review["rank"].map(lambda rank: "top5_focus" if int(rank) <= 5 else "watch")
        return review.reset_index(drop=True).reindex(columns=columns)
    return review.sort_values(["rank", "asset_id"], kind="stable").reset_index(drop=True)


def _mid_trend_latest_equity_is_flat_cash(result: dict[str, Any], *, trade_date: str) -> bool:
    equity = _records_frame(result.get("equity_curve"))
    if equity.empty:
        return False
    date_col = _first_existing_column(equity, ["trade_date", "date"])
    if not date_col:
        return False
    frame = equity.copy()
    frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    eligible = frame[frame[date_col].le(trade_date)].copy()
    if eligible.empty:
        return False
    latest = eligible.sort_values(date_col, kind="stable").iloc[-1]
    holdings_count = _score_value(latest.get("holdings_count"), None)
    invested_weight = _score_value(latest.get("invested_weight"), None)
    return (holdings_count is not None and holdings_count <= 0) or (
        invested_weight is not None and invested_weight <= 0
    )


def _current_holdings_from_trades(result: dict[str, Any], *, trade_date: str) -> pd.DataFrame:
    trades = _records_frame(result.get("trades"))
    if trades.empty:
        return pd.DataFrame()
    date_col = _first_existing_column(trades, ["trade_date", "date"])
    asset_col = _first_existing_column(trades, ["asset_id", "symbol", "ts_code", "stock_code"])
    weight_col = _first_existing_column(trades, ["target_weight", "weight"])
    if not date_col or not asset_col or not weight_col:
        return pd.DataFrame()
    frame = trades.copy()
    frame[date_col] = pd.to_datetime(frame[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame[frame[date_col].le(trade_date)].copy()
    if frame.empty:
        return pd.DataFrame()
    frame["_target_weight"] = pd.to_numeric(frame[weight_col], errors="coerce").fillna(0.0)
    latest = frame.sort_values([date_col, asset_col], kind="stable").groupby(asset_col, as_index=False).tail(1)
    latest = latest[latest["_target_weight"].gt(0)].copy()
    if latest.empty:
        return pd.DataFrame()
    position_order = _position_asset_order(result)
    latest["_position_order"] = latest[asset_col].map(position_order).fillna(len(position_order))
    latest = latest.sort_values(["_position_order", asset_col], kind="stable")
    latest["trade_date"] = trade_date
    latest["weight"] = latest["_target_weight"]
    latest["rank"] = range(1, len(latest) + 1)
    return latest.rename(columns={asset_col: "asset_id"}).reset_index(drop=True)


def _position_asset_order(result: dict[str, Any]) -> dict[str, int]:
    positions = _records_frame(result.get("positions"))
    asset_col = _first_existing_column(positions, ["asset_id", "symbol", "ts_code", "stock_code"])
    if positions.empty or not asset_col:
        return {}
    order: dict[str, int] = {}
    for index, asset_id in enumerate(positions[asset_col].astype(str).tolist()):
        order.setdefault(asset_id, index)
    return order


def _should_use_lhb_base_score(*, row: pd.Series, score_source: str | None) -> bool:
    if score_source != "auction_enhanced_score":
        return False
    return str(row.get("phase12a_rule_layer") or "").strip() == "pending_intraday"


def _lookup_lhb_base_score(
    lookup: dict[str, dict[str, Any]],
    *,
    asset_id: str,
) -> dict[str, Any] | None:
    keys = [asset_id]
    normalized_asset_id = _asset_id_from_review_code(asset_id)
    if normalized_asset_id:
        keys.append(normalized_asset_id)
    for key in keys:
        row = lookup.get(key)
        if row is not None:
            return row
    return None


def _lhb_base_score_lookup_for_trade_date(trade_date: str) -> dict[str, dict[str, Any]]:
    try:
        from stock_research.dashboard.strategy_backtest_adapters import build_lhb_shortline_scores_from_frames

        lhb, technical = _load_lhb_base_score_source_frames(trade_date)
        scores = build_lhb_shortline_scores_from_frames(lhb, technical)
    except Exception:
        return {}
    if scores.empty:
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for row in scores.to_dict("records"):
        score = _score_value(row.get("score_total"), "score_total")
        if score is None:
            continue
        raw_asset_id = str(row.get("asset_id") or "")
        payload = {
            "score_total": score,
            "score_components": _dict_or_empty(row.get("score_components")),
        }
        for key in {raw_asset_id, _asset_id_from_review_code(raw_asset_id)}:
            if key:
                lookup[key] = payload
    return lookup


def _load_lhb_base_score_source_frames(trade_date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    lhb_sql = """
        SELECT
            l.trade_date,
            COALESCE(a.asset_id, l.ts_code) AS asset_id,
            l.on_lhb,
            l.lhb_net_buy_ratio,
            l.lhb_net_buy_amount,
            l.institution_net_buy,
            l.repeat_on_list_count_3d,
            l.lhb_after_reversal,
            l.lhb_one_day_pump_risk
        FROM factor.lhb_event_features_daily l
        LEFT JOIN core.asset_master a ON a.ts_code = l.ts_code
        WHERE l.trade_date = %s
    """
    technical_sql = """
        SELECT trade_date, asset_id, amount_vs_20d, high_to_close_drawdown
        FROM factor.stock_technical_features_daily
        WHERE adjust_type = 'hfq'
          AND trade_date = %s
    """
    with connect(SETTINGS.research_service) as conn:
        lhb_rows = fetch_all(conn, lhb_sql, [trade_date])
        technical_rows = fetch_all(conn, technical_sql, [trade_date])
    return pd.DataFrame(lhb_rows), pd.DataFrame(technical_rows)


def _dict_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _lhb_same_day_candidate_frame(result: dict[str, Any], *, trade_date: str) -> pd.DataFrame:
    candidates = _records_frame(result.get("candidates"))
    if candidates.empty:
        return pd.DataFrame()
    if "trade_date" not in candidates.columns:
        return pd.DataFrame()
    frame = candidates.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame[frame["trade_date"].eq(trade_date)].copy()
    if frame.empty:
        return pd.DataFrame()
    if "auction_enhanced_score" in frame.columns:
        scored = pd.to_numeric(frame["auction_enhanced_score"], errors="coerce")
        frame = frame[scored.notna()].copy()
    return frame


def _lhb_delisting_assets_for_trade_date(trade_date: str) -> set[str]:
    sql = """
        SELECT ts_code, lhb_reason
        FROM factor.lhb_event_features_daily
        WHERE trade_date = %s
          AND lhb_reason LIKE '%%退市%%'
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [trade_date])
    excluded: set[str] = set()
    for row in rows:
        raw_asset_id = str(row.get("ts_code") or "")
        if raw_asset_id:
            excluded.add(raw_asset_id)
        normalized_asset_id = _asset_id_from_review_code(raw_asset_id)
        if normalized_asset_id:
            excluded.add(normalized_asset_id)
    return excluded


def _lhb_delisting_assets_from_result(result: dict[str, Any]) -> set[str]:
    frames = [
        _records_frame(result.get("signals")),
        _records_frame(result.get("candidates")),
    ]
    excluded: set[str] = set()
    reason_columns = ["reason", "list_reason", "lhb_reason", "abnormal_reason", "title", "security_name", "stock_name", "name"]
    delisting_terms = ("退市", "退市整理")
    for frame in frames:
        if frame.empty:
            continue
        asset_col = _first_existing_column(frame, ["asset_id", "ts_code", "symbol", "stock_code"])
        if not asset_col:
            continue
        for row in frame.to_dict("records"):
            reason_text = " ".join(str(row.get(column) or "") for column in reason_columns if column in row)
            if not any(term in reason_text for term in delisting_terms):
                continue
            raw_asset_id = str(row.get(asset_col) or "")
            if raw_asset_id:
                excluded.add(raw_asset_id)
            normalized_asset_id = _asset_id_from_review_code(raw_asset_id)
            if normalized_asset_id:
                excluded.add(normalized_asset_id)
    return excluded


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


def _mid_trend_daily_score_lookup(trade_date: str, asset_ids: list[str]) -> dict[tuple[str, str], tuple[float, str]]:
    normalized_assets = sorted({key for asset_id in asset_ids for key in {asset_id, _asset_id_from_review_code(asset_id)} if key})
    if not normalized_assets:
        return {}
    sql = """
        SELECT asset_id, score_total
        FROM factor.stock_score_daily
        WHERE score_version = %s
          AND trade_date = %s
          AND asset_id = ANY(%s)
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, ["manual_v1", trade_date, normalized_assets])
    lookup: dict[tuple[str, str], tuple[float, str]] = {}
    for row in rows:
        score = _score_value(row.get("score_total"), "mid_trend_funnel_score")
        if score is None:
            continue
        raw_asset_id = str(row.get("asset_id") or "")
        keys = {raw_asset_id, _asset_id_from_review_code(raw_asset_id)}
        for key in keys:
            if key:
                lookup[(trade_date, key)] = (score, "mid_trend_funnel_score")
    return lookup


def _score_from_lookup(
    lookup: dict[tuple[str, str], tuple[float, str]],
    *,
    trade_date: str,
    asset_id: str,
    allow_latest: bool = True,
) -> tuple[float | None, str | None]:
    keys = [(trade_date, asset_id)]
    normalized_asset_id = _asset_id_from_review_code(asset_id)
    if normalized_asset_id:
        keys.append((trade_date, normalized_asset_id))
    for key in keys:
        if key in lookup:
            return lookup[key]
    if not allow_latest:
        return None, None
    asset_keys = {asset_id}
    if normalized_asset_id:
        asset_keys.add(normalized_asset_id)
    latest_key = max(
        (
            key
            for key in lookup
            if key[1] in asset_keys
            and key[0]
            and key[0] <= trade_date
        ),
        default=None,
        key=lambda key: key[0],
    )
    if latest_key is not None:
        return lookup[latest_key]
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


def _write_eod_news_artifacts(
    *,
    run_id: str,
    trade_date: str,
    output_dir: Path,
    review_rows: pd.DataFrame,
    started_at: datetime,
) -> list[dict[str, Any]]:
    source_events = _load_eod_public_news_events(trade_date)
    news_path = output_dir / "public_news_events.csv"
    source_events.to_csv(news_path, index=False)

    mentions = _normalize_news_mentions_for_features(_load_eod_news_mentions(trade_date))
    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=[trade_date],
        mode="replay",
    )
    features = features.reindex(columns=NEWS_FEATURE_COLUMNS)
    feature_path = output_dir / "news_feature_daily.csv"
    features.to_csv(feature_path, index=False)
    _persist_news_features(features, trade_date)

    enrichment_candidates = _news_enrichment_candidates(review_rows, trade_date=trade_date)
    enrichment = build_topn_news_enrichment(
        candidates=enrichment_candidates,
        news_features=features,
    )
    enrichment_path = output_dir / "topn_news_enrichment.csv"
    enrichment.to_csv(enrichment_path, index=False)

    now = datetime.now(timezone.utc)
    news_latest_trade_date = _latest_local_date(source_events, "published_at")
    feature_latest_trade_date = _latest_value(features, "trade_date")
    enrichment_latest_trade_date = _latest_value(enrichment, "trade_date")
    return [
        build_manifest_entry(
            run_id=run_id,
            run_date=_today(),
            trade_date=trade_date,
            module="news",
            source="public_news",
            tier="tier2",
            status="success" if not source_events.empty and news_latest_trade_date == trade_date else "partial",
            started_at=started_at,
            ended_at=now,
            row_count=len(source_events),
            asset_count=None,
            latest_trade_date=news_latest_trade_date or None,
            artifact_path=news_path,
            config_version=f"quality>={NEWS_MIN_QUALITY_SCORE}",
            warnings=[] if not source_events.empty else [f"no accepted public news for {trade_date}"],
            metadata={
                "min_quality_score": NEWS_MIN_QUALITY_SCORE,
                "artifact_role": "accepted_public_news_events",
            },
        ),
        build_manifest_entry(
            run_id=run_id,
            run_date=_today(),
            trade_date=trade_date,
            module="news_features",
            source="news_feature_daily",
            tier="tier2",
            status="success" if not features.empty and feature_latest_trade_date == trade_date else "partial",
            started_at=started_at,
            ended_at=now,
            row_count=len(features),
            asset_count=_asset_count(features),
            latest_trade_date=feature_latest_trade_date or None,
            artifact_path=feature_path,
            config_version="replay_no_lookahead",
            warnings=[] if not features.empty else [f"no stock-level news features for {trade_date}"],
            metadata={
                "mode": "replay",
                "mention_rows": len(mentions),
                "db_table": "research.news_feature_daily",
            },
        ),
        build_manifest_entry(
            run_id=run_id,
            run_date=_today(),
            trade_date=trade_date,
            module="news_enrichment",
            source="topn_news_enrichment",
            tier="tier2",
            status="success" if not enrichment.empty and enrichment_latest_trade_date == trade_date else "partial",
            started_at=started_at,
            ended_at=now,
            row_count=len(enrichment),
            asset_count=_asset_count(enrichment),
            latest_trade_date=enrichment_latest_trade_date or None,
            artifact_path=enrichment_path,
            config_version="review_queue_topn_news_v1",
            warnings=[] if not enrichment.empty else [f"no review-candidate news enrichment for {trade_date}"],
            metadata={
                "candidate_rows": len(enrichment_candidates),
                "feature_rows": len(features),
            },
        ),
    ]


def _write_review_evidence_snapshot_entry(
    *,
    run_id: str,
    trade_date: str,
    output_dir: Path,
    started_at: datetime,
    snapshot_runner: Callable[..., dict[str, Any]] = run_eod_review_evidence_snapshots,
) -> dict[str, Any]:
    try:
        result = snapshot_runner(
            run_id=run_id,
            trade_date=trade_date,
            output_dir=output_dir,
            limit=30,
        )
    except Exception as exc:
        result = {
            "status": "partial",
            "row_count": 0,
            "asset_count": 0,
            "review_item_snapshot_count": 0,
            "evidence_digest_snapshot_count": 0,
            "warnings": [f"snapshot generation failed: {exc}"],
            "errors": [str(exc)],
            "artifact_path": "",
            "snapshot_status": "failed",
        }
    warnings = [str(warning) for warning in result.get("warnings") or []]
    errors = [str(error) for error in result.get("errors") or []]
    return build_manifest_entry(
        run_id=run_id,
        run_date=_today(),
        trade_date=trade_date,
        module="review_evidence_snapshots",
        source="review_queue/evidence_digest",
        tier="tier2",
        status=str(result.get("status") or "unavailable"),
        started_at=started_at,
        ended_at=datetime.now(timezone.utc),
        row_count=int(result.get("row_count") or 0),
        asset_count=int(result.get("asset_count") or 0),
        latest_trade_date=trade_date,
        warnings=warnings,
        error_message="; ".join(errors),
        artifact_path=str(result.get("artifact_path") or ""),
        config_version="review_queue_evidence_digest_snapshot_v1",
        metadata={
            "review_item_snapshot_count": int(result.get("review_item_snapshot_count") or 0),
            "evidence_digest_snapshot_count": int(result.get("evidence_digest_snapshot_count") or 0),
            "snapshot_status": str(result.get("snapshot_status") or result.get("status") or ""),
        },
    )


def _write_report_content_manifest_entries(
    *,
    run_id: str,
    trade_date: str,
    started_at: datetime,
) -> list[dict[str, Any]]:
    report_stats = _load_research_report_manifest_stats(trade_date)
    generated_reports = _generated_report_files(trade_date)
    now = datetime.now(timezone.utc)
    latest_report_date = str(report_stats.get("latest_trade_date") or "")
    generated_latest_date = trade_date if generated_reports else ""
    return [
        build_manifest_entry(
            run_id=run_id,
            run_date=_today(),
            trade_date=trade_date,
            module="research_reports",
            source="research.stock_report_source",
            tier="tier2",
            status="success" if int(report_stats.get("row_count") or 0) > 0 else "partial",
            started_at=started_at,
            ended_at=now,
            row_count=int(report_stats.get("row_count") or 0),
            asset_count=_optional_int(report_stats.get("asset_count")),
            latest_trade_date=latest_report_date or None,
            warnings=[] if int(report_stats.get("row_count") or 0) > 0 else ["no research reports available"],
            config_version="research_report_source_manifest_v1",
            metadata={
                "latest_publish_date": latest_report_date,
                "source": "research.stock_report_source",
            },
        ),
        build_manifest_entry(
            run_id=run_id,
            run_date=_today(),
            trade_date=trade_date,
            module="generated_reports",
            source="reports",
            tier="tier2",
            status="success" if generated_reports else "partial",
            started_at=started_at,
            ended_at=now,
            row_count=len(generated_reports),
            asset_count=None,
            latest_trade_date=generated_latest_date or None,
            artifact_path=generated_reports[0] if generated_reports else "",
            warnings=[] if generated_reports else [f"no generated reports found for {trade_date}"],
            config_version="local_report_file_manifest_v1",
            metadata={
                "report_paths": generated_reports[:20],
                "reports_dir": str(DEFAULT_REPORTS_DIR),
            },
        ),
    ]


def _load_research_report_manifest_stats(trade_date: str) -> dict[str, Any]:
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT COUNT(DISTINCT s.report_id) AS row_count,
                   COUNT(DISTINCT e.asset_id) AS asset_count,
                   MAX(s.publish_date)::text AS latest_trade_date
            FROM research.stock_report_source s
            LEFT JOIN research.stock_report_event e USING (report_id)
            WHERE s.publish_date <= %s::date
            """,
            [trade_date],
        )
    return dict(rows[0]) if rows else {}


def _generated_report_files(trade_date: str) -> list[str]:
    directory = Path(DEFAULT_REPORTS_DIR)
    if not directory.exists() or not directory.is_dir():
        return []
    return [
        str(path)
        for path in sorted(directory.iterdir())
        if path.is_file()
        and path.suffix.lower() in REPORT_SUFFIXES
        and trade_date in path.name
    ]


def _load_eod_public_news_events(trade_date: str) -> pd.DataFrame:
    sql = """
        SELECT source_event_id,
               source_name,
               source_channel,
               title,
               published_at,
               url,
               COALESCE(NULLIF(metadata #>> '{quality,score}', '')::numeric, 0) AS quality_score,
               metadata #> '{quality,reasons}' AS quality_reasons
        FROM research.news_event_source
        WHERE source_status = 'available'
          AND (published_at AT TIME ZONE 'Asia/Shanghai')::date = %s::date
          AND COALESCE(NULLIF(metadata #>> '{quality,score}', '')::numeric, 0) >= %s
        ORDER BY published_at DESC, source_event_id
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [trade_date, NEWS_MIN_QUALITY_SCORE])
    return pd.DataFrame(rows)


def _load_eod_news_mentions(trade_date: str) -> pd.DataFrame:
    sql = """
        SELECT m.source_event_id,
               m.asset_id,
               m.ts_code,
               m.stock_name,
               m.mapping_method,
               COALESCE(m.trade_date, (s.published_at AT TIME ZONE 'Asia/Shanghai')::date)::text AS trade_date,
               s.published_at,
               s.source_name,
               ''::text AS event_family,
               COALESCE(s.source_channel, '') AS source_channel,
               s.title,
               COALESCE(s.content, '') AS content
        FROM research.news_event_mention m
        JOIN research.news_event_source s USING (source_event_id)
        WHERE s.source_status = 'available'
          AND COALESCE(NULLIF(s.metadata #>> '{quality,score}', '')::numeric, 0) >= %s
          AND (s.published_at AT TIME ZONE 'Asia/Shanghai')::date
              BETWEEN %s::date - INTERVAL '20 days' AND %s::date
        ORDER BY s.published_at, m.source_event_id, m.asset_id
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [NEWS_MIN_QUALITY_SCORE, trade_date, trade_date])
    return pd.DataFrame(rows, columns=[
        "source_event_id",
        "asset_id",
        "ts_code",
        "stock_name",
        "mapping_method",
        "trade_date",
        "published_at",
        "source_name",
        "event_family",
        "source_channel",
        "title",
        "content",
    ])


def _normalize_news_mentions_for_features(mentions: pd.DataFrame) -> pd.DataFrame:
    if mentions.empty or "published_at" not in mentions.columns:
        return mentions
    frame = mentions.copy()
    published_at = pd.to_datetime(frame["published_at"], errors="coerce", utc=True)
    frame["published_at"] = published_at.dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
    return frame


def _persist_news_features(features: pd.DataFrame, trade_date: str) -> None:
    with connect(SETTINGS.research_service) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM research.news_feature_daily WHERE trade_date = %s", [trade_date])
            if features.empty:
                return
            insert_columns = [*NEWS_FEATURE_DB_COLUMNS, "metadata"]
            placeholders = ", ".join(["%s"] * len(NEWS_FEATURE_DB_COLUMNS) + ["%s::jsonb"])
            column_sql = ", ".join(insert_columns)
            rows = []
            for row in features.to_dict("records"):
                metadata = {
                    key: _json_scalar(value)
                    for key, value in row.items()
                    if key not in NEWS_FEATURE_DB_COLUMNS and pd.notna(value)
                }
                rows.append(
                    [
                        _db_feature_value(row.get(column), column)
                        for column in NEWS_FEATURE_DB_COLUMNS
                    ]
                    + [json.dumps(metadata, ensure_ascii=False)]
                )
            cur.executemany(
                f"""
                INSERT INTO research.news_feature_daily ({column_sql})
                VALUES ({placeholders})
                ON CONFLICT (trade_date, asset_id)
                DO UPDATE SET
                    ts_code = EXCLUDED.ts_code,
                    news_count_1d = EXCLUDED.news_count_1d,
                    news_count_3d = EXCLUDED.news_count_3d,
                    news_count_5d = EXCLUDED.news_count_5d,
                    major_news_count_3d = EXCLUDED.major_news_count_3d,
                    source_diversity_3d = EXCLUDED.source_diversity_3d,
                    overnight_news_count = EXCLUDED.overnight_news_count,
                    preopen_news_count = EXCLUDED.preopen_news_count,
                    headline_keyword_positive_count_3d = EXCLUDED.headline_keyword_positive_count_3d,
                    headline_keyword_risk_count_3d = EXCLUDED.headline_keyword_risk_count_3d,
                    theme_news_burst_flag = EXCLUDED.theme_news_burst_flag,
                    news_first_seen_gap = EXCLUDED.news_first_seen_gap,
                    news_attention_level = EXCLUDED.news_attention_level,
                    metadata = EXCLUDED.metadata
                """,
                rows,
            )


def _news_enrichment_candidates(review_rows: pd.DataFrame, *, trade_date: str) -> pd.DataFrame:
    if review_rows.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "rank", "score_total", "strategy_name"])
    frame = review_rows.copy()
    if "trade_date" not in frame.columns:
        frame["trade_date"] = trade_date
    frame["trade_date"] = frame["trade_date"].fillna(trade_date).astype(str).str[:10]
    if "asset_id" not in frame.columns:
        frame["asset_id"] = ""
    for column in ["rank", "score_total", "strategy_name"]:
        if column not in frame.columns:
            frame[column] = None
    return frame[["trade_date", "asset_id", "rank", "score_total", "strategy_name"]].copy()


def _latest_local_date(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    values = pd.to_datetime(frame[column], errors="coerce")
    if values.dropna().empty:
        return ""
    return str(values.dt.tz_convert("Asia/Shanghai").dt.date.max()) if values.dt.tz is not None else str(values.dt.date.max())


def _latest_value(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return ""
    values = pd.to_datetime(frame[column], errors="coerce").dropna()
    if values.empty:
        return ""
    return values.max().date().isoformat()


def _db_feature_value(value: Any, column: str) -> Any:
    if pd.isna(value):
        if column == "news_attention_level":
            return "low"
        if column == "theme_news_burst_flag":
            return False
        return None
    if column == "theme_news_burst_flag":
        return bool(value)
    if column in {"trade_date", "asset_id", "ts_code", "news_attention_level"}:
        return str(value)
    if column == "news_first_seen_gap":
        return _optional_int(value)
    return int(value)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


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
