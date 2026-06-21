from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


CORE_CHAIN_PRIORITY = {
    "ai_optical_interconnect": 40,
    "semiconductor_equipment": 38,
    "ai_server_pcb": 36,
    "advanced_packaging_materials": 35,
    "semiconductor_materials": 34,
    "hbm_storage": 34,
    "mlcc_high_end_passives": 32,
    "high_end_sensors": 30,
    "robotics_core_components": 24,
    "liquid_cooling_thermal": 22,
    "power_grid_energy_infrastructure": 16,
    "power_delivery": 14,
}

FIELD_TASK_HINTS = {
    "revenue_exposure_bucket": "收入拆分 产品收入 分部收入 订单 backlog 年报",
    "customer_certification_stage": "客户认证 design-in 定点 量产 订单 交付 投资者关系",
    "supplier_concentration_type": "进口依赖 国产替代 供应商数量 市占率 份额 稀缺",
    "supplier_concentration_evidence": "进口依赖 国产替代 供应商数量 市占率 份额 稀缺",
}


def run_serenity_source_collection_plan(
    *,
    manual_queue_path: str | Path,
    structured_detail_path: str | Path,
    output_dir: str | Path,
    run_id: str = "serenity_source_collection_plan",
    max_assets: int | None = None,
) -> dict[str, Any]:
    manual_queue = pd.read_csv(manual_queue_path, low_memory=False)
    structured_detail = pd.read_csv(structured_detail_path, low_memory=False)
    return build_serenity_source_collection_plan(
        manual_queue=manual_queue,
        structured_detail=structured_detail,
        output_dir=output_dir,
        run_id=run_id,
        max_assets=max_assets,
    )


def build_serenity_source_collection_plan(
    *,
    manual_queue: pd.DataFrame,
    structured_detail: pd.DataFrame,
    output_dir: str | Path | None = None,
    run_id: str = "serenity_source_collection_plan",
    max_assets: int | None = None,
) -> dict[str, Any]:
    queue = _prepare_manual_queue(manual_queue)
    structured = _prepare_structured(structured_detail)
    asset_queue = _build_asset_queue(queue, structured)
    if max_assets is not None:
        asset_queue = asset_queue.head(max_assets).copy()
    collection_tasks = _build_collection_tasks(asset_queue, queue)
    yanbaoke_tasks = _build_yanbaoke_tasks(asset_queue)
    report = _render_report(asset_queue, collection_tasks, yanbaoke_tasks, run_id)

    paths: dict[str, str] = {}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        files = {
            "asset_queue": output / "serenity_source_collection_asset_queue.csv",
            "collection_tasks": output / "serenity_source_collection_tasks.csv",
            "yanbaoke_tasks": output / "serenity_yanbaoke_backfill_tasks.csv",
            "report": output / "serenity_source_collection_plan_report.md",
        }
        asset_queue.to_csv(files["asset_queue"], index=False)
        collection_tasks.to_csv(files["collection_tasks"], index=False)
        yanbaoke_tasks.to_csv(files["yanbaoke_tasks"], index=False)
        files["report"].write_text(report, encoding="utf-8")
        paths = {key: str(value) for key, value in files.items()}

    return {
        "asset_queue": asset_queue,
        "collection_tasks": collection_tasks,
        "yanbaoke_tasks": yanbaoke_tasks,
        "report": report,
        "paths": paths,
    }


def _prepare_manual_queue(frame: pd.DataFrame) -> pd.DataFrame:
    queue = frame.copy()
    for column in ["asset_id", "stock_name", "field", "inferred_value", "evidence_grade", "needed_source_type"]:
        if column not in queue.columns:
            queue[column] = ""
        queue[column] = queue[column].map(_text)
    return queue[queue["asset_id"].ne("")].reset_index(drop=True)


def _prepare_structured(frame: pd.DataFrame) -> pd.DataFrame:
    structured = frame.copy()
    for column in [
        "asset_id",
        "stock_name",
        "first_hit_date",
        "primary_chain_id",
        "primary_chain_name",
        "matched_bottleneck_dimensions",
    ]:
        if column not in structured.columns:
            structured[column] = ""
        structured[column] = structured[column].map(_text)
    return structured.drop_duplicates(subset=["asset_id"]).reset_index(drop=True)


def _build_asset_queue(queue: pd.DataFrame, structured: pd.DataFrame) -> pd.DataFrame:
    missing = (
        queue.groupby("asset_id")
        .agg(
            stock_name=("stock_name", "first"),
            missing_field_count=("field", "nunique"),
            missing_fields=("field", lambda values: "|".join(sorted(set(map(str, values))))),
            inferred_values=("inferred_value", lambda values: "|".join(sorted(set(v for v in map(str, values) if v)))),
        )
        .reset_index()
    )
    merged = missing.merge(
        structured[
            [
                "asset_id",
                "first_hit_date",
                "primary_chain_id",
                "primary_chain_name",
                "matched_bottleneck_dimensions",
            ]
        ],
        on="asset_id",
        how="left",
    )
    merged["ts_code"] = merged["asset_id"].map(_asset_id_to_ts_code)
    merged["chain_priority"] = merged["primary_chain_id"].map(lambda value: CORE_CHAIN_PRIORITY.get(_text(value), 10))
    merged["source_collection_priority"] = (
        merged["missing_field_count"].astype(float) * 30
        + merged["chain_priority"].astype(float)
        + merged["inferred_values"].map(_positive_inference_bonus)
    )
    return merged.sort_values(
        ["source_collection_priority", "missing_field_count", "asset_id"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def _build_collection_tasks(asset_queue: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    rows = []
    queue_by_asset = {asset_id: group for asset_id, group in queue.groupby("asset_id")}
    for asset in asset_queue.to_dict("records"):
        asset_id = _text(asset.get("asset_id"))
        field_rows = queue_by_asset.get(asset_id, queue.iloc[0:0])
        fields = sorted(set(field_rows["field"].map(_text)))
        query_hint = " ".join(FIELD_TASK_HINTS.get(field, field) for field in fields)
        stock_name = _text(asset.get("stock_name"))
        ts_code = _text(asset.get("ts_code"))
        base_query = " ".join(
            part
            for part in [
                stock_name,
                ts_code,
                _text(asset.get("primary_chain_name")),
                query_hint,
            ]
            if part
        )
        rows.extend(
            [
                _task(asset, "yanbaoke_broker_report", base_query, "broker reports and PDF text"),
                _task(asset, "cninfo_annual_report", f"{stock_name} 年报 主营业务 分产品收入 客户 供应商", "annual report or ESG filing"),
                _task(asset, "cninfo_announcement", f"{stock_name} 订单 合同 中标 客户认证 量产 交付 公告", "company announcements"),
                _task(asset, "investor_qa_or_news", f"{stock_name} 投资者关系 问答 客户 认证 国产替代 供应链", "investor Q&A or reputable news"),
            ]
        )
    return pd.DataFrame(rows)


def _task(asset: dict[str, Any], source_channel: str, query: str, source_goal: str) -> dict[str, Any]:
    return {
        "asset_id": _text(asset.get("asset_id")),
        "ts_code": _text(asset.get("ts_code")),
        "stock_name": _text(asset.get("stock_name")),
        "primary_chain_id": _text(asset.get("primary_chain_id")),
        "source_channel": source_channel,
        "query": query,
        "source_goal": source_goal,
        "status": "pending",
    }


def _build_yanbaoke_tasks(asset_queue: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in asset_queue.to_dict("records"):
        rows.append(
            {
                "asset_id": _text(row.get("asset_id")),
                "ts_code": _text(row.get("ts_code")),
                "stock_name": _text(row.get("stock_name")),
                "start_date": "2024-01-01",
                "end_date": "2026-06-08",
                "status": "pending",
                "source_collection_priority": row.get("source_collection_priority"),
            }
        )
    return pd.DataFrame(rows)


def _render_report(asset_queue: pd.DataFrame, collection_tasks: pd.DataFrame, yanbaoke_tasks: pd.DataFrame, run_id: str) -> str:
    lines = [
        "# Serenity Source Collection Plan",
        "",
        f"Run ID: `{run_id}`",
        "",
        f"- target_assets: {len(asset_queue)}",
        f"- collection_tasks: {len(collection_tasks)}",
        f"- yanbaoke_tasks: {len(yanbaoke_tasks)}",
        "",
        "## Top Asset Queue",
        "",
        asset_queue.head(40).to_markdown(index=False) if not asset_queue.empty else "No rows.",
        "",
        "## Source Channels",
        "",
        collection_tasks["source_channel"].value_counts().rename_axis("source_channel").reset_index(name="task_count").to_markdown(index=False)
        if not collection_tasks.empty
        else "No rows.",
        "",
    ]
    return "\n".join(lines)


def _asset_id_to_ts_code(asset_id: str) -> str:
    parts = _text(asset_id).split(":")
    if len(parts) != 3:
        return ""
    exchange = parts[1]
    code = parts[2]
    suffix = "SZ" if exchange == "SZ" else "SH" if exchange == "SH" else exchange
    return f"{code}.{suffix}" if code and suffix else ""


def _positive_inference_bonus(values: str) -> float:
    text = _text(values)
    bonus = 0.0
    for keyword in [
        "core_or_high_confidence_product_exposure",
        "meaningful_segment_exposure",
        "order",
        "mass_production",
        "certification",
        "import_dependency_or_domestic_substitution_scarcity",
        "likely_concentrated_supply_chain",
    ]:
        if keyword in text:
            bonus += 4.0
    return min(bonus, 16.0)


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()
