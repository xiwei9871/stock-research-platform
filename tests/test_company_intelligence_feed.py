"""Tests for the CAP-01 evidence feed: yanbaoke brief parser + case loader."""
from __future__ import annotations

import json

from stock_research.company_intelligence_feed import (
    parse_evidence_brief,
    load_case_input,
)


BRIEF_SAMPLE = """# 301200 大族数控｜科技卡脖子证据简报（第二批）

## 候选背景
- 来源组：v5_hydrated

## 页码证据摘录

### 主营业务与收入结构
- [公司原始披露] 主营业务为 PCB 专用设备的研发、生产和销售 [P301200_010_01]（第 10 页）
- [券商二级研究观点] 钻孔类设备为主要产品（2025 年占营收 72.2%） [B301200_004_01]（第 4 页）

### 财务与经营快照
- [公司原始披露] 营业收入合计 5,772,935,488.47 元 [P301200_020_01]（第 20 页）

### 风险与反证
- [券商二级研究观点] 风险提示 AI 算力需求不及预期风险 [B301200_001_02]（第 1 页）

## 审阅要点
- 本批页码引用：4
"""


def test_parse_brief_extracts_evidence_with_page_and_source(tmp_path):
    path = tmp_path / "301200_大族数控_evidence_brief.md"
    path.write_text(BRIEF_SAMPLE, encoding="utf-8")

    parsed = parse_evidence_brief(path)

    assert parsed.company_code == "301200"
    assert parsed.company_name == "大族数控"
    assert len(parsed.evidence) == 4

    by_id = {ev.evidence_id: ev for ev in parsed.evidence}
    item = by_id["P301200_010_01"]
    assert item.dimension == "commercialization"
    assert item.direction == "support"
    assert item.page_or_section == "第 10 页"
    assert "PCB" in item.excerpt

    risk = by_id["B301200_001_02"]
    assert risk.dimension == "risk_counter"
    assert risk.direction == "refute"

    sources = {s.source_id: s for s in parsed.sources}
    assert sources["P301200_010_01"].source_type == "company_filing"
    assert sources["B301200_004_01"].source_type == "broker_report"


def test_parse_brief_maps_checklist_items_by_keywords(tmp_path):
    path = tmp_path / "301200_大族数控_evidence_brief.md"
    path.write_text(BRIEF_SAMPLE, encoding="utf-8")

    parsed = parse_evidence_brief(path)
    items = {ev.checklist_item for ev in parsed.evidence}

    # "研发、生产和销售" hits 客户验证-adjacent? 收入结构 excerpt hits 相关收入规模
    assert "相关收入规模" in items or "量产/订单" in items


def test_load_case_input_merges_brief_evidence_and_curated_claims(tmp_path):
    brief = tmp_path / "301200_大族数控_evidence_brief.md"
    brief.write_text(BRIEF_SAMPLE, encoding="utf-8")
    case = tmp_path / "case.json"
    case.write_text(
        json.dumps(
            {
                "company_code": "301200",
                "company_name": "大族数控",
                "as_of": "2026-10-20",
                "theme_context": {"theme_id": "semiconductor_equipment"},
                "brief_path": str(brief),
                "claims": [
                    {
                        "claim_id": "c-drill",
                        "dimension": "commercialization",
                        "claim_text": "钻孔设备构成主要收入",
                        "evidence_ids": ["B301200_004_01", "P301200_020_01"],
                    }
                ],
                "source_overrides": {
                    "P301200_010_01": {"published_at": "2026-04-30"},
                    "B301200_004_01": {"published_at": "2026-08-08",
                                        "available_at": "2026-10-19"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    inp = load_case_input(case)

    assert inp.company_code == "301200"
    assert len(inp.claims) == 1
    assert len(inp.evidence) == 4
    src = {s.source_id: s for s in inp.sources}
    assert src["P301200_010_01"].published_at == "2026-04-30"
    assert src["B301200_004_01"].available_at == "2026-10-19"
    assert inp.input_snapshot["brief_path"] == str(brief)


def test_render_markdown_sections_and_citations():
    from stock_research.company_intelligence import (
        CompanyEvidence, CompanySource, ResearchClaim, build_company_dossier,
    )
    from stock_research.company_intelligence_report import render_dossier_markdown

    dossier = build_company_dossier(
        company_code="002837", company_name="英维克", as_of="2026-10-20",
        claims=[ResearchClaim("c1", "commercialization", "液冷收入存在", ("e1",))],
        evidence=[
            CompanyEvidence("e1", "S1", "commercialization", "support",
                            excerpt="液冷收入xx", page_or_section="第 10 页"),
            CompanyEvidence("e2", "S2", "commercialization", "refute",
                            excerpt="未单独披露", page_or_section="第 3 页"),
        ],
        sources=[
            CompanySource("S1", "company_filing", published_at="2026-08-19"),
            CompanySource("S2", "broker_report", published_at="2026-10-12"),
        ],
    )
    md = render_dossier_markdown(dossier)
    assert "六维结论" in md
    assert "证据矩阵" in md
    assert "正反两面分析" in md
    assert "研究缺口" in md
    assert "研究结论" in md
    assert "e1" in md and "第 10 页" in md
    assert "正反冲突" in md  # contested commercialization
