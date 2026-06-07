# Tech Bottleneck Core Tech Top100 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `tech_bottleneck_core_tech_top100` experiment that expands the candidate pool to top100, filters for core technology sectors, and outputs P1/P2/P3 queues plus a top50 baseline comparison.

**Architecture:** Add a small deterministic core-tech gate module and a top100 experiment orchestration module. Reuse the existing `tech_bottleneck_quality_review` evidence-chain logic rather than changing strict P1 rules. Keep outputs file-based under `outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/`.

**Tech Stack:** Python, pandas, pytest, existing `stock_research` modules, CSV/JSON/Markdown artifacts.

---

## File Structure

- Create `src/stock_research/tech_bottleneck_core_tech_gate.py`
  - Classifies candidate rows as core-tech pass/reject using industry text, product family, product/evidence snippets, and deterministic keyword families.
  - Writes `core_tech_gate.csv`, `core_tech_candidates.csv`, `summary.md`, and `manifest.json`.

- Create `src/stock_research/tech_bottleneck_core_tech_top100.py`
  - Builds weekly top100 candidates from score rows supplied as a DataFrame or CSV.
  - Joins gate output, quality review output, and baseline top50 output.
  - Writes experiment artifacts including `top50_vs_top100_diff.csv` and `baseline_comparison.md`.

- Modify `src/stock_research/tech_bottleneck_quality_review.py`
  - Add machine-readable `next_evidence_need` values for P2 rows while preserving current P1 strict rules.
  - Do not loosen `auto_approve`.

- Modify `src/stock_research/cli.py`
  - Add file-based commands for the core-tech gate and core-tech top100 comparison so the experiment is runnable without notebooks.

- Add `tests/test_tech_bottleneck_core_tech_gate.py`
  - Unit tests for pass/reject categories and artifact writing.

- Add `tests/test_tech_bottleneck_core_tech_top100.py`
  - Unit tests for weekly top100 selection, top50-vs-top100 diffing, P1/P2/P3 summaries, and CLI parsing.

- Modify `tests/test_tech_bottleneck_quality_review.py`
  - Add tests for machine-readable P2 evidence needs.

---

### Task 1: Core-Tech Gate

**Files:**
- Create: `src/stock_research/tech_bottleneck_core_tech_gate.py`
- Create: `tests/test_tech_bottleneck_core_tech_gate.py`

- [ ] **Step 1: Write the failing core-tech gate tests**

Create `tests/test_tech_bottleneck_core_tech_gate.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_core_tech_gate import (
    build_core_tech_gate,
    run_core_tech_gate_from_files,
)


def test_build_core_tech_gate_passes_semiconductor_and_optical_names() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688361",
                "stock_name": "中科飞测",
                "trade_date": "2025-10-10",
                "rank": 42,
                "industry_name": "半导体设备",
            },
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "trade_date": "2025-06-20",
                "rank": 78,
                "industry_name": "通信设备",
            },
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688361",
                "trade_date": "2025-10-10",
                "evidence_type": "product_revenue_exposure",
                "product_family": "semiconductor_testing_metrology",
                "evidence_snippet": "晶圆检测设备收入增长",
            },
            {
                "asset_id": "CN:SZ:300394",
                "trade_date": "2025-06-20",
                "evidence_type": "bottleneck_keyword",
                "product_family": "optical_communication_components",
                "evidence_snippet": "高速光器件和光模块核心部件",
            },
        ]
    )

    result = build_core_tech_gate(candidates=candidates, evidence=evidence)
    gate = result["core_tech_gate"].set_index("asset_id")

    assert gate.loc["CN:SH:688361", "core_tech_gate"] == "pass"
    assert gate.loc["CN:SH:688361", "core_tech_category"] == "semiconductor_testing_metrology"
    assert gate.loc["CN:SZ:300394", "core_tech_gate"] == "pass"
    assert gate.loc["CN:SZ:300394", "core_tech_category"] == "optical_communication_components"
    assert result["manifest"]["pass_count"] == 2


def test_build_core_tech_gate_rejects_financial_consumer_and_generic_cyclicals() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600919",
                "stock_name": "江苏银行",
                "trade_date": "2025-01-03",
                "rank": 3,
                "industry_name": "银行",
            },
            {
                "asset_id": "CN:SZ:002847",
                "stock_name": "盐津铺子",
                "trade_date": "2025-01-03",
                "rank": 7,
                "industry_name": "食品饮料",
            },
            {
                "asset_id": "CN:SH:601919",
                "stock_name": "中远海控",
                "trade_date": "2025-01-03",
                "rank": 37,
                "industry_name": "航运港口",
            },
        ]
    )

    result = build_core_tech_gate(candidates=candidates, evidence=pd.DataFrame())
    gate = result["core_tech_gate"].set_index("asset_id")

    assert gate.loc["CN:SH:600919", "core_tech_gate"] == "reject"
    assert gate.loc["CN:SH:600919", "gate_reason"] == "excluded industry: financials"
    assert gate.loc["CN:SZ:002847", "gate_reason"] == "excluded industry: consumer"
    assert gate.loc["CN:SH:601919", "gate_reason"] == "excluded industry: infrastructure_or_cyclical"
    assert result["manifest"]["reject_count"] == 3


def test_run_core_tech_gate_from_files_writes_artifacts(tmp_path: Path) -> None:
    candidates_csv = tmp_path / "candidates.csv"
    evidence_csv = tmp_path / "evidence.csv"
    output_dir = tmp_path / "gate"
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "stock_name": "洁美科技",
                "trade_date": "2026-05-29",
                "rank": 56,
                "industry_name": "电子元件",
            }
        ]
    ).to_csv(candidates_csv, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "trade_date": "2026-05-29",
                "evidence_type": "product_revenue_exposure",
                "product_family": "semiconductor_materials_components",
                "evidence_snippet": "半导体载带和离型膜",
            }
        ]
    ).to_csv(evidence_csv, index=False)

    paths = run_core_tech_gate_from_files(
        candidates_csv=candidates_csv,
        evidence_csv=evidence_csv,
        output_dir=output_dir,
    )

    assert paths["core_tech_gate"] == output_dir / "core_tech_gate.csv"
    assert paths["core_tech_candidates"] == output_dir / "core_tech_candidates.csv"
    assert paths["summary"].exists()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["candidate_count"] == 1
    assert manifest["pass_count"] == 1
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_core_tech_gate.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'stock_research.tech_bottleneck_core_tech_gate'`.

- [ ] **Step 3: Implement the core-tech gate module**

Create `src/stock_research/tech_bottleneck_core_tech_gate.py` with:

```python
from __future__ import annotations

import json
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

PASS_PRODUCT_FAMILIES = {
    "semiconductor_equipment",
    "semiconductor_testing_metrology",
    "semiconductor_materials_components",
    "oled_display_materials",
    "optical_communication_components",
    "electronic_ceramics_mlcc",
    "advanced_medical_devices",
    "advanced_fluorochemicals_materials",
    "advanced_polymer_materials",
    "advanced_magnetic_materials",
    "image_sensor_semiconductors",
    "cloud_data_infrastructure",
    "medical_imaging",
}

PASS_TERMS = {
    "semiconductor_testing_metrology": ["晶圆检测", "量测", "测试设备", "探针台", "分选机"],
    "semiconductor_equipment": ["半导体设备", "刻蚀", "薄膜沉积", "清洗设备", "涂胶显影"],
    "semiconductor_materials_components": ["半导体材料", "载带", "离型膜", "靶材", "封装材料"],
    "optical_communication_components": ["光模块", "光器件", "光芯片", "CPO", "光引擎"],
    "advanced_medical_devices": ["医学影像", "数字化X射线", "植入", "高端医疗器械"],
    "electronic_ceramics_mlcc": ["MLCC", "电子陶瓷", "高频基板"],
    "cloud_data_infrastructure": ["AI基础设施", "数据中心", "工业软件", "云基础设施"],
}

REJECT_INDUSTRY_TERMS = [
    ("financials", ["银行", "保险", "证券", "多元金融"]),
    ("consumer", ["食品", "饮料", "宠物", "服装", "家居", "白酒", "乳品", "餐饮"]),
    ("infrastructure_or_cyclical", ["高速", "港口", "航运", "煤炭", "电力", "燃气", "公路", "铁路"]),
]


def build_core_tech_gate(*, candidates: pd.DataFrame, evidence: pd.DataFrame | None) -> dict[str, Any]:
    normalized = _normalize_candidates(candidates)
    evidence_text = _evidence_text_by_asset(evidence)
    rows: list[dict[str, Any]] = []
    for row in normalized.to_dict("records"):
        asset_id = row["asset_id"]
        text = " ".join(
            [
                row.get("stock_name", ""),
                row.get("industry_name", ""),
                evidence_text.get(asset_id, ""),
            ]
        )
        decision = _classify_row(text=text, industry_name=row.get("industry_name", ""))
        rows.append({**row, **decision})
    gate = pd.DataFrame(rows, columns=CORE_TECH_GATE_COLUMNS)
    core = gate[gate["core_tech_gate"].eq("pass")].copy()
    manifest = {
        "candidate_count": int(len(gate)),
        "asset_count": int(gate["asset_id"].nunique()) if not gate.empty else 0,
        "pass_count": int(len(core)),
        "reject_count": int(gate["core_tech_gate"].eq("reject").sum()) if not gate.empty else 0,
        "category_counts": gate["core_tech_category"].value_counts().to_dict() if not gate.empty else {},
    }
    return {"core_tech_gate": gate, "core_tech_candidates": core, "manifest": manifest}


def run_core_tech_gate_from_files(*, candidates_csv: Path, evidence_csv: Path | None, output_dir: Path) -> dict[str, Path]:
    candidates = pd.read_csv(candidates_csv)
    evidence = pd.read_csv(evidence_csv) if evidence_csv and evidence_csv.exists() else pd.DataFrame()
    outputs = build_core_tech_gate(candidates=candidates, evidence=evidence)
    return write_core_tech_gate_artifacts(
        outputs=outputs,
        output_dir=output_dir,
        inputs={"candidates_csv": str(candidates_csv), "evidence_csv": str(evidence_csv) if evidence_csv else ""},
    )


def write_core_tech_gate_artifacts(*, outputs: dict[str, Any], output_dir: Path, inputs: dict[str, Any]) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    gate_path = output_dir / "core_tech_gate.csv"
    candidates_path = output_dir / "core_tech_candidates.csv"
    summary_path = output_dir / "summary.md"
    manifest_path = output_dir / "manifest.json"
    outputs["core_tech_gate"].to_csv(gate_path, index=False)
    outputs["core_tech_candidates"].to_csv(candidates_path, index=False)
    manifest = {**outputs["manifest"], "inputs": inputs, "files": {"core_tech_gate": gate_path.name, "core_tech_candidates": candidates_path.name, "summary": summary_path.name}}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(_render_summary(manifest), encoding="utf-8")
    return {"core_tech_gate": gate_path, "core_tech_candidates": candidates_path, "summary": summary_path, "manifest": manifest_path}


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    normalized = candidates.copy()
    for column in ["asset_id", "stock_name", "trade_date", "rank", "industry_name"]:
        if column not in normalized.columns:
            normalized[column] = 0 if column == "rank" else ""
    normalized["asset_id"] = normalized["asset_id"].astype("string").fillna("")
    normalized["stock_name"] = normalized["stock_name"].astype("string").fillna("")
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    normalized["rank"] = pd.to_numeric(normalized["rank"], errors="coerce").fillna(0).astype(int)
    normalized["industry_name"] = normalized["industry_name"].astype("string").fillna("")
    return normalized[normalized["asset_id"].ne("") & normalized["trade_date"].ne("")].copy()


def _evidence_text_by_asset(evidence: pd.DataFrame | None) -> dict[str, str]:
    if evidence is None or evidence.empty or "asset_id" not in evidence.columns:
        return {}
    frame = evidence.copy()
    for column in ["product_family", "evidence_snippet", "matched_keyword"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["text"] = (
        frame["product_family"].astype("string").fillna("")
        + " "
        + frame["evidence_snippet"].astype("string").fillna("")
        + " "
        + frame["matched_keyword"].astype("string").fillna("")
    )
    return frame.groupby("asset_id", sort=False)["text"].apply(lambda values: " ".join(values.astype(str))).to_dict()


def _classify_row(*, text: str, industry_name: str) -> dict[str, str]:
    for reject_category, terms in REJECT_INDUSTRY_TERMS:
        if any(term in industry_name for term in terms):
            return {
                "core_tech_gate": "reject",
                "core_tech_category": "",
                "gate_reason": f"excluded industry: {reject_category}",
                "matched_terms": "|".join(term for term in terms if term in industry_name),
            }
    for family in PASS_PRODUCT_FAMILIES:
        if family in text:
            return {
                "core_tech_gate": "pass",
                "core_tech_category": family,
                "gate_reason": "matched core product family",
                "matched_terms": family,
            }
    for family, terms in PASS_TERMS.items():
        matched = [term for term in terms if term in text]
        if matched:
            return {
                "core_tech_gate": "pass",
                "core_tech_category": family,
                "gate_reason": "matched core technology terms",
                "matched_terms": "|".join(matched),
            }
    return {
        "core_tech_gate": "reject",
        "core_tech_category": "",
        "gate_reason": "no core technology evidence",
        "matched_terms": "",
    }


def _render_summary(manifest: dict[str, Any]) -> str:
    lines = [
        "# tech-bottleneck core-tech gate",
        "",
        f"- candidate_count: {manifest.get('candidate_count', 0)}",
        f"- asset_count: {manifest.get('asset_count', 0)}",
        f"- pass_count: {manifest.get('pass_count', 0)}",
        f"- reject_count: {manifest.get('reject_count', 0)}",
        "",
        "## Categories",
    ]
    for category, count in manifest.get("category_counts", {}).items():
        lines.append(f"- {category}: {count}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run the gate tests and verify they pass**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_core_tech_gate.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/stock_research/tech_bottleneck_core_tech_gate.py tests/test_tech_bottleneck_core_tech_gate.py
git commit -m "feat: add tech bottleneck core tech gate"
```

---

### Task 2: Machine-Readable P2 Evidence Needs

**Files:**
- Modify: `src/stock_research/tech_bottleneck_quality_review.py`
- Modify: `tests/test_tech_bottleneck_quality_review.py`

- [ ] **Step 1: Add failing tests for P2 evidence need labels**

Append to `tests/test_tech_bottleneck_quality_review.py`:

```python
def test_quality_review_labels_mapping_gap_with_machine_readable_need() -> None:
    review = build_quality_review(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688150",
                    "stock_name": "莱特光电",
                    "trade_date": "2025-07-11",
                }
            ]
        ),
        evidence_hits=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688150",
                    "stock_name": "莱特光电",
                    "candidate_trade_date": "2025-07-11",
                    "evidence_type": "bottleneck_keyword",
                    "evidence_snippet": "OLED终端材料国产替代",
                    "matched_keyword": "国产替代",
                },
                {
                    "asset_id": "CN:SH:688150",
                    "stock_name": "莱特光电",
                    "candidate_trade_date": "2025-07-11",
                    "evidence_type": "technical_barrier",
                    "evidence_snippet": "发光材料专利壁垒",
                    "matched_keyword": "专利",
                },
                {
                    "asset_id": "CN:SH:688150",
                    "stock_name": "莱特光电",
                    "candidate_trade_date": "2025-07-11",
                    "evidence_type": "capacity",
                    "evidence_snippet": "OLED材料产能建设",
                    "matched_keyword": "产能",
                },
            ]
        ),
        product_rows=pd.DataFrame(),
    )

    row = review.iloc[0]
    assert row["p3_decision"] == "needs_product_family_mapping"
    assert row["next_evidence_need"] == "needs_product_family_mapping"


def test_quality_review_labels_missing_support_evidence_need() -> None:
    review = build_quality_review(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SZ:301369",
                    "stock_name": "联动科技",
                    "trade_date": "2025-12-19",
                }
            ]
        ),
        evidence_hits=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SZ:301369",
                    "stock_name": "联动科技",
                    "candidate_trade_date": "2025-12-19",
                    "evidence_type": "product_revenue_exposure",
                    "evidence_snippet": "半导体测试设备收入",
                    "matched_keyword": "半导体测试设备",
                },
                {
                    "asset_id": "CN:SZ:301369",
                    "stock_name": "联动科技",
                    "candidate_trade_date": "2025-12-19",
                    "evidence_type": "bottleneck_keyword",
                    "evidence_snippet": "半导体测试设备国产替代",
                    "matched_keyword": "国产替代",
                },
                {
                    "asset_id": "CN:SZ:301369",
                    "stock_name": "联动科技",
                    "candidate_trade_date": "2025-12-19",
                    "evidence_type": "technical_barrier",
                    "evidence_snippet": "半导体测试设备技术壁垒",
                    "matched_keyword": "技术壁垒",
                },
            ]
        ),
        product_rows=pd.DataFrame(),
    )

    row = review.iloc[0]
    assert row["p3_decision"] == "needs_more_evidence"
    assert row["next_evidence_need"] == "needs_customer_or_certification_evidence|needs_capacity_evidence|needs_catalyst_evidence"
```

- [ ] **Step 2: Run the new focused tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_quality_review.py::test_quality_review_labels_mapping_gap_with_machine_readable_need tests/test_tech_bottleneck_quality_review.py::test_quality_review_labels_missing_support_evidence_need -q
```

Expected: tests fail because `next_evidence_need` is currently prose.

- [ ] **Step 3: Implement P2 evidence need labels**

In `src/stock_research/tech_bottleneck_quality_review.py`, update the decision branch that creates `needs_product_family_mapping` rows so it sets:

```python
next_evidence_need = "needs_product_family_mapping"
```

Update the branch that creates `needs_more_evidence` rows so it builds missing support labels:

```python
support_needs = []
if customer_quality in {"missing", "weak"}:
    support_needs.append("needs_customer_or_certification_evidence")
if capacity_quality in {"missing", "weak"}:
    support_needs.append("needs_capacity_evidence")
if catalyst_quality in {"missing", "weak"}:
    support_needs.append("needs_catalyst_evidence")
next_evidence_need = "|".join(support_needs) or "needs_pit_safe_source"
```

Do not change the `auto_approve` condition.

- [ ] **Step 4: Run quality review tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_quality_review.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/stock_research/tech_bottleneck_quality_review.py tests/test_tech_bottleneck_quality_review.py
git commit -m "feat: label tech bottleneck evidence gaps"
```

---

### Task 3: Top100 Candidate Selection and Comparison Builder

**Files:**
- Create: `src/stock_research/tech_bottleneck_core_tech_top100.py`
- Create: `tests/test_tech_bottleneck_core_tech_top100.py`

- [ ] **Step 1: Write failing tests for top100 selection and diffing**

Create `tests/test_tech_bottleneck_core_tech_top100.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_core_tech_top100 import (
    build_baseline_comparison,
    build_weekly_topn_candidates,
    run_core_tech_top100_from_files,
)


def test_build_weekly_topn_candidates_keeps_top100_per_week_and_top50_flag() -> None:
    score_rows = pd.DataFrame(
        [
            {"trade_date": "2025-01-03", "asset_id": f"A{i:03d}", "stock_name": f"票{i}", "score": 200 - i}
            for i in range(1, 106)
        ]
        + [
            {"trade_date": "2025-01-10", "asset_id": f"B{i:03d}", "stock_name": f"股{i}", "score": 300 - i}
            for i in range(1, 103)
        ]
    )

    candidates = build_weekly_topn_candidates(score_rows=score_rows, top_n=100)

    assert len(candidates) == 200
    assert candidates[candidates["trade_date"].eq("2025-01-03")]["rank"].max() == 100
    assert candidates[candidates["trade_date"].eq("2025-01-10")]["rank"].max() == 100
    assert candidates[candidates["asset_id"].eq("A050")].iloc[0]["in_top50_baseline"] is True
    assert candidates[candidates["asset_id"].eq("A051")].iloc[0]["in_top50_baseline"] is False


def test_build_baseline_comparison_reports_new_top100_p1_and_p2_names() -> None:
    top100_candidates = pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "旧P1", "trade_date": "2025-01-03", "rank": 20, "in_top50_baseline": True},
            {"asset_id": "B", "stock_name": "新增P1", "trade_date": "2025-01-03", "rank": 75, "in_top50_baseline": False},
            {"asset_id": "C", "stock_name": "新增P2", "trade_date": "2025-01-03", "rank": 88, "in_top50_baseline": False},
        ]
    )
    quality_review = pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "旧P1", "trade_date": "2025-01-03", "p3_decision": "auto_approve", "evidence_quality_score": 12},
            {"asset_id": "B", "stock_name": "新增P1", "trade_date": "2025-01-03", "p3_decision": "auto_approve", "evidence_quality_score": 11},
            {"asset_id": "C", "stock_name": "新增P2", "trade_date": "2025-01-03", "p3_decision": "needs_more_evidence", "evidence_quality_score": 8},
        ]
    )
    baseline_promotions = pd.DataFrame(
        [{"asset_id": "A", "stock_name": "旧P1", "trade_date": "2025-01-03"}]
    )

    result = build_baseline_comparison(
        top100_candidates=top100_candidates,
        quality_review=quality_review,
        baseline_promotions=baseline_promotions,
    )

    diff = result["top50_vs_top100_diff"].set_index("asset_id")
    assert diff.loc["B", "top100_increment_status"] == "new_p1_auto_promotion"
    assert diff.loc["C", "top100_increment_status"] == "new_p2_research_queue"
    assert result["manifest"]["new_p1_from_rank_51_100"] == 1
    assert result["manifest"]["new_p2_from_rank_51_100"] == 1
    assert "Top100 core-tech P1 asset count: 2" in result["baseline_comparison_md"]


def test_run_core_tech_top100_from_files_writes_comparison_artifacts(tmp_path: Path) -> None:
    scores_csv = tmp_path / "scores.csv"
    quality_review_csv = tmp_path / "quality_review.csv"
    baseline_promotions_csv = tmp_path / "baseline_promotions.csv"
    output_dir = tmp_path / "out"
    pd.DataFrame(
        [
            {"trade_date": "2025-01-03", "asset_id": f"A{i:03d}", "stock_name": f"票{i}", "score": 100 - i}
            for i in range(1, 55)
        ]
    ).to_csv(scores_csv, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "A052",
                "stock_name": "新增科技",
                "trade_date": "2025-01-03",
                "p3_decision": "auto_approve",
                "evidence_quality_score": 11,
                "next_evidence_need": "",
            }
        ]
    ).to_csv(quality_review_csv, index=False)
    pd.DataFrame(columns=["asset_id", "stock_name", "trade_date"]).to_csv(baseline_promotions_csv, index=False)

    paths = run_core_tech_top100_from_files(
        scores_csv=scores_csv,
        quality_review_csv=quality_review_csv,
        baseline_promotions_csv=baseline_promotions_csv,
        output_dir=output_dir,
        top_n=100,
    )

    assert paths["candidates_top100"].exists()
    assert paths["top50_vs_top100_diff"].exists()
    assert paths["baseline_comparison"].exists()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["top100_candidate_count"] == 54
    assert manifest["new_p1_from_rank_51_100"] == 1
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_core_tech_top100.py -q
```

Expected: fails with missing module.

- [ ] **Step 3: Implement top100 experiment helpers**

Create `src/stock_research/tech_bottleneck_core_tech_top100.py` with functions:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def build_weekly_topn_candidates(*, score_rows: pd.DataFrame, top_n: int = 100) -> pd.DataFrame:
    frame = score_rows.copy()
    for column in ["trade_date", "asset_id", "stock_name", "score"]:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "asset_id", "score"])
    frame = frame.sort_values(["trade_date", "score", "asset_id"], ascending=[True, False, True]).copy()
    frame["rank"] = frame.groupby("trade_date").cumcount() + 1
    frame = frame[frame["rank"].le(top_n)].copy()
    frame["in_top50_baseline"] = frame["rank"].le(50).astype(object)
    return frame.reset_index(drop=True)


def build_baseline_comparison(
    *,
    top100_candidates: pd.DataFrame,
    quality_review: pd.DataFrame,
    baseline_promotions: pd.DataFrame,
) -> dict[str, Any]:
    candidates = top100_candidates.copy()
    review = quality_review.copy()
    baseline_ids = set(baseline_promotions.get("asset_id", pd.Series(dtype=str)).astype(str))
    merged = candidates.merge(
        review,
        on=["asset_id", "stock_name", "trade_date"],
        how="left",
        suffixes=("", "_review"),
    )
    merged["p3_decision"] = merged["p3_decision"].fillna("not_reviewed")
    merged["in_top50_baseline"] = merged["in_top50_baseline"].astype(bool)
    merged["in_baseline_p1"] = merged["asset_id"].astype(str).isin(baseline_ids)
    merged["top100_increment_status"] = merged.apply(_increment_status, axis=1)
    diff = merged[~merged["in_top50_baseline"]].copy()
    p1_assets = merged[merged["p3_decision"].eq("auto_approve")]["asset_id"].nunique()
    p2_assets = merged[merged["p3_decision"].isin(["needs_more_evidence", "needs_product_family_mapping"])]["asset_id"].nunique()
    manifest = {
        "top100_candidate_count": int(len(candidates)),
        "top100_asset_count": int(candidates["asset_id"].nunique()) if not candidates.empty else 0,
        "baseline_p1_asset_count": int(len(baseline_ids)),
        "top100_p1_asset_count": int(p1_assets),
        "top100_p2_asset_count": int(p2_assets),
        "new_p1_from_rank_51_100": int(diff["top100_increment_status"].eq("new_p1_auto_promotion").sum()),
        "new_p2_from_rank_51_100": int(diff["top100_increment_status"].eq("new_p2_research_queue").sum()),
    }
    markdown = _render_baseline_comparison(manifest)
    return {"top50_vs_top100_diff": diff, "manifest": manifest, "baseline_comparison_md": markdown}


def run_core_tech_top100_from_files(
    *,
    scores_csv: Path,
    quality_review_csv: Path,
    baseline_promotions_csv: Path,
    output_dir: Path,
    top_n: int = 100,
) -> dict[str, Path]:
    scores = pd.read_csv(scores_csv)
    quality_review = pd.read_csv(quality_review_csv)
    baseline_promotions = pd.read_csv(baseline_promotions_csv)
    candidates = build_weekly_topn_candidates(score_rows=scores, top_n=top_n)
    comparison = build_baseline_comparison(
        top100_candidates=candidates,
        quality_review=quality_review,
        baseline_promotions=baseline_promotions,
    )
    return write_core_tech_top100_artifacts(
        candidates_top100=candidates,
        comparison=comparison,
        output_dir=output_dir,
        inputs={
            "scores_csv": str(scores_csv),
            "quality_review_csv": str(quality_review_csv),
            "baseline_promotions_csv": str(baseline_promotions_csv),
            "top_n": top_n,
        },
    )


def write_core_tech_top100_artifacts(
    *,
    candidates_top100: pd.DataFrame,
    comparison: dict[str, Any],
    output_dir: Path,
    inputs: dict[str, Any],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = output_dir / "candidates_top100.csv"
    diff_path = output_dir / "top50_vs_top100_diff.csv"
    comparison_path = output_dir / "baseline_comparison.md"
    manifest_path = output_dir / "manifest.json"
    candidates_top100.to_csv(candidates_path, index=False)
    comparison["top50_vs_top100_diff"].to_csv(diff_path, index=False)
    comparison_path.write_text(comparison["baseline_comparison_md"], encoding="utf-8")
    manifest = {**comparison["manifest"], "inputs": inputs, "files": {"candidates_top100": candidates_path.name, "top50_vs_top100_diff": diff_path.name, "baseline_comparison": comparison_path.name}}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"candidates_top100": candidates_path, "top50_vs_top100_diff": diff_path, "baseline_comparison": comparison_path, "manifest": manifest_path}


def _increment_status(row: pd.Series) -> str:
    if row.get("in_top50_baseline", False):
        return "top50_baseline_row"
    decision = row.get("p3_decision", "")
    if decision == "auto_approve":
        return "new_p1_auto_promotion"
    if decision in {"needs_more_evidence", "needs_product_family_mapping"}:
        return "new_p2_research_queue"
    return "new_p3_reject_or_noise"


def _render_baseline_comparison(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# tech-bottleneck top50 vs top100 comparison",
            "",
            f"- Top50 baseline P1 asset count: {manifest['baseline_p1_asset_count']}",
            f"- Top100 core-tech P1 asset count: {manifest['top100_p1_asset_count']}",
            f"- Top100 core-tech P2 asset count: {manifest['top100_p2_asset_count']}",
            f"- New P1 from ranks 51-100: {manifest['new_p1_from_rank_51_100']}",
            f"- New P2 from ranks 51-100: {manifest['new_p2_from_rank_51_100']}",
            "",
        ]
    )
```

- [ ] **Step 4: Run top100 tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_core_tech_top100.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/stock_research/tech_bottleneck_core_tech_top100.py tests/test_tech_bottleneck_core_tech_top100.py
git commit -m "feat: add core tech top100 comparison"
```

---

### Task 4: CLI Commands

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_tech_bottleneck_core_tech_gate.py`
- Modify: `tests/test_tech_bottleneck_core_tech_top100.py`

- [ ] **Step 1: Add failing CLI parser tests**

Append to `tests/test_tech_bottleneck_core_tech_gate.py`:

```python
from stock_research.cli import build_parser


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
```

Append to `tests/test_tech_bottleneck_core_tech_top100.py`:

```python
from stock_research.cli import build_parser


def test_cli_parser_accepts_core_tech_top100_command() -> None:
    args = build_parser().parse_args(
        [
            "tech-bottleneck-core-tech-top100",
            "--scores-csv",
            "scores.csv",
            "--quality-review-csv",
            "quality_review.csv",
            "--baseline-promotions-csv",
            "baseline.csv",
            "--output-dir",
            "out",
            "--top-n",
            "100",
        ]
    )

    assert args.command == "tech-bottleneck-core-tech-top100"
    assert args.scores_csv == "scores.csv"
    assert args.quality_review_csv == "quality_review.csv"
    assert args.baseline_promotions_csv == "baseline.csv"
    assert args.output_dir == "out"
    assert args.top_n == 100
```

- [ ] **Step 2: Run CLI parser tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_core_tech_gate.py::test_cli_parser_accepts_core_tech_gate_command tests/test_tech_bottleneck_core_tech_top100.py::test_cli_parser_accepts_core_tech_top100_command -q
```

Expected: argparse rejects unknown commands.

- [ ] **Step 3: Add parser commands**

In `src/stock_research/cli.py`, add subparsers matching the existing project parser style:

```python
core_gate = subparsers.add_parser("tech-bottleneck-core-tech-gate")
core_gate.add_argument("--candidates-csv", required=True)
core_gate.add_argument("--evidence-csv", required=False, default="")
core_gate.add_argument("--output-dir", required=True)

core_top100 = subparsers.add_parser("tech-bottleneck-core-tech-top100")
core_top100.add_argument("--scores-csv", required=True)
core_top100.add_argument("--quality-review-csv", required=True)
core_top100.add_argument("--baseline-promotions-csv", required=True)
core_top100.add_argument("--output-dir", required=True)
core_top100.add_argument("--top-n", type=int, default=100)
```

If `cli.py` dispatches commands in a `main()` function, add dispatch branches:

```python
if args.command == "tech-bottleneck-core-tech-gate":
    from stock_research.tech_bottleneck_core_tech_gate import run_core_tech_gate_from_files

    run_core_tech_gate_from_files(
        candidates_csv=Path(args.candidates_csv),
        evidence_csv=Path(args.evidence_csv) if args.evidence_csv else None,
        output_dir=Path(args.output_dir),
    )
    return

if args.command == "tech-bottleneck-core-tech-top100":
    from stock_research.tech_bottleneck_core_tech_top100 import run_core_tech_top100_from_files

    run_core_tech_top100_from_files(
        scores_csv=Path(args.scores_csv),
        quality_review_csv=Path(args.quality_review_csv),
        baseline_promotions_csv=Path(args.baseline_promotions_csv),
        output_dir=Path(args.output_dir),
        top_n=args.top_n,
    )
    return
```

- [ ] **Step 4: Run CLI parser tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_core_tech_gate.py::test_cli_parser_accepts_core_tech_gate_command tests/test_tech_bottleneck_core_tech_top100.py::test_cli_parser_accepts_core_tech_top100_command -q
```

Expected: tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/stock_research/cli.py tests/test_tech_bottleneck_core_tech_gate.py tests/test_tech_bottleneck_core_tech_top100.py
git commit -m "feat: add core tech bottleneck cli commands"
```

---

### Task 5: End-to-End Verification and Real Run

**Files:**
- Generated outputs only under `outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/`
- No source changes unless verification exposes a defect.

- [ ] **Step 1: Run focused pytest suite**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_tech_bottleneck_core_tech_gate.py \
  tests/test_tech_bottleneck_core_tech_top100.py \
  tests/test_tech_bottleneck_quality_review.py \
  tests/test_tech_bottleneck_observation_pool.py \
  tests/test_tech_bottleneck_experiment.py \
  -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run repository whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Build real top100 score export**

Use the existing database/export mechanism already used for top50 candidate generation. If the project has a stored command for topN export, use it. Otherwise create a local CSV from `factor.stock_score_daily` with these columns:

```text
trade_date,asset_id,stock_name,score,score_version,industry_name
```

Constraints:

- `score_version = manual_v1`
- `trade_date >= 2025-01-01`
- weekly cadence matching the previous top50 run
- top100 by descending score per selected date

Write it to:

```text
outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/candidates_top100.csv
```

- [ ] **Step 4: Run the core-tech gate on real candidates**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  tech-bottleneck-core-tech-gate \
  --candidates-csv outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/candidates_top100.csv \
  --evidence-csv outputs/tech_bottleneck_discovery/pilot_top50_20250101_20260607/combined_evidence_with_official_product/evidence.csv \
  --output-dir outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/core_tech_gate
```

Expected outputs:

- `core_tech_gate/core_tech_gate.csv`
- `core_tech_gate/core_tech_candidates.csv`
- `core_tech_gate/summary.md`
- `core_tech_gate/manifest.json`

- [ ] **Step 5: Run quality review on core-tech candidates**

Run the existing quality review file runner with:

```text
candidates_csv = outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/core_tech_gate/core_tech_candidates.csv
evidence_hits_csv = outputs/tech_bottleneck_discovery/pilot_top50_20250101_20260607/combined_evidence_with_official_product/evidence.csv
product_rows_csv = outputs/tech_bottleneck_discovery/pilot_top50_20250101_20260607/official_product_backfill/product_evidence.csv
output_dir = outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/quality_review
```

Expected outputs:

- `quality_review/quality_review.csv`
- `quality_review/promotion_assets.csv`
- `quality_review/human_review_assets.csv`
- `quality_review/rejected_assets.csv`
- `quality_review/manifest.json`

- [ ] **Step 6: Build top50-vs-top100 comparison**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  tech-bottleneck-core-tech-top100 \
  --scores-csv outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/scores_input.csv \
  --quality-review-csv outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/quality_review/quality_review.csv \
  --baseline-promotions-csv outputs/tech_bottleneck_discovery/pilot_top50_20250101_20260607/quality_review_family_expanded/promotion_assets.csv \
  --output-dir outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/comparison \
  --top-n 100
```

Expected outputs:

- `comparison/candidates_top100.csv`
- `comparison/top50_vs_top100_diff.csv`
- `comparison/baseline_comparison.md`
- `comparison/manifest.json`

- [ ] **Step 7: Summarize real-run findings**

Read:

```text
outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/core_tech_gate/manifest.json
outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/quality_review/manifest.json
outputs/tech_bottleneck_discovery/core_tech_top100_20250101_<latest_trade_date>/comparison/baseline_comparison.md
```

Report to the user:

- top100 candidate rows and assets
- core-tech gate pass rows and assets
- P1 auto-promotion assets
- P2 research-queue assets
- new P1 from ranks 51-100
- new P2 from ranks 51-100
- whether the current six P1 names still pass
- top five evidence gaps

- [ ] **Step 8: Commit any verification fixes**

If Task 5 required code fixes, commit them:

```bash
git add <changed source/test files>
git commit -m "fix: stabilize core tech top100 experiment"
```

If Task 5 generated only output files and outputs are intentionally ignored, do not commit generated artifacts.

---

## Self-Review

- Spec coverage: top100 candidate pool is covered by Task 3 and Task 5; core-tech gate by Task 1; targeted P2 evidence needs by Task 2; comparison outputs by Task 3; CLI/runability by Task 4 and Task 5.
- Placeholder scan: no task uses unresolved implementation markers. The only runtime substitution is `<latest_trade_date>`, which is intentionally resolved by the real data run.
- Type consistency: modules exchange pandas DataFrames and CSV paths; field names are consistent across tasks: `asset_id`, `stock_name`, `trade_date`, `rank`, `p3_decision`, `evidence_quality_score`, `next_evidence_need`.
