from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from stock_research.dashboard.evidence_digest import build_evidence_digest
from stock_research.dashboard.platform import load_platform_summary

BUCKET_ORDER = ["strong", "mixed", "risk_heavy", "thin"]
BUCKET_LABELS = {
    "strong": "High Conviction",
    "mixed": "Mixed Evidence",
    "risk_heavy": "Risk Flags",
    "thin": "Thin / Missing Sources",
}


def build_review_queue(
    *,
    trade_date: str | None = None,
    score_version: str = "manual_v1",
    limit: int = 20,
    lookback_days: int = 90,
) -> dict[str, Any]:
    bounded_limit = _bounded_int(limit, default=20, minimum=1, maximum=50)
    bounded_lookback_days = _bounded_int(lookback_days, default=90, minimum=1, maximum=365)
    summary = load_platform_summary(score_version=score_version, top_n=bounded_limit)
    selected_trade_date = str(
        trade_date
        or summary.get("latest_market_date")
        or summary.get("latest_score_date")
        or ""
    )
    warnings: list[str] = []
    groups: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in BUCKET_ORDER}

    for row in summary.get("topn_preview") or []:
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
        )
        groups[_bucket(digest)].append(item)

    return {
        "trade_date": selected_trade_date,
        "score_version": score_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
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


def _queue_item(
    *,
    row: dict[str, Any],
    digest: dict[str, Any],
    trade_date: str,
    score_version: str,
    rank: int | None,
) -> dict[str, Any]:
    canonical_asset_id = str(digest.get("canonical_asset_id") or digest.get("asset_id") or row.get("asset_id") or "")
    facts = list(digest.get("facts") or [])
    risk_flags = list(digest.get("risk_flags") or [])
    warnings = list(digest.get("warnings") or [])
    next_actions = list(digest.get("next_actions") or [])
    bucket = _bucket(digest)
    digest_score = _optional_int(digest.get("score"))
    return {
        "queue_id": f"{trade_date}:{score_version}:{canonical_asset_id}",
        "asset_id": str(row.get("asset_id") or digest.get("asset_id") or canonical_asset_id),
        "canonical_asset_id": canonical_asset_id,
        "display_name": _display_name(digest, canonical_asset_id),
        "trade_date": trade_date,
        "score_version": score_version,
        "rank": rank,
        "score_total": _optional_float(row.get("score_total")),
        "digest_score": digest_score,
        "bucket": bucket,
        "source_kinds": _source_kinds(facts),
        "risk_count": len(risk_flags),
        "warning_count": len(warnings),
        "next_action_count": len(next_actions),
        "digest": digest,
    }


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
