from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import stock_research.tech_bottleneck_core_tech_gate as core_tech_gate_module
from stock_research.cli import build_parser, main_for_args
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


def test_build_core_tech_gate_passes_core_leader_coverage_terms() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688256",
                "stock_name": "寒武纪",
                "trade_date": "2025-08-22",
                "rank": 3,
                "industry_name": "半导体",
                "product_snippet": "云端产品线 智能计算芯片 MLU",
            },
            {
                "asset_id": "CN:SZ:300476",
                "stock_name": "胜宏科技",
                "trade_date": "2025-07-04",
                "rank": 4,
                "industry_name": "电子元件",
                "product_snippet": "PCB制造 高阶HDI AI服务器PCB",
            },
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-13",
                "rank": 5,
                "industry_name": "通信设备",
                "product_snippet": "光通信收发模块 800G 1.6T",
            },
            {
                "asset_id": "CN:SZ:002371",
                "stock_name": "北方华创",
                "trade_date": "2026-05-22",
                "rank": 6,
                "industry_name": "半导体设备",
                "product_snippet": "电子工艺装备 半导体工艺装备",
            },
        ]
    )

    outputs = build_core_tech_gate(candidates=candidates, evidence=pd.DataFrame())
    rows = outputs["core_tech_gate"].set_index("asset_id")

    assert rows.loc["CN:SH:688256", "core_tech_gate"] == "pass"
    assert rows.loc["CN:SH:688256", "core_tech_category"] == "ai_compute_chips"
    assert rows.loc["CN:SZ:300476", "core_tech_category"] == "ai_server_high_speed_pcb"
    assert rows.loc["CN:SZ:300308", "core_tech_category"] == "optical_communication_components"
    assert rows.loc["CN:SZ:002371", "core_tech_category"] == "semiconductor_equipment"


def test_build_core_tech_gate_passes_chain_taxonomy_terms_without_generic_domestic_substitution() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "rank": 1,
                "industry_name": "通信设备",
                "product_snippet": "光通信模块 1.6T CPO 硅光",
            },
            {
                "asset_id": "CN:SH:688999",
                "stock_name": "HBM样本",
                "trade_date": "2025-06-20",
                "rank": 2,
                "industry_name": "半导体",
                "product_snippet": "HBM3E TSV 堆叠 后段产能",
            },
        ]
    )

    outputs = build_core_tech_gate(candidates=candidates, evidence=pd.DataFrame())
    rows = outputs["core_tech_gate"].set_index("asset_id")

    assert rows.loc["CN:SZ:300308", "core_tech_gate"] == "pass"
    assert rows.loc["CN:SZ:300308", "core_tech_category"] == "ai_optical_interconnect"
    assert rows.loc["CN:SH:688999", "core_tech_category"] == "hbm_high_end_memory"


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
                "evidence_date": "2025-06-20",
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


def test_build_core_tech_gate_normalizes_compact_dates_for_point_in_time_filtering() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688123",
                "stock_name": "普通样本",
                "trade_date": 20250620,
                "rank": 1,
                "industry_name": "综合",
            },
            {
                "asset_id": "CN:SH:688124",
                "stock_name": "浮点日期样本",
                "trade_date": 20250620.0,
                "rank": 2,
                "industry_name": "综合",
            },
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688123",
                "evidence_date": 20250701,
                "product_family": "semiconductor_equipment",
                "evidence_snippet": "公司披露半导体设备核心技术。",
                "matched_keyword": "半导体设备",
            },
            {
                "asset_id": "CN:SH:688124",
                "evidence_date": 20250620.0,
                "product_family": "semiconductor_equipment",
                "evidence_snippet": "公司披露半导体设备核心技术。",
                "matched_keyword": "半导体设备",
            },
        ]
    )

    outputs = build_core_tech_gate(candidates=candidates, evidence=evidence)
    rows = outputs["core_tech_gate"].set_index("asset_id")

    assert rows.loc["CN:SH:688123", "trade_date"] == "2025-06-20"
    assert rows.loc["CN:SH:688123", "core_tech_gate"] == "reject"
    assert rows.loc["CN:SH:688123", "gate_reason"] == "no core technology evidence"
    assert rows.loc["CN:SH:688124", "trade_date"] == "2025-06-20"
    assert rows.loc["CN:SH:688124", "core_tech_gate"] == "pass"
    assert rows.loc["CN:SH:688124", "core_tech_category"] == "semiconductor_equipment"


def test_build_core_tech_gate_excludes_candidate_scoped_evidence_without_availability_date() -> None:
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

    assert outputs["core_tech_gate"]["core_tech_gate"].tolist() == ["reject", "reject"]
    assert outputs["core_tech_gate"]["gate_reason"].tolist() == [
        "no core technology evidence",
        "no core technology evidence",
    ]


def test_build_core_tech_gate_uses_pit_safe_source_availability_dates() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688201",
                "stock_name": "未来披露样本",
                "trade_date": "2025-06-20",
                "rank": 1,
                "industry_name": "综合",
            },
            {
                "asset_id": "CN:SH:688202",
                "stock_name": "非安全样本",
                "trade_date": "2025-06-20",
                "rank": 2,
                "industry_name": "综合",
            },
            {
                "asset_id": "CN:SH:688203",
                "stock_name": "安全样本",
                "trade_date": "2025-06-20",
                "rank": 3,
                "industry_name": "综合",
            },
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688201",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-07-01",
                "as_of_safe": True,
                "product_family": "semiconductor_equipment",
                "evidence_snippet": "公司披露半导体设备核心技术。",
                "matched_keyword": "半导体设备",
            },
            {
                "asset_id": "CN:SH:688202",
                "evidence_date": "2025-06-01",
                "as_of_safe": "False",
                "product_family": "optical_communication_components",
                "evidence_snippet": "公司披露光模块核心技术。",
                "matched_keyword": "光模块",
            },
            {
                "asset_id": "CN:SH:688203",
                "evidence_date": "2025-06-01",
                "as_of_safe": True,
                "product_family": "medical_imaging",
                "evidence_snippet": "公司披露医学影像核心技术。",
                "matched_keyword": "医学影像",
            },
        ]
    )

    outputs = build_core_tech_gate(candidates=candidates, evidence=evidence)
    rows = outputs["core_tech_gate"].set_index("asset_id")

    assert rows.loc["CN:SH:688201", "core_tech_gate"] == "reject"
    assert rows.loc["CN:SH:688201", "gate_reason"] == "no core technology evidence"
    assert rows.loc["CN:SH:688202", "core_tech_gate"] == "reject"
    assert rows.loc["CN:SH:688202", "gate_reason"] == "no core technology evidence"
    assert rows.loc["CN:SH:688203", "core_tech_gate"] == "pass"
    assert rows.loc["CN:SH:688203", "core_tech_category"] == "medical_imaging"


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


def test_cli_parser_accepts_core_tech_gate_command() -> None:
    args = build_parser().parse_args(
        [
            "tech-bottleneck-core-tech-gate",
            "--candidates-csv",
            "candidates.csv",
            "--evidence-csv",
            "evidence.csv",
            "--output-dir",
            "out",
        ]
    )

    assert args.command == "tech-bottleneck-core-tech-gate"
    assert args.candidates_csv == "candidates.csv"
    assert args.evidence_csv == "evidence.csv"
    assert args.output_dir == "out"


def test_cli_parser_defaults_core_tech_gate_evidence_csv_to_none() -> None:
    args = build_parser().parse_args(
        [
            "tech-bottleneck-core-tech-gate",
            "--candidates-csv",
            "candidates.csv",
            "--output-dir",
            "out",
        ]
    )

    assert args.command == "tech-bottleneck-core-tech-gate"
    assert args.evidence_csv is None


def test_cli_dispatches_core_tech_gate(monkeypatch, capsys) -> None:
    calls = {}

    def fake_runner(**kwargs):
        calls["runner_kwargs"] = kwargs
        return {"gate": Path("out/core_tech_gate.csv")}

    monkeypatch.setattr(core_tech_gate_module, "run_core_tech_gate_from_files", fake_runner)

    main_for_args(
        [
            "tech-bottleneck-core-tech-gate",
            "--candidates-csv",
            "candidates.csv",
            "--evidence-csv",
            "evidence.csv",
            "--output-dir",
            "out",
        ]
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"gate": "out/core_tech_gate.csv"}
    assert calls["runner_kwargs"] == {
        "candidates_csv": Path("candidates.csv"),
        "evidence_csv": Path("evidence.csv"),
        "output_dir": Path("out"),
    }


def test_cli_dispatches_core_tech_gate_without_evidence_csv(monkeypatch, capsys) -> None:
    calls = {}

    def fake_runner(**kwargs):
        calls["runner_kwargs"] = kwargs
        return {"gate": Path("out/core_tech_gate.csv")}

    monkeypatch.setattr(core_tech_gate_module, "run_core_tech_gate_from_files", fake_runner)

    main_for_args(
        [
            "tech-bottleneck-core-tech-gate",
            "--candidates-csv",
            "candidates.csv",
            "--output-dir",
            "out",
        ]
    )

    capsys.readouterr()
    assert calls["runner_kwargs"] == {
        "candidates_csv": Path("candidates.csv"),
        "evidence_csv": None,
        "output_dir": Path("out"),
    }
