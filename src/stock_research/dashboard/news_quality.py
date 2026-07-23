from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from stock_research.public_news.models import PublicNewsItem

NEWS_QUALITY_THRESHOLD = 65
NEWS_MAX_ACCEPTED_PER_RUN = 3
NEWS_FRESHNESS_HOURS = 24
SOURCE_TIMEZONE = ZoneInfo("Asia/Shanghai")

LOW_SIGNAL_TOKENS = (
    "更多精彩",
    "点击查看",
    "滚动直播",
    "图文直播",
    "欢迎关注",
    "请关注",
)

TRADING_TOKENS = {
    "policy": ("政策", "监管", "发改委", "央行", "证监会", "关税", "制裁", "出口管制"),
    "sector_specific": (
        "半导体",
        "新能源",
        "机器人",
        "算力",
        "芯片",
        "有色",
        "军工",
        "医药",
        "地产",
        "消费",
        "产业链",
    ),
    "company_event": ("公告", "订单", "并购", "重组", "回购", "增持", "减持", "业绩", "中标"),
    "market_liquidity": (
        "逆回购",
        "流动性",
        "利率",
        "降准",
        "降息",
        "融资",
        "成交额",
        "资金面",
        "资金价格",
    ),
    "risk_event": ("调查", "处罚", "违约", "爆雷", "事故", "下调", "亏损", "退市"),
    "price_signal": ("涨价", "降价", "大涨", "大跌", "供给", "减产", "库存", "期货"),
}

A_SHARE_RELEVANCE_TOKENS = (
    "A股",
    "沪深",
    "上证",
    "深证",
    "创业板",
    "科创板",
    "北交所",
    "龙虎榜",
    "涨停",
    "跌停",
    "连板",
    "证监会",
    "交易所",
    "国家发改委",
    "发改委",
    "央行",
    "人民银行",
    "财政部",
    "商务部",
    "工信部",
    "中国",
    "国内",
)

DOMESTIC_SECTOR_TOKENS = (
    "半导体",
    "新能源",
    "机器人",
    "算力",
    "芯片",
    "有色",
    "军工",
    "医药",
    "地产",
    "消费",
    "产业链",
    "光伏",
    "锂电",
    "稀土",
)

OVERSEAS_ONLY_TOKENS = (
    "美股",
    "纳斯达克",
    "道指",
    "标普",
    "英特尔",
    "苹果",
    "SpaceX",
    "特斯拉",
    "英伟达",
    "美联储",
)

CATEGORY_SCORE = {
    "live": 18,
    "focus": 18,
    "company": 16,
    "market": 16,
    "macro": 14,
    "international": 10,
    "original": 8,
    "opinion": -8,
    "other": -10,
}


@dataclass(frozen=True)
class NewsQualityDecision:
    item: PublicNewsItem
    accepted: bool
    score: int
    reasons: list[str]
    reject_reason: str


@dataclass(frozen=True)
class NewsQualityResult:
    accepted_items: list[PublicNewsItem]
    decisions: list[NewsQualityDecision]
    rejection_counts: dict[str, int]
    threshold: int
    max_accepted: int


def evaluate_public_news_items(
    items: Iterable[PublicNewsItem],
    *,
    now: datetime | None = None,
    threshold: int = NEWS_QUALITY_THRESHOLD,
    max_accepted: int = NEWS_MAX_ACCEPTED_PER_RUN,
) -> NewsQualityResult:
    threshold = max(0, min(100, threshold))
    max_accepted = max(0, max_accepted)
    current_time = _as_utc(now or datetime.now(UTC))
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    decisions: list[NewsQualityDecision] = []
    accepted_candidates: list[NewsQualityDecision] = []
    rejection_counts: dict[str, int] = {}

    for item in items:
        decision = score_public_news_item(
            item,
            now=current_time,
            seen_urls=seen_urls,
            seen_titles=seen_titles,
            threshold=threshold,
        )
        decisions.append(decision)
        if decision.reject_reason:
            rejection_counts[decision.reject_reason] = (
                rejection_counts.get(decision.reject_reason, 0) + 1
            )
        if decision.accepted:
            accepted_candidates.append(decision)

    ranked = sorted(
        accepted_candidates,
        key=lambda decision: (
            decision.score,
            _parse_timestamp(decision.item.published_at)
            or _parse_timestamp(decision.item.collected_at)
            or datetime.min.replace(tzinfo=UTC),
            decision.item.news_id,
        ),
        reverse=True,
    )
    accepted_decisions = ranked[:max_accepted]
    overflow = max(0, len(ranked) - len(accepted_decisions))
    if overflow:
        rejection_counts["overflow"] = overflow

    run_id = f"public-news-{current_time.strftime('%Y%m%dT%H%M%SZ')}"
    accepted_items = [
        _with_quality_metadata(decision, accepted_at=current_time, run_id=run_id)
        for decision in accepted_decisions
    ]
    accepted_ids = {decision.item.news_id for decision in accepted_decisions}
    overflow_decisions = [
        NewsQualityDecision(
            item=decision.item,
            accepted=False,
            score=decision.score,
            reasons=decision.reasons,
            reject_reason="overflow",
        )
        for decision in ranked[max_accepted:]
    ]
    final_decisions = [
        *accepted_decisions,
        *overflow_decisions,
        *(
            decision
            for decision in decisions
            if not decision.accepted and decision.item.news_id not in accepted_ids
        ),
    ]
    return NewsQualityResult(
        accepted_items=accepted_items,
        decisions=final_decisions,
        rejection_counts=rejection_counts,
        threshold=threshold,
        max_accepted=max_accepted,
    )


def score_public_news_item(
    item: PublicNewsItem,
    *,
    now: datetime,
    seen_urls: set[str] | None = None,
    seen_titles: set[str] | None = None,
    threshold: int = NEWS_QUALITY_THRESHOLD,
) -> NewsQualityDecision:
    title = " ".join((item.title or "").split())
    summary = " ".join((item.summary or "").split())
    url = " ".join((item.url or "").split())
    if not title:
        return NewsQualityDecision(item, False, 0, [], "missing_title")
    if not url:
        return NewsQualityDecision(item, False, 0, [], "missing_url")

    normalized_title = title.lower()
    normalized_url = url.lower()
    if normalized_url in (seen_urls or set()) or normalized_title in (seen_titles or set()):
        return NewsQualityDecision(item, False, 0, [], "duplicate")
    if seen_urls is not None:
        seen_urls.add(normalized_url)
    if seen_titles is not None:
        seen_titles.add(normalized_title)

    text = f"{title} {summary}"
    if any(token in text for token in LOW_SIGNAL_TOKENS):
        return NewsQualityDecision(item, False, 0, [], "low_signal")

    if not _is_a_share_relevant(text):
        return NewsQualityDecision(item, False, 0, [], "not_a_share_relevant")

    published_at = _parse_timestamp(item.published_at) or _parse_timestamp(item.collected_at)
    if published_at and _as_utc(now) - published_at > timedelta(hours=NEWS_FRESHNESS_HOURS):
        return NewsQualityDecision(item, False, 0, [], "stale")

    reasons: list[str] = []
    score = 28
    if published_at:
        age_hours = max(0.0, (_as_utc(now) - published_at).total_seconds() / 3600)
        if age_hours <= 2:
            score += 18
            reasons.append("fresh")
        elif age_hours <= 8:
            score += 12
            reasons.append("same_day")
        else:
            score += 4
            reasons.append("recent")

    category = (item.category or "other").lower()
    score += CATEGORY_SCORE.get(category, 0)
    if category in {"live", "focus", "company", "market", "macro"}:
        reasons.append(category)

    for reason, tokens in TRADING_TOKENS.items():
        if any(token in text for token in tokens):
            score += 10
            reasons.append(reason)

    if any(char.isdigit() for char in text):
        score += 4
        reasons.append("numeric_detail")

    score = max(0, min(100, score))
    unique_reasons = sorted(set(reasons))
    if score < threshold:
        return NewsQualityDecision(item, False, score, unique_reasons, "below_threshold")
    return NewsQualityDecision(item, True, score, unique_reasons, "")


def _is_a_share_relevant(text: str) -> bool:
    if any(token in text for token in A_SHARE_RELEVANCE_TOKENS):
        return True
    if any(token in text for token in DOMESTIC_SECTOR_TOKENS) and not any(
        token in text for token in OVERSEAS_ONLY_TOKENS
    ):
        return True
    return False


def _with_quality_metadata(
    decision: NewsQualityDecision,
    *,
    accepted_at: datetime,
    run_id: str,
) -> PublicNewsItem:
    raw_payload: dict[str, Any] = dict(decision.item.raw_payload or {})
    raw_payload["quality"] = {
        "score": decision.score,
        "reasons": decision.reasons,
        "run_id": run_id,
        "accepted_at": accepted_at.isoformat(),
    }
    row = decision.item.to_dict()
    row["raw_payload"] = raw_payload
    return PublicNewsItem.from_dict(row)


def _parse_timestamp(value: str) -> datetime | None:
    text = " ".join((value or "").strip().split())
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return _as_utc(parsed)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SOURCE_TIMEZONE).astimezone(UTC)
    return value.astimezone(UTC)
