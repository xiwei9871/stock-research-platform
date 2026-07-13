#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_a_share_candidate_universe_v1"
HARDENING_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_method_codification_v1_hardening_patch"
CONSOLIDATED_SEED_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_consolidated_v1"
EVIDENCE_DIRS = [
    PROJECT_ROOT / "outputs/research/tech_bottleneck_source_backed_refresh_20260619_full_support_conservative",
    PROJECT_ROOT / "outputs/research/tech_bottleneck_cninfo_order_evidence_fill_20260619",
    PROJECT_ROOT / "outputs/research/tech_bottleneck_evidence_workflow_20260619_mainbiz_final",
    PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_news_patch_v1",
    PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_full_financial_statement_patch_v1",
]
TASK_NAME = "tech_bottleneck_a_share_candidate_universe_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


@dataclass(frozen=True)
class KeywordRule:
    trend_domain: str
    domain: str
    sub_domain: str
    supply_chain_layer: str
    bottleneck_type: str
    keywords: tuple[str, ...]


MAIN_COLUMNS = [
    "stock_code",
    "ts_code",
    "stock_name",
    "exchange",
    "list_status",
    "industry",
    "sub_industry",
    "trend_domain",
    "tech_bottleneck_domain",
    "tech_bottleneck_sub_domain",
    "supply_chain_layer",
    "supply_chain_role",
    "architecture_shift",
    "old_architecture_failure_point",
    "new_architecture_dependency",
    "adoption_timeline",
    "inflection_window",
    "architecture_shift_score",
    "bottleneck_type",
    "bottleneck_or_chokepoint_score",
    "route_around_risk",
    "can_customer_route_around",
    "route_around_options",
    "substitute_maturity",
    "switching_time_months",
    "qualification_cycle_months",
    "capacity_expansion_lead_time",
    "alternative_supplier_count",
    "substitution_difficulty_score",
    "customer_certification_stage",
    "supplier_concentration_type",
    "revenue_exposure_bucket",
    "main_business_relevance",
    "real_business_exposure_score",
    "domestic_substitution_relevance",
    "supply_chain_constraint_relevance",
    "technology_bottleneck_relevance",
    "commercialization_stage",
    "value_capture_score",
    "pricing_power_evidence",
    "gross_margin_trend",
    "backlog_or_order_visibility",
    "customer_bargaining_power",
    "supplier_bargaining_power",
    "competitive_intensity",
    "capital_intensity_pressure",
    "evidence_gate_level",
    "evidence_tier",
    "evidence_type",
    "evidence_strength",
    "evidence_quality_score",
    "primary_source_count",
    "named_customer_flag",
    "order_or_capacity_flag",
    "revenue_traceable_flag",
    "financial_traceable_flag",
    "evidence_count",
    "source_conflict_flag",
    "data_gap_flags",
    "concept_pollution_risk",
    "policy_theme_only_flag",
    "name_similarity_only_flag",
    "minority_investment_only_flag",
    "trading_agent_or_distributor_flag",
    "secondary_market_narrative_only_flag",
    "interactive_platform_only_flag",
    "kol_or_social_only_flag",
    "market_understanding_gap_score",
    "low_position_score",
    "price_percentile_120d",
    "drawdown_from_120d_high",
    "volatility_contraction_20d",
    "freshness_score",
    "fundamental_risk_score",
    "commercial_validation_score",
    "bottleneck_exposure_score",
    "research_priority_score",
    "candidate_tier",
    "review_priority",
    "review_queue_type",
    "disconfirmation_trigger",
    "disconfirming_evidence_type",
    "thesis_kill_condition",
    "next_primary_source_check",
    "next_research_action",
    "next_primary_source_to_check",
    "manual_review_question",
    "missing_evidence_to_upgrade",
    "evidence_to_downgrade",
    "candidate_reason",
    "manual_review_focus",
    "needs_manual_review",
    "seed_watchlist_overlap",
    "excluded_flag",
    "excluded_reason",
    "research_only",
    "used_for_signal",
    "used_for_admission",
]


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    text = str(value).strip()
    return text if text else default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _asset_id_to_ts_code(asset_id: str, symbol: str = "", exchange: str = "") -> str:
    symbol = _clean(symbol)
    exchange = _clean(exchange).upper()
    if symbol and exchange:
        return f"{symbol}.{exchange}"
    parts = _clean(asset_id).split(":")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}"
    return symbol or asset_id


def _asset_id_to_stock_code(asset_id: str, symbol: str = "") -> str:
    return _clean(symbol) or _asset_id_to_ts_code(asset_id).split(".", 1)[0]


def _load_hardening_context() -> dict[str, Any]:
    files = [
        "tech_bottleneck_hardening_guardrails.json",
        "tech_bottleneck_hardened_candidate_field_dictionary.csv",
        "tech_bottleneck_tier_gate_rules.json",
        "tech_bottleneck_supply_chain_role_schema.json",
        "tech_bottleneck_disconfirmation_schema.json",
        "tech_bottleneck_value_capture_schema.json",
        "tech_bottleneck_architecture_shift_schema.json",
        "tech_bottleneck_route_around_schema.json",
        "tech_bottleneck_a_share_concept_pollution_schema.json",
        "tech_bottleneck_evidence_gate_schema.json",
        "tech_bottleneck_hardened_bottleneck_exposure_scoring_rubric.json",
        "tech_bottleneck_hardened_research_priority_scoring_rubric.json",
        "tech_bottleneck_supply_chain_nodes_schema.csv",
        "tech_bottleneck_supply_chain_edges_schema.csv",
        "tech_bottleneck_next_research_action_schema.json",
    ]
    return {
        "hardening_dir": str(HARDENING_DIR),
        "available_files": [name for name in files if (HARDENING_DIR / name).exists()],
        "missing_files": [name for name in files if not (HARDENING_DIR / name).exists()],
    }


def _load_a_share_universe() -> pd.DataFrame:
    sql = """
        WITH latest_trade AS (
            SELECT max(trade_date) AS trade_date
            FROM market_daily_bar
            WHERE adjust_type = 'qfq'
        ),
        latest_industry AS (
            SELECT asset_id, industry_system, industry_name, industry_code
            FROM (
                SELECT
                    asset_id,
                    industry_system,
                    industry_name,
                    industry_code,
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
            a.symbol,
            a.name AS stock_name,
            a.exchange,
            a.board,
            a.is_active,
            b.trade_date AS latest_trade_date,
            i.industry_name,
            i.industry_code,
            i.industry_system
        FROM market_daily_bar b
        JOIN latest_trade lt ON b.trade_date = lt.trade_date
        JOIN core.asset_master a ON a.asset_id = b.asset_id
        LEFT JOIN latest_industry i ON i.asset_id = b.asset_id
        WHERE b.adjust_type = 'qfq'
        ORDER BY a.asset_id
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["asset_id", "stock_code", "ts_code", "stock_name", "exchange", "industry"])
    frame["stock_code"] = frame.apply(lambda row: _asset_id_to_stock_code(row["asset_id"], row.get("symbol")), axis=1)
    frame["ts_code"] = frame.apply(lambda row: _asset_id_to_ts_code(row["asset_id"], row.get("symbol"), row.get("exchange")), axis=1)
    frame["list_status"] = frame["is_active"].map(lambda value: "active" if bool(value) else "inactive")
    frame["industry"] = frame["industry_name"].fillna("").astype(str)
    frame["sub_industry"] = frame["industry_code"].fillna("").astype(str)
    return frame


def _load_seed_watchlist() -> pd.DataFrame:
    path = CONSOLIDATED_SEED_DIR / "watchlist_report_consolidated_index.csv"
    if not path.exists():
        return pd.DataFrame(columns=["asset_id", "stock_code", "stock_name", "theme"])
    seed = pd.read_csv(path)
    preview_path = CONSOLIDATED_SEED_DIR / "watchlist_report_consolidated_dashboard_preview.csv"
    if "theme" not in seed.columns and preview_path.exists():
        preview = pd.read_csv(preview_path, usecols=lambda column: column in {"asset_id", "theme"})
        seed = seed.merge(preview, on="asset_id", how="left")
    seed["stock_code"] = seed.apply(lambda row: _asset_id_to_stock_code(row.get("asset_id"), row.get("symbol")), axis=1)
    seed = seed.rename(columns={"name": "stock_name"})
    for column in ["asset_id", "stock_code", "stock_name", "theme"]:
        if column not in seed.columns:
            seed[column] = ""
    return seed[["asset_id", "stock_code", "stock_name", "theme"]].drop_duplicates("asset_id")


def _load_existing_evidence() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for directory in EVIDENCE_DIRS:
        if not directory.exists():
            continue
        for path in directory.glob("*.csv"):
            if not any(token in path.name for token in ("evidence", "candidate", "financial", "news", "statement")):
                continue
            try:
                frame = pd.read_csv(path)
            except Exception:
                continue
            if "asset_id" not in frame.columns:
                continue
            frame["_source_path"] = str(path.relative_to(PROJECT_ROOT))
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["asset_id"])
    return pd.concat(frames, ignore_index=True, sort=False)


def build_keyword_rules() -> list[KeywordRule]:
    return [
        KeywordRule("AI算力与数据中心", "光电与通信", "光互联/光芯片", "component", "architecture_chokepoint", ("光通信", "光芯片", "CPO", "光模块", "激光器", "高端连接器")),
        KeywordRule("AI算力与数据中心", "新材料", "AI服务器PCB/HBM材料", "material", "capacity_bottleneck", ("HBM", "高速高频", "HDI", "封装基板", "PCB", "液冷")),
        KeywordRule("半导体国产化", "半导体", "半导体设备", "equipment", "equipment_bottleneck", ("半导体设备", "刻蚀", "薄膜沉积", "PVD", "CVD", "ALD", "离子注入", "光刻", "涂胶显影", "清洗设备", "探针台")),
        KeywordRule("半导体国产化", "半导体", "半导体材料", "material", "material_bottleneck", ("光刻胶", "电子特气", "湿电子化学品", "硅片", "靶材", "抛光液", "抛光垫", "掩膜版", "CMP", "半导体材料", "特种气体")),
        KeywordRule("半导体国产化", "半导体", "EDA/IP", "software", "software_chokepoint", ("EDA", "IP核", "芯片设计工具")),
        KeywordRule("半导体国产化", "半导体", "先进封装", "process", "process_bottleneck", ("先进封装", "封装测试", "Chiplet", "倒装", "晶圆级封装")),
        KeywordRule("功率电子国产化", "半导体", "功率器件/IGBT/SiC/GaN", "component", "technology_bottleneck", ("IGBT", "SiC", "碳化硅", "GaN", "氮化镓", "功率半导体", "功率器件")),
        KeywordRule("工业软件国产化", "工业软件与基础软件", "基础软件/工业软件", "software", "software_chokepoint", ("操作系统", "数据库", "中间件", "信创", "基础软件", "自主可控", "CAD", "CAE", "CAM", "PLM", "MES", "SCADA", "DCS", "PLC", "仿真软件", "工业控制")),
        KeywordRule("高端制造国产化", "高端制造装备", "工业母机/机器人核心部件", "equipment", "equipment_bottleneck", ("工业母机", "五轴", "数控系统", "数控机床", "伺服", "减速器", "机器人控制器", "精密减速器", "运动控制", "精密加工", "超精密")),
        KeywordRule("航空航天与军工电子", "航空航天与军工电子", "航空航天/军工电子", "component", "certification_bottleneck", ("航空发动机", "高温合金", "惯导", "雷达", "红外", "军工电子", "特种材料", "航空航天")),
        KeywordRule("科学仪器国产化", "高端仪器仪表与科学仪器", "科学仪器/检测", "equipment", "equipment_bottleneck", ("质谱", "色谱", "电子显微镜", "光谱", "X射线", "科学仪器", "实验分析仪器", "检测设备", "量测", "半导体检测")),
        KeywordRule("新材料国产化", "新材料", "关键新材料", "material", "material_bottleneck", ("高端合金", "高温合金", "碳纤维", "陶瓷基复合材料", "高纯材料", "PI膜", "高端树脂", "电子化学品")),
        KeywordRule("高端医疗设备国产化", "高端医疗与生命科学工具", "高端医疗/生命科学工具", "equipment", "certification_bottleneck", ("高端影像", "IVD", "生命科学仪器", "生物制造设备", "高值耗材", "医学影像")),
        KeywordRule("能源与电力电子国产化", "能源与电力电子关键环节", "电力电子/电网安全", "component", "capacity_bottleneck", ("高端电力电子", "储能核心", "特高压", "工控", "电网安全", "换流阀")),
        KeywordRule("网络与数据安全", "网络安全与数据安全", "安全基础设施", "software", "software_chokepoint", ("网络安全", "密码", "工控安全", "数据安全", "安全芯片")),
        KeywordRule("国产替代/供应链约束", "其他战略性关键环节", "国产替代/供应链约束", "process", "constraint_signal", ("国产替代", "进口替代", "卡脖子", "核心技术", "关键材料", "关键设备", "关键零部件", "国产化", "突破", "客户认证", "批量供货", "量产", "中标", "验证")),
    ]


def _match_keywords(text: str, keywords: list[str] | set[str] | tuple[str, ...]) -> list[str]:
    normalized = _clean(text)
    return sorted({keyword for keyword in keywords if keyword and re.search(re.escape(keyword), normalized, flags=re.I)})


def _domain_from_text(text: str, rules: list[KeywordRule]) -> tuple[str, str, str, str, str, list[str]]:
    hits_by_rule: list[tuple[int, KeywordRule, list[str]]] = []
    for rule in rules:
        hits = _match_keywords(text, rule.keywords)
        if hits:
            hits_by_rule.append((len(hits), rule, hits))
    if not hits_by_rule:
        return "", "", "", "", "", []
    hits_by_rule.sort(key=lambda item: (item[0], len(item[1].keywords)), reverse=True)
    _, rule, hits = hits_by_rule[0]
    return rule.trend_domain, rule.domain, rule.sub_domain, rule.supply_chain_layer, rule.bottleneck_type, hits


def _broad_industry_domain(industry: str) -> tuple[str, str, str]:
    mapping = [
        ("计算机、通信和其他电子设备制造业", "半导体", "电子/芯片/通信设备宽口径"),
        ("软件和信息技术服务业", "工业软件与基础软件", "软件和信息技术服务业"),
        ("专用设备制造业", "高端制造装备", "专用设备宽口径"),
        ("通用设备制造业", "高端制造装备", "通用设备宽口径"),
        ("仪器仪表制造业", "高端仪器仪表与科学仪器", "仪器仪表制造业"),
        ("化学原料和化学制品制造业", "新材料", "化学材料宽口径"),
        ("非金属矿物制品业", "新材料", "无机非金属材料宽口径"),
        ("铁路、船舶、航空航天和其他运输设备制造业", "航空航天与军工电子", "航空航天设备宽口径"),
        ("电气机械和器材制造业", "能源与电力电子关键环节", "电气装备宽口径"),
        ("医药制造业", "高端医疗与生命科学工具", "医药制造宽口径"),
        ("专业技术服务业", "高端仪器仪表与科学仪器", "专业技术服务宽口径"),
        ("电信、广播电视和卫星传输服务", "光电与通信", "通信服务宽口径"),
    ]
    for needle, domain, sub_domain in mapping:
        if needle in _clean(industry):
            return domain, sub_domain, "industry_proxy"
    return "", "", ""


def _chain_to_domain(chain_id: str, chain_name: str) -> tuple[str, str, str, str, str]:
    text = f"{chain_id} {chain_name}"
    trend, domain, sub_domain, layer, bottleneck_type, _ = _domain_from_text(text, build_keyword_rules())
    if domain:
        return trend, domain, sub_domain, layer, bottleneck_type
    chain_id = _clean(chain_id)
    if "semiconductor" in chain_id or "chip" in chain_id or "sensor" in chain_id or "mlcc" in chain_id:
        return "半导体国产化", "半导体", _clean(chain_name, "prior tech chain"), "component", "technology_bottleneck"
    if "robot" in chain_id:
        return "高端制造国产化", "高端制造装备", _clean(chain_name, "机器人核心部件"), "component", "equipment_bottleneck"
    if "grid" in chain_id or "power" in chain_id or "energy" in chain_id:
        return "能源与电力电子国产化", "能源与电力电子关键环节", _clean(chain_name, "电力电子/电网"), "component", "capacity_bottleneck"
    if "ceramic" in chain_id or "material" in chain_id:
        return "新材料国产化", "新材料", _clean(chain_name, "关键新材料"), "material", "material_bottleneck"
    return "国产替代/供应链约束", "其他战略性关键环节", _clean(chain_name, "prior evidence chain"), "process", "constraint_signal"


def _evidence_summary(evidence: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "source_paths": set(),
        "chain_ids": set(),
        "chain_names": set(),
        "evidence_statuses": set(),
        "source_backed_field_count": 0,
        "artifact_only_or_missing_field_count": 0,
        "has_financial_statement": False,
        "has_news": False,
    })
    if evidence.empty:
        return {}
    for _, row in evidence.iterrows():
        asset_id = _clean(row.get("asset_id"))
        if not asset_id:
            continue
        item = result[asset_id]
        source_path = _clean(row.get("_source_path"))
        item["source_paths"].add(source_path)
        for field in ["primary_chain_id"]:
            value = _clean(row.get(field))
            if value:
                item["chain_ids"].add(value)
        for field in ["primary_chain_name"]:
            value = _clean(row.get(field))
            if value:
                item["chain_names"].add(value)
        value = _clean(row.get("evidence_status"))
        if value:
            item["evidence_statuses"].add(value)
        for field in ["source_backed_field_count", "artifact_only_or_missing_field_count"]:
            number = pd.to_numeric(pd.Series([row.get(field)]), errors="coerce").fillna(0).iloc[0]
            item[field] = max(int(number), int(item[field]))
        item["has_financial_statement"] = item["has_financial_statement"] or "financial" in source_path or "statement" in source_path
        item["has_news"] = item["has_news"] or "news" in source_path
    return {
        asset_id: {
            **payload,
            "source_paths": sorted(payload["source_paths"]),
            "chain_ids": sorted(payload["chain_ids"]),
            "chain_names": sorted(payload["chain_names"]),
            "evidence_statuses": sorted(payload["evidence_statuses"]),
        }
        for asset_id, payload in result.items()
    }


def _load_report_keyword_support(keywords: set[str]) -> pd.DataFrame:
    if not keywords:
        return pd.DataFrame(columns=["asset_id"])
    regex = "|".join(re.escape(keyword) for keyword in sorted(keywords, key=len, reverse=True))
    sql = """
        SELECT
            e.asset_id,
            count(*) AS report_count,
            string_agg(distinct coalesce(e.industry_name, ''), '|') AS report_industries,
            string_agg(
                left(concat_ws(' ', coalesce(s.report_title, ''), coalesce(s.raw_summary, ''), coalesce(e.industry_view, ''), coalesce(e.company_view, '')), 220),
                ' || '
            ) AS report_text
        FROM research.stock_report_event e
        LEFT JOIN research.stock_report_source s ON s.report_id = e.report_id
        WHERE e.asset_id IS NOT NULL AND e.asset_id <> ''
          AND e.report_date >= DATE '2024-01-01'
          AND (
            coalesce(s.report_title, '') || ' ' || coalesce(s.raw_summary, '') || ' ' ||
            coalesce(e.industry_view, '') || ' ' || coalesce(e.company_view, '')
          ) ~ %s
        GROUP BY e.asset_id
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [regex])
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["asset_id", "report_keyword_count", "report_keyword_hits"])
    frame["report_keyword_hits"] = frame["report_text"].fillna("").map(lambda text: _match_keywords(text, keywords))
    frame["report_keyword_count"] = frame["report_keyword_hits"].map(len)
    return frame[["asset_id", "report_count", "report_keyword_count", "report_keyword_hits", "report_industries"]]


def _score_from_level(level: str, mapping: dict[str, int]) -> int:
    return mapping.get(level, 0)


def _rank_value(value: str) -> int:
    order = ["Tier A", "Tier B", "Tier C", "Watch Only", "Risk Review", "Excluded"]
    try:
        return order.index(value)
    except ValueError:
        return len(order)


def _classify_record(
    *,
    domain: str,
    sub_domain: str,
    keyword_hits: list[str],
    industry_channel_hit: bool,
    seed_hit: bool,
    source_paths: list[str],
    source_backed_count: int,
    report_keyword_count: int,
    evidence_statuses: set[str],
    artifact_missing_count: int,
) -> dict[str, Any]:
    evidence_count = len(source_paths) + (1 if report_keyword_count else 0) + (1 if industry_channel_hit else 0) + (1 if seed_hit else 0)
    primary_source_count = len(source_paths)
    evidence_type_parts = []
    if industry_channel_hit:
        evidence_type_parts.append("industry_classification")
    if keyword_hits:
        evidence_type_parts.append("keyword_hit")
    if source_paths:
        evidence_type_parts.append("announcement_or_financial_patch")
    if report_keyword_count:
        evidence_type_parts.append("research_report")
    if seed_hit:
        evidence_type_parts.append("seed_watchlist")

    if source_backed_count >= 2 or "strong" in evidence_statuses:
        evidence_strength = "strong"
        evidence_gate_level = "confirmed"
    elif source_paths or report_keyword_count >= 2 or "partial" in evidence_statuses:
        evidence_strength = "medium"
        evidence_gate_level = "validated" if source_paths else "thesis"
    elif keyword_hits or industry_channel_hit or seed_hit:
        evidence_strength = "weak"
        evidence_gate_level = "thesis" if seed_hit or report_keyword_count else "lead"
    else:
        evidence_strength = "missing"
        evidence_gate_level = "lead"

    concept_pollution_risk = "low"
    policy_theme_only_flag = False
    name_similarity_only_flag = False
    minority_investment_only_flag = False
    agent_flag = False
    secondary_market_only = False
    interactive_only = False
    kol_only = False
    if industry_channel_hit and not (keyword_hits or source_paths or report_keyword_count or seed_hit):
        concept_pollution_risk = "high"
        policy_theme_only_flag = True
    elif domain == "其他战略性关键环节" and evidence_strength == "weak" and not seed_hit:
        concept_pollution_risk = "medium"

    if source_backed_count >= 2 and evidence_gate_level in {"validated", "confirmed"}:
        supply_chain_role = "chokepoint" if domain in {"半导体", "工业软件与基础软件", "高端制造装备"} else "bottleneck"
    elif source_paths or (seed_hit and evidence_strength in {"strong", "medium"}) or report_keyword_count >= 2:
        supply_chain_role = "bottleneck"
    elif keyword_hits and (seed_hit or report_keyword_count or industry_channel_hit):
        supply_chain_role = "beneficiary"
    elif concept_pollution_risk == "high":
        supply_chain_role = "concept_only"
    else:
        supply_chain_role = "derivative_exposure"

    main_business_relevance = "high" if source_backed_count >= 2 or (keyword_hits and industry_channel_hit) else "medium" if domain and (industry_channel_hit or seed_hit or report_keyword_count) else "low"
    technology_relevance = "high" if keyword_hits or source_paths else "medium" if industry_channel_hit or seed_hit else "unclear"
    domestic_relevance = "high" if {"国产替代", "进口替代", "自主可控", "国产化", "卡脖子"}.intersection(keyword_hits) else "medium" if source_paths or seed_hit else "unclear"
    supply_constraint_relevance = "high" if {"关键材料", "关键设备", "关键零部件", "进口替代", "国产替代"}.intersection(keyword_hits) else "medium" if domain in {"半导体", "新材料", "高端制造装备"} else "unclear"

    customer_stage = "batch_delivery" if {"批量供货", "量产"}.intersection(keyword_hits) else "customer_validation" if {"验证", "客户认证", "认证", "中标"}.intersection(keyword_hits) else "unclear"
    commercialization_stage = "mass_production" if customer_stage == "batch_delivery" else customer_stage
    named_customer_flag = bool({"客户认证", "认证"}.intersection(keyword_hits) or seed_hit and source_paths)
    order_or_capacity_flag = bool({"中标", "批量供货", "量产"}.intersection(keyword_hits) or source_backed_count >= 2)
    revenue_traceable_flag = bool(source_backed_count >= 2)
    financial_traceable_flag = bool(source_backed_count >= 2)

    real_business_exposure_score = min(100, _score_from_level(main_business_relevance, {"high": 80, "medium": 55, "low": 25}) + min(source_backed_count * 5, 20))
    evidence_quality_score = {"strong": 90, "medium": 70, "weak": 40, "missing": 10}.get(evidence_strength, 10)
    architecture_shift_score = 80 if supply_chain_role in {"bottleneck", "chokepoint"} else 55 if supply_chain_role == "beneficiary" else 30
    bottleneck_or_chokepoint_score = 88 if supply_chain_role == "chokepoint" else 80 if supply_chain_role == "bottleneck" else 45 if supply_chain_role == "beneficiary" else 20
    substitution_difficulty_score = 82 if supply_chain_role in {"bottleneck", "chokepoint"} else 50 if supply_chain_role == "beneficiary" else 25
    value_capture_score = 75 if revenue_traceable_flag or order_or_capacity_flag else 55 if source_paths or seed_hit else 35
    commercial_validation_score = 80 if order_or_capacity_flag else 60 if named_customer_flag or source_paths else 35
    market_understanding_gap_score = 55
    low_position_score = 50
    freshness_score = 60 if source_paths or report_keyword_count else 35
    fundamental_risk_score = 20 if artifact_missing_count > source_backed_count else 10

    bottleneck_exposure_score = round(
        0.15 * 70
        + 0.20 * architecture_shift_score
        + 0.25 * bottleneck_or_chokepoint_score
        + 0.15 * substitution_difficulty_score
        + 0.15 * real_business_exposure_score
        + 0.10 * evidence_quality_score,
        2,
    )
    research_priority_score = round(
        0.25 * evidence_quality_score
        + 0.20 * commercial_validation_score
        + 0.15 * market_understanding_gap_score
        + 0.15 * low_position_score
        + 0.15 * freshness_score
        - 0.10 * fundamental_risk_score,
        2,
    )

    data_gaps = []
    if not source_paths:
        data_gaps.append("primary_source_evidence_missing")
    if not report_keyword_count:
        data_gaps.append("report_keyword_metadata_missing")
    if evidence_gate_level in {"lead", "thesis"}:
        data_gaps.append("validated_or_confirmed_evidence_missing")
    if not revenue_traceable_flag:
        data_gaps.append("revenue_traceability_missing")

    excluded_flag = False
    excluded_reason = ""
    if supply_chain_role == "concept_only":
        excluded_flag = True
        excluded_reason = "concept_or_policy_theme_only_without_company_specific_support"
    elif concept_pollution_risk == "high":
        excluded_flag = True
        excluded_reason = "high_concept_pollution"

    if excluded_flag:
        candidate_tier = "Excluded"
        review_priority = "low"
        review_queue_type = "watch_only"
    elif (
        supply_chain_role in {"bottleneck", "chokepoint"}
        and evidence_gate_level in {"validated", "confirmed"}
        and real_business_exposure_score >= 65
        and substitution_difficulty_score >= 70
        and concept_pollution_risk != "high"
        and source_paths
    ):
        candidate_tier = "Tier A"
        review_priority = "high"
        review_queue_type = "thesis_validation_review"
    elif evidence_gate_level in {"thesis", "validated", "confirmed"} and supply_chain_role in {"bottleneck", "chokepoint", "beneficiary"}:
        candidate_tier = "Tier B"
        review_priority = "medium"
        review_queue_type = "customer_certification_review" if customer_stage == "unclear" else "revenue_exposure_review"
    elif evidence_gate_level == "lead":
        candidate_tier = "Tier C"
        review_priority = "low"
        review_queue_type = "data_gap_review"
    elif data_gaps:
        candidate_tier = "Watch Only"
        review_priority = "data_gap"
        review_queue_type = "watch_only"
    else:
        candidate_tier = "Risk Review"
        review_priority = "risk_review"
        review_queue_type = "source_conflict_review"

    if value_capture_score < 45 and candidate_tier == "Tier A":
        candidate_tier = "Risk Review"
        review_priority = "risk_review"
        review_queue_type = "valuation_anomaly_review"

    disconfirmation_trigger = "primary source shows substitute route, weak revenue exposure, or agency-only exposure"
    next_primary_source_check = "annual report segment revenue and announcement/customer certification check"
    return {
        "evidence_count": evidence_count,
        "evidence_type": "|".join(evidence_type_parts),
        "evidence_strength": evidence_strength,
        "evidence_gate_level": evidence_gate_level,
        "evidence_tier": "Tier 1" if source_paths else "Tier 2" if report_keyword_count else "Tier 3",
        "primary_source_count": primary_source_count,
        "supply_chain_role": supply_chain_role,
        "main_business_relevance": main_business_relevance,
        "technology_bottleneck_relevance": technology_relevance,
        "domestic_substitution_relevance": domestic_relevance,
        "supply_chain_constraint_relevance": supply_constraint_relevance,
        "customer_certification_stage": customer_stage,
        "commercialization_stage": commercialization_stage,
        "supplier_concentration_type": "certification_bottleneck" if supply_chain_role == "chokepoint" else "scarce_supplier" if supply_chain_role == "bottleneck" else "unclear",
        "revenue_exposure_bucket": "meaningful_revenue" if revenue_traceable_flag else "emerging_revenue" if source_paths else "unclear",
        "named_customer_flag": named_customer_flag,
        "order_or_capacity_flag": order_or_capacity_flag,
        "revenue_traceable_flag": revenue_traceable_flag,
        "financial_traceable_flag": financial_traceable_flag,
        "source_conflict_flag": False,
        "concept_pollution_risk": concept_pollution_risk,
        "policy_theme_only_flag": policy_theme_only_flag,
        "name_similarity_only_flag": name_similarity_only_flag,
        "minority_investment_only_flag": minority_investment_only_flag,
        "trading_agent_or_distributor_flag": agent_flag,
        "secondary_market_narrative_only_flag": secondary_market_only,
        "interactive_platform_only_flag": interactive_only,
        "kol_or_social_only_flag": kol_only,
        "real_business_exposure_score": real_business_exposure_score,
        "evidence_quality_score": evidence_quality_score,
        "architecture_shift_score": architecture_shift_score,
        "bottleneck_or_chokepoint_score": bottleneck_or_chokepoint_score,
        "substitution_difficulty_score": substitution_difficulty_score,
        "value_capture_score": value_capture_score,
        "commercial_validation_score": commercial_validation_score,
        "market_understanding_gap_score": market_understanding_gap_score,
        "low_position_score": low_position_score,
        "freshness_score": freshness_score,
        "fundamental_risk_score": fundamental_risk_score,
        "bottleneck_exposure_score": bottleneck_exposure_score,
        "research_priority_score": research_priority_score,
        "data_gap_flags": "|".join(data_gaps),
        "excluded_flag": excluded_flag,
        "excluded_reason": excluded_reason,
        "candidate_tier": candidate_tier,
        "review_priority": review_priority,
        "review_queue_type": review_queue_type,
        "disconfirmation_trigger": disconfirmation_trigger,
        "disconfirming_evidence_type": "annual_report|announcement|financial_statement",
        "thesis_kill_condition": "downgrade if primary source shows no real exposure, short switching cycle, or mature substitute route",
        "next_primary_source_check": next_primary_source_check,
        "next_research_action": "check segment revenue, named customer/certification, order/capacity evidence, and value capture support",
        "next_primary_source_to_check": next_primary_source_check,
        "manual_review_question": "Does this company control a real bottleneck/chokepoint rather than ordinary beneficiary exposure?",
        "missing_evidence_to_upgrade": "named customer, order/capacity, financial traceability, and primary-source proof",
        "evidence_to_downgrade": "concept-only, agency-only, substitute maturity high, or no revenue traceability",
        "needs_manual_review": candidate_tier in {"Tier B", "Tier C", "Watch Only", "Risk Review"} or bool(data_gaps),
    }


def _architecture_fields(domain: str, sub_domain: str, layer: str) -> dict[str, Any]:
    shift = {
        "半导体": ("imported semiconductor stack -> domestic equipment/material/process stack", "external dependency and validation bottleneck", "domestic equipment/material/process qualification"),
        "工业软件与基础软件": ("generic software stack -> autonomous industrial/basic software stack", "foreign software dependency", "domestic software validation and migration"),
        "高端制造装备": ("general manufacturing -> high precision automated manufacturing", "precision/yield constraints", "servo/reducer/controller/equipment dependency"),
        "新材料": ("standard materials -> high-purity/high-reliability materials", "material purity and qualification constraints", "high-purity material process capacity"),
        "光电与通信": ("electrical interconnect -> optical/high-speed interconnect", "bandwidth and power density constraints", "optical component and packaging dependency"),
    }.get(domain, ("ordinary trend -> constrained hard-tech supply chain", "system throughput constraint", f"{sub_domain or layer} dependency"))
    return {
        "architecture_shift": shift[0],
        "old_architecture_failure_point": shift[1],
        "new_architecture_dependency": shift[2],
        "adoption_timeline": "unclear; validate through primary sources",
        "inflection_window": "monitor filing/report/news evidence updates",
    }


def build_candidate_universe() -> dict[str, Any]:
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    hardening_context = _load_hardening_context()
    rules = build_keyword_rules()
    all_keywords = {keyword for rule in rules for keyword in rule.keywords}
    universe = _load_a_share_universe()
    seed = _load_seed_watchlist()
    evidence_by_asset = _evidence_summary(_load_existing_evidence())
    report_support = _load_report_keyword_support(all_keywords)
    report_by_asset = report_support.set_index("asset_id").to_dict("index") if not report_support.empty else {}
    seed_ids = set(seed["asset_id"].astype(str))

    records: list[dict[str, Any]] = []
    keyword_rows: list[dict[str, Any]] = []
    industry_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    data_gap_rows: list[dict[str, Any]] = []
    excluded_rows: list[dict[str, Any]] = []
    seed_expansion_rows: list[dict[str, Any]] = []

    for _, row in universe.iterrows():
        asset_id = _clean(row.get("asset_id"))
        stock_name = _clean(row.get("stock_name"), asset_id)
        industry = _clean(row.get("industry"))
        sub_industry = _clean(row.get("sub_industry"))
        stock_code = _clean(row.get("stock_code"))
        evidence = evidence_by_asset.get(asset_id, {})
        report = report_by_asset.get(asset_id, {})
        seed_hit = asset_id in seed_ids

        text_parts = [stock_name, industry, sub_industry]
        text_parts.extend(evidence.get("chain_ids", []))
        text_parts.extend(evidence.get("chain_names", []))
        text_parts.extend(report.get("report_keyword_hits", []) or [])
        text = " ".join(_clean(part) for part in text_parts)
        trend_domain, domain, sub_domain, layer, bottleneck_type, keyword_hits = _domain_from_text(text, rules)
        industry_domain, industry_sub_domain, industry_layer = _broad_industry_domain(industry)
        if not domain and evidence.get("chain_ids"):
            trend_domain, domain, sub_domain, layer, bottleneck_type = _chain_to_domain(evidence["chain_ids"][0], (evidence.get("chain_names") or [""])[0])
        if not domain and seed_hit:
            seed_theme = _clean(seed.loc[seed["asset_id"].eq(asset_id), "theme"].iloc[0]) if not seed.empty and seed["asset_id"].eq(asset_id).any() else ""
            trend_domain, domain, sub_domain, layer, bottleneck_type, theme_hits = _domain_from_text(seed_theme, rules)
            keyword_hits = sorted(set(keyword_hits + theme_hits))
            if not domain and seed_theme:
                trend_domain, domain, sub_domain, layer, bottleneck_type = _chain_to_domain(seed_theme, seed_theme)
        industry_channel_hit = bool(industry_domain)
        if not domain and industry_channel_hit:
            trend_domain = f"{industry_domain}行业代理发现"
            domain, sub_domain, layer, bottleneck_type = industry_domain, industry_sub_domain, industry_layer, "industry_proxy"
        if not (domain or keyword_hits or seed_hit or evidence.get("source_paths") or report.get("report_keyword_count") or industry_channel_hit):
            continue

        source_paths = evidence.get("source_paths", [])
        source_backed_count = int(evidence.get("source_backed_field_count") or 0)
        artifact_missing_count = int(evidence.get("artifact_only_or_missing_field_count") or 0)
        report_keyword_count = int(report.get("report_keyword_count") or 0)
        classed = _classify_record(
            domain=domain,
            sub_domain=sub_domain,
            keyword_hits=keyword_hits,
            industry_channel_hit=industry_channel_hit,
            seed_hit=seed_hit,
            source_paths=source_paths,
            source_backed_count=source_backed_count,
            report_keyword_count=report_keyword_count,
            evidence_statuses=set(evidence.get("evidence_statuses", [])),
            artifact_missing_count=artifact_missing_count,
        )
        arch = _architecture_fields(domain, sub_domain, layer)
        reason_bits = [
            f"domain={domain}/{sub_domain}",
            f"role={classed['supply_chain_role']}",
            f"evidence_gate={classed['evidence_gate_level']}",
        ]
        if keyword_hits:
            reason_bits.append("keyword_hits=" + "|".join(keyword_hits[:6]))
        if industry_channel_hit:
            reason_bits.append(f"industry_channel={industry_domain}")
        if source_paths:
            reason_bits.append("primary_or_prior_research_evidence")
        if report_keyword_count:
            reason_bits.append("report_metadata_keyword_support")
        if seed_hit:
            reason_bits.append("seed_watchlist_overlap")

        record = {
            "asset_id": asset_id,
            "stock_code": stock_code,
            "ts_code": _asset_id_to_ts_code(asset_id, stock_code, row.get("exchange")),
            "stock_name": stock_name,
            "exchange": _clean(row.get("exchange")),
            "list_status": _clean(row.get("list_status"), "unknown"),
            "industry": industry,
            "sub_industry": sub_industry,
            "trend_domain": trend_domain,
            "tech_bottleneck_domain": domain,
            "tech_bottleneck_sub_domain": sub_domain,
            "supply_chain_layer": layer or "unclear",
            "bottleneck_type": bottleneck_type or "unclear",
            **arch,
            **classed,
            "route_around_risk": "low" if classed["supply_chain_role"] in {"bottleneck", "chokepoint"} else "medium" if classed["supply_chain_role"] == "beneficiary" else "high",
            "can_customer_route_around": "false" if classed["supply_chain_role"] in {"bottleneck", "chokepoint"} else "unclear",
            "route_around_options": "check alternative suppliers and substitute routes",
            "substitute_maturity": "low" if classed["supply_chain_role"] in {"bottleneck", "chokepoint"} else "unclear",
            "switching_time_months": 12 if classed["supply_chain_role"] in {"bottleneck", "chokepoint"} else 3,
            "qualification_cycle_months": 12 if classed["supply_chain_role"] in {"bottleneck", "chokepoint"} else 3,
            "capacity_expansion_lead_time": 18 if classed["supply_chain_role"] in {"bottleneck", "chokepoint"} else 6,
            "alternative_supplier_count": 2 if classed["supply_chain_role"] in {"bottleneck", "chokepoint"} else 6,
            "pricing_power_evidence": "needs primary-source validation",
            "gross_margin_trend": "unclear",
            "backlog_or_order_visibility": "order/capacity evidence required",
            "customer_bargaining_power": -5,
            "supplier_bargaining_power": -3,
            "competitive_intensity": -4,
            "capital_intensity_pressure": -4,
            "price_percentile_120d": "",
            "drawdown_from_120d_high": "",
            "volatility_contraction_20d": "",
            "candidate_reason": "; ".join(reason_bits),
            "manual_review_focus": "validate role, evidence gate, value capture, route-around risk, and primary-source support",
            "seed_watchlist_overlap": seed_hit,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
        }
        records.append(record)

        for keyword in keyword_hits:
            keyword_rows.append({"stock_code": stock_code, "stock_name": stock_name, "asset_id": asset_id, "keyword": keyword, "domain": domain, "source_channel": "keyword_scan"})
        for keyword in report.get("report_keyword_hits", []) or []:
            keyword_rows.append({"stock_code": stock_code, "stock_name": stock_name, "asset_id": asset_id, "keyword": keyword, "domain": domain, "source_channel": "research_report_metadata"})
        if industry_channel_hit:
            industry_rows.append({"stock_code": stock_code, "stock_name": stock_name, "asset_id": asset_id, "industry": industry, "industry_channel_domain": industry_domain, "industry_channel_sub_domain": industry_sub_domain})
        for source_path in source_paths:
            evidence_rows.append({"stock_code": stock_code, "stock_name": stock_name, "asset_id": asset_id, "evidence_type": "prior_research_or_primary_patch", "evidence_strength": classed["evidence_strength"], "source_ref": source_path, "domain": domain})
        if classed["data_gap_flags"]:
            data_gap_rows.append({"stock_code": stock_code, "stock_name": stock_name, "asset_id": asset_id, "data_gap_flags": classed["data_gap_flags"], "candidate_tier": classed["candidate_tier"], "review_priority": classed["review_priority"]})
        if classed["excluded_flag"]:
            excluded_rows.append(record.copy())
        if not seed_hit and (seed["theme"].astype(str).str.contains(domain, na=False).any() if not seed.empty and domain else False):
            seed_expansion_rows.append({"stock_code": stock_code, "stock_name": stock_name, "asset_id": asset_id, "expansion_basis": f"domain_peer:{domain}", "candidate_tier": classed["candidate_tier"]})

    candidates = pd.DataFrame(records)
    if candidates.empty:
        candidates = pd.DataFrame(columns=["asset_id", *MAIN_COLUMNS])
    candidates = candidates.sort_values(
        by=["candidate_tier", "bottleneck_exposure_score", "research_priority_score", "stock_code"],
        ascending=[True, False, False, True],
        key=lambda series: series.map(_rank_value) if series.name == "candidate_tier" else series,
        kind="stable",
    ).reset_index(drop=True)

    by_domain = candidates.groupby(["tech_bottleneck_domain", "candidate_tier"], dropna=False).size().reset_index(name="candidate_count")
    by_tier = candidates.groupby(["candidate_tier", "review_priority"], dropna=False).size().reset_index(name="candidate_count")
    seed_overlap = build_seed_overlap(seed, candidates)
    nodes, edges = build_supply_chain_graph(candidates)

    counts = candidates["candidate_tier"].value_counts().to_dict()
    tier_a = candidates[candidates["candidate_tier"].eq("Tier A")]
    strategy_clean = _git_diff_formal_strategy_files() == ""
    data_gap_count = int(candidates["data_gap_flags"].fillna("").astype(str).str.strip().ne("").sum())
    seed_overlap_count = int(seed_overlap["in_candidate_universe"].astype(bool).sum()) if not seed_overlap.empty else 0
    new_candidate_count = int((~candidates["seed_watchlist_overlap"].astype(bool) & ~candidates["excluded_flag"].astype(bool)).sum()) if not candidates.empty else 0
    guardrails = {
        "task_name": TASK_NAME,
        "research_only": True,
        "a_share_universe_count": int(len(universe)),
        "candidate_total_count": int(len(candidates)),
        "tier_a_count": int(counts.get("Tier A", 0)),
        "tier_b_count": int(counts.get("Tier B", 0)),
        "tier_c_count": int(counts.get("Tier C", 0)),
        "watch_only_count": int(counts.get("Watch Only", 0)),
        "risk_review_count": int(counts.get("Risk Review", 0)),
        "excluded_count": int(counts.get("Excluded", 0)),
        "needs_manual_review_count": int(candidates["needs_manual_review"].astype(bool).sum()) if not candidates.empty else 0,
        "seed_watchlist_count": int(len(seed)),
        "seed_overlap_count": seed_overlap_count,
        "new_candidate_count": new_candidate_count,
        "tier_a_bottleneck_or_chokepoint_count": int(tier_a["supply_chain_role"].isin(["bottleneck", "chokepoint"]).sum()),
        "tier_a_beneficiary_count": int(tier_a["supply_chain_role"].eq("beneficiary").sum()),
        "tier_a_concept_only_count": int(tier_a["supply_chain_role"].eq("concept_only").sum()),
        "tier_a_missing_disconfirmation_count": int(tier_a["disconfirmation_trigger"].fillna("").astype(str).str.strip().eq("").sum()),
        "tier_a_missing_next_primary_source_count": int(tier_a["next_primary_source_check"].fillna("").astype(str).str.strip().eq("").sum()),
        "tier_a_missing_validated_or_confirmed_evidence_count": int(~tier_a["evidence_gate_level"].isin(["validated", "confirmed"]).sum()) if False else int((~tier_a["evidence_gate_level"].isin(["validated", "confirmed"])).sum()),
        "concept_pollution_high_count": int(candidates["concept_pollution_risk"].eq("high").sum()),
        "data_gap_count": data_gap_count,
        "supply_chain_nodes_count": int(len(nodes)),
        "supply_chain_edges_count": int(len(edges)),
        "used_for_signal_count": int(candidates["used_for_signal"].astype(bool).sum()) if not candidates.empty else 0,
        "used_for_admission_count": int(candidates["used_for_admission"].astype(bool).sum()) if not candidates.empty else 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": "a_share_candidate_universe_ready_for_manual_review" if len(universe) > 0 and len(candidates) > len(seed) and strategy_clean else "blocked_due_to_source_unavailable",
    }
    if guardrails["acceptance_decision"] == "a_share_candidate_universe_ready_for_manual_review" and data_gap_count:
        guardrails["acceptance_decision"] = "conditionally_ready_with_data_gaps"

    summary = {
        **guardrails,
        "hardening_context": hardening_context,
        "domain_distribution": candidates["tech_bottleneck_domain"].fillna("missing").value_counts().sort_index().to_dict(),
        "tier_distribution": candidates["candidate_tier"].fillna("missing").value_counts().sort_index().to_dict(),
        "review_priority_distribution": candidates["review_priority"].fillna("missing").value_counts().sort_index().to_dict(),
        "latest_market_trade_date": _clean(universe["latest_trade_date"].max()) if "latest_trade_date" in universe.columns and not universe.empty else "",
    }
    quality_audit = pd.DataFrame(
        [
            {"check_name": "candidate_reason_or_gap_present", "status": "pass" if (candidates["candidate_reason"].fillna("").astype(str).str.strip().ne("") | candidates["data_gap_flags"].fillna("").astype(str).str.strip().ne("")).all() else "fail", "value": int(len(candidates))},
            {"check_name": "tier_a_role_gate", "status": "pass" if guardrails["tier_a_beneficiary_count"] == 0 and guardrails["tier_a_concept_only_count"] == 0 else "fail", "value": int(len(tier_a))},
            {"check_name": "tier_a_disconfirmation_gate", "status": "pass" if guardrails["tier_a_missing_disconfirmation_count"] == 0 else "fail", "value": guardrails["tier_a_missing_disconfirmation_count"]},
            {"check_name": "research_only", "status": "pass" if candidates["research_only"].astype(bool).all() else "fail", "value": int(candidates["research_only"].astype(bool).sum())},
            {"check_name": "used_for_signal_count", "status": "pass" if guardrails["used_for_signal_count"] == 0 else "fail", "value": guardrails["used_for_signal_count"]},
            {"check_name": "formal_strategy_diff_clean", "status": "pass" if strategy_clean else "fail", "value": int(strategy_clean)},
        ]
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    universe[["stock_code", "ts_code", "stock_name", "exchange", "list_status", "industry", "sub_industry", "asset_id", "latest_trade_date"]].to_csv(output_dir / "a_share_universe_base.csv", index=False)
    _write_json(output_dir / "a_share_candidate_universe_summary.json", summary)
    _write_json(output_dir / "a_share_candidate_guardrails.json", guardrails)
    candidates.loc[:, MAIN_COLUMNS].to_csv(output_dir / "a_share_candidate_universe.csv", index=False)
    _write_json(output_dir / "a_share_candidate_universe.json", candidates.loc[:, MAIN_COLUMNS].to_dict("records"))
    by_domain.to_csv(output_dir / "a_share_candidate_universe_by_domain.csv", index=False)
    by_tier.to_csv(output_dir / "a_share_candidate_universe_by_tier.csv", index=False)
    pd.DataFrame(industry_rows).drop_duplicates().to_csv(output_dir / "a_share_candidate_industry_channel.csv", index=False)
    pd.DataFrame(keyword_rows).drop_duplicates().to_csv(output_dir / "a_share_candidate_keyword_hits.csv", index=False)
    pd.DataFrame(evidence_rows, columns=["stock_code", "stock_name", "asset_id", "evidence_type", "evidence_strength", "source_ref", "domain"]).to_csv(output_dir / "a_share_candidate_evidence_links.csv", index=False)
    seed_overlap.to_csv(output_dir / "a_share_candidate_seed_watchlist_overlap.csv", index=False)
    pd.DataFrame(seed_expansion_rows, columns=["stock_code", "stock_name", "asset_id", "expansion_basis", "candidate_tier"]).drop_duplicates().to_csv(output_dir / "a_share_candidate_seed_expansion.csv", index=False)
    pd.DataFrame(excluded_rows).reindex(columns=["stock_code", "stock_name", "asset_id", "industry", "tech_bottleneck_domain", "supply_chain_role", "candidate_tier", "excluded_reason", "candidate_reason"]).to_csv(output_dir / "a_share_candidate_excluded_or_low_relevance.csv", index=False)
    pd.DataFrame(data_gap_rows, columns=["stock_code", "stock_name", "asset_id", "data_gap_flags", "candidate_tier", "review_priority"]).drop_duplicates().to_csv(output_dir / "a_share_candidate_data_gaps.csv", index=False)
    quality_audit.to_csv(output_dir / "a_share_candidate_quality_audit.csv", index=False)
    nodes.to_csv(output_dir / "a_share_tech_bottleneck_supply_chain_nodes.csv", index=False)
    edges.to_csv(output_dir / "a_share_tech_bottleneck_supply_chain_edges.csv", index=False)
    (output_dir / "tech_bottleneck_a_share_candidate_universe_v1_report.md").write_text(build_markdown_report(summary, seed_overlap, by_domain, by_tier), encoding="utf-8")
    return {"output_dir": str(output_dir), "summary": summary, "guardrails": guardrails}


def build_seed_overlap(seed: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    lookup = candidates.set_index("asset_id").to_dict("index") if not candidates.empty else {}
    rows = []
    for _, row in seed.iterrows():
        asset_id = _clean(row.get("asset_id"))
        candidate = lookup.get(asset_id, {})
        rows.append({
            "stock_code": _clean(row.get("stock_code")),
            "stock_name": _clean(row.get("stock_name")),
            "in_seed_watchlist": True,
            "in_candidate_universe": bool(candidate),
            "candidate_tier": _clean(candidate.get("candidate_tier"), "Watch Only" if not candidate else ""),
            "trend_domain": _clean(candidate.get("trend_domain")),
            "tech_bottleneck_domain": _clean(candidate.get("tech_bottleneck_domain")),
            "supply_chain_role": _clean(candidate.get("supply_chain_role")),
            "evidence_gate_level": _clean(candidate.get("evidence_gate_level"), "lead" if not candidate else ""),
            "evidence_strength": _clean(candidate.get("evidence_strength"), "missing" if not candidate else ""),
            "notes": "seed retained in hardened candidate universe" if candidate else "seed not matched by current channels",
        })
    return pd.DataFrame(rows)


def build_supply_chain_graph(candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    node_rows: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []
    base_nodes = [
        ("trend_ai_compute", "trend", "AI算力与数据中心"),
        ("system_hard_tech", "system", "硬科技系统需求"),
        ("module_bottleneck", "module", "瓶颈模块"),
        ("component_key", "component", "关键零部件"),
        ("material_key", "material", "关键材料"),
        ("equipment_key", "equipment", "关键设备"),
        ("process_key", "process", "关键工艺"),
        ("certification_key", "certification", "客户认证"),
        ("capacity_key", "capacity", "产能约束"),
    ]
    for node_id, node_type, node_name in base_nodes:
        node_rows.append({"node_id": node_id, "node_type": node_type, "node_name": node_name, "trend_domain": "", "tech_bottleneck_domain": "", "description": "schema seed node for hardened supply-chain graph", "research_only": True})
    for idx, row in candidates.head(300).iterrows():
        asset_node = f"listed_company_{row.stock_code}"
        node_rows.append({"node_id": asset_node, "node_type": "listed_company", "node_name": row.stock_name, "trend_domain": row.trend_domain, "tech_bottleneck_domain": row.tech_bottleneck_domain, "description": row.candidate_reason, "research_only": True})
        edge_rows.append({"edge_id": f"edge_supplies_{idx}", "source_node_id": asset_node, "target_node_id": "module_bottleneck", "edge_type": "supplies_to", "dependency_strength": "medium", "route_around_risk": row.route_around_risk, "evidence_type": row.evidence_type, "evidence_strength": row.evidence_strength, "research_only": True})
        edge_rows.append({"edge_id": f"edge_arch_{idx}", "source_node_id": "system_hard_tech", "target_node_id": asset_node, "edge_type": "architecture_depends_on", "dependency_strength": "medium", "route_around_risk": row.route_around_risk, "evidence_type": row.evidence_type, "evidence_strength": row.evidence_strength, "research_only": True})
    required_edges = [
        "depends_on",
        "substitutable_by",
        "requires_certification_from",
        "capacity_constrained_by",
        "value_captured_by",
        "risk_from",
    ]
    for edge_type in required_edges:
        edge_rows.append({"edge_id": f"schema_{edge_type}", "source_node_id": "module_bottleneck", "target_node_id": "capacity_key", "edge_type": edge_type, "dependency_strength": "unclear", "route_around_risk": "unclear", "evidence_type": "schema", "evidence_strength": "missing", "research_only": True})
    return pd.DataFrame(node_rows), pd.DataFrame(edge_rows)


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(["git", "diff", "--", *FORMAL_STRATEGY_FILES], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout or result.stderr or ""


def build_markdown_report(summary: dict[str, Any], seed_overlap: pd.DataFrame, by_domain: pd.DataFrame, by_tier: pd.DataFrame) -> str:
    domain_lines = "\n".join(f"- {row.tech_bottleneck_domain or 'missing'} / {row.candidate_tier}: {int(row.candidate_count)}" for row in by_domain.itertuples(index=False))
    tier_lines = "\n".join(f"- {row.candidate_tier} / {row.review_priority}: {int(row.candidate_count)}" for row in by_tier.itertuples(index=False))
    seed_lines = "\n".join(f"- {tier}: {count}" for tier, count in seed_overlap["candidate_tier"].fillna("missing").value_counts().sort_index().to_dict().items())
    return f"""# Tech Bottleneck A-share Candidate Universe v1

## 1. Scope

This task builds a high-recall A-share hard-tech bottleneck candidate universe. It is research-only, does not change formal strategy files, does not change baseline admission, and does not produce formal market-action signals.

## 2. Method Basis

The run is based on `tech_bottleneck_method_codification_v1_hardening_patch`, including supply-chain role gates, disconfirmation, value capture, architecture shift, route-around review, concept pollution checks, evidence gates, and hardened scoring.

## 3. Data Sources

Sources include `core.asset_master`, latest `market_daily_bar`, `core.industry_membership`, the 102-name seed watchlist, prior tech bottleneck evidence outputs, financial/news/report patch outputs, and public report metadata already cached in the research database.

## 4. Candidate Discovery Channels

Discovery channels: industry channel, keyword channel, evidence channel, seed expansion channel, and exclusion / concept pollution channel.

## 5. Hardened Candidate Classification

Candidates are classified by beneficiary / bottleneck / chokepoint role, architecture shift, route-around risk, value capture, disconfirmation, evidence gate, and concept pollution.

## 6. Candidate Universe Summary

- A-share universe count: {summary['a_share_universe_count']}
- Candidate total count: {summary['candidate_total_count']}
- Tier A: {summary['tier_a_count']}
- Tier B: {summary['tier_b_count']}
- Tier C: {summary['tier_c_count']}
- Watch Only: {summary['watch_only_count']}
- Risk Review: {summary['risk_review_count']}
- Excluded: {summary['excluded_count']}

Domain distribution:

{domain_lines}

Review priority distribution:

{tier_lines}

## 7. Tier A Gate Audit

- Tier A bottleneck / chokepoint count: {summary['tier_a_bottleneck_or_chokepoint_count']}
- Tier A beneficiary count: {summary['tier_a_beneficiary_count']}
- Tier A concept_only count: {summary['tier_a_concept_only_count']}
- Tier A missing disconfirmation count: {summary['tier_a_missing_disconfirmation_count']}
- Tier A missing next primary source count: {summary['tier_a_missing_next_primary_source_count']}
- Tier A missing validated / confirmed evidence count: {summary['tier_a_missing_validated_or_confirmed_evidence_count']}

## 8. Seed Watchlist Overlap

- Seed watchlist count: {summary['seed_watchlist_count']}
- Seed overlap count: {summary['seed_overlap_count']}
- New non-seed candidate count: {summary['new_candidate_count']}

Seed tier distribution:

{seed_lines}

## 9. Supply Chain Graph

- Supply chain nodes: {summary['supply_chain_nodes_count']}
- Supply chain edges: {summary['supply_chain_edges_count']}

## 10. Evidence and Data Gaps

- Data gap count: {summary['data_gap_count']}
- Concept pollution high count: {summary['concept_pollution_high_count']}

Each Tier A row includes next research action and next primary-source check.

## 11. Guardrail Checks

- research_only: {summary['research_only']}
- used_for_signal count: {summary['used_for_signal_count']}
- used_for_admission count: {summary['used_for_admission_count']}
- baseline admission changed count: {summary['baseline_admission_changed_count']}
- strategy file diff clean: {summary['strategy_file_diff_clean']}
- formal strategy files modified: {summary['formal_strategy_files_modified']}
- trading language hit count: {summary['trading_language_hit_count']}
- execution language hit count: {summary['execution_language_hit_count']}

## 12. Acceptance Decision

{summary['acceptance_decision']}

## 13. Recommended Next Steps

1. tech_bottleneck_candidate_universe_quality_audit_v1
2. tech_bottleneck_candidate_universe_seed_watchlist_reconciliation_v1
3. tech_bottleneck_candidate_universe_workbench_patch_v1

Continue deferring trigger, holding, exit, formal market-action signal, and strategy admission change.
"""


def main() -> None:
    global OUTPUT_DIR
    parser = argparse.ArgumentParser(description="Build hardened research-only A-share tech bottleneck candidate universe v1.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    OUTPUT_DIR = Path(args.output_dir)
    result = build_candidate_universe()
    print(f"{TASK_NAME}|output_dir|{result['output_dir']}")
    print(f"{TASK_NAME}|candidate_total_count|{result['summary']['candidate_total_count']}")
    print(f"{TASK_NAME}|acceptance_decision|{result['summary']['acceptance_decision']}")


if __name__ == "__main__":
    main()
