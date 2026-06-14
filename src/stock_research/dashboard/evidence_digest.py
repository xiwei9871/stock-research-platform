from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from stock_research.dashboard.asset_profile import build_asset_profile
from stock_research.dashboard.market_monitor import build_market_monitor_eod
from stock_research.dashboard.news import load_asset_news
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.research_reports import load_asset_research_reports


def build_evidence_digest(
    asset_id: str,
    *,
    trade_date: str | None = None,
    lookback_days: int = 90,
    score_version: str = "manual_v1",
) -> dict[str, Any]:
    selected_trade_date = _selected_trade_date(trade_date, score_version)
    start_date = _start_date(selected_trade_date, lookback_days)
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

    warnings: list[str] = []
    news = _load_optional(
        warnings,
        "news",
        load_asset_news,
        canonical_asset_id,
        limit=5,
        lookback_days=min(max(int(lookback_days or 90), 1), 90),
    )
    reports = _load_optional(
        warnings,
        "research",
        load_asset_research_reports,
        canonical_asset_id,
        limit=5,
        lookback_days=lookback_days,
    )
    market = _load_optional(
        warnings,
        "market",
        build_market_monitor_eod,
        trade_date=selected_trade_date,
        score_version=score_version,
        top_n=5,
    )

    facts: list[dict[str, Any]] = []
    risk_flags: list[dict[str, Any]] = []
    source_refs: dict[str, Any] = {}
    next_actions: list[dict[str, Any]] = []

    _add_strategy_evidence(profile, facts, risk_flags)
    _add_news_evidence(news, facts, risk_flags, source_refs, next_actions)
    _add_research_evidence(reports, facts, risk_flags, source_refs, next_actions)
    _add_market_evidence(canonical_asset_id, market, facts, risk_flags, source_refs, next_actions)

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


def _selected_trade_date(trade_date: str | None, score_version: str) -> str:
    if trade_date:
        return trade_date
    summary = load_platform_summary(score_version=score_version, top_n=5)
    latest_market_date = str(summary.get("latest_market_date") or "")
    return latest_market_date or date.today().isoformat()


def _start_date(end_date: str, lookback_days: int) -> str:
    try:
        parsed = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return end_date
    try:
        bounded_lookback = max(1, int(lookback_days or 90))
    except (TypeError, ValueError):
        bounded_lookback = 90
    return (parsed - timedelta(days=bounded_lookback - 1)).isoformat()


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
    facts: list[dict[str, Any]],
    risk_flags: list[dict[str, Any]],
) -> None:
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
        source_refs["news_id"] = first.get("news_id")
        facts.append(
            {
                "kind": "news",
                "key": "latest_news",
                "label": str(first.get("title") or "Latest news"),
                "value": news_count,
                "published_at": first.get("published_at") or summary.get("latest_published_at"),
            }
        )
        next_actions.append(
            {
                "key": "open_news",
                "label": "Open news",
                "news_id": first.get("news_id"),
            }
        )
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
        source_refs["report_id"] = first.get("report_id")
        if first.get("event_key"):
            source_refs["event_key"] = first.get("event_key")
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
        next_actions.append(
            {
                "key": "open_research",
                "label": "Open research",
                "report_id": first.get("report_id"),
                "event_key": first.get("event_key"),
            }
        )
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
        next_actions.append(
            {
                "key": "open_market",
                "label": "Open market monitor",
                "monitor_tab": tab,
            }
        )
        return


def _find_market_item(asset_id: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    symbol = asset_id[:6]
    for item in items:
        if item.get("asset_id") == asset_id or item.get("symbol") == symbol:
            return item
    return None


def _bucket(score: int, facts: list[dict[str, Any]], risk_flags: list[dict[str, Any]]) -> str:
    if any(flag.get("severity") == "severe" for flag in risk_flags) or len(risk_flags) >= 3:
        return "risk_heavy"
    fact_categories = {fact.get("kind") for fact in facts if fact.get("kind")}
    if score >= 75:
        return "strong"
    if score >= 45 and len(fact_categories) >= 2:
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
