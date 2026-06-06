# tech-bottleneck Evidence Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a candidate-scoped `tech-bottleneck-evidence-backfill` path that writes normalized evidence artifacts and lets readiness audit consume those artifacts without look-ahead.

**Architecture:** Add a focused evidence module that normalizes candidate dates, extracts evidence from existing DB frames, classifies text snippets into Serenity evidence types, writes file artifacts, and exposes a DB-backed runner. Extend readiness with an optional `evidence_csv` context and add CLI wiring for both backfill and readiness merge.

**Tech Stack:** Python 3, pandas, psycopg via existing `stock_research.db.connect/fetch_all`, argparse CLI, pytest, Markdown/CSV/JSON file artifacts.

---

## File Structure

- Create `src/stock_research/tech_bottleneck_evidence_backfill.py`
  - Owns evidence column constants, candidate date expansion, evidence normalization, keyword classification, existing-DB context conversion, artifact writing, DB loader, and file/DB runner.
- Create `tests/test_tech_bottleneck_evidence_backfill.py`
  - Unit tests for evidence normalization, as-of filtering, keyword classification, artifact output, and runner behavior with fixture loaders.
- Modify `src/stock_research/tech_bottleneck_readiness.py`
  - Add optional evidence artifact support to `run_readiness_audit_from_files`, `build_readiness_audit`, and the context merge path.
- Modify `tests/test_tech_bottleneck_readiness.py`
  - Add tests proving strong evidence CSV rows set readiness flags and unsafe/proxy product rows do not set `has_product_revenue_exposure`.
- Modify `src/stock_research/cli.py`
  - Import `run_evidence_backfill_from_files`.
  - Register `tech-bottleneck-evidence-backfill`.
  - Add `--evidence-csv` to `tech-bottleneck-data-readiness-audit`.
- Modify `docs/tech-bottleneck-discovery-runbook.md`
  - Document the backfill-before-readiness workflow.
- Create `data/manual/tech_bottleneck_evidence_backfill_candidates_example.csv`
  - Tiny smoke fixture for CLI help and local artifact generation.

## Data Contracts

### Evidence Columns

```python
EVIDENCE_COLUMNS = [
    "run_id",
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
    "source_confidence",
    "is_proxy",
    "as_of_safe",
    "metadata_json",
]
```

### Evidence Type Mapping Into Readiness

```python
READINESS_EVIDENCE_TYPE_MAP = {
    "product_revenue_exposure": "has_product_revenue_exposure",
    "bottleneck_keyword": "has_bottleneck_keywords",
    "capacity": "has_capacity_evidence",
    "customer_certification": "has_customer_certification_evidence",
    "technical_barrier": "has_patent_or_technical_barrier",
    "patent_proxy": "has_patent_or_technical_barrier",
    "news_or_announcement_catalyst": "has_news_or_announcement_catalyst",
    "invalidation": "has_invalidation_evidence",
}
```

`product_revenue_exposure` sets `has_product_revenue_exposure` only when `source_confidence == "strong"`, `is_proxy == False`, and `as_of_safe == True`.

## Task 1: Evidence Normalization Module

**Files:**
- Create: `src/stock_research/tech_bottleneck_evidence_backfill.py`
- Create: `tests/test_tech_bottleneck_evidence_backfill.py`

- [ ] **Step 1: Write failing tests for candidate normalization and evidence row normalization**

Add to `tests/test_tech_bottleneck_evidence_backfill.py`:

```python
from __future__ import annotations

import json

import pandas as pd
import pytest

from stock_research.tech_bottleneck_evidence_backfill import (
    EVIDENCE_COLUMNS,
    classify_text_evidence,
    normalize_evidence_rows,
    normalize_evidence_candidates,
)


def test_normalize_evidence_candidates_requires_asset_id() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        normalize_evidence_candidates(
            pd.DataFrame([{"stock_name": "缺代码"}]),
            run_date="2026-06-06",
            start_date=None,
            end_date=None,
            lookback_days=365,
        )


def test_normalize_evidence_candidates_preserves_trade_date_as_as_of_date() -> None:
    rows = normalize_evidence_candidates(
        pd.DataFrame(
            [
                {"asset_id": "CN:SH:688001", "stock_name": "示例科技", "trade_date": "2025-01-10", "rank": 1},
                {"asset_id": "CN:SZ:300001", "trade_date": "2025-02-10", "rank": 2},
            ]
        ),
        run_date="2026-06-06",
        start_date="2025-01-01",
        end_date="2025-01-31",
        lookback_days=365,
    )

    assert rows["asset_id"].tolist() == ["CN:SH:688001"]
    assert rows.iloc[0]["as_of_date"] == "2025-01-10"
    assert rows.iloc[0]["lookback_days"] == 365
    assert rows.iloc[0]["rank"] == "1"


def test_normalize_evidence_rows_outputs_contract_and_json_metadata() -> None:
    evidence = normalize_evidence_rows(
        pd.DataFrame(
            [
                {
                    "run_id": "unit",
                    "asset_id": "CN:SH:688001",
                    "stock_name": "示例科技",
                    "candidate_trade_date": "2025-01-10",
                    "as_of_date": "2025-01-10",
                    "evidence_date": "2024-12-31",
                    "source_type": "finance.main_business_composition",
                    "source_id": "CN:SH:688001:2024-12-31:AI材料",
                    "source_title": "主营构成",
                    "evidence_type": "product_revenue_exposure",
                    "matched_keyword": "",
                    "evidence_snippet": "AI材料收入占比45%",
                    "source_confidence": "strong",
                    "is_proxy": False,
                    "as_of_safe": True,
                    "metadata_json": {"revenue_ratio": 45},
                }
            ]
        )
    )

    assert list(evidence.columns) == EVIDENCE_COLUMNS
    assert json.loads(evidence.iloc[0]["metadata_json"]) == {"revenue_ratio": 45}
    assert evidence.iloc[0]["is_proxy"] is False
    assert evidence.iloc[0]["as_of_safe"] is True


def test_classify_text_evidence_emits_expected_evidence_types() -> None:
    matches = classify_text_evidence(
        text="关键材料国产替代加速，扩产爬坡，客户认证推进，技术壁垒高，风险是需求不及预期。",
        source_type="research.stock_report_event",
        source_id="r1",
        source_title="关键材料跟踪",
        source_date="2025-01-05",
    )

    evidence_types = {row["evidence_type"] for row in matches}
    assert {
        "bottleneck_keyword",
        "capacity",
        "customer_certification",
        "technical_barrier",
        "invalidation",
    }.issubset(evidence_types)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_evidence_backfill.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `stock_research.tech_bottleneck_evidence_backfill`.

- [ ] **Step 3: Implement constants, candidate normalization, evidence normalization, and keyword classification**

Create `src/stock_research/tech_bottleneck_evidence_backfill.py` with the public functions imported by the tests. Reuse keyword lists from `stock_research.tech_bottleneck_readiness` so the readiness and backfill classifiers do not drift:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.db import connect, fetch_all
from stock_research.tech_bottleneck_readiness import (
    BOTTLENECK_KEYWORDS,
    CAPACITY_KEYWORDS,
    CUSTOMER_CERTIFICATION_KEYWORDS,
    INVALIDATION_KEYWORDS,
    TECHNICAL_BARRIER_KEYWORDS,
)


EVIDENCE_COLUMNS = [
    "run_id",
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
    "source_confidence",
    "is_proxy",
    "as_of_safe",
    "metadata_json",
]


TEXT_EVIDENCE_GROUPS = [
    ("bottleneck_keyword", BOTTLENECK_KEYWORDS),
    ("capacity", CAPACITY_KEYWORDS),
    ("customer_certification", CUSTOMER_CERTIFICATION_KEYWORDS),
    ("technical_barrier", TECHNICAL_BARRIER_KEYWORDS),
    ("invalidation", INVALIDATION_KEYWORDS),
]


def normalize_evidence_candidates(
    candidates: pd.DataFrame,
    *,
    run_date: str,
    start_date: str | None,
    end_date: str | None,
    lookback_days: int,
) -> pd.DataFrame:
    if "asset_id" not in candidates.columns:
        raise ValueError("evidence candidates must include asset_id")

    normalized = candidates.copy()
    for column in ["stock_name", "trade_date", "candidate_source", "rank"]:
        if column not in normalized.columns:
            normalized[column] = ""
    normalized["asset_id"] = normalized["asset_id"].map(_safe_text)
    normalized = normalized[normalized["asset_id"] != ""].copy()
    normalized["stock_name"] = normalized["stock_name"].map(_safe_text)
    normalized["trade_date"] = normalized["trade_date"].map(_date_text)
    normalized["candidate_source"] = normalized["candidate_source"].map(_safe_text)
    normalized["rank"] = normalized["rank"].map(_safe_text)
    normalized["as_of_date"] = normalized["trade_date"].map(lambda value: value or _date_text(run_date))
    normalized["lookback_days"] = int(lookback_days)

    start_ts = _date_timestamp(start_date)
    end_ts = _date_timestamp(end_date)
    as_of_ts = pd.to_datetime(normalized["as_of_date"], errors="coerce")
    if start_ts is not None:
        normalized = normalized[as_of_ts >= start_ts].copy()
        as_of_ts = pd.to_datetime(normalized["as_of_date"], errors="coerce")
    if end_ts is not None:
        normalized = normalized[as_of_ts <= end_ts].copy()

    return normalized[
        ["asset_id", "stock_name", "trade_date", "candidate_source", "rank", "as_of_date", "lookback_days"]
    ]


def normalize_evidence_rows(rows: pd.DataFrame) -> pd.DataFrame:
    normalized = rows.copy()
    for column in EVIDENCE_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = False if column in ["is_proxy", "as_of_safe"] else ""
    for column in [
        "run_id",
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
        "source_confidence",
    ]:
        normalized[column] = normalized[column].map(_safe_text)
    normalized["is_proxy"] = normalized["is_proxy"].map(bool).astype(object)
    normalized["as_of_safe"] = normalized["as_of_safe"].map(bool).astype(object)
    normalized["metadata_json"] = normalized["metadata_json"].map(_metadata_json)
    return normalized[EVIDENCE_COLUMNS]


def classify_text_evidence(
    *,
    text: str,
    source_type: str,
    source_id: str,
    source_title: str,
    source_date: str,
) -> list[dict[str, Any]]:
    safe_text = _safe_text(text)
    lowered = safe_text.lower()
    rows: list[dict[str, Any]] = []
    for evidence_type, keywords in TEXT_EVIDENCE_GROUPS:
        for keyword in keywords:
            if keyword.lower() in lowered:
                rows.append(
                    {
                        "evidence_date": _date_text(source_date),
                        "source_type": source_type,
                        "source_id": source_id,
                        "source_title": source_title,
                        "source_url": "",
                        "evidence_type": evidence_type,
                        "matched_keyword": keyword,
                        "evidence_snippet": _snippet(safe_text, keyword),
                        "source_confidence": "medium",
                        "is_proxy": evidence_type == "technical_barrier",
                        "as_of_safe": True,
                        "metadata_json": {},
                    }
                )
                break
    return rows
```

Add helper functions `_safe_text`, `_date_text`, `_date_timestamp`, `_metadata_json`, and `_snippet` using the same semantics as readiness.

- [ ] **Step 4: Run tests and commit**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_evidence_backfill.py -q
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/tech_bottleneck_evidence_backfill.py tests/test_tech_bottleneck_evidence_backfill.py
git commit -m "feat: add tech bottleneck evidence normalization"
```

## Task 2: Existing-DB Evidence Backfill Artifacts

**Files:**
- Modify: `src/stock_research/tech_bottleneck_evidence_backfill.py`
- Modify: `tests/test_tech_bottleneck_evidence_backfill.py`

- [ ] **Step 1: Write failing tests for DB-frame conversion and artifact writing**

Add tests that call `build_evidence_backfill` with fixture DataFrames:

```python
from pathlib import Path

from stock_research.tech_bottleneck_evidence_backfill import (
    build_evidence_backfill,
    write_evidence_artifacts,
)


def test_build_evidence_backfill_extracts_product_and_text_evidence() -> None:
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "示例科技",
                "trade_date": "2025-01-10",
                "candidate_source": "top50",
                "rank": 1,
            }
        ]
    )
    result = build_evidence_backfill(
        candidates=candidates,
        run_id="unit",
        run_date="2026-06-06",
        start_date=None,
        end_date=None,
        lookback_days=365,
        main_business=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_period": "2024-12-31",
                    "classify_type": "按产品分类",
                    "item_name": "AI关键材料",
                    "revenue": 100,
                    "revenue_ratio": 45,
                    "gross_margin": 35,
                }
            ]
        ),
        reports=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_id": "r1",
                    "report_date": "2025-01-05",
                    "report_title": "国产替代加速",
                    "raw_summary": "扩产爬坡，客户认证推进，技术壁垒高。",
                }
            ]
        ),
        events=pd.DataFrame(),
        news=pd.DataFrame(),
    )

    evidence_types = set(result.evidence["evidence_type"])
    assert "product_revenue_exposure" in evidence_types
    assert "bottleneck_keyword" in evidence_types
    assert "capacity" in evidence_types
    assert "customer_certification" in evidence_types
    assert "technical_barrier" in evidence_types
    assert bool(result.evidence[result.evidence["evidence_type"].eq("product_revenue_exposure")].iloc[0]["as_of_safe"])


def test_future_evidence_is_written_as_unsafe() -> None:
    result = build_evidence_backfill(
        candidates=pd.DataFrame([{"asset_id": "CN:SH:688001", "trade_date": "2025-01-10"}]),
        run_id="unit",
        run_date="2026-06-06",
        start_date=None,
        end_date=None,
        lookback_days=365,
        main_business=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_period": "2025-06-30",
                    "classify_type": "按产品分类",
                    "item_name": "未来产品",
                }
            ]
        ),
        reports=pd.DataFrame(),
        events=pd.DataFrame(),
        news=pd.DataFrame(),
    )

    assert len(result.evidence) == 1
    assert result.evidence.iloc[0]["as_of_safe"] is False


def test_write_evidence_artifacts(tmp_path: Path) -> None:
    result = build_evidence_backfill(
        candidates=pd.DataFrame([{"asset_id": "CN:SH:688001", "trade_date": "2025-01-10"}]),
        run_id="unit",
        run_date="2026-06-06",
        start_date=None,
        end_date=None,
        lookback_days=365,
        main_business=pd.DataFrame(),
        reports=pd.DataFrame(),
        events=pd.DataFrame(),
        news=pd.DataFrame(),
    )

    paths = write_evidence_artifacts(result=result, output_dir=tmp_path)
    assert paths["csv"].name == "evidence.csv"
    assert paths["json"].name == "evidence.json"
    assert paths["summary"].name == "coverage_summary.md"
    assert paths["source_gap_report"].name == "source_gap_report.csv"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_evidence_backfill.py -q
```

Expected: FAIL with missing `build_evidence_backfill` and `write_evidence_artifacts`.

- [ ] **Step 3: Implement `EvidenceBackfillResult`, context conversion, and artifact writing**

Add:

```python
class EvidenceBackfillResult:
    def __init__(self, *, candidates: pd.DataFrame, evidence: pd.DataFrame, source_gap_report: pd.DataFrame) -> None:
        self.candidates = candidates
        self.evidence = evidence
        self.source_gap_report = source_gap_report
```

Implement `build_evidence_backfill` to:

- Normalize candidates.
- Group `main_business`, `reports`, `events`, and `news` by `asset_id`.
- For each candidate, emit product rows from product-classified main business rows.
- Emit text rows from report title/summary, event summary, and news title/content.
- Compute `as_of_safe` per row with candidate `as_of_date` and lookback.
- Keep unsafe rows in artifacts.

Implement `write_evidence_artifacts`:

- `evidence.csv`: all normalized evidence rows.
- `evidence.json`: grouped by candidate key `asset_id|candidate_trade_date`.
- `coverage_summary.md`: counts by evidence type, source confidence, and `as_of_safe`.
- `source_gap_report.csv`: one row per candidate with missing evidence types after safe evidence filtering.

- [ ] **Step 4: Add DB loader and file runner**

Add `load_evidence_context_from_db` with queries aligned to `load_readiness_context_from_db`:

```sql
SELECT asset_id, report_period, classify_type, item_name, revenue, revenue_ratio, gross_margin
FROM finance.main_business_composition
WHERE asset_id = ANY(%s)
  AND report_period <= %s::date
```

Also load:

- `research.stock_report_event` joined to `research.stock_report_source`.
- `event.institution_survey`.
- `event.earnings_forecast`.
- `event.earnings_express`.
- `research.news_event_mention` joined to `research.news_event_source`.

Add `run_evidence_backfill_from_files`:

```python
def run_evidence_backfill_from_files(
    *,
    candidates_csv: Path,
    output_dir: Path,
    run_id: str,
    run_date: str,
    start_date: str | None,
    end_date: str | None,
    lookback_days: int,
    service: str,
    context_loader: Any | None = None,
) -> dict[str, Path]:
    candidates = pd.read_csv(candidates_csv)
    normalized = normalize_evidence_candidates(
        candidates,
        run_date=run_date,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
    )
    loader = context_loader or load_evidence_context_from_db
    context = loader(normalized, lookback_days=lookback_days, service=service)
    result = build_evidence_backfill(
        candidates=normalized,
        run_id=run_id,
        run_date=run_date,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
        **context,
    )
    return write_evidence_artifacts(result=result, output_dir=output_dir)
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_evidence_backfill.py -q
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/tech_bottleneck_evidence_backfill.py tests/test_tech_bottleneck_evidence_backfill.py
git commit -m "feat: write tech bottleneck evidence backfill artifacts"
```

## Task 3: Readiness Evidence CSV Integration

**Files:**
- Modify: `src/stock_research/tech_bottleneck_readiness.py`
- Modify: `tests/test_tech_bottleneck_readiness.py`

- [ ] **Step 1: Write failing tests for evidence CSV merging**

Add tests:

```python
def test_safe_strong_evidence_csv_sets_readiness_flags(tmp_path: Path) -> None:
    evidence_csv = tmp_path / "evidence.csv"
    pd.DataFrame(
        [
            {
                "run_id": "evidence-unit",
                "asset_id": "CN:SH:688099",
                "stock_name": "证据测试",
                "candidate_trade_date": "2026-06-05",
                "as_of_date": "2026-06-05",
                "evidence_date": "2026-05-20",
                "source_type": "fixture",
                "source_id": "fixture-product",
                "source_title": "主营构成",
                "source_url": "",
                "evidence_type": "product_revenue_exposure",
                "matched_keyword": "",
                "evidence_snippet": "AI关键材料收入占比45%",
                "source_confidence": "strong",
                "is_proxy": False,
                "as_of_safe": True,
                "metadata_json": "{}",
            },
            {
                "run_id": "evidence-unit",
                "asset_id": "CN:SH:688099",
                "stock_name": "证据测试",
                "candidate_trade_date": "2026-06-05",
                "as_of_date": "2026-06-05",
                "evidence_date": "2026-05-20",
                "source_type": "fixture",
                "source_id": "fixture-bottleneck",
                "source_title": "国产替代",
                "source_url": "",
                "evidence_type": "bottleneck_keyword",
                "matched_keyword": "国产替代",
                "evidence_snippet": "关键材料国产替代加速",
                "source_confidence": "medium",
                "is_proxy": False,
                "as_of_safe": True,
                "metadata_json": "{}",
            },
        ]
    ).to_csv(evidence_csv, index=False)

    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        evidence=pd.read_csv(evidence_csv),
        **_single_candidate_frames(report_title="经营跟踪", raw_summary="产品结构稳定。"),
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_product_revenue_exposure"] is True
    assert row["has_bottleneck_keywords"] is True
    assert audit.details[0]["flag_details"]["has_product_revenue_exposure"][0]["source_table"] == "evidence"


def test_proxy_or_unsafe_product_evidence_does_not_set_product_flag() -> None:
    base = {
        "run_id": "evidence-unit",
        "asset_id": "CN:SH:688099",
        "stock_name": "证据测试",
        "candidate_trade_date": "2026-06-05",
        "as_of_date": "2026-06-05",
        "evidence_date": "2026-05-20",
        "source_type": "fixture",
        "source_id": "fixture-product",
        "source_title": "产品描述",
        "source_url": "",
        "evidence_type": "product_revenue_exposure",
        "matched_keyword": "",
        "evidence_snippet": "产品描述但不是强主营构成",
        "source_confidence": "medium",
        "is_proxy": True,
        "as_of_safe": True,
        "metadata_json": "{}",
    }
    audit = build_readiness_audit(
        candidates=_single_candidate(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        evidence=pd.DataFrame([base, {**base, "source_confidence": "strong", "is_proxy": False, "as_of_safe": False}]),
        **_single_candidate_frames(report_title="经营跟踪", raw_summary="产品结构稳定。"),
    )

    row = audit.summary.set_index("asset_id").loc["CN:SH:688099"]
    assert row["has_product_revenue_exposure"] is False
```

- [ ] **Step 2: Run readiness tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: FAIL with unexpected keyword argument `evidence`.

- [ ] **Step 3: Extend `build_readiness_audit` to accept evidence rows**

Add `evidence: pd.DataFrame | None = None` to `build_readiness_audit`.

Inside the function:

- Add evidence to `lookups` as `_rows_by_asset(evidence)`.
- Filter with candidate `as_of_date`, `lookback_days`, `date_fields=["evidence_date"]`, and `require_date=True`.
- Keep only rows where `_bool_value(row.get("as_of_safe"))` is true.
- Map evidence rows to readiness flags.
- Append evidence samples to `flag_details`.
- Preserve proxy flags for `patent_proxy`, `technical_barrier`, and proxy text rows.

Add helpers:

```python
def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _safe_text(value).lower() in {"true", "1", "yes", "y"}
```

```python
def _evidence_flag_details(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_table": "evidence",
            "source_date": _date_text(row.get("evidence_date")),
            "summary": _safe_text(row.get("evidence_snippet") or row.get("source_title")),
            "source_id": _safe_text(row.get("source_id")),
            "evidence_type": _safe_text(row.get("evidence_type")),
            "matched_keyword": _safe_text(row.get("matched_keyword")),
        }
        for row in rows[:3]
    ]
```

- [ ] **Step 4: Extend runner to load optional evidence CSV**

Modify `run_readiness_audit_from_files` signature:

```python
evidence_csv: Path | None = None
```

Load:

```python
evidence = pd.read_csv(evidence_csv) if evidence_csv else pd.DataFrame()
```

Pass `evidence=evidence` into `build_readiness_audit`.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/tech_bottleneck_readiness.py tests/test_tech_bottleneck_readiness.py
git commit -m "feat: merge tech bottleneck evidence into readiness audit"
```

## Task 4: CLI, Example Fixture, and Runbook

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `docs/tech-bottleneck-discovery-runbook.md`
- Create: `data/manual/tech_bottleneck_evidence_backfill_candidates_example.csv`
- Modify: `tests/test_tech_bottleneck_evidence_backfill.py`

- [ ] **Step 1: Add CLI import and parser tests by help smoke**

No unit test harness exists for `cli.py`; use CLI help smoke in Step 5. Add import:

```python
from stock_research.tech_bottleneck_evidence_backfill import run_evidence_backfill_from_files
```

Register parser near existing tech-bottleneck commands:

```python
tech_bottleneck_evidence = subparsers.add_parser(
    "tech-bottleneck-evidence-backfill",
    help="Backfill candidate-scoped tech bottleneck evidence artifacts",
)
tech_bottleneck_evidence.add_argument("--candidates-csv", required=True)
tech_bottleneck_evidence.add_argument("--output-dir", required=True)
tech_bottleneck_evidence.add_argument("--run-id", required=True)
tech_bottleneck_evidence.add_argument("--start-date")
tech_bottleneck_evidence.add_argument("--end-date")
tech_bottleneck_evidence.add_argument("--lookback-days", type=int, default=365)
tech_bottleneck_evidence.add_argument("--service", default="stock_research")
```

Add `--evidence-csv` to `tech-bottleneck-data-readiness-audit`.

- [ ] **Step 2: Add CLI dispatch**

Near existing command dispatch:

```python
elif args.command == "tech-bottleneck-evidence-backfill":
    paths = run_evidence_backfill_from_files(
        candidates_csv=Path(args.candidates_csv),
        output_dir=Path(args.output_dir),
        run_id=args.run_id,
        run_date=date.today().isoformat(),
        start_date=args.start_date,
        end_date=args.end_date,
        lookback_days=args.lookback_days,
        service=args.service,
    )
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
```

Modify readiness dispatch to pass:

```python
evidence_csv=Path(args.evidence_csv) if args.evidence_csv else None
```

- [ ] **Step 3: Add example candidate CSV**

Create `data/manual/tech_bottleneck_evidence_backfill_candidates_example.csv`:

```csv
asset_id,stock_name,trade_date,candidate_source,rank
CN:SH:688001,示例科技,2025-01-10,manual_example,1
CN:SZ:300001,示例材料,2025-01-10,manual_example,2
```

- [ ] **Step 4: Update runbook**

Add a section before Data Readiness Audit:

````markdown
## Evidence Backfill

Run this when readiness shows data gaps. It builds candidate-scoped evidence artifacts without changing the candidate pool.

```bash
stock-research tech-bottleneck-evidence-backfill \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/evidence \
  --run-id pilot-top50-2025-evidence \
  --start-date 2025-01-01 \
  --lookback-days 365 \
  --service stock_research
```

Then rerun readiness with:

```bash
stock-research tech-bottleneck-data-readiness-audit \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --evidence-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/evidence/evidence.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness_after_backfill \
  --run-id pilot-top50-2025-readiness-after-backfill \
  --lookback-days 365 \
  --service stock_research
```
````

- [ ] **Step 5: Run verification and commit**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli tech-bottleneck-evidence-backfill --help
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli tech-bottleneck-data-readiness-audit --help
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_evidence_backfill.py tests/test_tech_bottleneck_readiness.py -q
```

Expected:

- Both help commands exit 0.
- Pytest passes.

Commit:

```bash
git add src/stock_research/cli.py docs/tech-bottleneck-discovery-runbook.md data/manual/tech_bottleneck_evidence_backfill_candidates_example.csv tests/test_tech_bottleneck_evidence_backfill.py
git commit -m "feat: add tech bottleneck evidence backfill cli"
```

## Task 5: Pilot Smoke Against Current Top50 Pool

**Files:**
- No source changes expected.
- Generated outputs under `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/`.

- [ ] **Step 1: Run evidence backfill on the current pilot pool**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli tech-bottleneck-evidence-backfill \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/evidence_existing_db \
  --run-id pilot-top50-2025-evidence-existing-db \
  --start-date 2025-01-01 \
  --lookback-days 365 \
  --service stock_research
```

Expected: command exits 0 and writes `evidence.csv`, `evidence.json`, `coverage_summary.md`, `source_gap_report.csv`.

- [ ] **Step 2: Rerun readiness with evidence CSV**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli tech-bottleneck-data-readiness-audit \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --evidence-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/evidence_existing_db/evidence.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness_after_existing_db_backfill \
  --run-id pilot-top50-2025-readiness-after-existing-db-backfill \
  --lookback-days 365 \
  --service stock_research
```

Expected: command exits 0 and writes readiness artifacts.

- [ ] **Step 3: Compare before/after coverage**

Run:

```bash
python - <<'PY'
import pandas as pd

before = pd.read_csv("outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness/readiness.csv")
after = pd.read_csv("outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness_after_existing_db_backfill/readiness.csv")
flags = [
    "has_product_revenue_exposure",
    "has_bottleneck_keywords",
    "has_capacity_evidence",
    "has_customer_certification_evidence",
    "has_patent_or_technical_barrier",
    "has_invalidation_evidence",
]
for flag in flags:
    print(f"{flag}: before={before[flag].map(bool).mean():.1%} after={after[flag].map(bool).mean():.1%}")
print("status before")
print(before["coverage_status"].value_counts())
print("status after")
print(after["coverage_status"].value_counts())
PY
```

Expected: output shows whether existing DB backfill improves proxy evidence. It may still leave product exposure low; that is an actionable source gap, not a failed implementation.

- [ ] **Step 4: Run final verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_evidence_backfill.py tests/test_tech_bottleneck_readiness.py tests/test_tech_bottleneck_discovery.py tests/test_tech_bottleneck_experiment.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit only source/docs/tests, not generated pilot outputs**

If source/doc/test files changed during smoke fixes:

```bash
git status --short
git add <source-doc-test-files-only>
git commit -m "fix: stabilize tech bottleneck evidence backfill smoke"
```

Do not commit generated `outputs/` artifacts unless the repository already tracks that exact output path.

## Self-Review Checklist

- Every implementation task has a test-first step.
- The first version is candidate-scoped and file-based.
- `as_of_safe = false` rows are preserved in evidence artifacts but ignored by readiness flags.
- Strong product evidence is required for `has_product_revenue_exposure`.
- Proxy evidence can improve bottleneck/capacity/customer/barrier flags but cannot hide missing product exposure.
- CLI and runbook show the actual workflow from evidence backfill to readiness rerun.
