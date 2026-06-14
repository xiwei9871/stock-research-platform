from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from stock_research.dashboard.asset_profile import build_asset_profile
from stock_research.dashboard.market_monitor import build_market_monitor_eod
from stock_research.dashboard.news import load_public_news_for_dashboard
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.research_reports import list_research_reports


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
        warnings.append("market date unavailable")
    profile = build_asset_profile(
        asset_id=asset_id,
        trade_date=selected_trade_date,
        start_date=start_date,
        end_date=selected_trade_date,
        score_version=score_version,
    )
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

    return {
        "asset_id": asset_id,
        "canonical_asset_id": canonical_asset_id,
        "trade_date": selected_trade_date,
        "title": title,
        "score": score,
        "bucket": bucket,
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
        warnings.append(f"platform summary unavailable: {exc}")
        return ""
    latest_market_date = str(summary.get("latest_market_date") or "")
    return latest_market_date


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
        warnings.append(f"{label} unavailable: {exc}")
        return {"summary": {}, "items": [], "warnings": []}
    if isinstance(payload, dict):
        return payload
    warnings.append(f"{label} unavailable: invalid payload")
    return {"summary": {}, "items": [], "warnings": []}


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
