from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_core_tech_gate import (
    build_core_tech_gate,
    run_core_tech_gate_from_files,
)


def test_build_core_tech_gate_passes_semiconductor_testing_and_optical_communication_examples() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "测试设备",
                "trade_date": "2026/06/05",
                "rank": None,
                "industry_name": "半导体设备",
            },
            {
                "asset_id": "CN:SZ:300001",
                "stock_name": "光模块",
                "trade_date": "2026-06-06",
                "rank": 7,
                "industry_name": "通信设备",
            },
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "product_family": "semiconductor_testing_metrology",
                "evidence_snippet": "公司拥有晶圆检测和量测设备核心技术。",
                "matched_keyword": "晶圆检测",
            },
            {
                "asset_id": "CN:SZ:300001",
                "product_family": "",
                "evidence_snippet": "面向数据中心客户批量交付800G光模块和光引擎。",
                "matched_keyword": "光模块",
            },
        ]
    )

    outputs = build_core_tech_gate(candidates=candidates, evidence=evidence)
    gate = outputs["core_tech_gate"].set_index("asset_id")

    assert list(outputs["core_tech_gate"].columns) == [
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
    assert gate.loc["CN:SH:688001", "core_tech_gate"] == "pass"
    assert gate.loc["CN:SH:688001", "core_tech_category"] == "semiconductor_testing_metrology"
    assert gate.loc["CN:SH:688001", "trade_date"] == "2026-06-05"
    assert gate.loc["CN:SH:688001", "rank"] == 0
    assert "semiconductor_testing_metrology" in gate.loc["CN:SH:688001", "matched_terms"]

    assert gate.loc["CN:SZ:300001", "core_tech_gate"] == "pass"
    assert gate.loc["CN:SZ:300001", "core_tech_category"] == "optical_communication_components"
    assert "光模块" in gate.loc["CN:SZ:300001", "matched_terms"]


def test_build_core_tech_gate_rejects_excluded_industries_with_exact_reasons() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600000",
                "stock_name": "银行样本",
                "trade_date": "2026-06-05",
                "rank": 1,
                "industry_name": "银行",
            },
            {
                "asset_id": "CN:SH:600519",
                "stock_name": "白酒样本",
                "trade_date": "2026-06-05",
                "rank": 2,
                "industry_name": "白酒",
            },
            {
                "asset_id": "CN:SH:601006",
                "stock_name": "铁路样本",
                "trade_date": "2026-06-05",
                "rank": 3,
                "industry_name": "铁路运输",
            },
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600000",
                "product_family": "semiconductor_equipment",
                "evidence_snippet": "半导体设备",
                "matched_keyword": "半导体设备",
            },
            {
                "asset_id": "CN:SH:600519",
                "product_family": "optical_communication_components",
                "evidence_snippet": "光模块",
                "matched_keyword": "光模块",
            },
            {
                "asset_id": "CN:SH:601006",
                "product_family": "medical_imaging",
                "evidence_snippet": "医学影像",
                "matched_keyword": "医学影像",
            },
        ]
    )

    outputs = build_core_tech_gate(candidates=candidates, evidence=evidence)
    rows = outputs["core_tech_gate"].set_index("asset_id")

    assert rows.loc["CN:SH:600000", "core_tech_gate"] == "reject"
    assert rows.loc["CN:SH:600000", "gate_reason"] == "excluded industry: financials"
    assert rows.loc["CN:SH:600519", "core_tech_gate"] == "reject"
    assert rows.loc["CN:SH:600519", "gate_reason"] == "excluded industry: consumer"
    assert rows.loc["CN:SH:601006", "core_tech_gate"] == "reject"
    assert rows.loc["CN:SH:601006", "gate_reason"] == "excluded industry: infrastructure_or_cyclical"


def test_build_core_tech_gate_uses_point_in_time_evidence_per_candidate_date() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688123",
                "stock_name": "普通样本",
                "trade_date": "2025-01-03",
                "rank": 1,
                "industry_name": "综合",
            },
            {
                "asset_id": "CN:SH:688123",
                "stock_name": "普通样本",
                "trade_date": "2025-06-20",
                "rank": 2,
                "industry_name": "综合",
            },
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688123",
                "candidate_trade_date": "2025-06-20",
                "product_family": "semiconductor_equipment",
                "evidence_snippet": "公司披露半导体设备核心技术。",
                "matched_keyword": "半导体设备",
            }
        ]
    )

    outputs = build_core_tech_gate(candidates=candidates, evidence=evidence)
    rows = outputs["core_tech_gate"].set_index(["asset_id", "trade_date"])

    early = rows.loc[("CN:SH:688123", "2025-01-03")]
    later = rows.loc[("CN:SH:688123", "2025-06-20")]
    assert early["core_tech_gate"] == "reject"
    assert early["gate_reason"] == "no core technology evidence"
    assert later["core_tech_gate"] == "pass"
    assert later["core_tech_category"] == "semiconductor_equipment"


def test_run_core_tech_gate_from_files_writes_required_artifacts_and_manifest_counts(tmp_path: Path) -> None:
    candidates_path = tmp_path / "candidates.csv"
    evidence_path = tmp_path / "evidence.csv"
    output_dir = tmp_path / "out"
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "测试设备",
                "trade_date": "2026-06-05",
                "rank": 1,
                "industry_name": "半导体设备",
            },
            {
                "asset_id": "CN:SH:600000",
                "stock_name": "银行样本",
                "trade_date": "2026-06-05",
                "rank": None,
                "industry_name": "银行",
            },
            {
                "asset_id": "CN:SZ:300777",
                "stock_name": "普通样本",
                "trade_date": "2026-06-06",
                "rank": 3,
                "industry_name": "综合",
            },
        ]
    ).to_csv(candidates_path, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "product_family": "semiconductor_testing_metrology",
                "evidence_snippet": "半导体测试设备包含探针台和分选机。",
                "matched_keyword": "探针台",
            }
        ]
    ).to_csv(evidence_path, index=False)

    paths = run_core_tech_gate_from_files(
        candidates_csv=candidates_path,
        evidence_csv=evidence_path,
        output_dir=output_dir,
    )

    assert paths["core_tech_gate"] == output_dir / "core_tech_gate.csv"
    assert paths["core_tech_candidates"] == output_dir / "core_tech_candidates.csv"
    assert paths["summary"] == output_dir / "summary.md"
    assert paths["manifest"] == output_dir / "manifest.json"
    assert all(path.exists() for path in paths.values())

    gate = pd.read_csv(paths["core_tech_gate"])
    candidates = pd.read_csv(paths["core_tech_candidates"])
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert len(gate) == 3
    assert len(candidates) == 1
    assert manifest["candidate_count"] == 3
    assert manifest["asset_count"] == 3
    assert manifest["pass_count"] == 1
    assert manifest["reject_count"] == 2
    assert manifest["category_counts"] == {
        "excluded_financials": 1,
        "no_core_technology_evidence": 1,
        "semiconductor_testing_metrology": 1,
    }
    assert "core technology gate" in paths["summary"].read_text(encoding="utf-8")
