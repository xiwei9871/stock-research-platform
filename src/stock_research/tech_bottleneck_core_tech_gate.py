from __future__ import annotations

import json
import math
from datetime import date, datetime
from numbers import Real
from pathlib import Path
from typing import Any

import pandas as pd


CORE_TECH_GATE_COLUMNS = [
    "asset_id",
    "stock_name",
    "trade_date",
    "rank",
    "industry_name",
    "core_tech_gate",
    "core_tech_category",
    "gate_reason",
    "matched_terms",
]

PASS_PRODUCT_FAMILIES = [
    "semiconductor_equipment",
    "semiconductor_testing_metrology",
    "semiconductor_materials_components",
    "oled_display_materials",
    "ai_optical_interconnect",
    "optical_communication_components",
    "hbm_high_end_memory",
    "ai_compute_chips",
    "ai_server_high_speed_pcb",
    "mlcc_high_end_passives",
    "electronic_ceramics_mlcc",
    "advanced_medical_devices",
    "advanced_fluorochemicals_materials",
    "advanced_polymer_materials",
    "advanced_magnetic_materials",
    "image_sensor_semiconductors",
    "cloud_data_infrastructure",
    "medical_imaging",
]

PASS_TERMS = {
    "semiconductor_testing_metrology": [
        "晶圆检测",
        "量测",
        "测试设备",
        "探针台",
        "分选机",
    ],
    "semiconductor_equipment": [
        "半导体设备",
        "刻蚀",
        "薄膜沉积",
        "清洗设备",
        "涂胶显影",
        "电子工艺装备",
        "半导体工艺装备",
        "平台型半导体设备",
    ],
    "semiconductor_materials_components": [
        "半导体材料",
        "载带",
        "离型膜",
        "靶材",
        "封装材料",
    ],
    "ai_optical_interconnect": [
        "光通信模块",
        "高速光模块",
        "800G",
        "1.6T",
        "3.2T",
        "CPO",
        "硅光",
        "光引擎",
    ],
    "optical_communication_components": [
        "光模块",
        "高速光模块",
        "光通信模块",
        "光通信收发模块",
        "光互联产品",
        "光器件",
        "光芯片",
        "800G",
        "1.6T",
        "4.25G以上",
        "CPO",
        "光引擎",
    ],
    "hbm_high_end_memory": [
        "HBM",
        "HBM3E",
        "HBM4",
        "TSV",
        "高带宽内存",
        "后段产能",
    ],
    "ai_compute_chips": [
        "AI芯片",
        "国产AI芯片",
        "算力芯片",
        "智能计算芯片",
        "智算芯片",
        "云端产品线",
        "MLU",
        "思元",
        "训练芯片",
        "推理芯片",
        "加速卡",
    ],
    "ai_server_high_speed_pcb": [
        "AI服务器PCB",
        "服务器PCB",
        "高速PCB",
        "数据中心PCB",
        "高阶HDI",
        "HDI",
        "高多层板",
        "高价值量PCB",
        "PCB制造",
    ],
    "mlcc_high_end_passives": [
        "MLCC",
        "多层陶瓷电容器",
        "高容量",
        "高可靠",
        "AI server PDN",
    ],
    "advanced_medical_devices": [
        "医学影像",
        "数字化X射线",
        "植入",
        "高端医疗器械",
    ],
    "medical_imaging": [
        "医学影像",
        "数字化X射线",
    ],
    "electronic_ceramics_mlcc": [
        "MLCC",
        "电子陶瓷",
        "高频基板",
    ],
    "cloud_data_infrastructure": [
        "AI基础设施",
        "数据中心",
        "工业软件",
        "云基础设施",
    ],
}

DATE_LIKE_EVIDENCE_COLUMNS = ["candidate_trade_date", "evidence_date", "published_at", "trade_date"]

REJECT_INDUSTRY_TERMS = {
    "financials": [
        "银行",
        "保险",
        "证券",
        "多元金融",
    ],
    "consumer": [
        "食品",
        "饮料",
        "宠物",
        "服装",
        "家居",
        "白酒",
        "乳品",
        "餐饮",
    ],
    "infrastructure_or_cyclical": [
        "高速",
        "港口",
        "航运",
        "煤炭",
        "电力",
        "燃气",
        "公路",
        "铁路",
    ],
}


def build_core_tech_gate(*, candidates: pd.DataFrame, evidence: pd.DataFrame | None) -> dict[str, Any]:
    normalized_candidates = _normalize_candidates(candidates)
    normalized_evidence = _normalize_evidence(evidence)
    rows: list[dict[str, Any]] = []

    for candidate in normalized_candidates.to_dict("records"):
        asset_id = candidate["asset_id"]
        industry_name = candidate["industry_name"]
        evidence_text = _evidence_text_for_candidate(normalized_evidence, asset_id, candidate["trade_date"])
        candidate_text = _candidate_text(candidate)
        combined_text = f"{candidate_text} {evidence_text}"

        excluded_category = _excluded_industry_category(industry_name)
        if excluded_category:
            gate = "reject"
            category = f"excluded_{excluded_category}"
            reason = f"excluded industry: {excluded_category}"
            matched_terms = _matched_terms(industry_name, {excluded_category: REJECT_INDUSTRY_TERMS[excluded_category]})
        else:
            category, matched_terms = _core_tech_match(combined_text)
            if category:
                gate = "pass"
                reason = "core technology evidence"
            else:
                gate = "reject"
                category = "no_core_technology_evidence"
                reason = "no core technology evidence"
                matched_terms = []

        rows.append(
            {
                "asset_id": asset_id,
                "stock_name": candidate["stock_name"],
                "trade_date": candidate["trade_date"],
                "rank": candidate["rank"],
                "industry_name": industry_name,
                "core_tech_gate": gate,
                "core_tech_category": category,
                "gate_reason": reason,
                "matched_terms": "; ".join(matched_terms),
            }
        )

    gate_frame = pd.DataFrame(rows).reindex(columns=CORE_TECH_GATE_COLUMNS)
    core_candidates = gate_frame[gate_frame["core_tech_gate"].eq("pass")].copy()
    manifest = _manifest(gate_frame)
    return {
        "core_tech_gate": gate_frame,
        "core_tech_candidates": core_candidates,
        "manifest": manifest,
    }


def run_core_tech_gate_from_files(
    *,
    candidates_csv: Path,
    evidence_csv: Path | None,
    output_dir: Path,
) -> dict[str, Path]:
    candidates = pd.read_csv(candidates_csv)
    evidence = pd.read_csv(evidence_csv) if evidence_csv else pd.DataFrame()
    outputs = build_core_tech_gate(candidates=candidates, evidence=evidence)
    inputs = {
        "candidates_csv": str(candidates_csv),
        "evidence_csv": str(evidence_csv) if evidence_csv else "",
    }
    return write_core_tech_gate_artifacts(outputs=outputs, output_dir=output_dir, inputs=inputs)


def write_core_tech_gate_artifacts(
    *,
    outputs: dict[str, Any],
    output_dir: Path,
    inputs: dict[str, Any],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    gate_path = output_dir / "core_tech_gate.csv"
    candidates_path = output_dir / "core_tech_candidates.csv"
    summary_path = output_dir / "summary.md"
    manifest_path = output_dir / "manifest.json"

    gate = outputs["core_tech_gate"].reindex(columns=CORE_TECH_GATE_COLUMNS)
    core_candidates = outputs["core_tech_candidates"].reindex(columns=CORE_TECH_GATE_COLUMNS)
    manifest = dict(outputs.get("manifest") or _manifest(gate))
    manifest["inputs"] = inputs
    manifest["files"] = {
        "core_tech_gate": gate_path.name,
        "core_tech_candidates": candidates_path.name,
        "summary": summary_path.name,
        "manifest": manifest_path.name,
    }

    gate.to_csv(gate_path, index=False)
    core_candidates.to_csv(candidates_path, index=False)
    summary_path.write_text(_render_summary(manifest), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "core_tech_gate": gate_path,
        "core_tech_candidates": candidates_path,
        "summary": summary_path,
        "manifest": manifest_path,
    }


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    normalized = candidates.copy()
    for column in ["asset_id", "stock_name", "trade_date", "industry_name"]:
        if column not in normalized:
            normalized[column] = ""
    if "rank" not in normalized:
        normalized["rank"] = 0

    normalized["asset_id"] = normalized["asset_id"].fillna("").astype(str)
    normalized["stock_name"] = normalized["stock_name"].fillna("").astype(str)
    normalized["industry_name"] = normalized["industry_name"].fillna("").astype(str)
    normalized["trade_date"] = normalized["trade_date"].map(_normalize_date)
    normalized["rank"] = pd.to_numeric(normalized["rank"], errors="coerce").fillna(0).astype(int)
    return normalized


def _normalize_date(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value):
        int_value = int(value)
        if value == int_value:
            compact_value = str(int_value)
            if len(compact_value) == 8:
                parsed_compact = pd.to_datetime(compact_value, format="%Y%m%d", errors="coerce")
                if not pd.isna(parsed_compact):
                    return parsed_compact.strftime("%Y-%m-%d")
    if isinstance(value, str):
        compact_value = value.strip()
        if len(compact_value) == 8 and compact_value.isdigit():
            parsed_compact = pd.to_datetime(compact_value, format="%Y%m%d", errors="coerce")
            if not pd.isna(parsed_compact):
                return parsed_compact.strftime("%Y-%m-%d")
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _normalize_evidence(evidence: pd.DataFrame | None) -> pd.DataFrame:
    if evidence is None or evidence.empty or "asset_id" not in evidence:
        return pd.DataFrame(columns=["asset_id", "_gate_text", "_evidence_date"])

    normalized = evidence.copy()
    for column in ["product_family", "evidence_snippet", "matched_keyword"]:
        if column not in normalized:
            normalized[column] = ""
    normalized["asset_id"] = normalized["asset_id"].fillna("").astype(str)
    text_columns = ["product_family", "evidence_snippet", "matched_keyword"]
    normalized["_gate_text"] = normalized[text_columns].astype("string").fillna("").agg(" ".join, axis=1)
    normalized["_evidence_date"] = normalized.apply(_evidence_date, axis=1)
    if "as_of_safe" in normalized:
        normalized = normalized[~normalized["as_of_safe"].map(_is_explicit_false)].copy()
    if any(column in normalized for column in DATE_LIKE_EVIDENCE_COLUMNS):
        normalized = normalized[normalized["_evidence_date"].ne("")].copy()
    return normalized[["asset_id", "_gate_text", "_evidence_date"]].copy()


def _evidence_date(row: pd.Series) -> str:
    for column in ["evidence_date", "published_at"]:
        if column in row:
            normalized = _normalize_valid_date(row[column])
            if normalized:
                return normalized
    return ""


def _is_explicit_false(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 0
    return str(value).strip().casefold() in {"false", "0", "no"}


def _normalize_valid_date(value: Any) -> str:
    return _normalize_date(value)


def _evidence_text_for_candidate(evidence: pd.DataFrame, asset_id: str, candidate_trade_date: str) -> str:
    if evidence.empty:
        return ""

    asset_evidence = evidence[evidence["asset_id"].eq(asset_id)]
    if asset_evidence.empty:
        return ""

    dated = asset_evidence[asset_evidence["_evidence_date"].ne("")]
    if dated.empty:
        matched = asset_evidence
    else:
        candidate_date = _normalize_valid_date(candidate_trade_date)
        if not candidate_date:
            return ""
        matched = dated[dated["_evidence_date"].le(candidate_date)]
    return " ".join(matched["_gate_text"].tolist())


def _candidate_text(candidate: dict[str, Any]) -> str:
    values = [value for key, value in candidate.items() if key not in {"rank"}]
    return " ".join("" if pd.isna(value) else str(value) for value in values)


def _excluded_industry_category(industry_name: str) -> str:
    for category, terms in REJECT_INDUSTRY_TERMS.items():
        if _matched_terms(industry_name, {category: terms}):
            return category
    return ""


def _core_tech_match(text: str) -> tuple[str, list[str]]:
    family_terms = _matched_terms(text, {"product_family": PASS_PRODUCT_FAMILIES})
    if family_terms:
        for family in PASS_PRODUCT_FAMILIES:
            if _contains_term(text, family):
                return family, family_terms

    best_category = ""
    best_matches: list[str] = []
    for category, terms in PASS_TERMS.items():
        term_matches = _matched_terms(text, {category: terms})
        if len(term_matches) > len(best_matches):
            best_category = category
            best_matches = term_matches
    return best_category, best_matches


def _matched_terms(text: str, term_groups: dict[str, list[str]]) -> list[str]:
    matches: list[str] = []
    for terms in term_groups.values():
        for term in terms:
            if _contains_term(text, term):
                matches.append(term)
    return matches


def _contains_term(text: str, term: str) -> bool:
    return _compact_text(term) in _compact_text(text)


def _compact_text(value: str) -> str:
    return "".join(str(value).casefold().split())


def _manifest(gate: pd.DataFrame) -> dict[str, Any]:
    if gate.empty:
        return {
            "candidate_count": 0,
            "asset_count": 0,
            "pass_count": 0,
            "reject_count": 0,
            "category_counts": {},
        }
    return {
        "candidate_count": int(len(gate)),
        "asset_count": int(gate["asset_id"].nunique()),
        "pass_count": int(gate["core_tech_gate"].eq("pass").sum()),
        "reject_count": int(gate["core_tech_gate"].eq("reject").sum()),
        "category_counts": gate["core_tech_category"].value_counts().sort_index().to_dict(),
    }


def _render_summary(manifest: dict[str, Any]) -> str:
    lines = [
        "# core technology gate Summary",
        "",
        f"- Candidates: {manifest['candidate_count']}",
        f"- Assets: {manifest['asset_count']}",
        f"- Pass: {manifest['pass_count']}",
        f"- Reject: {manifest['reject_count']}",
        "",
        "## Categories",
    ]
    category_counts = manifest.get("category_counts", {})
    if category_counts:
        for category, count in category_counts.items():
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- none: 0")
    return "\n".join(lines) + "\n"
