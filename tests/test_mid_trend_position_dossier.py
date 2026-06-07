from __future__ import annotations

from pathlib import Path

import pandas as pd

import stock_research.cli as cli
from stock_research.news_features import build_news_feature_daily, map_news_mentions
from stock_research.news_source_backfill import normalize_news_source_rows
from stock_research.topn_news_enrichment import build_topn_news_enrichment
from stock_research.mid_trend_position_dossier import (
    _build_holding_narrative,
    _normalize_dossier_news_enrichment,
    _normalize_dossier_portfolio_review,
    _normalize_dossier_research,
    _partition_dossier_rows,
    _render_candidate_section_entry,
    _render_trend_status,
    build_mid_trend_position_dossier_from_frames,
)


portfolio_review = pd.DataFrame(
    [
        {
            "trade_date": "2026-06-04",
            "asset_id": "CN:SH:600183",
            "ts_code": "600183.SH",
            "stock_name": "生益科技",
            "section": "top5",
            "shadow_top10_rank": 1,
            "weight": 0.2,
            "final_label": "高优先级持有",
            "why_hold_or_change": "高支持度且为核心持仓，继续持有。",
            "main_positive_evidence": "行业景气回升，研报覆盖较多。",
            "main_risk_evidence": "估值偏高，行业竞争加剧。",
            "latest_pdf_risk_summary": "下游需求不及预期风险；行业竞争加剧风险。",
        },
        {
            "trade_date": "2026-06-04",
            "asset_id": "CN:SZ:300201",
            "ts_code": "300201.SZ",
            "stock_name": "海伦哲",
            "section": "top5",
            "shadow_top10_rank": 2,
            "weight": 0.2,
            "final_label": "低优先级持有",
            "why_hold_or_change": "支持度偏弱，继续观察。",
            "main_positive_evidence": "",
            "main_risk_evidence": "",
            "latest_pdf_risk_summary": "",
        },
        {
            "trade_date": "2026-06-04",
            "asset_id": "CN:SH:688301",
            "ts_code": "688301.SH",
            "stock_name": "奕瑞科技",
            "section": "top6_10",
            "shadow_top10_rank": 6,
            "weight": 0.0,
            "final_label": "仅讨论",
            "why_hold_or_change": "候选调入观察。",
            "main_positive_evidence": "基本面稳健。",
            "main_risk_evidence": "短期波动较大。",
            "latest_pdf_risk_summary": "需求波动风险。",
        },
    ]
)

research_packet = pd.DataFrame(
    [
        {
            "trade_date": "2026-06-04",
            "asset_id": "CN:SH:600183",
            "ts_code": "600183.SH",
            "stock_name": "生益科技",
            "research_support_score_pit": 33,
            "broker_report_count_90d": 3,
            "target_price_median_pit": 103.5,
            "target_upside_median_pit": pd.NA,
            "broker_coverage_count_pit": 3,
            "pdf_target_price_count_90d": 3,
            "pdf_target_price_high_confidence_count_90d": 1,
            "pdf_profit_forecast_count_90d": 3,
            "pdf_risk_section_count_90d": 3,
            "latest_pdf_risk_summary": "下游需求不及预期风险；行业竞争加剧风险。",
            "fundamental_hard_risk": "no_clear_hard_risk",
            "main_positive_evidence": "行业景气回升，研报覆盖较多。",
            "main_risk_evidence": "估值偏高，行业竞争加剧。",
            "why_hold_or_change": "高支持度且为核心持仓，继续持有。",
        },
        {
            "trade_date": "2026-06-05",
            "asset_id": "CN:SH:688301",
            "ts_code": "688301.SH",
            "stock_name": "奕瑞科技",
            "research_support_score_pit": 24,
            "broker_report_count_90d": 2,
            "target_price_median_pit": 210.0,
            "target_upside_median_pit": 0.15,
            "broker_coverage_count_pit": 2,
            "pdf_target_price_count_90d": 2,
            "pdf_target_price_high_confidence_count_90d": 1,
            "pdf_profit_forecast_count_90d": 2,
            "pdf_risk_section_count_90d": 1,
            "latest_pdf_risk_summary": "需求波动风险。",
            "fundamental_hard_risk": "no_clear_hard_risk",
            "main_positive_evidence": "基本面稳健。",
            "main_risk_evidence": "短期波动较大。",
            "why_hold_or_change": "候选调入观察。",
        },
    ]
)

news_enrichment = pd.DataFrame(
    [
        {
            "trade_date": "2026-06-04",
            "asset_id": "CN:SH:600183",
            "ts_code": "600183.SH",
            "stock_name": "生益科技",
            "news_compact_summary": "近3日主力资金关注 + 券商金股推荐共振",
            "news_consensus_summary": "近3日正向新闻2条，关注度high",
            "news_risk_summary": "近3日风险关键词新闻1条",
            "theme_catalyst_summary": "近3日重大/主线催化新闻1条",
            "overnight_catalyst_note": "隔夜催化新闻1条",
            "news_attention_level": "high",
            "news_risk_attention_flag": True,
            "news_enrichment_quality_flag": "rich",
        },
        {
            "trade_date": "2026-06-04",
            "asset_id": "CN:SH:688301",
            "ts_code": "688301.SH",
            "stock_name": "奕瑞科技",
            "news_consensus_summary": "近3日正向新闻1条，关注度unknown",
            "news_risk_summary": "",
            "theme_catalyst_summary": "近3日正向/催化新闻1条",
            "overnight_catalyst_note": "",
            "news_attention_level": "unknown",
            "news_risk_attention_flag": float("nan"),
            "news_enrichment_quality_flag": "medium",
        },
    ]
)


def test_position_dossier_builds_required_sections() -> None:
    review = portfolio_review.copy()
    review["is_current_holding"] = [True, True, False]

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=review,
        research_packet_candidates=research_packet,
    )
    markdown = result["markdown"]
    assert "## 组合级执行摘要" in markdown
    assert "## 当前持仓 Top5" in markdown
    assert "## 候选调入名单" in markdown
    assert "## 候选调出名单" in markdown
    assert "## 附录：结构化证据摘要表" in markdown
    assert "### 1. 生益科技（600183.SH）" in markdown
    assert "当前结论" in markdown
    assert "一句话判断" in markdown
    assert "支持持有的 3 条核心证据" in markdown
    assert "反对持有的 2 条核心证据" in markdown
    assert "今天最关键观察点" in markdown
    assert "它在涨什么" in markdown
    assert "行业/主线位置" in markdown
    assert "行业地位与产品地位" in markdown
    assert "机构支持逻辑与分歧点" in markdown
    assert "技术与趋势状态" in markdown
    assert "主要风险与反例" in markdown
    assert "证伪条件 / 继续跟踪点" in markdown
    assert "信息不足，需补充" in markdown
    assert "新闻/催化跟踪" not in markdown


def test_position_dossier_renders_news_sections_when_enrichment_present() -> None:
    review = portfolio_review.copy()
    review["is_current_holding"] = [True, True, False]
    research = research_packet.copy()
    research.loc[research["asset_id"].eq("CN:SH:688301"), "trade_date"] = "2026-06-04"

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="live",
        portfolio_review=review,
        research_packet_candidates=research,
        news_enrichment=news_enrichment,
    )

    markdown = result["markdown"]
    assert "### 1. 生益科技（600183.SH）" in markdown
    assert "- 新闻/催化跟踪" in markdown
    assert "  - 新闻短摘要：近3日主力资金关注 + 券商金股推荐共振" in markdown
    assert "  - 新闻关注度：high" in markdown
    assert "  - 新闻共识：近3日正向新闻2条，关注度high" in markdown
    assert "  - 新闻风险：近3日风险关键词新闻1条" in markdown
    assert "  - 主题催化：近3日重大/主线催化新闻1条" in markdown
    assert "  - 隔夜催化：隔夜催化新闻1条" in markdown
    assert "  - 风险新闻关注：true" in markdown
    assert "### 1. 奕瑞科技（688301.SH）" in markdown
    assert "  - 新闻关注度：unknown" in markdown
    assert "  - 主题催化：近3日正向/催化新闻1条" in markdown
    assert markdown.index("- 新闻/催化跟踪") < markdown.index("  - 新闻短摘要：近3日主力资金关注 + 券商金股推荐共振") < markdown.index("  - 新闻关注度：high")


def test_news_pipeline_end_to_end_smoke_builds_dossier_with_news_enrichment() -> None:
    normalized_events = normalize_news_source_rows(
        [
            {
                "source_event_id": "news-1",
                "source_name": "tushare_news",
                "source_channel": "major",
                "title": "  生益科技订单增长获机构看好  ",
                "content": "600183.SH 生益科技订单增长，产业链景气回升。",
                "published_at": "2026-06-04 08:20:00",
            },
            {
                "source_event_id": "news-2",
                "source_name": "tushare_news",
                "source_channel": "flash",
                "title": "生益科技风险提示",
                "content": "600183.SH 生益科技公告提示短期波动风险。",
                "published_at": "2026-06-04 09:10:00",
            },
        ],
        source_status="available",
    )

    assets = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
            }
        ]
    )
    mentions = map_news_mentions(normalized_events, assets)
    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-04"],
        mode="replay",
    )
    enrichment = build_topn_news_enrichment(
        candidates=pd.DataFrame(
            [
                {
                    "trade_date": "2026-06-04",
                    "asset_id": "CN:SH:600183",
                    "ts_code": "600183.SH",
                    "stock_name": "生益科技",
                }
            ]
        ),
        news_features=features,
    )

    review = portfolio_review.iloc[[0]].copy()
    review["is_current_holding"] = [True]
    research = research_packet.iloc[[0]].copy()

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=review,
        research_packet_candidates=research,
        news_enrichment=enrichment,
    )

    assert normalized_events["source_status"].eq("available").all()
    assert len(mentions) == 2
    assert features.loc[0, "news_count_3d"] == 2
    assert features.loc[0, "major_news_count_3d"] == 1
    assert features.loc[0, "headline_keyword_positive_count_3d"] == 1
    assert features.loc[0, "headline_keyword_risk_count_3d"] == 1
    assert enrichment.loc[0, "news_attention_level"] == "medium"
    assert enrichment.loc[0, "theme_catalyst_summary"] == "近3日订单/中标催化新闻1条"
    assert enrichment.loc[0, "news_risk_attention_flag"] is True
    assert result["summary"]["news_enrichment_provided"] == "yes"
    assert result["summary"]["news_enrichment_used"] == "yes"
    assert result["summary"]["matched_news_rows"] == 1
    assert "- 新闻/催化跟踪" in result["markdown"]
    assert "  - 新闻关注度：medium" in result["markdown"]
    assert "  - 主题催化：近3日订单/中标催化新闻1条" in result["markdown"]
    assert "  - 风险新闻关注：true" in result["markdown"]


def test_position_dossier_preserves_unknown_news_risk_flag_after_csv_like_reload() -> None:
    review = portfolio_review.copy()
    review["is_current_holding"] = [True, True, False]
    research = research_packet.copy()
    research.loc[research["asset_id"].eq("CN:SH:688301"), "trade_date"] = "2026-06-04"
    csv_like_news = news_enrichment.copy()
    csv_like_news["news_risk_attention_flag"] = pd.Series([True, float("nan")], dtype=object)

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="live",
        portfolio_review=review,
        research_packet_candidates=research,
        news_enrichment=csv_like_news,
    )

    markdown = result["markdown"]
    assert "### 1. 奕瑞科技（688301.SH）" in markdown
    assert "  - 风险新闻关注：unknown" in markdown
    assert "  - 风险新闻关注：false" not in markdown


def test_position_dossier_exposes_news_enrichment_match_status_when_no_rows_match() -> None:
    review = portfolio_review.copy()
    review["is_current_holding"] = [True, True, False]
    unmatched_news = news_enrichment.copy()
    unmatched_news["trade_date"] = "2026-06-03"

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="live",
        portfolio_review=review,
        research_packet_candidates=research_packet,
        news_enrichment=unmatched_news,
    )

    assert result["summary"]["news_enrichment_provided"] == "yes"
    assert result["summary"]["news_enrichment_used"] == "no"
    assert result["summary"]["matched_news_rows"] == 0
    assert "- news_enrichment_provided: yes" in result["markdown"]
    assert "- news_enrichment_used: no" in result["markdown"]
    assert "- matched_news_rows: 0" in result["markdown"]


def test_normalize_dossier_news_enrichment_uses_file_order_last_row_wins() -> None:
    frame = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "news_consensus_summary": "old row",
                "news_attention_level": "low",
                "news_risk_attention_flag": False,
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "news_consensus_summary": "new row",
                "news_attention_level": "high",
                "news_risk_attention_flag": True,
            },
        ]
    )

    normalized = _normalize_dossier_news_enrichment(frame, trade_date="2026-06-04")

    assert len(normalized) == 1
    row = normalized.iloc[0]
    assert row["news_consensus_summary"] == "new row"
    assert row["news_attention_level"] == "high"
    assert bool(row["news_risk_attention_flag"]) is True


def test_position_dossier_holding_sections_render_two_layer_narrative() -> None:
    review = portfolio_review.copy()
    review["is_current_holding"] = [True, True, False]

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=review,
        research_packet_candidates=research_packet,
    )
    markdown = result["markdown"]

    assert "### 1. 生益科技（600183.SH）" in markdown
    assert "- 当前结论：高优先级持有" in markdown
    assert "- 一句话判断：高支持度且为核心持仓，继续持有。但反证仍需盯住估值偏高，行业竞争加剧。" in markdown
    assert "支持持有的 3 条核心证据" in markdown
    assert "1. 行业景气回升，研报覆盖较多。" in markdown
    assert "2. 近90天研报3篇；覆盖机构3家" in markdown
    assert "3. 目标价中位数103.5" in markdown
    assert "反对持有的 2 条核心证据" in markdown
    assert "1. 估值偏高，行业竞争加剧。" in markdown
    assert "2. 下游需求不及预期风险；行业竞争加剧风险。" in markdown
    assert "- 今天最关键观察点：下游需求不及预期风险；行业竞争加剧风险。" in markdown
    assert "- 它在涨什么：行业景气回升，研报覆盖较多。" in markdown
    assert "- 行业/主线位置：信息不足，需补充" in markdown
    assert "- 行业地位与产品地位：信息不足，需补充" in markdown
    assert "- 机构支持逻辑与分歧点：近90天研报3篇；覆盖机构3家；90天覆盖3篇" in markdown
    assert "- 技术与趋势状态：Top5持仓，影子排名 1，当前权重 0.2。" in markdown
    assert "- 主要风险与反例：估值偏高，行业竞争加剧。下游需求不及预期风险；行业竞争加剧风险。" in markdown
    assert "- 证伪条件 / 继续跟踪点：估值偏高，行业竞争加剧。" in markdown


def test_build_holding_narrative_extracts_structured_fields() -> None:
    review = portfolio_review.copy()
    review["is_current_holding"] = [True, True, False]
    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=review,
        research_packet_candidates=research_packet,
    )
    row = result["holdings"].loc[result["holdings"]["asset_id"].eq("CN:SH:600183")].iloc[0]

    narrative = _build_holding_narrative(row)

    assert narrative["current_conclusion"] == "高优先级持有"
    assert narrative["one_line_judgment"] == "高支持度且为核心持仓，继续持有。但反证仍需盯住估值偏高，行业竞争加剧。"
    assert narrative["support_evidence"] == [
        "行业景气回升，研报覆盖较多。",
        "近90天研报3篇；覆盖机构3家",
        "目标价中位数103.5",
    ]
    assert narrative["oppose_evidence"] == [
        "估值偏高，行业竞争加剧。",
        "下游需求不及预期风险；行业竞争加剧风险。",
    ]
    assert narrative["key_watch_point"] == "下游需求不及预期风险；行业竞争加剧风险。"
    assert narrative["what_is_working"] == "行业景气回升，研报覆盖较多。"
    assert narrative["industry_theme_position"] == "信息不足，需补充"
    assert narrative["industry_product_position"] == "信息不足，需补充"
    assert narrative["institutional_logic"] == "近90天研报3篇；覆盖机构3家；90天覆盖3篇"
    assert narrative["trend_status"] == "Top5持仓，影子排名 1，当前权重 0.2。"
    assert narrative["key_risks"] == "估值偏高，行业竞争加剧。下游需求不及预期风险；行业竞争加剧风险。"
    assert narrative["falsification_or_follow_up"] == "估值偏高，行业竞争加剧。"


def test_build_holding_narrative_uses_placeholders_when_merged_narrative_fields_are_missing() -> None:
    row = pd.Series(
        {
            "final_label": "高优先级持有",
            "why_hold_or_change": "原始复盘结论，不应回退使用。",
            "main_positive_evidence": "原始正面证据，不应回退使用。",
            "main_risk_evidence": "原始风险证据，不应回退使用。",
            "latest_pdf_risk_summary": "原始风险摘要，不应回退使用。",
            "one_line_judgment": "",
            "support_fact_1": "",
            "support_fact_2": "",
            "support_fact_3": "",
            "oppose_fact_1": "",
            "oppose_fact_2": "",
            "watch_point": "",
            "falsification_condition": "",
            "what_is_working_summary": "",
            "industry_position_summary": "",
            "institution_view_summary": "",
            "risk_summary": "",
            "section": "top5",
            "shadow_top10_rank": 1,
            "weight": 0.2,
        }
    )

    narrative = _build_holding_narrative(row)

    assert narrative["current_conclusion"] == "高优先级持有"
    assert narrative["one_line_judgment"] == "信息不足，需补充"
    assert narrative["support_evidence"] == ["信息不足，需补充"] * 3
    assert narrative["oppose_evidence"] == ["信息不足，需补充"] * 2
    assert narrative["key_watch_point"] == "信息不足，需补充"
    assert narrative["what_is_working"] == "信息不足，需补充"
    assert narrative["industry_theme_position"] == "信息不足，需补充"
    assert narrative["industry_product_position"] == "信息不足，需补充"
    assert narrative["institutional_logic"] == "信息不足，需补充"
    assert narrative["key_risks"] == "信息不足，需补充"
    assert narrative["falsification_or_follow_up"] == "信息不足，需补充"
    assert narrative["trend_status"] == "Top5持仓，影子排名 1，当前权重 0.2。"


def test_render_trend_status_degrades_cleanly_when_section_missing() -> None:
    row = pd.Series({"section": "", "shadow_top10_rank": 7, "weight": 0.3})

    assert _render_trend_status(row) == "信息不足，需补充"


def test_position_dossier_candidate_sections_render_explicit_reasoning_lines() -> None:
    review = portfolio_review.copy()
    review["is_current_holding"] = [True, True, False]
    research = research_packet.copy()
    research.loc[research["asset_id"].eq("CN:SH:688301"), "trade_date"] = "2026-06-04"

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="live",
        portfolio_review=review,
        research_packet_candidates=research,
    )
    markdown = result["markdown"]

    assert "## 候选调入名单" in markdown
    assert "### 1. 奕瑞科技（688301.SH）" in markdown
    assert "- 调入结论：仅讨论" in markdown
    assert "- 核心理由：候选调入观察。但反证仍需盯住短期波动较大。" in markdown
    assert "- 支持证据：基本面稳健。" in markdown
    assert "- 风险提示：短期波动较大。" in markdown
    assert "- 研究信号：支持分 24；90天券商报告数 2；目标价中位数 210.0。" in markdown
    assert "- 跟踪重点：后续兑现依赖目标涨幅假设继续成立（15%）。" in markdown
    assert "## 候选调出名单" in markdown
    assert "### 1. 海伦哲（300201.SZ）" in markdown
    assert "- 调出结论：低优先级持有" in markdown
    assert "- 核心理由：支持度偏弱，继续观察。" in markdown
    assert "- 支持继续观察/调出证据：支持度偏弱，继续观察。" in markdown
    assert "- 风险或反例：信息不足，需补充" in markdown


def test_position_dossier_candidate_section_uses_placeholders_when_narrative_fields_are_missing() -> None:
    row = pd.Series(
        {
            "asset_id": "CN:SH:688301",
            "ts_code": "688301.SH",
            "stock_name": "奕瑞科技",
            "final_label": "仅讨论",
            "why_hold_or_change": "原始调入理由，不应回退使用。",
            "main_positive_evidence": "原始支持证据，不应回退使用。",
            "main_risk_evidence": "原始风险提示，不应回退使用。",
            "latest_pdf_risk_summary": "原始跟踪点，不应回退使用。",
            "one_line_judgment": "",
            "support_fact_1": "",
            "support_fact_2": "",
            "support_fact_3": "",
            "oppose_fact_1": "",
            "oppose_fact_2": "",
            "watch_point": "",
            "falsification_condition": "",
            "what_is_working_summary": "",
            "industry_position_summary": "",
            "institution_view_summary": "",
            "risk_summary": "",
            "research_support_score_pit": 24,
            "broker_report_count_90d": 2,
            "target_price_median_pit": 210.0,
        }
    )

    rendered = "\n".join(
        _render_candidate_section_entry(
            index=1,
            row=row,
            conclusion_label="调入结论",
            evidence_label="支持证据",
            risk_label="风险提示",
        )
    )

    assert "- 核心理由：信息不足，需补充" in rendered
    assert "- 支持证据：信息不足，需补充" in rendered
    assert "- 风险提示：信息不足，需补充" in rendered
    assert "- 跟踪重点：信息不足，需补充" in rendered
    assert "原始调入理由，不应回退使用。" not in rendered
    assert "原始支持证据，不应回退使用。" not in rendered
    assert "原始风险提示，不应回退使用。" not in rendered


def test_position_dossier_appendix_and_placeholders_remain_deterministic() -> None:
    review = portfolio_review.copy()
    review["is_current_holding"] = [True, True, False]
    review.loc[0, "main_positive_evidence"] = ""
    review.loc[0, "main_risk_evidence"] = ""
    review.loc[0, "latest_pdf_risk_summary"] = ""
    research = research_packet.copy()
    research.loc[0, "main_positive_evidence"] = ""
    research.loc[0, "main_risk_evidence"] = ""
    research.loc[0, "latest_pdf_risk_summary"] = ""

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=review,
        research_packet_candidates=research,
    )
    markdown = result["markdown"]

    assert markdown.count("信息不足，需补充") >= 6
    assert "| asset_id | stock_name | is_current_holding | final_label | why_hold_or_change | research_support_score_pit | target_price_median_pit | pdf_profit_forecast_count_90d | latest_pdf_risk_summary | dossier_bucket |" in markdown
    assert "| CN:SH:600183 | 生益科技 | True | 高优先级持有 | 高支持度且为核心持仓，继续持有。 | 33 | 103.5 | 3 |  | holding |" in markdown


def test_position_dossier_live_mode_accepts_enhanced_fields() -> None:
    live_research_packet = research_packet.copy()
    normalized = _normalize_dossier_research(live_research_packet, trade_date="2026-06-04", mode="live")
    current_row = normalized.loc[normalized["asset_id"].eq("CN:SH:600183")].iloc[0]

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="live",
        portfolio_review=portfolio_review,
        research_packet_candidates=live_research_packet,
    )

    assert result["summary"]["mode"] == "live"
    assert result["summary"]["enhanced_sources_used"] == "yes"
    assert current_row["target_price_median_pit"] == 103.5
    assert current_row["pdf_profit_forecast_count_90d"] == 3
    assert current_row["latest_pdf_risk_summary"] == "下游需求不及预期风险；行业竞争加剧风险。"
    assert "103.5" in result["markdown"]
    assert "下游需求不及预期风险；行业竞争加剧风险。" in result["markdown"]


def test_position_dossier_replay_mode_filters_future_research_rows() -> None:
    filtered = _normalize_dossier_research(research_packet, trade_date="2026-06-04", mode="replay")
    assert not filtered.empty
    assert filtered["asset_id"].tolist() == ["CN:SH:600183"]
    assert filtered["trade_date"].min() == pd.Timestamp("2026-06-04")
    assert filtered["trade_date"].max() <= pd.Timestamp("2026-06-04")


def test_position_dossier_holdings_only_use_explicit_is_current_holding_flag() -> None:
    review = portfolio_review.copy()
    review = review.drop(columns=["weight"])

    normalized = _normalize_dossier_portfolio_review(review, trade_date="2026-06-04")
    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=review,
        research_packet_candidates=research_packet,
    )

    assert normalized["is_current_holding"].tolist() == [False, False, False]
    assert result["holdings"].empty


def test_partition_dossier_rows_respects_holding_add_and_reduce_buckets() -> None:
    review = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "final_label": "高优先级持有",
                "why_hold_or_change": "继续持有。",
                "is_current_holding": True,
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "奕瑞科技",
                "shadow_top10_rank": 2,
                "final_label": "候选调入",
                "why_hold_or_change": "候选调入观察。",
                "is_current_holding": False,
            },
        ]
    )
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "research_support_score_pit": 10,
                "broker_report_count_90d": 1,
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "research_support_score_pit": 24,
                "broker_report_count_90d": 2,
            },
        ]
    )

    holdings, candidate_adds, candidate_reduces = _partition_dossier_rows(
        normalized_review=_normalize_dossier_portfolio_review(review, trade_date="2026-06-04"),
        normalized_research=_normalize_dossier_research(research, trade_date="2026-06-04", mode="replay"),
    )

    assert holdings["asset_id"].tolist() == ["CN:SH:600183"]
    assert candidate_adds["asset_id"].tolist() == ["CN:SH:688301"]
    assert "CN:SH:600183" in candidate_reduces["asset_id"].tolist()


def test_position_dossier_shortlists_candidate_adds_and_reduces_for_summary_flags() -> None:
    review = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "H1",
                "ts_code": "H1.SH",
                "stock_name": "Holding 1",
                "section": "top5",
                "shadow_top10_rank": 1,
                "final_label": "高优先级持有",
                "why_hold_or_change": "继续持有。",
                "is_current_holding": True,
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "H2",
                "ts_code": "H2.SH",
                "stock_name": "Holding 2",
                "section": "top5",
                "shadow_top10_rank": 2,
                "final_label": "低优先级持有",
                "why_hold_or_change": "继续观察。",
                "is_current_holding": True,
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "H3",
                "ts_code": "H3.SH",
                "stock_name": "Holding 3",
                "section": "top5",
                "shadow_top10_rank": 3,
                "final_label": "低优先级持有",
                "why_hold_or_change": "继续观察。",
                "is_current_holding": True,
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "H4",
                "ts_code": "H4.SH",
                "stock_name": "Holding 4",
                "section": "top5",
                "shadow_top10_rank": 4,
                "final_label": "低优先级持有",
                "why_hold_or_change": "继续观察。",
                "is_current_holding": True,
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "A1",
                "ts_code": "A1.SH",
                "stock_name": "Add 1",
                "section": "top6_10",
                "shadow_top10_rank": 6,
                "final_label": "候选调入",
                "why_hold_or_change": "候选调入观察。",
                "is_current_holding": False,
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "A2",
                "ts_code": "A2.SH",
                "stock_name": "Add 2",
                "section": "top6_10",
                "shadow_top10_rank": 7,
                "final_label": "候选调入",
                "why_hold_or_change": "候选调入观察。",
                "is_current_holding": False,
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "A3",
                "ts_code": "A3.SH",
                "stock_name": "Add 3",
                "section": "top6_10",
                "shadow_top10_rank": 8,
                "final_label": "仅讨论",
                "why_hold_or_change": "候选调入观察。",
                "is_current_holding": False,
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "A4",
                "ts_code": "A4.SH",
                "stock_name": "Add 4",
                "section": "top6_10",
                "shadow_top10_rank": 9,
                "final_label": "观察",
                "why_hold_or_change": "继续观察。",
                "is_current_holding": False,
            },
        ]
    )
    research = pd.DataFrame(
        [
            {"trade_date": "2026-06-04", "asset_id": "H1", "research_support_score_pit": 5, "broker_report_count_90d": 1},
            {"trade_date": "2026-06-04", "asset_id": "H2", "research_support_score_pit": 1, "broker_report_count_90d": 0},
            {"trade_date": "2026-06-04", "asset_id": "H3", "research_support_score_pit": 2, "broker_report_count_90d": 0},
            {"trade_date": "2026-06-04", "asset_id": "H4", "research_support_score_pit": 3, "broker_report_count_90d": 0},
            {"trade_date": "2026-06-04", "asset_id": "A1", "research_support_score_pit": 30, "broker_report_count_90d": 3},
            {"trade_date": "2026-06-04", "asset_id": "A2", "research_support_score_pit": 20, "broker_report_count_90d": 2},
            {"trade_date": "2026-06-04", "asset_id": "A3", "research_support_score_pit": 10, "broker_report_count_90d": 1},
            {"trade_date": "2026-06-04", "asset_id": "A4", "research_support_score_pit": 0, "broker_report_count_90d": 0},
        ]
    )

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=review,
        research_packet_candidates=research,
    )

    assert result["candidate_adds"]["asset_id"].tolist() == ["A1", "A2", "A3"]
    assert result["candidate_reduces"]["asset_id"].tolist() == ["H2", "H3", "H4"]

    summary_rows = result["summary_rows"].set_index("asset_id")
    assert bool(summary_rows.loc["A1", "is_candidate_add"]) is True
    assert bool(summary_rows.loc["A2", "is_candidate_add"]) is True
    assert bool(summary_rows.loc["A3", "is_candidate_add"]) is True
    assert bool(summary_rows.loc["A4", "is_candidate_add"]) is False
    assert bool(summary_rows.loc["H2", "is_candidate_reduce"]) is True
    assert bool(summary_rows.loc["H3", "is_candidate_reduce"]) is True
    assert bool(summary_rows.loc["H4", "is_candidate_reduce"]) is True
    assert bool(summary_rows.loc["H1", "is_candidate_reduce"]) is False


def test_position_dossier_accepts_portfolio_review_runtime_column_names() -> None:
    review = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "candidate_rank": 1,
                "target_weight": 0.2,
                "is_current_holding": True,
                "final_label": "高优先级持有",
                "why_hold_or_change": "高支持度且为核心持仓，继续持有。",
            },
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "奕瑞科技",
                "candidate_rank": 6,
                "target_weight": 0.0,
                "is_current_holding": False,
                "final_label": "仅讨论",
                "why_hold_or_change": "候选调入观察。",
            },
        ]
    )

    normalized = _normalize_dossier_portfolio_review(review, trade_date="2026-06-04")

    assert normalized["shadow_top10_rank"].tolist() == [1, 6]
    assert normalized["weight"].tolist() == [0.2, 0.0]


def test_position_dossier_accepts_portfolio_review_without_trade_date_column() -> None:
    review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "candidate_rank": 1,
                "target_weight": 0.2,
                "is_current_holding": True,
                "final_label": "高优先级持有",
                "why_hold_or_change": "高支持度且为核心持仓，继续持有。",
            }
        ]
    )

    normalized = _normalize_dossier_portfolio_review(review, trade_date="2026-06-04")

    assert len(normalized) == 1
    assert normalized["asset_id"].tolist() == ["CN:SH:600183"]
    assert str(normalized["trade_date"].iloc[0].date()) == "2026-06-04"


def test_position_dossier_builds_summary_rows_and_writes_outputs(tmp_path: Path) -> None:
    review = portfolio_review.copy()
    review["is_current_holding"] = [True, True, False]
    research = research_packet.copy()
    research.loc[research["asset_id"].eq("CN:SH:688301"), "trade_date"] = "2026-06-04"

    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="live",
        portfolio_review=review,
        research_packet_candidates=research,
        output_dir=tmp_path,
    )

    summary_rows = result["summary_rows"]
    assert summary_rows["asset_id"].tolist() == [
        "CN:SH:600183",
        "CN:SZ:300201",
        "CN:SH:688301",
    ]
    assert summary_rows["current_decision"].tolist() == [
        "高优先级持有",
        "低优先级持有",
        "仅讨论",
    ]
    assert summary_rows["one_line_judgment"].tolist() == [
        "高支持度且为核心持仓，继续持有。但反证仍需盯住估值偏高，行业竞争加剧。",
        "支持度偏弱，继续观察。",
        "候选调入观察。但反证仍需盯住短期波动较大。",
    ]
    assert summary_rows["core_support_points"].tolist() == [
        "行业景气回升，研报覆盖较多。 | 近90天研报3篇；覆盖机构3家 | 目标价中位数103.5",
        "支持度偏弱，继续观察。 | 信息不足，需补充 | 信息不足，需补充",
        "基本面稳健。 | 近90天研报2篇；覆盖机构2家 | 目标价中位数210；目标涨幅中位数15%",
    ]
    assert summary_rows["core_opposition_points"].tolist() == [
        "估值偏高，行业竞争加剧。 | 下游需求不及预期风险；行业竞争加剧风险。",
        "信息不足，需补充 | 信息不足，需补充",
        "短期波动较大。 | 需求波动风险。",
    ]
    assert summary_rows["is_candidate_add"].tolist() == [False, False, True]
    assert summary_rows["is_candidate_reduce"].tolist() == [True, True, False]
    assert summary_rows["trend_tag"].tolist() == ["Top5", "Top5", "Top6-10"]
    assert summary_rows["research_tag"].tolist() == ["enhanced_research", "research_gap", "enhanced_research"]
    assert summary_rows["risk_tag"].tolist() == ["no_clear_hard_risk", "information_gap", "no_clear_hard_risk"]
    assert summary_rows["rebalance_tag"].tolist() == ["holding", "candidate_reduce", "candidate_add"]

    csv_path = tmp_path / "mid_trend_position_dossier_summary_2026-06-04.csv"
    md_path = tmp_path / "mid_trend_position_dossier_2026-06-04.md"
    assert result["paths"] == {
        "csv": str(csv_path),
        "md": str(md_path),
        "report": str(md_path),
    }
    assert csv_path.exists()
    assert md_path.exists()

    written = pd.read_csv(csv_path)
    assert written["asset_id"].tolist() == summary_rows["asset_id"].tolist()
    assert "Mid Trend Position Dossier 2026-06-04" in md_path.read_text(encoding="utf-8")


def test_cli_dispatches_mid_trend_position_dossier(monkeypatch, capsys, tmp_path: Path) -> None:
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "summary": {
                "news_enrichment_provided": "yes",
                "news_enrichment_used": "no",
                "matched_news_rows": 0,
            },
            "summary_rows": pd.DataFrame([{"ts_code": "600183.SH"}]),
            "paths": {
                "csv": str(tmp_path / "dossier_summary.csv"),
                "report": str(tmp_path / "dossier.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_position_dossier", fake_run, raising=False)

    cli.main_for_args(
        [
            "build-mid-trend-position-dossier",
            "--trade-date",
            "2026-06-04",
            "--mode",
            "live",
            "--portfolio-review-path",
            "outputs/research/mid_trend_portfolio_review.csv",
            "--research-packet-path",
            "outputs/research/mid_trend_research_packet_candidates.csv",
            "--news-enrichment-path",
            "outputs/research/topn_news_enrichment.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured == {
        "trade_date": "2026-06-04",
        "mode": "live",
        "portfolio_review_path": "outputs/research/mid_trend_portfolio_review.csv",
        "research_packet_path": "outputs/research/mid_trend_research_packet_candidates.csv",
        "news_enrichment_path": "outputs/research/topn_news_enrichment.csv",
        "output_dir": str(tmp_path),
    }
    out = capsys.readouterr().out
    assert f"mid_trend_position_dossier|csv|{tmp_path / 'dossier_summary.csv'}" in out
    assert f"mid_trend_position_dossier|report|{tmp_path / 'dossier.md'}" in out
    assert "mid_trend_position_dossier|rows|1" in out
    assert "mid_trend_position_dossier|news_enrichment_provided|yes" in out
    assert "mid_trend_position_dossier|news_enrichment_used|no" in out
    assert "mid_trend_position_dossier|matched_news_rows|0" in out
