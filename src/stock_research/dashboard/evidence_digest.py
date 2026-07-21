from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from stock_research.data_run_manifest import load_latest_data_run_manifest
from stock_research.dashboard.asset_profile import build_asset_profile
from stock_research.dashboard.display_date_gate import resolve_default_trade_date
from stock_research.dashboard.market_monitor import build_market_monitor_eod
from stock_research.dashboard.news import load_public_news_for_dashboard
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.research_reports import list_research_reports

SECTION_KEYS = [
    "asset_profile",
    "score_snapshot",
    "factor_contributions",
    "strategy_context",
    "market_monitor",
    "news",
    "research_reports",
    "lhb",
    "industry",
    "financial",
    "technical_features",
    "generated_reports",
    "operator_history",
    "follow_up_history",
    "risk_flags",
]


def build_evidence_digest(
    asset_id: str,
    *,
    trade_date: str | None = None,
    lookback_days: int = 90,
    score_version: str = "manual_v1",
) -> dict[str, Any]:
    warnings: list[str] = []
    selected_trade_date = _selected_trade_date(trade_date, score_version, warnings)
    bounded_lookback_days = _bounded_lookback_days(lookback_days)
    start_date = _start_date(selected_trade_date, bounded_lookback_days)
    news_start_date = _start_date(selected_trade_date, min(bounded_lookback_days, 7))
    if not selected_trade_date:
        if "market date unavailable" not in warnings:
            warnings.append("market date unavailable")
        return _unavailable_evidence_digest(asset_id, score_version, warnings)
    try:
        profile = build_asset_profile(
            asset_id=asset_id,
            trade_date=selected_trade_date,
            start_date=start_date,
            end_date=selected_trade_date,
            score_version=score_version,
        )
    except Exception as exc:
        profile = {
            "asset_id": asset_id,
            "canonical_asset_id": asset_id,
            "asset": None,
            "score": {},
            "signals": [],
            "decisions": [],
            "outcomes": [],
            "factor_values": [],
            "coverage": {},
        }
        warnings.append(f"asset profile unavailable: {exc}")
    canonical_asset_id = str(profile.get("canonical_asset_id") or asset_id)
    asset = profile.get("asset") or {}
    score_row = profile.get("score") or {}
    score = _evidence_score(score_row)

    news = (
        _load_optional(
            warnings,
            "news",
            _load_news_for_digest,
            asset_id=canonical_asset_id,
            start_time=news_start_date,
            end_time=_end_of_day_time(selected_trade_date),
            limit=5,
        )
        if selected_trade_date
        else _empty_optional_source()
    )
    reports = (
        _load_optional(
            warnings,
            "research",
            _load_research_for_digest,
            asset_id=canonical_asset_id,
            start_date=start_date,
            end_date=selected_trade_date,
            limit=5,
        )
        if selected_trade_date
        else _empty_optional_source()
    )
    market = (
        _load_optional(
            warnings,
            "market",
            build_market_monitor_eod,
            trade_date=selected_trade_date,
            score_version=score_version,
            top_n=5,
        )
        if selected_trade_date
        else _empty_market_source()
    )

    facts: list[dict[str, Any]] = []
    risk_flags: list[dict[str, Any]] = []
    source_refs: dict[str, Any] = {}
    next_actions: list[dict[str, Any]] = []

    _add_strategy_evidence(profile, canonical_asset_id, facts, risk_flags, source_refs, next_actions)
    _add_news_evidence(news, facts, risk_flags, source_refs, next_actions)
    _add_research_evidence(reports, facts, risk_flags, source_refs, next_actions)
    _add_market_evidence(canonical_asset_id, market, facts, risk_flags, source_refs, next_actions)
    _ensure_required_actions(canonical_asset_id, next_actions)

    warnings.extend(str(warning) for warning in (news.get("warnings") or []))
    warnings.extend(str(warning) for warning in (reports.get("warnings") or []))
    warnings.extend(str(warning) for warning in (market.get("warnings") or []))

    bucket = _bucket(score, facts, risk_flags)
    title = _title(bucket, asset, canonical_asset_id)
    manifest = _manifest_context(selected_trade_date)
    warnings.extend(manifest["warnings"])
    sections = _build_sections(
        asset_id=canonical_asset_id,
        trade_date=selected_trade_date,
        score_version=score_version,
        profile=profile,
        news=news,
        reports=reports,
        market=market,
        risk_flags=risk_flags,
        manifest_modules=manifest["modules"],
    )
    missing_evidence = _evidence_by_status(sections, {"missing", "error"})
    partial_evidence = _evidence_by_status(sections, {"partial", "unavailable"})
    overall_status = _overall_status(sections, missing_evidence, partial_evidence)
    digest_key = _digest_key(selected_trade_date, score_version, canonical_asset_id)

    return {
        "asset_id": asset_id,
        "canonical_asset_id": canonical_asset_id,
        "stock_code": canonical_asset_id,
        "stock_name": str(asset.get("name") or asset.get("display_name") or asset.get("asset_name") or ""),
        "trade_date": selected_trade_date,
        "latest_trade_date": manifest["latest_trade_date"] or selected_trade_date,
        "run_id": manifest["run_id"],
        "digest_key": digest_key,
        "generated_at": _generated_at(selected_trade_date),
        "overall_status": overall_status,
        "title": title,
        "score": score,
        "bucket": bucket,
        "sections": sections,
        "missing_evidence": missing_evidence,
        "partial_evidence": partial_evidence,
        "lineage": {
            "run_id": manifest["run_id"],
            "latest_trade_date": manifest["latest_trade_date"] or selected_trade_date,
            "score_version": score_version,
            "topn_rank": _to_int(score_row.get("rank")),
            "score": _to_float(score_row.get("score_total")),
            "factor_as_of": selected_trade_date,
            "manifest_modules": manifest["modules"],
        },
        "errors": _section_errors(sections),
        "facts": facts,
        "risk_flags": risk_flags,
        "source_refs": source_refs,
        "next_actions": next_actions,
        "warnings": warnings,
    }


def _selected_trade_date(trade_date: str | None, score_version: str, warnings: list[str]) -> str:
    if trade_date:
        return trade_date
    try:
        summary = load_platform_summary(score_version=score_version, top_n=5)
    except Exception as exc:
        warnings.append(f"platform summary unavailable: {type(exc).__name__}")
        return ""
    resolution = resolve_default_trade_date(summary)
    warning = str(resolution.get("warning") or "")
    if warning:
        warnings.append(warning)
    return str(resolution.get("trade_date") or "")


def _unavailable_evidence_digest(
    asset_id: str,
    score_version: str,
    warnings: list[str],
) -> dict[str, Any]:
    empty_profile = {
        "asset": None,
        "score": {},
        "signals": [],
        "decisions": [],
        "outcomes": [],
        "factor_values": [],
    }
    sections = _build_sections(
        asset_id=asset_id,
        trade_date="",
        score_version=score_version,
        profile=empty_profile,
        news=_empty_optional_source(),
        reports=_empty_optional_source(),
        market=_empty_market_source(),
        risk_flags=[],
        manifest_modules=[],
    )
    missing_evidence = _evidence_by_status(sections, {"missing", "error"})
    partial_evidence = _evidence_by_status(sections, {"partial", "unavailable"})
    return {
        "asset_id": asset_id,
        "canonical_asset_id": asset_id,
        "stock_code": asset_id,
        "stock_name": "",
        "trade_date": "",
        "latest_trade_date": "",
        "run_id": "",
        "digest_key": _digest_key("", score_version, asset_id),
        "generated_at": "",
        "overall_status": "BLOCKED",
        "title": _title("thin", {}, asset_id),
        "score": 0,
        "bucket": "thin",
        "sections": sections,
        "missing_evidence": missing_evidence,
        "partial_evidence": partial_evidence,
        "lineage": {
            "run_id": "",
            "latest_trade_date": "",
            "score_version": score_version,
            "topn_rank": None,
            "score": None,
            "factor_as_of": "",
            "manifest_modules": [],
        },
        "errors": _section_errors(sections),
        "facts": [],
        "risk_flags": [],
        "source_refs": {},
        "next_actions": [],
        "warnings": list(dict.fromkeys(warnings)),
    }


def _start_date(end_date: str, lookback_days: int) -> str:
    if not end_date:
        return ""
    try:
        parsed = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return end_date
    return (parsed - timedelta(days=_bounded_lookback_days(lookback_days) - 1)).isoformat()


def _end_of_day_time(trade_date: str) -> str:
    if not trade_date:
        return ""
    try:
        datetime.strptime(trade_date, "%Y-%m-%d")
    except ValueError:
        return trade_date
    return f"{trade_date}T23:59:59+08:00"


def _bounded_lookback_days(lookback_days: int) -> int:
    try:
        return max(1, int(lookback_days or 90))
    except (TypeError, ValueError):
        return 90


def _empty_optional_source() -> dict[str, Any]:
    return {"summary": {}, "items": [], "warnings": []}


def _empty_market_source() -> dict[str, Any]:
    return {
        "emotion_stock_lists": {"auction": [], "limit_up": [], "broken_limit_up": [], "limit_down": []},
        "warnings": [],
    }


def _generated_at(selected_trade_date: str) -> str:
    if not selected_trade_date:
        return ""
    return f"{selected_trade_date}T00:00:00+00:00"


def _digest_key(trade_date: str, score_version: str, asset_id: str) -> str:
    return f"{trade_date}:{score_version}:{asset_id}"


def _manifest_context(trade_date: str) -> dict[str, Any]:
    if not trade_date:
        return {"run_id": "", "latest_trade_date": "", "modules": [], "warnings": []}
    try:
        modules = list(load_latest_data_run_manifest(trade_date=trade_date))
    except Exception as exc:
        return {
            "run_id": "",
            "latest_trade_date": trade_date,
            "modules": [],
            "warnings": [f"data run manifest unavailable: {exc}"],
        }
    run_id = ""
    latest_trade_date = trade_date
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
    return {
        "run_id": run_id,
        "latest_trade_date": latest_trade_date,
        "modules": normalized,
        "warnings": [],
    }


def _build_sections(
    *,
    asset_id: str,
    trade_date: str,
    score_version: str,
    profile: dict[str, Any],
    news: dict[str, Any],
    reports: dict[str, Any],
    market: dict[str, Any],
    risk_flags: list[dict[str, Any]],
    manifest_modules: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    asset = profile.get("asset") if isinstance(profile.get("asset"), dict) else None
    score_row = profile.get("score") if isinstance(profile.get("score"), dict) else {}
    factor_values = list(profile.get("factor_values") or [])
    signals = list(profile.get("signals") or [])
    decisions = list(profile.get("decisions") or [])
    outcomes = list(profile.get("outcomes") or [])
    stock_lists = market.get("emotion_stock_lists") if isinstance(market, dict) else {}
    market_items = [
        item
        for tab in ("auction", "limit_up", "broken_limit_up", "limit_down")
        for item in (stock_lists or {}).get(tab, [])
        if isinstance(item, dict) and (item.get("asset_id") == asset_id or item.get("symbol") == asset_id[:6])
    ]
    sections = {
        "asset_profile": _section(
            status="available" if asset else "missing",
            as_of=trade_date,
            source="asset_profile",
            item_count=1 if asset else 0,
            data=asset or {},
        ),
        "score_snapshot": _section(
            status="available" if score_row else "missing",
            as_of=str(score_row.get("trade_date") or trade_date) if score_row else trade_date,
            source=f"score:{score_version}",
            item_count=1 if score_row else 0,
            data=score_row or {},
        ),
        "factor_contributions": _section(
            status="available" if factor_values else "skipped",
            as_of=trade_date,
            source="factor.factor_daily",
            item_count=len(factor_values),
            data={"items": factor_values},
        ),
        "strategy_context": _section(
            status="available" if signals else "skipped",
            as_of=trade_date,
            source="watchlist_signals",
            item_count=len(signals),
            data={"items": signals},
        ),
        "market_monitor": _section(
            status=_market_section_status(market, market_items),
            as_of=trade_date,
            source="market_monitor_eod",
            item_count=len(market_items),
            warnings=list(market.get("warnings") or []) if isinstance(market, dict) else [],
            data={"items": market_items},
        ),
        "news": _optional_section("news", news, trade_date, "public_news"),
        "research_reports": _optional_section("research_reports", reports, trade_date, "research_reports"),
        "lhb": _manifest_or_skipped_section("lhb", trade_date, manifest_modules),
        "industry": _manifest_or_skipped_section("industry", trade_date, manifest_modules),
        "financial": _manifest_or_skipped_section("financial", trade_date, manifest_modules),
        "technical_features": _manifest_or_skipped_section("technical_features", trade_date, manifest_modules),
        "generated_reports": _manifest_or_skipped_section("generated_reports", trade_date, manifest_modules),
        "operator_history": _section(
            status="available" if decisions else "skipped",
            as_of=trade_date,
            source="operator_decision_event",
            item_count=len(decisions),
            data={"items": decisions},
        ),
        "follow_up_history": _section(
            status="available" if outcomes else "skipped",
            as_of=trade_date,
            source="operator_decision_outcome_event",
            item_count=len(outcomes),
            data={"items": outcomes},
        ),
        "risk_flags": _section(
            status="available" if risk_flags else "skipped",
            as_of=trade_date,
            source="evidence_digest",
            item_count=len(risk_flags),
            data={"items": risk_flags},
        ),
    }
    return {key: sections[key] for key in SECTION_KEYS}


def _section(
    *,
    status: str,
    as_of: str,
    source: str,
    item_count: int,
    warnings: list[str] | None = None,
    error_message: str = "",
    data: dict[str, Any] | None = None,
    artifact_path: str = "",
) -> dict[str, Any]:
    return {
        "status": status,
        "as_of": as_of,
        "source": source,
        "item_count": item_count,
        "warnings": [str(warning) for warning in (warnings or []) if str(warning)],
        "error_message": error_message,
        "data": data or {},
        "artifact_path": artifact_path,
    }


def _optional_section(key: str, payload: dict[str, Any], trade_date: str, source: str) -> dict[str, Any]:
    items = list(payload.get("items") or []) if isinstance(payload, dict) else []
    warnings = list(payload.get("warnings") or []) if isinstance(payload, dict) else []
    error_warning = next((str(warning) for warning in warnings if "unavailable" in str(warning)), "")
    if error_warning:
        status = "partial"
        error_message = error_warning
    elif items:
        status = "available"
        error_message = ""
    else:
        status = "missing"
        error_message = ""
    return _section(
        status=status,
        as_of=trade_date,
        source=source,
        item_count=len(items),
        warnings=[str(warning) for warning in warnings],
        error_message=error_message,
        data={"summary": payload.get("summary") or {}, "items": items} if isinstance(payload, dict) else {},
    )


def _market_section_status(market: dict[str, Any], matched_items: list[dict[str, Any]]) -> str:
    warnings = list(market.get("warnings") or []) if isinstance(market, dict) else []
    if any("unavailable" in str(warning) for warning in warnings):
        return "partial"
    if matched_items:
        return "available"
    return "missing"


def _manifest_or_skipped_section(
    module: str,
    trade_date: str,
    manifest_modules: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = _find_manifest_module(module, manifest_modules)
    if not manifest:
        return _section(status="skipped", as_of=trade_date, source=module, item_count=0)
    return _manifest_section(module, trade_date, manifest)


def _manifest_or_unavailable_section(
    module: str,
    trade_date: str,
    manifest_modules: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = _find_manifest_module(module, manifest_modules)
    if not manifest:
        return _section(
            status="unavailable",
            as_of=trade_date,
            source=module,
            item_count=0,
            warnings=[f"{module} evidence not connected to digest v1"],
        )
    return _manifest_section(module, trade_date, manifest)


def _manifest_section(module: str, trade_date: str, manifest: dict[str, Any]) -> dict[str, Any]:
    status = str(manifest.get("status") or "unavailable")
    section_status = {
        "success": "available",
        "partial": "partial",
        "skipped": "skipped",
        "failed": "unavailable",
        "unavailable": "unavailable",
    }.get(status, "unavailable")
    return _section(
        status=section_status,
        as_of=trade_date,
        source=module,
        item_count=0,
        warnings=[str(warning) for warning in manifest.get("warnings") or []],
        error_message=str(manifest.get("error_message") or ""),
        artifact_path=str(manifest.get("artifact_path") or ""),
        data={"manifest": manifest},
    )


def _find_manifest_module(module: str, manifest_modules: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in manifest_modules:
        if item.get("module") == module:
            return item
    return None


def _evidence_by_status(sections: dict[str, dict[str, Any]], statuses: set[str]) -> list[str]:
    ignored = {"factor_contributions", "strategy_context", "operator_history", "follow_up_history", "risk_flags"}
    return [
        key
        for key, section in sections.items()
        if key not in ignored and section.get("status") in statuses
    ]


def _overall_status(
    sections: dict[str, dict[str, Any]],
    missing_evidence: list[str],
    partial_evidence: list[str],
) -> str:
    if sections["asset_profile"]["status"] in {"missing", "error"}:
        return "BLOCKED"
    if sections["score_snapshot"]["status"] in {"missing", "error"}:
        return "BLOCKED"
    blocking_missing = [item for item in missing_evidence if item in {"asset_profile", "score_snapshot"}]
    if blocking_missing:
        return "BLOCKED"
    if missing_evidence or partial_evidence:
        return "PARTIAL"
    return "OK"


def _section_errors(sections: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for key, section in sections.items():
        error = str(section.get("error_message") or "")
        if error:
            errors.append(f"{key}: {error}")
    return errors


def _load_news_for_digest(
    *,
    asset_id: str,
    start_time: str,
    end_time: str,
    limit: int,
) -> dict[str, Any]:
    payload = load_public_news_for_dashboard(
        asset_id=asset_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    if not isinstance(payload, dict):
        return payload
    return {
        "asset_id": asset_id,
        "summary": payload.get("summary") or {},
        "items": list(payload.get("items") or []),
        "warnings": list(payload.get("warnings") or []),
    }


def _load_research_for_digest(
    *,
    asset_id: str,
    start_date: str,
    end_date: str,
    limit: int,
) -> dict[str, Any]:
    payload = list_research_reports(
        asset_id=asset_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if not isinstance(payload, dict):
        return payload
    items = list(payload.get("items") or [])
    summary = dict(payload.get("summary") or {})
    if not summary:
        latest = items[0] if items else {}
        summary = {
            "report_count_30d": _recent_research_count(items, end_date, 30),
            "report_count_90d": int(payload.get("total") or len(items)),
            "broker_coverage_count_90d": len(
                {str(item.get("broker") or "") for item in items if item.get("broker")}
            ),
            "latest_report_date": latest.get("publish_date") or latest.get("report_date"),
            "latest_rating": str(latest.get("rating") or ""),
            "latest_target_price": latest.get("target_price"),
        }
    return {
        "asset_id": asset_id,
        "summary": summary,
        "items": items,
        "warnings": list(payload.get("warnings") or []),
    }


def _recent_research_count(items: list[dict[str, Any]], end_date: str, days: int) -> int:
    start_date = _start_date(end_date, days)
    if not start_date or not end_date:
        return 0
    count = 0
    for item in items:
        publish_date = str(item.get("publish_date") or item.get("report_date") or "")[:10]
        if start_date <= publish_date <= end_date:
            count += 1
    return count


def _load_optional(
    warnings: list[str],
    label: str,
    loader: Any,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    try:
        payload = loader(*args, **kwargs)
    except Exception as exc:
        warning = f"{label} unavailable: {exc}"
        warnings.append(warning)
        return {"summary": {}, "items": [], "warnings": [warning]}
    if isinstance(payload, dict):
        return payload
    warning = f"{label} unavailable: invalid payload"
    warnings.append(warning)
    return {"summary": {}, "items": [], "warnings": [warning]}


def _evidence_score(score_row: dict[str, Any]) -> int:
    rank = _to_int(score_row.get("rank"))
    if rank is not None:
        return max(0, min(100, 100 - rank + 1))
    score_total = _to_float(score_row.get("score_total"))
    if score_total is not None:
        return round(max(0.0, min(100.0, score_total)))
    return 0


def _add_strategy_evidence(
    profile: dict[str, Any],
    asset_id: str,
    facts: list[dict[str, Any]],
    risk_flags: list[dict[str, Any]],
    source_refs: dict[str, Any],
    next_actions: list[dict[str, Any]],
) -> None:
    source_refs["strategy_asset_id"] = asset_id
    next_actions.append(
        {
            "key": "review_stock",
            "label": "Review stock",
            "workspace": "stock",
            "asset_id": asset_id,
            "query": asset_id,
        }
    )

    score_row = profile.get("score") or {}
    rank = _to_int(score_row.get("rank"))
    if rank is not None:
        facts.append(
            {
                "kind": "strategy",
                "key": "score_rank",
                "label": "Strategy score rank",
                "value": rank,
            }
        )

    risk_tags = sorted(
        {
            str(tag)
            for signal in (profile.get("signals") or [])
            for tag in (signal.get("risk_tags") or [])
            if tag
        }
    )
    if risk_tags:
        risk_flags.append(
            {
                "key": "strategy_risk_tags",
                "severity": "medium",
                "label": "Strategy risk tags present",
                "value": risk_tags,
            }
        )


def _add_news_evidence(
    news: dict[str, Any],
    facts: list[dict[str, Any]],
    risk_flags: list[dict[str, Any]],
    source_refs: dict[str, Any],
    next_actions: list[dict[str, Any]],
) -> None:
    summary = news.get("summary") or {}
    items = list(news.get("items") or [])
    news_count = int(summary.get("news_count_7d") or len(items))
    if items:
        first = items[0]
        news_id = first.get("news_id")
        if news_id:
            source_refs["news_id"] = news_id
        facts.append(
            {
                "kind": "news",
                "key": "latest_news",
                "label": str(first.get("title") or "Latest news"),
                "value": news_count,
                "published_at": first.get("published_at") or summary.get("latest_published_at"),
            }
        )
        action = {
            "key": "open_news",
            "label": "Open news",
        }
        if news_id:
            action["news_id"] = news_id
        next_actions.append(action)
    else:
        risk_flags.append(
            {
                "key": "low_news_coverage",
                "severity": "low",
                "label": "Low news coverage",
                "value": news_count,
            }
        )


def _add_research_evidence(
    reports: dict[str, Any],
    facts: list[dict[str, Any]],
    risk_flags: list[dict[str, Any]],
    source_refs: dict[str, Any],
    next_actions: list[dict[str, Any]],
) -> None:
    summary = reports.get("summary") or {}
    items = list(reports.get("items") or [])
    report_count = int(summary.get("report_count_90d") or len(items))
    if items:
        first = items[0]
        report_id = first.get("report_id")
        event_key = first.get("event_key")
        if report_id:
            source_refs["report_id"] = report_id
        if event_key:
            source_refs["event_key"] = event_key
        facts.append(
            {
                "kind": "research",
                "key": "latest_research",
                "label": str(first.get("report_title") or "Latest research"),
                "value": report_count,
                "rating": first.get("rating") or summary.get("latest_rating"),
                "target_price": first.get("target_price") or summary.get("latest_target_price"),
            }
        )
        action = {
            "key": "open_research",
            "label": "Open research",
        }
        if report_id:
            action["report_id"] = report_id
        if event_key:
            action["event_key"] = event_key
        next_actions.append(action)
    else:
        risk_flags.append(
            {
                "key": "thin_research",
                "severity": "low",
                "label": "Thin research coverage",
                "value": report_count,
            }
        )


def _add_market_evidence(
    asset_id: str,
    market: dict[str, Any],
    facts: list[dict[str, Any]],
    risk_flags: list[dict[str, Any]],
    source_refs: dict[str, Any],
    next_actions: list[dict[str, Any]],
) -> None:
    stock_lists = market.get("emotion_stock_lists") or {}
    for tab in ("limit_up", "broken_limit_up", "limit_down", "auction"):
        match = _find_market_item(asset_id, stock_lists.get(tab) or [])
        if not match:
            continue
        if tab:
            source_refs["monitor_tab"] = tab
        if tab == "limit_down":
            risk_flags.append(
                {
                    "key": "market_limit_down",
                    "severity": "severe",
                    "label": "Market limit-down pressure",
                    "value": match.get("pct_chg"),
                }
            )
        elif tab == "broken_limit_up":
            risk_flags.append(
                {
                    "key": "market_broken_limit_up",
                    "severity": "medium",
                    "label": "Broken limit-up pressure",
                    "value": match.get("pct_chg"),
                }
            )
        else:
            facts.append(
                {
                    "kind": "market",
                    "key": f"market_{tab}",
                    "label": f"Market monitor: {tab}",
                    "value": match.get("pct_chg"),
                    "amount": match.get("amount"),
                }
            )
        action = {
            "key": "open_market",
            "label": "Open market monitor",
        }
        if tab:
            action["monitor_tab"] = tab
        next_actions.append(action)
        return


def _find_market_item(asset_id: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    symbol = asset_id[:6]
    for item in items:
        if item.get("asset_id") == asset_id or item.get("symbol") == symbol:
            return item
    return None


def _ensure_required_actions(asset_id: str, next_actions: list[dict[str, Any]]) -> None:
    required = {
        "open_news": {"label": "Open news", "workspace": "news"},
        "open_research": {"label": "Open research", "workspace": "researchReports"},
        "open_market": {"label": "Open market monitor", "workspace": "market"},
        "review_stock": {"label": "Review stock", "workspace": "stock"},
    }
    actions_by_key = {
        str(action.get("key")): action
        for action in next_actions
        if action.get("key") in required
    }
    for key, defaults in required.items():
        action = actions_by_key.get(key)
        if action is None:
            action = {"key": key}
            next_actions.append(action)
        action.setdefault("label", defaults["label"])
        if key == "open_research":
            action["workspace"] = defaults["workspace"]
        else:
            action.setdefault("workspace", defaults["workspace"])
        action.setdefault("asset_id", asset_id)
        action.setdefault("query", asset_id)


def _bucket(score: int, facts: list[dict[str, Any]], risk_flags: list[dict[str, Any]]) -> str:
    has_severe_risk = any(flag.get("severity") == "severe" for flag in risk_flags)
    if has_severe_risk or len(risk_flags) >= 3:
        return "risk_heavy"
    source_categories = {
        fact.get("kind")
        for fact in facts
        if fact.get("kind") in {"news", "research", "market"}
    }
    if score >= 75 and len(source_categories) >= 2:
        return "strong"
    if score >= 45 and len(source_categories) >= 2:
        return "mixed"
    return "thin"


def _title(bucket: str, asset: dict[str, Any], asset_id: str) -> str:
    name = str(asset.get("name") or asset.get("symbol") or asset_id)
    labels = {
        "strong": "Strong evidence",
        "mixed": "Mixed evidence",
        "risk_heavy": "Risk-heavy evidence",
        "thin": "Thin evidence",
    }
    return f"{labels[bucket]}: {name}"


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
