from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pandas as pd


QUALITY_REVIEW_COLUMNS = [
    "asset_id",
    "stock_name",
    "trade_date",
    "p3_decision",
    "product_family",
    "product_linkage_quality",
    "bottleneck_quality",
    "technical_quality",
    "customer_quality",
    "capacity_quality",
    "catalyst_quality",
    "weak_evidence_count",
    "evidence_quality_score",
    "decision_reason",
    "next_evidence_need",
]

QUEUE_COLUMNS = [
    "asset_id",
    "stock_name",
    "trade_date",
    "p3_decision",
    "review_priority",
    "review_action",
    "product_family",
    "product_linkage_quality",
    "bottleneck_quality",
    "technical_quality",
    "customer_quality",
    "capacity_quality",
    "catalyst_quality",
    "weak_evidence_count",
    "evidence_quality_score",
    "decision_reason",
    "next_evidence_need",
]


PRODUCT_FAMILIES = {
    "chrome_chemicals": [
        "铬的氧化物",
        "铬盐",
        "铬盐联产",
        "重铬酸盐",
        "重铬酸钠",
        "重铬酸钾",
        "高端氧化铬绿",
        "高纯氧化铬绿",
        "氧化铬绿",
        "高纯金属铬",
        "金属铬",
        "铬鞣剂",
        "铬化学品",
    ],
    "auto_sealing": [
        "橡胶密封条",
        "塑胶密封条",
        "汽车密封条",
        "高端密封条",
        "密封条",
        "胶料配方",
        "无边框汽车密封条",
        "天窗密封条",
    ],
    "power_grid_equipment": [
        "开关类",
        "线圈类",
        "无功补偿",
        "智能设备",
        "输配电",
        "GIS",
        "GIL",
        "断路器",
        "隔离开关",
        "高压开关",
        "750kV",
        "特高压",
        "电力电容器",
        "变电站",
        "继电保护",
    ],
    "medical_diagnostics": [
        "传染病检测产品",
        "传染病类",
        "体外诊断",
        "诊断试剂",
        "POCT",
        "即时诊断",
        "免疫检测",
        "女性健康检测",
        "毒品及药物滥用检测",
        "肿瘤标志物检测",
        "心肌标志物检测",
        "检测仪器",
        "生物原料",
        "上游生物原料",
    ],
    "medical_imaging": [
        "超声医学影像设备",
        "医学影像设备",
        "国产超声",
        "超声",
        "探头",
        "注册产品",
        "辅助诊断",
        "医院专科化检查",
    ],
    "pharma_api_intermediates": [
        "关键医药中间体",
        "医药中间体",
        "医药原料药",
        "特色原料药",
        "原料药",
        "动保原料药",
        "医药制剂",
        "化学药品",
        "中间体自产",
    ],
    "advanced_magnetic_materials": [
        "非晶合金薄带",
        "非晶合金",
        "非晶",
        "纳米晶产品",
        "纳米晶",
        "磁性粉末",
        "磁性材料",
        "高频系统",
        "加速器",
    ],
    "hydraulics_motion_control": [
        "液压油缸",
        "液压泵阀",
        "液压系统",
        "液压行业",
        "液压",
        "插装阀",
        "电缸",
        "滚珠丝杠",
        "滚柱丝杠",
        "导轨",
    ],
    "industrial_vehicles": [
        "叉车",
        "工业车辆",
        "新能源产品",
        "智能工业车辆",
        "锂电池模组",
        "PACK",
    ],
    "aerial_work_platforms": [
        "剪叉式高空作业平台",
        "桅柱式高空作业平台",
        "臂式高空作业平台",
        "高空作业平台",
        "高空作业",
        "业平台产品",
    ],
    "copper_superconducting_wire": [
        "漆包线",
        "特种导体",
        "裸铜线",
        "铜杆",
        "铜基丝线材",
        "高温超导",
        "电磁线",
    ],
    "image_sensor_semiconductors": [
        "图像传感器",
        "CMOS",
        "半导体设计",
        "半导体代理",
        "模拟解决方案",
        "触控与显示",
        "高端智能手机",
        "自动驾驶",
    ],
    "semiconductor_equipment": [
        "半导体设备",
        "半导体工艺装备",
        "电子工艺装备",
        "电子专用设备",
        "平台型半导体设备",
        "薄膜沉积设备",
        "刻蚀设备",
        "清洗设备",
        "热处理设备",
        "涂胶显影设备",
        "离子注入",
        "等离子体",
        "先进制程",
        "晶圆制造设备",
        "集成电路设备",
    ],
    "semiconductor_testing_metrology": [
        "半导体测试设备",
        "测试设备",
        "晶圆检测设备",
        "量测设备",
        "检测设备",
        "测试系统",
        "探针台",
        "分选机",
        "AOI",
        "机器视觉",
        "先进封装",
        "集成电路测试",
    ],
    "semiconductor_materials_components": [
        "半导体材料",
        "电子材料",
        "靶材",
        "溅射靶材",
        "前驱体",
        "电子级硅微粉",
        "球形硅微粉",
        "载带",
        "离型膜",
        "MLCC离型膜",
        "引线框架",
        "封装材料",
        "关键材料",
    ],
    "oled_display_materials": [
        "OLED",
        "OLED终端材料",
        "OLED有机材料",
        "有机发光材料",
        "发光材料",
        "掩膜版",
        "掩模版",
        "显示材料",
        "面板材料",
        "显示面板",
    ],
    "optical_communication_components": [
        "光通信器件",
        "光通信模块",
        "光通信收发模块",
        "光互联产品",
        "光模块",
        "高速光模块",
        "无源器件",
        "有源器件",
        "光引擎",
        "高速光器件",
        "光电器件",
        "800G",
        "1.6T",
        "4.25G以上",
        "数据中心",
        "高速率",
        "硅光",
        "CPO",
    ],
    "ai_compute_chips": [
        "AI芯片",
        "国产AI芯片",
        "算力芯片",
        "智能计算芯片",
        "智算芯片",
        "云端产品线",
        "边缘产品线",
        "MLU",
        "思元",
        "训练芯片",
        "推理芯片",
        "加速卡",
        "智能计算集群系统",
    ],
    "ai_server_high_speed_pcb": [
        "PCB制造",
        "AI服务器PCB",
        "服务器PCB",
        "高速PCB",
        "数据中心PCB",
        "高阶HDI",
        "HDI",
        "高多层板",
        "高价值量PCB",
        "算力板",
        "高频高速板",
    ],
    "hbm_high_end_memory": [
        "HBM",
        "HBM3E",
        "HBM4",
        "高带宽内存",
        "TSV",
        "堆叠",
        "后段产能",
        "base die",
    ],
    "mlcc_high_end_passives": [
        "MLCC",
        "多层陶瓷电容器",
        "片式多层陶瓷电容器",
        "高容量",
        "高温",
        "高可靠",
        "小型化",
        "AI server PDN",
        "GPU周边",
    ],
    "electronic_ceramics_mlcc": [
        "电子陶瓷",
        "陶瓷材料",
        "MLCC",
        "片式多层陶瓷电容器",
        "多层陶瓷电容器",
        "电容器",
        "电感",
        "电子元件",
        "被动元件",
    ],
    "advanced_medical_devices": [
        "数字化X线探测器",
        "X线探测器",
        "平板探测器",
        "医学影像",
        "医疗器械",
        "骨科植入物",
        "植入物",
        "注册证",
        "医用耗材",
        "手术器械",
    ],
    "advanced_fluorochemicals_materials": [
        "含氟材料",
        "氟化工",
        "制冷剂",
        "氟聚合物",
        "PVDF",
        "含氟精细化学品",
        "电子级氢氟酸",
        "氟材料",
    ],
    "advanced_polymer_materials": [
        "改性塑料",
        "高分子材料",
        "合成树脂",
        "工程塑料",
        "特种工程塑料",
        "可降解材料",
        "PVA",
        "聚乙烯醇",
        "碳纤维复合材料",
        "复合材料",
    ],
    "cloud_data_infrastructure": [
        "云计算大数据",
        "数据中心",
        "行业解决方案",
        "智能化产品",
        "新型基础设施",
    ],
    "low_tech_consumer_goods": [
        "袜子",
        "无缝服饰",
        "无缝运动服饰",
        "家居服饰",
        "功能性手套",
        "非功能性手套",
        "防护手套",
        "吸尘器",
        "小家电",
        "两轮车",
        "四轮车",
        "配件及其他",
    ],
}

EXCLUDED_PRODUCT_FAMILIES = {"low_tech_consumer_goods"}

WEAK_CONTEXT_TERMS = [
    "利润分配",
    "公司章程",
    "减值测试",
    "商誉减值",
    "不良品",
    "会计准则",
    "财务报告",
    "收入表",
    "OCR",
    "类智 关产能",
    "租金",
    "延期",
]

BOTTLENECK_TERMS = ["卡脖子", "国产化", "自主可控", "替代进口", "打破境外", "垄断", "封锁"]
TECHNICAL_TERMS = ["核心技术", "技术优势", "胶料配方", "发明专利", "授权专利", "有效专利", "国家标准"]
CUSTOMER_TERMS = ["合格供应商", "客户认证", "客户定点", "定点", "批量供货", "主流汽车整车厂", "批量订单"]
CAPACITY_TERMS = ["产能", "投产", "产量", "销量", "扩产", "引进设备"]
CATALYST_TERMS = ["中标", "量产", "批量订单", "批量供货", "客户突破", "认证通过", "获批", "商业化"]


def classify_product_family(product_text: str, semantic_text: str = "") -> str:
    combined = _clean_text(f"{product_text} {semantic_text}")
    product_clean = _clean_text(product_text)
    semantic_clean = _clean_text(semantic_text)
    best_family = ""
    best_score = 0
    for family, terms in PRODUCT_FAMILIES.items():
        product_hits = sum(1 for term in terms if term.lower() in product_clean.lower())
        semantic_hits = sum(1 for term in terms if term.lower() in semantic_clean.lower())
        combined_hits = sum(1 for term in terms if term.lower() in combined.lower())
        if product_text and semantic_text:
            if product_hits == 0:
                continue
            if semantic_hits == 0 and family not in EXCLUDED_PRODUCT_FAMILIES:
                continue
            score = product_hits * 3 + semantic_hits * 3 + combined_hits
        else:
            score = combined_hits
        if score > best_score:
            best_family = family
            best_score = score
    return best_family


def build_quality_review(
    *,
    candidates: pd.DataFrame,
    product_rows: pd.DataFrame | None,
    evidence_hits: pd.DataFrame | None,
) -> pd.DataFrame:
    normalized_candidates = _normalize_candidates(candidates)
    normalized_products = _normalize_product_rows(product_rows)
    normalized_hits = _normalize_evidence_hits(evidence_hits)
    rows: list[dict[str, Any]] = []

    for candidate in normalized_candidates.to_dict("records"):
        key = (candidate["asset_id"], candidate["trade_date"])
        product_text = _candidate_product_text(candidate, normalized_products, key)
        candidate_hits = normalized_hits[
            normalized_hits["asset_id"].eq(key[0]) & normalized_hits["trade_date"].eq(key[1])
        ].copy()
        candidate_hits = pd.concat([candidate_hits, _candidate_wide_hits(candidate)], ignore_index=True)
        if candidate_hits.empty:
            semantic_text = ""
        else:
            semantic_text = " ".join(
                candidate_hits[["evidence_bucket", "term", "snippet", "quality"]]
                .astype("string")
                .fillna("")
                .agg(" ".join, axis=1)
                .tolist()
            )
        family = classify_product_family(product_text, semantic_text)
        qualities = {
            "product_linkage": _product_linkage_quality(product_text, semantic_text, family),
            "bottleneck": _bucket_quality(candidate_hits, BOTTLENECK_TERMS, buckets=["bottleneck", "bottleneck_or_domestic_substitution"]),
            "technical": _bucket_quality(candidate_hits, TECHNICAL_TERMS, buckets=["technical_barrier"]),
            "customer": _bucket_quality(candidate_hits, CUSTOMER_TERMS, buckets=["customer_certification", "weak_customer_or_catalyst"]),
            "capacity": _bucket_quality(candidate_hits, CAPACITY_TERMS, buckets=["capacity", "weak_capacity", "capacity_or_commercial"]),
            "catalyst": _bucket_quality(candidate_hits, CATALYST_TERMS, buckets=["news_or_announcement_catalyst", "catalyst", "weak_catalyst", "capacity_or_commercial"]),
        }
        decision, reason, next_need = _decision(qualities, family)
        weak_count = sum(1 for value in qualities.values() if value == "weak")
        score = sum(_quality_score(value) for value in qualities.values())
        rows.append(
            {
                "asset_id": candidate["asset_id"],
                "stock_name": candidate["stock_name"],
                "trade_date": candidate["trade_date"],
                "p3_decision": decision,
                "product_family": family,
                "product_linkage_quality": qualities["product_linkage"],
                "bottleneck_quality": qualities["bottleneck"],
                "technical_quality": qualities["technical"],
                "customer_quality": qualities["customer"],
                "capacity_quality": qualities["capacity"],
                "catalyst_quality": qualities["catalyst"],
                "weak_evidence_count": weak_count,
                "evidence_quality_score": score,
                "decision_reason": reason,
                "next_evidence_need": next_need,
            }
        )

    return pd.DataFrame(rows).reindex(columns=QUALITY_REVIEW_COLUMNS)


def write_quality_review_artifacts(
    *,
    review: pd.DataFrame,
    output_dir: Path,
    inputs: dict[str, str] | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "quality_review.csv"
    json_path = output_dir / "quality_review.json"
    summary_path = output_dir / "summary.md"
    mapping_backlog_path = output_dir / "product_family_mapping_backlog.csv"
    promotion_pool_path = output_dir / "promotion_pool.csv"
    human_review_queue_path = output_dir / "human_review_queue.csv"
    rejected_pool_path = output_dir / "rejected_pool.csv"
    promotion_assets_path = output_dir / "promotion_assets.csv"
    human_review_assets_path = output_dir / "human_review_assets.csv"
    rejected_assets_path = output_dir / "rejected_assets.csv"
    action_plan_path = output_dir / "operator_action_plan.md"
    manifest_path = output_dir / "manifest.json"
    review.to_csv(csv_path, index=False)
    mapping_backlog = _mapping_backlog(review)
    mapping_backlog.to_csv(mapping_backlog_path, index=False)
    queues = build_operational_queues(review)
    queues["promotion_pool"].to_csv(promotion_pool_path, index=False)
    queues["human_review_queue"].to_csv(human_review_queue_path, index=False)
    queues["rejected_pool"].to_csv(rejected_pool_path, index=False)
    asset_queues = build_asset_level_queues(queues)
    asset_queues["promotion_assets"].to_csv(promotion_assets_path, index=False)
    asset_queues["human_review_assets"].to_csv(human_review_assets_path, index=False)
    asset_queues["rejected_assets"].to_csv(rejected_assets_path, index=False)
    payload = {
        "candidate_count": int(len(review)),
        "asset_count": int(review["asset_id"].nunique()) if "asset_id" in review else 0,
        "decision_counts": review["p3_decision"].value_counts().to_dict() if "p3_decision" in review else {},
        "family_counts": review["product_family"].value_counts().to_dict() if "product_family" in review else {},
        "mapping_backlog_count": int(len(mapping_backlog)),
        "promotion_pool_count": int(len(queues["promotion_pool"])),
        "human_review_queue_count": int(len(queues["human_review_queue"])),
        "rejected_pool_count": int(len(queues["rejected_pool"])),
        "promotion_assets_count": int(len(asset_queues["promotion_assets"])),
        "human_review_assets_count": int(len(asset_queues["human_review_assets"])),
        "rejected_assets_count": int(len(asset_queues["rejected_assets"])),
        "quality_score_mean": float(review["evidence_quality_score"].mean()) if "evidence_quality_score" in review and not review.empty else 0.0,
    }
    if inputs:
        payload["inputs"] = inputs
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(_render_summary(review, payload), encoding="utf-8")
    action_plan_path.write_text(_render_action_plan(payload, asset_queues), encoding="utf-8")
    manifest = {
        **payload,
        "files": {
            "quality_review": csv_path.name,
            "quality_review_json": json_path.name,
            "summary": summary_path.name,
            "mapping_backlog": mapping_backlog_path.name,
            "promotion_pool": promotion_pool_path.name,
            "human_review_queue": human_review_queue_path.name,
            "rejected_pool": rejected_pool_path.name,
            "promotion_assets": promotion_assets_path.name,
            "human_review_assets": human_review_assets_path.name,
            "rejected_assets": rejected_assets_path.name,
            "action_plan": action_plan_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "csv": csv_path,
        "json": json_path,
        "summary": summary_path,
        "mapping_backlog": mapping_backlog_path,
        "promotion_pool": promotion_pool_path,
        "human_review_queue": human_review_queue_path,
        "rejected_pool": rejected_pool_path,
        "promotion_assets": promotion_assets_path,
        "human_review_assets": human_review_assets_path,
        "rejected_assets": rejected_assets_path,
        "action_plan": action_plan_path,
        "manifest": manifest_path,
    }


def run_quality_review_from_files(
    *,
    candidates_csv: Path,
    output_dir: Path,
    evidence_hits_csv: Path | None,
    product_rows_csv: Path | None,
) -> dict[str, Path]:
    candidates = pd.read_csv(candidates_csv)
    evidence_hits = pd.read_csv(evidence_hits_csv) if evidence_hits_csv else pd.DataFrame()
    product_rows = pd.read_csv(product_rows_csv) if product_rows_csv else pd.DataFrame()
    review = build_quality_review(candidates=candidates, product_rows=product_rows, evidence_hits=evidence_hits)
    inputs = {
        "candidates_csv": str(candidates_csv),
        "evidence_hits_csv": str(evidence_hits_csv) if evidence_hits_csv else "",
        "product_rows_csv": str(product_rows_csv) if product_rows_csv else "",
    }
    return write_quality_review_artifacts(review=review, output_dir=output_dir, inputs=inputs)


def build_operational_queues(review: pd.DataFrame) -> dict[str, pd.DataFrame]:
    normalized = _normalize_review_for_queues(review)
    if normalized.empty:
        empty = pd.DataFrame(columns=QUEUE_COLUMNS)
        return {
            "promotion_pool": empty.copy(),
            "human_review_queue": empty.copy(),
            "rejected_pool": empty.copy(),
        }

    normalized["review_action"] = normalized["p3_decision"].map(_review_action).fillna("manual_triage")
    normalized["review_priority"] = normalized.apply(_review_priority, axis=1)
    queued = normalized.reindex(columns=QUEUE_COLUMNS)
    queued = queued.sort_values(
        ["review_priority", "evidence_quality_score", "asset_id", "trade_date"],
        ascending=[True, False, True, True],
    )
    return {
        "promotion_pool": queued[queued["p3_decision"].eq("auto_approve")].copy(),
        "human_review_queue": queued[queued["p3_decision"].eq("needs_more_evidence") | queued["p3_decision"].eq("needs_product_family_mapping")].copy(),
        "rejected_pool": queued[queued["p3_decision"].eq("reject_or_noise")].copy(),
    }


def build_asset_level_queues(queues: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {
        "promotion_assets": _dedupe_queue_by_asset(queues.get("promotion_pool", pd.DataFrame())),
        "human_review_assets": _dedupe_queue_by_asset(queues.get("human_review_queue", pd.DataFrame())),
        "rejected_assets": _dedupe_queue_by_asset(queues.get("rejected_pool", pd.DataFrame())),
    }


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.copy()
    if "trade_date" not in frame.columns and "candidate_trade_date" in frame.columns:
        frame = frame.rename(columns={"candidate_trade_date": "trade_date"})
    for column in ["asset_id", "stock_name", "trade_date", "product_snippet"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["asset_id"] = frame["asset_id"].astype("string").fillna("")
    frame["stock_name"] = frame["stock_name"].astype("string").fillna("")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    frame["product_snippet"] = frame["product_snippet"].astype("string").fillna("")
    return frame[frame["asset_id"].ne("") & frame["trade_date"].ne("")].copy()


def _normalize_product_rows(product_rows: pd.DataFrame | None) -> pd.DataFrame:
    frame = product_rows.copy() if product_rows is not None else pd.DataFrame()
    if "trade_date" not in frame.columns and "candidate_trade_date" in frame.columns:
        frame = frame.rename(columns={"candidate_trade_date": "trade_date"})
    if "snippet" not in frame.columns and "evidence_snippet" in frame.columns:
        frame["snippet"] = frame["evidence_snippet"]
    if "as_of_safe" in frame.columns:
        frame = frame[frame["as_of_safe"].map(_bool_value)].copy()
    for column in ["asset_id", "trade_date", "product_name", "product", "business_item", "item_name", "snippet", "evidence_snippet"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["asset_id"] = frame["asset_id"].astype("string").fillna("")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    for column in ["product_name", "product", "business_item", "item_name", "snippet", "evidence_snippet"]:
        frame[column] = frame[column].astype("string").fillna("")
    return frame


def _normalize_evidence_hits(evidence_hits: pd.DataFrame | None) -> pd.DataFrame:
    frame = evidence_hits.copy() if evidence_hits is not None else pd.DataFrame()
    if "trade_date" not in frame.columns and "candidate_trade_date" in frame.columns:
        frame = frame.rename(columns={"candidate_trade_date": "trade_date"})
    if "snippet" not in frame.columns and "evidence_snippet" in frame.columns:
        frame = frame.rename(columns={"evidence_snippet": "snippet"})
    if "term" not in frame.columns and "matched_keyword" in frame.columns:
        frame = frame.rename(columns={"matched_keyword": "term"})
    if "evidence_bucket" not in frame.columns and "evidence_type" in frame.columns:
        frame = frame.rename(columns={"evidence_type": "evidence_bucket"})
    for column in ["asset_id", "trade_date", "evidence_bucket", "term", "snippet", "quality"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["asset_id"] = frame["asset_id"].astype("string").fillna("")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    for column in ["evidence_bucket", "term", "snippet", "quality"]:
        frame[column] = frame[column].astype("string").fillna("")
    return frame[frame["asset_id"].ne("") & frame["trade_date"].ne("")].copy()


def _normalize_review_for_queues(review: pd.DataFrame) -> pd.DataFrame:
    frame = review.copy()
    for column in QUEUE_COLUMNS:
        if column not in frame.columns:
            frame[column] = 0 if column in {"weak_evidence_count", "evidence_quality_score"} else ""
    frame["asset_id"] = frame["asset_id"].astype("string").fillna("")
    frame["stock_name"] = frame["stock_name"].astype("string").fillna("")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    for column in [
        "p3_decision",
        "product_family",
        "product_linkage_quality",
        "bottleneck_quality",
        "technical_quality",
        "customer_quality",
        "capacity_quality",
        "catalyst_quality",
        "decision_reason",
        "next_evidence_need",
    ]:
        frame[column] = frame[column].astype("string").fillna("")
    frame["weak_evidence_count"] = pd.to_numeric(frame["weak_evidence_count"], errors="coerce").fillna(0).astype(int)
    frame["evidence_quality_score"] = pd.to_numeric(frame["evidence_quality_score"], errors="coerce").fillna(0).astype(int)
    return frame[frame["asset_id"].ne("") & frame["trade_date"].ne("")].copy()


def _dedupe_queue_by_asset(queue: pd.DataFrame) -> pd.DataFrame:
    columns = [*QUEUE_COLUMNS, "candidate_count_for_asset", "candidate_dates_for_asset"]
    if queue is None or queue.empty:
        return pd.DataFrame(columns=columns)
    frame = _normalize_review_for_queues(queue)
    frame["review_action"] = frame["p3_decision"].map(_review_action).fillna("manual_triage")
    frame["review_priority"] = frame.apply(_review_priority, axis=1)
    candidate_counts = frame.groupby("asset_id")["trade_date"].count().rename("candidate_count_for_asset")
    candidate_dates = frame.groupby("asset_id")["trade_date"].apply(lambda values: "|".join(sorted(set(values)))).rename(
        "candidate_dates_for_asset"
    )
    ranked = (
        frame.sort_values(["review_priority", "evidence_quality_score", "trade_date"], ascending=[True, False, True])
        .drop_duplicates("asset_id", keep="first")
        .merge(candidate_counts, on="asset_id", how="left")
        .merge(candidate_dates, on="asset_id", how="left")
    )
    return ranked.reindex(columns=columns)


def _candidate_product_text(candidate: dict[str, Any], product_rows: pd.DataFrame, key: tuple[str, str]) -> str:
    parts = [_clean_text(str(candidate.get("product_snippet") or ""))]
    if not product_rows.empty:
        rows = product_rows[product_rows["asset_id"].eq(key[0]) & product_rows["trade_date"].isin(["", key[1]])]
        for column in ["product_name", "product", "business_item", "item_name", "snippet", "evidence_snippet"]:
            if column in rows:
                parts.extend(rows[column].astype("string").fillna("").tolist())
    return " ".join(part for part in parts if part)


def _candidate_wide_hits(candidate: dict[str, Any]) -> pd.DataFrame:
    bucket_columns = [
        ("bottleneck", "bottleneck_keyword", "bottleneck_snippet"),
        ("technical_barrier", "technical_keyword", "technical_snippet"),
        ("news_or_announcement_catalyst", "catalyst_keyword", "catalyst_snippet"),
        ("capacity", "capacity_keyword", "capacity_snippet"),
        ("customer_certification", "customer_keyword", "customer_snippet"),
    ]
    rows: list[dict[str, str]] = []
    for bucket, keyword_column, snippet_column in bucket_columns:
        term = _clean_text(str(candidate.get(keyword_column) or ""))
        snippet = _clean_text(str(candidate.get(snippet_column) or ""))
        if not term and not snippet:
            continue
        rows.append(
            {
                "asset_id": str(candidate.get("asset_id") or ""),
                "trade_date": str(candidate.get("trade_date") or ""),
                "evidence_bucket": bucket,
                "term": term,
                "snippet": snippet,
                "quality": "",
            }
        )
    return pd.DataFrame(rows, columns=["asset_id", "trade_date", "evidence_bucket", "term", "snippet", "quality"])


def _product_linkage_quality(product_text: str, semantic_text: str, family: str) -> str:
    if not product_text or not family:
        return "missing"
    if semantic_text and classify_product_family(product_text, semantic_text) == family:
        return "strong"
    return "medium"


def _bucket_quality(hits: pd.DataFrame, positive_terms: list[str], *, buckets: list[str]) -> str:
    if hits.empty:
        return "missing"
    bucket_set = {bucket.lower() for bucket in buckets}
    scoped = hits[hits["evidence_bucket"].str.lower().isin(bucket_set)].copy()
    if scoped.empty:
        text = " ".join(hits[["term", "snippet"]].astype("string").fillna("").agg(" ".join, axis=1).tolist())
        if not _contains_any(text, positive_terms):
            return "missing"
        scoped = hits.copy()
    qualities = [_row_quality(row, positive_terms) for row in scoped.to_dict("records")]
    if "strong" in qualities:
        return "strong"
    if "medium" in qualities:
        return "medium"
    if "weak" in qualities:
        return "weak"
    return "missing"


def _row_quality(row: dict[str, Any], positive_terms: list[str]) -> str:
    explicit_quality = _clean_text(str(row.get("quality") or "")).lower()
    if explicit_quality in {"strong", "medium", "weak"}:
        return explicit_quality
    bucket = _clean_text(str(row.get("evidence_bucket") or "")).lower()
    text = _clean_text(f"{row.get('term', '')} {row.get('snippet', '')}")
    if "weak" in bucket or _contains_any(text, WEAK_CONTEXT_TERMS):
        return "weak"
    if _contains_any(text, positive_terms):
        return "strong"
    return "medium" if len(text) >= 20 else "missing"


def _decision(qualities: dict[str, str], family: str) -> tuple[str, str, str]:
    if family in EXCLUDED_PRODUCT_FAMILIES:
        return (
            "reject_or_noise",
            f"excluded product family for tech-bottleneck discovery: {family}",
            "do not promote unless a specific hard-tech bottleneck sub-product is mapped separately",
        )
    if qualities["product_linkage"] == "missing" or not family:
        if _core_evidence_ok(qualities) and any(qualities[key] == "strong" for key in ["customer", "capacity", "catalyst"]):
            return (
                "needs_product_family_mapping",
                "product and evidence are not linked by current product-family dictionary, but core evidence is not weak",
                "needs_product_family_mapping",
            )
        return (
            "reject_or_noise",
            "missing same-product-family linkage between product exposure and semantic evidence",
            "replace generic product/OCR evidence with PIT-safe product-family evidence",
        )
    core_ok = _core_evidence_ok(qualities)
    support_strong = any(qualities[key] == "strong" for key in ["customer", "capacity", "catalyst"])
    support_weak = any(qualities[key] == "weak" for key in ["customer", "capacity", "catalyst"])
    if qualities["product_linkage"] == "strong" and qualities["bottleneck"] == "strong" and qualities["technical"] == "strong" and support_strong:
        return (
            "auto_approve",
            "same product family with strong bottleneck, technical barrier, and commercialization/capacity/customer support",
            "human review can verify source page but no data backfill blocker remains",
        )
    if core_ok:
        reason = "same product family has product and core technical/bottleneck evidence, but support evidence is incomplete"
        if support_weak:
            reason += " or weak"
        return (
            "needs_more_evidence",
            reason,
            _next_support_evidence_need(qualities),
        )
    return (
        "reject_or_noise",
        "product family exists but core bottleneck or technical evidence is missing/weak",
        "replace noisy semantic hits with official product-specific evidence",
    )


def _review_action(decision: str) -> str:
    return {
        "auto_approve": "add_to_observation_pool",
        "needs_more_evidence": "targeted_evidence_review",
        "needs_product_family_mapping": "product_family_mapping_review",
        "reject_or_noise": "exclude_from_observation_pool",
    }.get(str(decision), "manual_triage")


def _review_priority(row: pd.Series) -> str:
    decision = str(row.get("p3_decision") or "")
    score = int(row.get("evidence_quality_score") or 0)
    weak = int(row.get("weak_evidence_count") or 0)
    if decision == "auto_approve":
        if score >= 11 and weak == 0:
            return "P1_observe"
        return "P2_observe_after_review"
    if decision == "needs_more_evidence":
        if score >= 10 and weak == 0:
            return "P1_evidence_review"
        return "P2_evidence_review"
    if decision == "needs_product_family_mapping":
        return "P2_mapping_review"
    if decision == "reject_or_noise":
        return "P3_reject_audit"
    return "P9_manual_triage"


def _core_evidence_ok(qualities: dict[str, str]) -> bool:
    return qualities["bottleneck"] in {"strong", "medium"} and qualities["technical"] in {"strong", "medium"}


def _next_support_evidence_need(qualities: dict[str, str]) -> str:
    needs = []
    if qualities["customer"] in {"missing", "weak"}:
        needs.append("needs_customer_or_certification_evidence")
    if qualities["capacity"] in {"missing", "weak"}:
        needs.append("needs_capacity_evidence")
    if qualities["catalyst"] in {"missing", "weak"}:
        needs.append("needs_catalyst_evidence")
    return "|".join(needs) if needs else "needs_pit_safe_source"


def _quality_score(value: str) -> int:
    return {"strong": 2, "medium": 1, "weak": -1, "missing": 0}.get(value, 0)


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("<em>", "").replace("</em>", "")).strip()


def _render_summary(review: pd.DataFrame, payload: dict[str, Any]) -> str:
    lines = [
        "# Tech Bottleneck Quality Review",
        "",
        f"- candidates: {payload['candidate_count']}",
        f"- assets: {payload['asset_count']}",
        f"- decision_counts: {payload['decision_counts']}",
        f"- family_counts: {payload['family_counts']}",
        f"- mapping_backlog_count: {payload.get('mapping_backlog_count', 0)}",
        f"- promotion_pool_count: {payload.get('promotion_pool_count', 0)}",
        f"- human_review_queue_count: {payload.get('human_review_queue_count', 0)}",
        f"- rejected_pool_count: {payload.get('rejected_pool_count', 0)}",
        f"- promotion_assets_count: {payload.get('promotion_assets_count', 0)}",
        f"- human_review_assets_count: {payload.get('human_review_assets_count', 0)}",
        f"- rejected_assets_count: {payload.get('rejected_assets_count', 0)}",
        f"- quality_score_mean: {payload['quality_score_mean']:.3f}",
    ]
    if not review.empty:
        lines += ["", "## Candidates"]
        for row in review.to_dict("records"):
            lines.append(
                f"- {row['trade_date']} {row['stock_name']} {row['asset_id']}: "
                f"{row['p3_decision']} family={row.get('product_family', '')} "
                f"score={row.get('evidence_quality_score', '')}"
            )
    return "\n".join(lines) + "\n"


def _render_action_plan(payload: dict[str, Any], asset_queues: dict[str, pd.DataFrame]) -> str:
    lines = [
        "# Tech Bottleneck Operator Action Plan",
        "",
        "This file is generated from evidence quality review only. It is not a return test.",
        "",
        "## Counts",
        f"- promotion_assets: {payload.get('promotion_assets_count', 0)}",
        f"- human_review_assets: {payload.get('human_review_assets_count', 0)}",
        f"- rejected_assets: {payload.get('rejected_assets_count', 0)}",
        f"- mapping_backlog: {payload.get('mapping_backlog_count', 0)}",
        "",
    ]
    sections = [
        ("Promotion Assets", "promotion_assets", "Add to observation pool after final source-page spot check."),
        ("Human Review Assets", "human_review_assets", "Run targeted evidence review before promotion."),
        ("Rejected Assets", "rejected_assets", "Keep excluded unless a hard-tech sub-product is remapped."),
    ]
    for title, key, note in sections:
        rows = asset_queues.get(key, pd.DataFrame())
        lines += [f"## {title}", f"- action: {note}"]
        if rows is None or rows.empty:
            lines.append("- none")
        else:
            for row in rows.to_dict("records"):
                lines.append(
                    f"- {row.get('stock_name', '')} {row.get('asset_id', '')} {row.get('trade_date', '')}: "
                    f"{row.get('product_family', '')}, {row.get('review_priority', '')}, "
                    f"score={row.get('evidence_quality_score', '')}, "
                    f"candidate_dates={row.get('candidate_dates_for_asset', '')}"
                )
        lines.append("")
    return "\n".join(lines)


def _mapping_backlog(review: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "asset_id",
        "stock_name",
        "trade_date",
        "p3_decision",
        "product_family",
        "product_linkage_quality",
        "bottleneck_quality",
        "technical_quality",
        "customer_quality",
        "capacity_quality",
        "catalyst_quality",
        "evidence_quality_score",
        "decision_reason",
        "next_evidence_need",
    ]
    for column in columns:
        if column not in review.columns:
            review[column] = ""
    backlog = review[review["p3_decision"].eq("needs_product_family_mapping")].copy()
    if backlog.empty:
        return pd.DataFrame(columns=columns)
    return backlog.reindex(columns=columns).sort_values(
        ["evidence_quality_score", "asset_id", "trade_date"],
        ascending=[False, True, True],
    )
