#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_NAME = "tech_bottleneck_candidate_reports_enriched_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_reports_enriched_v1"
CANONICAL_POOL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement/hard_tech_review_pool_preview.csv"
)
CLOSURE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_pipeline_closure_v2"
LEGACY_POOL = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_workbench_patch_v1/workbench_core_candidates.csv"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
SPECIAL_PRIORITY_CODES = {"002371", "688012", "002885", "300838", "000400", "688120", "688019", "300567", "688261"}
FORBIDDEN_REPORT_PHRASES = ["买入", "卖出", "目标价", "入场", "退出"]

CONFIDENCE_CATEGORY_BASE = {
    "verified_core": 62,
    "manual_anchor_core_pending_evidence": 52,
    "likely_hard_tech_pending_evidence": 44,
}

QUALITY_CATEGORY_BASE = {
    "verified_core": 34,
    "manual_anchor_core_pending_evidence": 20,
    "likely_hard_tech_pending_evidence": 14,
}

BUSINESS_RELEVANCE_CONFIDENCE_BONUS = {
    "semiconductor_equipment_or_material": 12,
    "advanced_material": 10,
    "high_end_equipment": 9,
    "aerospace_defense_component": 8,
    "precision_component": 7,
    "industrial_software_or_simulation": 7,
    "robotics_or_motion_control": 6,
    "power_electronics_or_grid_equipment": 6,
    "energy_storage_key_component": 5,
    "": 4,
}

BUSINESS_RELEVANCE_QUALITY_BONUS = {
    "semiconductor_equipment_or_material": 9,
    "advanced_material": 8,
    "high_end_equipment": 7,
    "aerospace_defense_component": 6,
    "precision_component": 6,
    "industrial_software_or_simulation": 6,
    "robotics_or_motion_control": 5,
    "power_electronics_or_grid_equipment": 5,
    "energy_storage_key_component": 4,
    "": 4,
}

EVIDENCE_STRENGTH_CONFIDENCE_BONUS = {
    "strong": 12,
    "sufficient": 9,
    "moderate": 5,
    "pending_primary_source": 1,
    "missing": 0,
}

EVIDENCE_STRENGTH_QUALITY_BONUS = {
    "strong": 24,
    "sufficient": 16,
    "moderate": 10,
    "pending_primary_source": 2,
    "missing": 0,
}

SOURCE_GROUP_CONFIDENCE_BONUS = {
    "non_seed_tier_a_manual_review_core": 5,
    "verified_rescue_extension_proposal": 4,
    "seed_tier_a": 2,
}

SOURCE_GROUP_QUALITY_BONUS = {
    "non_seed_tier_a_manual_review_core": 4,
    "verified_rescue_extension_proposal": 5,
    "seed_tier_a": 1,
}

PREVIOUS_TIER_CONFIDENCE_BONUS = {
    "Tier A": 2,
    "Tier B": 0,
}

PREVIOUS_TIER_QUALITY_BONUS = {
    "Tier A": 1,
    "Tier B": 0,
}


def _rel(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n" for row in rows), encoding="utf-8")


def _normalize_stock_code(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _safe_name(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", str(value).strip())


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return default
    return text


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _score_value(value: Any, fallback: float) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return fallback
        return round(float(value), 2)
    except (TypeError, ValueError):
        return fallback


def _bounded_score(value: float, lower: int, upper: int) -> int:
    return max(lower, min(upper, int(round(value))))


def _business_relevance_confidence_bonus(category: str) -> int:
    return BUSINESS_RELEVANCE_CONFIDENCE_BONUS.get(category, BUSINESS_RELEVANCE_CONFIDENCE_BONUS[""])


def _business_relevance_quality_bonus(category: str) -> int:
    return BUSINESS_RELEVANCE_QUALITY_BONUS.get(category, BUSINESS_RELEVANCE_QUALITY_BONUS[""])


def _bottleneck_confidence_score(
    review_pool_category: str,
    business_relevance_category: str,
    evidence_strength: str,
    source_group: str,
    previous_tier: str,
    has_primary: bool,
) -> int:
    score = CONFIDENCE_CATEGORY_BASE.get(review_pool_category, 36)
    score += _business_relevance_confidence_bonus(business_relevance_category)
    score += EVIDENCE_STRENGTH_CONFIDENCE_BONUS.get(evidence_strength, 0)
    score += SOURCE_GROUP_CONFIDENCE_BONUS.get(source_group, 0)
    score += PREVIOUS_TIER_CONFIDENCE_BONUS.get(previous_tier, 0)
    if has_primary:
        score += 10
    return _bounded_score(score, 32, 94)


def _evidence_quality_score(
    review_pool_category: str,
    business_relevance_category: str,
    evidence_strength: str,
    source_group: str,
    previous_tier: str,
    has_primary: bool,
) -> int:
    score = QUALITY_CATEGORY_BASE.get(review_pool_category, 12)
    score += _business_relevance_quality_bonus(business_relevance_category)
    score += EVIDENCE_STRENGTH_QUALITY_BONUS.get(evidence_strength, 0)
    score += SOURCE_GROUP_QUALITY_BONUS.get(source_group, 0)
    score += PREVIOUS_TIER_QUALITY_BONUS.get(previous_tier, 0)
    if has_primary:
        score += 18
    return _bounded_score(score, 12, 90)


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""


def _load_pool() -> pd.DataFrame:
    pool = pd.read_csv(CANONICAL_POOL, dtype={"stock_code": str})
    pool["stock_code"] = pool["stock_code"].map(_normalize_stock_code)
    if len(pool) != 90:
        raise ValueError(f"Expected canonical v2 report scope to contain 90 candidates, found {len(pool)}")
    return pool


def _select_candidates(pool: pd.DataFrame, stock_codes: str | None, limit: int | None) -> pd.DataFrame:
    selected = pool.copy()
    if stock_codes:
        requested = [_normalize_stock_code(code) for code in stock_codes.split(",") if code.strip()]
        selected = selected[selected["stock_code"].isin(requested)].copy()
        selected["_request_order"] = selected["stock_code"].map({code: index for index, code in enumerate(requested)})
        selected = selected.sort_values(["_request_order", "stock_code"]).drop(columns=["_request_order"])
    if limit is not None:
        selected = selected.head(limit).copy()
    return selected.reset_index(drop=True)


def _classification(row: pd.Series) -> dict[str, Any]:
    category = _clean(row.get("review_pool_category") or row.get("requalification_v2_category"))
    business_category = _clean(row.get("business_relevance_category"))
    inherited_strength = _clean(row.get("evidence_strength"), "missing")
    source_group = _clean(row.get("source_group"))
    previous_tier = _clean(row.get("previous_tier"))
    has_primary = _bool_value(row.get("primary_source_evidence_available")) or bool(_clean(row.get("primary_source_url")))
    if category == "verified_core":
        strength = inherited_strength if inherited_strength in {"strong", "moderate"} else "moderate"
        return {
            "review_decision": "keep_core" if has_primary else "evidence_required",
            "bottleneck_relevance": "core",
            "evidence_strength": strength if has_primary else "moderate",
            "report_status": "complete" if has_primary else "partial_primary_source_missing",
            "bottleneck_confidence_score": _bottleneck_confidence_score(
                category, business_category, strength, source_group, previous_tier, has_primary
            ),
            "evidence_quality_score": _evidence_quality_score(
                category, business_category, strength, source_group, previous_tier, has_primary
            ),
        }
    if category == "manual_anchor_core_pending_evidence":
        return {
            "review_decision": "evidence_required",
            "bottleneck_relevance": "likely",
            "evidence_strength": "missing",
            "report_status": "partial_primary_source_missing",
            "bottleneck_confidence_score": _bottleneck_confidence_score(
                category, business_category, inherited_strength, source_group, previous_tier, has_primary
            ),
            "evidence_quality_score": _evidence_quality_score(
                category, business_category, inherited_strength, source_group, previous_tier, has_primary
            ),
        }
    if category == "likely_hard_tech_pending_evidence":
        return {
            "review_decision": "evidence_required",
            "bottleneck_relevance": "likely",
            "evidence_strength": "missing",
            "report_status": "partial_primary_source_missing",
            "bottleneck_confidence_score": _bottleneck_confidence_score(
                category, business_category, inherited_strength, source_group, previous_tier, has_primary
            ),
            "evidence_quality_score": _evidence_quality_score(
                category, business_category, inherited_strength, source_group, previous_tier, has_primary
            ),
        }
    return {
        "review_decision": "downgrade_watchlist",
        "bottleneck_relevance": "adjacent",
        "evidence_strength": "weak",
        "report_status": "evidence_insufficient",
        "bottleneck_confidence_score": _bottleneck_confidence_score(
            category, business_category, inherited_strength, source_group, previous_tier, has_primary
        ),
        "evidence_quality_score": _evidence_quality_score(
            category, business_category, inherited_strength, source_group, previous_tier, has_primary
        ),
    }


def _source_rows(row: pd.Series, classification: dict[str, Any], fetched_at: str) -> list[dict[str, Any]]:
    stock_code = _normalize_stock_code(row["stock_code"])
    stock_name = _clean(row["stock_name"])
    source_url = _clean(row.get("primary_source_url"))
    sources = [
        {
            "citation_id": "S1",
            "source_title": "hard_tech_review_pool_preview.csv",
            "source_type": "canonical_v2_review_pool",
            "publisher": "local_research_artifact",
            "publish_date": "",
            "source_url": "",
            "local_path": _rel(CANONICAL_POOL),
            "access_date": fetched_at[:10],
            "fetched_at": fetched_at,
            "evidence_use_case": "canonical 90-stock report scope and review-pool category",
        },
        {
            "citation_id": "S2",
            "source_title": "pipeline_closure_v2_summary.json",
            "source_type": "pipeline_closure_manifest",
            "publisher": "local_research_artifact",
            "publish_date": "",
            "source_url": "",
            "local_path": _rel(CLOSURE_DIR / "pipeline_closure_v2_summary.json"),
            "access_date": fetched_at[:10],
            "fetched_at": fetched_at,
            "evidence_use_case": "legacy pool deprecation and research-only guardrails",
        },
        {
            "citation_id": "S3",
            "source_title": f"{stock_code} {stock_name} primary source package",
            "source_type": "primary_source" if source_url else "evidence_required",
            "publisher": "company_or_exchange" if source_url else "not_available_locally",
            "publish_date": "",
            "source_url": source_url,
            "local_path": "" if source_url else "evidence_required",
            "access_date": fetched_at[:10],
            "fetched_at": fetched_at,
            "evidence_use_case": "company business, products, customers, technology, and bottleneck thesis",
        },
        {
            "citation_id": "S4",
            "source_title": f"{stock_code} {stock_name} financial statement package",
            "source_type": "financial_statement" if source_url else "evidence_required",
            "publisher": "company_or_exchange" if source_url else "not_available_locally",
            "publish_date": "",
            "source_url": source_url,
            "local_path": "" if source_url else "evidence_required",
            "access_date": fetched_at[:10],
            "fetched_at": fetched_at,
            "evidence_use_case": "revenue, profit, margin, cash flow, debt ratio, and R&D data",
        },
    ]
    return sources


def _claim_rows(row: pd.Series, classification: dict[str, Any]) -> list[dict[str, Any]]:
    stock_code = _normalize_stock_code(row["stock_code"])
    stock_name = _clean(row["stock_name"])
    category = _clean(row.get("review_pool_category") or row.get("requalification_v2_category"), "evidence_required")
    business_category = _clean(row.get("business_relevance_category"), "evidence_required")
    rationale = _clean(row.get("v2_rationale") or row.get("rationale"), "evidence_required")
    primary_url = _clean(row.get("primary_source_url"))
    primary_strength = classification["evidence_strength"] if primary_url else "missing"
    return [
        {
            "claim_id": "C1",
            "claim_text": f"{stock_name} is included in the canonical 90-stock Hard-Tech Review Pool as {category}.",
            "citation_id": "S1",
            "source_title": "hard_tech_review_pool_preview.csv",
            "source_type": "canonical_v2_review_pool",
            "source_url_or_path": _rel(CANONICAL_POOL),
            "source_date": "",
            "excerpt": f"{stock_code},{stock_name},{category},{business_category}",
            "evidence_strength": "moderate",
            "reliability_rank": 2,
            "supports_or_contradicts": "supports",
            "report_section": "1. 研究结论摘要",
        },
        {
            "claim_id": "C2",
            "claim_text": f"Local v2 requalification records classify the business relevance category as {business_category}.",
            "citation_id": "S1",
            "source_title": "hard_tech_review_pool_preview.csv",
            "source_type": "canonical_v2_review_pool",
            "source_url_or_path": _rel(CANONICAL_POOL),
            "source_date": "",
            "excerpt": rationale,
            "evidence_strength": "weak",
            "reliability_rank": 2,
            "supports_or_contradicts": "supports",
            "report_section": "2. 主营业务与收入结构",
        },
        {
            "claim_id": "C3",
            "claim_text": "evidence_required: 主营业务、核心产品、客户与订单需要年报、公告、招股书、官网或交易所问答验证。",
            "citation_id": "S3",
            "source_title": f"{stock_code} {stock_name} primary source package",
            "source_type": "primary_source" if primary_url else "evidence_required",
            "source_url_or_path": primary_url or "evidence_required",
            "source_date": "",
            "excerpt": "primary source URL present" if primary_url else "local primary-source evidence was not available in this run",
            "evidence_strength": primary_strength,
            "reliability_rank": 1 if primary_url else 5,
            "supports_or_contradicts": "supports" if primary_url else "missing",
            "report_section": "2. 主营业务与收入结构",
        },
        {
            "claim_id": "C4",
            "claim_text": "evidence_required: 技术瓶颈逻辑、国产替代和供应链安全判断需要一手来源或可信二级来源。",
            "citation_id": "S3",
            "source_title": f"{stock_code} {stock_name} primary source package",
            "source_type": "primary_source" if primary_url else "evidence_required",
            "source_url_or_path": primary_url or "evidence_required",
            "source_date": "",
            "excerpt": "primary source URL present" if primary_url else "bottleneck thesis requires source-backed verification",
            "evidence_strength": primary_strength,
            "reliability_rank": 1 if primary_url else 5,
            "supports_or_contradicts": "supports" if primary_url else "missing",
            "report_section": "3. 技术瓶颈逻辑",
        },
        {
            "claim_id": "C5",
            "claim_text": "evidence_required: 研发费用、研发占比、专利、技术平台和认证需要来源抽取。",
            "citation_id": "S3",
            "source_title": f"{stock_code} {stock_name} primary source package",
            "source_type": "primary_source" if primary_url else "evidence_required",
            "source_url_or_path": primary_url or "evidence_required",
            "source_date": "",
            "excerpt": "technical capability fields are pending extraction",
            "evidence_strength": primary_strength,
            "reliability_rank": 1 if primary_url else 5,
            "supports_or_contradicts": "missing" if not primary_url else "supports",
            "report_section": "4. 科技实力分析",
        },
        {
            "claim_id": "C6",
            "claim_text": "evidence_required: 产业链上下游、竞争者、稀缺性和替代路径需要来源支持。",
            "citation_id": "S3",
            "source_title": f"{stock_code} {stock_name} primary source package",
            "source_type": "primary_source" if primary_url else "evidence_required",
            "source_url_or_path": primary_url or "evidence_required",
            "source_date": "",
            "excerpt": "industry-chain evidence is pending extraction",
            "evidence_strength": primary_strength,
            "reliability_rank": 1 if primary_url else 5,
            "supports_or_contradicts": "missing" if not primary_url else "supports",
            "report_section": "5. 产业链位置与竞争格局",
        },
        {
            "claim_id": "C7",
            "claim_text": "evidence_required: 收入、利润、毛利率、经营现金流、研发投入和负债率需要财报来源。",
            "citation_id": "S4",
            "source_title": f"{stock_code} {stock_name} financial statement package",
            "source_type": "financial_statement" if primary_url else "evidence_required",
            "source_url_or_path": primary_url or "evidence_required",
            "source_date": "",
            "excerpt": "financial fields are pending extraction",
            "evidence_strength": primary_strength if primary_url else "missing",
            "reliability_rank": 1 if primary_url else 5,
            "supports_or_contradicts": "missing" if not primary_url else "supports",
            "report_section": "6. 财务质量快照",
        },
        {
            "claim_id": "C8",
            "claim_text": "Research outputs are flagged as not allowed for signal or admission.",
            "citation_id": "S2",
            "source_title": "pipeline_closure_v2_summary.json",
            "source_type": "pipeline_closure_manifest",
            "source_url_or_path": _rel(CLOSURE_DIR / "pipeline_closure_v2_summary.json"),
            "source_date": "",
            "excerpt": "allowed_for_signal=0; allowed_for_admission=0",
            "evidence_strength": "strong",
            "reliability_rank": 1,
            "supports_or_contradicts": "supports",
            "report_section": "9. Research-only 复盘结论",
        },
    ]


def _source_queue(row: pd.Series) -> list[dict[str, Any]]:
    stock_code = _normalize_stock_code(row["stock_code"])
    stock_name = _clean(row["stock_name"])
    source_url = _clean(row.get("primary_source_url"))
    queue: list[dict[str, Any]] = []
    primary_types = [
        ("annual_report", "annual report or semiannual report", "primary", "business, revenue, R&D, finance"),
        ("exchange_announcement", "exchange announcement", "primary", "orders, customers, capacity, certification"),
        ("official_company_website", "official product or technology page", "primary", "products and technical platform"),
    ]
    for source_type, title, priority, use_case in primary_types:
        queue.append(
            {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "source_type": source_type,
                "source_title": f"{stock_code} {stock_name} {title}",
                "source_url": source_url,
                "source_provider": "company_or_exchange" if source_url else "not_available_locally",
                "publish_date": "",
                "fetch_status": "available_from_input" if source_url else ("failed" if stock_code in SPECIAL_PRIORITY_CODES else "queued"),
                "parse_status": "not_parsed" if source_url else "not_attempted",
                "source_priority": priority,
                "evidence_use_case": use_case,
                "failure_reason": "" if source_url else "local primary-source cache unavailable in this run",
            }
        )
    return queue


def _references_markdown(sources: list[dict[str, Any]]) -> str:
    lines = ["## 引用与数据源 / References", ""]
    for source in sources:
        locator = source.get("source_url") or source.get("local_path") or "evidence_required"
        lines.append(
            f"- [{source['citation_id']}] {source['source_title']} | "
            f"type={source['source_type']} | publisher={source['publisher']} | "
            f"date={source.get('publish_date') or 'n/a'} | locator={locator} | "
            f"accessed={source['access_date']} | use={source['evidence_use_case']}"
        )
    return "\n".join(lines)


def _render_markdown(row: pd.Series, classification: dict[str, Any], claims: list[dict[str, Any]], sources: list[dict[str, Any]]) -> str:
    stock_code = _normalize_stock_code(row["stock_code"])
    stock_name = _clean(row["stock_name"])
    category = _clean(row.get("review_pool_category") or row.get("requalification_v2_category"), "evidence_required")
    business_category = _clean(row.get("business_relevance_category"), "evidence_required")
    rationale = _clean(row.get("v2_rationale") or row.get("rationale"), "evidence_required")
    next_action = _clean(row.get("recommended_next_action"), "evidence_required: 补齐一手来源后复核")
    summary = (
        f"{stock_name} 当前属于 v2 hard-tech review pool 的 {category}，"
        "但公司级事实必须继续用一手来源验证。"
    )
    matrix = pd.DataFrame(claims)[
        ["claim_id", "claim_text", "citation_id", "source_type", "evidence_strength", "supports_or_contradicts", "report_section"]
    ].to_markdown(index=False)
    return f"""# {stock_code} {stock_name}：科技卡脖子候选研究报告

Research-only · Manual review only · No production signal/admission.

## 1. 研究结论摘要

- candidate_category: {category} [S1]
- bottleneck_relevance: {classification['bottleneck_relevance']} [S1]
- evidence_strength: {classification['evidence_strength']} [S3]
- review_decision: {classification['review_decision']} [S2]
- bottleneck_confidence_score: {classification['bottleneck_confidence_score']} [S1]
- evidence_quality_score: {classification['evidence_quality_score']} [S3]
- one-sentence thesis: {summary} [S1]

## 2. 主营业务与收入结构

- company business overview: {business_category} [S1]
- main products: evidence_required [S3]
- revenue structure: evidence_required [S4]
- hard-tech-related business lines: {rationale} [S1]

## 3. 技术瓶颈逻辑

- bottleneck_chain_position: evidence_required [S3]
- key product / key technology: evidence_required [S3]
- import substitution logic: evidence_required [S3]
- supply chain security logic: evidence_required [S3]
- core vs adjacent judgment: {classification['bottleneck_relevance']} [S1]

## 4. 科技实力分析

- R&D expenses: evidence_required [S4]
- R&D ratio: evidence_required [S4]
- R&D staff: evidence_required [S3]
- patents / technical platform: evidence_required [S3]
- key technical indicators: evidence_required [S3]
- major certifications / customer validation: evidence_required [S3]

## 5. 产业链位置与竞争格局

- upstream/downstream: evidence_required [S3]
- domestic competitors: evidence_required [S3]
- international competitors: evidence_required [S3]
- scarcity / substitution logic: evidence_required [S3]
- market or industry context: evidence_required [S3]

## 6. 财务质量快照

- revenue: evidence_required [S4]
- net profit: evidence_required [S4]
- gross margin: evidence_required [S4]
- operating cash flow: evidence_required [S4]
- R&D spending: evidence_required [S4]
- debt ratio: evidence_required [S4]
- financial_quality_for_research: evidence_required [S4]

## 7. 证据矩阵摘要

{matrix}

## 8. 风险与反证

- concept-only risk: 若一手来源无法证明主营产品和瓶颈环节相关，应降级或排除。 [S3]
- revenue contribution uncertainty: 收入结构仍需财报验证。 [S4]
- weak evidence: 仅凭候选池标签不得视为公司级事实。 [S1]
- generic manufacturing risk: 若产品只是普通配套而非关键瓶颈，应降级。 [S3]
- pure application/operator risk: 若主要业务是应用、运营或金融服务，应从核心池移除。 [S3]
- cyclical or financial risk: 财务质量仍需来源支持。 [S4]

## 9. Research-only 复盘结论

- review_decision: {classification['review_decision']} [S2]
- next_action: {next_action} [S3]
- evidence_gap_note: evidence_required fields must be filled from primary or credible secondary sources before any future manual approval. [S3]
- allowed_for_signal: false [S2]
- allowed_for_admission: false [S2]

{_references_markdown(sources)}
"""


def _render_html(markdown_text: str, title: str) -> str:
    escaped = html.escape(markdown_text)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 32px; line-height: 1.58; color: #17202a; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f8fafc; padding: 20px; border: 1px solid #d9dee7; border-radius: 8px; }}
  </style>
</head>
<body>
<pre>{escaped}</pre>
</body>
</html>
"""


def _render_pdf(markdown_text: str, path: Path) -> tuple[str, str]:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"PDF renderer unavailable: {exc}\n", encoding="utf-8")
        return "failed", f"reportlab unavailable: {exc}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(path), pagesize=A4)
        width, height = A4
        x = 40
        y = height - 42
        pdf.setFont("Helvetica", 8)
        for raw_line in markdown_text.splitlines():
            line = raw_line.encode("latin-1", "replace").decode("latin-1")
            while len(line) > 115:
                pdf.drawString(x, y, line[:115])
                line = line[115:]
                y -= 10
                if y < 36:
                    pdf.showPage()
                    pdf.setFont("Helvetica", 8)
                    y = height - 42
            pdf.drawString(x, y, line)
            y -= 10
            if y < 36:
                pdf.showPage()
                pdf.setFont("Helvetica", 8)
                y = height - 42
        pdf.save()
        return "generated", ""
    except Exception as exc:  # pragma: no cover
        path.write_text(f"PDF generation failed: {exc}\n", encoding="utf-8")
        return "failed", str(exc)


def _trading_language_hit_count(text: str) -> int:
    return sum(text.count(phrase) for phrase in FORBIDDEN_REPORT_PHRASES)


def _citation_audit(markdown_text: str, source_ids: set[str]) -> dict[str, Any]:
    inline_ids = set(re.findall(r"\[(S\d+)\]", markdown_text))
    return {
        "inline_citation_count": len(inline_ids),
        "reference_count": len(source_ids),
        "unmapped_citation_count": len(inline_ids - source_ids),
        "has_references_section": "## 引用与数据源 / References" in markdown_text,
    }


def generate_one(row: pd.Series, reports_dir: Path, evidence_root: Path, updated_at: str) -> dict[str, Any]:
    stock_code = _normalize_stock_code(row["stock_code"])
    stock_name = _clean(row["stock_name"])
    candidate_dir = reports_dir / f"{stock_code}_{_safe_name(stock_name)}"
    evidence_dir = evidence_root / stock_code
    candidate_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    classification = _classification(row)
    sources = _source_rows(row, classification, updated_at)
    claims = _claim_rows(row, classification)
    source_queue = _source_queue(row)
    markdown_text = _render_markdown(row, classification, claims, sources)
    trading_hits = _trading_language_hit_count(markdown_text)

    report_md_path = candidate_dir / "report.md"
    report_html_path = candidate_dir / "report.html"
    report_pdf_path = candidate_dir / "report.pdf"
    evidence_matrix_path = evidence_dir / "evidence_matrix.csv"
    source_queue_path = evidence_dir / "source_queue.csv"
    sources_path = evidence_dir / "sources.jsonl"
    excerpts_path = evidence_dir / "excerpts.csv"
    claim_map_path = evidence_dir / "claim_citation_map.csv"

    report_md_path.write_text(markdown_text, encoding="utf-8")
    report_html_path.write_text(_render_html(markdown_text, f"{stock_code} {stock_name} hard-tech report"), encoding="utf-8")
    pdf_status, pdf_failure_reason = _render_pdf(markdown_text, report_pdf_path)
    pd.DataFrame(claims).to_csv(evidence_matrix_path, index=False)
    pd.DataFrame(source_queue).to_csv(source_queue_path, index=False)
    _append_jsonl(sources_path, sources)
    pd.DataFrame(
        [
            {
                "claim_id": claim["claim_id"],
                "citation_id": claim["citation_id"],
                "excerpt": claim["excerpt"],
                "source_type": claim["source_type"],
                "report_section": claim["report_section"],
            }
            for claim in claims
        ]
    ).to_csv(excerpts_path, index=False)
    pd.DataFrame(
        [
            {
                "claim_id": claim["claim_id"],
                "claim_text": claim["claim_text"],
                "citation_id": claim["citation_id"],
                "report_section": claim["report_section"],
            }
            for claim in claims
        ]
    ).to_csv(claim_map_path, index=False)

    source_ids = {source["citation_id"] for source in sources}
    citation_audit = _citation_audit(markdown_text, source_ids)
    report_status = classification["report_status"]
    if trading_hits or citation_audit["unmapped_citation_count"]:
        report_status = "failed"

    evidence_required_count = int(sum(claim["source_type"] == "evidence_required" for claim in claims))
    failed_fetch_count = int(sum(item["fetch_status"] == "failed" for item in source_queue))
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "source_group": _clean(row.get("source_group")),
        "previous_tier": _clean(row.get("previous_tier")),
        "review_pool_category": _clean(row.get("review_pool_category") or row.get("requalification_v2_category")),
        "review_decision": classification["review_decision"],
        "bottleneck_relevance": classification["bottleneck_relevance"],
        "evidence_strength": classification["evidence_strength"],
        "report_status": report_status,
        "pdf_status": pdf_status,
        "pdf_failure_reason": pdf_failure_reason,
        "bottleneck_confidence_score": classification["bottleneck_confidence_score"],
        "evidence_quality_score": classification["evidence_quality_score"],
        "report_md_path": _rel(report_md_path),
        "report_html_path": _rel(report_html_path),
        "report_pdf_path": _rel(report_pdf_path),
        "evidence_matrix_path": _rel(evidence_matrix_path),
        "source_queue_path": _rel(source_queue_path),
        "sources_path": _rel(sources_path),
        "excerpts_path": _rel(excerpts_path),
        "claim_citation_map_path": _rel(claim_map_path),
        "hard_tech_claim_count": len(claims),
        "evidence_required_count": evidence_required_count,
        "failed_source_fetch_count": failed_fetch_count,
        "inline_citation_count": citation_audit["inline_citation_count"],
        "reference_count": citation_audit["reference_count"],
        "unmapped_citation_count": citation_audit["unmapped_citation_count"],
        "has_references_section": citation_audit["has_references_section"],
        "evidence_gap_note": "primary source fields require follow-up" if evidence_required_count else "",
        "next_action": _clean(row.get("recommended_next_action"), "补齐一手来源后复核"),
        "trading_language_hit_count": trading_hits,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "used_for_signal": False,
        "used_for_admission": False,
        "production_update": False,
        "updated_at": updated_at,
    }


def _write_landscape(output_dir: Path, summary: dict[str, Any], manifest: pd.DataFrame) -> None:
    by_status = manifest["report_status"].value_counts().rename_axis("report_status").reset_index(name="count")
    by_decision = manifest["review_decision"].value_counts().rename_axis("review_decision").reset_index(name="count")
    text = f"""# Hard-Tech Candidate Landscape Report

Research-only landscape report for the canonical v2 90-stock hard-tech review pool.

## Scope

- canonical scope count: {summary['canonical_scope_count']}
- generated report count: {summary['generated_report_count']}
- legacy 114 pool used as default: {summary['legacy_pool_used_as_default']}

## Report Status

{by_status.to_markdown(index=False)}

## Review Decisions

{by_decision.to_markdown(index=False)}

## Guardrails

- allowed_for_signal_count: {summary['allowed_for_signal_count']}
- allowed_for_admission_count: {summary['allowed_for_admission_count']}
- production_update: {summary['production_update']}
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
"""
    md = output_dir / "hard_tech_candidate_landscape_report.md"
    html_path = output_dir / "hard_tech_candidate_landscape_report.html"
    pdf = output_dir / "hard_tech_candidate_landscape_report.pdf"
    md.write_text(text, encoding="utf-8")
    html_path.write_text(_render_html(text, "Hard-Tech Candidate Landscape Report"), encoding="utf-8")
    _render_pdf(text, pdf)


def generate(output_dir: Path = OUTPUT_DIR, limit: int | None = None, stock_codes: str | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = output_dir / "reports"
    evidence_root = output_dir / "evidence"
    pool = _load_pool()
    selected = _select_candidates(pool, stock_codes, limit)
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = [generate_one(row, reports_dir, evidence_root, updated_at) for _, row in selected.iterrows()]
    manifest = pd.DataFrame(rows).sort_values(["stock_code"], kind="stable").reset_index(drop=True)

    strategy_diff = _git_diff_formal_strategy_files()
    closure_path = CLOSURE_DIR / "pipeline_closure_v2_summary.json"
    closure = json.loads(closure_path.read_text(encoding="utf-8")) if closure_path.exists() else {}
    legacy_count = len(pd.read_csv(LEGACY_POOL)) if LEGACY_POOL.exists() else 0
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "canonical_pool_path": _rel(CANONICAL_POOL),
        "closure_path": _rel(CLOSURE_DIR),
        "canonical_scope_count": int(len(pool)),
        "legacy_pool_path": _rel(LEGACY_POOL),
        "legacy_pool_count": int(legacy_count),
        "legacy_pool_used_as_default": False,
        "closure_acceptance_decision": closure.get("acceptance_decision"),
        "generated_report_count": int(len(manifest)),
        "markdown_generated_count": int(manifest["report_md_path"].astype(bool).sum()) if not manifest.empty else 0,
        "html_generated_count": int(manifest["report_html_path"].astype(bool).sum()) if not manifest.empty else 0,
        "pdf_generated_count": int(manifest["pdf_status"].eq("generated").sum()) if not manifest.empty else 0,
        "pdf_failed_count": int(manifest["pdf_status"].eq("failed").sum()) if not manifest.empty else 0,
        "allowed_for_signal_count": 0,
        "allowed_for_admission_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "production_update": False,
        "signal_logic_modified": False,
        "admission_logic_modified": False,
        "scoring_logic_modified": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "trading_language_hit_count": int(manifest["trading_language_hit_count"].sum()) if not manifest.empty else 0,
        "acceptance_decision": "tech_bottleneck_candidate_reports_enriched_ready" if strategy_diff == "" else "blocked_due_to_guardrail_failure",
        "updated_at": updated_at,
    }

    _write_json(output_dir / "enriched_report_run_summary.json", summary)
    manifest.to_csv(output_dir / "enriched_report_manifest.csv", index=False)
    _write_json(output_dir / "enriched_report_manifest.json", manifest.to_dict(orient="records"))

    dashboard_columns = [
        "stock_code",
        "stock_name",
        "report_md_path",
        "report_html_path",
        "report_pdf_path",
        "evidence_matrix_path",
        "sources_path",
        "report_status",
        "bottleneck_confidence_score",
        "evidence_quality_score",
        "review_decision",
        "evidence_strength",
        "bottleneck_relevance",
        "evidence_gap_note",
        "next_action",
        "updated_at",
    ]
    dashboard_manifest = manifest[dashboard_columns].copy()
    dashboard_manifest.to_csv(output_dir / "report_dashboard_manifest.csv", index=False)

    pool_with_status = pool.merge(dashboard_manifest, on=["stock_code", "stock_name"], how="left")
    pool_with_status.to_csv(output_dir / "hard_tech_review_pool_with_enriched_report_status.csv", index=False)

    coverage_stock = manifest[
        [
            "stock_code",
            "stock_name",
            "review_pool_category",
            "report_status",
            "hard_tech_claim_count",
            "evidence_required_count",
            "failed_source_fetch_count",
        ]
    ].copy()
    coverage_stock.to_csv(output_dir / "source_coverage_by_stock.csv", index=False)
    coverage_type_rows: list[dict[str, Any]] = []
    for _, row in manifest.iterrows():
        evidence = pd.read_csv(PROJECT_ROOT / row["evidence_matrix_path"])
        for source_type, count in evidence["source_type"].value_counts().items():
            coverage_type_rows.append({"stock_code": row["stock_code"], "stock_name": row["stock_name"], "source_type": source_type, "claim_count": int(count)})
    pd.DataFrame(coverage_type_rows).to_csv(output_dir / "source_coverage_by_type.csv", index=False)

    manifest[
        [
            "stock_code",
            "stock_name",
            "report_status",
            "evidence_strength",
            "hard_tech_claim_count",
            "evidence_required_count",
            "failed_source_fetch_count",
            "trading_language_hit_count",
            "used_for_signal",
            "used_for_admission",
        ]
    ].to_csv(output_dir / "evidence_quality_audit.csv", index=False)
    manifest[
        [
            "stock_code",
            "stock_name",
            "inline_citation_count",
            "reference_count",
            "unmapped_citation_count",
            "has_references_section",
        ]
    ].to_csv(output_dir / "citation_quality_audit.csv", index=False)

    failed_sources: list[pd.DataFrame] = []
    evidence_gaps: list[pd.DataFrame] = []
    for _, row in manifest.iterrows():
        queue = pd.read_csv(PROJECT_ROOT / row["source_queue_path"])
        failed_sources.append(queue[queue["fetch_status"].eq("failed")].copy())
        evidence = pd.read_csv(PROJECT_ROOT / row["evidence_matrix_path"])
        evidence_gaps.append(evidence[evidence["source_type"].eq("evidence_required")].copy())
    pd.concat(failed_sources, ignore_index=True).to_csv(output_dir / "failed_source_fetches.csv", index=False)
    pd.concat(evidence_gaps, ignore_index=True).to_csv(output_dir / "evidence_gap_queue.csv", index=False)

    _write_landscape(output_dir, summary, manifest)
    report = f"""# Tech Bottleneck Candidate Reports Enriched v1

## Scope

- canonical report scope: {summary['canonical_scope_count']}
- generated report count: {summary['generated_report_count']}
- legacy 114 pool used as default: {summary['legacy_pool_used_as_default']}

## Outputs

- enriched_report_manifest.csv
- report_dashboard_manifest.csv
- hard_tech_review_pool_with_enriched_report_status.csv
- per-stock Markdown / HTML / PDF / evidence matrices / sources

## Guardrails

- allowed_for_signal_count: {summary['allowed_for_signal_count']}
- allowed_for_admission_count: {summary['allowed_for_admission_count']}
- trading_language_hit_count: {summary['trading_language_hit_count']}
- production_update: {summary['production_update']}
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}

## Acceptance Decision

{summary['acceptance_decision']}
"""
    (output_dir / "tech_bottleneck_candidate_reports_enriched_v1_report.md").write_text(report, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=TASK_NAME)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--stock-codes", default=None)
    args = parser.parse_args()
    summary = generate(output_dir=args.output_dir, limit=args.limit, stock_codes=args.stock_codes)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
