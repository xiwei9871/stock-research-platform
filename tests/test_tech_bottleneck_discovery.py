from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_discovery import (
    build_tech_bottleneck_packets,
    render_tech_bottleneck_markdown,
    write_tech_bottleneck_artifacts,
)


def _candidate_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "示例光电",
                "trade_date": "2026-06-05",
                "terminal_demand": "AI 数据中心光互连",
                "supply_chain_node": "高速光模块上游关键材料",
                "company_exposure": "公司提供关键衬底材料，客户验证周期长。",
                "terminal_demand_certainty": 5,
                "single_point_importance": 5,
                "supply_concentration": 4,
                "capacity_expansion_difficulty": 4,
                "technical_barrier": 5,
                "qualification_or_customer_switching_cost": 4,
                "substitution_difficulty": 4,
                "value_capture_power": 3,
                "market_cap_room": 4,
                "low_sell_side_coverage": 5,
                "low_institutional_attention": 4,
                "old_business_mispricing": 4,
                "new_business_not_in_numbers": 5,
                "valuation_vs_peers": 3,
                "price_not_overheated": 4,
                "narrative_early_stage": 5,
                "risk_penalty": 1,
            },
            {
                "asset_id": "CN:SZ:300001",
                "stock_name": "普通科技",
                "trade_date": "2026-06-05",
                "terminal_demand": "泛 AI 概念",
                "supply_chain_node": "下游应用软件",
                "company_exposure": "概念相关，未披露直接收入。",
                "terminal_demand_certainty": 2,
                "single_point_importance": 1,
                "supply_concentration": 1,
                "capacity_expansion_difficulty": 1,
                "technical_barrier": 1,
                "qualification_or_customer_switching_cost": 1,
                "substitution_difficulty": 1,
                "value_capture_power": 1,
                "market_cap_room": 2,
                "low_sell_side_coverage": 2,
                "low_institutional_attention": 2,
                "old_business_mispricing": 1,
                "new_business_not_in_numbers": 1,
                "valuation_vs_peers": 1,
                "price_not_overheated": 1,
                "narrative_early_stage": 1,
                "risk_penalty": 4,
            },
        ]
    )


def _evidence_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "evidence_tier": "tier1",
                "source_type": "annual_report",
                "source_url_or_path": "reports/example-annual-report.pdf",
                "source_date": "2026-04-30",
                "claim": "公司披露关键材料客户验证和扩产计划。",
                "supports": "客户验证周期长，供给扩张受产能约束。",
                "contradicts": "",
                "confidence": "high",
                "freshness": "fresh",
            },
            {
                "asset_id": "CN:SH:688001",
                "evidence_tier": "tier1",
                "source_type": "announcement",
                "source_url_or_path": "announcements/example-capacity.pdf",
                "source_date": "2026-05-20",
                "claim": "公司公告新产能建设周期超过 18 个月。",
                "supports": "扩产慢，短期供给不易快速释放。",
                "contradicts": "",
                "confidence": "high",
                "freshness": "fresh",
            },
            {
                "asset_id": "CN:SZ:300001",
                "evidence_tier": "tier3",
                "source_type": "social_media",
                "source_url_or_path": "https://example.com/social",
                "source_date": "2026-06-01",
                "claim": "社媒称公司可能受益 AI。",
                "supports": "概念相关。",
                "contradicts": "",
                "confidence": "low",
                "freshness": "fresh",
            },
        ]
    )


def test_build_tech_bottleneck_packets_scores_and_states() -> None:
    packets = build_tech_bottleneck_packets(
        candidates=_candidate_frame(),
        evidence=_evidence_frame(),
        run_id="tech-bottleneck-2026-06-05",
    )

    rows = packets.set_index("asset_id")
    strong = rows.loc["CN:SH:688001"]
    weak = rows.loc["CN:SZ:300001"]

    assert strong["chokepoint_score"] == 34.0
    assert strong["underpricing_score"] == 34.0
    assert strong["evidence_score"] == 5.0
    assert strong["candidate_state"] == "conviction_candidate"
    assert "市场可能仍按旧业务或普通供应商定价" in strong["market_misconception"]
    assert len(strong["evidence_items"]) == 2

    assert weak["chokepoint_score"] == 9.0
    assert weak["underpricing_score"] == 11.0
    assert weak["evidence_score"] == 1.0
    assert weak["candidate_state"] == "reject"
    assert len(weak["evidence_items"]) == 1


def test_render_tech_bottleneck_markdown_includes_review_and_evidence() -> None:
    packets = build_tech_bottleneck_packets(
        candidates=_candidate_frame(),
        evidence=_evidence_frame(),
        run_id="tech-bottleneck-2026-06-05",
    )
    packet = packets.set_index("asset_id").loc["CN:SH:688001"].to_dict()

    markdown = render_tech_bottleneck_markdown(packet)

    assert "# 示例光电 tech-bottleneck-discovery Packet" in markdown
    assert "State: `conviction_candidate`" in markdown
    assert "## Evidence" in markdown
    assert "[tier1] 公司披露关键材料客户验证和扩产计划。" in markdown
    assert "Decision: `pending_review`" in markdown


def test_write_tech_bottleneck_artifacts_writes_json_csv_markdown(tmp_path: Path) -> None:
    packets = build_tech_bottleneck_packets(
        candidates=_candidate_frame(),
        evidence=_evidence_frame(),
        run_id="tech-bottleneck-2026-06-05",
    )

    paths = write_tech_bottleneck_artifacts(packets=packets, output_dir=tmp_path)

    assert paths["json"].exists()
    assert paths["csv"].exists()
    assert paths["summary"].exists()
    assert (tmp_path / "CN_SH_688001.md").exists()
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload[0]["run_id"] == "tech-bottleneck-2026-06-05"
    assert "tech-bottleneck-discovery Summary" in paths["summary"].read_text(encoding="utf-8")
