# Tech Bottleneck Targeted P2 Evidence Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a targeted evidence-completion step for the current five-asset P2 tech-bottleneck queue, adding only point-in-time safe product-family bridge evidence and then re-running strict quality review.

**Architecture:** Add one focused module, `tech_bottleneck_targeted_p2_backfill.py`, that audits P2 evidence lineage, creates deterministic bridge suggestions, emits derived bridge evidence, combines evidence, and writes a promotion delta report. Reuse existing `tech_bottleneck_quality_review.run_quality_review_from_files` for strict re-review; do not change P1 auto-approval rules.

**Tech Stack:** Python, pandas, pytest, existing CSV artifact workflow, existing `tech_bottleneck_evidence_backfill.normalize_evidence_rows`, existing `tech_bottleneck_quality_review` runner.

---

## File Structure

- Create `src/stock_research/tech_bottleneck_targeted_p2_backfill.py`
  - Owns deterministic bridge target definitions for the current P2 assets.
  - Builds `targeted_evidence_gap_audit.csv`.
  - Builds `product_family_bridge_suggestions.csv`.
  - Builds `targeted_backfill_evidence.csv`.
  - Combines original and bridge evidence.
  - Writes `promotion_delta.md` and `manifest.json`.

- Create `tests/test_tech_bottleneck_targeted_p2_backfill.py`
  - Unit tests for candidate filtering, lineage audit, bridge suggestion generation, PIT-safe bridge evidence creation, artifact writing, and promotion delta rendering.

- Modify `src/stock_research/cli.py`
  - Add optional file-based command `tech-bottleneck-targeted-p2-backfill`.
  - Dispatch should call the new module with `Path` arguments.

- Modify `tests/test_tech_bottleneck_targeted_p2_backfill.py`
  - Add CLI parser and dispatch tests after module tests pass.

Generated outputs live under:

`outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill/`

---

### Task 1: Targeted P2 Backfill Core Module

**Files:**
- Create: `src/stock_research/tech_bottleneck_targeted_p2_backfill.py`
- Create: `tests/test_tech_bottleneck_targeted_p2_backfill.py`

- [ ] **Step 1: Write failing tests for candidate filtering and bridge suggestions**

Create `tests/test_tech_bottleneck_targeted_p2_backfill.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_targeted_p2_backfill import (
    BRIDGE_TARGETS,
    build_bridge_suggestions,
    build_targeted_gap_audit,
    normalize_p2_mapping_queue,
)


def test_normalize_p2_mapping_queue_keeps_only_mapping_review_rows() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "trade_date": "2025-06-20",
                "p3_decision": "needs_product_family_mapping",
                "review_priority": "P2_mapping_review",
                "next_evidence_need": "needs_product_family_mapping",
                "candidate_dates_for_asset": "2025-06-20",
            },
            {
                "asset_id": "CN:SZ:000001",
                "stock_name": "非目标",
                "trade_date": "2025-06-20",
                "p3_decision": "needs_more_evidence",
                "review_priority": "P2_evidence_review",
                "next_evidence_need": "needs_capacity_evidence",
            },
        ]
    )

    normalized = normalize_p2_mapping_queue(queue)

    assert normalized["asset_id"].tolist() == ["CN:SZ:300394"]
    assert normalized.iloc[0]["candidate_trade_date"] == "2025-06-20"
    assert normalized.iloc[0]["bridge_family"] == "optical_communication_components"


def test_build_targeted_gap_audit_counts_existing_family_evidence() -> None:
    queue = normalize_p2_mapping_queue(
        pd.DataFrame(
            [
                {
                    "asset_id": "CN:SZ:300394",
                    "stock_name": "天孚通信",
                    "trade_date": "2025-06-20",
                    "p3_decision": "needs_product_family_mapping",
                    "review_priority": "P2_mapping_review",
                    "next_evidence_need": "needs_product_family_mapping",
                }
            ]
        )
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-06-01",
                "evidence_type": "product_revenue_exposure",
                "evidence_snippet": "光器件收入增长",
                "matched_keyword": "",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-06-02",
                "evidence_type": "bottleneck_keyword",
                "evidence_snippet": "高速光引擎国产替代",
                "matched_keyword": "国产替代",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-06-03",
                "evidence_type": "technical_barrier",
                "evidence_snippet": "CPO光通信器件技术壁垒",
                "matched_keyword": "技术壁垒",
                "as_of_safe": True,
            },
        ]
    )

    audit = build_targeted_gap_audit(queue=queue, evidence=evidence)
    row = audit.iloc[0]

    assert row["asset_id"] == "CN:SZ:300394"
    assert row["candidate_bridge_family"] == "optical_communication_components"
    assert row["product_evidence_count"] == 1
    assert row["bottleneck_evidence_count"] == 1
    assert row["technical_evidence_count"] == 1
    assert row["missing_bridge_side"] == "missing_product_family_on_semantic_evidence"


def test_build_bridge_suggestions_requires_product_and_semantic_terms() -> None:
    queue = normalize_p2_mapping_queue(
        pd.DataFrame(
            [
                {
                    "asset_id": "CN:SZ:300394",
                    "stock_name": "天孚通信",
                    "trade_date": "2025-06-20",
                    "p3_decision": "needs_product_family_mapping",
                    "review_priority": "P2_mapping_review",
                    "next_evidence_need": "needs_product_family_mapping",
                }
            ]
        )
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-06-02",
                "evidence_type": "bottleneck_keyword",
                "evidence_snippet": "高速光引擎国产替代并进入客户导入阶段",
                "matched_keyword": "国产替代",
                "as_of_safe": True,
                "source_id": "r1",
                "source_type": "research_report",
            }
        ]
    )

    suggestions = build_bridge_suggestions(queue=queue, evidence=evidence)
    row = suggestions.iloc[0]

    assert row["asset_id"] == "CN:SZ:300394"
    assert row["bridge_family"] == "optical_communication_components"
    assert row["bridge_status"] == "bridgeable"
    assert "光引擎" in row["matched_product_terms"]
    assert "国产替代" in row["matched_semantic_terms"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_targeted_p2_backfill.py -q
```

Expected: fails with missing module.

- [ ] **Step 3: Implement candidate filtering, audit, and suggestions**

Create `src/stock_research/tech_bottleneck_targeted_p2_backfill.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


TARGET_ASSET_FAMILIES = {
    "CN:SZ:002859": "semiconductor_materials_components",
    "CN:SZ:300567": "semiconductor_testing_metrology",
    "CN:SZ:300394": "optical_communication_components",
    "CN:SZ:002371": "semiconductor_equipment",
    "CN:SH:688686": "semiconductor_testing_metrology",
}

BRIDGE_TARGETS = {
    "semiconductor_materials_components": {
        "product_terms": ["载带", "离型膜", "MLCC离型膜", "半导体材料", "电子元件材料"],
        "semantic_terms": ["国产替代", "技术壁垒", "客户认证", "产能", "半导体封装"],
    },
    "semiconductor_testing_metrology": {
        "product_terms": ["半导体检测", "量测设备", "AOI", "测试设备", "面板检测", "机器视觉", "视觉检测"],
        "semantic_terms": ["国产替代", "先进封装", "技术壁垒", "客户导入", "产能", "量产", "半导体"],
    },
    "optical_communication_components": {
        "product_terms": ["光器件", "光模块", "高速光引擎", "光引擎", "CPO", "光通信器件"],
        "semantic_terms": ["国产替代", "高速率", "AI算力", "客户导入", "量产"],
    },
    "semiconductor_equipment": {
        "product_terms": ["刻蚀", "PVD", "CVD", "清洗设备", "热处理设备", "半导体设备"],
        "semantic_terms": ["国产替代", "先进制程", "技术壁垒", "客户导入", "产能"],
    },
}

P2_QUEUE_COLUMNS = [
    "asset_id",
    "stock_name",
    "candidate_trade_date",
    "p3_decision",
    "review_priority",
    "next_evidence_need",
    "bridge_family",
]


def normalize_p2_mapping_queue(queue: pd.DataFrame) -> pd.DataFrame:
    frame = queue.copy()
    for column in ["asset_id", "stock_name", "trade_date", "p3_decision", "review_priority", "next_evidence_need"]:
        if column not in frame.columns:
            frame[column] = ""
    frame["asset_id"] = frame["asset_id"].astype("string").fillna("")
    frame["stock_name"] = frame["stock_name"].astype("string").fillna("")
    frame["candidate_trade_date"] = frame["trade_date"].map(_date_text)
    frame["bridge_family"] = frame["asset_id"].map(TARGET_ASSET_FAMILIES).fillna("")
    frame = frame[
        frame["p3_decision"].eq("needs_product_family_mapping")
        & frame["review_priority"].eq("P2_mapping_review")
        & frame["next_evidence_need"].eq("needs_product_family_mapping")
        & frame["bridge_family"].ne("")
        & frame["candidate_trade_date"].ne("")
    ].copy()
    return frame.reindex(columns=P2_QUEUE_COLUMNS)


def build_targeted_gap_audit(*, queue: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    normalized_evidence = _normalize_evidence(evidence)
    rows: list[dict[str, Any]] = []
    for candidate in queue.to_dict("records"):
        asset_id = candidate["asset_id"]
        candidate_date = candidate["candidate_trade_date"]
        family = candidate["bridge_family"]
        asset_evidence = _pit_safe_asset_evidence(normalized_evidence, asset_id, candidate_date)
        rows.append(
            {
                "asset_id": asset_id,
                "stock_name": candidate["stock_name"],
                "candidate_trade_date": candidate_date,
                "candidate_bridge_family": family,
                "product_evidence_count": _count_hits(asset_evidence, family, ["product_revenue_exposure"]),
                "bottleneck_evidence_count": _count_hits(asset_evidence, family, ["bottleneck_keyword"]),
                "technical_evidence_count": _count_hits(asset_evidence, family, ["technical_barrier"]),
                "support_evidence_count": _count_hits(
                    asset_evidence,
                    family,
                    ["capacity", "customer_certification", "news_or_announcement_catalyst"],
                ),
                "current_blocker": candidate["next_evidence_need"],
                "missing_bridge_side": _missing_bridge_side(asset_evidence, family),
            }
        )
    return pd.DataFrame(rows)


def build_bridge_suggestions(*, queue: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    normalized_evidence = _normalize_evidence(evidence)
    rows: list[dict[str, Any]] = []
    for candidate in queue.to_dict("records"):
        asset_id = candidate["asset_id"]
        candidate_date = candidate["candidate_trade_date"]
        family = candidate["bridge_family"]
        target = BRIDGE_TARGETS[family]
        asset_evidence = _pit_safe_asset_evidence(normalized_evidence, asset_id, candidate_date)
        matched_rows = []
        product_terms: set[str] = set()
        semantic_terms: set[str] = set()
        for item in asset_evidence.to_dict("records"):
            text = _evidence_text(item)
            matched_product = [term for term in target["product_terms"] if term in text]
            matched_semantic = [term for term in target["semantic_terms"] if term in text]
            if matched_product and matched_semantic:
                matched_rows.append(str(item.get("source_id") or ""))
                product_terms.update(matched_product)
                semantic_terms.update(matched_semantic)
        rows.append(
            {
                "asset_id": asset_id,
                "stock_name": candidate["stock_name"],
                "candidate_trade_date": candidate_date,
                "bridge_family": family,
                "bridge_status": "bridgeable" if product_terms and semantic_terms else "insufficient_pit_safe_bridge_evidence",
                "matched_product_terms": "|".join(sorted(product_terms)),
                "matched_semantic_terms": "|".join(sorted(semantic_terms)),
                "source_evidence_ids": "|".join(sorted(value for value in set(matched_rows) if value)),
            }
        )
    return pd.DataFrame(rows)
```

Also include private helpers:

```python
def _date_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat"}:
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    if len(text) == 8 and text.isdigit():
        parsed = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    else:
        parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "y"}


def _normalize_evidence(evidence: pd.DataFrame) -> pd.DataFrame:
    frame = evidence.copy()
    for column in [
        "asset_id",
        "stock_name",
        "candidate_trade_date",
        "as_of_date",
        "evidence_date",
        "source_type",
        "source_id",
        "source_title",
        "source_url",
        "evidence_type",
        "matched_keyword",
        "evidence_snippet",
        "as_of_safe",
    ]:
        if column not in frame.columns:
            frame[column] = ""
    frame["candidate_trade_date"] = frame["candidate_trade_date"].map(_date_text)
    frame["evidence_date"] = frame["evidence_date"].map(_date_text)
    frame["as_of_safe"] = frame["as_of_safe"].map(_bool_value)
    return frame


def _pit_safe_asset_evidence(evidence: pd.DataFrame, asset_id: str, candidate_date: str) -> pd.DataFrame:
    return evidence[
        evidence["asset_id"].astype(str).eq(asset_id)
        & evidence["as_of_safe"].eq(True)
        & evidence["evidence_date"].ne("")
        & evidence["evidence_date"].le(candidate_date)
    ].copy()


def _evidence_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(column) or "")
        for column in ["source_title", "matched_keyword", "evidence_snippet", "metadata_json"]
    )


def _count_hits(frame: pd.DataFrame, family: str, evidence_types: list[str]) -> int:
    if frame.empty:
        return 0
    target = BRIDGE_TARGETS[family]
    terms = target["product_terms"] + target["semantic_terms"]
    subset = frame[frame["evidence_type"].isin(evidence_types)]
    return int(sum(any(term in _evidence_text(row) for term in terms) for row in subset.to_dict("records")))


def _missing_bridge_side(frame: pd.DataFrame, family: str) -> str:
    product = _count_hits(frame, family, ["product_revenue_exposure"])
    semantic = _count_hits(frame, family, ["bottleneck_keyword", "technical_barrier", "capacity", "customer_certification", "news_or_announcement_catalyst"])
    if product == 0 and semantic == 0:
        return "insufficient_pit_safe_bridge_evidence"
    if product == 0:
        return "missing_product_family_on_product_evidence"
    if semantic == 0:
        return "missing_product_family_on_semantic_evidence"
    return "missing_product_family_on_semantic_evidence"
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_targeted_p2_backfill.py -q
```

Expected: tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/stock_research/tech_bottleneck_targeted_p2_backfill.py tests/test_tech_bottleneck_targeted_p2_backfill.py
git commit -m "feat: add targeted p2 bottleneck bridge audit"
```

---

### Task 2: Derived Bridge Evidence and Artifacts

**Files:**
- Modify: `src/stock_research/tech_bottleneck_targeted_p2_backfill.py`
- Modify: `tests/test_tech_bottleneck_targeted_p2_backfill.py`

- [ ] **Step 1: Add failing tests for bridge evidence and artifact writer**

Append to `tests/test_tech_bottleneck_targeted_p2_backfill.py`:

```python
from stock_research.tech_bottleneck_targeted_p2_backfill import (
    build_targeted_bridge_evidence,
    run_targeted_p2_backfill_from_files,
    write_targeted_backfill_artifacts,
)


def test_build_targeted_bridge_evidence_marks_derived_proxy_rows() -> None:
    queue = normalize_p2_mapping_queue(
        pd.DataFrame(
            [
                {
                    "asset_id": "CN:SZ:300394",
                    "stock_name": "天孚通信",
                    "trade_date": "2025-06-20",
                    "p3_decision": "needs_product_family_mapping",
                    "review_priority": "P2_mapping_review",
                    "next_evidence_need": "needs_product_family_mapping",
                }
            ]
        )
    )
    evidence = pd.DataFrame(
        [
            {
                "run_id": "source-run",
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "candidate_trade_date": "2025-06-20",
                "as_of_date": "2025-06-20",
                "evidence_date": "2025-06-02",
                "source_type": "research_report",
                "source_id": "r1",
                "source_title": "天孚通信高速光引擎国产替代",
                "source_url": "https://example.com/r1",
                "evidence_type": "bottleneck_keyword",
                "matched_keyword": "国产替代",
                "evidence_snippet": "高速光引擎国产替代并量产",
                "source_confidence": "strong",
                "is_proxy": False,
                "as_of_safe": True,
                "metadata_json": "{}",
            }
        ]
    )
    suggestions = build_bridge_suggestions(queue=queue, evidence=evidence)

    bridge = build_targeted_bridge_evidence(queue=queue, evidence=evidence, suggestions=suggestions, run_id="targeted-run")
    row = bridge.iloc[0]

    assert row["run_id"] == "targeted-run"
    assert row["source_type"] == "derived_product_family_bridge"
    assert row["evidence_type"] == "bottleneck_keyword"
    assert row["matched_keyword"].startswith("optical_communication_components:")
    assert row["is_proxy"] is True
    assert row["as_of_safe"] is True
    metadata = json.loads(row["metadata_json"])
    assert metadata["bridge_family"] == "optical_communication_components"
    assert metadata["source_candidate_trade_date"] == "2025-06-20"


def test_write_targeted_backfill_artifacts_writes_required_files(tmp_path: Path) -> None:
    audit = pd.DataFrame([{"asset_id": "A", "candidate_bridge_family": "optical_communication_components"}])
    suggestions = pd.DataFrame([{"asset_id": "A", "bridge_status": "bridgeable"}])
    bridge = pd.DataFrame([{"asset_id": "A", "evidence_type": "bottleneck_keyword", "source_type": "derived_product_family_bridge"}])
    combined = pd.DataFrame([{"asset_id": "A", "evidence_type": "bottleneck_keyword"}])
    review = pd.DataFrame([{"asset_id": "A", "p3_decision": "auto_approve"}])
    paths = write_targeted_backfill_artifacts(
        output_dir=tmp_path,
        audit=audit,
        suggestions=suggestions,
        bridge_evidence=bridge,
        combined_evidence=combined,
        review_after=review,
        promotion_delta_md="# delta\n",
        manifest={"p2_asset_count_before": 1},
    )

    assert paths["targeted_evidence_gap_audit"].exists()
    assert paths["product_family_bridge_suggestions"].exists()
    assert paths["targeted_backfill_evidence"].exists()
    assert paths["combined_evidence_after_targeted_backfill"].exists()
    assert paths["quality_review_after_targeted_backfill"].exists()
    assert paths["promotion_delta"].read_text(encoding="utf-8") == "# delta\n"
    assert json.loads(paths["manifest"].read_text(encoding="utf-8"))["p2_asset_count_before"] == 1
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_targeted_p2_backfill.py::test_build_targeted_bridge_evidence_marks_derived_proxy_rows tests/test_tech_bottleneck_targeted_p2_backfill.py::test_write_targeted_backfill_artifacts_writes_required_files -q
```

Expected: missing functions.

- [ ] **Step 3: Implement bridge evidence and artifact functions**

Add to `src/stock_research/tech_bottleneck_targeted_p2_backfill.py`:

```python
from stock_research.tech_bottleneck_evidence_backfill import normalize_evidence_rows


def build_targeted_bridge_evidence(
    *,
    queue: pd.DataFrame,
    evidence: pd.DataFrame,
    suggestions: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    normalized_evidence = _normalize_evidence(evidence)
    rows: list[dict[str, Any]] = []
    bridgeable = suggestions[suggestions["bridge_status"].eq("bridgeable")]
    for suggestion in bridgeable.to_dict("records"):
        asset_id = suggestion["asset_id"]
        candidate_date = suggestion["candidate_trade_date"]
        family = suggestion["bridge_family"]
        asset_evidence = _pit_safe_asset_evidence(normalized_evidence, asset_id, candidate_date)
        source = _first_bridge_source(asset_evidence, family)
        if source is None:
            continue
        rows.append(
            {
                "run_id": run_id,
                "asset_id": asset_id,
                "stock_name": suggestion.get("stock_name", ""),
                "candidate_trade_date": candidate_date,
                "as_of_date": candidate_date,
                "evidence_date": source.get("evidence_date", ""),
                "source_type": "derived_product_family_bridge",
                "source_id": f"{asset_id}:{candidate_date}:{family}:bridge",
                "source_title": source.get("source_title", ""),
                "source_url": source.get("source_url", ""),
                "evidence_type": source.get("evidence_type", "bottleneck_keyword"),
                "matched_keyword": f"{family}:{suggestion.get('matched_product_terms', '')}|{suggestion.get('matched_semantic_terms', '')}",
                "evidence_snippet": source.get("evidence_snippet", ""),
                "source_confidence": "medium",
                "is_proxy": True,
                "as_of_safe": True,
                "metadata_json": {
                    "bridge_family": family,
                    "bridge_reason": "matched product and semantic terms in PIT-safe source evidence",
                    "source_evidence_ids": suggestion.get("source_evidence_ids", ""),
                    "source_candidate_trade_date": candidate_date,
                },
            }
        )
    return normalize_evidence_rows(pd.DataFrame(rows))


def combine_evidence(*, original_evidence: pd.DataFrame, bridge_evidence: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([original_evidence, bridge_evidence], ignore_index=True, sort=False)


def write_targeted_backfill_artifacts(
    *,
    output_dir: Path,
    audit: pd.DataFrame,
    suggestions: pd.DataFrame,
    bridge_evidence: pd.DataFrame,
    combined_evidence: pd.DataFrame,
    review_after: pd.DataFrame,
    promotion_delta_md: str,
    manifest: dict[str, Any],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "targeted_evidence_gap_audit": output_dir / "targeted_evidence_gap_audit.csv",
        "product_family_bridge_suggestions": output_dir / "product_family_bridge_suggestions.csv",
        "targeted_backfill_evidence": output_dir / "targeted_backfill_evidence.csv",
        "combined_evidence_after_targeted_backfill": output_dir / "combined_evidence_after_targeted_backfill.csv",
        "quality_review_after_targeted_backfill": output_dir / "quality_review_after_targeted_backfill.csv",
        "promotion_delta": output_dir / "promotion_delta.md",
        "manifest": output_dir / "manifest.json",
    }
    audit.to_csv(paths["targeted_evidence_gap_audit"], index=False)
    suggestions.to_csv(paths["product_family_bridge_suggestions"], index=False)
    bridge_evidence.to_csv(paths["targeted_backfill_evidence"], index=False)
    combined_evidence.to_csv(paths["combined_evidence_after_targeted_backfill"], index=False)
    review_after.to_csv(paths["quality_review_after_targeted_backfill"], index=False)
    paths["promotion_delta"].write_text(promotion_delta_md, encoding="utf-8")
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths
```

Also add:

```python
def _first_bridge_source(frame: pd.DataFrame, family: str) -> dict[str, Any] | None:
    target = BRIDGE_TARGETS[family]
    for row in frame.to_dict("records"):
        text = _evidence_text(row)
        if any(term in text for term in target["product_terms"]) and any(term in text for term in target["semantic_terms"]):
            return row
    return None
```

- [ ] **Step 4: Run tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_targeted_p2_backfill.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/stock_research/tech_bottleneck_targeted_p2_backfill.py tests/test_tech_bottleneck_targeted_p2_backfill.py
git commit -m "feat: emit targeted p2 bridge evidence"
```

---

### Task 3: Promotion Delta Report

**Files:**
- Modify: `src/stock_research/tech_bottleneck_targeted_p2_backfill.py`
- Modify: `tests/test_tech_bottleneck_targeted_p2_backfill.py`

- [ ] **Step 1: Add failing tests for promotion delta and file runner**

Append:

```python
from stock_research.tech_bottleneck_targeted_p2_backfill import (
    render_promotion_delta,
)


def test_render_promotion_delta_lists_promoted_and_blocked_assets() -> None:
    before = pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "Alpha", "p3_decision": "needs_product_family_mapping"},
            {"asset_id": "B", "stock_name": "Beta", "p3_decision": "needs_product_family_mapping"},
        ]
    )
    after = pd.DataFrame(
        [
            {"asset_id": "A", "stock_name": "Alpha", "p3_decision": "auto_approve", "next_evidence_need": ""},
            {"asset_id": "B", "stock_name": "Beta", "p3_decision": "needs_product_family_mapping", "next_evidence_need": "needs_product_family_mapping"},
        ]
    )
    bridge = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "evidence_type": "bottleneck_keyword",
                "source_type": "derived_product_family_bridge",
                "metadata_json": json.dumps({"bridge_family": "optical_communication_components"}),
            }
        ]
    )

    markdown = render_promotion_delta(before_review=before, after_review=after, bridge_evidence=bridge)

    assert "P2 asset count before: 2" in markdown
    assert "P1 asset count after: 1" in markdown
    assert "Alpha (A)" in markdown
    assert "Beta (B): needs_product_family_mapping" in markdown
    assert "optical_communication_components" in markdown
```

- [ ] **Step 2: Run focused test and verify failure**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_targeted_p2_backfill.py::test_render_promotion_delta_lists_promoted_and_blocked_assets -q
```

Expected: missing function.

- [ ] **Step 3: Implement promotion delta**

Add:

```python
def render_promotion_delta(
    *,
    before_review: pd.DataFrame,
    after_review: pd.DataFrame,
    bridge_evidence: pd.DataFrame,
) -> str:
    before_p2 = before_review[before_review["p3_decision"].eq("needs_product_family_mapping")].copy()
    after_p1 = after_review[after_review["p3_decision"].eq("auto_approve")].copy()
    before_ids = set(before_p2["asset_id"].astype(str))
    promoted = after_p1[after_p1["asset_id"].astype(str).isin(before_ids)].drop_duplicates("asset_id")
    still_blocked = after_review[
        after_review["asset_id"].astype(str).isin(before_ids)
        & after_review["p3_decision"].isin(["needs_product_family_mapping", "needs_more_evidence", "reject_or_noise"])
    ].drop_duplicates("asset_id")
    lines = [
        "# Targeted P2 Backfill Promotion Delta",
        "",
        f"- P2 asset count before: {len(before_ids)}",
        f"- P1 asset count before: {before_review[before_review['p3_decision'].eq('auto_approve')]['asset_id'].nunique() if 'asset_id' in before_review else 0}",
        f"- P1 asset count after: {after_p1['asset_id'].nunique() if 'asset_id' in after_p1 else 0}",
        "",
        "## Promoted From P2 To P1",
    ]
    if promoted.empty:
        lines.append("- None")
    else:
        for row in promoted.to_dict("records"):
            lines.append(f"- {row.get('stock_name', '')} ({row.get('asset_id', '')})")
    lines += ["", "## Still Blocked"]
    if still_blocked.empty:
        lines.append("- None")
    else:
        for row in still_blocked.to_dict("records"):
            lines.append(f"- {row.get('stock_name', '')} ({row.get('asset_id', '')}): {row.get('next_evidence_need', row.get('p3_decision', ''))}")
    lines += ["", "## Added Evidence"]
    if bridge_evidence.empty:
        lines.append("- None")
    else:
        for _, row in bridge_evidence.iterrows():
            family = ""
            try:
                family = json.loads(str(row.get("metadata_json") or "{}")).get("bridge_family", "")
            except json.JSONDecodeError:
                family = ""
            lines.append(f"- {family}: {row.get('source_type', '')}/{row.get('evidence_type', '')}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run all targeted tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_targeted_p2_backfill.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/stock_research/tech_bottleneck_targeted_p2_backfill.py tests/test_tech_bottleneck_targeted_p2_backfill.py
git commit -m "feat: report targeted p2 promotion delta"
```

---

### Task 4: CLI Command and End-to-End Runner

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/tech_bottleneck_targeted_p2_backfill.py`
- Modify: `tests/test_tech_bottleneck_targeted_p2_backfill.py`

- [ ] **Step 1: Add failing CLI parser and dispatch tests**

Append:

```python
from stock_research.cli import build_parser, main


def test_cli_parser_accepts_targeted_p2_backfill_command() -> None:
    args = build_parser().parse_args(
        [
            "tech-bottleneck-targeted-p2-backfill",
            "--human-review-assets-csv",
            "human.csv",
            "--quality-review-csv",
            "quality.csv",
            "--evidence-csv",
            "evidence.csv",
            "--output-dir",
            "out",
        ]
    )

    assert args.command == "tech-bottleneck-targeted-p2-backfill"
    assert args.human_review_assets_csv == "human.csv"
    assert args.quality_review_csv == "quality.csv"
    assert args.evidence_csv == "evidence.csv"
    assert args.output_dir == "out"


def test_cli_dispatches_targeted_p2_backfill(monkeypatch, tmp_path: Path) -> None:
    calls = {}

    def fake_run(**kwargs):
        calls.update(kwargs)
        return {"manifest": tmp_path / "manifest.json"}

    monkeypatch.setattr(
        "stock_research.tech_bottleneck_targeted_p2_backfill.run_targeted_p2_backfill_from_files",
        fake_run,
    )

    main(
        [
            "tech-bottleneck-targeted-p2-backfill",
            "--human-review-assets-csv",
            "human.csv",
            "--quality-review-csv",
            "quality.csv",
            "--evidence-csv",
            "evidence.csv",
            "--output-dir",
            "out",
        ]
    )

    assert calls["human_review_assets_csv"] == Path("human.csv")
    assert calls["quality_review_csv"] == Path("quality.csv")
    assert calls["evidence_csv"] == Path("evidence.csv")
    assert calls["output_dir"] == Path("out")
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_targeted_p2_backfill.py::test_cli_parser_accepts_targeted_p2_backfill_command tests/test_tech_bottleneck_targeted_p2_backfill.py::test_cli_dispatches_targeted_p2_backfill -q
```

Expected: unknown command.

- [ ] **Step 3: Implement runner and CLI**

Add to module:

```python
def run_targeted_p2_backfill_from_files(
    *,
    human_review_assets_csv: Path,
    quality_review_csv: Path,
    evidence_csv: Path,
    output_dir: Path,
    run_id: str = "targeted-p2-backfill",
) -> dict[str, Path]:
    queue = normalize_p2_mapping_queue(pd.read_csv(human_review_assets_csv))
    before_review = pd.read_csv(quality_review_csv)
    evidence = pd.read_csv(evidence_csv, low_memory=False)
    audit = build_targeted_gap_audit(queue=queue, evidence=evidence)
    suggestions = build_bridge_suggestions(queue=queue, evidence=evidence)
    bridge = build_targeted_bridge_evidence(queue=queue, evidence=evidence, suggestions=suggestions, run_id=run_id)
    combined = combine_evidence(original_evidence=evidence, bridge_evidence=bridge)
    after_review = before_review.copy()
    delta_md = render_promotion_delta(before_review=before_review, after_review=after_review, bridge_evidence=bridge)
    manifest = {
        "p2_asset_count_before": int(queue["asset_id"].nunique()) if not queue.empty else 0,
        "bridge_evidence_count": int(len(bridge)),
        "bridgeable_count": int(suggestions["bridge_status"].eq("bridgeable").sum()) if not suggestions.empty else 0,
        "inputs": {
            "human_review_assets_csv": str(human_review_assets_csv),
            "quality_review_csv": str(quality_review_csv),
            "evidence_csv": str(evidence_csv),
        },
    }
    return write_targeted_backfill_artifacts(
        output_dir=output_dir,
        audit=audit,
        suggestions=suggestions,
        bridge_evidence=bridge,
        combined_evidence=combined,
        review_after=after_review,
        promotion_delta_md=delta_md,
        manifest=manifest,
    )
```

Note: this runner writes artifacts and combined evidence. The actual strict quality review re-run can happen in Task 5 using existing `tech-bottleneck-quality-review` against the combined evidence.

Add parser and dispatch in `src/stock_research/cli.py`:

```python
targeted_p2 = subparsers.add_parser("tech-bottleneck-targeted-p2-backfill")
targeted_p2.add_argument("--human-review-assets-csv", required=True)
targeted_p2.add_argument("--quality-review-csv", required=True)
targeted_p2.add_argument("--evidence-csv", required=True)
targeted_p2.add_argument("--output-dir", required=True)
```

Dispatch:

```python
elif args.command == "tech-bottleneck-targeted-p2-backfill":
    from stock_research.tech_bottleneck_targeted_p2_backfill import run_targeted_p2_backfill_from_files

    paths = run_targeted_p2_backfill_from_files(
        human_review_assets_csv=Path(args.human_review_assets_csv),
        quality_review_csv=Path(args.quality_review_csv),
        evidence_csv=Path(args.evidence_csv),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: Run targeted and CLI tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_targeted_p2_backfill.py -q
```

Expected: all targeted tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/stock_research/cli.py src/stock_research/tech_bottleneck_targeted_p2_backfill.py tests/test_tech_bottleneck_targeted_p2_backfill.py
git commit -m "feat: add targeted p2 backfill cli"
```

---

### Task 5: Real Run and Strict Re-Review

**Files:**
- Generated outputs only under `outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill/`
- No source changes unless verification exposes a defect.

- [ ] **Step 1: Run focused test suite**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_tech_bottleneck_targeted_p2_backfill.py \
  tests/test_tech_bottleneck_quality_review.py \
  tests/test_tech_bottleneck_core_tech_gate.py \
  tests/test_tech_bottleneck_core_tech_top100.py \
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Run targeted P2 backfill**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  tech-bottleneck-targeted-p2-backfill \
  --human-review-assets-csv outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/quality_review/human_review_assets.csv \
  --quality-review-csv outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/quality_review/quality_review.csv \
  --evidence-csv outputs/tech_bottleneck_discovery/pilot_top50_20250101_20260607/combined_evidence_with_official_product/evidence.csv \
  --output-dir outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill
```

Expected files:

- `targeted_evidence_gap_audit.csv`
- `product_family_bridge_suggestions.csv`
- `targeted_backfill_evidence.csv`
- `combined_evidence_after_targeted_backfill.csv`
- `quality_review_after_targeted_backfill.csv`
- `promotion_delta.md`
- `manifest.json`

- [ ] **Step 4: Re-run strict quality review using combined evidence**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  tech-bottleneck-quality-review \
  --candidates-csv outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/core_tech_gate/core_tech_candidates.csv \
  --evidence-hits-csv outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill/combined_evidence_after_targeted_backfill.csv \
  --product-rows-csv outputs/tech_bottleneck_discovery/pilot_top50_20250101_20260607/official_product_backfill/product_evidence.csv \
  --output-dir outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill/quality_review_after_targeted_backfill_run
```

Expected: quality review artifacts are written.

- [ ] **Step 5: Summarize real-run findings**

Read:

```text
outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill/manifest.json
outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill/product_family_bridge_suggestions.csv
outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill/targeted_backfill_evidence.csv
outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill/quality_review_after_targeted_backfill_run/manifest.json
outputs/tech_bottleneck_discovery/core_tech_top100_20250101_20260605/targeted_p2_backfill/quality_review_after_targeted_backfill_run/promotion_assets.csv
```

Report:

- P2 assets before.
- Bridgeable assets.
- Derived evidence row count.
- P1 assets before and after.
- P2 assets promoted to P1.
- Assets still blocked and why.

- [ ] **Step 6: Commit verification fixes if needed**

If code fixes were needed:

```bash
git add <changed source/test files>
git commit -m "fix: stabilize targeted p2 backfill"
```

If only ignored output files changed, do not commit generated artifacts.

---

## Self-Review

- Spec coverage: lineage audit is Task 1, bridge suggestions and derived evidence are Tasks 1-2, artifact outputs are Task 2, promotion delta is Task 3, CLI and real run are Tasks 4-5, strict re-review is Task 5.
- Scope check: plan stays on the five current P2 assets and does not expand universe, loosen P1, or add return tests.
- Type consistency: all public functions use pandas DataFrames and `Path` objects; generated evidence uses existing evidence column contract through `normalize_evidence_rows`.
- Marker scan: no unresolved implementation markers are intentionally left in the plan.
