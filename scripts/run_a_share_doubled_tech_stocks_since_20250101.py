#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_NAME = "a_share_doubled_tech_stocks_since_20250101_v1"
START_DATE = "2025-01-01"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stocks_since_20250101_v1"
CANONICAL_HARD_TECH_POOL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_seed_tier_a_requalification_v2_review_pool_refinement/hard_tech_review_pool_preview.csv"
)
CANDIDATE_UNIVERSE = PROJECT_ROOT / "outputs/research/tech_bottleneck_a_share_candidate_universe_v1/a_share_candidate_universe.csv"
SPECIAL_CANDIDATES = {
    "胜宏科技",
    "中际旭创",
    "新易盛",
    "天孚通信",
    "寒武纪",
    "源杰科技",
    "联特科技",
    "生益电子",
    "生益科技",
    "沪电股份",
    "工业富联",
    "江波龙",
    "佰维存储",
    "德明利",
    "长川科技",
    "中科飞测",
    "精测电子",
    "北方华创",
    "中微公司",
    "华海清科",
    "安集科技",
}

REQUIRED_COLUMNS = [
    "stock_code",
    "stock_name",
    "exchange",
    "listing_date",
    "start_date_used",
    "start_close_qfq",
    "latest_date",
    "latest_close_qfq",
    "return_since_20250101",
    "max_return_since_20250101",
    "is_doubled",
    "is_ipo_after_20250101",
    "industry",
    "concept_tags",
    "tech_theme",
    "hard_tech_relevance",
    "include_decision",
    "exclusion_reason",
    "evidence_source",
    "source_url",
    "notes",
]

TECH_KEYWORDS = {
    "半导体": "semiconductor",
    "集成电路": "semiconductor",
    "芯片": "semiconductor",
    "电子元件": "electronic_component",
    "电子器件": "electronic_component",
    "电子设备": "electronic_component",
    "计算机、通信": "electronic_component",
    "电子专用材料": "semiconductor_material",
    "电子专用设备": "semiconductor_equipment",
    "光通信": "optical_communication",
    "光模块": "optical_communication",
    "光芯片": "optical_communication",
    "通信设备": "optical_communication",
    "PCB": "pcb_ai_server_component",
    "印制电路": "pcb_ai_server_component",
    "服务器": "ai_computing_hardware",
    "存储": "memory_storage",
    "先进封装": "advanced_packaging",
    "软件": "industrial_software",
    "EDA": "industrial_software",
    "工业软件": "industrial_software",
    "机器人": "robotics_motion_control",
    "伺服": "robotics_motion_control",
    "减速器": "robotics_motion_control",
    "传感器": "robotics_motion_control",
    "自动化": "industrial_automation",
    "仪器仪表": "scientific_instrument",
    "科学仪器": "scientific_instrument",
    "专用设备": "high_end_equipment",
    "电气机械": "power_electronics_or_grid_equipment",
    "电力设备": "power_electronics_or_grid_equipment",
    "新材料": "advanced_material",
    "航空": "aerospace_defense_component",
    "航天": "aerospace_defense_component",
    "国防": "aerospace_defense_component",
}

EXCLUSION_KEYWORDS = {
    "银行": "financial",
    "证券": "financial",
    "保险": "financial",
    "金融": "financial",
    "电力、热力生产和供应": "utility_operator",
    "燃气生产和供应": "utility_operator",
    "水的生产和供应": "utility_operator",
    "照明": "consumer_or_lighting",
    "商贸": "consumer_or_trading",
    "贸易": "consumer_or_trading",
    "房地产": "real_estate",
    "煤炭": "commodity_resource",
    "石油": "commodity_resource",
    "采矿": "commodity_resource",
}


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and pd.isna(value):
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _normalize_stock_code(value: Any) -> str:
    text = _clean(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _ts_code(stock_code: str, exchange: str) -> str:
    suffix = "SH" if exchange.upper() in {"SH", "SSE"} else "SZ" if exchange.upper() in {"SZ", "SZSE"} else "BJ"
    return f"{stock_code}.{suffix}"


def _exchange_label(exchange: str, board: str, stock_code: str) -> str:
    board = _clean(board)
    exchange = _clean(exchange)
    if stock_code.startswith(("83", "87", "88")) or "BSE" in board:
        return "BSE"
    if stock_code.startswith("688") or "STAR" in board:
        return "STAR"
    if stock_code.startswith("300") or "CHINEXT" in board:
        return "ChiNext"
    if exchange == "SH":
        return "SSE"
    if exchange == "SZ":
        return "SZSE"
    return exchange or "unknown"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _load_price_returns(service: str, start_date: str) -> pd.DataFrame:
    sql = """
        WITH bars AS (
            SELECT asset_id, trade_date, close::float AS close
            FROM market_daily_bar
            WHERE adjust_type = 'qfq'
              AND trade_date >= %s
              AND close IS NOT NULL
              AND close > 0
        ),
        start_rows AS (
            SELECT DISTINCT ON (asset_id)
                asset_id,
                trade_date AS start_date_used,
                close AS start_close_qfq
            FROM bars
            ORDER BY asset_id, trade_date ASC
        ),
        latest_rows AS (
            SELECT DISTINCT ON (asset_id)
                asset_id,
                trade_date AS latest_date,
                close AS latest_close_qfq
            FROM bars
            ORDER BY asset_id, trade_date DESC
        ),
        max_rows AS (
            SELECT asset_id, max(close) AS max_close_qfq
            FROM bars
            GROUP BY asset_id
        ),
        latest_industry AS (
            SELECT asset_id, industry_name
            FROM (
                SELECT
                    asset_id,
                    industry_name,
                    row_number() OVER (
                        PARTITION BY asset_id
                        ORDER BY coalesce(end_date, DATE '9999-12-31') DESC, start_date DESC NULLS LAST
                    ) AS rn
                FROM core.industry_membership
                WHERE industry_name IS NOT NULL AND industry_name <> ''
            ) ranked
            WHERE rn = 1
        )
        SELECT
            a.asset_id,
            a.symbol AS stock_code,
            a.name AS stock_name,
            a.exchange,
            a.board,
            a.list_date AS listing_date,
            coalesce(i.industry_name, '') AS industry,
            s.start_date_used,
            s.start_close_qfq,
            l.latest_date,
            l.latest_close_qfq,
            m.max_close_qfq
        FROM start_rows s
        JOIN latest_rows l ON l.asset_id = s.asset_id
        JOIN max_rows m ON m.asset_id = s.asset_id
        JOIN core.asset_master a ON a.asset_id = s.asset_id
        LEFT JOIN latest_industry i ON i.asset_id = s.asset_id
        WHERE a.is_active = true
        ORDER BY a.symbol
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [start_date])
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("No qfq daily bars found for A-share universe")
    frame["stock_code"] = frame["stock_code"].map(_normalize_stock_code)
    frame["exchange"] = frame.apply(lambda row: _exchange_label(row.get("exchange"), row.get("board"), row["stock_code"]), axis=1)
    frame["listing_date"] = pd.to_datetime(frame["listing_date"]).dt.strftime("%Y-%m-%d")
    frame["start_date_used"] = pd.to_datetime(frame["start_date_used"]).dt.strftime("%Y-%m-%d")
    frame["latest_date"] = pd.to_datetime(frame["latest_date"]).dt.strftime("%Y-%m-%d")
    frame["start_close_qfq"] = frame["start_close_qfq"].astype(float)
    frame["latest_close_qfq"] = frame["latest_close_qfq"].astype(float)
    frame["max_close_qfq"] = frame["max_close_qfq"].astype(float)
    frame["return_since_20250101"] = frame["latest_close_qfq"] / frame["start_close_qfq"] - 1.0
    frame["max_return_since_20250101"] = frame["max_close_qfq"] / frame["start_close_qfq"] - 1.0
    frame["is_doubled"] = frame["return_since_20250101"] >= 1.0
    frame["is_ipo_after_20250101"] = frame["listing_date"] > START_DATE
    return frame


def _load_hard_tech_maps() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    canonical: dict[str, dict[str, str]] = {}
    if CANONICAL_HARD_TECH_POOL.exists():
        frame = pd.read_csv(CANONICAL_HARD_TECH_POOL, dtype={"stock_code": str}).fillna("")
        frame["stock_code"] = frame["stock_code"].map(_normalize_stock_code)
        for _, row in frame.iterrows():
            canonical[row["stock_code"]] = {
                "theme": _clean(row.get("business_relevance_category") or row.get("review_pool_category"), "hard_tech_review_pool"),
                "relevance": _clean(row.get("review_pool_category"), "hard_tech_review_pool"),
                "source": "canonical_hard_tech_review_pool_v2",
                "tags": ",".join(
                    item
                    for item in [
                        _clean(row.get("source_group")),
                        _clean(row.get("previous_tier")),
                        _clean(row.get("review_pool_category")),
                        _clean(row.get("business_relevance_category")),
                    ]
                    if item
                ),
            }
    candidate_universe: dict[str, dict[str, str]] = {}
    if CANDIDATE_UNIVERSE.exists():
        frame = pd.read_csv(CANDIDATE_UNIVERSE, dtype={"stock_code": str}, low_memory=False).fillna("")
        frame["stock_code"] = frame["stock_code"].map(_normalize_stock_code)
        for _, row in frame.iterrows():
            tier = _clean(row.get("candidate_tier"))
            excluded = str(row.get("excluded_flag")).lower() == "true" or tier == "Excluded"
            candidate_universe[row["stock_code"]] = {
                "theme": _clean(row.get("tech_bottleneck_domain") or row.get("tech_bottleneck_sub_domain"), "candidate_universe"),
                "relevance": "excluded_candidate_universe" if excluded else f"candidate_universe_{tier or 'unknown'}",
                "source": "tech_bottleneck_a_share_candidate_universe_v1",
                "tags": ",".join(
                    item
                    for item in [
                        _clean(row.get("tech_bottleneck_domain")),
                        _clean(row.get("tech_bottleneck_sub_domain")),
                        _clean(row.get("supply_chain_role")),
                        tier,
                    ]
                    if item
                ),
                "excluded": "true" if excluded else "false",
            }
    return canonical, candidate_universe


def _keyword_theme(text: str) -> tuple[str, str]:
    for keyword, theme in TECH_KEYWORDS.items():
        if keyword.lower() in text.lower():
            return theme, f"keyword:{keyword}"
    return "", ""


def _exclusion_reason(stock_name: str, industry: str, tags: str) -> str:
    text = f"{stock_name} {industry} {tags}"
    for keyword, reason in EXCLUSION_KEYWORDS.items():
        if keyword in text:
            return reason
    return ""


def _classify(frame: pd.DataFrame) -> pd.DataFrame:
    canonical, candidate_universe = _load_hard_tech_maps()
    records: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        stock_code = row["stock_code"]
        stock_name = _clean(row["stock_name"])
        industry = _clean(row.get("industry"))
        canonical_hit = canonical.get(stock_code)
        candidate_hit = candidate_universe.get(stock_code)
        tags = ""
        tech_theme = ""
        hard_tech_relevance = "non_tech_or_unclassified"
        evidence_source = "industry_keyword_heuristic"
        if canonical_hit:
            tech_theme = canonical_hit["theme"]
            hard_tech_relevance = canonical_hit["relevance"]
            tags = canonical_hit["tags"]
            evidence_source = canonical_hit["source"]
        elif candidate_hit and candidate_hit.get("excluded") != "true":
            tech_theme = candidate_hit["theme"]
            hard_tech_relevance = candidate_hit["relevance"]
            tags = candidate_hit["tags"]
            evidence_source = candidate_hit["source"]
        else:
            tech_theme, hit = _keyword_theme(f"{stock_name} {industry}")
            if tech_theme:
                hard_tech_relevance = "industry_or_name_keyword_candidate"
                tags = hit
                if candidate_hit and candidate_hit.get("excluded") == "true":
                    hard_tech_relevance = "industry_keyword_candidate_universe_excluded_review_required"
                    evidence_source = "industry_keyword_heuristic;tech_bottleneck_candidate_universe_excluded"
        exclusion_reason = _exclusion_reason(stock_name, industry, tags)
        if candidate_hit and candidate_hit.get("excluded") == "true" and not canonical_hit and not tech_theme:
            exclusion_reason = exclusion_reason or "candidate_universe_excluded"
        is_tech = bool(tech_theme) and not exclusion_reason
        if row["is_doubled"] and is_tech:
            include_decision = "included_hard_tech" if canonical_hit else "included_tech_candidate"
        elif row["is_doubled"] and exclusion_reason in {"financial", "utility_operator"}:
            include_decision = "excluded_operator_financial"
        elif row["is_doubled"] and exclusion_reason:
            include_decision = "excluded_non_tech"
        elif row["is_doubled"]:
            include_decision = "excluded_non_tech"
            exclusion_reason = exclusion_reason or "no_hard_tech_evidence"
        elif is_tech:
            include_decision = "tech_not_doubled"
        else:
            include_decision = "not_doubled_non_tech"
            exclusion_reason = exclusion_reason or "not_doubled_or_no_hard_tech_evidence"
        records.append(
            {
                "concept_tags": tags,
                "tech_theme": tech_theme,
                "hard_tech_relevance": hard_tech_relevance,
                "include_decision": include_decision,
                "exclusion_reason": "" if include_decision.startswith("included") or include_decision == "tech_not_doubled" else exclusion_reason,
                "evidence_source": evidence_source,
                "source_url": "local_db:market_daily_bar(qfq);local_artifacts:tech_bottleneck_candidate_universe",
                "notes": (
                    "IPO cohort: return calculated from first qfq bar after listing/start date"
                    if row["is_ipo_after_20250101"]
                    else "return calculated from first qfq close on or after 2025-01-01"
                ),
            }
        )
    enriched = pd.concat([frame.reset_index(drop=True), pd.DataFrame(records)], axis=1)
    return enriched


def _finalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["stock_code"] = result["stock_code"].map(_normalize_stock_code)
    result = result.sort_values(["return_since_20250101", "stock_code"], ascending=[False, True], kind="stable")
    for col in ["start_close_qfq", "latest_close_qfq", "return_since_20250101", "max_return_since_20250101"]:
        result[col] = result[col].astype(float).round(6)
    return result[REQUIRED_COLUMNS]


def _summary_payload(price_audit: pd.DataFrame, doubled_tech: pd.DataFrame, all_doubled: pd.DataFrame, excluded: pd.DataFrame, ipo: pd.DataFrame) -> dict[str, Any]:
    latest_day = _clean(price_audit["latest_date"].max())
    near = price_audit[
        price_audit["include_decision"].eq("tech_not_doubled")
        & price_audit["return_since_20250101"].ge(0.8)
        & price_audit["return_since_20250101"].lt(1.0)
    ]
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "price_source": "local_db_market_daily_bar_qfq",
        "price_source_detail": "stock_research service market_daily_bar adjust_type=qfq",
        "date_range_start": START_DATE,
        "latest_trading_day": latest_day,
        "a_share_universe_count": int(price_audit["stock_code"].nunique()),
        "all_doubled_count": int(len(all_doubled)),
        "doubled_tech_count": int(len(doubled_tech)),
        "excluded_non_tech_doubled_count": int(len(excluded)),
        "ipo_after_20250101_doubled_count": int(len(ipo)),
        "tech_close_to_doubling_count": int(len(near)),
        "special_candidate_checked_count": int(price_audit["stock_name"].isin(SPECIAL_CANDIDATES).sum()),
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "production_update": False,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "acceptance_decision": "a_share_doubled_tech_stocks_since_20250101_ready",
    }


def _write_report(path: Path, summary: dict[str, Any], doubled_tech: pd.DataFrame, excluded: pd.DataFrame, near: pd.DataFrame, ipo: pd.DataFrame) -> None:
    top_cols = ["stock_code", "stock_name", "return_since_20250101", "tech_theme", "hard_tech_relevance"]
    report = f"""# A-share doubled technology stocks since 2025-01-01 v1

Research-only screen. No signal, no admission logic, no production update.

## Scope

- A-share universe count: {summary['a_share_universe_count']}
- price source: {summary['price_source_detail']}
- start date: {summary['date_range_start']}
- latest trading day: {summary['latest_trading_day']}
- adjusted close: qfq close from `market_daily_bar`

## confirmed doubled hard-tech stocks

Count: {summary['doubled_tech_count']}

{doubled_tech[top_cols].head(80).to_markdown(index=False) if not doubled_tech.empty else 'No confirmed doubled hard-tech stocks found.'}

## doubled but non-tech stocks

Count: {summary['excluded_non_tech_doubled_count']}

{excluded[['stock_code', 'stock_name', 'return_since_20250101', 'exclusion_reason']].head(80).to_markdown(index=False) if not excluded.empty else 'No doubled non-tech exclusions found.'}

## tech stocks close to doubling

Definition: hard-tech / technology classified stocks with return between 80% and 100%.

{near[top_cols].head(80).to_markdown(index=False) if not near.empty else 'No close-to-doubling tech candidates found.'}

## IPO cohort

IPO-after-2025 cohort uses the first available qfq close after listing/start date.

{ipo[top_cols + ['listing_date', 'start_date_used']].head(80).to_markdown(index=False) if not ipo.empty else 'No IPO-after-2025 doubled stocks found.'}

## Method

Return is calculated as `latest_close_qfq / start_close_qfq - 1`, where start close is the first qfq adjusted close on or after 2025-01-01. For post-2025 IPOs, the same rule naturally uses the first available qfq bar after listing.

Technology classification is research-only and uses the v2 hard-tech review pool, the A-share hard-tech candidate universe, current industry membership, and hard-tech keywords. Financial, pure operator, utility, consumer/lighting, generic resource, and no-evidence rows are excluded or listed separately.
"""
    path.write_text(report, encoding="utf-8")


def generate(output_dir: Path = OUTPUT_DIR, service: str = SETTINGS.research_service, start_date: str = START_DATE) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    returns = _load_price_returns(service, start_date)
    classified = _classify(returns)
    price_audit = _finalize_columns(classified)
    all_doubled = price_audit[price_audit["is_doubled"]].copy()
    doubled_tech = price_audit[price_audit["include_decision"].isin(["included_hard_tech", "included_tech_candidate"])].copy()
    excluded = all_doubled[all_doubled["include_decision"].isin(["excluded_non_tech", "excluded_concept_only", "excluded_operator_financial"])].copy()
    ipo = all_doubled[all_doubled["is_ipo_after_20250101"]].copy()
    near = price_audit[
        price_audit["include_decision"].eq("tech_not_doubled")
        & price_audit["return_since_20250101"].ge(0.8)
        & price_audit["return_since_20250101"].lt(1.0)
    ].copy()

    price_audit.to_csv(output_dir / "price_return_audit.csv", index=False)
    doubled_tech.to_csv(output_dir / "doubled_tech_stocks.csv", index=False)
    all_doubled.to_csv(output_dir / "all_doubled_a_share_stocks.csv", index=False)
    excluded.to_csv(output_dir / "excluded_non_tech_doubled_stocks.csv", index=False)
    ipo.to_csv(output_dir / "ipo_after_20250101_doubled_stocks.csv", index=False)

    classification_cols = [
        "stock_code",
        "stock_name",
        "industry",
        "concept_tags",
        "tech_theme",
        "hard_tech_relevance",
        "include_decision",
        "exclusion_reason",
        "evidence_source",
        "notes",
    ]
    price_audit[classification_cols].to_csv(output_dir / "tech_classification_audit.csv", index=False)
    evidence = price_audit[
        [
            "stock_code",
            "stock_name",
            "evidence_source",
            "source_url",
            "tech_theme",
            "hard_tech_relevance",
            "include_decision",
            "notes",
        ]
    ].copy()
    evidence["evidence_note"] = evidence["notes"]
    evidence.to_csv(output_dir / "source_evidence_matrix.csv", index=False)

    summary = _summary_payload(price_audit, doubled_tech, all_doubled, excluded, ipo)
    _write_json(output_dir / "doubled_tech_stocks_summary.json", summary)
    _write_report(output_dir / "a_share_doubled_tech_stocks_since_20250101_v1_report.md", summary, doubled_tech, excluded, near, ipo)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=TASK_NAME)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--service", default=SETTINGS.research_service)
    parser.add_argument("--start-date", default=START_DATE)
    args = parser.parse_args()
    summary = generate(output_dir=args.output_dir, service=args.service, start_date=args.start_date)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
