from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.research_evidence_registry import (
    evidence_from_digest_snapshot,
    evidence_from_review_item_snapshot,
    upsert_evidence_artifact,
)
from stock_research.research_objects import (
    stable_id,
    upsert_evidence_link,
    upsert_research_case,
    upsert_research_claim,
)


SOURCE_TYPES = {"review_item_snapshot", "evidence_digest_snapshot", "all"}


def case_id_from_review_snapshot(row: dict[str, Any]) -> str:
    return stable_id("research_case", "review_item_snapshot", _text(row.get("snapshot_id")))


def case_from_review_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("review_item_payload") if isinstance(row.get("review_item_payload"), dict) else {}
    source_type = _text(row.get("source_type")) or "review_item_snapshot"
    source_name = _text(row.get("source_name")) or source_type
    display_name = _text(payload.get("display_name") or row.get("stock_name") or row.get("asset_id"))
    return {
        "case_id": case_id_from_review_snapshot(row),
        "trade_date": _optional_date(row.get("trade_date")),
        "asset_id": _text(row.get("asset_id")),
        "theme": source_type,
        "title": f"{display_name} · {source_name}" if source_name else display_name,
        "status": "open",
        "priority": _priority_from_review(row),
        "source_type": "review_item_snapshot",
        "source_id": _text(row.get("snapshot_id")),
        "created_by": "research_case_seed_v1",
        "metadata": {
            "run_id": _text(row.get("run_id")),
            "digest_key": _text(row.get("digest_key")),
            "source_type": source_type,
            "source_name": source_name,
            "score": _optional_float(row.get("score")),
            "evidence_status": _text(row.get("evidence_status")),
            "missing_evidence_count": _int(row.get("missing_evidence_count")),
            "partial_evidence_count": _int(row.get("partial_evidence_count")),
            "warnings_count": _int(row.get("warnings_count")),
        },
    }


def claims_from_review_snapshot(row: dict[str, Any], case_id: str) -> list[dict[str, Any]]:
    payload = row.get("review_item_payload") if isinstance(row.get("review_item_payload"), dict) else {}
    source_id = _text(row.get("snapshot_id"))
    claims: list[dict[str, Any]] = []

    summary = _first_text(
        payload.get("summary"),
        payload.get("reason"),
        payload.get("evidence_summary"),
        payload.get("display_reason"),
    )
    if summary:
        claims.append(_claim(case_id, "summary", summary, source_type="review_item_snapshot", source_id=source_id))

    score = _optional_float(row.get("score") if row.get("score") is not None else payload.get("score"))
    source_name = _text(row.get("source_name") or payload.get("source_name"))
    if score is not None:
        text = f"{source_name or 'review queue'} score={score:g}"
        claims.append(
            _claim(
                case_id,
                "opportunity",
                text,
                confidence=_confidence_from_score(score),
                source_type="review_item_snapshot",
                source_id=source_id,
            )
        )

    missing = _int(row.get("missing_evidence_count"))
    partial = _int(row.get("partial_evidence_count"))
    status = _text(row.get("evidence_status"))
    if missing or partial or status:
        text = f"evidence_status={status or 'unknown'}, missing={missing}, partial={partial}"
        claims.append(_claim(case_id, "risk", text, source_type="review_item_snapshot", source_id=source_id))

    catalyst = _first_text(payload.get("catalyst"), payload.get("next_action"), payload.get("next_actions"))
    if catalyst:
        claims.append(_claim(case_id, "catalyst", catalyst, source_type="review_item_snapshot", source_id=source_id))

    return claims


def claims_from_digest_snapshot(row: dict[str, Any], case_id: str) -> list[dict[str, Any]]:
    payload = row.get("digest_payload") if isinstance(row.get("digest_payload"), dict) else {}
    source_id = _text(row.get("snapshot_id"))
    claims: list[dict[str, Any]] = []

    summary = _first_text(payload.get("summary"), payload.get("title"), payload.get("bucket"), row.get("overall_status"))
    if summary:
        claims.append(_claim(case_id, "summary", summary, source_type="evidence_digest_snapshot", source_id=source_id))

    score = _optional_float(payload.get("score"))
    bucket = _text(payload.get("bucket"))
    if score is not None or bucket:
        parts = []
        if bucket:
            parts.append(f"bucket={bucket}")
        if score is not None:
            parts.append(f"score={score:g}")
        claims.append(
            _claim(
                case_id,
                "opportunity",
                ", ".join(parts),
                confidence=_confidence_from_score(score) if score is not None else None,
                source_type="evidence_digest_snapshot",
                source_id=source_id,
            )
        )

    missing = _text_list(row.get("missing_evidence"))
    partial = _text_list(row.get("partial_evidence"))
    status = _text(row.get("overall_status"))
    if missing or partial or status:
        text = f"overall_status={status or 'unknown'}, missing={','.join(missing) or 'none'}, partial={','.join(partial) or 'none'}"
        claims.append(_claim(case_id, "risk", text, source_type="evidence_digest_snapshot", source_id=source_id))

    catalyst = _first_text(payload.get("catalyst"), payload.get("next_action"), payload.get("next_actions"))
    if catalyst:
        claims.append(_claim(case_id, "catalyst", catalyst, source_type="evidence_digest_snapshot", source_id=source_id))

    return claims


def run_research_case_seed(
    *,
    trade_date: str | None = None,
    source_type: str = "all",
    dry_run: bool = False,
    limit: int = 100,
    output_dir: str | Path = "outputs/research",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    source_type = source_type or "all"
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"invalid_source_type:{source_type}")

    limit_value = _clamp_limit(limit)
    summary = _empty_summary(trade_date=trade_date, source_type=source_type, dry_run=dry_run)
    review_rows = _load_review_rows(trade_date=trade_date, limit=limit_value, service=service) if source_type in {"review_item_snapshot", "all"} else []
    digest_rows = _load_digest_rows(trade_date=trade_date, limit=limit_value, service=service) if source_type in {"evidence_digest_snapshot", "all"} else []
    summary["scanned"]["review_item_snapshot"] = len(review_rows)
    summary["scanned"]["evidence_digest_snapshot"] = len(digest_rows)

    case_by_digest_key = _existing_case_lookup(trade_date=trade_date, service=service) if source_type == "evidence_digest_snapshot" else {}
    for row in review_rows:
        case = case_from_review_snapshot(dict(row))
        case_by_digest_key[_text(row.get("digest_key"))] = case["case_id"]
        review_evidence = evidence_from_review_item_snapshot(dict(row))
        review_claims = claims_from_review_snapshot(dict(row), case["case_id"])
        _apply_case_plan(
            case=case,
            evidence=review_evidence,
            claims=review_claims,
            summary=summary,
            dry_run=dry_run,
            service=service,
        )

    for row in digest_rows:
        digest_key = _text(row.get("digest_key"))
        case_id = case_by_digest_key.get(digest_key)
        if not case_id:
            summary["skipped"]["unmatched_digest"] += 1
            if len(summary["unmatched_digest_samples"]) < 5:
                summary["unmatched_digest_samples"].append(
                    {
                        "snapshot_id": _text(row.get("snapshot_id")),
                        "digest_key": digest_key,
                        "asset_id": _text(row.get("asset_id")),
                        "reason": "no_review_item_case",
                    }
                )
            continue
        summary["digest_matched_cases"] += 1
        digest_evidence = evidence_from_digest_snapshot(dict(row))
        digest_claims = claims_from_digest_snapshot(dict(row), case_id)
        _apply_supplement_plan(
            case_id=case_id,
            evidence=digest_evidence,
            claims=digest_claims,
            summary=summary,
            dry_run=dry_run,
            service=service,
        )

    paths = write_research_case_seed_summary(summary, output_dir=output_dir)
    summary.update(paths)
    return summary


def run_research_case_seed_idempotency_audit(
    *,
    trade_date: str | None = None,
    source_type: str = "all",
    limit: int = 100,
    output_dir: str | Path = "outputs/research/research_case_seed_idempotency_audit_v1",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    before = _load_audit_counts(service=service)
    seed_summary = run_research_case_seed(
        trade_date=trade_date,
        source_type=source_type,
        dry_run=False,
        limit=limit,
        output_dir=output_dir,
        service=service,
    )
    after = _load_audit_counts(service=service)
    count_delta = {
        key: _int(after.get(key)) - _int(before.get(key))
        for key in (
            "research_case_count",
            "research_claim_count",
            "evidence_artifact_count",
            "evidence_link_count",
        )
    }
    inserted = {
        "research_case": max(0, count_delta["research_case_count"]),
        "research_claim": max(0, count_delta["research_claim_count"]),
        "evidence_artifact": max(0, count_delta["evidence_artifact_count"]),
        "evidence_link": max(0, count_delta["evidence_link_count"]),
    }
    planned_evidence_artifacts = _int(seed_summary.get("scanned", {}).get("review_item_snapshot")) + _int(
        seed_summary.get("digest_matched_cases")
    )
    summary = {
        "trade_date": trade_date or "",
        "source_type": source_type,
        "limit": _clamp_limit(limit),
        "before": before,
        "after": after,
        "count_delta": count_delta,
        "distinct_counts": {
            "case_id": _int(after.get("distinct_case_id_count")),
            "claim_id": _int(after.get("distinct_claim_id_count")),
            "evidence_id": _int(after.get("distinct_evidence_id_count")),
            "link_id": _int(after.get("distinct_link_id_count")),
        },
        "duplicate_logical_keys": {
            "research_case": _int(after.get("duplicate_case_logical_keys_count")),
            "research_claim": _int(after.get("duplicate_claim_logical_keys_count")),
            "evidence_artifact": _int(after.get("duplicate_evidence_logical_keys_count")),
            "evidence_link": _int(after.get("duplicate_link_logical_keys_count")),
        },
        "second_run": {
            "inserted": inserted,
            "updated_or_existing": {
                "research_case": max(0, _int(seed_summary.get("cases_upserted")) - inserted["research_case"]),
                "research_claim": max(0, _int(seed_summary.get("claims_upserted")) - inserted["research_claim"]),
                "evidence_artifact": max(0, planned_evidence_artifacts - inserted["evidence_artifact"]),
                "evidence_link": max(0, _int(seed_summary.get("evidence_links_upserted")) - inserted["evidence_link"]),
            },
            "skipped": seed_summary.get("skipped", {}),
            "errors": seed_summary.get("errors", []),
            "seed_summary": seed_summary,
        },
    }
    summary.update(write_research_case_seed_idempotency_audit_summary(summary, output_dir=output_dir))
    return summary


def write_research_case_seed_summary(summary: dict[str, Any], *, output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "research_case_seed_summary.json"
    markdown_path = output_path / "research_case_seed_summary.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_summary_markdown(summary), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def write_research_case_seed_idempotency_audit_summary(
    summary: dict[str, Any],
    *,
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "research_case_seed_idempotency_audit_summary.json"
    markdown_path = output_path / "research_case_seed_idempotency_audit_summary.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_audit_summary_markdown(summary), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def _load_audit_counts(*, service: str) -> dict[str, Any]:
    sql = """
    SELECT
        (SELECT count(*) FROM research.research_case) AS research_case_count,
        (SELECT count(*) FROM research.research_claim) AS research_claim_count,
        (SELECT count(*) FROM research.evidence_artifact) AS evidence_artifact_count,
        (SELECT count(*) FROM research.evidence_link) AS evidence_link_count,
        (SELECT count(DISTINCT case_id) FROM research.research_case) AS distinct_case_id_count,
        (SELECT count(DISTINCT claim_id) FROM research.research_claim) AS distinct_claim_id_count,
        (SELECT count(DISTINCT evidence_id) FROM research.evidence_artifact) AS distinct_evidence_id_count,
        (SELECT count(DISTINCT link_id) FROM research.evidence_link) AS distinct_link_id_count,
        (
            SELECT count(*) FROM (
                SELECT source_type, source_id
                FROM research.research_case
                GROUP BY source_type, source_id
                HAVING count(*) > 1
            ) duplicates
        ) AS duplicate_case_logical_keys_count,
        (
            SELECT count(*) FROM (
                SELECT case_id, claim_type, claim_text, metadata->>'source_type', metadata->>'source_id'
                FROM research.research_claim
                GROUP BY case_id, claim_type, claim_text, metadata->>'source_type', metadata->>'source_id'
                HAVING count(*) > 1
            ) duplicates
        ) AS duplicate_claim_logical_keys_count,
        (
            SELECT count(*) FROM (
                SELECT source_type, source_id
                FROM research.evidence_artifact
                GROUP BY source_type, source_id
                HAVING count(*) > 1
            ) duplicates
        ) AS duplicate_evidence_logical_keys_count,
        (
            SELECT count(*) FROM (
                SELECT evidence_id, target_type, target_id, relation
                FROM research.evidence_link
                GROUP BY evidence_id, target_type, target_id, relation
                HAVING count(*) > 1
            ) duplicates
        ) AS duplicate_link_logical_keys_count
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [])
    return dict(rows[0]) if rows else {}


def _apply_case_plan(
    *,
    case: dict[str, Any],
    evidence: dict[str, Any],
    claims: list[dict[str, Any]],
    summary: dict[str, Any],
    dry_run: bool,
    service: str,
) -> None:
    summary["cases_planned"] += 1
    if not dry_run:
        upsert_research_case(case, service=service)
        summary["cases_upserted"] += 1
    _apply_evidence_claim_link_plan(
        case_id=case["case_id"],
        evidence=evidence,
        claims=claims,
        summary=summary,
        dry_run=dry_run,
        service=service,
    )


def _apply_supplement_plan(
    *,
    case_id: str,
    evidence: dict[str, Any],
    claims: list[dict[str, Any]],
    summary: dict[str, Any],
    dry_run: bool,
    service: str,
) -> None:
    _apply_evidence_claim_link_plan(
        case_id=case_id,
        evidence=evidence,
        claims=claims,
        summary=summary,
        dry_run=dry_run,
        service=service,
    )


def _apply_evidence_claim_link_plan(
    *,
    case_id: str,
    evidence: dict[str, Any],
    claims: list[dict[str, Any]],
    summary: dict[str, Any],
    dry_run: bool,
    service: str,
) -> None:
    valid_claims = [claim for claim in claims if _text(claim.get("claim_text"))]
    summary["claims_planned"] += len(valid_claims)
    summary["skipped"]["missing_claim_text"] += len(claims) - len(valid_claims)
    summary["evidence_links_planned"] += 1 + len(valid_claims)
    if dry_run:
        return
    try:
        upsert_evidence_artifact(evidence, service=service)
        upsert_evidence_link(_link(evidence["evidence_id"], "research_case", case_id, evidence), service=service)
        summary["evidence_links_upserted"] += 1
        for claim in valid_claims:
            upsert_research_claim(claim, service=service)
            summary["claims_upserted"] += 1
            upsert_evidence_link(_link(evidence["evidence_id"], "research_claim", claim["claim_id"], evidence), service=service)
            summary["evidence_links_upserted"] += 1
    except Exception as exc:  # pragma: no cover - defensive around DB write errors.
        summary["errors"].append(
            {
                "evidence_id": _text(evidence.get("evidence_id")),
                "error": str(exc),
            }
        )


def _load_review_rows(*, trade_date: str | None, limit: int, service: str) -> list[dict[str, Any]]:
    clauses, params = _trade_date_filter(trade_date)
    params.append(limit)
    sql = f"""
    SELECT
        snapshot_id,
        run_id,
        trade_date::text AS trade_date,
        asset_id,
        stock_name,
        digest_key,
        source_type,
        source_name,
        source_rank,
        topn_rank,
        score,
        evidence_status,
        missing_evidence_count,
        partial_evidence_count,
        warnings_count,
        payload_hash,
        review_item_payload
    FROM ops.review_item_snapshot
    WHERE {" AND ".join(clauses)}
    ORDER BY trade_date DESC, updated_at DESC
    LIMIT %s
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, params)


def _load_digest_rows(*, trade_date: str | None, limit: int, service: str) -> list[dict[str, Any]]:
    clauses, params = _trade_date_filter(trade_date)
    params.append(limit)
    sql = f"""
    SELECT
        snapshot_id,
        run_id,
        trade_date::text AS trade_date,
        asset_id,
        stock_name,
        digest_key,
        overall_status,
        missing_evidence,
        partial_evidence,
        sections_status,
        payload_hash,
        digest_payload
    FROM ops.evidence_digest_snapshot
    WHERE {" AND ".join(clauses)}
    ORDER BY trade_date DESC, updated_at DESC
    LIMIT %s
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, params)


def _existing_case_lookup(*, trade_date: str | None, service: str) -> dict[str, str]:
    clauses = ["source_type = 'review_item_snapshot'"]
    params: list[Any] = []
    if trade_date:
        clauses.append("trade_date = %s")
        params.append(trade_date)
    sql = f"""
    SELECT case_id, metadata->>'digest_key' AS digest_key
    FROM research.research_case
    WHERE {" AND ".join(clauses)}
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return {_text(row.get("digest_key")): _text(row.get("case_id")) for row in rows if _text(row.get("digest_key"))}


def _trade_date_filter(trade_date: str | None) -> tuple[list[str], list[Any]]:
    if not trade_date:
        return ["1=1"], []
    return ["trade_date = %s"], [trade_date]


def _claim(
    case_id: str,
    claim_type: str,
    claim_text: str,
    *,
    confidence: float | None = None,
    source_type: str,
    source_id: str,
) -> dict[str, Any]:
    text = _text(claim_text)
    return {
        "claim_id": stable_id("research_claim", case_id, source_type, source_id, claim_type, text),
        "case_id": case_id,
        "claim_type": claim_type,
        "claim_text": text,
        "confidence": confidence,
        "status": "draft",
        "created_by": "research_case_seed_v1",
        "metadata": {"source_type": source_type, "source_id": source_id},
    }


def _link(evidence_id: str, target_type: str, target_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "target_type": target_type,
        "target_id": target_id,
        "relation": "supports",
        "metadata": {
            "source_type": evidence.get("source_type"),
            "source_id": evidence.get("source_id"),
            "seed_version": "research_case_seed_v1",
        },
    }


def _priority_from_review(row: dict[str, Any]) -> int:
    for key in ("source_rank", "topn_rank"):
        value = _optional_int(row.get(key))
        if value is not None:
            return max(1, value)
    score = _optional_float(row.get("score"))
    if score is not None:
        return max(1, min(100, int(round(100 - score))))
    return 50


def _confidence_from_score(score: float) -> float:
    value = score / 100 if score > 1 else score
    return round(max(0.0, min(1.0, value)), 4)


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list):
            text = " / ".join(str(item) for item in value if str(item).strip())
        else:
            text = str(value or "")
        text = text.strip()
        if text:
            return text
    return ""


def _text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _empty_summary(*, trade_date: str | None, source_type: str, dry_run: bool) -> dict[str, Any]:
    return {
        "trade_date": trade_date or "",
        "source_type": source_type,
        "scanned": {"review_item_snapshot": 0, "evidence_digest_snapshot": 0},
        "cases_planned": 0,
        "cases_upserted": 0,
        "claims_planned": 0,
        "claims_upserted": 0,
        "evidence_links_planned": 0,
        "evidence_links_upserted": 0,
        "digest_matched_cases": 0,
        "skipped": {"unmatched_digest": 0, "missing_claim_text": 0},
        "unmatched_digest_samples": [],
        "errors": [],
        "dry_run": bool(dry_run),
    }


def _summary_markdown(summary: dict[str, Any]) -> str:
    skipped = summary.get("skipped") or {}
    lines = [
        "# Research Case Seed Summary",
        "",
        f"- trade_date: {summary.get('trade_date') or ''}",
        f"- source_type: {summary.get('source_type') or ''}",
        f"- review_item_snapshot scanned: {(summary.get('scanned') or {}).get('review_item_snapshot', 0)}",
        f"- evidence_digest_snapshot scanned: {(summary.get('scanned') or {}).get('evidence_digest_snapshot', 0)}",
        f"- cases_planned: {summary.get('cases_planned')}",
        f"- cases_upserted: {summary.get('cases_upserted')}",
        f"- digest_matched_cases: {summary.get('digest_matched_cases')}",
        f"- claims_planned: {summary.get('claims_planned')}",
        f"- claims_upserted: {summary.get('claims_upserted')}",
        f"- evidence_links_planned: {summary.get('evidence_links_planned')}",
        f"- evidence_links_upserted: {summary.get('evidence_links_upserted')}",
        f"- skipped.unmatched_digest: {skipped.get('unmatched_digest', 0)}",
        f"- skipped.missing_claim_text: {skipped.get('missing_claim_text', 0)}",
        f"- dry_run: {summary.get('dry_run')}",
        f"- errors: {len(summary.get('errors') or [])}",
    ]
    samples = summary.get("unmatched_digest_samples") or []
    if samples:
        lines.append("")
        lines.append("## Unmatched Digest Samples")
        for sample in samples:
            lines.append(f"- {sample}")
    lines.append("")
    return "\n".join(lines)


def _audit_summary_markdown(summary: dict[str, Any]) -> str:
    second_run = summary.get("second_run") or {}
    lines = [
        "# Research Case Seed Idempotency Audit",
        "",
        f"- trade_date: {summary.get('trade_date') or ''}",
        f"- source_type: {summary.get('source_type') or ''}",
        f"- limit: {summary.get('limit')}",
        "",
        "## Count Delta",
    ]
    for key, value in (summary.get("count_delta") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Duplicate Logical Keys"])
    for key, value in (summary.get("duplicate_logical_keys") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Second Run"])
    for key, value in (second_run.get("inserted") or {}).items():
        lines.append(f"- inserted.{key}: {value}")
    for key, value in (second_run.get("updated_or_existing") or {}).items():
        lines.append(f"- updated_or_existing.{key}: {value}")
    lines.append(f"- skipped: {second_run.get('skipped') or {}}")
    lines.append(f"- errors: {len(second_run.get('errors') or [])}")
    lines.append("")
    return "\n".join(lines)


def _clamp_limit(value: int) -> int:
    return max(1, min(1000, int(value or 100)))


def _optional_date(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:10] if text else None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    return _optional_int(value) or 0


def _text(value: Any) -> str:
    return str(value or "").strip()
