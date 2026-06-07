import pytest

from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.topn_news_enrichment import (
    build_topn_news_enrichment,
    run_topn_news_enrichment,
)


def _build_single_semantic_row_enrichment(
    **feature_overrides: object,
) -> pd.DataFrame:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_keyword_positive_count_3d": 0,
                "headline_keyword_risk_count_3d": 0,
                "major_news_count_3d": 0,
                "overnight_news_count": 0,
                "headline_broker_reco_count_3d": 0,
                "headline_capital_flow_count_3d": 0,
                "headline_business_catalyst_count_3d": 0,
                "headline_risk_event_count_3d": 0,
                **feature_overrides,
            }
        ]
    )
    return build_topn_news_enrichment(candidates=candidates, news_features=features)


def test_build_topn_news_enrichment_summarizes_catalyst_and_risk() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "high",
                "headline_keyword_positive_count_3d": 3,
                "headline_keyword_risk_count_3d": 1,
                "major_news_count_3d": 2,
                "overnight_news_count": 1,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日重大/主线催化新闻2条"
    assert enriched.loc[0, "news_consensus_summary"] == "近3日正向新闻3条，关注度high"
    assert enriched.loc[0, "news_risk_summary"] == "近3日风险关键词新闻1条"
    assert enriched.loc[0, "overnight_catalyst_note"] == "隔夜催化新闻1条"
    assert enriched.loc[0, "news_risk_attention_flag"] is True
    assert enriched.loc[0, "news_enrichment_quality_flag"] == "rich"


def test_build_topn_news_enrichment_marks_missing_news_coverage_as_unknown() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300831",
                "ts_code": "300831.SZ",
                "stock_name": "派瑞股份",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "high",
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert len(enriched) == 1
    assert enriched.loc[0, "news_attention_level"] == "unknown"
    assert enriched.loc[0, "news_consensus_summary"] == ""
    assert enriched.loc[0, "news_risk_summary"] == ""
    assert enriched.loc[0, "theme_catalyst_summary"] == ""
    assert enriched.loc[0, "overnight_catalyst_note"] == ""
    assert enriched.loc[0, "news_compact_summary"] == ""
    assert enriched.loc[0, "news_risk_attention_flag"] is None


@pytest.mark.parametrize(
    "feature_overrides, expected_compact",
    [
        (
            {
                "headline_main_force_flow_count_3d": 1,
                "headline_gold_stock_count_3d": 1,
            },
            "近3日主力资金关注 + 券商金股推荐共振",
        ),
        (
            {
                "headline_order_bid_count_3d": 1,
                "headline_main_force_flow_count_3d": 1,
            },
            "近3日订单/中标催化 + 主力资金关注",
        ),
        (
            {
                "headline_regulatory_inquiry_count_3d": 1,
            },
            "近3日监管问询但无新增催化",
        ),
        (
            {
                "headline_main_force_flow_count_3d": 1,
            },
            "近3日主力资金关注",
        ),
        (
            {},
            "近3日无明显新增催化",
        ),
    ],
)
def test_build_topn_news_enrichment_composes_news_compact_summary(
    feature_overrides: dict[str, object],
    expected_compact: str,
) -> None:
    enriched = _build_single_semantic_row_enrichment(**feature_overrides)

    assert enriched.loc[0, "news_compact_summary"] == expected_compact


def test_build_topn_news_enrichment_uses_category_level_semantic_phrase_when_subcategories_are_absent() -> None:
    enriched = _build_single_semantic_row_enrichment(
        headline_broker_reco_count_3d=1,
        headline_gold_stock_count_3d=0,
        headline_rating_action_count_3d=0,
        headline_broker_positive_view_count_3d=0,
    )

    assert enriched.loc[0, "news_compact_summary"] == "近3日券商推荐类新闻1条"


@pytest.mark.parametrize(
    "feature_overrides, expected_compact",
    [
        ({"headline_broker_reco_count_3d": 1}, "近3日券商推荐类新闻1条"),
        ({"headline_capital_flow_count_3d": 1}, "近3日资金关注类新闻1条"),
        ({"headline_business_catalyst_count_3d": 1}, "近3日经营催化类新闻1条"),
        ({"headline_risk_event_count_3d": 1}, "近3日风险事件类新闻1条但无新增催化"),
    ],
)
def test_build_topn_news_enrichment_uses_category_level_semantic_fallback_for_compact_summary(
    feature_overrides: dict[str, object],
    expected_compact: str,
) -> None:
    enriched = _build_single_semantic_row_enrichment(**feature_overrides)

    assert enriched.loc[0, "news_compact_summary"] == expected_compact


def test_build_topn_news_enrichment_uses_legacy_signals_for_compact_summary() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_keyword_positive_count_3d": 2,
                "headline_keyword_risk_count_3d": 1,
                "major_news_count_3d": 3,
                "overnight_news_count": 0,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_compact_summary"] == "近3日正向新闻2条 + 近3日重大/主线催化新闻3条"


def test_build_topn_news_enrichment_uses_legacy_positive_and_risk_signals_for_compact_summary() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_keyword_positive_count_3d": 2,
                "headline_keyword_risk_count_3d": 1,
                "major_news_count_3d": 0,
                "overnight_news_count": 0,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_compact_summary"] == "近3日正向新闻2条 + 近3日风险关键词新闻1条"


@pytest.mark.parametrize(
    "feature_overrides, expected_consensus, expected_theme",
    [
        (
            {
                "news_attention_level": "low",
                "headline_broker_reco_count_3d": 1,
                "headline_capital_flow_count_3d": 0,
                "headline_business_catalyst_count_3d": 0,
                "headline_risk_event_count_3d": 0,
            },
            "近3日券商推荐类新闻1条，关注度low",
            "近3日券商催化类新闻1条",
        ),
        (
            {
                "news_attention_level": "medium",
                "headline_broker_reco_count_3d": 0,
                "headline_capital_flow_count_3d": 2,
                "headline_business_catalyst_count_3d": 0,
                "headline_risk_event_count_3d": 0,
            },
            "近3日资金关注类新闻2条，关注度medium",
            "近3日资金关注类新闻2条",
        ),
        (
            {
                "news_attention_level": "high",
                "headline_broker_reco_count_3d": 0,
                "headline_capital_flow_count_3d": 0,
                "headline_business_catalyst_count_3d": 3,
                "headline_risk_event_count_3d": 0,
            },
            "近3日经营催化类新闻3条，关注度high",
            "近3日经营/主题催化新闻3条",
        ),
    ],
)
def test_build_topn_news_enrichment_prioritizes_semantic_counters_for_consensus_and_theme(
    feature_overrides: dict[str, object],
    expected_consensus: str,
    expected_theme: str,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                **feature_overrides,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_consensus_summary"] == expected_consensus
    assert enriched.loc[0, "theme_catalyst_summary"] == expected_theme


@pytest.mark.parametrize(
    "feature_overrides, expected_consensus",
    [
        (
            {"headline_gold_stock_count_3d": 1},
            "近3日券商金股/推荐新闻1条，关注度low",
        ),
        (
            {"headline_rating_action_count_3d": 2},
            "近3日评级/目标价新闻2条，关注度low",
        ),
        (
            {"headline_broker_positive_view_count_3d": 3},
            "近3日券商看好类新闻3条，关注度low",
        ),
        (
            {"headline_main_force_flow_count_3d": 4},
            "近3日主力资金关注新闻4条，关注度low",
        ),
        (
            {"headline_margin_flow_count_3d": 5},
            "近3日融资/杠杆资金新闻5条，关注度low",
        ),
        (
            {"headline_capital_flow_generic_count_3d": 6},
            "近3日资金关注类新闻6条，关注度low",
        ),
        (
            {"headline_order_bid_count_3d": 7},
            "近3日订单/中标新闻7条，关注度low",
        ),
        (
            {"headline_product_breakthrough_count_3d": 8},
            "近3日新品/突破新闻8条，关注度low",
        ),
        (
            {"headline_industry_boom_count_3d": 9},
            "近3日行业景气新闻9条，关注度low",
        ),
    ],
)
def test_build_topn_news_enrichment_uses_subcategory_priority_for_consensus(
    feature_overrides: dict[str, object],
    expected_consensus: str,
) -> None:
    enriched = _build_single_semantic_row_enrichment(**feature_overrides)

    assert enriched.loc[0, "news_consensus_summary"] == expected_consensus


@pytest.mark.parametrize(
    "feature_overrides, expected_risk",
    [
        (
            {"headline_regulatory_inquiry_count_3d": 1},
            "近3日监管问询/风险提示新闻1条",
        ),
        (
            {"headline_shareholder_reduction_count_3d": 2},
            "近3日减持类风险新闻2条",
        ),
        (
            {"headline_litigation_penalty_count_3d": 3},
            "近3日诉讼/处罚类风险新闻3条",
        ),
        (
            {"headline_loss_warning_count_3d": 4},
            "近3日亏损/业绩风险新闻4条",
        ),
    ],
)
def test_build_topn_news_enrichment_uses_subcategory_priority_for_risk(
    feature_overrides: dict[str, object],
    expected_risk: str,
) -> None:
    enriched = _build_single_semantic_row_enrichment(**feature_overrides)

    assert enriched.loc[0, "news_risk_summary"] == expected_risk


def test_build_topn_news_enrichment_keeps_quiet_fallback_for_risk_only_subcategory_hits() -> None:
    enriched = _build_single_semantic_row_enrichment(
        headline_regulatory_inquiry_count_3d=1,
    )

    assert enriched.loc[0, "news_risk_summary"] == "近3日监管问询/风险提示新闻1条"
    assert enriched.loc[0, "news_consensus_summary"] == "近3日未见明显正向新闻，关注度low"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日未见重大/主线催化新闻"
    assert enriched.loc[0, "news_risk_attention_flag"] is True


def test_build_topn_news_enrichment_adds_historical_event_summary_without_affecting_media_summaries() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2025-01-24",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-24",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_keyword_positive_count_3d": 2,
                "headline_keyword_risk_count_3d": 1,
                "major_news_count_3d": 0,
                "overnight_news_count": 0,
                "earnings_notice_count_20d": 1,
                "risk_notice_count_20d": 0,
                "research_report_count_20d": 2,
                "rating_action_count_20d": 1,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "historical_event_summary"] == "近20日有1条业绩类公告 + 2篇机构研报"
    assert enriched.loc[0, "news_consensus_summary"] == "近3日正向新闻2条，关注度low"
    assert enriched.loc[0, "news_risk_summary"] == "近3日风险关键词新闻1条"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日正向/催化新闻2条"
    assert enriched.loc[0, "overnight_catalyst_note"] == ""


def test_build_topn_news_enrichment_prefers_rating_action_histories_when_notice_counts_are_absent() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2025-01-24",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-24",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_keyword_positive_count_3d": 0,
                "headline_keyword_risk_count_3d": 0,
                "major_news_count_3d": 0,
                "overnight_news_count": 0,
                "earnings_notice_count_20d": 0,
                "risk_notice_count_20d": 0,
                "research_report_count_20d": 2,
                "rating_action_count_20d": 1,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "historical_event_summary"] == "近20日有2篇机构研报，其中1次评级动作"
    assert enriched.loc[0, "news_consensus_summary"] == "近3日未见明显正向新闻，关注度low"
    assert enriched.loc[0, "news_risk_summary"] == "近3日未见风险关键词新闻"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日未见重大/主线催化新闻"


@pytest.mark.parametrize(
    "feature_overrides, expected_theme",
    [
        (
            {"headline_order_bid_count_3d": 1},
            "近3日订单/中标催化新闻1条",
        ),
        (
            {"headline_product_breakthrough_count_3d": 2},
            "近3日新品/突破催化新闻2条",
        ),
        (
            {"headline_industry_boom_count_3d": 3},
            "近3日景气/扩产催化新闻3条",
        ),
        (
            {"headline_gold_stock_count_3d": 4},
            "近3日券商金股催化新闻4条",
        ),
        (
            {"headline_rating_action_count_3d": 5},
            "近3日评级催化新闻5条",
        ),
        (
            {"headline_main_force_flow_count_3d": 6},
            "近3日主力资金关注新闻6条",
        ),
        (
            {"headline_margin_flow_count_3d": 7},
            "近3日融资/杠杆资金新闻7条",
        ),
        (
            {"headline_capital_flow_generic_count_3d": 8},
            "近3日资金关注类新闻8条",
        ),
    ],
)
def test_build_topn_news_enrichment_uses_subcategory_priority_for_theme(
    feature_overrides: dict[str, object],
    expected_theme: str,
) -> None:
    enriched = _build_single_semantic_row_enrichment(**feature_overrides)

    assert enriched.loc[0, "theme_catalyst_summary"] == expected_theme


def test_build_topn_news_enrichment_ignores_dirty_subcategory_values_and_keeps_category_fallback() -> None:
    enriched = _build_single_semantic_row_enrichment(
        headline_gold_stock_count_3d="N/A",
        headline_rating_action_count_3d="",
        headline_broker_positive_view_count_3d="-1",
        headline_main_force_flow_count_3d=0,
        headline_margin_flow_count_3d=0,
        headline_capital_flow_generic_count_3d=0,
        headline_order_bid_count_3d=0,
        headline_product_breakthrough_count_3d=0,
        headline_industry_boom_count_3d=0,
        headline_regulatory_inquiry_count_3d=0,
        headline_shareholder_reduction_count_3d=0,
        headline_litigation_penalty_count_3d=0,
        headline_loss_warning_count_3d=0,
        headline_broker_reco_count_3d=1,
        headline_business_catalyst_count_3d=3,
    )

    assert enriched.loc[0, "news_consensus_summary"] == "近3日券商推荐类新闻1条，关注度low"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日经营/主题催化新闻3条"
    assert enriched.loc[0, "news_compact_summary"] == "近3日券商推荐类新闻1条"


def test_build_topn_news_enrichment_reports_risk_event_summary() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_broker_reco_count_3d": 0,
                "headline_capital_flow_count_3d": 0,
                "headline_business_catalyst_count_3d": 0,
                "headline_risk_event_count_3d": 2,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_risk_summary"] == "近3日风险事件类新闻2条"
    assert enriched.loc[0, "news_consensus_summary"] == "近3日未见明显正向新闻，关注度low"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日未见重大/主线催化新闻"
    assert enriched.loc[0, "news_risk_attention_flag"] is True


def test_build_topn_news_enrichment_uses_quiet_fallback_when_covered_but_no_semantic_category() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "medium",
                "headline_broker_reco_count_3d": 0,
                "headline_capital_flow_count_3d": 0,
                "headline_business_catalyst_count_3d": 0,
                "headline_risk_event_count_3d": 0,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_consensus_summary"] == "近3日未见明显正向新闻，关注度medium"
    assert enriched.loc[0, "news_risk_summary"] == "近3日未见风险关键词新闻"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日未见重大/主线催化新闻"
    assert enriched.loc[0, "news_risk_attention_flag"] is False


def test_build_topn_news_enrichment_keeps_overnight_note_when_semantic_counts_are_zero() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_broker_reco_count_3d": 0,
                "headline_capital_flow_count_3d": 0,
                "headline_business_catalyst_count_3d": 0,
                "headline_risk_event_count_3d": 0,
                "overnight_news_count": 2,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_consensus_summary"] == "近3日未见明显正向新闻，关注度low"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日未见重大/主线催化新闻"
    assert enriched.loc[0, "overnight_catalyst_note"] == "隔夜催化新闻2条"


def test_build_topn_news_enrichment_treats_negative_semantic_counts_as_zero() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_broker_reco_count_3d": -1,
                "headline_capital_flow_count_3d": 0,
                "headline_business_catalyst_count_3d": 0,
                "headline_risk_event_count_3d": 0,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_consensus_summary"] == "近3日未见明显正向新闻，关注度low"
    assert enriched.loc[0, "news_risk_summary"] == "近3日未见风险关键词新闻"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日未见重大/主线催化新闻"
    assert enriched.loc[0, "overnight_catalyst_note"] == "近3日未见隔夜催化新闻"


def test_build_topn_news_enrichment_skips_quiet_overnight_note_when_risk_event_exists() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_broker_reco_count_3d": 0,
                "headline_capital_flow_count_3d": 0,
                "headline_business_catalyst_count_3d": 0,
                "headline_risk_event_count_3d": 1,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_risk_summary"] == "近3日风险事件类新闻1条"
    assert enriched.loc[0, "overnight_catalyst_note"] == ""


def test_build_topn_news_enrichment_uses_semantic_mode_per_row_in_mixed_schema_file() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            },
            {
                "asset_id": "CN:SZ:300831",
                "ts_code": "300831.SZ",
                "stock_name": "派瑞股份",
                "trade_date": "2026-06-02",
            },
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_broker_reco_count_3d": 1,
                "headline_capital_flow_count_3d": 0,
                "headline_business_catalyst_count_3d": 0,
                "headline_risk_event_count_3d": 0,
                "headline_keyword_positive_count_3d": 0,
                "major_news_count_3d": 0,
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SZ:300831",
                "ts_code": "300831.SZ",
                "news_attention_level": "medium",
                "headline_broker_reco_count_3d": "",
                "headline_capital_flow_count_3d": "",
                "headline_business_catalyst_count_3d": "",
                "headline_risk_event_count_3d": "",
                "headline_keyword_positive_count_3d": 2,
                "headline_keyword_risk_count_3d": 1,
                "major_news_count_3d": 1,
                "overnight_news_count": 1,
            },
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    by_asset = enriched.set_index("asset_id")
    assert by_asset.loc["CN:SH:600183", "news_consensus_summary"] == "近3日券商推荐类新闻1条，关注度low"
    assert by_asset.loc["CN:SH:600183", "theme_catalyst_summary"] == "近3日券商催化类新闻1条"
    assert by_asset.loc["CN:SZ:300831", "news_consensus_summary"] == "近3日正向新闻2条，关注度medium"
    assert by_asset.loc["CN:SZ:300831", "theme_catalyst_summary"] == "近3日重大/主线催化新闻1条"


def test_build_topn_news_enrichment_ignores_dirty_semantic_placeholders_for_legacy_rows() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_broker_reco_count_3d": "N/A",
                "headline_capital_flow_count_3d": "",
                "headline_business_catalyst_count_3d": "N/A",
                "headline_risk_event_count_3d": "N/A",
                "headline_keyword_positive_count_3d": 2,
                "headline_keyword_risk_count_3d": 1,
                "major_news_count_3d": 3,
                "overnight_news_count": 1,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_consensus_summary"] == "近3日正向新闻2条，关注度low"
    assert enriched.loc[0, "news_risk_summary"] == "近3日风险关键词新闻1条"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日重大/主线催化新闻3条"
    assert enriched.loc[0, "overnight_catalyst_note"] == "隔夜催化新闻1条"
    assert enriched.loc[0, "news_compact_summary"] == "近3日正向新闻2条 + 近3日重大/主线催化新闻3条"


def test_build_topn_news_enrichment_ignores_negative_semantic_sentinels_for_legacy_rows() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_broker_reco_count_3d": -1,
                "headline_capital_flow_count_3d": -1,
                "headline_business_catalyst_count_3d": -1,
                "headline_risk_event_count_3d": -1,
                "headline_keyword_positive_count_3d": 2,
                "headline_keyword_risk_count_3d": 1,
                "major_news_count_3d": 3,
                "overnight_news_count": 1,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_consensus_summary"] == "近3日正向新闻2条，关注度low"
    assert enriched.loc[0, "news_risk_summary"] == "近3日风险关键词新闻1条"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日重大/主线催化新闻3条"
    assert enriched.loc[0, "overnight_catalyst_note"] == "隔夜催化新闻1条"
    assert enriched.loc[0, "news_compact_summary"] == "近3日正向新闻2条 + 近3日重大/主线催化新闻3条"


def test_build_topn_news_enrichment_falls_back_to_legacy_when_semantic_row_is_mixed_dirty() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_broker_reco_count_3d": 0,
                "headline_capital_flow_count_3d": -1,
                "headline_business_catalyst_count_3d": "N/A",
                "headline_risk_event_count_3d": "",
                "headline_keyword_positive_count_3d": 2,
                "headline_keyword_risk_count_3d": 1,
                "major_news_count_3d": 3,
                "overnight_news_count": 1,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_consensus_summary"] == "近3日正向新闻2条，关注度low"
    assert enriched.loc[0, "news_risk_summary"] == "近3日风险关键词新闻1条"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日重大/主线催化新闻3条"
    assert enriched.loc[0, "overnight_catalyst_note"] == "隔夜催化新闻1条"
    assert enriched.loc[0, "news_compact_summary"] == "近3日正向新闻2条 + 近3日重大/主线催化新闻3条"


@pytest.mark.parametrize("attention_level", ["low", "medium", "high"])
def test_build_topn_news_enrichment_uses_fallback_summary_when_counts_are_zero(
    attention_level: str,
) -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": attention_level,
                "headline_keyword_positive_count_3d": 0,
                "headline_keyword_risk_count_3d": 0,
                "major_news_count_3d": 0,
                "overnight_news_count": 0,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_attention_level"] == attention_level
    assert enriched.loc[0, "news_consensus_summary"] == f"近3日未见明显正向新闻，关注度{attention_level}"
    assert enriched.loc[0, "news_risk_summary"] == "近3日未见风险关键词新闻"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日未见重大/主线催化新闻"
    assert enriched.loc[0, "overnight_catalyst_note"] == "近3日未见隔夜催化新闻"
    assert enriched.loc[0, "news_enrichment_quality_flag"] == "rich"


def test_build_topn_news_enrichment_normalizes_attention_level_and_handles_dirty_counts() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": " HIGH ",
                "headline_keyword_positive_count_3d": "N/A",
                "headline_keyword_risk_count_3d": "",
                "major_news_count_3d": "1.0",
                "overnight_news_count": "2.00",
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_attention_level"] == "high"
    assert enriched.loc[0, "news_consensus_summary"] == ""
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日重大/主线催化新闻1条"
    assert enriched.loc[0, "overnight_catalyst_note"] == "隔夜催化新闻2条"
    assert enriched.loc[0, "news_risk_summary"] == ""
    assert enriched.loc[0, "news_risk_attention_flag"] is False


def test_build_topn_news_enrichment_aligns_catalyst_trigger_and_wording() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            },
            {
                "asset_id": "CN:SH:688390",
                "ts_code": "688390.SH",
                "stock_name": "固德威",
                "trade_date": "2026-06-02",
            },
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "headline_keyword_positive_count_3d": 2,
                "major_news_count_3d": 0,
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:688390",
                "headline_keyword_positive_count_3d": 1,
                "major_news_count_3d": 3,
            },
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    by_asset = enriched.set_index("asset_id")
    assert by_asset.loc["CN:SH:600183", "theme_catalyst_summary"] == "近3日正向/催化新闻2条"
    assert by_asset.loc["CN:SH:688390", "theme_catalyst_summary"] == "近3日重大/主线催化新闻3条"
    assert "0条" not in by_asset.loc["CN:SH:600183", "theme_catalyst_summary"]


def test_build_topn_news_enrichment_file_order_last_row_wins_when_features_duplicate_key() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "news_attention_level": "low",
                "headline_keyword_positive_count_3d": 1,
            },
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "news_attention_level": "high",
                "headline_keyword_positive_count_3d": 4,
                "major_news_count_3d": 2,
            },
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert len(enriched) == 1
    assert enriched.loc[0, "asset_id"] == "CN:SH:600183"
    assert enriched.loc[0, "news_attention_level"] == "high"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日重大/主线催化新闻2条"
    assert enriched.loc[0, "news_risk_attention_flag"] is False


def test_run_topn_news_enrichment_writes_artifact_and_returns_stable_path(tmp_path) -> None:
    candidates_path = tmp_path / "candidates.csv"
    news_features_path = tmp_path / "news_features.csv"
    output_dir = tmp_path / "out"

    pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2026-06-02",
            },
            {
                "asset_id": "CN:SZ:300831",
                "ts_code": "300831.SZ",
                "stock_name": "派瑞股份",
                "trade_date": "2026-06-02",
            },
        ]
    ).to_csv(candidates_path, index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "CN:SH:600183",
                "news_attention_level": "high",
                "headline_keyword_positive_count_3d": 2,
                "headline_keyword_risk_count_3d": 1,
                "major_news_count_3d": 1,
            }
        ]
    ).to_csv(news_features_path, index=False)

    result = run_topn_news_enrichment(
        candidates_path=candidates_path,
        news_features_path=news_features_path,
        output_dir=output_dir,
    )

    enrichment_path = output_dir / "topn_news_enrichment.csv"
    assert result["paths"]["enrichment"] == str(enrichment_path)
    assert enrichment_path.exists()

    written = pd.read_csv(enrichment_path)
    assert len(written) == 2
    by_asset = written.set_index("asset_id")
    assert by_asset.loc["CN:SH:600183", "news_attention_level"] == "high"
    assert by_asset.loc["CN:SZ:300831", "news_attention_level"] == "unknown"


def test_topn_news_enrichment_cli_writes_artifact_and_prints_path(
    monkeypatch,
    capsys,
    tmp_path,
) -> None:
    output_path = tmp_path / "topn_news_enrichment.csv"
    monkeypatch.setattr(
        "stock_research.cli.run_topn_news_enrichment",
        lambda **kwargs: {
            "enrichment": pd.DataFrame(),
            "paths": {"enrichment": str(output_path)},
        },
    )

    cli.main_for_args(
        [
            "topn-news-enrichment",
            "--candidates-path",
            "inputs/candidates.csv",
            "--news-features-path",
            "inputs/news_features.csv",
        ]
    )

    output = capsys.readouterr().out
    assert "topn_news_enrichment|enrichment|" in output
    assert str(output_path) in output


def test_build_topn_news_enrichment_reports_historical_summary_for_report_only_coverage() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2025-01-24",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-24",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_keyword_positive_count_3d": 0,
                "headline_keyword_risk_count_3d": 0,
                "major_news_count_3d": 0,
                "overnight_news_count": 0,
                "earnings_notice_count_20d": 0,
                "risk_notice_count_20d": 0,
                "research_report_count_20d": 2,
                "rating_action_count_20d": 0,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "historical_event_summary"] == "近20日有2篇机构研报"


def test_build_topn_news_enrichment_reports_historical_summary_for_notice_coverage() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "trade_date": "2025-01-24",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-24",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "news_attention_level": "low",
                "headline_keyword_positive_count_3d": 0,
                "headline_keyword_risk_count_3d": 0,
                "major_news_count_3d": 0,
                "overnight_news_count": 0,
                "notice_count_3d": 1,
                "notice_count_10d": 2,
                "governance_notice_count_20d": 1,
                "contract_investment_notice_count_20d": 1,
                "earnings_notice_count_20d": 0,
                "risk_notice_count_20d": 0,
                "research_report_count_20d": 0,
                "rating_action_count_20d": 0,
            }
        ]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "historical_event_summary"] != ""
    assert "公告" in enriched.loc[0, "historical_event_summary"]
