from __future__ import annotations

import pandas as pd

from stock_research.research_narrative import (
    build_research_decision_narrative_from_fact_sheet,
    build_research_fact_sheet_from_frames,
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


def test_build_research_fact_sheet_from_frames_maps_core_fields() -> None:
    fact_sheet = build_research_fact_sheet_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet,
    )
    rows = fact_sheet.set_index("asset_id")

    core_row = rows.loc["CN:SH:600183"]
    assert core_row.name == "CN:SH:600183"
    assert core_row["ts_code"] == "600183.SH"
    assert core_row["stock_name"] == "生益科技"
    assert str(core_row["trade_date"]) == "2026-06-04"
    assert core_row["report_count_90d"] == 3
    assert core_row["target_price_median"] == 103.5
    assert core_row["risk_summary_compact"] == "下游需求不及预期风险；行业竞争加剧风险。"
    assert bool(core_row["has_target_price"]) is True

    sparse_row = rows.loc["CN:SZ:300201"]
    assert sparse_row["ts_code"] == "300201.SZ"
    assert sparse_row["stock_name"] == "海伦哲"
    assert str(sparse_row["trade_date"]) == "2026-06-04"
    assert pd.isna(sparse_row["target_price_median"])
    assert bool(sparse_row["has_target_price"]) is False


def test_build_research_decision_narrative_from_fact_sheet_generates_support_and_oppose_facts() -> None:
    fact_sheet = build_research_fact_sheet_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet,
    )
    narrative = build_research_decision_narrative_from_fact_sheet(fact_sheet)
    row = narrative.set_index("asset_id").loc["CN:SH:600183"]
    assert row["one_line_judgment"] == "高支持度且为核心持仓，继续持有。但反证仍需盯住估值偏高，行业竞争加剧。"
    assert row["support_fact_1"] == "行业景气回升，研报覆盖较多。"
    assert row["support_fact_2"] == "近90天研报3篇；覆盖机构3家"
    assert row["support_fact_3"] == "目标价中位数103.5"
    assert row["oppose_fact_1"] == "估值偏高，行业竞争加剧。"
    assert row["oppose_fact_2"] == "下游需求不及预期风险；行业竞争加剧风险。"
    assert row["watch_point"] == "下游需求不及预期风险；行业竞争加剧风险。"
    assert row["falsification_condition"] == "估值偏高，行业竞争加剧。"
    assert row["what_is_working_summary"] == "行业景气回升，研报覆盖较多。"
    assert row["industry_position_summary"] == "信息不足，需补充"
    assert row["institution_view_summary"] == "近90天研报3篇；覆盖机构3家；90天覆盖3篇"
    assert row["valuation_summary"] == "目标价中位数103.5"
    assert row["risk_summary"] == "估值偏高，行业竞争加剧。下游需求不及预期风险；行业竞争加剧风险。"
    assert row["decision_confidence"] == "rich"
    assert row["narrative_quality_flag"] == "medium"


def test_build_research_decision_narrative_degrades_sparse_rows_to_placeholders() -> None:
    fact_sheet = build_research_fact_sheet_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet,
    )
    narrative = build_research_decision_narrative_from_fact_sheet(fact_sheet)
    row = narrative.set_index("asset_id").loc["CN:SZ:300201"]

    assert row["one_line_judgment"] == "支持度偏弱，继续观察。"
    assert row["support_fact_1"] == "支持度偏弱，继续观察。"
    assert row["support_fact_2"] == "信息不足，需补充"
    assert row["support_fact_3"] == "信息不足，需补充"
    assert row["oppose_fact_1"] == "信息不足，需补充"
    assert row["oppose_fact_2"] == "信息不足，需补充"
    assert row["watch_point"] == "信息不足，需补充"
    assert row["falsification_condition"] == "信息不足，需补充"
    assert row["industry_position_summary"] == "信息不足，需补充"
    assert row["institution_view_summary"] == "信息不足，需补充"
    assert row["valuation_summary"] == "信息不足，需补充"
    assert row["risk_summary"] == "信息不足，需补充"
    assert row["decision_confidence"] == "thin"
    assert row["narrative_quality_flag"] == "thin"


def test_build_research_decision_narrative_synthesizes_rich_rows_deterministically() -> None:
    fact_sheet = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "示例公司",
                "trade_date": "2026-06-04",
                "report_count_90d": 5,
                "broker_coverage_count": 4,
                "latest_rating": "买入",
                "target_price_median": 42.0,
                "target_upside_median": 0.25,
                "profit_forecast_count": 5,
                "pdf_risk_section_count": 4,
                "research_support_score": 36,
                "research_confidence": "rich",
                "bull_case_summary": "需求扩张带动量价齐升。",
                "key_growth_driver": "高端产品放量。",
                "institution_consensus_note": "近90天研报5篇；覆盖机构4家",
                "positive_rating_summary": "评级：买入；90天覆盖5篇",
                "target_price_basis_note": "目标价中位数42；目标涨幅中位数25%；参考评级买入",
                "bear_case_summary": "原材料波动压缩利润。",
                "key_risk_driver": "原材料波动压缩利润。",
                "negative_research_note": "部分机构担心需求持续性。",
                "institution_disagreement_note": "部分机构担心需求持续性。",
                "risk_summary_compact": "需求不及预期风险。",
                "industry_position_note": "行业龙头，份额持续提升。",
                "product_position_note": "高端产品占比提升。",
                "moat_or_scarcity_note": "客户认证壁垒较强。",
                "industry_mainline_context": "国产替代持续推进。",
                "theme_alignment_note": "高优先级持有；主线环境：国产替代持续推进。",
                "analyst_core_assumption": "需求扩张带动量价齐升。",
                "valuation_anchor_note": "目标价中位数42；目标涨幅中位数25%；参考评级买入",
                "expectation_dependency_note": "后续兑现依赖目标涨幅假设继续成立（25%）。",
                "has_target_price": True,
                "has_profit_forecast": True,
                "has_industry_position": True,
                "has_product_position": True,
                "has_moat_note": True,
                "has_bull_case": True,
                "has_bear_case": True,
            }
        ]
    )

    narrative = build_research_decision_narrative_from_fact_sheet(fact_sheet)
    row = narrative.iloc[0]

    assert row["one_line_judgment"] == "需求扩张带动量价齐升。但反证仍需盯住原材料波动压缩利润。"
    assert row["support_fact_1"] == "高端产品放量。"
    assert row["support_fact_2"] == "近90天研报5篇；覆盖机构4家"
    assert row["support_fact_3"] == "目标价中位数42；目标涨幅中位数25%；参考评级买入"
    assert row["oppose_fact_1"] == "原材料波动压缩利润。"
    assert row["oppose_fact_2"] == "需求不及预期风险。"
    assert row["watch_point"] == "后续兑现依赖目标涨幅假设继续成立（25%）。"
    assert row["falsification_condition"] == "原材料波动压缩利润。"
    assert (
        row["industry_position_summary"]
        == "行业龙头，份额持续提升。高端产品占比提升。客户认证壁垒较强。国产替代持续推进。"
    )
    assert (
        row["institution_view_summary"]
        == "近90天研报5篇；覆盖机构4家；评级：买入；90天覆盖5篇；部分机构担心需求持续性。"
    )
    assert (
        row["valuation_summary"]
        == "目标价中位数42；目标涨幅中位数25%；参考评级买入。后续兑现依赖目标涨幅假设继续成立（25%）。"
    )
    assert row["risk_summary"] == "原材料波动压缩利润。需求不及预期风险。"
    assert row["decision_confidence"] == "rich"
    assert row["narrative_quality_flag"] == "rich"


def test_research_fact_sheet_replay_filters_future_rows() -> None:
    fact_sheet = build_research_fact_sheet_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet,
    )
    rows = fact_sheet.set_index("asset_id")
    replay_row = rows.loc["CN:SH:688301"]
    assert pd.isna(replay_row["target_price_median"])
    assert pd.isna(replay_row["report_count_90d"])


def test_research_fact_sheet_keeps_same_day_discussion_rows() -> None:
    same_day_research_packet = pd.concat(
        [
            research_packet,
            pd.DataFrame(
                [
                    {
                        "trade_date": "2026-06-04",
                        "asset_id": "CN:SH:688301",
                        "ts_code": "688301.SH",
                        "stock_name": "奕瑞科技",
                        "research_support_score_pit": 22,
                        "broker_report_count_90d": 1,
                        "target_price_median_pit": 205.0,
                        "target_upside_median_pit": 0.12,
                        "broker_coverage_count_pit": 1,
                        "pdf_target_price_count_90d": 1,
                        "pdf_target_price_high_confidence_count_90d": 1,
                        "pdf_profit_forecast_count_90d": 1,
                        "pdf_risk_section_count_90d": 1,
                        "latest_pdf_risk_summary": "需求波动风险。",
                        "fundamental_hard_risk": "no_clear_hard_risk",
                        "main_positive_evidence": "基本面稳健。",
                        "main_risk_evidence": "短期波动较大。",
                        "why_hold_or_change": "候选调入观察。",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    fact_sheet = build_research_fact_sheet_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=portfolio_review,
        research_packet_candidates=same_day_research_packet,
    )
    rows = fact_sheet.set_index("asset_id")

    discussion_row = rows.loc["CN:SH:688301"]
    assert discussion_row["ts_code"] == "688301.SH"
    assert discussion_row["stock_name"] == "奕瑞科技"
    assert str(discussion_row["trade_date"]) == "2026-06-04"


def test_research_fact_sheet_uses_normal_pandas_set_index_behavior() -> None:
    fact_sheet = build_research_fact_sheet_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet,
    )

    indexed = fact_sheet.set_index("asset_id")
    assert "asset_id" not in indexed.columns


def test_research_fact_sheet_dedupes_same_day_review_rows_by_best_rank() -> None:
    duplicate_review = pd.concat(
        [
            portfolio_review,
            pd.DataFrame(
                [
                    {
                        "trade_date": "2026-06-04",
                        "asset_id": "CN:SH:600183",
                        "ts_code": "600183.SH",
                        "stock_name": "生益科技-重复",
                        "section": "top6_10",
                        "shadow_top10_rank": 9,
                        "weight": 0.05,
                        "final_label": "仅讨论",
                        "why_hold_or_change": "重复行，不应优先。",
                        "main_positive_evidence": "重复正面。",
                        "main_risk_evidence": "重复风险。",
                        "latest_pdf_risk_summary": "重复风险摘要。",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    fact_sheet = build_research_fact_sheet_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=duplicate_review,
        research_packet_candidates=research_packet,
    )
    row = fact_sheet.set_index("asset_id").loc["CN:SH:600183"]

    assert row["stock_name"] == "生益科技"
    assert row["bull_case_summary"] == "高支持度且为核心持仓，继续持有。"
