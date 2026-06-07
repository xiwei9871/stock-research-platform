from __future__ import annotations

from pathlib import Path

import pandas as pd


TOPN_NEWS_ENRICHMENT_COLUMNS = [
    "trade_date",
    "asset_id",
    "ts_code",
    "stock_name",
    "news_consensus_summary",
    "news_risk_summary",
    "news_compact_summary",
    "theme_catalyst_summary",
    "historical_event_summary",
    "overnight_catalyst_note",
    "news_attention_level",
    "news_risk_attention_flag",
    "news_enrichment_quality_flag",
]

SEMANTIC_NEWS_FEATURE_COLUMNS = (
    "headline_broker_reco_count_3d",
    "headline_capital_flow_count_3d",
    "headline_business_catalyst_count_3d",
    "headline_risk_event_count_3d",
)

SEMANTIC_CONSENSUS_SUBCATEGORY_PRIORITY = (
    ("headline_gold_stock_count_3d", "近3日券商金股/推荐新闻{count}条，关注度{attention}"),
    ("headline_rating_action_count_3d", "近3日评级/目标价新闻{count}条，关注度{attention}"),
    ("headline_broker_positive_view_count_3d", "近3日券商看好类新闻{count}条，关注度{attention}"),
    ("headline_main_force_flow_count_3d", "近3日主力资金关注新闻{count}条，关注度{attention}"),
    ("headline_margin_flow_count_3d", "近3日融资/杠杆资金新闻{count}条，关注度{attention}"),
    ("headline_capital_flow_generic_count_3d", "近3日资金关注类新闻{count}条，关注度{attention}"),
    ("headline_order_bid_count_3d", "近3日订单/中标新闻{count}条，关注度{attention}"),
    ("headline_product_breakthrough_count_3d", "近3日新品/突破新闻{count}条，关注度{attention}"),
    ("headline_industry_boom_count_3d", "近3日行业景气新闻{count}条，关注度{attention}"),
)

SEMANTIC_RISK_SUBCATEGORY_PRIORITY = (
    ("headline_regulatory_inquiry_count_3d", "近3日监管问询/风险提示新闻{count}条"),
    ("headline_shareholder_reduction_count_3d", "近3日减持类风险新闻{count}条"),
    ("headline_litigation_penalty_count_3d", "近3日诉讼/处罚类风险新闻{count}条"),
    ("headline_loss_warning_count_3d", "近3日亏损/业绩风险新闻{count}条"),
)

SEMANTIC_THEME_SUBCATEGORY_PRIORITY = (
    ("headline_order_bid_count_3d", "近3日订单/中标催化新闻{count}条"),
    ("headline_product_breakthrough_count_3d", "近3日新品/突破催化新闻{count}条"),
    ("headline_industry_boom_count_3d", "近3日景气/扩产催化新闻{count}条"),
    ("headline_gold_stock_count_3d", "近3日券商金股催化新闻{count}条"),
    ("headline_rating_action_count_3d", "近3日评级催化新闻{count}条"),
    ("headline_main_force_flow_count_3d", "近3日主力资金关注新闻{count}条"),
    ("headline_margin_flow_count_3d", "近3日融资/杠杆资金新闻{count}条"),
    ("headline_capital_flow_generic_count_3d", "近3日资金关注类新闻{count}条"),
)

COMPACT_BROKER_SUBCATEGORY_PRIORITY = (
    ("headline_gold_stock_count_3d", "券商金股推荐"),
    ("headline_rating_action_count_3d", "评级/目标价"),
    ("headline_broker_positive_view_count_3d", "券商看好"),
)

COMPACT_CAPITAL_SUBCATEGORY_PRIORITY = (
    ("headline_main_force_flow_count_3d", "主力资金关注"),
    ("headline_margin_flow_count_3d", "融资/杠杆资金"),
    ("headline_capital_flow_generic_count_3d", "资金关注"),
)

COMPACT_CATALYST_SUBCATEGORY_PRIORITY = (
    ("headline_order_bid_count_3d", "订单/中标催化"),
    ("headline_product_breakthrough_count_3d", "新品/突破催化"),
    ("headline_industry_boom_count_3d", "景气/扩产催化"),
)

COMPACT_RISK_SUBCATEGORY_PRIORITY = (
    ("headline_regulatory_inquiry_count_3d", "监管问询"),
    ("headline_shareholder_reduction_count_3d", "减持风险"),
    ("headline_litigation_penalty_count_3d", "诉讼/处罚"),
    ("headline_loss_warning_count_3d", "亏损/业绩风险"),
)


def _empty_enrichment() -> pd.DataFrame:
    return pd.DataFrame(columns=TOPN_NEWS_ENRICHMENT_COLUMNS)


def _derive_quality_flag(row: dict[str, object]) -> str:
    populated = sum(
        bool(row.get(column))
        for column in (
            "news_consensus_summary",
            "news_risk_summary",
            "theme_catalyst_summary",
            "overnight_catalyst_note",
        )
    )
    if populated >= 4:
        return "rich"
    if populated >= 2:
        return "medium"
    return "thin"


def _as_int(value: object) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) if float(value).is_integer() else 0
    text = str(value).strip()
    if not text:
        return 0
    if text.isdigit() or (text.startswith(("+", "-")) and text[1:].isdigit()):
        return int(text)
    try:
        numeric_value = float(text)
    except ValueError:
        return 0
    if numeric_value.is_integer():
        return int(numeric_value)
    return 0


def _semantic_count(value: object) -> int:
    return max(0, _as_int(value))


def _first_positive_semantic_summary(
    item: object,
    priority: tuple[tuple[str, str], ...],
    *,
    attention_level: str | None = None,
) -> str:
    for column, template in priority:
        count = _semantic_count(getattr(item, column, 0))
        if count > 0:
            return template.format(count=count, attention=attention_level or "")
    return ""


def _first_positive_compact_phrase(
    item: object,
    priority: tuple[tuple[str, str], ...],
) -> str:
    for column, phrase in priority:
        if _semantic_count(getattr(item, column, 0)) > 0:
            return phrase
    return ""


def _has_non_negative_parseable_semantic_value(value: object) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return float(value).is_integer() and value >= 0
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        if text.startswith("-"):
            return False
        if text.isdigit() or (text.startswith("+") and text[1:].isdigit()):
            return True
        try:
            numeric_value = float(text)
        except ValueError:
            return False
        return numeric_value.is_integer() and numeric_value >= 0
    return False


def _normalize_attention_level(value: object, *, has_news_feature: bool) -> str:
    text = "" if pd.isna(value) else str(value).strip().lower()
    if text:
        return text
    return "low" if has_news_feature else "unknown"


def _build_zero_count_fallback_summaries(attention_level: str) -> dict[str, str]:
    return {
        "news_consensus_summary": f"近3日未见明显正向新闻，关注度{attention_level}",
        "news_risk_summary": "近3日未见风险关键词新闻",
        "theme_catalyst_summary": "近3日未见重大/主线催化新闻",
        "overnight_catalyst_note": "近3日未见隔夜催化新闻",
    }


def _build_historical_notice_summary(item: object) -> str:
    for column, template in (
        ("earnings_notice_count_20d", "近20日有{count}条业绩类公告"),
        ("governance_notice_count_20d", "近20日有{count}条治理类公告"),
        ("contract_investment_notice_count_20d", "近20日有{count}条合同/投资类公告"),
        ("risk_notice_count_20d", "近20日有{count}条风险类公告"),
        ("notice_count_3d", "近3日有{count}条公告"),
        ("notice_count_10d", "近10日有{count}条公告"),
    ):
        count = _as_int(getattr(item, column, 0))
        if count > 0:
            return template.format(count=count)
    return ""


def _build_historical_event_summary(item: object) -> str:
    earnings_notice_count = _as_int(getattr(item, "earnings_notice_count_20d", 0))
    risk_notice_count = _as_int(getattr(item, "risk_notice_count_20d", 0))
    notice_summary = _build_historical_notice_summary(item)
    report_count = _as_int(getattr(item, "research_report_count_20d", 0))
    rating_action_count = _as_int(getattr(item, "rating_action_count_20d", 0))

    if earnings_notice_count > 0 and report_count > 0:
        return f"近20日有{earnings_notice_count}条业绩类公告 + {report_count}篇机构研报"
    if risk_notice_count > 0 and report_count == 0:
        return f"近20日有{risk_notice_count}条风险类公告，暂无新增机构研报"
    if report_count > 0 and rating_action_count > 0:
        return f"近20日有{report_count}篇机构研报，其中{rating_action_count}次评级动作"
    if notice_summary and report_count > 0:
        return f"{notice_summary} + 近20日有{report_count}篇机构研报"
    if report_count > 0:
        return f"近20日有{report_count}篇机构研报"
    if notice_summary:
        return notice_summary
    return ""


def _build_news_compact_summary(item: object, *, has_news_feature: bool, use_semantic_mode: bool) -> str:
    if not has_news_feature:
        return ""

    if use_semantic_mode:
        broker_phrase = _first_positive_compact_phrase(item, COMPACT_BROKER_SUBCATEGORY_PRIORITY) or (
            f"券商推荐类新闻{_semantic_count(getattr(item, 'headline_broker_reco_count_3d', 0))}条"
            if _semantic_count(getattr(item, "headline_broker_reco_count_3d", 0)) > 0
            else ""
        )
        capital_phrase = _first_positive_compact_phrase(item, COMPACT_CAPITAL_SUBCATEGORY_PRIORITY) or (
            f"资金关注类新闻{_semantic_count(getattr(item, 'headline_capital_flow_count_3d', 0))}条"
            if _semantic_count(getattr(item, "headline_capital_flow_count_3d", 0)) > 0
            else ""
        )
        catalyst_phrase = _first_positive_compact_phrase(item, COMPACT_CATALYST_SUBCATEGORY_PRIORITY) or (
            f"经营催化类新闻{_semantic_count(getattr(item, 'headline_business_catalyst_count_3d', 0))}条"
            if _semantic_count(getattr(item, "headline_business_catalyst_count_3d", 0)) > 0
            else ""
        )
        risk_phrase = _first_positive_compact_phrase(item, COMPACT_RISK_SUBCATEGORY_PRIORITY) or (
            f"风险事件类新闻{_semantic_count(getattr(item, 'headline_risk_event_count_3d', 0))}条"
            if _semantic_count(getattr(item, "headline_risk_event_count_3d", 0)) > 0
            else ""
        )

        if capital_phrase and broker_phrase:
            return f"近3日{capital_phrase} + {broker_phrase}共振"
        if catalyst_phrase and capital_phrase:
            return f"近3日{catalyst_phrase} + {capital_phrase}"
        if risk_phrase and not catalyst_phrase:
            return f"近3日{risk_phrase}但无新增催化"

        for phrase in (broker_phrase, capital_phrase, catalyst_phrase, risk_phrase):
            if phrase:
                return f"近3日{phrase}"

        return "近3日无明显新增催化"

    positive_count = _as_int(getattr(item, "headline_keyword_positive_count_3d", 0))
    risk_count = _as_int(getattr(item, "headline_keyword_risk_count_3d", 0))
    major_count = _as_int(getattr(item, "major_news_count_3d", 0))

    if positive_count > 0 and major_count > 0:
        return f"近3日正向新闻{positive_count}条 + 近3日重大/主线催化新闻{major_count}条"
    if positive_count > 0 and risk_count > 0:
        return f"近3日正向新闻{positive_count}条 + 近3日风险关键词新闻{risk_count}条"
    if major_count > 0 and risk_count > 0:
        return f"近3日重大/主线催化新闻{major_count}条 + 近3日风险关键词新闻{risk_count}条"
    if positive_count > 0:
        return f"近3日正向新闻{positive_count}条"
    if major_count > 0:
        return f"近3日重大/主线催化新闻{major_count}条"
    if risk_count > 0:
        return f"近3日风险关键词新闻{risk_count}条"
    return "近3日无明显新增催化"


def build_topn_news_enrichment(
    candidates: pd.DataFrame,
    news_features: pd.DataFrame,
) -> pd.DataFrame:
    if candidates.empty:
        return _empty_enrichment()

    candidate_frame = candidates.copy()
    feature_frame = news_features.copy()
    candidate_frame["trade_date"] = pd.to_datetime(candidate_frame["trade_date"], errors="coerce").dt.date
    if feature_frame.empty:
        feature_frame = pd.DataFrame(columns=["trade_date", "asset_id"])
    else:
        feature_frame["trade_date"] = pd.to_datetime(feature_frame["trade_date"], errors="coerce").dt.date
        # Task 4 keeps a minimal, deterministic duplicate contract: if the input
        # file has repeated trade_date + asset_id rows, the last row in file
        # order wins. This is not freshness-aware aggregation.
        feature_frame = feature_frame.drop_duplicates(
            subset=["trade_date", "asset_id"],
            keep="last",
        ).copy()
        feature_frame["has_news_feature"] = True
    has_semantic_news_features = all(column in feature_frame.columns for column in SEMANTIC_NEWS_FEATURE_COLUMNS)

    merged = candidate_frame.merge(
        feature_frame,
        on=["trade_date", "asset_id"],
        how="left",
        suffixes=("", "_feature"),
    )

    rows: list[dict[str, object]] = []
    for item in merged.itertuples(index=False):
        positive_count = _as_int(getattr(item, "headline_keyword_positive_count_3d", 0))
        risk_count = _as_int(getattr(item, "headline_keyword_risk_count_3d", 0))
        major_count = _as_int(getattr(item, "major_news_count_3d", 0))
        overnight_count = _as_int(getattr(item, "overnight_news_count", 0))
        broker_reco_count = _semantic_count(getattr(item, "headline_broker_reco_count_3d", 0))
        capital_flow_count = _semantic_count(getattr(item, "headline_capital_flow_count_3d", 0))
        business_catalyst_count = _semantic_count(getattr(item, "headline_business_catalyst_count_3d", 0))
        risk_event_count = _semantic_count(getattr(item, "headline_risk_event_count_3d", 0))
        gold_stock_count = _semantic_count(getattr(item, "headline_gold_stock_count_3d", 0))
        rating_action_count = _semantic_count(getattr(item, "headline_rating_action_count_3d", 0))
        broker_positive_view_count = _semantic_count(getattr(item, "headline_broker_positive_view_count_3d", 0))
        main_force_flow_count = _semantic_count(getattr(item, "headline_main_force_flow_count_3d", 0))
        margin_flow_count = _semantic_count(getattr(item, "headline_margin_flow_count_3d", 0))
        capital_flow_generic_count = _semantic_count(getattr(item, "headline_capital_flow_generic_count_3d", 0))
        order_bid_count = _semantic_count(getattr(item, "headline_order_bid_count_3d", 0))
        product_breakthrough_count = _semantic_count(getattr(item, "headline_product_breakthrough_count_3d", 0))
        industry_boom_count = _semantic_count(getattr(item, "headline_industry_boom_count_3d", 0))
        regulatory_inquiry_count = _semantic_count(getattr(item, "headline_regulatory_inquiry_count_3d", 0))
        shareholder_reduction_count = _semantic_count(getattr(item, "headline_shareholder_reduction_count_3d", 0))
        litigation_penalty_count = _semantic_count(getattr(item, "headline_litigation_penalty_count_3d", 0))
        loss_warning_count = _semantic_count(getattr(item, "headline_loss_warning_count_3d", 0))
        has_news_feature = pd.notna(getattr(item, "has_news_feature", None))
        raw_attention_level = getattr(item, "news_attention_level", None)
        attention_level = _normalize_attention_level(raw_attention_level, has_news_feature=has_news_feature)
        row_has_semantic_values = all(
            _has_non_negative_parseable_semantic_value(getattr(item, column, None))
            for column in SEMANTIC_NEWS_FEATURE_COLUMNS
        )
        use_semantic_mode = has_semantic_news_features and row_has_semantic_values
        has_positive_semantic_subcategory = any(
            count > 0
            for count in (
                gold_stock_count,
                rating_action_count,
                broker_positive_view_count,
                main_force_flow_count,
                margin_flow_count,
                capital_flow_generic_count,
                order_bid_count,
                product_breakthrough_count,
                industry_boom_count,
            )
        )
        has_risk_semantic_subcategory = any(
            count > 0
            for count in (
                regulatory_inquiry_count,
                shareholder_reduction_count,
                litigation_penalty_count,
                loss_warning_count,
            )
        )

        if use_semantic_mode:
            use_fallback_summaries = (
                has_news_feature
                and attention_level in {"low", "medium", "high"}
                and broker_reco_count == 0
                and capital_flow_count == 0
                and business_catalyst_count == 0
                and not has_positive_semantic_subcategory
            )
            use_quiet_overnight_note = (
                has_news_feature
                and attention_level in {"low", "medium", "high"}
                and broker_reco_count == 0
                and capital_flow_count == 0
                and business_catalyst_count == 0
                and risk_event_count == 0
                and not has_positive_semantic_subcategory
            )
        else:
            use_fallback_summaries = (
                has_news_feature
                and attention_level in {"low", "medium", "high"}
                and positive_count == 0
                and risk_count == 0
                and major_count == 0
                and overnight_count == 0
            )
            use_quiet_overnight_note = use_fallback_summaries
        fallback_summaries = (
            _build_zero_count_fallback_summaries(attention_level) if use_fallback_summaries else {}
        )

        if use_semantic_mode:
            consensus_subcategory_summary = _first_positive_semantic_summary(
                item,
                SEMANTIC_CONSENSUS_SUBCATEGORY_PRIORITY,
                attention_level=attention_level,
            )
            risk_subcategory_summary = _first_positive_semantic_summary(
                item,
                SEMANTIC_RISK_SUBCATEGORY_PRIORITY,
            )
            theme_subcategory_summary = _first_positive_semantic_summary(
                item,
                SEMANTIC_THEME_SUBCATEGORY_PRIORITY,
            )
            news_consensus_summary = (
                fallback_summaries.get("news_consensus_summary")
                if use_fallback_summaries
                else (
                    consensus_subcategory_summary
                    or (
                        f"近3日券商推荐类新闻{broker_reco_count}条，关注度{attention_level}"
                        if broker_reco_count > 0
                        else (
                            f"近3日资金关注类新闻{capital_flow_count}条，关注度{attention_level}"
                            if capital_flow_count > 0
                            else (
                                f"近3日经营催化类新闻{business_catalyst_count}条，关注度{attention_level}"
                                if business_catalyst_count > 0
                                else ""
                            )
                        )
                    )
                )
            )
            news_risk_summary = (
                risk_subcategory_summary
                or (
                    f"近3日风险事件类新闻{risk_event_count}条"
                    if risk_event_count > 0
                    else (
                        fallback_summaries.get("news_risk_summary")
                        if use_fallback_summaries
                        else ("近3日未见风险关键词新闻" if has_news_feature else "")
                    )
                )
            )
            theme_catalyst_summary = (
                fallback_summaries.get("theme_catalyst_summary")
                if use_fallback_summaries
                else (
                    theme_subcategory_summary
                    or (
                        f"近3日经营/主题催化新闻{business_catalyst_count}条"
                        if business_catalyst_count > 0
                        else (
                            f"近3日券商催化类新闻{broker_reco_count}条"
                            if broker_reco_count > 0
                            else (
                                f"近3日资金关注类新闻{capital_flow_count}条"
                                if capital_flow_count > 0
                                else ("近3日未见重大/主线催化新闻" if has_news_feature else "")
                            )
                        )
                    )
                )
            )
        else:
            news_consensus_summary = (
                fallback_summaries.get("news_consensus_summary")
                if use_fallback_summaries
                else (
                    f"近3日正向新闻{positive_count}条，关注度{attention_level}"
                    if positive_count > 0
                    else ""
                )
            )
            news_risk_summary = (
                fallback_summaries.get("news_risk_summary")
                if use_fallback_summaries
                else (
                    f"近3日风险关键词新闻{risk_count}条"
                    if risk_count > 0
                    else ""
                )
            )
            theme_catalyst_summary = (
                fallback_summaries.get("theme_catalyst_summary")
                if use_fallback_summaries
                else (
                    f"近3日重大/主线催化新闻{major_count}条"
                    if major_count > 0
                    else (f"近3日正向/催化新闻{positive_count}条" if positive_count > 0 else "")
                )
            )

        news_compact_summary = _build_news_compact_summary(
            item,
            has_news_feature=has_news_feature,
            use_semantic_mode=use_semantic_mode,
        )

        row = {
            "trade_date": item.trade_date.isoformat() if pd.notna(item.trade_date) else None,
            "asset_id": item.asset_id,
            "ts_code": getattr(item, "ts_code", None),
            "stock_name": getattr(item, "stock_name", None),
            "news_consensus_summary": news_consensus_summary,
            "news_risk_summary": news_risk_summary,
            "news_compact_summary": news_compact_summary,
            "theme_catalyst_summary": theme_catalyst_summary,
            "historical_event_summary": _build_historical_event_summary(item),
            "overnight_catalyst_note": (
                f"隔夜催化新闻{overnight_count}条"
                if overnight_count > 0
                else (
                    fallback_summaries.get("overnight_catalyst_note")
                    if use_quiet_overnight_note
                    else ""
                )
            ),
            "news_attention_level": attention_level,
            "news_risk_attention_flag": (
                (
                    risk_event_count > 0
                    or has_risk_semantic_subcategory
                    if use_semantic_mode
                    else risk_count > 0
                )
                if has_news_feature
                else None
            ),
        }
        row["news_enrichment_quality_flag"] = _derive_quality_flag(row)
        rows.append(row)

    frame = pd.DataFrame(rows).reindex(columns=TOPN_NEWS_ENRICHMENT_COLUMNS)
    if not frame.empty:
        frame["news_risk_attention_flag"] = frame["news_risk_attention_flag"].astype(object)
    return frame


def run_topn_news_enrichment(
    candidates_path: str | Path,
    news_features_path: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    candidate_frame = pd.read_csv(candidates_path)
    news_feature_frame = pd.read_csv(news_features_path)
    enrichment = build_topn_news_enrichment(
        candidates=candidate_frame,
        news_features=news_feature_frame,
    )

    destination_dir = Path(output_dir or "outputs/research/topn_news_enrichment")
    destination_dir.mkdir(parents=True, exist_ok=True)
    enrichment_path = destination_dir / "topn_news_enrichment.csv"
    enrichment.to_csv(enrichment_path, index=False)

    return {
        "enrichment": enrichment,
        "paths": {"enrichment": str(enrichment_path)},
    }
