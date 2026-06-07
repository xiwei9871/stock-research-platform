from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.research_windows import load_trade_dates


NEWS_MENTION_COLUMNS = [
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
]

NEWS_FEATURE_COLUMNS = [
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
    "headline_capital_flow_count_3d",
    "headline_main_force_flow_count_3d",
    "headline_margin_flow_count_3d",
    "headline_capital_flow_generic_count_3d",
    "headline_gold_stock_count_3d",
    "headline_rating_action_count_3d",
    "headline_broker_positive_view_count_3d",
    "headline_order_bid_count_3d",
    "headline_product_breakthrough_count_3d",
    "headline_industry_boom_count_3d",
    "headline_regulatory_inquiry_count_3d",
    "headline_shareholder_reduction_count_3d",
    "headline_litigation_penalty_count_3d",
    "headline_loss_warning_count_3d",
    "headline_broker_reco_count_3d",
    "headline_business_catalyst_count_3d",
    "headline_risk_event_count_3d",
    "notice_count_3d",
    "notice_count_10d",
    "risk_notice_count_20d",
    "earnings_notice_count_20d",
    "governance_notice_count_20d",
    "contract_investment_notice_count_20d",
    "research_report_count_20d",
    "rating_action_count_20d",
    "theme_news_burst_flag",
    "news_first_seen_gap",
    "news_attention_level",
]

NEWS_BUCKET_SUMMARY_COLUMNS = [
    "bucket",
    "sample_count",
    "avg_news_count_3d",
    "avg_future_5d_return",
]

NEWS_REGIME_SUMMARY_COLUMNS = [
    "regime",
    "bucket",
    "sample_count",
    "avg_news_count_3d",
    "avg_future_5d_return",
]

POSITIVE_HEADLINE_KEYWORDS = (
    "增长",
    "看好",
    "订单",
    "中标",
    "突破",
    "增持",
    "上调",
    "回购",
    "景气",
    "新高",
)
RISK_HEADLINE_KEYWORDS = (
    "风险",
    "提示",
    "下滑",
    "亏损",
    "减持",
    "监管",
    "诉讼",
    "违约",
    "暴雷",
    "停牌",
)
CAPITAL_FLOW_HEADLINE_KEYWORDS = (
    "主力",
    "资金",
    "抢筹",
    "加仓",
    "融资",
    "融资客",
    "杠杆",
)
MAIN_FORCE_FLOW_HEADLINE_KEYWORDS = (
    "主力资金",
    "主力资金抢筹",
    "主力资金流入",
    "主力资金流出",
    "主力净流入",
    "主力抢筹",
    "主力加仓",
    "主力流入",
)
MARGIN_FLOW_HEADLINE_KEYWORDS = (
    "融资客",
    "融资",
    "杠杆",
    "融券",
)
CAPITAL_FLOW_GENERIC_HEADLINE_KEYWORDS = (
    "资金",
    "主力",
    "抢筹",
    "加仓",
    "流入",
    "流出",
)
GOLD_STOCK_HEADLINE_KEYWORDS = (
    "券商金股",
    "金股推荐",
    "金股",
)
RATING_ACTION_HEADLINE_KEYWORDS = (
    "评级上调",
    "上调评级",
    "买入评级",
    "增持评级",
    "目标价上调",
    "上调目标价",
)
NOTICE_RISK_HEADLINE_KEYWORDS = (
    "风险提示",
    "风险警示",
    "监管问询",
    "问询函",
    "关注函",
    "监管函",
    "立案",
    "处罚",
    "诉讼",
    "违约",
    "停牌",
)
NOTICE_EARNINGS_HEADLINE_KEYWORDS = (
    "业绩预告",
    "业绩预增",
    "业绩快报",
    "业绩公告",
    "预增",
    "预减",
    "盈利",
    "亏损",
)
NOTICE_GOVERNANCE_HEADLINE_KEYWORDS = (
    "股东大会",
    "董事会",
    "监事会",
    "分红",
    "股权激励",
    "回购",
    "章程",
    "选举",
    "增补",
    "注销",
)
NOTICE_CONTRACT_INVESTMENT_HEADLINE_KEYWORDS = (
    "合同",
    "签订",
    "中标",
    "投资",
    "项目",
    "合作",
    "协议",
    "设立",
    "募投",
)
BROKER_POSITIVE_VIEW_CONTEXT_KEYWORDS = (
    "券商",
    "研报",
    "研究",
    "评级",
    "报告",
    "机构",
)
BROKER_POSITIVE_VIEW_POSITIVE_KEYWORDS = (
    "看好",
    "推荐",
    "增持",
    "上调",
    "买入",
    "目标价上调",
    "上调目标价",
    "金股",
    "券商研报",
)
BROKER_POSITIVE_VIEW_NEGATIVE_KEYWORDS = (
    "维持评级",
    "评级下调",
    "下调评级",
    "目标价下调",
    "下调目标价",
    "中性评级",
    "减持评级",
    "卖出评级",
)
ORDER_BID_HEADLINE_KEYWORDS = (
    "订单",
    "中标",
    "签单",
    "定点",
    "签约",
)
PRODUCT_BREAKTHROUGH_HEADLINE_KEYWORDS = (
    "新品",
    "突破",
    "技术突破",
    "量产",
    "投产",
    "发布",
)
INDUSTRY_BOOM_HEADLINE_KEYWORDS = (
    "行业景气",
    "景气",
    "高景气",
    "需求回暖",
    "行业复苏",
    "扩产",
    "供需改善",
)
REGULATORY_INQUIRY_HEADLINE_KEYWORDS = (
    "监管问询",
    "问询函",
    "关注函",
    "监管函",
    "风险提示",
    "风险警示",
)
SHAREHOLDER_REDUCTION_HEADLINE_KEYWORDS = (
    "减持",
    "股东减持",
    "高管减持",
    "计划减持",
)
LITIGATION_PENALTY_HEADLINE_KEYWORDS = (
    "诉讼",
    "处罚",
    "立案",
    "罚款",
    "仲裁",
)
LOSS_WARNING_HEADLINE_KEYWORDS = (
    "亏损",
    "预亏",
    "亏损预警",
    "亏损扩大",
    "业绩预告",
    "业绩下滑",
)
BROKER_RECO_HEADLINE_KEYWORDS = (
    "券商看好",
    "券商推荐",
    "券商研报推荐",
    "金股推荐",
    "评级上调",
    "上调评级",
    "买入评级",
    "增持评级",
    "目标价上调",
    "上调目标价",
)
BROKER_RECO_NEGATIVE_KEYWORDS = (
    "维持评级",
    "评级下调",
    "下调评级",
    "目标价下调",
    "下调目标价",
    "中性评级",
    "减持评级",
    "卖出评级",
)
BUSINESS_CATALYST_HEADLINE_KEYWORDS = (
    "订单",
    "中标",
    "新品",
    "景气",
    "扩产",
    "突破",
    "签约",
)
RISK_EVENT_HEADLINE_KEYWORDS = (
    "风险提示",
    "风险警示",
    "监管问询",
    "监管问询函",
    "减持",
    "诉讼",
    "亏损",
    "停牌",
    "违约",
    "立案",
    "处罚",
    "问询函",
)


def _empty_mentions() -> pd.DataFrame:
    return pd.DataFrame(columns=NEWS_MENTION_COLUMNS)


def _empty_features() -> pd.DataFrame:
    return pd.DataFrame(columns=NEWS_FEATURE_COLUMNS)


def _empty_bucket_summary() -> pd.DataFrame:
    return pd.DataFrame(columns=NEWS_BUCKET_SUMMARY_COLUMNS)


def _empty_regime_summary() -> pd.DataFrame:
    return pd.DataFrame(columns=NEWS_REGIME_SUMMARY_COLUMNS)


def _metadata_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            try:
                parsed = ast.literal_eval(value)
            except (SyntaxError, ValueError):
                return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def map_news_mentions(events: pd.DataFrame, assets: pd.DataFrame) -> pd.DataFrame:
    if events.empty or assets.empty:
        return _empty_mentions()

    event_frame = events.copy()
    event_frame["published_at"] = pd.to_datetime(event_frame["published_at"], errors="coerce")
    event_frame = event_frame.loc[event_frame["published_at"].notna()].copy()
    if event_frame.empty:
        return _empty_mentions()

    asset_frame = assets.copy()
    asset_frame["ts_code"] = asset_frame["ts_code"].fillna("").astype(str).str.upper()
    asset_frame["stock_name"] = asset_frame["stock_name"].fillna("").astype(str).str.strip()
    asset_frame = asset_frame.sort_values(["ts_code", "asset_id"], kind="stable").reset_index(drop=True)

    ts_code_candidates = [
        (
            row.ts_code,
            {
                "asset_id": row.asset_id,
                "ts_code": row.ts_code,
                "stock_name": row.stock_name,
            },
        )
        for row in asset_frame.itertuples(index=False)
        if row.ts_code
    ]
    stock_name_candidates = [
        (
            row.stock_name,
            {
                "asset_id": row.asset_id,
                "ts_code": row.ts_code,
                "stock_name": row.stock_name,
            },
        )
        for row in asset_frame.itertuples(index=False)
        if row.stock_name
    ]

    mention_rows: list[dict[str, object]] = []
    for event in event_frame.itertuples(index=False):
        metadata = _metadata_dict(getattr(event, "metadata", None))
        matched_candidates = metadata.get("matched_candidates") or []
        if matched_candidates:
            direct_rows: list[dict[str, object]] = []
            seen_asset_ids: set[str] = set()
            for candidate in matched_candidates:
                if not isinstance(candidate, dict):
                    continue
                asset_id = str(candidate.get("asset_id") or "").strip()
                ts_code = str(candidate.get("ts_code") or "").strip().upper()
                stock_name = str(candidate.get("stock_name") or "").strip()
                if not asset_id or asset_id in seen_asset_ids:
                    continue
                direct_rows.append(
                    {
                        "source_event_id": getattr(event, "source_event_id", None),
                        "asset_id": asset_id,
                        "ts_code": ts_code,
                        "stock_name": stock_name,
                        "mapping_method": "matched_candidate",
                        "trade_date": event.published_at.date().isoformat(),
                        "published_at": event.published_at,
                        "source_name": getattr(event, "source_name", None),
                        "event_family": getattr(event, "event_family", None),
                        "source_channel": getattr(event, "source_channel", None),
                        "title": getattr(event, "title", None),
                        "content": getattr(event, "content", None),
                    }
                )
                seen_asset_ids.add(asset_id)
            if direct_rows:
                mention_rows.extend(direct_rows)
                continue

        text = " ".join(
            [
                str(getattr(event, "title", "") or ""),
                str(getattr(event, "content", "") or ""),
            ]
        )
        normalized_text = text.upper()
        matched_asset_ids: set[str] = set()

        for ts_code, asset in ts_code_candidates:
            if ts_code and ts_code in normalized_text:
                mention_rows.append(
                {
                    "source_event_id": getattr(event, "source_event_id", None),
                    "asset_id": asset["asset_id"],
                    "ts_code": asset["ts_code"],
                    "stock_name": asset["stock_name"],
                    "mapping_method": "ts_code",
                    "trade_date": event.published_at.date().isoformat(),
                    "published_at": event.published_at,
                    "source_name": getattr(event, "source_name", None),
                    "event_family": getattr(event, "event_family", None),
                    "source_channel": getattr(event, "source_channel", None),
                    "title": getattr(event, "title", None),
                    "content": getattr(event, "content", None),
                }
            )
                matched_asset_ids.add(str(asset["asset_id"]))

        for stock_name, asset in stock_name_candidates:
            if not stock_name or str(asset["asset_id"]) in matched_asset_ids:
                continue
            if stock_name in text:
                mention_rows.append(
                    {
                        "source_event_id": getattr(event, "source_event_id", None),
                        "asset_id": asset["asset_id"],
                        "ts_code": asset["ts_code"],
                        "stock_name": asset["stock_name"],
                        "mapping_method": "stock_name",
                        "trade_date": event.published_at.date().isoformat(),
                        "published_at": event.published_at,
                        "source_name": getattr(event, "source_name", None),
                        "event_family": getattr(event, "event_family", None),
                        "source_channel": getattr(event, "source_channel", None),
                        "title": getattr(event, "title", None),
                        "content": getattr(event, "content", None),
                    }
                )

    if not mention_rows:
        return _empty_mentions()
    return pd.DataFrame(mention_rows).reindex(columns=NEWS_MENTION_COLUMNS)


def _contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _contains_broker_positive_view(text: str) -> bool:
    return _contains_keyword(text, BROKER_POSITIVE_VIEW_CONTEXT_KEYWORDS) and _contains_keyword(
        text, BROKER_POSITIVE_VIEW_POSITIVE_KEYWORDS
    ) and not _contains_keyword(text, BROKER_POSITIVE_VIEW_NEGATIVE_KEYWORDS)


def _contains_generic_capital_flow(text: str) -> bool:
    return _contains_keyword(text, CAPITAL_FLOW_GENERIC_HEADLINE_KEYWORDS) and not _contains_keyword(
        text, MAIN_FORCE_FLOW_HEADLINE_KEYWORDS
    ) and not _contains_keyword(text, MARGIN_FLOW_HEADLINE_KEYWORDS)


def _count_keyword_hits(texts: pd.Series, keywords: tuple[str, ...]) -> int:
    return int(texts.map(lambda text: _contains_keyword(text, keywords)).astype(int).sum())


def _derive_attention_level(news_count_3d: int, source_diversity_3d: int) -> str:
    if news_count_3d >= 5 or source_diversity_3d >= 3:
        return "high"
    if news_count_3d >= 2:
        return "medium"
    return "low"


def _normalize_attention_bucket(frame: pd.DataFrame) -> pd.Series:
    if "news_attention_level" in frame.columns:
        values = frame["news_attention_level"].fillna("").astype(str).str.strip()
        return values.where(values != "", "unknown")

    numeric = pd.to_numeric(frame.get("news_count_3d", 0), errors="coerce").fillna(0)
    bucket = pd.Series("low", index=frame.index, dtype=object)
    bucket.loc[numeric >= 2] = "medium"
    bucket.loc[numeric >= 5] = "high"
    return bucket


def build_news_feature_daily(
    mentions: pd.DataFrame,
    trade_dates: list[str],
    mode: str = "replay",
) -> pd.DataFrame:
    if mode not in {"replay", "live"}:
        raise ValueError(f"unsupported mode: {mode}")
    if mentions.empty or not trade_dates:
        return _empty_features()

    frame = mentions.copy()
    frame["published_at"] = pd.to_datetime(frame["published_at"], errors="coerce")
    frame = frame.loc[frame["published_at"].notna()].copy()
    if frame.empty:
        return _empty_features()
    if "title" not in frame.columns:
        frame["title"] = ""
    if "source_name" not in frame.columns:
        frame["source_name"] = ""
    if "source_channel" not in frame.columns:
        frame["source_channel"] = ""
    frame["title"] = frame["title"].fillna("").astype(str)
    frame["source_name"] = frame["source_name"].fillna("").astype(str)
    if "event_family" not in frame.columns:
        frame["event_family"] = ""
    frame["event_family"] = frame["event_family"].fillna("").astype(str).str.strip()
    frame["source_channel"] = frame["source_channel"].fillna("").astype(str)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.normalize()
    frame["published_trade_date"] = frame["published_at"].dt.normalize()

    rows: list[dict[str, object]] = []
    trade_date_values = pd.to_datetime(pd.Series(trade_dates), errors="coerce").dropna().dt.normalize()
    for trade_date in trade_date_values:
        if mode == "live":
            eligible = frame.copy()
        else:
            cutoff = trade_date + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            eligible = frame.loc[frame["published_at"] <= cutoff].copy()
        if eligible.empty:
            continue

        start_1d = trade_date
        start_3d = trade_date - pd.Timedelta(days=2)
        start_10d = trade_date - pd.Timedelta(days=9)
        start_5d = trade_date - pd.Timedelta(days=4)
        start_20d = trade_date - pd.Timedelta(days=19)
        overnight_start = trade_date - pd.Timedelta(hours=6)
        overnight_end = trade_date + pd.Timedelta(hours=9)
        preopen_start = trade_date + pd.Timedelta(hours=9)
        preopen_end = trade_date + pd.Timedelta(hours=9, minutes=30)

        for (asset_id, ts_code), asset_rows in eligible.groupby(["asset_id", "ts_code"], dropna=False):
            window_1d = asset_rows.loc[asset_rows["published_at"] >= start_1d]
            window_3d = asset_rows.loc[asset_rows["published_at"] >= start_3d]
            window_5d = asset_rows.loc[asset_rows["published_at"] >= start_5d]
            notice_window_3d = window_3d.loc[window_3d["event_family"] == "disclosure_notice"]
            notice_window_10d = asset_rows.loc[
                (asset_rows["published_at"] >= start_10d)
                & (asset_rows["event_family"] == "disclosure_notice")
            ]
            notice_20d = asset_rows.loc[
                (asset_rows["published_at"] >= start_20d)
                & (asset_rows["event_family"] == "disclosure_notice")
            ]
            report_20d = asset_rows.loc[
                (asset_rows["published_at"] >= start_20d)
                & (asset_rows["event_family"] == "institution_report")
            ]
            overnight_window = asset_rows.loc[
                (asset_rows["published_at"] >= overnight_start)
                & (asset_rows["published_at"] < overnight_end)
            ]
            preopen_window = asset_rows.loc[
                (asset_rows["published_at"] >= preopen_start)
                & (asset_rows["published_at"] < preopen_end)
            ]

            title_3d = window_3d["title"].fillna("").astype(str)
            positive_count = _count_keyword_hits(title_3d, POSITIVE_HEADLINE_KEYWORDS)
            risk_count = _count_keyword_hits(title_3d, RISK_HEADLINE_KEYWORDS)
            capital_flow_count = _count_keyword_hits(title_3d, CAPITAL_FLOW_HEADLINE_KEYWORDS)
            main_force_flow_count = _count_keyword_hits(title_3d, MAIN_FORCE_FLOW_HEADLINE_KEYWORDS)
            margin_flow_count = _count_keyword_hits(title_3d, MARGIN_FLOW_HEADLINE_KEYWORDS)
            capital_flow_generic_count = int(title_3d.map(_contains_generic_capital_flow).astype(int).sum())
            gold_stock_count = _count_keyword_hits(title_3d, GOLD_STOCK_HEADLINE_KEYWORDS)
            rating_action_count = _count_keyword_hits(title_3d, RATING_ACTION_HEADLINE_KEYWORDS)
            broker_positive_view_count = int(title_3d.map(_contains_broker_positive_view).astype(int).sum())
            order_bid_count = _count_keyword_hits(title_3d, ORDER_BID_HEADLINE_KEYWORDS)
            product_breakthrough_count = _count_keyword_hits(title_3d, PRODUCT_BREAKTHROUGH_HEADLINE_KEYWORDS)
            industry_boom_count = _count_keyword_hits(title_3d, INDUSTRY_BOOM_HEADLINE_KEYWORDS)
            regulatory_inquiry_count = _count_keyword_hits(title_3d, REGULATORY_INQUIRY_HEADLINE_KEYWORDS)
            shareholder_reduction_count = _count_keyword_hits(title_3d, SHAREHOLDER_REDUCTION_HEADLINE_KEYWORDS)
            litigation_penalty_count = _count_keyword_hits(title_3d, LITIGATION_PENALTY_HEADLINE_KEYWORDS)
            loss_warning_count = _count_keyword_hits(title_3d, LOSS_WARNING_HEADLINE_KEYWORDS)
            broker_reco_count = int(
                title_3d.map(
                    lambda text: _contains_keyword(text, BROKER_RECO_HEADLINE_KEYWORDS)
                    and not _contains_keyword(text, BROKER_RECO_NEGATIVE_KEYWORDS)
                )
                .astype(int)
                .sum()
            )
            business_catalyst_count = _count_keyword_hits(title_3d, BUSINESS_CATALYST_HEADLINE_KEYWORDS)
            risk_event_count = _count_keyword_hits(title_3d, RISK_EVENT_HEADLINE_KEYWORDS)
            notice_count_3d = int(len(notice_window_3d))
            notice_count_10d = int(len(notice_window_10d))
            notice_titles_20d = notice_20d["title"].fillna("").astype(str)
            report_titles_20d = report_20d["title"].fillna("").astype(str)
            risk_notice_count = _count_keyword_hits(notice_titles_20d, NOTICE_RISK_HEADLINE_KEYWORDS)
            earnings_notice_count = _count_keyword_hits(notice_titles_20d, NOTICE_EARNINGS_HEADLINE_KEYWORDS)
            governance_notice_count = _count_keyword_hits(notice_titles_20d, NOTICE_GOVERNANCE_HEADLINE_KEYWORDS)
            contract_investment_notice_count = _count_keyword_hits(
                notice_titles_20d, NOTICE_CONTRACT_INVESTMENT_HEADLINE_KEYWORDS
            )
            research_report_count = int(len(report_20d))
            rating_action_count_20d = _count_keyword_hits(report_titles_20d, RATING_ACTION_HEADLINE_KEYWORDS)
            source_names = window_3d["source_name"].fillna("").astype(str).str.strip()
            source_diversity_3d = int(source_names[source_names != ""].nunique(dropna=True))
            major_news_count_3d = int(
                window_3d["source_channel"].fillna("").astype(str).str.contains("major", case=False).sum()
                if "source_channel" in window_3d
                else 0
            )
            news_count_3d = int(len(window_3d))
            first_seen_gap = int((trade_date - asset_rows["published_trade_date"].min()).days)
            rows.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "ts_code": ts_code,
                    "news_count_1d": int(len(window_1d)),
                    "news_count_3d": news_count_3d,
                    "news_count_5d": int(len(window_5d)),
                    "major_news_count_3d": major_news_count_3d,
                    "source_diversity_3d": source_diversity_3d,
                    "overnight_news_count": int(len(overnight_window)),
                    "preopen_news_count": int(len(preopen_window)),
                    "headline_keyword_positive_count_3d": positive_count,
                    "headline_keyword_risk_count_3d": risk_count,
                    "headline_capital_flow_count_3d": capital_flow_count,
                    "headline_main_force_flow_count_3d": main_force_flow_count,
                    "headline_margin_flow_count_3d": margin_flow_count,
                    "headline_capital_flow_generic_count_3d": capital_flow_generic_count,
                    "headline_gold_stock_count_3d": gold_stock_count,
                    "headline_rating_action_count_3d": rating_action_count,
                    "headline_broker_positive_view_count_3d": broker_positive_view_count,
                    "headline_order_bid_count_3d": order_bid_count,
                    "headline_product_breakthrough_count_3d": product_breakthrough_count,
                    "headline_industry_boom_count_3d": industry_boom_count,
                    "headline_regulatory_inquiry_count_3d": regulatory_inquiry_count,
                    "headline_shareholder_reduction_count_3d": shareholder_reduction_count,
                    "headline_litigation_penalty_count_3d": litigation_penalty_count,
                    "headline_loss_warning_count_3d": loss_warning_count,
                    "headline_broker_reco_count_3d": broker_reco_count,
                    "headline_business_catalyst_count_3d": business_catalyst_count,
                    "headline_risk_event_count_3d": risk_event_count,
                    "notice_count_3d": notice_count_3d,
                    "notice_count_10d": notice_count_10d,
                    "risk_notice_count_20d": risk_notice_count,
                    "earnings_notice_count_20d": earnings_notice_count,
                    "governance_notice_count_20d": governance_notice_count,
                    "contract_investment_notice_count_20d": contract_investment_notice_count,
                    "research_report_count_20d": research_report_count,
                    "rating_action_count_20d": rating_action_count_20d,
                    "theme_news_burst_flag": bool(news_count_3d >= 3 and source_diversity_3d >= 2),
                    "news_first_seen_gap": first_seen_gap,
                    "news_attention_level": _derive_attention_level(news_count_3d, source_diversity_3d),
                }
            )

    if not rows:
        return _empty_features()
    return pd.DataFrame(rows).reindex(columns=NEWS_FEATURE_COLUMNS)


def summarize_news_feature_buckets(feature_frame: pd.DataFrame) -> pd.DataFrame:
    if feature_frame.empty:
        return _empty_bucket_summary()

    frame = feature_frame.copy()
    frame["bucket"] = _normalize_attention_bucket(frame)
    frame["news_count_3d"] = pd.to_numeric(frame.get("news_count_3d", 0), errors="coerce")
    frame["future_5d_return"] = pd.to_numeric(frame.get("future_5d_return"), errors="coerce")

    summary = (
        frame.groupby("bucket", dropna=False)
        .agg(
            sample_count=("asset_id", "size"),
            avg_news_count_3d=("news_count_3d", "mean"),
            avg_future_5d_return=("future_5d_return", "mean"),
        )
        .reset_index()
    )
    return summary.reindex(columns=NEWS_BUCKET_SUMMARY_COLUMNS)


def summarize_news_feature_regimes(feature_frame: pd.DataFrame) -> pd.DataFrame:
    if feature_frame.empty:
        return _empty_regime_summary()

    frame = feature_frame.copy()
    frame["bucket"] = _normalize_attention_bucket(frame)
    if "market_regime" in frame.columns:
        regime = frame["market_regime"].fillna("").astype(str).str.strip()
        frame["regime"] = regime.where(regime != "", "unknown")
    else:
        frame["regime"] = "unknown"

    frame["news_count_3d"] = pd.to_numeric(frame.get("news_count_3d", 0), errors="coerce")
    frame["future_5d_return"] = pd.to_numeric(frame.get("future_5d_return"), errors="coerce")

    summary = (
        frame.groupby(["regime", "bucket"], dropna=False)
        .agg(
            sample_count=("asset_id", "size"),
            avg_news_count_3d=("news_count_3d", "mean"),
            avg_future_5d_return=("future_5d_return", "mean"),
        )
        .reset_index()
    )
    return summary.reindex(columns=NEWS_REGIME_SUMMARY_COLUMNS)


def _default_output_dir(*, start_date: str, end_date: str, mode: str) -> Path:
    return Path("outputs/research") / f"news_feature_backfill_{start_date}_{end_date}_{mode}"


def _load_assets_for_news_mapping() -> pd.DataFrame:
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT asset_id, ts_code, name AS stock_name
            FROM core.asset_master
            WHERE ts_code IS NOT NULL AND ts_code <> ''
            """,
        )
    return pd.DataFrame(rows)


def _load_trade_dates_for_news_features(start_date: str, end_date: str) -> list[str]:
    return load_trade_dates(start_date=start_date, end_date=end_date)


def run_news_feature_backfill(
    *,
    events_path: str | Path,
    start_date: str,
    end_date: str,
    mode: str = "replay",
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    events = pd.read_csv(events_path)
    assets = _load_assets_for_news_mapping()
    mentions = map_news_mentions(events=events, assets=assets)
    trade_dates = _load_trade_dates_for_news_features(start_date=start_date, end_date=end_date)
    features = build_news_feature_daily(mentions=mentions, trade_dates=trade_dates, mode=mode)

    resolved_output_dir = Path(output_dir) if output_dir is not None else _default_output_dir(
        start_date=start_date,
        end_date=end_date,
        mode=mode,
    )
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "mentions": str(resolved_output_dir / "news_feature_mentions.csv"),
        "features": str(resolved_output_dir / "news_feature_daily.csv"),
    }
    mentions.to_csv(paths["mentions"], index=False)
    features.to_csv(paths["features"], index=False)
    return {"mentions": mentions, "features": features, "paths": paths}


def run_news_feature_diagnostics(
    *,
    feature_frame: pd.DataFrame | None = None,
    feature_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    if feature_frame is None:
        if feature_path is None:
            raise ValueError("feature_path is required when feature_frame is not provided")
        frame = pd.read_csv(feature_path)
    else:
        frame = feature_frame.copy()

    warnings: list[str] = []
    if frame.empty:
        warnings.append("feature frame is empty")
    if len(frame) < 20:
        warnings.append(f"small sample: {len(frame)} rows")
    if "future_5d_return" not in frame.columns:
        warnings.append("future_5d_return missing; return diagnostics will be sparse")
    else:
        future_returns = pd.to_numeric(frame.get("future_5d_return"), errors="coerce")
        if future_returns.notna().sum() == 0:
            warnings.append("future_5d_return has no usable numeric values; return diagnostics will be sparse")
    if "market_regime" not in frame.columns:
        warnings.append("market_regime missing; regime segmentation degraded to unknown")

    bucket_summary = summarize_news_feature_buckets(frame)
    regime_summary = summarize_news_feature_regimes(frame)

    if not bucket_summary.empty and bucket_summary["sample_count"].min() < 5:
        warnings.append("bucket summary contains groups with sample_count < 5")
    if not regime_summary.empty and regime_summary["sample_count"].min() < 5:
        warnings.append("regime summary contains groups with sample_count < 5")
    if not regime_summary.empty and regime_summary["regime"].astype(str).eq("unknown").all():
        warnings.append("regime summary is entirely unknown")

    destination_dir = Path(output_dir or "outputs/research/news_feature_diagnostics")
    destination_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "bucket_summary": str(destination_dir / "news_feature_bucket_effectiveness.csv"),
        "regime_summary": str(destination_dir / "news_feature_regime_effectiveness.csv"),
        "report": str(destination_dir / "news_feature_diagnostics_report.md"),
    }
    bucket_summary.to_csv(paths["bucket_summary"], index=False)
    regime_summary.to_csv(paths["regime_summary"], index=False)

    report_lines = [
        "# News Feature Diagnostics",
        "",
        f"- rows: {len(frame)}",
        f"- warnings: {len(warnings)}",
        "",
        "## Warnings",
    ]
    if warnings:
        report_lines.extend(f"- {warning}" for warning in warnings)
    else:
        report_lines.append("- none")
    report_lines.extend(
        [
            "",
            "## Bucket Summary",
            "",
            f"- path: {paths['bucket_summary']}",
            "",
            "### Bucket Summary Preview",
            "",
        ]
    )
    if bucket_summary.empty:
        report_lines.append("- no bucket rows")
    else:
        report_lines.extend(bucket_summary.head(5).to_markdown(index=False).splitlines())
    report_lines.extend(
        [
            "",
            "## Regime Summary",
            "",
            f"- path: {paths['regime_summary']}",
            "",
            "### Regime Summary Preview",
            "",
        ]
    )
    if regime_summary.empty:
        report_lines.append("- no regime rows")
    else:
        if regime_summary["regime"].astype(str).eq("unknown").all():
            report_lines.append("- regime coverage is all `unknown`")
            report_lines.append("")
        report_lines.extend(regime_summary.head(5).to_markdown(index=False).splitlines())
    Path(paths["report"]).write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "bucket_summary": bucket_summary,
        "regime_summary": regime_summary,
        "warnings": warnings,
        "paths": paths,
    }
