from pathlib import Path

import pandas as pd

from stock_research.serenity_source_collection_plan import build_serenity_source_collection_plan


def test_source_collection_plan_prioritizes_all_artifact_core_tech_and_writes_tasks(tmp_path: Path):
    manual_queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "field": "revenue_exposure_bucket",
                "inferred_value": "core_or_high_confidence_product_exposure",
                "evidence_grade": "artifact_only",
                "needed_source_type": "annual report segment revenue",
            },
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "field": "customer_certification_stage",
                "inferred_value": "order",
                "evidence_grade": "artifact_only",
                "needed_source_type": "customer order evidence",
            },
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "field": "supplier_concentration_type",
                "inferred_value": "likely_concentrated_supply_chain",
                "evidence_grade": "artifact_only",
                "needed_source_type": "supplier count",
            },
            {
                "asset_id": "CN:SH:601939",
                "stock_name": "建设银行",
                "field": "revenue_exposure_bucket",
                "inferred_value": "concept_or_indirect_exposure_review",
                "evidence_grade": "artifact_only",
                "needed_source_type": "product revenue",
            },
        ]
    )
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "first_hit_date": "2025-04-01",
                "primary_chain_id": "ai_optical_interconnect",
                "primary_chain_name": "AI 光模块/光通信",
                "matched_bottleneck_dimensions": "800G|1.6T|客户认证|交付",
            },
            {
                "asset_id": "CN:SH:601939",
                "stock_name": "建设银行",
                "first_hit_date": "2025-08-01",
                "primary_chain_id": "robotics_core_components",
                "primary_chain_name": "机器人核心零部件",
                "matched_bottleneck_dimensions": "银行|金融服务",
            },
        ]
    )

    result = build_serenity_source_collection_plan(
        manual_queue=manual_queue,
        structured_detail=structured,
        output_dir=tmp_path,
        run_id="unit",
        max_assets=10,
    )

    assets = result["asset_queue"].set_index("asset_id")
    assert assets.index.tolist()[0] == "CN:SZ:300308"
    assert assets.loc["CN:SZ:300308", "missing_field_count"] == 3
    assert assets.loc["CN:SZ:300308", "source_collection_priority"] > assets.loc["CN:SH:601939", "source_collection_priority"]

    tasks = result["collection_tasks"]
    optical_tasks = tasks[tasks["asset_id"].eq("CN:SZ:300308")]
    assert set(optical_tasks["source_channel"]) >= {
        "yanbaoke_broker_report",
        "cninfo_annual_report",
        "cninfo_announcement",
        "investor_qa_or_news",
    }
    assert "收入拆分" in " ".join(optical_tasks["query"].tolist())

    yanbaoke = result["yanbaoke_tasks"].set_index("asset_id")
    assert yanbaoke.loc["CN:SZ:300308", "ts_code"] == "300308.SZ"
    assert yanbaoke.loc["CN:SZ:300308", "status"] == "pending"
    assert Path(result["paths"]["yanbaoke_tasks"]).exists()
