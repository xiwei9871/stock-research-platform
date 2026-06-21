from pathlib import Path

import pandas as pd

from stock_research.serenity_method_evidence_fields import (
    build_serenity_method_evidence_fields,
)


def test_build_serenity_method_evidence_fields_splits_core_method_fields(tmp_path: Path):
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "first_hit_date": "2025-06-05",
                "primary_chain_id": "ai_optical_interconnect",
                "primary_chain_name": "AI 光模块/光通信",
                "matched_bottleneck_dimensions": "800G|1.6T|客户认证|交付周期",
                "hit_count": 8,
                "revenue_yoy": 32.1,
                "np_yoy": 45.2,
            },
            {
                "asset_id": "CN:SH:601939",
                "stock_name": "建设银行",
                "first_hit_date": "2025-08-01",
                "primary_chain_id": "robotics_core_components",
                "primary_chain_name": "机器人核心零部件",
                "matched_bottleneck_dimensions": "银行|金融服务",
                "hit_count": 1,
                "revenue_yoy": 1.0,
                "np_yoy": 1.0,
            },
            {
                "asset_id": "CN:SZ:002371",
                "stock_name": "北方华创",
                "first_hit_date": "2025-02-14",
                "primary_chain_id": "semiconductor_equipment",
                "primary_chain_name": "半导体设备",
                "matched_bottleneck_dimensions": "国产替代|刻蚀|薄膜沉积|长验证周期",
                "hit_count": 5,
                "revenue_yoy": 38.0,
                "np_yoy": 52.0,
            },
        ]
    )

    result = build_serenity_method_evidence_fields(
        candidates=candidates,
        output_dir=tmp_path,
        run_id="unit",
    )

    detail = result["detail"].set_index("asset_id")
    optical = detail.loc["CN:SZ:300308"]
    assert optical["customer_certification_stage"] == "order"
    assert optical["supplier_concentration_type"] == "likely_concentrated_supply_chain"
    assert optical["supplier_concentration_bucket"] == "concentrated_likely"
    assert optical["revenue_exposure_bucket"] == "core_or_high_confidence_product_exposure"
    assert optical["revenue_exposure_audit_rule"] == "core product-node chain plus direct bottleneck dimensions"

    bank = detail.loc["CN:SH:601939"]
    assert bank["customer_certification_stage"] == "not_identified"
    assert bank["supplier_concentration_type"] == "concentration_not_established"
    assert bank["supplier_import_dependency_flag"] == "not_established"
    assert bank["supplier_domestic_substitute_count_bucket"] == "not_established"
    assert bank["revenue_exposure_bucket"] == "concept_or_indirect_exposure_review"

    equipment = detail.loc["CN:SZ:002371"]
    assert equipment["customer_certification_stage"] == "certification"
    assert equipment["supplier_concentration_type"] == "import_dependency_or_domestic_substitution_scarcity"
    assert equipment["supplier_import_dependency_flag"] == "import_dependency_likely"
    assert equipment["supplier_domestic_substitute_count_bucket"] == "few_domestic_substitutes_likely"
    assert equipment["revenue_exposure_bucket"] == "meaningful_segment_exposure"
    assert equipment["customer_certification_needed_source_type"] == "customer certification/design-in/order evidence from reports, announcements, or investor Q&A"

    long = result["long"]
    assert set(long["field"]) == {
        "customer_certification_stage",
        "supplier_concentration_type",
        "revenue_exposure_bucket",
    }
    assert "source_provenance" in result["detail"].columns
    assert Path(result["paths"]["report"]).exists()
