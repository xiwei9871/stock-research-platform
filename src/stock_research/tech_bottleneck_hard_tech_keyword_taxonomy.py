from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_hard_tech_keyword_taxonomy_v1"
REVIEW_UNIVERSE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_quality_reassessment_v1/review_universe_quality_reassessment.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

POLICY_SOURCE_KEYWORDS: list[dict[str, Any]] = [
    {
        "source_name": "2025政府工作报告/未来产业口径",
        "source_url": "https://m.12371.gov.cn/content/2025-03/12/content_486480.html",
        "keywords": ["人工智能", "量子科技", "生物制造", "具身智能", "6G", "商业航天", "低空经济", "深海科技"],
    },
    {
        "source_name": "工信部等七部门未来产业创新发展实施意见",
        "source_url": "https://zwgk.mct.gov.cn/zfxxgkml/kjjy/202401/t20240131_951102.html",
        "keywords": [
            "人形机器人",
            "脑机接口",
            "量子信息",
            "6G",
            "卫星互联网",
            "算力基础设施",
            "工业互联网",
            "物联网",
            "车联网",
            "千兆光网",
        ],
    },
    {
        "source_name": "科创50指数说明",
        "source_url": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000688factsheet.pdf",
        "keywords": ["科创板", "科创50", "高市值", "高流动性"],
    },
]

SEED_KEYWORD_CATEGORIES: dict[str, list[str]] = {
    "high_speed_interconnect": [
        "AI PCB",
        "AIPCB",
        "高速PCB",
        "高阶PCB",
        "高频高速板",
        "高速连接器",
        "高速背板连接器",
        "铜缆高速连接",
        "高速铜缆",
        "高速线缆",
        "高速互连",
        "高速信号完整性",
        "交换机背板",
        "HDI",
        "10阶以上HDI",
        "ABF载板",
        "IC载板",
        "224Gbps",
        "AI服务器",
        "HPC",
        "GPU平台",
    ],
    "semiconductor_compute": [
        "半导体",
        "芯片",
        "集成电路",
        "CPU",
        "GPU",
        "DPU",
        "FPGA",
        "ASIC",
        "AI芯片",
        "处理器",
        "算力",
        "先进制程",
        "EDA",
        "IP核",
    ],
    "memory_and_storage": [
        "存储",
        "存储芯片",
        "DRAM",
        "NAND",
        "NOR",
        "HBM",
        "DDR",
        "DDR5",
        "内存接口",
        "固态硬盘",
        "SSD",
        "闪存",
    ],
    "semiconductor_equipment_material": [
        "半导体设备",
        "刻蚀",
        "薄膜",
        "沉积",
        "光刻",
        "涂胶显影",
        "离子注入",
        "清洗",
        "检测设备",
        "量测",
        "探针台",
        "封装",
        "先进封装",
        "电子特气",
        "光刻胶",
        "靶材",
        "CMP",
        "抛光液",
        "硅片",
    ],
    "optical_and_network": [
        "光模块",
        "光通信",
        "光互联",
        "光芯片",
        "光器件",
        "光收发",
        "收发模块",
        "CPO",
        "硅光",
        "相干光",
        "800G",
        "1.6T",
        "5G",
        "6G",
        "卫星互联网",
    ],
    "power_and_grid": ["IGBT", "SiC", "碳化硅", "氮化镓", "GaN", "功率器件", "电源管理", "特高压", "智能电网", "储能", "新型储能", "氢能"],
    "high_end_equipment_robotics": ["工业母机", "数控", "高端装备", "机器人", "人形机器人", "伺服", "减速器", "控制器", "机器视觉", "激光"],
    "instrument_sensor": ["科学仪器", "高端仪器", "传感器", "红外", "雷达", "计量", "检测", "质谱", "色谱", "示波器"],
    "industrial_software": ["工业软件", "基础软件", "操作系统", "数据库", "CAE", "CAD", "CAM", "MES", "PLC", "工控"],
    "advanced_materials": ["新材料", "电子化学品", "稀土", "磁材", "高端磁性", "陶瓷", "碳纤维", "膜材料", "合金", "复合材料"],
    "aerospace_biotech_future": ["航空", "航天", "商业航天", "低空经济", "北斗", "卫星", "生物制造", "脑机接口", "量子", "量子信息"],
}

LOW_VALUE_KEYWORDS = ["贸易", "经销", "代理", "渠道", "组装", "代工", "消费电子"]


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _keyword_catalog() -> pd.DataFrame:
    source_map: dict[str, set[str]] = defaultdict(set)
    category_map: dict[str, set[str]] = defaultdict(set)
    url_map: dict[str, set[str]] = defaultdict(set)
    for category, keywords in SEED_KEYWORD_CATEGORIES.items():
        for keyword in keywords:
            source_map[keyword].add("curated_seed")
            category_map[keyword].add(category)
    for source in POLICY_SOURCE_KEYWORDS:
        for keyword in source["keywords"]:
            source_map[keyword].add("policy_seed")
            category_map[keyword].add("policy_future_industry")
            url_map[keyword].add(source["source_url"])
    rows = []
    for keyword in sorted(source_map):
        rows.append(
            {
                "keyword": keyword,
                "keyword_category": "|".join(sorted(category_map[keyword])),
                "source_types": "|".join(sorted(source_map[keyword])),
                "source_urls": "|".join(sorted(url_map[keyword])),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def _load_star50_from_akshare() -> pd.DataFrame:
    try:
        import akshare as ak

        frame = ak.index_stock_cons(symbol="000688")
    except Exception:
        return pd.DataFrame()
    if frame.empty:
        return pd.DataFrame()
    result = frame.rename(columns={"品种代码": "stock_code", "品种名称": "stock_name", "纳入日期": "included_date"}).copy()
    result["stock_code"] = result["stock_code"].map(_stock_code)
    return result[[column for column in ["stock_code", "stock_name", "included_date"] if column in result.columns]]


def _load_market_profile(codes: list[str], *, service: str) -> pd.DataFrame:
    if not codes:
        return pd.DataFrame(columns=["stock_code", "db_industry", "db_concept_tags", "business_text"])
    asset_ids = []
    for code in codes:
        exchange = "SH" if code.startswith(("6", "9")) else "BJ" if code.startswith(("8", "4")) else "SZ"
        asset_ids.append(f"CN:{exchange}:{code}")
    with connect(service) as conn:
        industry = fetch_all(
            conn,
            """
            SELECT a.symbol AS stock_code, string_agg(DISTINCT i.industry_name, '/' ORDER BY i.industry_name) AS db_industry
            FROM core.asset_master a
            LEFT JOIN core.industry_membership i ON a.asset_id = i.asset_id
            WHERE a.asset_id = ANY(%s)
            GROUP BY a.symbol
            """,
            [asset_ids],
        )
        concepts = fetch_all(
            conn,
            """
            SELECT a.symbol AS stock_code, string_agg(DISTINCT c.concept_name, '/' ORDER BY c.concept_name) AS db_concept_tags
            FROM core.asset_master a
            LEFT JOIN core.concept_membership c ON a.asset_id = c.asset_id
            WHERE a.asset_id = ANY(%s)
            GROUP BY a.symbol
            """,
            [asset_ids],
        )
        business = fetch_all(
            conn,
            """
            SELECT a.symbol AS stock_code, string_agg(DISTINCT b.item_name, '/' ORDER BY b.item_name) AS business_text
            FROM core.asset_master a
            LEFT JOIN finance.main_business_composition b ON a.asset_id = b.asset_id
            WHERE a.asset_id = ANY(%s)
            GROUP BY a.symbol
            """,
            [asset_ids],
        )
    result = pd.DataFrame({"stock_code": codes})
    for frame in [pd.DataFrame(industry), pd.DataFrame(concepts), pd.DataFrame(business)]:
        if not frame.empty:
            frame["stock_code"] = frame["stock_code"].map(_stock_code)
            result = result.merge(frame, on="stock_code", how="left")
    return result.fillna("")


def _star50_constituents(path: Path | None, review_universe: pd.DataFrame, *, service: str) -> tuple[pd.DataFrame, str]:
    if path:
        frame = _read_csv(path)
        source = "file"
    else:
        frame = _load_star50_from_akshare()
        source = "akshare_index_stock_cons_000688" if not frame.empty else "unavailable"
    if frame.empty:
        frame = review_universe[
            review_universe.get("concept_tags", pd.Series("", index=review_universe.index)).astype(str).str.contains("科创", na=False)
            | review_universe.get("stock_code", pd.Series("", index=review_universe.index)).astype(str).str.startswith("688")
        ][["stock_code", "stock_name"]].head(50)
        source = "review_universe_star_market_fallback"
    frame = frame.copy()
    frame["stock_code"] = frame["stock_code"].map(_stock_code)
    profile = _load_market_profile(frame["stock_code"].tolist(), service=service)
    frame = frame.merge(profile, on="stock_code", how="left").fillna("")
    frame["star50_source"] = source
    return frame, source


def _combined_text(row: pd.Series) -> str:
    columns = [
        "industry",
        "db_industry",
        "concept_tags",
        "db_concept_tags",
        "business_text",
        "top_product_name",
        "strongest_primary_source_claim",
        "weakest_or_riskiest_claim",
        "evidence_summary_for_review",
    ]
    return " / ".join(str(row.get(column) or "") for column in columns)


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    upper = text.upper()
    return [keyword for keyword in keywords if keyword.upper() in upper]


def _stock_keyword_audit(review_universe: pd.DataFrame, star50: pd.DataFrame, taxonomy: pd.DataFrame) -> pd.DataFrame:
    keywords = taxonomy["keyword"].astype(str).tolist()
    star50_codes = set(star50["stock_code"].astype(str)) if not star50.empty else set()
    rows = []
    for _, row in review_universe.iterrows():
        text = _combined_text(row)
        hits = _keyword_hits(text, keywords)
        low_value_hits = _keyword_hits(text, LOW_VALUE_KEYWORDS)
        rows.append(
            {
                "stock_code": _stock_code(row.get("stock_code")),
                "stock_name": row.get("stock_name", ""),
                "in_star50_sample": _stock_code(row.get("stock_code")) in star50_codes,
                "matched_keyword_count": len(hits),
                "matched_keywords": "|".join(hits),
                "low_value_keyword_hits": "|".join(low_value_hits),
                "quality_reassessment_tier": row.get("quality_reassessment_tier", ""),
                "bottleneck_confidence_score": row.get("bottleneck_confidence_score", ""),
                "evidence_quality_score": row.get("evidence_quality_score", ""),
                "evidence_count": row.get("evidence_count", ""),
                "page_citation_count": row.get("page_citation_count", ""),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def _keyword_source_audit(taxonomy: pd.DataFrame, star50: pd.DataFrame, review_universe: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for source in POLICY_SOURCE_KEYWORDS:
        for keyword in source["keywords"]:
            rows.append(
                {
                    "source_type": "policy_seed",
                    "source_name": source["source_name"],
                    "source_url": source["source_url"],
                    "stock_code": "",
                    "stock_name": "",
                    "keyword": keyword,
                    "research_only": True,
                }
            )
    keywords = taxonomy["keyword"].astype(str).tolist()
    for _, row in star50.iterrows():
        text = _combined_text(row)
        for keyword in _keyword_hits(text, keywords):
            rows.append(
                {
                    "source_type": "star50_constituent",
                    "source_name": row.get("star50_source", "star50"),
                    "source_url": "",
                    "stock_code": _stock_code(row.get("stock_code")),
                    "stock_name": row.get("stock_name", ""),
                    "keyword": keyword,
                    "research_only": True,
                }
            )
    for _, row in review_universe.iterrows():
        text = _combined_text(row)
        for keyword in _keyword_hits(text, keywords):
            rows.append(
                {
                    "source_type": "review_universe",
                    "source_name": "tech_bottleneck_review_universe",
                    "source_url": "",
                    "stock_code": _stock_code(row.get("stock_code")),
                    "stock_name": row.get("stock_name", ""),
                    "keyword": keyword,
                    "research_only": True,
                }
            )
    return pd.DataFrame(rows)


def _missing_keyword_candidates(stock_hits: pd.DataFrame) -> pd.DataFrame:
    frame = stock_hits.copy()
    frame["bottleneck_confidence_score"] = pd.to_numeric(frame["bottleneck_confidence_score"], errors="coerce").fillna(0)
    frame["evidence_quality_score"] = pd.to_numeric(frame["evidence_quality_score"], errors="coerce").fillna(0)
    mask = (
        frame["matched_keyword_count"].eq(0)
        & (frame["bottleneck_confidence_score"].ge(75) | frame["evidence_quality_score"].ge(60))
    )
    result = frame[mask].copy()
    if result.empty:
        return pd.DataFrame(columns=frame.columns)
    return result.sort_values(["bottleneck_confidence_score", "evidence_quality_score"], ascending=False)


def _report(summary: dict[str, Any]) -> str:
    return f"""# {TASK_NAME}

## Summary

- review universe: {summary['review_universe_count']}
- star50 constituents: {summary['star50_constituent_count']} ({summary['star50_source']})
- keyword count: {summary['keyword_count']}
- stock keyword hit rows: {summary['stock_keyword_hit_rows']}
- missing keyword candidates: {summary['missing_keyword_candidate_count']}

## Guardrails

- research-only: true
- quality reassessment performed: false
- frozen quality pool generated: false
- used_for_signal/admission: 0 / 0
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## Next

Use this taxonomy as an audited input for `tech_bottleneck_review_universe_quality_reassessment_v2`.
"""


def run(
    *,
    review_universe_path: Path = REVIEW_UNIVERSE,
    star50_constituents_path: Path | None = None,
    output_dir: Path = OUTPUT_DIR,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    review_universe = _read_csv(review_universe_path)
    if review_universe.empty:
        raise FileNotFoundError(f"missing or empty review universe: {review_universe_path}")
    taxonomy = _keyword_catalog()
    star50, star50_source = _star50_constituents(star50_constituents_path, review_universe, service=service)
    stock_hits = _stock_keyword_audit(review_universe, star50, taxonomy)
    source_audit = _keyword_source_audit(taxonomy, star50, review_universe)
    missing = _missing_keyword_candidates(stock_hits)
    strategy_clean = _strategy_diff_clean()

    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_count": int(len(review_universe)),
        "star50_constituent_count": int(len(star50)),
        "star50_source": star50_source,
        "keyword_count": int(len(taxonomy)),
        "stock_keyword_hit_rows": int(len(stock_hits)),
        "source_audit_rows": int(len(source_audit)),
        "missing_keyword_candidate_count": int(len(missing)),
        "quality_reassessment_performed": False,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "acceptance_decision": "hard_tech_keyword_taxonomy_ready" if strategy_clean else "blocked_due_to_guardrail_violation",
    }
    guardrails = {
        "task_name": TASK_NAME,
        "research_only": True,
        "quality_reassessment_performed": False,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": strategy_clean,
        "acceptance_decision": summary["acceptance_decision"],
    }

    taxonomy.to_csv(output_dir / "hard_tech_keyword_taxonomy.csv", index=False)
    star50.to_csv(output_dir / "star50_keyword_seed_sample.csv", index=False)
    stock_hits.to_csv(output_dir / "stock_keyword_hit_audit.csv", index=False)
    source_audit.to_csv(output_dir / "keyword_source_audit.csv", index=False)
    missing.to_csv(output_dir / "missing_keyword_candidates.csv", index=False)
    _write_json(output_dir / "hard_tech_keyword_taxonomy_summary.json", summary)
    _write_json(output_dir / "hard_tech_keyword_taxonomy_guardrails.json", guardrails)
    (output_dir / "tech_bottleneck_hard_tech_keyword_taxonomy_v1_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=TASK_NAME)
    parser.add_argument("--review-universe-path", type=Path, default=REVIEW_UNIVERSE)
    parser.add_argument("--star50-constituents-path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)
    run(
        review_universe_path=args.review_universe_path,
        star50_constituents_path=args.star50_constituents_path,
        output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
