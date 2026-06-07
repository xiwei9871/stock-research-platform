# Tech Chain Taxonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configuration-driven `tech_chain_taxonomy` evidence layer so tech-bottleneck discovery recognizes hard-tech supply-chain bottlenecks beyond generic domestic-substitution terms.

**Architecture:** Add a local taxonomy JSON file and a focused Python module that loads chain definitions, maps candidates/evidence into chain dimensions, and emits normalized review artifacts. Existing core gate and quality review consume the chain outputs without replacing their current generic behavior, so the rollout improves coverage while keeping P1/P2 strictness.

**Tech Stack:** Python 3.14, pandas, pytest, existing `stock_research` CLI patterns, CSV/JSON artifacts.

---

## File Structure

- Create `data/manual/tech_chain_taxonomy_v1.json`: versioned taxonomy configuration containing the twenty chain definitions from the approved design.
- Create `src/stock_research/tech_chain_taxonomy.py`: dataclasses/loaders, normalization, candidate-to-chain mapping, evidence-to-dimension mapping, quality decision helpers, artifact writer.
- Create `tests/test_tech_chain_taxonomy.py`: unit tests for config loading, chain matching, evidence mapping, PIT filtering, quality decisions, and artifact writing.
- Modify `src/stock_research/cli.py`: add `tech-chain-taxonomy-review` CLI command.
- Modify `src/stock_research/tech_bottleneck_core_tech_gate.py`: optionally use taxonomy chain context as an additional pass path.
- Modify `src/stock_research/tech_bottleneck_quality_review.py`: consume taxonomy-derived product family/chain evidence only when supplied by the new review command; do not loosen existing generic decisions.
- Modify `tests/test_tech_bottleneck_core_tech_gate.py`: add taxonomy-backed gate tests.
- Modify `tests/test_tech_bottleneck_quality_review.py`: add taxonomy-compatible quality review tests.

Before implementation, check `git status --short`. The branch currently may contain uncommitted core-leader repair files. Do not revert them. If they are still uncommitted, either commit them separately first or keep taxonomy changes in distinct files and commits.

---

### Task 1: Add Versioned Taxonomy Configuration

**Files:**
- Create: `data/manual/tech_chain_taxonomy_v1.json`
- Create: `tests/test_tech_chain_taxonomy.py`
- Create: `src/stock_research/tech_chain_taxonomy.py`

- [ ] **Step 1: Write the failing taxonomy loader test**

Add this to `tests/test_tech_chain_taxonomy.py`:

```python
from pathlib import Path

from stock_research.tech_chain_taxonomy import load_taxonomy


def test_load_taxonomy_v1_contains_core_chains() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))

    assert taxonomy.version == "tech_chain_taxonomy_v1"
    assert len(taxonomy.chains) == 20
    chain_ids = {chain.chain_id for chain in taxonomy.chains}
    assert {
        "ai_optical_interconnect",
        "ai_compute_chips",
        "hbm_high_end_memory",
        "mlcc_high_end_passives",
        "semiconductor_equipment",
    }.issubset(chain_ids)

    optical = taxonomy.chain_by_id("ai_optical_interconnect")
    assert "800G" in optical.bottleneck_dimensions["bandwidth_generation"]
    assert "CPO" in optical.bottleneck_dimensions["architecture_route"]
    assert "EML" in optical.bottleneck_dimensions["critical_components"]

    hbm = taxonomy.chain_by_id("hbm_high_end_memory")
    assert "HBM3E" in hbm.bottleneck_dimensions["memory_generation"]
    assert "Samsung" in hbm.global_reference_entities
    assert "SK hynix" in hbm.global_reference_entities

    mlcc = taxonomy.chain_by_id("mlcc_high_end_passives")
    assert "AI server PDN" in mlcc.bottleneck_dimensions["power_density"]
    assert "Murata" in mlcc.global_reference_entities
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_chain_taxonomy.py::test_load_taxonomy_v1_contains_core_chains -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_research.tech_chain_taxonomy'`.

- [ ] **Step 3: Add the taxonomy JSON**

Create `data/manual/tech_chain_taxonomy_v1.json` with this structure. Include all twenty chains from the approved spec. The first three entries must be exactly:

```json
{
  "version": "tech_chain_taxonomy_v1",
  "chains": [
    {
      "chain_id": "ai_optical_interconnect",
      "display_name": "AI光模块/光通信",
      "chain_context_terms": ["光模块", "光通信", "光器件", "光引擎", "光互联", "数据中心互联", "AI集群"],
      "product_exposure_terms": ["光通信模块", "光通信收发模块", "光无源器件", "光有源器件", "光互联产品", "高速光模块", "4.25G以上"],
      "bottleneck_dimensions": {
        "bandwidth_generation": ["800G", "1.6T", "3.2T", "高速光模块"],
        "architecture_route": ["硅光", "CPO", "LPO", "NPO", "光引擎"],
        "critical_components": ["EML", "CW", "FAU", "DSP", "光芯片", "光器件"],
        "process_delivery": ["耦合", "封装", "良率", "低功耗", "高速率"],
        "customer_delivery": ["北美CSP", "大客户导入", "份额", "交付", "产能爬坡"]
      },
      "technical_execution_terms": ["技术平台", "光电连接", "研发", "规模量产", "高端产品", "低功耗"],
      "commercial_validation_terms": ["客户导入", "订单", "份额", "批量交付", "产能", "扩产"],
      "invalidation_terms": ["需求不及预期", "降价", "竞争加剧", "物料紧缺", "客户份额下降"],
      "global_reference_entities": ["Nvidia", "Broadcom", "Marvell", "Coherent", "Lumentum"]
    },
    {
      "chain_id": "hbm_high_end_memory",
      "display_name": "HBM/高端存储",
      "chain_context_terms": ["HBM", "高带宽内存", "高端存储", "AI存储"],
      "product_exposure_terms": ["HBM3", "HBM3E", "HBM4", "DRAM", "存储芯片"],
      "bottleneck_dimensions": {
        "memory_generation": ["HBM3E", "HBM4", "12Hi", "16Hi"],
        "stacking_tsv": ["TSV", "堆叠", "base die", "micro bump"],
        "packaging_linkage": ["CoWoS", "2.5D", "interposer"],
        "qualification_yield": ["Nvidia认证", "客户验证", "良率", "后段产能"],
        "supply_allocation": ["长协", "产能分配", "供给紧张", "sold out"]
      },
      "technical_execution_terms": ["TSV", "堆叠", "良率", "后段", "认证"],
      "commercial_validation_terms": ["客户验证", "长协", "产能分配", "扩产", "供给紧张"],
      "invalidation_terms": ["良率不及预期", "认证不及预期", "扩产不及预期", "需求不及预期"],
      "global_reference_entities": ["Samsung", "SK hynix", "Micron", "Nvidia"]
    },
    {
      "chain_id": "mlcc_high_end_passives",
      "display_name": "MLCC/高端被动元件",
      "chain_context_terms": ["MLCC", "多层陶瓷电容器", "片式多层陶瓷电容器", "被动元件"],
      "product_exposure_terms": ["MLCC", "陶瓷电容", "高容量电容", "高可靠电容", "电子陶瓷"],
      "bottleneck_dimensions": {
        "power_density": ["AI server PDN", "GPU周边", "高瞬态电流"],
        "product_grade": ["高容量", "高温", "高可靠", "小型化", "车规级"],
        "materials_process": ["陶瓷粉体", "介质材料", "叠层", "烧结"],
        "supply_concentration": ["Murata", "Samsung Electro-Mechanics", "Taiyo Yuden"],
        "capacity_tightness": ["涨价", "交期", "满产", "长协"]
      },
      "technical_execution_terms": ["高容量", "小型化", "叠层", "烧结", "高可靠"],
      "commercial_validation_terms": ["客户认证", "涨价", "满产", "长协", "交期"],
      "invalidation_terms": ["需求不及预期", "降价", "竞争加剧", "消费电子疲弱"],
      "global_reference_entities": ["Murata", "Samsung Electro-Mechanics", "Taiyo Yuden"]
    }
  ]
}
```

Then append the remaining seventeen chain objects from `docs/superpowers/specs/2026-06-08-tech-chain-taxonomy-design.md`. Use the chain ids listed in Task 2.

- [ ] **Step 4: Add loader dataclasses**

Create `src/stock_research/tech_chain_taxonomy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TechChainDefinition:
    chain_id: str
    display_name: str
    chain_context_terms: list[str]
    product_exposure_terms: list[str]
    bottleneck_dimensions: dict[str, list[str]]
    technical_execution_terms: list[str]
    commercial_validation_terms: list[str]
    invalidation_terms: list[str]
    global_reference_entities: list[str]


@dataclass(frozen=True)
class TechChainTaxonomy:
    version: str
    chains: list[TechChainDefinition]

    def chain_by_id(self, chain_id: str) -> TechChainDefinition:
        for chain in self.chains:
            if chain.chain_id == chain_id:
                return chain
        raise KeyError(chain_id)


def load_taxonomy(path: Path | str) -> TechChainTaxonomy:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    chains = [_chain_from_payload(item) for item in payload.get("chains", [])]
    return TechChainTaxonomy(version=str(payload.get("version", "")), chains=chains)


def _chain_from_payload(item: dict[str, Any]) -> TechChainDefinition:
    return TechChainDefinition(
        chain_id=str(item.get("chain_id", "")),
        display_name=str(item.get("display_name", "")),
        chain_context_terms=_string_list(item.get("chain_context_terms")),
        product_exposure_terms=_string_list(item.get("product_exposure_terms")),
        bottleneck_dimensions={
            str(key): _string_list(value)
            for key, value in dict(item.get("bottleneck_dimensions") or {}).items()
        },
        technical_execution_terms=_string_list(item.get("technical_execution_terms")),
        commercial_validation_terms=_string_list(item.get("commercial_validation_terms")),
        invalidation_terms=_string_list(item.get("invalidation_terms")),
        global_reference_entities=_string_list(item.get("global_reference_entities")),
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
```

- [ ] **Step 5: Run the test to verify it passes**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_chain_taxonomy.py::test_load_taxonomy_v1_contains_core_chains -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data/manual/tech_chain_taxonomy_v1.json src/stock_research/tech_chain_taxonomy.py tests/test_tech_chain_taxonomy.py
git commit -m "feat: add tech chain taxonomy config"
```

---

### Task 2: Map Candidates to Technology Chains

**Files:**
- Modify: `src/stock_research/tech_chain_taxonomy.py`
- Modify: `tests/test_tech_chain_taxonomy.py`

- [ ] **Step 1: Write failing candidate mapping test**

Append to `tests/test_tech_chain_taxonomy.py`:

```python
import pandas as pd

from stock_research.tech_chain_taxonomy import build_chain_mapping, load_taxonomy


def test_build_chain_mapping_identifies_chain_context_and_product_exposure() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "industry_name": "通信设备",
                "product_snippet": "光通信模块、光通信收发模块收入占比高",
            },
            {
                "asset_id": "CN:SH:688256",
                "stock_name": "寒武纪",
                "trade_date": "2025-08-22",
                "industry_name": "半导体",
                "product_snippet": "云端产品线 智能计算芯片 MLU",
            },
            {
                "asset_id": "CN:SZ:300476",
                "stock_name": "胜宏科技",
                "trade_date": "2025-07-04",
                "industry_name": "电子元件",
                "product_snippet": "AI服务器PCB 高阶HDI 高多层板",
            },
        ]
    )

    mapping = build_chain_mapping(candidates=candidates, taxonomy=taxonomy)
    rows = mapping.set_index("asset_id")

    assert rows.loc["CN:SZ:300308", "primary_chain_id"] == "ai_optical_interconnect"
    assert rows.loc["CN:SZ:300308", "product_exposure_quality"] == "strong"
    assert rows.loc["CN:SH:688256", "primary_chain_id"] == "ai_compute_chips"
    assert rows.loc["CN:SZ:300476", "primary_chain_id"] == "ai_server_pcb"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_chain_taxonomy.py::test_build_chain_mapping_identifies_chain_context_and_product_exposure -q
```

Expected: FAIL with `ImportError` or `AttributeError` for `build_chain_mapping`.

- [ ] **Step 3: Implement candidate mapping**

Add to `src/stock_research/tech_chain_taxonomy.py`:

```python
import math
from datetime import date, datetime

import pandas as pd


CHAIN_MAPPING_COLUMNS = [
    "asset_id",
    "stock_name",
    "trade_date",
    "primary_chain_id",
    "primary_chain_name",
    "matched_chain_ids",
    "matched_context_terms",
    "matched_product_terms",
    "chain_context_quality",
    "product_exposure_quality",
]


def build_chain_mapping(*, candidates: pd.DataFrame, taxonomy: TechChainTaxonomy) -> pd.DataFrame:
    normalized = _normalize_candidates(candidates)
    rows: list[dict[str, Any]] = []
    for candidate in normalized.to_dict("records"):
        text = _compactible_text(
            " ".join(
                [
                    candidate["stock_name"],
                    candidate["industry_name"],
                    candidate["product_snippet"],
                ]
            )
        )
        matches = [_candidate_chain_match(chain, text) for chain in taxonomy.chains]
        matches = [match for match in matches if match["score"] > 0]
        matches = sorted(matches, key=lambda item: (item["product_hits"], item["context_hits"], item["score"]), reverse=True)
        primary = matches[0] if matches else {}
        rows.append(
            {
                "asset_id": candidate["asset_id"],
                "stock_name": candidate["stock_name"],
                "trade_date": candidate["trade_date"],
                "primary_chain_id": str(primary.get("chain_id", "")),
                "primary_chain_name": str(primary.get("display_name", "")),
                "matched_chain_ids": "|".join(match["chain_id"] for match in matches),
                "matched_context_terms": "|".join(primary.get("context_terms", [])),
                "matched_product_terms": "|".join(primary.get("product_terms", [])),
                "chain_context_quality": "strong" if int(primary.get("context_hits", 0)) > 0 else "missing",
                "product_exposure_quality": "strong" if int(primary.get("product_hits", 0)) > 0 else "missing",
            }
        )
    return pd.DataFrame(rows).reindex(columns=CHAIN_MAPPING_COLUMNS)


def _candidate_chain_match(chain: TechChainDefinition, text: str) -> dict[str, Any]:
    context_terms = _matched_terms(text, chain.chain_context_terms)
    product_terms = _matched_terms(text, chain.product_exposure_terms)
    context_hits = len(context_terms)
    product_hits = len(product_terms)
    return {
        "chain_id": chain.chain_id,
        "display_name": chain.display_name,
        "context_terms": context_terms,
        "product_terms": product_terms,
        "context_hits": context_hits,
        "product_hits": product_hits,
        "score": context_hits + product_hits * 3,
    }


def _normalize_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.copy()
    for column in ["asset_id", "stock_name", "trade_date", "industry_name", "product_snippet"]:
        if column not in frame:
            frame[column] = ""
    frame["asset_id"] = frame["asset_id"].astype("string").fillna("")
    frame["stock_name"] = frame["stock_name"].astype("string").fillna("")
    frame["industry_name"] = frame["industry_name"].astype("string").fillna("")
    frame["product_snippet"] = frame["product_snippet"].astype("string").fillna("")
    frame["trade_date"] = frame["trade_date"].map(_normalize_date)
    return frame[frame["asset_id"].ne("") & frame["trade_date"].ne("")].copy()


def _normalize_date(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and math.isfinite(value) and int(value) == value:
        value = int(value)
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        parsed = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    else:
        parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    compact_text = _compactible_text(text)
    return [term for term in terms if _compactible_text(term) in compact_text]


def _compactible_text(value: str) -> str:
    return "".join(str(value).casefold().split())
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_chain_taxonomy.py::test_build_chain_mapping_identifies_chain_context_and_product_exposure -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/tech_chain_taxonomy.py tests/test_tech_chain_taxonomy.py
git commit -m "feat: map candidates to tech chains"
```

---

### Task 3: Map Evidence to Chain-Specific Bottleneck Dimensions

**Files:**
- Modify: `src/stock_research/tech_chain_taxonomy.py`
- Modify: `tests/test_tech_chain_taxonomy.py`

- [ ] **Step 1: Write failing evidence mapping test**

Append to `tests/test_tech_chain_taxonomy.py`:

```python
from stock_research.tech_chain_taxonomy import build_chain_evidence_review


def test_build_chain_evidence_review_maps_dimensions_and_filters_future_rows() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "product_exposure_quality": "strong",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-05-22",
                "evidence_type": "technical_barrier",
                "matched_keyword": "CPO",
                "evidence_snippet": "持续扩产备料并积极研发布局3.2T、CPO等",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-09-17",
                "evidence_type": "technical_barrier",
                "matched_keyword": "1.6T",
                "evidence_snippet": "1.6T上量将进一步提升盈利",
                "as_of_safe": False,
            },
        ]
    )

    review = build_chain_evidence_review(mapping=mapping, evidence=evidence, taxonomy=taxonomy)

    assert len(review) == 1
    row = review.iloc[0]
    assert row["asset_id"] == "CN:SZ:300308"
    assert row["chain_id"] == "ai_optical_interconnect"
    assert row["bottleneck_dimension"] == "architecture_route"
    assert row["matched_terms"] == "CPO"
    assert row["evidence_quality"] == "strong"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_chain_taxonomy.py::test_build_chain_evidence_review_maps_dimensions_and_filters_future_rows -q
```

Expected: FAIL with missing `build_chain_evidence_review`.

- [ ] **Step 3: Implement evidence mapping**

Add to `src/stock_research/tech_chain_taxonomy.py`:

```python
CHAIN_EVIDENCE_COLUMNS = [
    "asset_id",
    "stock_name",
    "trade_date",
    "chain_id",
    "chain_name",
    "evidence_type",
    "bottleneck_dimension",
    "matched_terms",
    "evidence_quality",
    "evidence_date",
    "snippet",
]


def build_chain_evidence_review(
    *,
    mapping: pd.DataFrame,
    evidence: pd.DataFrame | None,
    taxonomy: TechChainTaxonomy,
) -> pd.DataFrame:
    normalized_mapping = _normalize_mapping(mapping)
    normalized_evidence = _normalize_evidence(evidence)
    rows: list[dict[str, Any]] = []
    for item in normalized_mapping.to_dict("records"):
        if not item["primary_chain_id"]:
            continue
        chain = taxonomy.chain_by_id(item["primary_chain_id"])
        candidate_evidence = normalized_evidence[
            normalized_evidence["asset_id"].eq(item["asset_id"])
            & normalized_evidence["candidate_trade_date"].eq(item["trade_date"])
            & normalized_evidence["as_of_safe"]
        ].copy()
        for evidence_row in candidate_evidence.to_dict("records"):
            text = _compactible_text(f"{evidence_row['matched_keyword']} {evidence_row['snippet']}")
            for dimension, terms in chain.bottleneck_dimensions.items():
                matched = _matched_terms(text, terms)
                if not matched:
                    continue
                rows.append(
                    {
                        "asset_id": item["asset_id"],
                        "stock_name": item["stock_name"],
                        "trade_date": item["trade_date"],
                        "chain_id": chain.chain_id,
                        "chain_name": chain.display_name,
                        "evidence_type": evidence_row["evidence_type"],
                        "bottleneck_dimension": dimension,
                        "matched_terms": "|".join(matched),
                        "evidence_quality": _chain_evidence_quality(evidence_row, matched),
                        "evidence_date": evidence_row["evidence_date"],
                        "snippet": evidence_row["snippet"],
                    }
                )
    return pd.DataFrame(rows).reindex(columns=CHAIN_EVIDENCE_COLUMNS)


def _normalize_mapping(mapping: pd.DataFrame) -> pd.DataFrame:
    frame = mapping.copy()
    for column in ["asset_id", "stock_name", "trade_date", "primary_chain_id", "product_exposure_quality"]:
        if column not in frame:
            frame[column] = ""
        frame[column] = frame[column].astype("string").fillna("")
    frame["trade_date"] = frame["trade_date"].map(_normalize_date)
    return frame[frame["asset_id"].ne("") & frame["trade_date"].ne("")].copy()


def _normalize_evidence(evidence: pd.DataFrame | None) -> pd.DataFrame:
    frame = evidence.copy() if evidence is not None else pd.DataFrame()
    if "trade_date" not in frame and "candidate_trade_date" in frame:
        frame = frame.rename(columns={"candidate_trade_date": "trade_date"})
    if "candidate_trade_date" not in frame and "trade_date" in frame:
        frame["candidate_trade_date"] = frame["trade_date"]
    if "snippet" not in frame and "evidence_snippet" in frame:
        frame = frame.rename(columns={"evidence_snippet": "snippet"})
    if "matched_keyword" not in frame and "term" in frame:
        frame = frame.rename(columns={"term": "matched_keyword"})
    if "evidence_type" not in frame and "evidence_bucket" in frame:
        frame = frame.rename(columns={"evidence_bucket": "evidence_type"})
    for column in ["asset_id", "stock_name", "candidate_trade_date", "evidence_date", "evidence_type", "matched_keyword", "snippet"]:
        if column not in frame:
            frame[column] = ""
        frame[column] = frame[column].astype("string").fillna("")
    if "as_of_safe" not in frame:
        frame["as_of_safe"] = True
    frame["as_of_safe"] = frame["as_of_safe"].map(_bool_value)
    frame["candidate_trade_date"] = frame["candidate_trade_date"].map(_normalize_date)
    frame["evidence_date"] = frame["evidence_date"].map(_normalize_date)
    return frame[frame["asset_id"].ne("") & frame["candidate_trade_date"].ne("")].copy()


def _bool_value(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    return str(value).strip().casefold() in {"true", "1", "yes", "y"}


def _chain_evidence_quality(row: dict[str, Any], matched_terms: list[str]) -> str:
    text = _compactible_text(f"{row.get('matched_keyword', '')} {row.get('snippet', '')}")
    if len(matched_terms) >= 2:
        return "strong"
    if any(term in text for term in ["良率", "认证", "量产", "客户", "交付", "产能"]):
        return "strong"
    return "medium"
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_chain_taxonomy.py::test_build_chain_evidence_review_maps_dimensions_and_filters_future_rows -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/tech_chain_taxonomy.py tests/test_tech_chain_taxonomy.py
git commit -m "feat: map tech chain evidence dimensions"
```

---

### Task 4: Build Chain-Specific Quality Review

**Files:**
- Modify: `src/stock_research/tech_chain_taxonomy.py`
- Modify: `tests/test_tech_chain_taxonomy.py`

- [ ] **Step 1: Write failing quality review test**

Append to `tests/test_tech_chain_taxonomy.py`:

```python
from stock_research.tech_chain_taxonomy import build_chain_quality_review


def test_build_chain_quality_review_routes_chain_candidates_without_generic_bottleneck_terms() -> None:
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "primary_chain_name": "AI光模块/光通信",
                "product_exposure_quality": "strong",
            },
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "primary_chain_name": "AI光模块/光通信",
                "product_exposure_quality": "missing",
            },
        ]
    )
    evidence_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "chain_id": "ai_optical_interconnect",
                "bottleneck_dimension": "architecture_route",
                "evidence_quality": "strong",
            }
        ]
    )

    review = build_chain_quality_review(mapping=mapping, chain_evidence=evidence_review)
    rows = review.set_index("asset_id")

    assert rows.loc["CN:SZ:300308", "chain_decision"] == "needs_more_evidence"
    assert rows.loc["CN:SZ:300308", "decision_reason"] == "chain bottleneck is mapped but support evidence is incomplete"
    assert rows.loc["CN:SZ:300394", "chain_decision"] == "needs_product_family_mapping"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_chain_taxonomy.py::test_build_chain_quality_review_routes_chain_candidates_without_generic_bottleneck_terms -q
```

Expected: FAIL with missing `build_chain_quality_review`.

- [ ] **Step 3: Implement chain quality review**

Add to `src/stock_research/tech_chain_taxonomy.py`:

```python
CHAIN_QUALITY_COLUMNS = [
    "asset_id",
    "stock_name",
    "trade_date",
    "primary_chain_id",
    "primary_chain_name",
    "chain_decision",
    "product_exposure_quality",
    "bottleneck_dimension_count",
    "strong_bottleneck_dimension_count",
    "matched_bottleneck_dimensions",
    "decision_reason",
    "next_evidence_need",
]


def build_chain_quality_review(*, mapping: pd.DataFrame, chain_evidence: pd.DataFrame) -> pd.DataFrame:
    normalized_mapping = _normalize_mapping(mapping)
    evidence = chain_evidence.copy()
    for column in ["asset_id", "trade_date", "bottleneck_dimension", "evidence_quality"]:
        if column not in evidence:
            evidence[column] = ""
        evidence[column] = evidence[column].astype("string").fillna("")
    rows: list[dict[str, Any]] = []
    for item in normalized_mapping.to_dict("records"):
        candidate_evidence = evidence[
            evidence["asset_id"].eq(item["asset_id"]) & evidence["trade_date"].eq(item["trade_date"])
        ].copy()
        dimensions = sorted({value for value in candidate_evidence["bottleneck_dimension"].tolist() if value})
        strong_dimensions = sorted(
            {
                row["bottleneck_dimension"]
                for row in candidate_evidence.to_dict("records")
                if row.get("bottleneck_dimension") and row.get("evidence_quality") == "strong"
            }
        )
        decision, reason, next_need = _chain_decision(
            chain_id=item["primary_chain_id"],
            product_quality=item["product_exposure_quality"],
            strong_dimension_count=len(strong_dimensions),
        )
        rows.append(
            {
                "asset_id": item["asset_id"],
                "stock_name": item["stock_name"],
                "trade_date": item["trade_date"],
                "primary_chain_id": item["primary_chain_id"],
                "primary_chain_name": item.get("primary_chain_name", ""),
                "chain_decision": decision,
                "product_exposure_quality": item["product_exposure_quality"],
                "bottleneck_dimension_count": len(dimensions),
                "strong_bottleneck_dimension_count": len(strong_dimensions),
                "matched_bottleneck_dimensions": "|".join(dimensions),
                "decision_reason": reason,
                "next_evidence_need": next_need,
            }
        )
    return pd.DataFrame(rows).reindex(columns=CHAIN_QUALITY_COLUMNS)


def _chain_decision(*, chain_id: str, product_quality: str, strong_dimension_count: int) -> tuple[str, str, str]:
    if not chain_id:
        return ("reject_or_noise", "no recognized tech chain context", "needs_chain_context_evidence")
    if product_quality == "missing":
        return (
            "needs_product_family_mapping",
            "tech chain is mapped but PIT-safe product exposure is incomplete",
            "needs_pit_safe_product_exposure",
        )
    if strong_dimension_count <= 0:
        return (
            "needs_more_evidence",
            "product exposure is mapped but chain-specific bottleneck evidence is incomplete",
            "needs_chain_bottleneck_dimension_evidence",
        )
    return (
        "needs_more_evidence",
        "chain bottleneck is mapped but support evidence is incomplete",
        "needs_customer_capacity_or_catalyst_evidence",
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_chain_taxonomy.py::test_build_chain_quality_review_routes_chain_candidates_without_generic_bottleneck_terms -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/tech_chain_taxonomy.py tests/test_tech_chain_taxonomy.py
git commit -m "feat: add tech chain quality review"
```

---

### Task 5: Write Artifacts and Add CLI Command

**Files:**
- Modify: `src/stock_research/tech_chain_taxonomy.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_tech_chain_taxonomy.py`

- [ ] **Step 1: Write failing artifact and CLI tests**

Append to `tests/test_tech_chain_taxonomy.py`:

```python
import json

from stock_research.tech_chain_taxonomy import run_tech_chain_taxonomy_review_from_files


def test_run_tech_chain_taxonomy_review_from_files_writes_outputs(tmp_path: Path) -> None:
    taxonomy_path = tmp_path / "taxonomy.json"
    taxonomy_path.write_text(Path("data/manual/tech_chain_taxonomy_v1.json").read_text(encoding="utf-8"), encoding="utf-8")
    candidates_csv = tmp_path / "candidates.csv"
    evidence_csv = tmp_path / "evidence.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "industry_name": "通信设备",
                "product_snippet": "光通信模块 CPO",
            }
        ]
    ).to_csv(candidates_csv, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-05-22",
                "evidence_type": "technical_barrier",
                "matched_keyword": "CPO",
                "evidence_snippet": "研发3.2T、CPO等高速光模块",
                "as_of_safe": True,
            }
        ]
    ).to_csv(evidence_csv, index=False)

    paths = run_tech_chain_taxonomy_review_from_files(
        candidates_csv=candidates_csv,
        evidence_csv=evidence_csv,
        taxonomy_json=taxonomy_path,
        output_dir=tmp_path / "out",
    )

    assert paths["chain_mapping"].exists()
    assert paths["chain_evidence_review"].exists()
    assert paths["chain_quality_review"].exists()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["candidate_count"] == 1
    assert manifest["chain_quality_decision_counts"] == {"needs_more_evidence": 1}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_chain_taxonomy.py::test_run_tech_chain_taxonomy_review_from_files_writes_outputs -q
```

Expected: FAIL with missing `run_tech_chain_taxonomy_review_from_files`.

- [ ] **Step 3: Implement artifact writer and runner**

Add to `src/stock_research/tech_chain_taxonomy.py`:

```python
def run_tech_chain_taxonomy_review_from_files(
    *,
    candidates_csv: Path,
    evidence_csv: Path | None,
    taxonomy_json: Path,
    output_dir: Path,
) -> dict[str, Path]:
    taxonomy = load_taxonomy(taxonomy_json)
    candidates = pd.read_csv(candidates_csv)
    evidence = pd.read_csv(evidence_csv) if evidence_csv else pd.DataFrame()
    mapping = build_chain_mapping(candidates=candidates, taxonomy=taxonomy)
    chain_evidence = build_chain_evidence_review(mapping=mapping, evidence=evidence, taxonomy=taxonomy)
    quality = build_chain_quality_review(mapping=mapping, chain_evidence=chain_evidence)
    return write_tech_chain_taxonomy_artifacts(
        mapping=mapping,
        chain_evidence=chain_evidence,
        quality=quality,
        output_dir=output_dir,
        inputs={
            "candidates_csv": str(candidates_csv),
            "evidence_csv": str(evidence_csv) if evidence_csv else "",
            "taxonomy_json": str(taxonomy_json),
        },
    )


def write_tech_chain_taxonomy_artifacts(
    *,
    mapping: pd.DataFrame,
    chain_evidence: pd.DataFrame,
    quality: pd.DataFrame,
    output_dir: Path,
    inputs: dict[str, str],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = output_dir / "chain_mapping.csv"
    evidence_path = output_dir / "chain_evidence_review.csv"
    quality_path = output_dir / "chain_quality_review.csv"
    manifest_path = output_dir / "manifest.json"
    summary_path = output_dir / "summary.md"
    mapping.to_csv(mapping_path, index=False)
    chain_evidence.to_csv(evidence_path, index=False)
    quality.to_csv(quality_path, index=False)
    manifest = {
        "candidate_count": int(len(mapping)),
        "mapped_chain_assets": int(mapping[mapping["primary_chain_id"].ne("")]["asset_id"].nunique()) if not mapping.empty else 0,
        "chain_evidence_rows": int(len(chain_evidence)),
        "chain_quality_decision_counts": quality["chain_decision"].value_counts().to_dict() if not quality.empty else {},
        "inputs": inputs,
        "files": {
            "chain_mapping": mapping_path.name,
            "chain_evidence_review": evidence_path.name,
            "chain_quality_review": quality_path.name,
            "manifest": manifest_path.name,
            "summary": summary_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(_render_chain_summary(manifest), encoding="utf-8")
    return {
        "chain_mapping": mapping_path,
        "chain_evidence_review": evidence_path,
        "chain_quality_review": quality_path,
        "manifest": manifest_path,
        "summary": summary_path,
    }


def _render_chain_summary(manifest: dict[str, Any]) -> str:
    lines = [
        "# Tech Chain Taxonomy Review",
        "",
        f"- Candidates: {manifest['candidate_count']}",
        f"- Mapped chain assets: {manifest['mapped_chain_assets']}",
        f"- Chain evidence rows: {manifest['chain_evidence_rows']}",
        "",
        "## Decisions",
    ]
    counts = manifest.get("chain_quality_decision_counts", {})
    if counts:
        for decision, count in counts.items():
            lines.append(f"- {decision}: {count}")
    else:
        lines.append("- none: 0")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Add CLI parser and dispatch**

Modify `src/stock_research/cli.py` near the other tech-bottleneck commands:

```python
    tech_chain_taxonomy = subparsers.add_parser(
        "tech-chain-taxonomy-review",
        help="Map candidates and evidence to configurable hard-tech chain taxonomy dimensions.",
    )
    tech_chain_taxonomy.add_argument("--candidates-csv", required=True)
    tech_chain_taxonomy.add_argument("--evidence-csv")
    tech_chain_taxonomy.add_argument("--taxonomy-json", default="data/manual/tech_chain_taxonomy_v1.json")
    tech_chain_taxonomy.add_argument("--output-dir", required=True)
```

Modify the command dispatch section:

```python
    elif args.command == "tech-chain-taxonomy-review":
        from stock_research.tech_chain_taxonomy import run_tech_chain_taxonomy_review_from_files

        paths = run_tech_chain_taxonomy_review_from_files(
            candidates_csv=Path(args.candidates_csv),
            evidence_csv=Path(args.evidence_csv) if args.evidence_csv else None,
            taxonomy_json=Path(args.taxonomy_json),
            output_dir=Path(args.output_dir),
        )
        print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_chain_taxonomy.py -q
```

Expected: all tests in `tests/test_tech_chain_taxonomy.py` pass.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/tech_chain_taxonomy.py src/stock_research/cli.py tests/test_tech_chain_taxonomy.py
git commit -m "feat: add tech chain taxonomy review cli"
```

---

### Task 6: Integrate Taxonomy with Core Gate and Existing Quality Review

**Files:**
- Modify: `src/stock_research/tech_bottleneck_core_tech_gate.py`
- Modify: `src/stock_research/tech_bottleneck_quality_review.py`
- Modify: `tests/test_tech_bottleneck_core_tech_gate.py`
- Modify: `tests/test_tech_bottleneck_quality_review.py`

- [ ] **Step 1: Write gate integration test**

Add to `tests/test_tech_bottleneck_core_tech_gate.py`:

```python
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
```

- [ ] **Step 2: Write quality review compatibility test**

Add to `tests/test_tech_bottleneck_quality_review.py`:

```python
def test_classify_product_family_links_taxonomy_chain_terms() -> None:
    assert (
        classify_product_family(
            "HBM3E TSV 堆叠 高带宽内存",
            "Nvidia认证 客户验证 后段产能 良率",
        )
        == "hbm_high_end_memory"
    )
    assert (
        classify_product_family(
            "MLCC 高容量 高可靠 小型化",
            "AI server PDN GPU周边 高瞬态电流 满产",
        )
        == "mlcc_high_end_passives"
    )
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_tech_bottleneck_core_tech_gate.py::test_build_core_tech_gate_passes_chain_taxonomy_terms_without_generic_domestic_substitution \
  tests/test_tech_bottleneck_quality_review.py::test_classify_product_family_links_taxonomy_chain_terms \
  -q
```

Expected: FAIL because the existing gate/product family dictionaries do not include HBM and MLCC taxonomy families.

- [ ] **Step 4: Add taxonomy chain ids to existing dictionaries**

Modify `src/stock_research/tech_bottleneck_core_tech_gate.py`:

```python
PASS_PRODUCT_FAMILIES = [
    ...
    "ai_optical_interconnect",
    "hbm_high_end_memory",
    "mlcc_high_end_passives",
]

PASS_TERMS.update(
    {
        "ai_optical_interconnect": ["光通信模块", "高速光模块", "800G", "1.6T", "3.2T", "CPO", "硅光", "光引擎"],
        "hbm_high_end_memory": ["HBM", "HBM3E", "HBM4", "TSV", "高带宽内存", "后段产能"],
        "mlcc_high_end_passives": ["MLCC", "多层陶瓷电容器", "高容量", "高可靠", "AI server PDN"],
    }
)
```

Modify `src/stock_research/tech_bottleneck_quality_review.py`:

```python
PRODUCT_FAMILIES.update(
    {
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
    }
)
```

If the files use literal dictionaries instead of `.update`, add the entries inside the existing dictionaries rather than appending `.update`.

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_tech_bottleneck_core_tech_gate.py \
  tests/test_tech_bottleneck_quality_review.py \
  tests/test_tech_chain_taxonomy.py \
  -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/tech_bottleneck_core_tech_gate.py src/stock_research/tech_bottleneck_quality_review.py tests/test_tech_bottleneck_core_tech_gate.py tests/test_tech_bottleneck_quality_review.py
git commit -m "feat: connect taxonomy chains to bottleneck review"
```

---

### Task 7: Real Replay and Validation Artifacts

**Files:**
- Modify only if needed: `docs/tech-bottleneck-discovery-runbook.md`
- Runtime outputs: `outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/tech_chain_taxonomy_review/`

- [ ] **Step 1: Run focused tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_tech_chain_taxonomy.py \
  tests/test_tech_bottleneck_core_tech_gate.py \
  tests/test_tech_bottleneck_quality_review.py \
  tests/test_tech_bottleneck_core_leader_miss_audit.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run taxonomy review on current top100 dataset**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli tech-chain-taxonomy-review \
  --candidates-csv outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/candidates_top100.csv \
  --evidence-csv outputs/tech_bottleneck_discovery/pilot_top50_20250101_20260607/combined_evidence_with_official_product/evidence.csv \
  --taxonomy-json data/manual/tech_chain_taxonomy_v1.json \
  --output-dir outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/tech_chain_taxonomy_review
```

Expected output JSON includes:

```json
{
  "chain_mapping": "outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/tech_chain_taxonomy_review/chain_mapping.csv",
  "chain_evidence_review": "outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/tech_chain_taxonomy_review/chain_evidence_review.csv",
  "chain_quality_review": "outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/tech_chain_taxonomy_review/chain_quality_review.csv"
}
```

- [ ] **Step 3: Summarize core leader outcomes**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'
import pandas as pd
base = "outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/tech_chain_taxonomy_review"
ids = ["CN:SZ:002371", "CN:SZ:300502", "CN:SZ:300308", "CN:SZ:300476", "CN:SH:688256", "CN:SZ:300394"]
mapping = pd.read_csv(f"{base}/chain_mapping.csv")
quality = pd.read_csv(f"{base}/chain_quality_review.csv")
print(mapping[mapping["asset_id"].isin(ids)][["asset_id", "stock_name", "trade_date", "primary_chain_id", "product_exposure_quality"]].to_string(index=False))
print(quality[quality["asset_id"].isin(ids)][["asset_id", "stock_name", "trade_date", "primary_chain_id", "chain_decision", "matched_bottleneck_dimensions", "decision_reason"]].to_string(index=False))
PY
```

Expected: optical leaders map to `ai_optical_interconnect`, 寒武纪 maps to `ai_compute_chips`, 胜宏科技 maps to `ai_server_pcb`, 北方华创 maps to `semiconductor_equipment`.

- [ ] **Step 4: Run formatting and regression checks**

Run:

```bash
git diff --check
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_tech_chain_taxonomy.py \
  tests/test_tech_bottleneck_core_tech_gate.py \
  tests/test_tech_bottleneck_quality_review.py \
  tests/test_tech_bottleneck_targeted_p2_backfill.py \
  tests/test_tech_bottleneck_core_tech_top100.py \
  -q
```

Expected: `git diff --check` exits 0 and tests pass.

- [ ] **Step 5: Commit validation run support**

Do not commit generated `outputs/` files unless the repository already tracks comparable experiment outputs. Commit only code, tests, taxonomy config, and docs:

```bash
git status --short
git add data/manual/tech_chain_taxonomy_v1.json src/stock_research/tech_chain_taxonomy.py src/stock_research/cli.py src/stock_research/tech_bottleneck_core_tech_gate.py src/stock_research/tech_bottleneck_quality_review.py tests/test_tech_chain_taxonomy.py tests/test_tech_bottleneck_core_tech_gate.py tests/test_tech_bottleneck_quality_review.py
git commit -m "feat: add tech chain taxonomy review"
```

If every implementation task already committed its changes, this final commit should have nothing to commit. In that case, record the output paths and validation numbers in the final response.

---

## Self-Review Notes

- Spec coverage: the plan covers taxonomy config, chain schema, candidate mapping, evidence mapping, P1/P2-compatible chain decisions, CLI outputs, and validation on core leaders plus top100.
- Scope control: the plan does not change ranking, portfolio construction, or live web scraping.
- PIT safety: evidence mapping uses `as_of_safe == True`; future evidence cannot upgrade chain evidence.
- Configuration boundary: chain definitions live in JSON and the review logic is generic.
