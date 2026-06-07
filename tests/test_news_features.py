from pathlib import Path

import pandas as pd
import pytest

from stock_research import cli
from stock_research.news_features import (
    _load_assets_for_news_mapping,
    build_news_feature_daily,
    map_news_mentions,
    run_news_feature_diagnostics,
    run_news_feature_backfill,
)


def test_map_news_mentions_matches_ts_code_and_stock_name() -> None:
    events = pd.DataFrame(
        [
            {
                "source_event_id": "n1",
                "title": "生益科技获机构看好",
                "content": "600183.SH 生益科技",
                "published_at": "2026-06-01 08:30:00",
            }
        ]
    )
    assets = pd.DataFrame(
        [{"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}]
    )

    mentions = map_news_mentions(events=events, assets=assets)

    assert len(mentions) == 1
    assert mentions.loc[0, "asset_id"] == "CN:SH:600183"
    assert mentions.loc[0, "mapping_method"] == "ts_code"


def test_map_news_mentions_prefers_matched_candidates_metadata_over_free_text_scan() -> None:
    events = pd.DataFrame(
        [
            {
                "source_event_id": "n_meta",
                "title": "72.06亿元主力资金今日抢筹电子板块",
                "content": "002409 雅克科技 600330 天通股份 600183 生益科技 300408 三环集团",
                "published_at": "2026-06-02 16:53:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "metadata": "{'provider': 'akshare_stock_news_em', 'matched_candidates': [{'asset_id': 'CN:SH:600183', 'ts_code': '600183.SH', 'stock_name': '生益科技'}]}",
            }
        ]
    )
    assets = pd.DataFrame(
        [
            {"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"},
            {"asset_id": "CN:SZ:002409", "ts_code": "002409.SZ", "stock_name": "雅克科技"},
            {"asset_id": "CN:SH:600330", "ts_code": "600330.SH", "stock_name": "天通股份"},
        ]
    )

    mentions = map_news_mentions(events=events, assets=assets)

    assert len(mentions) == 1
    assert mentions.loc[0, "asset_id"] == "CN:SH:600183"
    assert mentions.loc[0, "ts_code"] == "600183.SH"
    assert mentions.loc[0, "mapping_method"] == "matched_candidate"


def test_map_news_mentions_uses_json_metadata_with_null_in_matched_candidates() -> None:
    events = pd.DataFrame(
        [
            {
                "source_event_id": "n_json_meta",
                "title": "生益科技与天通股份合作推进",
                "content": "生益科技 天通股份",
                "published_at": "2026-06-02 16:53:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "metadata": '{"provider":"akshare_stock_news_em","matched_candidates":[{"asset_id":"CN:SH:600183","ts_code":"600183.SH","stock_name":null}]}',
            }
        ]
    )
    assets = pd.DataFrame(
        [
            {"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"},
            {"asset_id": "CN:SH:600330", "ts_code": "600330.SH", "stock_name": "天通股份"},
        ]
    )

    mentions = map_news_mentions(events=events, assets=assets)

    assert len(mentions) == 1
    assert mentions.loc[0, "asset_id"] == "CN:SH:600183"
    assert mentions.loc[0, "mapping_method"] == "matched_candidate"


def test_map_news_mentions_preserves_event_family() -> None:
    events = pd.DataFrame(
        [
            {
                "source_event_id": "n_family",
                "title": "生益科技2024年年度业绩预增公告",
                "content": "600183.SH 生益科技",
                "published_at": "2025-01-24 08:30:00",
                "event_family": "disclosure_notice",
            }
        ]
    )
    assets = pd.DataFrame(
        [{"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}]
    )

    mentions = map_news_mentions(events=events, assets=assets)

    assert len(mentions) == 1
    assert mentions.loc[0, "event_family"] == "disclosure_notice"


def test_map_news_mentions_preserves_event_family_for_matched_candidate_branch() -> None:
    events = pd.DataFrame(
        [
            {
                "source_event_id": "n_matched_family",
                "title": "生益科技2024年年度业绩预增公告",
                "content": "",
                "published_at": "2025-01-24 08:30:00",
                "source_name": "eastmoney_individual_notice",
                "source_channel": "eastmoney_notice",
                "event_family": "disclosure_notice",
                "metadata": '{"matched_candidates":[{"asset_id":"CN:SH:600183","ts_code":"600183.SH","stock_name":"生益科技"}]}',
            }
        ]
    )
    assets = pd.DataFrame(
        [{"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}]
    )

    mentions = map_news_mentions(events=events, assets=assets)

    assert len(mentions) == 1
    assert mentions.loc[0, "mapping_method"] == "matched_candidate"
    assert mentions.loc[0, "event_family"] == "disclosure_notice"


def test_build_news_feature_daily_respects_replay_cutoff() -> None:
    mentions = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "published_at": "2026-06-02 09:00:00",
                "trade_date": "2026-06-02",
                "title": "订单增长",
                "source_name": "cls",
            },
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "published_at": "2026-06-03 09:00:00",
                "trade_date": "2026-06-03",
                "title": "风险提示",
                "source_name": "cls",
            },
        ]
    )

    feature = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert feature.loc[0, "news_count_1d"] == 1


def test_build_news_feature_daily_counts_t_minus_one_evening_news_in_overnight_slice() -> None:
    mentions = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "published_at": "2026-06-05 20:30:00",
                "trade_date": "2026-06-05",
                "title": "T-1 evening 订单增长",
                "source_name": "cls",
            }
        ]
    )

    feature = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-06"],
        mode="replay",
    )

    assert feature.loc[0, "overnight_news_count"] == 1
    assert feature.loc[0, "news_count_1d"] == 0


def test_build_news_feature_daily_counts_family_aware_historical_notice_and_report_features() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "notice-1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2025-01-24",
                "published_at": "2025-01-24 08:30:00",
                "source_name": "eastmoney_individual_notice",
                "source_channel": "eastmoney_notice",
                "title": "生益科技2024年年度业绩预增公告",
                "content": "",
                "event_family": "disclosure_notice",
            },
            {
                "source_event_id": "notice-2",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2025-01-19",
                "published_at": "2025-01-19 09:30:00",
                "source_name": "cninfo_disclosure_announcement",
                "source_channel": "cninfo_notice",
                "title": "关于召开股东大会的通知",
                "content": "",
                "event_family": "disclosure_notice",
            },
            {
                "source_event_id": "notice-3",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2025-01-10",
                "published_at": "2025-01-10 09:30:00",
                "source_name": "cninfo_disclosure_announcement",
                "source_channel": "cninfo_notice",
                "title": "风险提示：公司收到监管问询函",
                "content": "",
                "event_family": "disclosure_notice",
            },
            {
                "source_event_id": "notice-4",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2025-01-08",
                "published_at": "2025-01-08 09:30:00",
                "source_name": "eastmoney_individual_notice",
                "source_channel": "eastmoney_notice",
                "title": "签订重大合同公告",
                "content": "",
                "event_family": "disclosure_notice",
            },
            {
                "source_event_id": "report-1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2025-01-24",
                "published_at": "2025-01-24 10:30:00",
                "source_name": "eastmoney_research_report",
                "source_channel": "eastmoney_research",
                "title": "产品结构优化，业绩爆发式增长",
                "content": "",
                "event_family": "institution_report",
            },
            {
                "source_event_id": "report-2",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2025-01-22",
                "published_at": "2025-01-22 10:30:00",
                "source_name": "eastmoney_research_report",
                "source_channel": "eastmoney_research",
                "title": "上调评级至买入，维持目标价",
                "content": "",
                "event_family": "institution_report",
            },
            {
                "source_event_id": "media-1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2025-01-24",
                "published_at": "2025-01-24 11:30:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "主力资金抢筹生益科技",
                "content": "",
            },
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2025-01-24"],
        mode="replay",
    )

    row = features.iloc[0]
    assert row["notice_count_3d"] == 1
    assert row["notice_count_10d"] == 2
    assert row["risk_notice_count_20d"] == 1
    assert row["earnings_notice_count_20d"] == 1
    assert row["governance_notice_count_20d"] == 1
    assert row["contract_investment_notice_count_20d"] == 1
    assert row["research_report_count_20d"] == 2
    assert row["rating_action_count_20d"] == 1
    assert row["headline_main_force_flow_count_3d"] == 1


def test_build_news_feature_daily_live_mode_uses_all_loaded_mentions() -> None:
    mentions = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "published_at": "2026-06-02 09:00:00",
                "trade_date": "2026-06-02",
                "title": "订单增长",
                "source_name": "cls",
            },
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "published_at": "2026-06-03 09:00:00",
                "trade_date": "2026-06-03",
                "title": "风险提示",
                "source_name": "cls",
            },
        ]
    )

    feature = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="live",
    )

    assert feature.loc[0, "news_count_1d"] == 2
    assert feature.loc[0, "headline_keyword_risk_count_3d"] == 1


def test_build_news_feature_daily_counts_title_semantic_categories() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "主力资金抢筹 生益科技获融资客加仓",
                "content": "",
            },
            {
                "source_event_id": "evt-2",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 10:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "澎湃新闻",
                "title": "券商推荐 生益科技进入6月金股名单",
                "content": "",
            },
            {
                "source_event_id": "evt-3",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 11:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "生益科技订单突破 景气度提升",
                "content": "",
            },
            {
                "source_event_id": "evt-4",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 13:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "生益科技风险提示：监管问询与减持压力",
                "content": "",
            },
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_capital_flow_count_3d"] == 1
    assert features.loc[0, "headline_broker_reco_count_3d"] == 1
    assert features.loc[0, "headline_business_catalyst_count_3d"] == 1
    assert features.loc[0, "headline_risk_event_count_3d"] == 1


def test_build_news_feature_daily_counts_main_force_flow_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-main-force",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "主力资金抢筹生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_main_force_flow_count_3d"] == 1


def test_build_news_feature_daily_does_not_count_generic_funds_flow_as_main_force_flow() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-main-force-generic",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "资金流入生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_main_force_flow_count_3d"] == 0


def test_build_news_feature_daily_counts_margin_flow_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-margin-flow",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "融资客加仓生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_margin_flow_count_3d"] == 1


def test_build_news_feature_daily_counts_capital_flow_generic_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-capital-flow",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "资金关注生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_capital_flow_generic_count_3d"] == 1


def test_build_news_feature_daily_does_not_duplicate_specific_flow_subcategories() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-flow-main-force",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "主力资金抢筹生益科技",
                "content": "",
            },
            {
                "source_event_id": "evt-flow-margin",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:20:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "融资客加仓生益科技",
                "content": "",
            },
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_main_force_flow_count_3d"] == 1
    assert features.loc[0, "headline_margin_flow_count_3d"] == 1
    assert features.loc[0, "headline_capital_flow_generic_count_3d"] == 0


def test_build_news_feature_daily_counts_gold_stock_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-gold-stock",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "券商金股推荐生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_gold_stock_count_3d"] == 1


def test_build_news_feature_daily_does_not_count_bare_portfolio_language_as_gold_stock() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-gold-stock-generic",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "月度组合覆盖生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_gold_stock_count_3d"] == 0


def test_build_news_feature_daily_counts_rating_action_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-rating-action",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "评级上调生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_rating_action_count_3d"] == 1


def test_build_news_feature_daily_does_not_count_neutral_or_negative_broker_action_as_rating_action() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-rating-action-negative",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "维持评级生益科技",
                "content": "",
            },
            {
                "source_event_id": "evt-rating-action-negative-target",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:20:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "目标价下调生益科技",
                "content": "",
            },
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_rating_action_count_3d"] == 0


def test_build_news_feature_daily_counts_broker_positive_view_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-broker-view",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "券商看好生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_broker_positive_view_count_3d"] == 1


def test_build_news_feature_daily_does_not_count_negative_broker_view_as_positive() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-broker-positive-negative-target",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "券商研报：目标价下调生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_broker_positive_view_count_3d"] == 0


def test_build_news_feature_daily_does_not_count_generic_broker_positive_view_language() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-broker-positive-negative",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "看好后市 生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_broker_positive_view_count_3d"] == 0


def test_build_news_feature_daily_does_not_count_broker_research_without_positive_language() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-broker-research-negative",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "券商研报：下调评级生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_broker_positive_view_count_3d"] == 0


def test_build_news_feature_daily_counts_main_force_flow_additional_phrase_jia_cang() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-main-force-jia-cang",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "主力加仓生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_main_force_flow_count_3d"] == 1


def test_build_news_feature_daily_does_not_count_generic_funds_inflow_as_main_force_flow() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-main-force-funds-inflow",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "资金流入生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_main_force_flow_count_3d"] == 0


def test_build_news_feature_daily_does_not_count_bare_monthly_portfolio_language_as_gold_stock() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-gold-stock-monthly",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "月度组合覆盖生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_gold_stock_count_3d"] == 0


def test_build_news_feature_daily_does_not_count_bare_recommendation_portfolio_language_as_gold_stock() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-gold-stock-recommend",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "推荐组合纳入生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_gold_stock_count_3d"] == 0


def test_build_news_feature_daily_counts_order_bid_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-order-bid",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "订单中标生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_order_bid_count_3d"] == 1


def test_build_news_feature_daily_counts_order_bid_additional_phrase_signing() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-order-bid-sign",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "项目签约生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_order_bid_count_3d"] == 1


def test_build_news_feature_daily_counts_product_breakthrough_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-product-breakthrough",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "新品突破生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_product_breakthrough_count_3d"] == 1


def test_build_news_feature_daily_counts_industry_boom_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-industry-boom",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "行业景气提升生益科技受益",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_industry_boom_count_3d"] == 1


def test_build_news_feature_daily_counts_industry_boom_additional_phrase_expansion() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-industry-boom-expand",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "扩产提升生益科技产能",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_industry_boom_count_3d"] == 1


def test_build_news_feature_daily_counts_industry_boom_additional_phrase_supply_demand_improvement() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-industry-boom-supply-demand",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "供需改善带动生益科技景气回升",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_industry_boom_count_3d"] == 1


def test_build_news_feature_daily_counts_regulatory_inquiry_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-regulatory-inquiry",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "监管问询生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_regulatory_inquiry_count_3d"] == 1


def test_build_news_feature_daily_counts_regulatory_inquiry_additional_phrase_risk_warning() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-regulatory-risk-warning",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "风险警示生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_regulatory_inquiry_count_3d"] == 1


def test_build_news_feature_daily_counts_shareholder_reduction_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-shareholder-reduction",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "股东减持生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_shareholder_reduction_count_3d"] == 1


def test_build_news_feature_daily_counts_litigation_penalty_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-litigation-penalty",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "诉讼处罚生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_litigation_penalty_count_3d"] == 1


def test_build_news_feature_daily_counts_loss_warning_subcategory() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-loss-warning",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "亏损预警生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_loss_warning_count_3d"] == 1


def test_build_news_feature_daily_counts_loss_warning_additional_phrase_operating_downturn() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-loss-warning-downturn",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "业绩下滑生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_loss_warning_count_3d"] == 1


def test_build_news_feature_daily_allows_title_overlap_across_semantic_categories() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-overlap",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "主力资金抢筹 券商推荐 生益科技",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_capital_flow_count_3d"] == 1
    assert features.loc[0, "headline_broker_reco_count_3d"] == 1
    assert features.loc[0, "headline_business_catalyst_count_3d"] == 0
    assert features.loc[0, "headline_risk_event_count_3d"] == 0


def test_build_news_feature_daily_ignores_blank_source_names_in_source_diversity() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-source-1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "",
                "source_channel": "证券时报网",
                "title": "主力资金抢筹",
                "content": "",
            },
            {
                "source_event_id": "evt-source-2",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 10:10:00",
                "source_name": "   ",
                "source_channel": "澎湃新闻",
                "title": "券商推荐 生益科技",
                "content": "",
            },
            {
                "source_event_id": "evt-source-3",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 11:10:00",
                "source_name": None,
                "source_channel": "证券日报",
                "title": "订单突破",
                "content": "",
            },
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "source_diversity_3d"] == 0


def test_build_news_feature_daily_does_not_count_generic_positive_language_as_broker_reco() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-broker-negative",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "证券时报网",
                "source_channel": "证券时报网",
                "title": "业绩改善 看好后市",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_broker_reco_count_3d"] == 0


def test_build_news_feature_daily_does_not_count_negative_broker_headlines_as_broker_reco() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-broker-reco-negative-1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "证券时报网",
                "source_channel": "券商研究",
                "title": "券商研报：下调评级生益科技",
                "content": "",
            },
            {
                "source_event_id": "evt-broker-reco-negative-2",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:20:00",
                "source_name": "证券时报网",
                "source_channel": "券商研究",
                "title": "目标价下调生益科技",
                "content": "",
            },
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_broker_reco_count_3d"] == 0


def test_build_news_feature_daily_counts_specific_broker_reco_phrases() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-broker-1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "证券时报网",
                "source_channel": "券商研究",
                "title": "券商看好 生益科技",
                "content": "",
            },
            {
                "source_event_id": "evt-broker-2",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 10:10:00",
                "source_name": "证券时报网",
                "source_channel": "券商研究",
                "title": "评级上调 生益科技获关注",
                "content": "",
            },
            {
                "source_event_id": "evt-broker-3",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 11:10:00",
                "source_name": "证券时报网",
                "source_channel": "券商研究",
                "title": "金股推荐：生益科技入选",
                "content": "",
            },
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_broker_reco_count_3d"] == 3


def test_build_news_feature_daily_does_not_count_generic_risk_language_as_risk_event() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-risk-negative",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "证券时报网",
                "source_channel": "证券时报网",
                "title": "经营存在风险",
                "content": "",
            }
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_risk_event_count_3d"] == 0


def test_build_news_feature_daily_counts_specific_risk_event_phrases() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-risk-1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "证券时报网",
                "source_channel": "监管公告",
                "title": "监管问询 生益科技收到关注函",
                "content": "",
            },
            {
                "source_event_id": "evt-risk-2",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 10:10:00",
                "source_name": "证券时报网",
                "source_channel": "监管公告",
                "title": "问询函下发 生益科技需回复",
                "content": "",
            },
            {
                "source_event_id": "evt-risk-3",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 11:10:00",
                "source_name": "证券时报网",
                "source_channel": "监管公告",
                "title": "风险提示 生益科技收到监管问询",
                "content": "",
            },
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_risk_event_count_3d"] == 3


def test_run_news_feature_backfill_writes_mentions_and_features_for_mocked_trading_dates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    events_path = tmp_path / "events.csv"
    pd.DataFrame(
        [
            {
                "source_event_id": "n1",
                "title": "订单增长",
                "content": "600183.SH 生益科技",
                "published_at": "2026-06-01 08:30:00",
                "source_name": "cls",
                "source_channel": "major",
            }
        ]
    ).to_csv(events_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_features._load_assets_for_news_mapping",
        lambda: pd.DataFrame(
            [{"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}]
        ),
    )
    monkeypatch.setattr(
        "stock_research.news_features._load_trade_dates_for_news_features",
        lambda start_date, end_date: ["2026-06-02", "2026-06-04"],
    )

    result = run_news_feature_backfill(
        events_path=events_path,
        start_date="2026-06-01",
        end_date="2026-06-05",
        mode="replay",
        output_dir=tmp_path / "out",
    )

    assert Path(result["paths"]["mentions"]).exists()
    assert Path(result["paths"]["features"]).exists()
    assert result["features"]["trade_date"].tolist() == ["2026-06-02", "2026-06-04"]
    assert result["mentions"]["asset_id"].tolist() == ["CN:SH:600183"]


def test_load_assets_for_news_mapping_uses_research_service(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    class DummyConn:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_connect(service):
        recorded["service"] = service
        return DummyConn()

    monkeypatch.setattr("stock_research.news_features.connect", fake_connect)
    monkeypatch.setattr(
        "stock_research.news_features.fetch_all",
        lambda conn, sql, params=None: [
            {"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}
        ],
    )

    assets = _load_assets_for_news_mapping()

    assert recorded["service"]
    assert list(assets.columns) == ["asset_id", "ts_code", "stock_name"]
    assert assets.loc[0, "asset_id"] == "CN:SH:600183"


def test_news_feature_backfill_cli_prints_artifact_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "stock_research.cli.run_news_feature_backfill",
        lambda **kwargs: {
            "mentions": pd.DataFrame(),
            "features": pd.DataFrame(),
            "paths": {
                "mentions": str(tmp_path / "mentions.csv"),
                "features": str(tmp_path / "features.csv"),
            },
        },
    )

    cli.main_for_args(
        [
            "news-feature-backfill",
            "--events-path",
            "inputs/events.csv",
            "--start-date",
            "2026-06-01",
            "--end-date",
            "2026-06-02",
        ]
    )

    output = capsys.readouterr().out
    assert "news_feature_backfill|mentions|" in output
    assert "news_feature_backfill|features|" in output


def test_news_feature_diagnostics_returns_bucket_summary_with_small_samples(tmp_path) -> None:
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "A",
                "news_attention_level": "high",
                "news_count_3d": 4,
                "future_5d_return": 0.03,
            },
            {
                "trade_date": "2026-06-03",
                "asset_id": "B",
                "news_attention_level": "low",
                "news_count_3d": 0,
                "future_5d_return": -0.01,
            },
        ]
    )

    result = run_news_feature_diagnostics(feature_frame=features, output_dir=tmp_path)

    assert "bucket" in result["bucket_summary"].columns
    assert result["warnings"]
    assert Path(result["paths"]["bucket_summary"]).exists()
    assert Path(result["paths"]["regime_summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_news_feature_diagnostics_warns_when_market_regime_is_missing_and_report_previews_unknown_regime(
    tmp_path,
) -> None:
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "A",
                "news_attention_level": "high",
                "news_count_3d": 4,
                "future_5d_return": 0.03,
            },
            {
                "trade_date": "2026-06-03",
                "asset_id": "B",
                "news_attention_level": "low",
                "news_count_3d": 0,
                "future_5d_return": -0.01,
            },
        ]
    )

    result = run_news_feature_diagnostics(feature_frame=features, output_dir=tmp_path)

    assert any("market_regime" in warning for warning in result["warnings"])
    report_text = Path(result["paths"]["report"]).read_text(encoding="utf-8")
    assert "unknown" in report_text
    assert "Bucket Summary Preview" in report_text
    assert "Regime Summary Preview" in report_text


def test_news_feature_diagnostics_warns_when_future_returns_have_no_usable_numeric_values(
    tmp_path,
) -> None:
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "A",
                "news_attention_level": "high",
                "news_count_3d": 4,
                "future_5d_return": "n/a",
                "market_regime": "mainline",
            },
            {
                "trade_date": "2026-06-03",
                "asset_id": "B",
                "news_attention_level": "low",
                "news_count_3d": 0,
                "future_5d_return": "",
                "market_regime": "rotation",
            },
        ]
    )

    result = run_news_feature_diagnostics(feature_frame=features, output_dir=tmp_path)

    assert any("future_5d_return has no usable numeric values" in warning for warning in result["warnings"])


def test_news_feature_diagnostics_report_keeps_bucket_and_regime_previews_under_matching_sections(
    tmp_path,
) -> None:
    features = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-02",
                "asset_id": "A",
                "news_attention_level": "high",
                "news_count_3d": 4,
                "future_5d_return": 0.03,
                "market_regime": "mainline",
            },
            {
                "trade_date": "2026-06-03",
                "asset_id": "B",
                "news_attention_level": "low",
                "news_count_3d": 0,
                "future_5d_return": -0.01,
                "market_regime": "rotation",
            },
        ]
    )

    result = run_news_feature_diagnostics(feature_frame=features, output_dir=tmp_path)
    report_text = Path(result["paths"]["report"]).read_text(encoding="utf-8")

    bucket_section = report_text.index("## Bucket Summary")
    bucket_preview = report_text.index("### Bucket Summary Preview")
    regime_section = report_text.index("## Regime Summary")
    regime_preview = report_text.index("### Regime Summary Preview")

    assert bucket_section < bucket_preview < regime_section
    assert regime_section < regime_preview


def test_news_feature_diagnostics_cli_prints_artifact_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "stock_research.cli.run_news_feature_diagnostics",
        lambda **kwargs: {
            "bucket_summary": pd.DataFrame(),
            "regime_summary": pd.DataFrame(),
            "warnings": ["small sample"],
            "paths": {
                "bucket_summary": str(tmp_path / "bucket.csv"),
                "regime_summary": str(tmp_path / "regime.csv"),
                "report": str(tmp_path / "report.md"),
            },
        },
    )

    cli.main_for_args(
        [
            "news-feature-diagnostics",
            "--feature-path",
            "outputs/research/news_feature_daily.csv",
        ]
    )

    output = capsys.readouterr().out
    assert "news_feature_diagnostics|bucket_summary|" in output
    assert "news_feature_diagnostics|regime_summary|" in output
    assert "news_feature_diagnostics|report|" in output
    assert "news_feature_diagnostics|warnings|1" in output
    assert "news_feature_diagnostics|warning|small sample" in output
