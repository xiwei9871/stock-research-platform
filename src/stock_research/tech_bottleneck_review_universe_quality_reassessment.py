from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.tech_bottleneck_hard_tech_keyword_taxonomy import POLICY_SOURCE_KEYWORDS, SEED_KEYWORD_CATEGORIES


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_review_universe_quality_reassessment_v1"
FRONTEND_DATASET = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
    "tech_bottleneck_review_universe_frontend_dataset.csv"
)
REPORT_EVIDENCE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_report_pdf_targeted_docling_fallback_v1/"
    "review_universe_report_evidence_for_reassessment.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

HARD_TECH_KEYWORDS = sorted(
    set().union(*SEED_KEYWORD_CATEGORIES.values(), *(source["keywords"] for source in POLICY_SOURCE_KEYWORDS))
)

LOW_VALUE_KEYWORDS = ["贸易", "经销", "代理", "组装", "代工", "渠道", "软件服务", "消费电子"]
CONCEPT_POLLUTION_KEYWORDS = ["概念", "主题", "元宇宙", "网红", "传媒", "游戏", "营销"]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if math.isnan(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _contains_any(text: str, keywords: list[str]) -> bool:
    upper = text.upper()
    return any(keyword.upper() in upper for keyword in keywords)


def _count_keywords(text: str, keywords: list[str]) -> int:
    upper = text.upper()
    return sum(1 for keyword in keywords if keyword.upper() in upper)


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _as_percent(value: Any) -> float:
    number = _to_float(value)
    if 0 < abs(number) <= 1.5:
        return number * 100
    return number


def _asset_id_for_code(code: str) -> str:
    if code.startswith(("6", "9")):
        exchange = "SH"
    elif code.startswith(("8", "4")):
        exchange = "BJ"
    else:
        exchange = "SZ"
    return f"CN:{exchange}:{code}"


def _load_market_profile_from_db(
    codes: list[str],
    *,
    as_of_date: str,
    service: str,
) -> dict[str, pd.DataFrame]:
    asset_ids = [_asset_id_for_code(code) for code in codes]
    with connect(service) as conn:
        company = fetch_all(
            conn,
            """
            SELECT symbol AS stock_code, asset_id, name, region, exchange, board
            FROM core.asset_master
            WHERE asset_id = ANY(%s)
            """,
            [asset_ids],
        )
        industry = fetch_all(
            conn,
            """
            SELECT DISTINCT ON (asset_id)
                   asset_id,
                   industry_name AS db_industry
            FROM core.industry_membership
            WHERE asset_id = ANY(%s)
              AND start_date <= %s::date
              AND (end_date IS NULL OR end_date >= %s::date)
            ORDER BY asset_id, level DESC, start_date DESC
            """,
            [asset_ids, as_of_date, as_of_date],
        )
        concepts = fetch_all(
            conn,
            """
            SELECT asset_id,
                   string_agg(DISTINCT concept_name, '/' ORDER BY concept_name) AS db_concept_tags
            FROM core.concept_membership
            WHERE asset_id = ANY(%s)
              AND start_date <= %s::date
              AND (end_date IS NULL OR end_date >= %s::date)
            GROUP BY asset_id
            """,
            [asset_ids, as_of_date, as_of_date],
        )
        income = fetch_all(
            conn,
            """
            WITH latest AS (
                SELECT DISTINCT ON (asset_id)
                       asset_id,
                       report_period::text AS latest_report_period,
                       announcement_date::text AS income_announcement_date,
                       revenue AS latest_revenue,
                       np_parent AS latest_np_parent
                FROM finance.income_statement
                WHERE asset_id = ANY(%s)
                  AND announcement_date <= %s::date
                  AND (revenue IS NOT NULL OR np_parent IS NOT NULL)
                ORDER BY asset_id, report_period DESC, announcement_date DESC
            )
            SELECT * FROM latest
            """,
            [asset_ids, as_of_date],
        )
        indicator = fetch_all(
            conn,
            """
            SELECT DISTINCT ON (asset_id)
                   asset_id,
                   report_period::text AS indicator_report_period,
                   roe,
                   gross_margin,
                   debt_ratio,
                   ocf_to_np
            FROM finance.indicator_quarter
            WHERE asset_id = ANY(%s)
              AND announcement_date <= %s::date
            ORDER BY asset_id, announcement_date DESC, report_period DESC
            """,
            [asset_ids, as_of_date],
        )
        cash = fetch_all(
            conn,
            """
            SELECT DISTINCT ON (asset_id)
                   asset_id,
                   report_period::text AS cash_flow_report_period,
                   net_operate_cash_flow
            FROM finance.cash_flow
            WHERE asset_id = ANY(%s)
              AND announcement_date <= %s::date
            ORDER BY asset_id, announcement_date DESC, report_period DESC
            """,
            [asset_ids, as_of_date],
        )
        business = fetch_all(
            conn,
            """
            WITH latest_period AS (
                SELECT asset_id, max(report_period) AS report_period
                FROM finance.main_business_composition
                WHERE asset_id = ANY(%s)
                GROUP BY asset_id
            )
            SELECT b.asset_id,
                   b.report_period::text AS business_report_period,
                   b.classify_type,
                   b.item_name,
                   b.revenue,
                   b.revenue_ratio,
                   b.gross_margin
            FROM finance.main_business_composition b
            JOIN latest_period p
              ON b.asset_id = p.asset_id
             AND b.report_period = p.report_period
            ORDER BY b.asset_id, b.classify_type, b.revenue DESC NULLS LAST, b.item_name
            """,
            [asset_ids],
        )
    company_df = pd.DataFrame(company)
    if company_df.empty:
        company_df = pd.DataFrame({"stock_code": codes, "asset_id": [_asset_id_for_code(code) for code in codes]})
    company_df["stock_code"] = company_df["stock_code"].map(_stock_code)
    industry_df = pd.DataFrame(industry)
    concepts_df = pd.DataFrame(concepts)
    financial = company_df[["stock_code", "asset_id"]].copy()
    for frame in [industry_df, concepts_df, pd.DataFrame(income), pd.DataFrame(indicator), pd.DataFrame(cash)]:
        if not frame.empty:
            financial = financial.merge(frame, on="asset_id", how="left")
    company_full = company_df.merge(industry_df, on="asset_id", how="left") if not industry_df.empty else company_df.assign(db_industry="")
    company_full = company_full.merge(concepts_df, on="asset_id", how="left") if not concepts_df.empty else company_full.assign(db_concept_tags="")
    business_summary = _summarize_business(pd.DataFrame(business), company_df[["stock_code", "asset_id"]])
    return {
        "company": company_full.fillna(""),
        "concepts": company_full[["stock_code", "db_concept_tags"]].fillna(""),
        "financial": financial.drop(columns=["asset_id"], errors="ignore").fillna(""),
        "business": business_summary.fillna(""),
    }


def _summarize_business(business: pd.DataFrame, code_map: pd.DataFrame) -> pd.DataFrame:
    if business.empty:
        return pd.DataFrame(
            {
                "stock_code": code_map["stock_code"],
                "business_report_period": "",
                "top_product_name": "",
                "top_product_revenue_ratio": "",
                "top_product_gross_margin": "",
                "hard_tech_product_hit_count": 0,
                "product_item_count": 0,
            }
        )
    rows: list[dict[str, Any]] = []
    merged = business.merge(code_map, on="asset_id", how="left")
    for code, group in merged.groupby("stock_code"):
        product = group[group["classify_type"].astype(str).str.contains("产品", na=False)].copy()
        if product.empty:
            product = group.copy()
        product = product.sort_values("revenue", ascending=False, na_position="last")
        top = product.iloc[0] if not product.empty else {}
        product_text = " ".join(product["item_name"].fillna("").astype(str).tolist())
        rows.append(
            {
                "stock_code": _stock_code(code),
                "business_report_period": str(top.get("business_report_period") or top.get("report_period") or ""),
                "top_product_name": str(top.get("item_name") or ""),
                "top_product_revenue_ratio": _as_percent(top.get("revenue_ratio")),
                "top_product_gross_margin": _as_percent(top.get("gross_margin")),
                "hard_tech_product_hit_count": _count_keywords(product_text, HARD_TECH_KEYWORDS),
                "product_item_count": int(len(product)),
            }
        )
    result = pd.DataFrame(rows)
    return code_map[["stock_code"]].merge(result, on="stock_code", how="left")


def _evidence_score(row: pd.Series, report_count: int) -> float:
    score = 0.45 * _to_float(row.get("bottleneck_confidence_score"), 50) + 0.35 * _to_float(row.get("evidence_quality_score"), 40)
    score += min(8, _to_float(row.get("page_citation_count")) / 4)
    score += min(5, report_count / 8)
    if _truthy(row.get("primary_source_supported")):
        score += 7
    if str(row.get("evidence_strength")).lower() in {"strong", "充分"}:
        score += 5
    return _clip(score)


def _business_alignment_score(row: pd.Series) -> float:
    text = " / ".join(
        str(row.get(column) or "")
        for column in [
            "industry",
            "db_industry",
            "concept_tags",
            "db_concept_tags",
            "top_product_name",
            "strongest_primary_source_claim",
            "evidence_summary_for_review",
        ]
    )
    score = 35 + min(35, _count_keywords(text, HARD_TECH_KEYWORDS) * 6)
    top_ratio = _to_float(row.get("top_product_revenue_ratio"))
    top_gm = _to_float(row.get("top_product_gross_margin"))
    hard_hits = _to_float(row.get("hard_tech_product_hit_count"))
    if top_ratio >= 50 and hard_hits:
        score += 15
    elif top_ratio >= 30 and hard_hits:
        score += 8
    if top_gm >= 35:
        score += 10
    elif top_gm >= 20:
        score += 5
    if _contains_any(text, LOW_VALUE_KEYWORDS):
        score -= 15
    return _clip(score)


def _financial_quality_score(row: pd.Series) -> float:
    gross_margin = _as_percent(row.get("gross_margin"))
    roe = _as_percent(row.get("roe"))
    debt_ratio = _as_percent(row.get("debt_ratio"))
    ocf_to_np = _to_float(row.get("ocf_to_np"))
    top_gm = _to_float(row.get("top_product_gross_margin"))
    score = 35
    gm_anchor = max(gross_margin, top_gm)
    if gm_anchor >= 45:
        score += 25
    elif gm_anchor >= 30:
        score += 18
    elif gm_anchor >= 20:
        score += 10
    elif gm_anchor and gm_anchor < 12:
        score -= 15
    if roe >= 12:
        score += 15
    elif roe >= 6:
        score += 8
    elif roe and roe < 2:
        score -= 8
    if ocf_to_np >= 0.8:
        score += 10
    elif ocf_to_np < 0:
        score -= 8
    if debt_ratio >= 75:
        score -= 12
    elif debt_ratio >= 65:
        score -= 6
    elif debt_ratio and debt_ratio <= 45:
        score += 5
    return _clip(score)


def _risk_penalty(row: pd.Series) -> float:
    penalty = 0.0
    concept_risk = str(row.get("concept_pollution_risk") or "").lower()
    route_risk = str(row.get("route_around_or_substitution_risk") or "").lower()
    value_risk = str(row.get("value_capture_risk") or "").lower()
    weak_claim = str(row.get("weakest_or_riskiest_claim") or "")
    business_text = " / ".join(
        str(row.get(column) or "") for column in ["concept_tags", "db_concept_tags", "top_product_name"]
    )
    risk_text = " / ".join([concept_risk, route_risk, value_risk, weak_claim, business_text])
    if concept_risk in {"high", "高风险"} or route_risk in {"high", "高风险"}:
        penalty += 12
    if concept_risk in {"medium", "中风险"} or route_risk in {"medium", "中风险"}:
        penalty += 5
    if value_risk in {"weak", "unclear", "high"}:
        penalty += 5
    if concept_risk == "high" or _contains_any(weak_claim, CONCEPT_POLLUTION_KEYWORDS):
        penalty += 10
    if _contains_any(business_text, LOW_VALUE_KEYWORDS):
        penalty += 10
    if not str(row.get("top_product_name") or "").strip():
        penalty += 6
    return min(35, penalty)


def _tier(row: pd.Series) -> tuple[str, str, str]:
    score = _to_float(row.get("overall_quality_score"))
    evidence = _to_float(row.get("evidence_chain_score"))
    business = _to_float(row.get("business_alignment_score"))
    financial = _to_float(row.get("financial_quality_score"))
    penalty = _to_float(row.get("risk_penalty"))
    if score >= 78 and evidence >= 70 and business >= 70 and financial >= 55 and penalty <= 16:
        return (
            "tier_1_core_review_priority",
            "keep_or_priority_manual_review",
            "证据链、主营硬科技匹配和经营质量同时较强，优先人工复核是否保留为高质量层。",
        )
    if score >= 65 and evidence >= 60 and business >= 58:
        return (
            "tier_2_strong_review_candidate",
            "manual_review_keep_or_hold",
            "证据和主营方向较强，但经营质量、替代风险或价值捕获仍需人工确认。",
        )
    if score >= 48:
        return (
            "tier_3_quality_or_value_capture_gap",
            "hold_or_need_more_evidence",
            "卡脖子 thesis 有一定基础，但主营占比、毛利、现金流、替代路径或概念污染存在缺口。",
        )
    return (
        "tier_4_downgrade_or_reject_review",
        "downgrade_or_reject_review",
        "证据、主营硬科技相关性或经营质量不足，优先复核是否降级或剔除。",
    )


def _merge_inputs(dataset: pd.DataFrame, report_evidence: pd.DataFrame, market_profile: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base = dataset.copy()
    report_counts = report_evidence.groupby("stock_code").size().rename("broker_report_evidence_count").reset_index() if not report_evidence.empty else pd.DataFrame(columns=["stock_code", "broker_report_evidence_count"])
    page_counts = report_evidence[report_evidence.get("citation_granularity", pd.Series(dtype=str)).eq("page_level")].groupby("stock_code").size().rename("broker_report_page_citation_count").reset_index() if not report_evidence.empty and "citation_granularity" in report_evidence.columns else pd.DataFrame(columns=["stock_code", "broker_report_page_citation_count"])
    for frame in [report_counts, page_counts]:
        base = base.merge(frame, on="stock_code", how="left")
    for key in ["company", "concepts", "financial", "business"]:
        frame = market_profile.get(key, pd.DataFrame())
        if not frame.empty:
            frame = frame.copy()
            frame["stock_code"] = frame["stock_code"].map(_stock_code)
            base = base.merge(frame, on="stock_code", how="left", suffixes=("", f"_{key}"))
    return base.fillna("")


def _score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        report_count = int(_to_float(row.get("broker_report_evidence_count")))
        evidence_score = _evidence_score(row, report_count)
        business_score = _business_alignment_score(row)
        financial_score = _financial_quality_score(row)
        penalty = _risk_penalty(row)
        overall = _clip(0.38 * evidence_score + 0.30 * business_score + 0.24 * financial_score + 8 - penalty)
        output = row.to_dict()
        output.update(
            {
                "evidence_chain_score": round(evidence_score, 1),
                "business_alignment_score": round(business_score, 1),
                "financial_quality_score": round(financial_score, 1),
                "risk_penalty": round(penalty, 1),
                "overall_quality_score": round(overall, 1),
            }
        )
        tier, action, reason = _tier(pd.Series(output))
        output.update(
            {
                "quality_reassessment_tier": tier,
                "recommended_review_action": action,
                "quality_reassessment_reason": reason,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "auto_added_to_quality_pool": False,
            }
        )
        rows.append(output)
    return pd.DataFrame(rows)


def _build_business_snapshot(scored: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "stock_code",
        "stock_name",
        "region",
        "industry",
        "db_industry",
        "concept_tags",
        "db_concept_tags",
        "business_report_period",
        "top_product_name",
        "top_product_revenue_ratio",
        "top_product_gross_margin",
        "hard_tech_product_hit_count",
        "latest_report_period",
        "latest_revenue",
        "latest_np_parent",
        "net_operate_cash_flow",
        "roe",
        "gross_margin",
        "debt_ratio",
        "ocf_to_np",
        "financial_quality_score",
        "business_alignment_score",
    ]
    for column in columns:
        if column not in scored.columns:
            scored[column] = ""
    return scored[columns].copy()


def _summary(
    scored: pd.DataFrame,
    *,
    expected_count: int,
    strategy_clean: bool,
) -> dict[str, Any]:
    tier_counts = scored["quality_reassessment_tier"].value_counts().to_dict()
    region_gap = int(scored.get("region", pd.Series([""] * len(scored))).astype(str).str.len().eq(0).sum())
    concept_gap = int(scored.get("db_concept_tags", pd.Series([""] * len(scored))).astype(str).str.len().eq(0).sum())
    industry_gap = int(scored.get("db_industry", pd.Series([""] * len(scored))).astype(str).str.len().eq(0).sum())
    business_gap = int(scored.get("top_product_name", pd.Series([""] * len(scored))).astype(str).str.len().eq(0).sum())
    used_for_signal = int(scored["used_for_signal"].map(_truthy).sum())
    used_for_admission = int(scored["used_for_admission"].map(_truthy).sum())
    blocking = (
        len(scored) != expected_count
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_total_count": int(len(scored)),
        "tier_1_core_review_priority_count": int(tier_counts.get("tier_1_core_review_priority", 0)),
        "tier_2_strong_review_candidate_count": int(tier_counts.get("tier_2_strong_review_candidate", 0)),
        "tier_3_quality_or_value_capture_gap_count": int(tier_counts.get("tier_3_quality_or_value_capture_gap", 0)),
        "tier_4_downgrade_or_reject_review_count": int(tier_counts.get("tier_4_downgrade_or_reject_review", 0)),
        "market_profile_region_gap_count": region_gap,
        "market_profile_concept_gap_count": concept_gap,
        "market_profile_industry_gap_count": industry_gap,
        "business_composition_gap_count": business_gap,
        "reassessment_performed": True,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": "blocked_due_to_guardrail_violation" if blocking else "review_universe_quality_reassessment_ready",
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_total_count": summary["review_universe_total_count"],
        "reassessment_performed": True,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "acceptance_decision": summary["acceptance_decision"],
    }


def _write_report(output: Path, summary: dict[str, Any]) -> None:
    text = f"""# {TASK_NAME}

## Summary

- review universe: {summary['review_universe_total_count']}
- tier 1: {summary['tier_1_core_review_priority_count']}
- tier 2: {summary['tier_2_strong_review_candidate_count']}
- tier 3: {summary['tier_3_quality_or_value_capture_gap_count']}
- tier 4: {summary['tier_4_downgrade_or_reject_review_count']}
- region/concept/industry gaps: {summary['market_profile_region_gap_count']} / {summary['market_profile_concept_gap_count']} / {summary['market_profile_industry_gap_count']}
- business composition gaps: {summary['business_composition_gap_count']}

## Guardrails

- research-only: true
- reassessment performed: true
- frozen quality pool generated: false
- auto added to quality pool: 0
- used_for_signal/admission: 0 / 0
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## Acceptance

{summary['acceptance_decision']}
"""
    (output / "tech_bottleneck_review_universe_quality_reassessment_v1_report.md").write_text(text, encoding="utf-8")


def run(
    *,
    frontend_dataset_path: Path = FRONTEND_DATASET,
    report_evidence_path: Path = REPORT_EVIDENCE,
    output_dir: Path = OUTPUT_DIR,
    as_of_date: str = "2026-07-09",
    service: str = SETTINGS.research_service,
    market_profile: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    dataset = _read_csv(Path(frontend_dataset_path))
    report_evidence = _read_csv(Path(report_evidence_path)) if Path(report_evidence_path).exists() else pd.DataFrame()
    codes = dataset["stock_code"].astype(str).map(_stock_code).tolist()
    profile = market_profile or _load_market_profile_from_db(codes, as_of_date=as_of_date, service=service)
    merged = _merge_inputs(dataset, report_evidence, profile)
    scored = _score_frame(merged)
    business_snapshot = _build_business_snapshot(scored)
    score_breakdown = scored[
        [
            "stock_code",
            "stock_name",
            "evidence_chain_score",
            "business_alignment_score",
            "financial_quality_score",
            "risk_penalty",
            "overall_quality_score",
            "quality_reassessment_tier",
            "recommended_review_action",
            "quality_reassessment_reason",
        ]
    ].copy()
    tier_buckets = (
        scored.groupby("quality_reassessment_tier", as_index=False)
        .agg(stock_count=("stock_code", "count"), avg_overall_quality_score=("overall_quality_score", "mean"))
        .sort_values("quality_reassessment_tier")
    )
    strategy_clean = _strategy_diff_clean()
    summary = _summary(
        scored,
        expected_count=len(dataset),
        strategy_clean=strategy_clean,
    )
    guardrails = _guardrails(summary)

    scored.to_csv(output / "review_universe_quality_reassessment.csv", index=False)
    score_breakdown.to_csv(output / "review_universe_quality_score_breakdown.csv", index=False)
    business_snapshot.to_csv(output / "review_universe_business_quality_snapshot.csv", index=False)
    tier_buckets.to_csv(output / "review_universe_reassessment_tier_buckets.csv", index=False)
    _write_json(output / "review_universe_quality_reassessment_summary.json", summary)
    _write_json(output / "review_universe_quality_reassessment_guardrails.json", guardrails)
    _write_report(output, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reassess the current tech bottleneck review universe with evidence and business quality."
    )
    parser.add_argument("--frontend-dataset-path", type=Path, default=FRONTEND_DATASET)
    parser.add_argument("--report-evidence-path", type=Path, default=REPORT_EVIDENCE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--as-of-date", default="2026-07-09")
    parser.add_argument("--service", default=SETTINGS.research_service)
    args = parser.parse_args(argv)
    summary = run(
        frontend_dataset_path=args.frontend_dataset_path,
        report_evidence_path=args.report_evidence_path,
        output_dir=args.output_dir,
        as_of_date=args.as_of_date,
        service=args.service,
    )
    print(f"{TASK_NAME}|acceptance_decision|{summary['acceptance_decision']}")
    print(f"{TASK_NAME}|review_universe_total_count|{summary['review_universe_total_count']}")
    print(f"{TASK_NAME}|tier_1|{summary['tier_1_core_review_priority_count']}")
    print(f"{TASK_NAME}|tier_2|{summary['tier_2_strong_review_candidate_count']}")
    print(f"{TASK_NAME}|tier_3|{summary['tier_3_quality_or_value_capture_gap_count']}")
    print(f"{TASK_NAME}|tier_4|{summary['tier_4_downgrade_or_reject_review_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
