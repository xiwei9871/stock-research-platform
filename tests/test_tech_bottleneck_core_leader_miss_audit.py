from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_core_leader_miss_audit import (
    build_core_leader_miss_audit,
    run_core_leader_miss_audit_from_files,
)


def test_build_core_leader_miss_audit_identifies_stage_and_reason() -> None:
    watchlist = pd.DataFrame(
        [
            {"asset_id": "CN:SH:688256", "stock_name": "寒武纪"},
            {"asset_id": "CN:SZ:300308", "stock_name": "中际旭创"},
            {"asset_id": "CN:SZ:300999", "stock_name": "缺席样本"},
        ]
    )
    candidates = pd.DataFrame(
        [
            {"asset_id": "CN:SH:688256", "stock_name": "寒武纪", "trade_date": "2025-08-22", "rank": 3},
            {"asset_id": "CN:SZ:300308", "stock_name": "中际旭创", "trade_date": "2025-06-13", "rank": 5},
        ]
    )
    gate = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688256",
                "stock_name": "寒武纪",
                "trade_date": "2025-08-22",
                "core_tech_gate": "reject",
                "core_tech_category": "no_core_technology_evidence",
                "gate_reason": "no core technology evidence",
                "matched_terms": "",
            },
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-13",
                "core_tech_gate": "pass",
                "core_tech_category": "optical_communication_components",
                "gate_reason": "core technology evidence",
                "matched_terms": "光模块",
            },
        ]
    )
    review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-13",
                "p3_decision": "reject_or_noise",
                "product_family": "",
                "product_linkage_quality": "missing",
                "bottleneck_quality": "missing",
                "technical_quality": "medium",
                "customer_quality": "medium",
                "capacity_quality": "strong",
                "catalyst_quality": "missing",
                "evidence_quality_score": 4,
                "decision_reason": "missing same-product-family linkage between product exposure and semantic evidence",
                "next_evidence_need": "replace generic product/OCR evidence with PIT-safe product-family evidence",
            }
        ]
    )

    audit = build_core_leader_miss_audit(
        watchlist=watchlist,
        candidates=candidates,
        gate=gate,
        quality_review=review,
    ).set_index("asset_id")

    assert audit.loc["CN:SH:688256", "fail_stage"] == "core_tech_gate"
    assert audit.loc["CN:SH:688256", "primary_reason"] == "no core technology evidence"
    assert audit.loc["CN:SZ:300308", "fail_stage"] == "quality_review"
    assert audit.loc["CN:SZ:300308", "primary_reason"] == "missing same-product-family linkage between product exposure and semantic evidence"
    assert audit.loc["CN:SZ:300999", "fail_stage"] == "not_in_top_candidates"


def test_run_core_leader_miss_audit_from_files_writes_artifacts(tmp_path: Path) -> None:
    watchlist_csv = tmp_path / "watchlist.csv"
    candidates_csv = tmp_path / "candidates.csv"
    gate_csv = tmp_path / "gate.csv"
    review_csv = tmp_path / "review.csv"
    watchlist_csv.write_text("asset_id,stock_name\nCN:SZ:002371,北方华创\n", encoding="utf-8")
    pd.DataFrame(
        [{"asset_id": "CN:SZ:002371", "stock_name": "北方华创", "trade_date": "2026-05-22", "rank": 1}]
    ).to_csv(candidates_csv, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002371",
                "stock_name": "北方华创",
                "trade_date": "2026-05-22",
                "core_tech_gate": "pass",
                "core_tech_category": "semiconductor_equipment",
                "gate_reason": "core technology evidence",
            }
        ]
    ).to_csv(gate_csv, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002371",
                "stock_name": "北方华创",
                "trade_date": "2026-05-22",
                "p3_decision": "needs_product_family_mapping",
                "product_family": "",
                "product_linkage_quality": "missing",
                "evidence_quality_score": 7,
                "decision_reason": "product and evidence are not linked by current product-family dictionary, but core evidence is not weak",
            }
        ]
    ).to_csv(review_csv, index=False)

    paths = run_core_leader_miss_audit_from_files(
        watchlist_csv=watchlist_csv,
        candidates_csv=candidates_csv,
        gate_csv=gate_csv,
        quality_review_csv=review_csv,
        output_dir=tmp_path / "out",
    )

    assert paths["audit"].exists()
    assert paths["summary"].exists()
    audit = pd.read_csv(paths["audit"])
    assert audit.iloc[0]["fail_stage"] == "p2_human_review"
