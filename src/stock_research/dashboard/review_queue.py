from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from typing import Any

from stock_research.config import SETTINGS
from stock_research.data_run_manifest import load_latest_data_run_manifest, load_recent_data_run_manifest
from stock_research.dashboard.display_date_gate import select_display_date
from stock_research.dashboard.evidence_digest import build_evidence_digest
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.scores import load_top_scores_for_dashboard
from stock_research.dashboard.strategy_backtest_adapters import STRATEGY_BACKTEST_REGISTRY, StrategyBacktestParams
from stock_research.dashboard.strategy_catalog import list_strategy_catalog
from stock_research.db import connect, fetch_all
from stock_research.strategy_publication_artifacts import ARTIFACT_VERSION

BUCKET_ORDER = ["strong", "mixed", "risk_heavy", "thin"]
BUCKET_LABELS = {
    "strong": "High Conviction",
    "mixed": "Mixed Evidence",
    "risk_heavy": "Risk Flags",
    "thin": "Thin / Missing Sources",
}
RESEARCH_OUTPUT_ROOT = Path("/Users/xiwei/stock_research/outputs/research")


def load_strategy_contracts(*, profile: str = "balanced") -> dict[str, Any]:
    from stock_research.strategy_contracts import load_strategy_contracts as load_contracts

    return load_contracts(profile=profile)


def validate_strategy_summary_against_contract(summary: dict[str, Any], contract: Any) -> Any:
    from stock_research.strategy_contracts import (
        validate_strategy_summary_against_contract as validate_summary,
    )

    return validate_summary(summary, contract)


def build_review_queue(
    *,
    trade_date: str | None = None,
    score_version: str = "manual_v1",
    limit: int = 20,
    lookback_days: int = 90,
    review_mode: str = "strategy_topn",
    use_strategy_snapshots: bool = True,
) -> dict[str, Any]:
    bounded_limit = _bounded_int(limit, default=20, minimum=1, maximum=50)
    bounded_lookback_days = _bounded_int(lookback_days, default=90, minimum=1, maximum=365)
    normalized_review_mode = review_mode if review_mode in {"strategy_topn", "score_topn"} else "strategy_topn"
    summary_top_n = 10 if normalized_review_mode == "strategy_topn" else bounded_limit
    summary = load_platform_summary(score_version=score_version, top_n=summary_top_n)
    explicit_trade_date = bool(trade_date)
    selected_trade_date = str(trade_date) if explicit_trade_date else _default_display_trade_date(summary)
    if normalized_review_mode == "strategy_topn":
        identity_aware_strategy_ids = _identity_aware_manifest_strategy_ids(
            trade_date=selected_trade_date
        )
        strategy_rows = _attach_asset_names(_load_manifest_strategy_rows(trade_date=selected_trade_date, limit=50))
        if not strategy_rows:
            strategy_rows = (
                _load_strategy_snapshot_rows(trade_date=selected_trade_date, limit=50)
                if use_strategy_snapshots
                else []
            )
            strategy_rows = _without_strategy_rows(
                strategy_rows, identity_aware_strategy_ids
            )
        if not strategy_rows:
            strategy_rows = load_active_strategy_topn_rows(trade_date=selected_trade_date, limit=min(bounded_limit, 10))
        if strategy_rows:
            return _strategy_review_queue(
                rows=strategy_rows,
                selected_trade_date=selected_trade_date,
                score_version="strategy_topn",
                lookback_days=bounded_lookback_days,
            )

    score_rows = (
        load_top_scores_for_dashboard(selected_trade_date, score_version, bounded_limit)
        if explicit_trade_date or _should_load_scores_for_default_date(summary, selected_trade_date)
        else summary.get("topn_preview") or []
    )
    warnings: list[str] = []
    manifest = (
        _manifest_context(selected_trade_date, warnings)
        if score_rows
        else {"run_id": "", "latest_trade_date": selected_trade_date, "modules": []}
    )
    groups: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in BUCKET_ORDER}

    for row in score_rows:
        asset_id = str(row.get("asset_id") or "")
        if not asset_id:
            continue
        rank = _optional_int(row.get("rank"))
        try:
            digest = build_evidence_digest(
                asset_id,
                trade_date=selected_trade_date,
                lookback_days=bounded_lookback_days,
                score_version=score_version,
            )
        except Exception as exc:
            warning = f"{asset_id} digest unavailable: {exc}"
            warnings.append(warning)
            digest = _fallback_digest(asset_id, selected_trade_date, warning)
        item = _queue_item(
            row=row,
            digest=digest,
            trade_date=selected_trade_date,
            score_version=score_version,
            rank=rank,
            generated_at=_generated_at(selected_trade_date),
            manifest_modules=manifest["modules"],
            manifest_run_id=manifest["run_id"],
            manifest_latest_trade_date=manifest["latest_trade_date"],
        )
        groups[_bucket(digest)].append(item)

    return {
        "trade_date": selected_trade_date,
        "score_version": score_version,
        "review_mode": "score_topn",
        "generated_at": _generated_at(selected_trade_date),
        "groups": [
            {
                "bucket": bucket,
                "label": BUCKET_LABELS[bucket],
                "count": len(sorted_items := sorted(groups[bucket], key=_sort_key)),
                "items": sorted_items,
            }
            for bucket in BUCKET_ORDER
        ],
        "warnings": warnings,
    }


def _default_display_trade_date(summary: dict[str, Any]) -> str:
    latest_market_date = str(summary.get("latest_market_date") or "")
    if latest_market_date:
        return latest_market_date
    try:
        gate = select_display_date(
            list(load_recent_data_run_manifest()),
            latest_market_date=latest_market_date,
        )
    except Exception:
        gate = {}
    return str(
        gate.get("display_trade_date")
        or summary.get("latest_score_date")
        or ""
    )


def _should_load_scores_for_default_date(summary: dict[str, Any], selected_trade_date: str) -> bool:
    if not selected_trade_date:
        return False
    latest_score_date = str(summary.get("latest_score_date") or summary.get("latest_market_date") or "")
    return selected_trade_date != latest_score_date


def load_active_strategy_topn_rows(*, trade_date: str, limit: int) -> list[dict[str, Any]]:
    manifest_rows = _load_manifest_strategy_rows(trade_date=trade_date, limit=limit)
    if manifest_rows:
        return _attach_asset_names(manifest_rows)
    blocked_strategy_ids = _identity_aware_manifest_strategy_ids(trade_date=trade_date)
    suppress_tech_fallback = _has_untrusted_tech_manifest(trade_date=trade_date)
    artifact_rows = _load_strategy_artifact_topn_rows(trade_date=trade_date, limit=limit)
    db_rows = _load_db_strategy_position_rows(trade_date=trade_date, limit=limit)
    if suppress_tech_fallback:
        blocked_strategy_ids.add("tech_bottleneck")
    if blocked_strategy_ids:
        artifact_rows = _without_strategy_rows(artifact_rows, blocked_strategy_ids)
        db_rows = _without_strategy_rows(db_rows, blocked_strategy_ids)
    return _attach_asset_names(
        _select_latest_strategy_sources(artifact_rows=artifact_rows, db_rows=db_rows)
    )


def _load_strategy_snapshot_rows(*, trade_date: str, limit: int) -> list[dict[str, Any]]:
    if not trade_date:
        return []
    try:
        from stock_research.review_evidence_snapshots import list_review_item_snapshots

        snapshots = list_review_item_snapshots(trade_date=trade_date, limit=limit)
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        payload = snapshot.get("review_item_payload")
        if not isinstance(payload, dict):
            continue
        if str(payload.get("score_version") or "") != "strategy_topn":
            continue
        row = dict(payload)
        row.setdefault("trade_date", str(snapshot.get("trade_date") or trade_date)[:10])
        row.setdefault("latest_trade_date", str(snapshot.get("latest_trade_date") or row.get("trade_date") or trade_date)[:10])
        row.setdefault("asset_id", str(snapshot.get("stock_code") or snapshot.get("asset_id") or row.get("asset_id") or ""))
        row.setdefault("canonical_asset_id", str(snapshot.get("asset_id") or row.get("canonical_asset_id") or row.get("asset_id") or ""))
        row.setdefault("stock_name", str(snapshot.get("stock_name") or row.get("stock_name") or row.get("display_name") or ""))
        row.setdefault("display_name", str(row.get("stock_name") or row.get("display_name") or ""))
        row.setdefault("source_type", str(snapshot.get("source_type") or row.get("source_type") or "strategy_manifest"))
        row.setdefault("source_name", str(snapshot.get("source_name") or row.get("source_name") or ""))
        row.setdefault("source_rank", snapshot.get("source_rank") if snapshot.get("source_rank") is not None else row.get("source_rank"))
        row.setdefault("topn_rank", snapshot.get("topn_rank") if snapshot.get("topn_rank") is not None else row.get("topn_rank") or row.get("rank"))
        row.setdefault("rank", row.get("topn_rank") or row.get("source_rank"))
        row.setdefault("score_total", snapshot.get("score") if snapshot.get("score") is not None else row.get("score_total") or row.get("score"))
        rows.append(row)
    return _select_latest_strategy_sources(artifact_rows=rows, db_rows=[])


def _load_manifest_strategy_rows(*, trade_date: str, limit: int) -> list[dict[str, Any]]:
    if not trade_date:
        return []
    try:
        modules = list(load_latest_data_run_manifest(trade_date=trade_date))
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for module in modules:
        module_name = str(module.get("module") or "")
        if not module_name.startswith("strategy_") or str(module.get("status") or "") != "success":
            continue
        if not _manifest_strategy_snapshot_valid(module):
            continue
        if not _manifest_strategy_identity_valid(module):
            continue
        if not _manifest_strategy_artifact_path_valid(module):
            continue
        if not _manifest_strategy_contract_valid(module):
            continue
        artifact_path = Path(str(module.get("artifact_path") or ""))
        rows.extend(_read_manifest_strategy_artifact(artifact_path, trade_date=trade_date, limit=limit, manifest=module))
    return _select_latest_strategy_sources(artifact_rows=rows, db_rows=[])


def _manifest_strategy_snapshot_valid(module: dict[str, Any]) -> bool:
    if str(module.get("module") or "") != "strategy_tech_bottleneck":
        return True
    metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
    snapshot_date = _candidate_snapshot_latest_date(metadata)
    manifest_trade_date = str(module.get("trade_date") or module.get("latest_trade_date") or "")[:10]
    return bool(snapshot_date and manifest_trade_date and snapshot_date == manifest_trade_date)


def _has_untrusted_tech_manifest(*, trade_date: str) -> bool:
    if not trade_date:
        return False
    try:
        modules = list(load_latest_data_run_manifest(trade_date=trade_date))
    except Exception:
        return False
    for module in modules:
        if str(module.get("module") or "") != "strategy_tech_bottleneck":
            continue
        if str(module.get("status") or "") == "success" and not _manifest_strategy_snapshot_valid(module):
            return True
    return False


def _without_strategy_rows(
    rows: list[dict[str, Any]], strategy_ids: set[str]
) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("strategy_id") or "") not in strategy_ids]


def _identity_aware_manifest_strategy_ids(*, trade_date: str) -> set[str]:
    if not trade_date:
        return set()
    try:
        modules = list(load_latest_data_run_manifest(trade_date=trade_date))
    except Exception:
        return set()
    blocked: set[str] = set()
    for module in modules:
        strategy_id = _manifest_strategy_id(module)
        if strategy_id and _manifest_declares_identity_v1(module):
            blocked.add(strategy_id)
    return blocked


def _candidate_snapshot_latest_date(metadata: dict[str, Any]) -> str:
    snapshot_date = metadata.get("candidate_snapshot_latest_date")
    if not snapshot_date and isinstance(metadata.get("summary"), dict):
        snapshot_date = metadata["summary"].get("candidate_snapshot_latest_date")
    return str(snapshot_date or "")[:10]


def _manifest_strategy_contract_valid(module: dict[str, Any]) -> bool:
    strategy_id = _manifest_strategy_id(module)
    if not strategy_id:
        return True
    metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
    summary = metadata.get("summary") if isinstance(metadata.get("summary"), dict) else {}
    if not summary:
        return True
    try:
        contract = load_strategy_contracts(profile="balanced").get(strategy_id)
    except Exception:
        return True
    if contract is None:
        return True
    return validate_strategy_summary_against_contract(summary, contract).status == "success"


def _manifest_strategy_id(module: dict[str, Any]) -> str | None:
    return {
        "strategy_lhb_shortline": "lhb_shortline",
        "strategy_mid_trend": "mid_trend",
        "strategy_tech_bottleneck": "tech_bottleneck",
    }.get(str(module.get("module") or ""))


def _manifest_declares_identity_v1(module: dict[str, Any]) -> bool:
    metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
    summary = metadata.get("summary") if isinstance(metadata.get("summary"), dict) else {}
    config = metadata.get("config") if isinstance(metadata.get("config"), dict) else {}
    identity = metadata.get("publication_identity")
    summary_identity = summary.get("publication_identity")
    declarations = (
        metadata.get("identity_schema_version"),
        summary.get("identity_schema_version"),
        config.get("identity_schema_version"),
        identity.get("identity_schema_version") if isinstance(identity, dict) else None,
        summary_identity.get("identity_schema_version")
        if isinstance(summary_identity, dict)
        else None,
    )
    artifact_versions = (
        module.get("artifact_version"),
        metadata.get("artifact_version"),
        summary.get("artifact_version"),
        config.get("artifact_version"),
    )
    return (
        "strategy_publication_identity_v1" in declarations
        or ARTIFACT_VERSION in artifact_versions
    )


def _manifest_strategy_identity_valid(module: dict[str, Any]) -> bool:
    strategy_id = _manifest_strategy_id(module)
    if not strategy_id:
        return True
    metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
    actual = metadata.get("publication_identity")
    if not _manifest_declares_identity_v1(module) and not isinstance(actual, dict):
        return True
    if not isinstance(actual, dict):
        return False
    try:
        from stock_research.strategy_publication_contracts import (
            build_publication_identity,
            get_publication_contract,
            validate_publication_identity,
        )

        expected = build_publication_identity(get_publication_contract(strategy_id, profile="balanced"))
    except Exception:
        return False
    if validate_publication_identity(actual, expected):
        return False
    summary = metadata.get("summary") if isinstance(metadata.get("summary"), dict) else {}
    summary_identity = summary.get("publication_identity")
    if _manifest_declares_identity_v1(module) and not isinstance(summary_identity, dict):
        return False
    return not isinstance(summary_identity, dict) or not validate_publication_identity(
        summary_identity, expected
    )


def _manifest_strategy_artifact_path_valid(module: dict[str, Any]) -> bool:
    if not _manifest_declares_identity_v1(module):
        return True
    strategy_id = _manifest_strategy_id(module)
    metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
    output_paths = metadata.get("output_paths") if isinstance(metadata.get("output_paths"), dict) else {}
    publish_id = str(metadata.get("publish_id") or "")
    artifact_version = str(metadata.get("artifact_version") or "")
    artifact_path = Path(str(module.get("artifact_path") or ""))
    if not strategy_id or not publish_id or not artifact_version:
        return False
    if artifact_path.name != "review.csv":
        return False
    version_dir = artifact_path.parent
    if version_dir.name != publish_id:
        return False
    if version_dir.parent.name != strategy_id or version_dir.parent.parent.name != "strategy_runs":
        return False
    expected_files = {
        "equity_path": "equity.csv",
        "positions_path": "positions.csv",
        "trades_path": "trades.csv",
        "review_path": "review.csv",
        "summary_path": "summary.json",
        "publication_manifest_path": "publication_manifest.json",
    }
    if any(output_paths.get(key) in (None, "") for key in expected_files):
        return False
    for container in (metadata, output_paths):
        for key, expected_name in expected_files.items():
            declared = container.get(key)
            if declared in (None, ""):
                continue
            declared_path = Path(str(declared))
            if (
                declared_path.name != expected_name
                or declared_path.parent.resolve() != version_dir.resolve()
            ):
                return False
    if Path(str(output_paths.get("review_path") or "")).resolve() != artifact_path.resolve():
        return False
    return True


def _read_manifest_strategy_artifact(
    artifact_path: Path,
    *,
    trade_date: str,
    limit: int,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    frame = _read_artifact_frame(artifact_path)
    if frame is None or "trade_date" not in frame.columns:
        return []
    rows = _rows_for_latest_date(frame, trade_date=trade_date, date_col="trade_date")
    if rows is None:
        return []
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(_sort_records(rows, ["rank", "source_rank"])[:limit], start=1):
        asset_id = _asset_id_from_ts_code(row.get("asset_id") or row.get("ts_code") or row.get("stock_code"))
        strategy_id = _optional_text(row.get("strategy_id"))
        if not asset_id or not strategy_id:
            continue
        rank = _optional_int(row.get("rank") or row.get("source_rank")) or index
        score, score_source, score_explanation = _manifest_strategy_score(row, strategy_id=strategy_id, rank=rank)
        normalized.append(
            {
                "trade_date": str(row.get("trade_date") or "")[:10],
                "asset_id": asset_id,
                "rank": rank,
                "score_total": score,
                "score_version": "strategy_topn",
                "score_components": _optional_json_object(row.get("score_components")),
                "strategy_id": strategy_id,
                "strategy_name": str(row.get("strategy_name") or strategy_id),
                "strategy_run_id": str(row.get("strategy_run_id") or manifest.get("run_id") or ""),
                "source_type": str(row.get("source_type") or "strategy_manifest"),
                "source_name": str(row.get("source_name") or row.get("strategy_name") or strategy_id),
                "source_rank": rank,
                "review_tier": str(row.get("review_tier") or ("top5_focus" if rank <= 5 else "top10_watch")),
                "confirmation_state": _optional_text(row.get("confirmation_state")),
                "phase12a_rule_layer": _optional_text(row.get("phase12a_rule_layer")),
                "phase12a_rule_action": _optional_text(row.get("phase12a_rule_action")),
                "fill_status": _optional_text(row.get("fill_status")),
                "stock_name": _optional_text(row.get("stock_name") or row.get("name") or row.get("security_name")),
                "stock_name_source": _optional_text(row.get("stock_name_source")),
                "eligibility_status": _optional_text(row.get("eligibility_status")),
                "top5_eligible": _optional_bool(row.get("top5_eligible")),
                "backtest_entry_eligible": _optional_bool(row.get("backtest_entry_eligible")),
                "buy_signal_status": _optional_text(row.get("buy_signal_status")),
                "eligibility_reason_codes": _optional_json_list(row.get("eligibility_reason_codes")),
                "eligibility_warning_codes": _optional_json_list(row.get("eligibility_warning_codes")),
                "eligibility_contract_version": _optional_text(row.get("eligibility_contract_version")),
                "risk_gate_code": _optional_text(row.get("risk_gate_code")),
                "risk_gate_reason": _optional_text(row.get("risk_gate_reason")),
                "price_limit_regime": _optional_text(row.get("price_limit_regime")),
                "near_limit_down_threshold": _optional_float(row.get("near_limit_down_threshold")),
                "data_quality_status": _optional_text(row.get("data_quality_status")),
                "pct_chg": _optional_float(row.get("pct_chg")),
                "score_source": score_source,
                "score_explanation": score_explanation,
                "review_notes": _optional_json_list(row.get("review_notes")),
                "warnings": _optional_json_list(row.get("warnings")),
                "risk_flags": _optional_json_list(row.get("risk_flags")),
                "manifest_module": str(manifest.get("module") or ""),
            }
        )
    return normalized


def _manifest_strategy_score(row: dict[str, Any], *, strategy_id: str, rank: int) -> tuple[float | None, str | None, str | None]:
    existing_source = _optional_text(row.get("score_source"))
    existing_explanation = _optional_text(row.get("score_explanation"))
    raw_score = _optional_float(row.get("score_total") or row.get("score"))
    if strategy_id == "tech_bottleneck" and raw_score is not None and raw_score <= 1.0:
        return round(raw_score * 100.0, 2), existing_source or "bottleneck_score", existing_explanation or (
            "技术瓶颈发现分已换算为 0-100 分"
        )
    if raw_score is not None:
        return round(raw_score, 2), existing_source, existing_explanation
    return None, existing_source, existing_explanation


def _select_latest_strategy_sources(
    *,
    artifact_rows: list[dict[str, Any]],
    db_rows: list[dict[str, Any]],
    live_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    source_order: list[tuple[str, str]] = []
    for source_name, rows in (("artifact", artifact_rows), ("db", db_rows), ("live", live_rows or [])):
        by_strategy: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            strategy_id = str(row.get("strategy_id") or "")
            if not strategy_id:
                continue
            by_strategy.setdefault(strategy_id, []).append(row)
        for strategy_id, strategy_rows in by_strategy.items():
            grouped[f"{source_name}:{strategy_id}"] = strategy_rows
            source_order.append((source_name, strategy_id))

    selected_by_strategy: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    strategy_order: list[str] = []
    for source_name, strategy_id in source_order:
        key = f"{source_name}:{strategy_id}"
        rows = grouped[key]
        latest_date = max(str(row.get("trade_date") or "")[:10] for row in rows)
        previous = selected_by_strategy.get(strategy_id)
        if previous is None:
            selected_by_strategy[strategy_id] = (latest_date, rows)
            strategy_order.append(strategy_id)
            continue
        previous_date, previous_rows = previous
        previous_priority = max(_strategy_source_priority(row) for row in previous_rows)
        current_priority = max(_strategy_source_priority(row) for row in rows)
        if latest_date > previous_date or (latest_date == previous_date and current_priority > previous_priority):
            selected_by_strategy[strategy_id] = (latest_date, rows)

    selected: list[dict[str, Any]] = []
    for strategy_id in strategy_order:
        selected.extend(selected_by_strategy[strategy_id][1])
    return selected


def _strategy_source_priority(row: dict[str, Any]) -> int:
    source_type = str(row.get("source_type") or "")
    if source_type == "strategy_topn":
        return 3
    if source_type == "strategy_live_score":
        return 2
    if source_type == "strategy_artifact":
        return 1
    return 0


def _load_db_strategy_position_rows(*, trade_date: str, limit: int) -> list[dict[str, Any]]:
    strategy_names = _active_strategy_names()
    strategy_ids = list(strategy_names)
    if not strategy_ids:
        return []
    try:
        with connect(SETTINGS.research_service) as conn:
            rows = fetch_all(
                conn,
                """
                WITH active_runs AS (
                    SELECT DISTINCT ON (strategy_id)
                           run_id, strategy_id, strategy_name, combo_scheme, end_date
                    FROM backtest.strategy_backtest_run
                    WHERE strategy_id = ANY(%s)
                    ORDER BY strategy_id, end_date DESC, created_at DESC
                ),
                latest_position_dates AS (
                    SELECT r.run_id, max(p.trade_date) AS trade_date
                    FROM active_runs r
                    JOIN backtest.strategy_backtest_position p ON p.run_id = r.run_id
                    WHERE (%s = '' OR p.trade_date <= %s::date)
                    GROUP BY r.run_id
                )
                SELECT r.run_id, r.strategy_id, r.strategy_name, r.combo_scheme,
                       p.trade_date::text AS trade_date, p.asset_id, p.weight, p.rank, p.row_json
                FROM active_runs r
                JOIN latest_position_dates latest
                  ON latest.run_id = r.run_id
                JOIN backtest.strategy_backtest_position p
                  ON p.run_id = latest.run_id
                 AND p.trade_date = latest.trade_date
                ORDER BY r.strategy_id, COALESCE(p.rank, p.row_index + 1), p.row_index
                """,
                [strategy_ids, trade_date or "", trade_date or ""],
            )
    except Exception:
        return []

    grouped_counts: dict[str, int] = {}
    normalized: list[dict[str, Any]] = []
    for row in rows:
        strategy_id = str(row.get("strategy_id") or "")
        if strategy_id not in strategy_names:
            continue
        grouped_counts[strategy_id] = grouped_counts.get(strategy_id, 0) + 1
        if grouped_counts[strategy_id] > limit:
            continue
        row_json = row.get("row_json") if isinstance(row.get("row_json"), dict) else {}
        rank = _optional_int(row.get("rank") or row_json.get("rank") or row_json.get("score_rank") or row_json.get("shadow_top10_rank"))
        if rank is None:
            rank = grouped_counts[strategy_id]
        score = _optional_float(
            row_json.get("score_total")
            or row_json.get("score")
            or row_json.get("mid_trend_funnel_score")
            or row_json.get("bottleneck_score")
        )
        normalized.append(
            {
                "trade_date": str(row.get("trade_date") or "")[:10],
                "asset_id": str(row.get("asset_id") or row_json.get("asset_id") or ""),
                "rank": rank,
                "score_total": score,
                "score_version": "strategy_topn",
                "score_components": dict(row_json.get("score_components") or {}),
                "strategy_id": strategy_id,
                "strategy_name": str(row.get("strategy_name") or strategy_names[strategy_id]),
                "strategy_run_id": str(row.get("run_id") or ""),
                "combo_scheme": str(row.get("combo_scheme") or ""),
                "source_type": "strategy_topn",
                "source_name": str(row.get("strategy_name") or strategy_names[strategy_id]),
                "source_rank": rank,
                "review_tier": "top5_focus" if rank <= 5 else "top10_watch",
                "weight": _optional_float(row.get("weight") or row_json.get("weight") or row_json.get("target_weight")),
            }
        )
    return normalized


def _load_live_strategy_score_rows(*, trade_date: str, limit: int) -> list[dict[str, Any]]:
    if not trade_date:
        return []
    strategy_names = _active_strategy_names()
    params = StrategyBacktestParams(start_date=trade_date, end_date=trade_date, score_version="manual_v1", adjust_type="hfq")
    normalized: list[dict[str, Any]] = []
    for strategy_id, strategy_name in strategy_names.items():
        adapter = STRATEGY_BACKTEST_REGISTRY.get(strategy_id)
        if adapter is None or not hasattr(adapter, "load_scores"):
            continue
        try:
            frame = adapter.load_scores(params)
        except Exception:
            continue
        if frame is None or frame.empty:
            continue
        rows = frame.to_dict("records")
        strategy_rows = [
            row
            for row in rows
            if str(row.get("trade_date") or "")[:10] == trade_date and str(row.get("asset_id") or "")
        ]
        strategy_rows = sorted(
            strategy_rows,
            key=lambda row: (
                _optional_int(row.get("rank")) or 10**9,
                -(_optional_float(row.get("score_total")) or 0.0),
                str(row.get("asset_id") or ""),
            ),
        )
        for index, row in enumerate(strategy_rows[:limit], start=1):
            rank = _optional_int(row.get("rank")) or index
            normalized.append(
                {
                    "trade_date": str(row.get("trade_date") or "")[:10],
                    "asset_id": str(row.get("asset_id") or ""),
                    "rank": rank,
                    "score_total": _optional_float(row.get("score_total")),
                    "score_version": "strategy_topn",
                    "score_components": dict(row.get("score_components") or {}),
                    "strategy_id": strategy_id,
                    "strategy_name": strategy_name,
                    "strategy_run_id": f"live-score:{strategy_id}:{trade_date}",
                    "source_type": "strategy_live_score",
                    "source_name": strategy_name,
                    "source_rank": rank,
                    "review_tier": "top5_focus" if rank <= 5 else "top10_watch",
                    "review_notes": ["实时策略候选分数：尚未写入回测持仓表"],
                    "warnings": ["该条来自实时候选分数，用于复盘候选，不代表已执行持仓"],
                }
            )
    return normalized


def _load_strategy_artifact_topn_rows(*, trade_date: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(_load_lhb_shortline_artifact_rows(trade_date=trade_date, limit=limit))
    rows.extend(_load_mid_trend_artifact_rows(trade_date=trade_date, limit=limit))
    rows.extend(_load_tech_bottleneck_artifact_rows(trade_date=trade_date, limit=limit))
    return rows


def _load_lhb_shortline_artifact_rows(*, trade_date: str, limit: int) -> list[dict[str, Any]]:
    base = RESEARCH_OUTPUT_ROOT / "web_lhb_shortline_v1_runs"
    paths = [*base.glob("*/lhb_shortline_v1_candidates.csv"), *base.glob("*/lhb_phase18c_selected_trades_v1.csv")]
    frame = _best_latest_artifact_frame(paths, trade_date=trade_date, date_col="trade_date")
    if frame is None:
        return []
    rows = _rows_for_latest_date(frame, trade_date=trade_date, date_col="trade_date")
    if rows is None:
        return []
    rows = _dedupe_records_by_asset(
        _sort_records(rows, ["auction_enhanced_score", "phase18c_top_n"], descending=["auction_enhanced_score"])
    )
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:limit], start=1):
        asset_id = _asset_id_from_ts_code(row.get("asset_id") or row.get("ts_code"))
        if not asset_id:
            continue
        score = _optional_float(row.get("auction_enhanced_score") or row.get("score_total"))
        rule_layer = _optional_text(row.get("phase12a_rule_layer"))
        eligibility_status = _optional_text(row.get("eligibility_status"))
        confirmation_state = _optional_text(row.get("confirmation_state")) or _lhb_artifact_confirmation_state(
            rule_layer=rule_layer,
            rule_action=_optional_text(row.get("phase12a_rule_action")),
            fill_status=_optional_text(row.get("fill_status")),
            eligibility_status=eligibility_status,
        )
        fill_status = _optional_text(row.get("fill_status"))
        notes = []
        if rule_layer:
            notes.append(f"龙虎榜候选：{rule_layer}")
        if fill_status:
            notes.append(f"填充状态：{fill_status}")
        risk_flags = []
        realized_return = _optional_float(row.get("realized_return"))
        if realized_return is not None and realized_return < 0:
            risk_flags.append(
                {
                    "key": "lhb_recent_loss",
                    "label": f"最近成交回撤 {realized_return * 100:.1f}%",
                    "severity": "warning",
                }
            )
        if score is not None and score < 0:
            risk_flags.append({"key": "lhb_negative_score", "label": "龙虎榜增强分为负", "severity": "warning"})
        normalized.append(
            {
                "trade_date": str(row.get("trade_date") or "")[:10],
                "asset_id": asset_id,
                "rank": index,
                "score_total": score,
                "score_version": "strategy_topn",
                "score_components": {},
                "strategy_id": "lhb_shortline",
                "strategy_name": "LHB Shortline Combo",
                "strategy_run_id": "artifact:lhb_shortline_v1",
                "source_type": "strategy_artifact",
                "source_name": "LHB Shortline Combo",
                "source_rank": index,
                "review_tier": "risk_watch" if confirmation_state == "risk_watch" else ("top5_focus" if index <= 5 else "top10_watch"),
                "confirmation_state": confirmation_state,
                "phase12a_rule_layer": rule_layer,
                "phase12a_rule_action": _optional_text(row.get("phase12a_rule_action")),
                "fill_status": fill_status,
                "eligibility_status": eligibility_status,
                "top5_eligible": _optional_bool(row.get("top5_eligible")),
                "backtest_entry_eligible": _optional_bool(row.get("backtest_entry_eligible")),
                "eligibility_reason_codes": _optional_json_list(row.get("eligibility_reason_codes")),
                "eligibility_warning_codes": _optional_json_list(row.get("eligibility_warning_codes")),
                "eligibility_contract_version": _optional_text(row.get("eligibility_contract_version")),
                "weight": _optional_float(row.get("weight") or row.get("target_weight")),
                "stock_name": _optional_text(row.get("stock_name") or row.get("name") or row.get("security_name")),
                "score_source": "auction_enhanced_score",
                "score_explanation": "龙虎榜竞价增强分；负分表示策略规则强惩罚或不建议跟随",
                "review_notes": notes,
                "risk_flags": risk_flags,
                "warnings": ["龙虎榜列表页为策略轻量复盘，完整成交链路请打开个股工作台"],
            }
        )
    return normalized


def _lhb_artifact_confirmation_state(
    *,
    rule_layer: str | None,
    rule_action: str | None,
    fill_status: str | None,
    eligibility_status: str | None,
) -> str:
    if eligibility_status == "risk_watch":
        return "risk_watch"
    if eligibility_status == "hard_reject":
        return "retreat"
    if rule_layer == "pending_intraday" or rule_action == "pending":
        return "pending_confirmation"
    if (rule_layer or "").startswith("follow_pool") or rule_action == "follow_allowed" or fill_status == "filled":
        return "confirmed_follow"
    if rule_layer in {"watch_pool", "chase_control"}:
        return "watch_only"
    if rule_layer == "retreat_hard":
        return "retreat"
    return "pending_confirmation" if eligibility_status == "eligible" else "watch_only"


def _load_mid_trend_artifact_rows(*, trade_date: str, limit: int) -> list[dict[str, Any]]:
    paths = [
        RESEARCH_OUTPUT_ROOT / "mid_trend_shadow_top10_context_fixed_20260602/mid_trend_shadow_top10.csv",
        RESEARCH_OUTPUT_ROOT / "mid_trend_refresh_20260602/mid_trend_watch_top10.csv",
        RESEARCH_OUTPUT_ROOT / "mid_trend_watch_top10.csv",
    ]
    frame = _best_latest_artifact_frame(paths, trade_date=trade_date, date_col="trade_date")
    if frame is None:
        return []
    rows = _rows_for_latest_date(frame, trade_date=trade_date, date_col="trade_date")
    if rows is None:
        return []
    rows = _dedupe_records_by_asset(_sort_records(rows, ["shadow_top10_rank", "mid_trend_top10_rank", "rank"]))
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:limit], start=1):
        asset_id = _asset_id_from_ts_code(row.get("asset_id") or row.get("ts_code"))
        if not asset_id:
            continue
        rank = _optional_int(row.get("shadow_top10_rank") or row.get("mid_trend_top10_rank") or row.get("rank")) or index
        score = _optional_float(row.get("mid_trend_funnel_score") or row.get("score_total") or row.get("score"))
        notes = []
        for label, key in (("中趋势层", "mid_trend_layer"), ("结构槽位", "structure_slot"), ("观察备注", "shadow_note")):
            value = _optional_text(row.get(key))
            if value:
                notes.append(f"{label}：{value}")
        normalized.append(
            {
                "trade_date": str(row.get("trade_date") or "")[:10],
                "asset_id": asset_id,
                "rank": rank,
                "score_total": score,
                "score_version": "strategy_topn",
                "score_components": {},
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "strategy_run_id": "artifact:mid_trend_shadow_top10",
                "source_type": "strategy_artifact",
                "source_name": "Mid Trend Combo",
                "source_rank": rank,
                "review_tier": "top5_focus" if rank <= 5 else "top10_watch",
                "weight": _optional_float(row.get("weight") or row.get("target_weight")),
                "stock_name": _optional_text(row.get("stock_name") or row.get("name") or row.get("security_name")),
                "score_source": "mid_trend_funnel_score",
                "score_explanation": "中趋势漏斗分；越高代表趋势结构、波动和回撤组合越符合策略",
                "review_notes": notes or ["中趋势 Top10 候选"],
                "warnings": ["中趋势列表页为轻量复盘，完整新闻/研报证据请打开个股工作台"],
            }
        )
    return normalized


def _load_tech_bottleneck_artifact_rows(*, trade_date: str, limit: int) -> list[dict[str, Any]]:
    path = RESEARCH_OUTPUT_ROOT / "tech_bottleneck_discovery_v0_1_closeout_20260608/latest_positions.csv"
    frame = _best_latest_artifact_frame([path], trade_date=trade_date, date_col="trade_date")
    if frame is None:
        return []
    rows = _rows_for_latest_date(frame, trade_date=trade_date, date_col="trade_date")
    if rows is None:
        return []
    rows = _dedupe_records_by_asset(_sort_records(rows, ["bottleneck_rank", "rank"]))
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:limit], start=1):
        asset_id = _asset_id_from_ts_code(row.get("asset_id") or row.get("ts_code"))
        if not asset_id:
            continue
        rank = _optional_int(row.get("bottleneck_rank") or row.get("rank")) or index
        raw_score = _optional_float(row.get("bottleneck_score") or row.get("score_total") or row.get("score"))
        score = raw_score * 100.0 if raw_score is not None and raw_score <= 1.0 else raw_score
        notes = [f"技术瓶颈排名 #{rank}"]
        protection_name = _optional_text(row.get("protection_name"))
        if protection_name:
            notes.append(f"保护规则：{protection_name}")
        normalized.append(
            {
                "trade_date": str(row.get("trade_date") or "")[:10],
                "asset_id": asset_id,
                "rank": rank,
                "score_total": score,
                "score_version": "strategy_topn",
                "score_components": {},
                "strategy_id": "tech_bottleneck",
                "strategy_name": "Tech Bottleneck Combo",
                "strategy_run_id": "artifact:tech_bottleneck_latest_positions",
                "source_type": "strategy_artifact",
                "source_name": "Tech Bottleneck Combo",
                "source_rank": rank,
                "review_tier": "top5_focus" if rank <= 5 else "top10_watch",
                "weight": _optional_float(row.get("weight") or row.get("target_weight")),
                "stock_name": _optional_text(row.get("stock_name") or row.get("name") or row.get("security_name")),
                "score_source": "bottleneck_score",
                "score_explanation": "技术瓶颈发现分；越高代表越符合瓶颈突破/保护规则",
                "review_notes": notes,
                "warnings": ["技术瓶颈列表页为轻量复盘，完整新闻/研报证据请打开个股工作台"],
            }
        )
    return normalized


def _strategy_review_queue(
    *,
    rows: list[dict[str, Any]],
    selected_trade_date: str,
    score_version: str,
    lookback_days: int,
) -> dict[str, Any]:
    warnings: list[str] = []
    by_strategy: dict[str, list[dict[str, Any]]] = {}
    labels: dict[str, str] = {}
    for row in rows:
        asset_id = str(row.get("asset_id") or "")
        strategy_id = str(row.get("strategy_id") or "unknown")
        if not asset_id:
            continue
        item_trade_date = str(row.get("trade_date") or selected_trade_date)
        digest = _strategy_lightweight_digest(row, asset_id, item_trade_date)
        item = _queue_item(
            row=row,
            digest=digest,
            trade_date=item_trade_date,
            score_version=score_version,
            rank=_optional_int(row.get("rank")),
            generated_at=_generated_at(item_trade_date),
            manifest_modules=[],
            manifest_run_id=str(row.get("strategy_run_id") or ""),
            manifest_latest_trade_date=item_trade_date,
        )
        by_strategy.setdefault(strategy_id, []).append(item)
        labels[strategy_id] = str(row.get("strategy_name") or strategy_id)

    latest_item_date = max((str(row.get("trade_date") or "") for row in rows), default=selected_trade_date)
    if selected_trade_date and latest_item_date and latest_item_date < selected_trade_date:
        warnings.append(
            f"策略复盘数据最新日期 {latest_item_date}，早于平台日期 {selected_trade_date}；请检查策略候选/回测是否已更新。"
        )
    if selected_trade_date:
        for strategy_id, strategy_rows in by_strategy.items():
            strategy_latest_date = max(
                (str(item.get("latest_trade_date") or item.get("trade_date") or "") for item in strategy_rows),
                default="",
            )
            if strategy_latest_date and strategy_latest_date < selected_trade_date:
                strategy_label = labels.get(strategy_id, strategy_id)
                warnings.append(
                    f"{strategy_label} 复盘数据最新日期 {strategy_latest_date}，早于平台日期 {selected_trade_date}；"
                    "该策略未完成当日真实执行产物。"
                )
    active_strategy_names = _active_strategy_names()
    for strategy_id, strategy_label in active_strategy_names.items():
        by_strategy.setdefault(strategy_id, [])
        labels.setdefault(strategy_id, strategy_label)
    strategy_order = list(active_strategy_names)
    ordered_strategy_ids = [strategy_id for strategy_id in strategy_order if strategy_id in by_strategy]
    ordered_strategy_ids.extend(strategy_id for strategy_id in by_strategy if strategy_id not in ordered_strategy_ids)
    groups = [
        {
            "bucket": f"strategy:{strategy_id}",
            "label": labels.get(strategy_id, strategy_id),
            "count": len(sorted_items := sorted(by_strategy[strategy_id], key=_sort_key)),
            "items": sorted_items,
        }
        for strategy_id in ordered_strategy_ids
    ]
    return {
        "trade_date": latest_item_date or selected_trade_date,
        "score_version": score_version,
        "review_mode": "strategy_topn",
        "generated_at": _generated_at(latest_item_date or selected_trade_date),
        "groups": groups,
        "warnings": warnings,
    }


def _strategy_lightweight_digest(row: dict[str, Any], asset_id: str, trade_date: str) -> dict[str, Any]:
    strategy_name = str(row.get("strategy_name") or "策略")
    display_name = _row_display_name(row, asset_id)
    rank = _optional_int(row.get("rank"))
    tier = str(row.get("review_tier") or "")
    confirmation_state = _optional_text(row.get("confirmation_state"))
    tier_label = {
        "pending_confirmation": "Top5 次日确认待定",
        "confirmed_follow": "已确认可跟踪",
        "watch_only": "观察候选",
        "risk_watch": "风险观察",
        "retreat": "退出/回避",
    }.get(confirmation_state) or {
        "top5_focus": "Top5 重点复盘",
        "risk_watch": "跌停风险观察",
    }.get(tier, "Top6-10 观察")
    title = f"{strategy_name} {tier_label}"
    facts = [
        {
            "kind": "strategy",
            "label": f"{strategy_name} 最近持仓/候选排名 #{rank if rank is not None else '-'}",
            "value": tier_label,
            "severity": "neutral",
        }
    ]
    weight = _optional_float(row.get("weight"))
    if weight is not None:
        facts.append(
            {
                "kind": "strategy",
                "label": "策略目标权重",
                "value": round(weight * 100.0, 2),
                "severity": "neutral",
            }
        )
    for note in row.get("review_notes") or []:
        facts.append({"kind": "strategy", "label": str(note), "value": "", "severity": "neutral"})
    if confirmation_state:
        facts.append(
            {
                "kind": "strategy",
                "label": "确认状态",
                "value": confirmation_state,
                "severity": "neutral",
            }
        )
    rule_layer = _optional_text(row.get("phase12a_rule_layer"))
    if rule_layer:
        facts.append(
            {
                "kind": "strategy",
                "label": "规则层",
                "value": rule_layer,
                "severity": "neutral",
            }
        )
    score_source = _optional_text(row.get("score_source"))
    score_explanation = _optional_text(row.get("score_explanation"))
    if score_source or score_explanation:
        facts.append(
            {
                "kind": "strategy",
                "label": f"评分来源：{score_source or '策略产物'}",
                "value": score_explanation or "",
                "severity": "neutral",
            }
        )
    risk_flags = [dict(flag) for flag in (row.get("risk_flags") or []) if isinstance(flag, dict)]
    risk_gate_code = _optional_text(row.get("risk_gate_code"))
    if risk_gate_code:
        risk_flags.append(
            {
                "code": risk_gate_code,
                "message": _optional_text(row.get("risk_gate_reason")) or risk_gate_code,
                "severity": "warning",
            }
        )
    eligibility_warning_codes = _optional_json_list(row.get("eligibility_warning_codes"))
    if "st_high_risk" in eligibility_warning_codes:
        risk_flags.append(
            {
                "code": "st_high_risk",
                "message": "ST高风险",
                "severity": "warning",
            }
        )
    digest_warnings = [str(warning) for warning in (row.get("warnings") or []) if str(warning)]
    if not digest_warnings:
        digest_warnings.append("策略列表页为轻量复盘，完整新闻/研报证据请打开个股工作台")
    score = _optional_float(row.get("score_total"))
    if score is None:
        digest_warnings.append("策略候选分数缺失，请检查对应策略产物是否已更新")
    return {
        "asset_id": asset_id,
        "canonical_asset_id": asset_id,
        "trade_date": trade_date,
        "latest_trade_date": trade_date,
        "run_id": str(row.get("strategy_run_id") or ""),
        "digest_key": f"{trade_date}:strategy_topn:{asset_id}",
        "generated_at": _generated_at(trade_date),
        "overall_status": "PARTIAL",
        "title": title,
        "score": round(score, 2) if score is not None else 0,
        "bucket": "mixed",
        "facts": facts,
        "risk_flags": risk_flags,
        "source_refs": {
            "strategy_asset_id": asset_id,
            "strategy_name": strategy_name,
            "display_name": display_name,
            "asset_name": display_name,
        },
        "next_actions": [
            {
                "key": "review_stock",
                "label": "打开个股工作台",
                "workspace": "stock",
                "asset_id": asset_id,
                "query": display_name,
            }
        ],
        "warnings": digest_warnings,
        "missing_evidence": ["full_evidence_digest"],
        "partial_evidence": ["strategy_position"],
        "lineage": {
            "run_id": str(row.get("strategy_run_id") or ""),
            "strategy_run_id": str(row.get("strategy_run_id") or ""),
            "strategy_name": strategy_name,
            "latest_trade_date": trade_date,
            "factor_as_of": trade_date,
            "manifest_modules": [],
        },
    }


def _queue_item(
    *,
    row: dict[str, Any],
    digest: dict[str, Any],
    trade_date: str,
    score_version: str,
    rank: int | None,
    generated_at: str,
    manifest_modules: list[dict[str, Any]],
    manifest_run_id: str,
    manifest_latest_trade_date: str,
) -> dict[str, Any]:
    canonical_asset_id = str(digest.get("canonical_asset_id") or digest.get("asset_id") or row.get("asset_id") or "")
    facts = list(digest.get("facts") or [])
    risk_flags = list(digest.get("risk_flags") or [])
    digest_warnings = list(digest.get("warnings") or [])
    warnings = [str(warning) for warning in digest_warnings]
    next_actions = list(digest.get("next_actions") or [])
    bucket = _bucket(digest)
    digest_score = _optional_int(digest.get("score"))
    score = _optional_float(row.get("score_total"))
    if score is None:
        score = _optional_float(digest.get("score"))
    lineage = digest.get("lineage") if isinstance(digest.get("lineage"), dict) else {}
    strategy_run_id = _optional_text(row.get("strategy_run_id") or lineage.get("strategy_run_id"))
    if strategy_run_id is None:
        warnings.append("strategy_run_id unavailable for score_topn candidate")
    run_id = str(digest.get("run_id") or lineage.get("run_id") or manifest_run_id or "")
    latest_trade_date = str(
        digest.get("latest_trade_date") or lineage.get("latest_trade_date") or manifest_latest_trade_date or trade_date
    )
    digest_key = str(digest.get("digest_key") or f"{trade_date}:{score_version}:{canonical_asset_id}")
    missing_evidence = [str(item) for item in (digest.get("missing_evidence") or [])]
    partial_evidence = [str(item) for item in (digest.get("partial_evidence") or [])]
    evidence_status = str(digest.get("overall_status") or _evidence_status_from_bucket(bucket))
    digest_manifest_modules = lineage.get("manifest_modules")
    if not isinstance(digest_manifest_modules, list):
        digest_manifest_modules = manifest_modules
    display_name = _row_display_name(row, canonical_asset_id) or _display_name(digest, canonical_asset_id)
    stock_code = _optional_text(row.get("stock_code") or row.get("ts_code")) or canonical_asset_id
    return {
        "queue_id": f"{trade_date}:{score_version}:{canonical_asset_id}",
        "asset_id": str(row.get("asset_id") or digest.get("asset_id") or canonical_asset_id),
        "canonical_asset_id": canonical_asset_id,
        "stock_code": stock_code,
        "stock_name": display_name,
        "display_name": display_name,
        "trade_date": trade_date,
        "latest_trade_date": latest_trade_date,
        "run_id": run_id,
        "generated_at": generated_at,
        "score_version": score_version,
        "rank": rank,
        "score": score,
        "source_type": str(row.get("source_type") or "score_topn"),
        "source_name": str(row.get("source_name") or f"{score_version}_topn"),
        "source_rank": _optional_int(row.get("source_rank")) if row.get("source_rank") is not None else rank,
        "score_components": dict(row.get("score_components") or {}),
        "topn_rank": rank,
        "strategy_id": _optional_text(row.get("strategy_id")),
        "strategy_name": _optional_text(row.get("strategy_name") or lineage.get("strategy_name")),
        "strategy_run_id": strategy_run_id,
        "review_tier": _optional_text(row.get("review_tier")),
        "confirmation_state": _optional_text(row.get("confirmation_state")),
        "phase12a_rule_layer": _optional_text(row.get("phase12a_rule_layer")),
        "phase12a_rule_action": _optional_text(row.get("phase12a_rule_action")),
        "fill_status": _optional_text(row.get("fill_status")),
        "stock_name_source": _optional_text(row.get("stock_name_source")),
        "eligibility_status": _optional_text(row.get("eligibility_status")),
        "top5_eligible": _optional_bool(row.get("top5_eligible")),
        "backtest_entry_eligible": _optional_bool(row.get("backtest_entry_eligible")),
        "buy_signal_status": _optional_text(row.get("buy_signal_status")),
        "eligibility_reason_codes": _optional_json_list(row.get("eligibility_reason_codes")),
        "eligibility_warning_codes": _optional_json_list(row.get("eligibility_warning_codes")),
        "eligibility_contract_version": _optional_text(row.get("eligibility_contract_version")),
        "risk_gate_code": _optional_text(row.get("risk_gate_code")),
        "risk_gate_reason": _optional_text(row.get("risk_gate_reason")),
        "price_limit_regime": _optional_text(row.get("price_limit_regime")),
        "near_limit_down_threshold": _optional_float(row.get("near_limit_down_threshold")),
        "data_quality_status": _optional_text(row.get("data_quality_status")),
        "pct_chg": _optional_float(row.get("pct_chg")),
        "weight": _optional_float(row.get("weight")),
        "factor_as_of": str(lineage.get("factor_as_of") or trade_date),
        "factor_snapshot_id": _optional_text(lineage.get("factor_snapshot_id") or row.get("factor_snapshot_id")),
        "digest_key": digest_key,
        "evidence_digest_id": digest_key,
        "digest_url_path": _digest_url_path(canonical_asset_id, trade_date, score_version),
        "stock_workspace_url_path": f"/stock/{canonical_asset_id}?trade_date={trade_date}",
        "evidence_status": evidence_status,
        "missing_evidence": missing_evidence,
        "partial_evidence": partial_evidence,
        "missing_evidence_count": len(missing_evidence),
        "partial_evidence_count": len(partial_evidence),
        "warnings_count": len(warnings),
        "warnings": warnings,
        "manifest_modules": digest_manifest_modules,
        "digest_title": str(digest.get("title") or BUCKET_LABELS[bucket]),
        "score_total": _optional_float(row.get("score_total")),
        "digest_score": digest_score,
        "bucket": bucket,
        "source_kinds": _source_kinds(facts),
        "risk_count": len(risk_flags),
        "warning_count": len(digest_warnings),
        "next_action_count": len(next_actions),
        "digest": digest,
    }


def _best_latest_artifact_frame(paths: list[Path], *, trade_date: str, date_col: str):
    best = None
    best_key: tuple[str, int, str] | None = None
    for path in paths:
        frame = _read_artifact_frame(path)
        if frame is None or date_col not in frame.columns:
            continue
        rows = _rows_for_latest_date(frame, trade_date=trade_date, date_col=date_col)
        if rows is None:
            continue
        latest_date = max((str(row.get(date_col) or "")[:10] for row in rows), default="")
        key = (latest_date, len(rows), str(path))
        if best_key is None or key > best_key:
            best = frame
            best_key = key
    return best


def _read_artifact_frame(path: Path):
    if not path.exists():
        return None
    try:
        import pandas as pd

        return pd.read_csv(path, low_memory=False)
    except Exception:
        return None


def _rows_for_latest_date(frame, *, trade_date: str, date_col: str) -> list[dict[str, Any]] | None:
    if date_col not in frame.columns:
        return None
    working = frame.copy()
    working[date_col] = working[date_col].astype(str).str.slice(0, 10)
    if trade_date:
        working = working[working[date_col] <= str(trade_date)[:10]]
    if working.empty:
        return None
    latest_date = str(working[date_col].max())[:10]
    latest = working[working[date_col] == latest_date]
    return _clean_records(latest.to_dict("records"))


def _clean_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for record in records:
        item: dict[str, Any] = {}
        for key, value in record.items():
            text = str(value)
            if text == "nan":
                item[key] = None
            else:
                item[key] = value
        cleaned.append(item)
    return cleaned


def _sort_records(
    records: list[dict[str, Any]],
    keys: list[str],
    *,
    descending: list[str] | None = None,
) -> list[dict[str, Any]]:
    descending_set = set(descending or [])

    def sort_key(row: dict[str, Any]) -> tuple:
        values: list[Any] = []
        for key in keys:
            value = _optional_float(row.get(key))
            if value is None:
                values.append(1_000_000)
            elif key in descending_set:
                values.append(-value)
            else:
                values.append(value)
        values.append(str(row.get("asset_id") or row.get("ts_code") or ""))
        return tuple(values)

    return sorted(records, key=sort_key)


def _dedupe_records_by_asset(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in records:
        asset_id = _asset_id_from_ts_code(row.get("asset_id") or row.get("ts_code"))
        if not asset_id or asset_id in seen:
            continue
        seen.add(asset_id)
        deduped.append(row)
    return deduped


def _asset_id_from_ts_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("CN:"):
        return text
    if "." not in text:
        return text
    symbol, exchange = text.split(".", 1)
    exchange = exchange.upper()
    if exchange in {"SH", "SSE", "SHH"}:
        return f"CN:SH:{symbol.zfill(6)}"
    if exchange in {"SZ", "SZSE", "SHE"}:
        return f"CN:SZ:{symbol.zfill(6)}"
    return text


def _attach_asset_names(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    asset_ids = [str(row.get("asset_id") or "") for row in rows if row.get("asset_id")]
    names = _load_asset_names(asset_ids)
    enriched: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        asset_id = str(item.get("asset_id") or "")
        if not _row_display_name(item, asset_id) and asset_id in names:
            item["stock_name"] = names[asset_id]
        enriched.append(item)
    return enriched


def _load_asset_names(asset_ids: list[str]) -> dict[str, str]:
    unique_asset_ids = sorted({asset_id for asset_id in asset_ids if asset_id})
    if not unique_asset_ids:
        return {}
    try:
        with connect(SETTINGS.research_service) as conn:
            rows = fetch_all(
                conn,
                """
                SELECT asset_id, name
                FROM core.asset_master
                WHERE asset_id = ANY(%s)
                """,
                [unique_asset_ids],
            )
    except Exception:
        return {}
    return {str(row.get("asset_id")): str(row.get("name")) for row in rows if row.get("asset_id") and row.get("name")}


def _row_display_name(row: dict[str, Any], asset_id: str) -> str:
    for key in ("display_name", "stock_name", "asset_name", "security_name", "name"):
        value = _optional_text(row.get(key))
        if value and value != asset_id:
            return value
    return ""


def _active_strategy_names() -> dict[str, str]:
    strategies: dict[str, str] = {}
    for strategy in list_strategy_catalog():
        strategy_id = str(strategy.get("strategy_id") or "")
        if strategy.get("status") == "runnable" and strategy_id:
            strategies[strategy_id] = str(strategy.get("strategy_name") or strategy_id)
    return strategies


def _generated_at(selected_trade_date: str) -> str:
    if not selected_trade_date:
        return ""
    return f"{selected_trade_date}T00:00:00+00:00"


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    parsed = _optional_int(value)
    if parsed is None:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_json_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except Exception:
        return [str(value)]
    return parsed if isinstance(parsed, list) else [parsed]


def _optional_json_object(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _manifest_context(selected_trade_date: str, warnings: list[str]) -> dict[str, Any]:
    if not selected_trade_date:
        return {"run_id": "", "latest_trade_date": "", "modules": []}
    try:
        modules = list(load_latest_data_run_manifest(trade_date=selected_trade_date))
    except Exception as exc:
        warnings.append(f"data run manifest unavailable: {exc}")
        return {"run_id": "", "latest_trade_date": selected_trade_date, "modules": []}
    run_id = ""
    latest_trade_date = selected_trade_date
    normalized: list[dict[str, Any]] = []
    for module in modules:
        item = dict(module)
        if not run_id and item.get("run_id"):
            run_id = str(item.get("run_id"))
        if item.get("latest_trade_date"):
            latest_trade_date = str(item.get("latest_trade_date"))[:10]
        elif item.get("trade_date"):
            latest_trade_date = str(item.get("trade_date"))[:10]
        normalized.append(
            {
                "module": str(item.get("module") or ""),
                "tier": str(item.get("tier") or ""),
                "status": str(item.get("status") or ""),
                "warnings": list(item.get("warnings") or []),
                "error_message": str(item.get("error_message") or ""),
                "artifact_path": str(item.get("artifact_path") or ""),
            }
        )
    return {"run_id": run_id, "latest_trade_date": latest_trade_date, "modules": normalized}


def _digest_url_path(asset_id: str, trade_date: str, score_version: str) -> str:
    return "/api/evidence-digest?" + urlencode(
        {
            "asset_id": asset_id,
            "trade_date": trade_date,
            "score_version": score_version,
        }
    )


def _evidence_status_from_bucket(bucket: str) -> str:
    if bucket == "thin":
        return "PARTIAL"
    return "OK"


def _bucket(digest: dict[str, Any]) -> str:
    bucket = str(digest.get("bucket") or "")
    if bucket in BUCKET_ORDER:
        return bucket
    if digest.get("risk_flags"):
        return "risk_heavy"
    if not digest.get("facts"):
        return "thin"
    return "mixed"


def _source_kinds(facts: list[dict[str, Any]]) -> list[str]:
    kinds: list[str] = []
    seen: set[str] = set()
    for fact in facts:
        kind = str(fact.get("kind") or "")
        if kind and kind not in seen:
            seen.add(kind)
            kinds.append(kind)
    return kinds


def _sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    rank = _optional_int(item.get("rank"))
    digest_score = _optional_int(item.get("digest_score"))
    return (
        rank if rank is not None else 1_000_000,
        -(digest_score if digest_score is not None else 0),
        str(item.get("asset_id") or ""),
    )


def _fallback_digest(asset_id: str, trade_date: str, warning: str) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "canonical_asset_id": asset_id,
        "trade_date": trade_date,
        "title": "Thin / Missing Sources",
        "score": 0,
        "bucket": "thin",
        "facts": [],
        "risk_flags": [],
        "source_refs": {"strategy_asset_id": asset_id},
        "next_actions": [
            {
                "key": "review_stock",
                "label": "Review Stock",
                "workspace": "stock",
                "asset_id": asset_id,
                "query": asset_id,
            }
        ],
        "warnings": [warning],
    }


def _display_name(digest: dict[str, Any], canonical_asset_id: str) -> str:
    asset = digest.get("asset") if isinstance(digest.get("asset"), dict) else {}
    for key in ("display_name", "name", "asset_name"):
        value = asset.get(key)
        if value:
            return str(value)
    source_refs = digest.get("source_refs") if isinstance(digest.get("source_refs"), dict) else {}
    for key in ("display_name", "asset_name", "security_name", "name"):
        value = source_refs.get(key)
        if value:
            return str(value)
    return canonical_asset_id
