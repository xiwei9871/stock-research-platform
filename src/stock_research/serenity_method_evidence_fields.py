from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


METHOD_FIELDS = [
    "customer_certification_stage",
    "supplier_concentration_type",
    "revenue_exposure_bucket",
]

CORE_REVENUE_CHAINS = {
    "ai_optical_interconnect",
    "mlcc_high_end_passives",
}

MEANINGFUL_SEGMENT_CHAINS = {
    "ai_server_pcb",
    "advanced_packaging_materials",
    "semiconductor_equipment",
    "semiconductor_materials",
    "high_end_sensors",
    "liquid_cooling_thermal",
    "magnetic_inductor_materials",
    "ceramics_electronic_materials",
}

EARLY_RAMP_CHAINS = {
    "robotics_core_components",
    "power_grid_energy_infrastructure",
    "power_delivery",
    "hbm_storage",
    "lithography_eda_ip",
}

NON_PRODUCT_NODE_KEYWORDS = {"银行", "金融", "保险", "证券", "农商行"}

DIRECT_NODE_KEYWORDS = {
    "光模块",
    "800g",
    "1.6t",
    "cpo",
    "刻蚀",
    "薄膜",
    "沉积",
    "量测",
    "检测",
    "mlcc",
    "hbm",
}

ORDER_KEYWORDS = {"订单", "交付", "出货", "delivery", "backlog"}
MASS_PRODUCTION_KEYWORDS = {"量产", "批量", "放量", "mass production", "ramp"}
DESIGN_IN_KEYWORDS = {"design-in", "design in", "导入", "定点", "验证通过"}
CERTIFICATION_KEYWORDS = {"认证", "验证", "qualification", "合格供应商", "客户验证"}
SUPPLIER_SCARCE_KEYWORDS = {"进口", "国产替代", "稀缺", "少数", "垄断", "独供", "高端", "scarce"}
CONCENTRATED_CHAIN_IDS = {
    "ai_optical_interconnect",
    "semiconductor_materials",
    "advanced_packaging_materials",
}
IMPORT_DEPENDENCY_CHAIN_IDS = {
    "semiconductor_equipment",
    "mlcc_high_end_passives",
    "hbm_storage",
    "semiconductor_materials",
    "advanced_packaging_materials",
    "ai_server_pcb",
    "ceramics_electronic_materials",
    "magnetic_inductor_materials",
}


def run_serenity_method_evidence_fields(
    *,
    candidates_csv: str | Path,
    output_dir: str | Path,
    run_id: str = "serenity_method_evidence_fields",
) -> dict[str, Any]:
    candidates = pd.read_csv(candidates_csv, low_memory=False)
    return build_serenity_method_evidence_fields(candidates=candidates, output_dir=output_dir, run_id=run_id)


def build_serenity_method_evidence_fields(
    *,
    candidates: pd.DataFrame,
    output_dir: str | Path | None = None,
    run_id: str = "serenity_method_evidence_fields",
) -> dict[str, Any]:
    frame = candidates.copy()
    for column in [
        "asset_id",
        "stock_name",
        "first_hit_date",
        "primary_chain_id",
        "primary_chain_name",
        "matched_bottleneck_dimensions",
        "hit_count",
        "revenue_yoy",
        "np_yoy",
    ]:
        if column not in frame.columns:
            frame[column] = pd.NA

    records = []
    for row in frame.to_dict("records"):
        customer = _classify_customer_stage(row)
        supplier = _classify_supplier_concentration(row)
        revenue = _classify_revenue_exposure(row)
        records.append(
            {
                **_base_record(row, run_id),
                **customer,
                **supplier,
                **revenue,
                "method_evidence_readiness": _readiness(customer, supplier, revenue),
            }
        )

    detail = pd.DataFrame(records).sort_values(["method_evidence_readiness", "asset_id"], ascending=[False, True])
    long = _to_long(detail)
    summary = _summary(long)
    report = _render_report(detail, summary, run_id)

    paths: dict[str, str] = {}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        files = {
            "detail": output / "serenity_method_evidence_fields_detail.csv",
            "long": output / "serenity_method_evidence_fields_long.csv",
            "summary": output / "serenity_method_evidence_fields_summary.csv",
            "report": output / "serenity_method_evidence_fields_report.md",
        }
        detail.to_csv(files["detail"], index=False)
        long.to_csv(files["long"], index=False)
        summary.to_csv(files["summary"], index=False)
        files["report"].write_text(report, encoding="utf-8")
        paths = {key: str(value) for key, value in files.items()}

    return {"detail": detail, "long": long, "summary": summary, "report": report, "paths": paths}


def _base_record(row: dict[str, Any], run_id: str) -> dict[str, Any]:
    return {
        "asset_id": _text(row.get("asset_id")),
        "stock_name": _text(row.get("stock_name")),
        "first_hit_date": _text(row.get("first_hit_date")),
        "primary_chain_id": _text(row.get("primary_chain_id")),
        "primary_chain_name": _text(row.get("primary_chain_name")),
        "matched_bottleneck_dimensions": _text(row.get("matched_bottleneck_dimensions")),
        "hit_count": row.get("hit_count"),
        "revenue_yoy": row.get("revenue_yoy"),
        "np_yoy": row.get("np_yoy"),
        "source_provenance": f"{run_id}:candidate_row",
        "source_provenance_scope": "local_artifact_row",
        "source_provenance_limit": "not primary-source quote-level evidence",
    }


def _classify_customer_stage(row: dict[str, Any]) -> dict[str, str]:
    text = _row_text(row)
    chain_id = _text(row.get("primary_chain_id"))
    if _has_any(text, NON_PRODUCT_NODE_KEYWORDS):
        stage = "not_identified"
        status = "missing"
        rule = "financial-service wording does not establish product-node customer certification"
    elif _has_any(text, ORDER_KEYWORDS):
        stage = "order"
        status = "partial"
        rule = "order, delivery, shipment, or backlog wording is present"
    elif _has_any(text, MASS_PRODUCTION_KEYWORDS):
        stage = "mass_production"
        status = "partial"
        rule = "mass production, batch delivery, ramp, or volume production wording is present"
    elif _has_any(text, DESIGN_IN_KEYWORDS):
        stage = "design_in"
        status = "partial"
        rule = "design-in, selected supplier, or introduction wording is present"
    elif _has_any(text, CERTIFICATION_KEYWORDS) or chain_id in {
        "semiconductor_equipment",
        "high_end_sensors",
        "mlcc_high_end_passives",
        "ai_optical_interconnect",
        "robotics_core_components",
    }:
        stage = "certification"
        status = "weak"
        rule = "qualification-heavy chain or certification wording, without source-backed stage"
    else:
        stage = "not_identified"
        status = "missing"
        rule = "no customer certification, design-in, mass-production, or order signal"
    return {
        "customer_certification_stage": stage,
        "customer_certification_status": status,
        "customer_certification_audit_rule": rule,
        "customer_certification_needed_source_type": "customer certification/design-in/order evidence from reports, announcements, or investor Q&A",
    }


def _classify_supplier_concentration(row: dict[str, Any]) -> dict[str, str]:
    text = _row_text(row)
    chain_id = _text(row.get("primary_chain_id"))
    if chain_id in IMPORT_DEPENDENCY_CHAIN_IDS or _has_any(text, SUPPLIER_SCARCE_KEYWORDS):
        bucket = "import_dependency_or_domestic_substitution_scarcity"
        status = "partial" if _has_any(text, SUPPLIER_SCARCE_KEYWORDS) else "weak"
        rule = "chain or wording points to import dependency, scarcity, or few domestic substitutes"
        import_flag = "import_dependency_likely"
        substitute_bucket = "few_domestic_substitutes_likely"
        concentration_bucket = "scarce_supply_likely"
    elif chain_id in CONCENTRATED_CHAIN_IDS:
        bucket = "likely_concentrated_supply_chain"
        status = "weak"
        rule = "chain is typically concentrated, but candidate lacks source-backed supplier count"
        import_flag = "not_established"
        substitute_bucket = "not_established"
        concentration_bucket = "concentrated_likely"
    else:
        bucket = "concentration_not_established"
        status = "weak"
        rule = "no import dependency, supplier count, domestic substitute count, or concentration signal"
        import_flag = "not_established"
        substitute_bucket = "not_established"
        concentration_bucket = "not_established"
    return {
        "supplier_concentration_type": bucket,
        "supplier_import_dependency_flag": import_flag,
        "supplier_domestic_substitute_count_bucket": substitute_bucket,
        "supplier_concentration_bucket": concentration_bucket,
        "supplier_concentration_status": status,
        "supplier_concentration_audit_rule": rule,
        "supplier_concentration_needed_source_type": "industry report or company disclosure showing import reliance, supplier count, market share, or domestic substitute count",
    }


def _classify_revenue_exposure(row: dict[str, Any]) -> dict[str, str]:
    text = _row_text(row)
    chain_id = _text(row.get("primary_chain_id"))
    direct_node = _has_any(text, DIRECT_NODE_KEYWORDS)
    if _has_any(text, NON_PRODUCT_NODE_KEYWORDS):
        bucket = "concept_or_indirect_exposure_review"
        status = "weak"
        rule = "financial-service or non-product-node mapping needs explicit product exposure proof"
    elif chain_id in CORE_REVENUE_CHAINS and direct_node:
        bucket = "core_or_high_confidence_product_exposure"
        status = "partial"
        rule = "core product-node chain plus direct bottleneck dimensions"
    elif chain_id in CORE_REVENUE_CHAINS | MEANINGFUL_SEGMENT_CHAINS:
        bucket = "meaningful_segment_exposure"
        status = "weak"
        rule = "chain implies meaningful segment exposure, but product revenue split is not source-backed"
    elif chain_id in EARLY_RAMP_CHAINS:
        bucket = "early_ramp_or_inflection_exposure"
        status = "weak"
        rule = "chain implies emerging exposure, but current revenue contribution is not quantified"
    else:
        bucket = "concept_or_indirect_exposure_review"
        status = "weak"
        rule = "mapping is indirect or concept-like until product revenue evidence is attached"
    return {
        "revenue_exposure_bucket": bucket,
        "revenue_exposure_status": status,
        "revenue_exposure_audit_rule": rule,
        "revenue_exposure_needed_source_type": "annual report segment revenue, product revenue split, order backlog, or management disclosure",
    }


def _readiness(*field_records: dict[str, str]) -> float:
    score = 0.0
    weights = {"missing": 0.0, "weak": 0.35, "partial": 0.7, "strong": 1.0}
    for record in field_records:
        statuses = [value for key, value in record.items() if key.endswith("_status")]
        score += weights.get(statuses[0] if statuses else "missing", 0.0)
    return round(score / max(len(field_records), 1), 4)


def _to_long(detail: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in detail.to_dict("records"):
        for field in METHOD_FIELDS:
            prefix = field.replace("_stage", "").replace("_type", "").replace("_bucket", "")
            if field == "customer_certification_stage":
                status = row["customer_certification_status"]
                rule = row["customer_certification_audit_rule"]
                needed = row["customer_certification_needed_source_type"]
            elif field == "supplier_concentration_type":
                status = row["supplier_concentration_status"]
                rule = row["supplier_concentration_audit_rule"]
                needed = row["supplier_concentration_needed_source_type"]
            else:
                status = row["revenue_exposure_status"]
                rule = row["revenue_exposure_audit_rule"]
                needed = row["revenue_exposure_needed_source_type"]
            rows.append(
                {
                    "asset_id": row["asset_id"],
                    "stock_name": row["stock_name"],
                    "field": field,
                    "value": row[field],
                    "status": status,
                    "audit_rule": rule,
                    "needed_source_type": needed,
                    "source_provenance": row["source_provenance"],
                    "source_provenance_scope": row["source_provenance_scope"],
                }
            )
    return pd.DataFrame(rows)


def _summary(long: pd.DataFrame) -> pd.DataFrame:
    if long.empty:
        return pd.DataFrame(columns=["field", "missing", "weak", "partial", "strong", "total", "weak_or_missing", "weak_or_missing_ratio"])
    summary = (
        long.pivot_table(index="field", columns="status", values="asset_id", aggfunc="count", fill_value=0)
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for column in ["missing", "weak", "partial", "strong"]:
        if column not in summary.columns:
            summary[column] = 0
    summary["total"] = summary[["missing", "weak", "partial", "strong"]].sum(axis=1)
    summary["weak_or_missing"] = summary["missing"] + summary["weak"]
    summary["weak_or_missing_ratio"] = summary["weak_or_missing"] / summary["total"].where(summary["total"] != 0, 1)
    return summary[["field", "missing", "weak", "partial", "strong", "total", "weak_or_missing", "weak_or_missing_ratio"]]


def _render_report(detail: pd.DataFrame, summary: pd.DataFrame, run_id: str) -> str:
    lines = [
        "# Serenity Method Evidence Fields",
        "",
        f"Run ID: `{run_id}`",
        "",
        "Scope: auditable first-pass schema for customer stage, supplier concentration, and revenue exposure.",
        "",
        "Important limit: current provenance is local artifact row level, not primary-source quote level.",
        "",
        "## Field Summary",
        "",
        summary.to_markdown(index=False),
        "",
        "## Bucket Definitions",
        "",
        "- customer_certification_stage: not_identified, certification, design_in, mass_production, order.",
        "- supplier_concentration_type: concentration_not_established, likely_concentrated_supply_chain, import_dependency_or_domestic_substitution_scarcity.",
        "- supplier side audit columns: supplier_import_dependency_flag, supplier_domestic_substitute_count_bucket, supplier_concentration_bucket.",
        "- revenue_exposure_bucket: core_or_high_confidence_product_exposure, meaningful_segment_exposure, early_ramp_or_inflection_exposure, concept_or_indirect_exposure_review.",
        "",
        "## Top Review Rows",
        "",
    ]
    sample_columns = [
        "asset_id",
        "stock_name",
        "primary_chain_id",
        "customer_certification_stage",
        "supplier_concentration_type",
        "revenue_exposure_bucket",
        "method_evidence_readiness",
    ]
    lines.append(detail[sample_columns].head(30).to_markdown(index=False) if not detail.empty else "No rows.")
    lines.append("")
    return "\n".join(lines)


def _row_text(row: dict[str, Any]) -> str:
    return " ".join(
        [
            _text(row.get("stock_name")),
            _text(row.get("primary_chain_id")),
            _text(row.get("primary_chain_name")),
            _text(row.get("matched_bottleneck_dimensions")),
        ]
    ).lower()


def _has_any(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)
