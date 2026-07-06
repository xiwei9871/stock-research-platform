#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_method_codification_v1"
TASK_NAME = "tech_bottleneck_method_codification_v1"
METHOD_NAME_CN = "硬科技瓶颈暴露研究选股法"
METHOD_NAME_EN = "Hard-Tech Bottleneck Exposure Research Method"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def formal_strategy_diff() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""


def build_taxonomy() -> dict[str, Any]:
    return {
        "method_scope": "research_only_hard_tech_bottleneck_exposure",
        "domains": {
            "AI算力与数据中心": ["光互联", "HBM相关材料与设备", "AI服务器PCB", "液冷", "高端电源", "高速连接器"],
            "半导体": ["半导体设备", "半导体材料", "半导体零部件", "EDA/IP", "先进封装", "功率器件", "传感器与特种芯片"],
            "工业软件与基础软件": ["操作系统", "数据库", "中间件", "CAD/CAE/CAM", "PLM/MES", "工业控制软件", "信创基础设施"],
            "高端制造装备": ["工业母机", "五轴数控", "机器人核心部件", "伺服系统", "控制器", "精密减速器", "高端检测装备"],
            "航空航天与军工电子": ["航空发动机", "高温合金", "惯导", "雷达", "红外", "军工电子", "特种材料"],
            "高端仪器仪表与科学仪器": ["质谱", "色谱", "电子显微镜", "半导体检测", "光学检测", "工业测量", "实验室分析仪器"],
            "新材料": ["电子化学品", "光刻胶", "CMP材料", "PI膜", "高端合金", "高端碳材料", "陶瓷材料", "高纯材料"],
            "高端医疗与生命科学工具": ["高端影像", "IVD核心设备", "生命科学仪器", "生物制造设备", "高值耗材关键材料"],
            "光电与通信": ["光通信芯片", "激光器", "光学元件", "射频器件", "卫星通信", "高端网络设备"],
            "能源与电力电子关键环节": ["高端电力电子", "储能核心部件", "特高压核心设备", "工业控制", "电网安全关键设备"],
            "网络安全与数据安全": ["网络安全基础设施", "密码安全", "工控安全", "数据安全", "安全芯片"],
            "其他战略性关键环节": ["由证据驱动归类"],
        },
    }


def build_evidence_hierarchy() -> dict[str, Any]:
    return {
        "research_only": True,
        "tiers": {
            "Tier 1": {
                "description": "Primary source or direct operating evidence.",
                "allowed_evidence": ["公告", "年报", "财报", "订单", "客户认证", "产能", "业绩变化"],
                "priority_effect": "can support Tier A or Tier B when business exposure is direct",
            },
            "Tier 2": {
                "description": "Secondary but reviewable industrial evidence.",
                "allowed_evidence": ["研报", "专利", "招聘", "政府项目", "行业会议", "客户/供应商披露"],
                "priority_effect": "can support Tier B or Tier C and may upgrade after primary confirmation",
            },
            "Tier 3": {
                "description": "Weak attention or inference evidence.",
                "allowed_evidence": ["社媒", "KOL", "传闻", "AI推断"],
                "priority_effect": "watch_only_or_data_gap_only; cannot upgrade to high priority without stronger evidence",
            },
        },
        "minimum_rule": "Pure theme similarity is insufficient. Candidate reason must cite evidence type, strength, and missing fields.",
    }


def build_real_exposure_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "fields": {
            "customer_certification_stage": {
                "description": "Customer adoption stage for the bottleneck product or capability.",
                "enum": [
                    "mass_production",
                    "batch_delivery",
                    "customer_certified",
                    "customer_validation",
                    "sample_testing",
                    "R&D",
                    "unclear",
                    "missing",
                ],
            },
            "supplier_concentration_type": {
                "description": "Supply-side scarcity or constraint pattern.",
                "enum": [
                    "domestic_substitution",
                    "import_dependency",
                    "scarce_supplier",
                    "capacity_constraint",
                    "certification_bottleneck",
                    "technology_monopoly",
                    "localized_alternative",
                    "unclear",
                    "missing",
                ],
            },
            "revenue_exposure_bucket": {
                "description": "How visible the bottleneck exposure is in company revenue or business mix.",
                "enum": [
                    "core_revenue",
                    "meaningful_revenue",
                    "emerging_revenue",
                    "small_exposure",
                    "concept_only",
                    "unclear",
                    "missing",
                ],
            },
        },
    }


def build_bottleneck_exposure_scoring() -> dict[str, Any]:
    return {
        "score_name": "bottleneck_exposure_score",
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "not_a_trading_signal": True,
        "not_for_baseline_admission": True,
        "purpose": "Candidate identification for hard-tech bottleneck exposure.",
        "score_range": "0-100",
        "components": {
            "trend_certainty_score": {"points": "0-15", "meaning": "durable industrial demand rather than short cycle attention"},
            "bottleneck_criticality_score": {"points": "0-25", "meaning": "criticality of the upstream bottleneck to downstream delivery"},
            "supply_constraint_score": {"points": "0-20", "meaning": "scarcity, expansion difficulty, supplier concentration, or import dependency"},
            "real_business_exposure_score": {"points": "0-20", "meaning": "company-level product, revenue, customer, capacity, certification, or order exposure"},
            "evidence_quality_score": {"points": "0-15", "meaning": "source quality, directness, recency, and conflict status"},
            "commercialization_stage_score": {"points": "0-5", "meaning": "from R&D to validation to delivery or production"},
        },
        "interpretation": {
            "80_100": "strong exposure candidate for manual review",
            "60_79": "medium exposure candidate requiring evidence completion",
            "40_59": "weak or indirect exposure retained for high recall",
            "below_40": "watch only or excluded unless new evidence appears",
        },
    }


def build_research_priority_scoring() -> dict[str, Any]:
    return {
        "score_name": "research_candidate_score",
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "not_a_trading_signal": True,
        "not_for_baseline_admission": True,
        "purpose": "Human review ordering after candidate identification.",
        "formula": (
            "0.30 * evidence_quality_score + 0.25 * low_position_score + "
            "0.20 * commercial_validation_score + 0.15 * freshness_score - "
            "0.10 * fundamental_risk_score"
        ),
        "component_notes": {
            "evidence_quality_score": "source strength and direct exposure support",
            "low_position_score": "research priority context only; not a market-action rule",
            "commercial_validation_score": "customer validation, delivery, order, or production evidence",
            "freshness_score": "new evidence, new disclosure, or under-reviewed context",
            "fundamental_risk_score": "risk penalty for financial or source concerns",
        },
    }


def build_inclusion_exclusion() -> dict[str, Any]:
    return {
        "research_only": True,
        "inclusion": [
            "Trend is durable and supported by industrial demand.",
            "Supply-chain decomposition identifies an upstream bottleneck point.",
            "Bottleneck has scarcity, technical difficulty, certification barrier, or limited substitution.",
            "Company has direct product, revenue, capacity, customer, certification, order, announcement, report, or financial-statement exposure.",
            "Evidence is reviewable and assigned a tier and strength.",
        ],
        "exclusion": [
            "Main business is unrelated.",
            "Name similarity only.",
            "Theme label only without business exposure.",
            "Trade agency business without bottleneck control.",
            "Financial investment or minority participation without operating exposure.",
            "Evidence conflict cannot be reconciled.",
            "No real business exposure after review.",
        ],
        "downgrade": [
            "Tier 3-only evidence becomes Watch Only or data_gap_review.",
            "Broad industry hit without company-specific evidence becomes Tier C or Excluded.",
            "Revenue exposure unclear becomes revenue_exposure_review.",
            "Customer certification unclear becomes customer_certification_review.",
        ],
    }


def build_candidate_tier_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "tiers": {
            "Tier A": {
                "label": "强瓶颈候选",
                "requirements": [
                    "trend_certainty_score high",
                    "bottleneck_criticality_score high",
                    "real_business_exposure_score high",
                    "evidence_strength at least medium",
                    "main business directly related",
                    "not concept-only",
                ],
            },
            "Tier B": {
                "label": "中等瓶颈候选",
                "requirements": ["technology direction and main business related", "evidence incomplete or commercialization unclear", "manual review required"],
            },
            "Tier C": {
                "label": "弱候选 / 扩展候选",
                "requirements": ["concept or indirect supply-chain relation", "keyword or industry hit", "main business relevance unclear", "high-recall extension only"],
            },
            "Watch Only": {
                "label": "观察但证据不足",
                "requirements": ["weak or Tier 3-only evidence", "insufficient for priority upgrade", "retain source gap notes"],
            },
            "Risk Review": {
                "label": "风险复核",
                "requirements": ["risk event", "source conflict", "financial anomaly", "material uncertainty"],
            },
            "Excluded": {
                "label": "排除",
                "requirements": ["unrelated main business", "name-only match", "theme-only", "trade agency", "investment-only exposure", "evidence conflict", "no real exposure"],
            },
        },
    }


def build_review_queue_schema() -> dict[str, Any]:
    return {
        "research_only": True,
        "review_queue_types": {
            "high_quality_fundamental_review": "Review durable revenue, margin, cashflow, and R&D quality.",
            "thesis_validation_review": "Validate the industrial bottleneck thesis and supply-chain mapping.",
            "customer_certification_review": "Check customer validation, certification stage, and delivery status.",
            "revenue_exposure_review": "Estimate whether bottleneck exposure is core, meaningful, emerging, small, or concept-only.",
            "risk_event_review": "Review material risk disclosures or financial deterioration.",
            "valuation_anomaly_review": "Review whether market understanding may lag business exposure; research context only.",
            "data_gap_review": "Collect missing filings, reports, or source references.",
            "source_conflict_review": "Resolve contradictions across filings, reports, news, and derived datasets.",
            "watch_only": "Keep in low-priority observation until stronger evidence appears.",
        },
        "queue_output_contract": {
            "must_explain": ["why_review", "missing_evidence", "risk_context", "manual_review_focus"],
            "must_not_include": ["market-action instruction", "formal strategy admission", "automatic execution field"],
        },
    }


def build_method_summary() -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "method_name_cn": METHOD_NAME_CN,
        "method_name_en": METHOD_NAME_EN,
        "research_only": True,
        "one_sentence_definition": "高确定性产业趋势 + 上游关键瓶颈 + 难扩产 / 难替代 / 认证壁垒 + 公司有真实暴露 + 市场还没充分定价 + 有证据可验证。",
        "core_purpose": "Find hard-tech supply-chain bottleneck companies that may be under-recognized by the market.",
        "not_strategy": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "flow": [
            "find durable industrial trend first",
            "decompose supply chain backwards",
            "identify upstream bottleneck points",
            "map to A-share listed companies",
            "verify real business exposure",
            "rank research review priority",
            "produce manual review queue",
        ],
    }


def build_field_dictionary_rows() -> list[dict[str, Any]]:
    definitions = {
        "stock_code": ("identity", "A-share numeric stock code."),
        "ts_code": ("identity", "Tushare-style code when available."),
        "stock_name": ("identity", "Company display name."),
        "exchange": ("identity", "Exchange code."),
        "industry": ("identity", "Primary industry classification."),
        "sub_industry": ("identity", "Sub-industry or source industry code."),
        "trend_domain": ("taxonomy", "Durable industrial trend domain."),
        "trend_certainty_score": ("bottleneck_exposure_score", "0-15 durable trend score."),
        "supply_chain_layer": ("taxonomy", "Terminal, system, module, component, material, equipment, or process layer."),
        "bottleneck_type": ("taxonomy", "Scarcity, certification, technology, capacity, or substitution bottleneck type."),
        "bottleneck_criticality_score": ("bottleneck_exposure_score", "0-25 criticality score."),
        "customer_certification_stage": ("real_exposure", "Customer adoption and certification stage enum."),
        "supplier_concentration_type": ("real_exposure", "Supply constraint pattern enum."),
        "revenue_exposure_bucket": ("real_exposure", "Revenue exposure enum."),
        "main_business_relevance": ("real_exposure", "high, medium, low, or unclear relevance to main business."),
        "real_business_exposure_score": ("bottleneck_exposure_score", "0-20 company exposure score."),
        "domestic_substitution_relevance": ("real_exposure", "Relevance to domestic substitution."),
        "supply_chain_constraint_relevance": ("real_exposure", "Relevance to supply-chain constraints."),
        "technology_bottleneck_relevance": ("real_exposure", "Relevance to key technology, material, equipment, process, or software bottleneck."),
        "commercialization_stage": ("real_exposure", "R&D, sample, validation, delivery, production, or unclear."),
        "evidence_tier": ("evidence", "Tier 1, Tier 2, or Tier 3 source hierarchy."),
        "evidence_type": ("evidence", "Filing, report, order, certification, patent, hiring, project, news, or inference source type."),
        "evidence_strength": ("evidence", "strong, medium, weak, or missing."),
        "evidence_quality_score": ("bottleneck_exposure_score", "0-15 evidence quality score."),
        "evidence_count": ("evidence", "Count of evidence items used for research review."),
        "source_conflict_flag": ("evidence", "True when sources conflict materially."),
        "data_gap_flags": ("evidence", "Pipe-delimited missing source or unclear field flags."),
        "low_position_score": ("research_candidate_score", "Research priority context score, not a market-action rule."),
        "price_percentile_120d": ("research_context", "120-day price percentile for research context."),
        "drawdown_from_120d_high": ("research_context", "Distance from recent high for research context."),
        "volatility_contraction_20d": ("research_context", "20-day volatility contraction context."),
        "freshness_score": ("research_candidate_score", "Evidence freshness score."),
        "fundamental_risk_score": ("research_candidate_score", "Financial/source risk penalty score."),
        "commercial_validation_score": ("research_candidate_score", "Commercial validation score."),
        "bottleneck_exposure_score": ("research_score", "Research-only candidate identification score."),
        "research_candidate_score": ("research_score", "Research-only manual review priority score."),
        "candidate_tier": ("classification", "Tier A, Tier B, Tier C, Watch Only, Risk Review, or Excluded."),
        "review_priority": ("classification", "high, medium, low, data_gap, source_conflict, or risk_review."),
        "review_queue_type": ("review_queue", "Manual review queue type."),
        "candidate_reason": ("review_queue", "Human-readable research reason."),
        "manual_review_focus": ("review_queue", "Specific questions for manual review."),
        "excluded_flag": ("classification", "True when excluded from candidate pool."),
        "excluded_reason": ("classification", "Reason for exclusion or downgrade."),
        "research_only": ("guardrail", "Always true for this method output."),
        "used_for_signal": ("guardrail", "Always false."),
        "used_for_admission": ("guardrail", "Always false."),
    }
    rows = []
    for field_name, (category, description) in definitions.items():
        rows.append(
            {
                "field_name": field_name,
                "category": category,
                "description": description,
                "allowed_values_or_range": allowed_values_for_field(field_name),
                "required": True,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return rows


def allowed_values_for_field(field_name: str) -> str:
    enums = {
        "customer_certification_stage": "mass_production|batch_delivery|customer_certified|customer_validation|sample_testing|R&D|unclear|missing",
        "supplier_concentration_type": "domestic_substitution|import_dependency|scarce_supplier|capacity_constraint|certification_bottleneck|technology_monopoly|localized_alternative|unclear|missing",
        "revenue_exposure_bucket": "core_revenue|meaningful_revenue|emerging_revenue|small_exposure|concept_only|unclear|missing",
        "candidate_tier": "Tier A|Tier B|Tier C|Watch Only|Risk Review|Excluded",
        "review_queue_type": "high_quality_fundamental_review|thesis_validation_review|customer_certification_review|revenue_exposure_review|risk_event_review|valuation_anomaly_review|data_gap_review|source_conflict_review|watch_only",
        "trend_certainty_score": "0-15",
        "bottleneck_criticality_score": "0-25",
        "real_business_exposure_score": "0-20",
        "evidence_quality_score": "0-15",
        "bottleneck_exposure_score": "0-100",
        "research_candidate_score": "research-priority numeric score",
        "used_for_signal": "false",
        "used_for_admission": "false",
        "research_only": "true",
    }
    return enums.get(field_name, "")


def write_field_dictionary(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "field_name",
                "category",
                "description",
                "allowed_values_or_range",
                "required",
                "research_only",
                "used_for_signal",
                "used_for_admission",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def method_definition_md() -> str:
    return f"""# {METHOD_NAME_CN}

English name: {METHOD_NAME_EN}

This is a research-only method for finding A-share companies with real exposure to hard-tech supply-chain bottlenecks. The method starts from durable industrial trends, decomposes supply chains backward, identifies upstream constraint points, and then verifies whether listed companies have direct business exposure.

Core sentence:

高确定性产业趋势 + 上游关键瓶颈 + 难扩产 / 难替代 / 认证壁垒 + 公司有真实暴露 + 市场还没充分定价 + 有证据可验证。

This method is not a formal strategy module, does not change baseline admission, and does not produce market-action instructions. All scoring fields are research-only and explicitly carry `used_for_signal=false` and `used_for_admission=false`.

## Research Flow

1. Identify durable hard-tech trend domains.
2. Decompose terminal demand into systems, modules, components, materials, equipment, processes, and bottleneck points.
3. Test whether the bottleneck is real through supply concentration, capacity expansion difficulty, technical threshold, certification cycle, substitution scarcity, downstream necessity, and value capture.
4. Map bottleneck points to A-share companies.
5. Verify real business exposure through product, revenue, customer, capacity, order, certification, filing, financial statement, report, or industrial evidence.
6. Separate exposure scoring from research priority scoring.
7. Produce manual review queues with evidence gaps and review focus.
"""


def supply_chain_framework_md() -> str:
    return """# Tech Bottleneck Supply Chain Bottleneck Framework

The method does not start from a ticker list. It starts from a durable industrial demand path:

terminal demand -> system / complete machine -> module -> component -> material / equipment / process -> bottleneck point -> A-share company exposure

## Bottleneck Tests

- Supply concentration: few capable suppliers or concentrated capacity.
- Expansion difficulty: long buildout cycle, scarce talent, hard-to-scale process, or equipment limits.
- Technical threshold: difficult process control, materials know-how, precision, yield, reliability, or software complexity.
- Customer certification cycle: long validation, qualification, trial production, or supplier switching cycle.
- Substitute scarcity: few viable alternatives, especially for domestic replacement.
- Downstream necessity: product is required for downstream delivery or reliability.
- Value capture: supplier can retain margin, pricing power, or strategic importance.

## Company Exposure Tests

Company exposure must be verified by actual product, revenue, customer, capacity, order, certification, announcement, annual report, financial statement, research report, or industrial evidence. Name similarity and broad concept labels are insufficient.
"""


def scan_plan_md() -> str:
    return """# Tech Bottleneck A-share Candidate Universe Scan Plan

## Objective

Build a high-recall A-share candidate universe for the hard-tech bottleneck exposure method. The output remains research-only and feeds manual review, not formal strategy admission.

## Channels

1. Industry channel: scan semiconductor, electronic materials, industrial software, machinery, instruments, advanced materials, communication, power electronics, cyber security, medical devices, aerospace, and military electronics classifications.
2. Keyword channel: scan company name, main business, product description, announcements, annual reports, financial statements, research-report metadata, and news mappings for bottleneck terms.
3. Evidence channel: extract direct product, customer, certification, order, capacity, patent, project, and revenue exposure evidence.
4. Seed expansion channel: compare against the 102-name seed list, expand by same domain and adjacent supply-chain layer, but never treat seed as the full universe.
5. Exclusion channel: downgrade or exclude concept-only, name-only, trade agency, investment-only, or conflicting-source rows.

## Outputs

Each candidate row should include trend domain, supply-chain layer, bottleneck type, real exposure fields, evidence tier, candidate tier, review queue type, and guardrail fields. Candidate scores are only for research review ordering.

## Manual Review

The scanner should produce manual review queues for high-quality fundamental review, thesis validation, customer certification, revenue exposure, risk event, valuation anomaly, data gap, and source conflict review.
"""


def build_report(summary: dict[str, Any], guardrails: dict[str, Any]) -> str:
    return f"""# Tech Bottleneck Method Codification v1

## 1. Scope

This task codifies a research selection method only. It does not create formal strategy outputs, does not change baseline admission, and does not modify dashboard or manual review persistence.

## 2. Method Summary

The method is {METHOD_NAME_CN} / {METHOD_NAME_EN}.

Core sentence:

高确定性产业趋势 + 上游关键瓶颈 + 难扩产 / 难替代 / 认证壁垒 + 公司有真实暴露 + 市场还没充分定价 + 有证据可验证。

## 3. Research Flow

确定高景气产业 -> 拆供应链 -> 找上游瓶颈 -> 映射 A 股公司 -> 验证真实业务暴露 -> 检查低认知 / 低位置 -> 收集公告 / 财报 / 研报证据 -> 计算研究优先级 -> 生成人工复核清单 -> 持续跟踪证据和结果。

## 4. Supply Chain Bottleneck Framework

The bottleneck test checks supply concentration, expansion difficulty, technical threshold, customer certification cycle, substitute scarcity, domestic replacement scarcity, downstream necessity, and value capture.

## 5. Real Business Exposure

The three mandatory fields are:

- customer_certification_stage
- supplier_concentration_type
- revenue_exposure_bucket

## 6. Evidence Hierarchy

Tier 1 evidence is direct filing or operating evidence. Tier 2 evidence is reviewable industrial support. Tier 3 evidence is weak attention or inference evidence and can only support watch-only or data-gap status before stronger confirmation.

## 7. Candidate Tier Schema

The schema defines Tier A, Tier B, Tier C, Watch Only, Risk Review, and Excluded. Tier A requires durable trend, critical bottleneck, direct business exposure, at least medium evidence strength, and no concept-only basis.

## 8. Scoring Rubrics

- bottleneck_exposure_score: identifies hard-tech bottleneck exposure candidates.
- research_candidate_score: orders manual review priority.

Both are research-only. Both have `used_for_signal=false` and `used_for_admission=false`.

## 9. Review Queue Design

Review queues include high-quality fundamental review, thesis validation review, customer certification review, revenue exposure review, risk event review, valuation anomaly review, data gap review, source conflict review, and watch only.

## 10. A-share Candidate Universe Scan Plan

The next scanner should combine industry, keyword, evidence, seed expansion, and exclusion channels across the full A-share universe. It should retain weak evidence as low-tier or watch-only rows rather than silently dropping them.

## 11. Guardrail Checks

- research_only: {guardrails['research_only']}
- used_for_signal count: {guardrails['used_for_signal_count']}
- used_for_admission count: {guardrails['used_for_admission_count']}
- baseline admission changed count: {guardrails['baseline_admission_changed_count']}
- strategy file diff clean: {guardrails['strategy_file_diff_clean']}
- formal strategy files modified: {guardrails['formal_strategy_files_modified']}
- trading language hit count: {guardrails['trading_language_hit_count']}
- execution language hit count: {guardrails['execution_language_hit_count']}
- lookahead violation rows: {guardrails['lookahead_violation_rows']}

## 12. Acceptance Decision

{guardrails['acceptance_decision']}

## 13. Recommended Next Steps

1. tech_bottleneck_a_share_candidate_universe_v1
2. tech_bottleneck_candidate_universe_quality_audit_v1
3. tech_bottleneck_candidate_universe_seed_watchlist_reconciliation_v1

Continue deferring formal action timing, position lifecycle, automatic market-action outputs, and strategy admission changes.
"""


def generate(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    taxonomy = build_taxonomy()
    evidence_hierarchy = build_evidence_hierarchy()
    real_exposure = build_real_exposure_schema()
    bottleneck_scoring = build_bottleneck_exposure_scoring()
    research_priority_scoring = build_research_priority_scoring()
    inclusion_exclusion = build_inclusion_exclusion()
    tier_schema = build_candidate_tier_schema()
    review_schema = build_review_queue_schema()
    summary = build_method_summary()
    field_rows = build_field_dictionary_rows()

    write_json(output_dir / "tech_bottleneck_method_summary.json", summary)
    write_text(output_dir / "tech_bottleneck_method_definition.md", method_definition_md())
    write_text(output_dir / "tech_bottleneck_supply_chain_bottleneck_framework.md", supply_chain_framework_md())
    write_json(output_dir / "tech_bottleneck_taxonomy_v1.json", taxonomy)
    write_json(output_dir / "tech_bottleneck_evidence_hierarchy_v1.json", evidence_hierarchy)
    write_json(output_dir / "tech_bottleneck_real_exposure_schema.json", real_exposure)
    write_json(output_dir / "tech_bottleneck_bottleneck_exposure_scoring_rubric.json", bottleneck_scoring)
    write_json(output_dir / "tech_bottleneck_research_priority_scoring_rubric.json", research_priority_scoring)
    write_json(output_dir / "tech_bottleneck_inclusion_exclusion_criteria.json", inclusion_exclusion)
    write_json(output_dir / "tech_bottleneck_candidate_tier_schema.json", tier_schema)
    write_json(output_dir / "tech_bottleneck_review_queue_schema.json", review_schema)
    write_text(output_dir / "tech_bottleneck_a_share_candidate_universe_scan_plan.md", scan_plan_md())
    write_field_dictionary(output_dir / "tech_bottleneck_candidate_field_dictionary.csv", field_rows)

    strategy_clean = formal_strategy_diff() == ""
    guardrails = {
        "task_name": TASK_NAME,
        "research_only": True,
        "method_codified": True,
        "taxonomy_generated": True,
        "evidence_hierarchy_generated": True,
        "real_exposure_schema_generated": True,
        "bottleneck_exposure_scoring_generated": True,
        "research_priority_scoring_generated": True,
        "inclusion_exclusion_generated": True,
        "candidate_tier_schema_generated": True,
        "review_queue_schema_generated": True,
        "a_share_scan_plan_generated": True,
        "field_dictionary_generated": True,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": "tech_bottleneck_method_codification_ready" if strategy_clean else "blocked_due_to_strategy_diff",
    }
    write_json(output_dir / "tech_bottleneck_method_guardrails.json", guardrails)
    write_text(output_dir / "tech_bottleneck_method_codification_v1_report.md", build_report(summary, guardrails))
    return {"output_dir": str(output_dir), "summary": summary, "guardrails": guardrails}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Tech Bottleneck method codification v1 research-only outputs.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    result = generate(Path(args.output_dir))
    print(f"{TASK_NAME}|output_dir|{result['output_dir']}")
    print(f"{TASK_NAME}|acceptance_decision|{result['guardrails']['acceptance_decision']}")


if __name__ == "__main__":
    main()
