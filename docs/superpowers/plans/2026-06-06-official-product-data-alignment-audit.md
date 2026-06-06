# Official Product Data Alignment Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an artifact-based audit that explains, for every `tech-bottleneck-discovery` candidate row, why official product revenue evidence is or is not point-in-time usable.

**Architecture:** Add a focused alignment module that reads existing candidate and official product backfill artifacts, classifies each candidate row with one deterministic alignment status, and writes CSV/JSON/Markdown outputs. Keep the audit read-only: it must not fetch disclosures, create product evidence, score stocks, run returns, or weaken the strict PIT contract.

**Tech Stack:** Python 3, pandas, existing `stock_research` CLI, existing official disclosure product backfill artifacts, pytest.

---

## File Structure

- Create `src/stock_research/official_product_data_alignment_audit.py`
  - Owns candidate normalization, artifact normalization, per-candidate alignment classification, status summaries, artifact writing, and file runner.
- Modify `src/stock_research/cli.py`
  - Imports the new runner.
  - Adds `tech-bottleneck-official-product-data-alignment-audit`.
  - Dispatches the command without opening a DB connection.
- Create `tests/test_official_product_data_alignment_audit.py`
  - Unit tests for normalization, safe/unsafe evidence classification, manifest/product fallback classification, summary rows, artifact writing, and CLI dispatch.
- Modify `docs/tech-bottleneck-discovery-runbook.md`
  - Adds the alignment audit step after official product backfill and before readiness/return testing.

---

### Task 1: Candidate Normalization And Candidate-Scoped Evidence Statuses

**Files:**
- Create: `src/stock_research/official_product_data_alignment_audit.py`
- Create: `tests/test_official_product_data_alignment_audit.py`

- [ ] **Step 1: Write failing tests for candidate normalization and candidate-scoped evidence statuses**

Add this content to `tests/test_official_product_data_alignment_audit.py`:

```python
import json
from pathlib import Path

import pandas as pd

from stock_research.official_product_data_alignment_audit import (
    ALIGNMENT_AUDIT_COLUMNS,
    normalize_alignment_candidates,
    build_alignment_audit,
)


def test_normalize_alignment_candidates_accepts_real_pilot_shape():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "stock_name": "平安银行",
                "trade_date": "2025-01-03",
                "candidate_source": "pilot_top50",
                "rank": "1",
            }
        ]
    )

    normalized = normalize_alignment_candidates(candidates)

    assert normalized.to_dict("records") == [
        {
            "asset_id": "CN:SZ:000001",
            "ts_code": "000001.SZ",
            "stock_name": "平安银行",
            "candidate_trade_date": pd.Timestamp("2025-01-03").date(),
            "as_of_date": pd.Timestamp("2025-01-03").date(),
        }
    ]


def test_safe_product_evidence_produces_pit_safe_status():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "candidate_trade_date": "2025-05-09",
                "as_of_date": "2025-05-09",
            }
        ]
    )
    product_evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "candidate_trade_date": "2025-05-09",
                "as_of_date": "2025-05-09",
                "evidence_date": "2025-04-25",
                "source_title": "2024年年度报告",
                "source_id": "121999",
                "source_url": "http://example.com/report.pdf",
                "as_of_safe": True,
                "metadata_json": json.dumps(
                    {
                        "report_period": "2024-12-31",
                        "publish_date": "2025-04-25",
                        "source_document_id": "121999",
                        "source_document_url": "http://example.com/report.pdf",
                        "item_name": "先进封装设备",
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=product_evidence,
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=pd.DataFrame(),
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert audit.columns.tolist() == ALIGNMENT_AUDIT_COLUMNS
    assert row["alignment_status"] == "pit_safe_product_evidence_available"
    assert row["alignment_reason"] == "candidate row has strict PIT-safe official product evidence"
    assert row["has_pit_safe_product_evidence"] is True
    assert row["safe_product_evidence_count"] == 1
    assert row["unsafe_product_evidence_count"] == 0
    assert row["best_report_period"] == pd.Timestamp("2024-12-31").date()
    assert row["best_publish_date"] == pd.Timestamp("2025-04-25").date()
    assert row["best_source_document_id"] == "121999"
    assert row["best_source_document_url"] == "http://example.com/report.pdf"
    assert row["recommended_action"] == "use_for_readiness"


def test_future_disclosure_evidence_remains_blocked():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "candidate_trade_date": "2025-04-18",
                "as_of_date": "2025-04-18",
            }
        ]
    )
    product_evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "candidate_trade_date": "2025-04-18",
                "as_of_date": "2025-04-18",
                "evidence_date": "2025-04-25",
                "source_title": "2024年年度报告",
                "source_id": "121999",
                "source_url": "http://example.com/report.pdf",
                "as_of_safe": False,
                "metadata_json": json.dumps(
                    {
                        "report_period": "2024-12-31",
                        "publish_date": "2025-04-25",
                        "source_document_id": "121999",
                        "source_document_url": "http://example.com/report.pdf",
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=product_evidence,
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=pd.DataFrame(),
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "joinable_but_future_disclosure"
    assert row["alignment_reason"] == "official product evidence exists but publish_date is after candidate as_of_date"
    assert row["has_pit_safe_product_evidence"] is False
    assert row["safe_product_evidence_count"] == 0
    assert row["unsafe_product_evidence_count"] == 1
    assert row["best_report_period"] == pd.Timestamp("2024-12-31").date()
    assert row["best_publish_date"] == pd.Timestamp("2025-04-25").date()
    assert row["min_future_publish_date"] == pd.Timestamp("2025-04-25").date()
    assert row["days_until_first_future_disclosure"] == 7
    assert row["recommended_action"] == "shift_test_window_later"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_product_data_alignment_audit.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_research.official_product_data_alignment_audit'`.

- [ ] **Step 3: Implement the initial module with normalization and evidence classification**

Create `src/stock_research/official_product_data_alignment_audit.py`:

```python
"""Official product evidence alignment audit for tech bottleneck discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

ALIGNMENT_AUDIT_COLUMNS = [
    "run_id",
    "asset_id",
    "ts_code",
    "stock_name",
    "candidate_trade_date",
    "as_of_date",
    "alignment_status",
    "alignment_reason",
    "has_pit_safe_product_evidence",
    "safe_product_evidence_count",
    "unsafe_product_evidence_count",
    "best_report_period",
    "best_publish_date",
    "best_disclosure_type",
    "best_source_document_id",
    "best_source_document_url",
    "best_source_title",
    "best_product_main_business_rows",
    "best_manifest_rows",
    "manifest_rows_for_asset",
    "product_main_business_rows_for_asset",
    "joinable_report_periods_for_asset",
    "manifest_query_error_count_for_asset",
    "max_safe_report_period",
    "min_future_publish_date",
    "days_until_first_future_disclosure",
    "recommended_action",
]

ALIGNMENT_STATUS_SUMMARY_COLUMNS = [
    "run_id",
    "group",
    "group_value",
    "candidate_rows",
    "candidate_assets",
    "pit_safe_rows",
    "future_disclosure_rows",
    "missing_product_period_rows",
    "manifest_query_error_rows",
]

RECOMMENDED_ACTION_BY_STATUS = {
    "pit_safe_product_evidence_available": "use_for_readiness",
    "joinable_but_future_disclosure": "shift_test_window_later",
    "joinable_but_report_period_future": "ignore_future_period",
    "manifest_available_no_joinable_product_period": "backfill_historical_product_rows",
    "manifest_available_no_product_rows": "backfill_product_table_source",
    "product_rows_available_no_official_manifest": "extend_or_fix_manifest_source",
    "no_official_manifest_or_product_rows": "investigate_source_coverage",
    "manifest_query_error": "rerun_manifest_source",
}


@dataclass(frozen=True)
class OfficialProductDataAlignmentAuditResult:
    output_dir: Path
    candidate_rows: int
    candidate_assets: int
    pit_safe_rows: int
    future_disclosure_rows: int
    manifest_query_error_rows: int


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _date_value(value: Any):
    if value is None:
        return pd.NaT
    try:
        if pd.isna(value):
            return pd.NaT
    except (TypeError, ValueError):
        pass
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    return parsed.date()


def _derive_ts_code(asset_id: Any) -> str:
    text = _safe_text(asset_id)
    parts = text.split(":")
    if len(parts) == 3 and parts[0] == "CN" and parts[1] in {"SZ", "SH"}:
        return f"{parts[2]}.{parts[1]}"
    return ""


def normalize_alignment_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.copy()
    for column in ["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date", "trade_date"]:
        if column not in frame.columns:
            frame[column] = ""
    if frame.empty:
        return pd.DataFrame(columns=["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date"])

    frame["asset_id"] = frame["asset_id"].map(_safe_text)
    frame["ts_code"] = frame["ts_code"].map(_safe_text)
    missing_ts_code = frame["ts_code"].eq("")
    frame.loc[missing_ts_code, "ts_code"] = frame.loc[missing_ts_code, "asset_id"].map(_derive_ts_code)
    frame["stock_name"] = frame["stock_name"].map(_safe_text)
    frame["candidate_trade_date"] = frame["candidate_trade_date"].where(
        frame["candidate_trade_date"].astype(str).str.strip().ne(""),
        frame["trade_date"],
    )
    frame["as_of_date"] = frame["as_of_date"].where(
        frame["as_of_date"].astype(str).str.strip().ne(""),
        frame["candidate_trade_date"],
    )
    frame["candidate_trade_date"] = frame["candidate_trade_date"].map(_date_value)
    frame["as_of_date"] = frame["as_of_date"].map(_date_value)
    frame = frame[
        frame["asset_id"].ne("")
        & frame["ts_code"].ne("")
        & frame["candidate_trade_date"].notna()
        & frame["as_of_date"].notna()
    ].copy()
    return frame[["asset_id", "ts_code", "stock_name", "candidate_trade_date", "as_of_date"]].reset_index(drop=True)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _safe_text(value).lower()
    return text in {"true", "1", "yes", "y"}


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = _safe_text(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_product_evidence(product_evidence: pd.DataFrame) -> pd.DataFrame:
    frame = product_evidence.copy()
    for column in [
        "asset_id",
        "candidate_trade_date",
        "as_of_date",
        "evidence_date",
        "source_title",
        "source_id",
        "source_url",
        "as_of_safe",
        "metadata_json",
    ]:
        if column not in frame.columns:
            frame[column] = ""
    if frame.empty:
        return frame
    frame["asset_id"] = frame["asset_id"].map(_safe_text)
    frame["candidate_trade_date"] = frame["candidate_trade_date"].map(_date_value)
    frame["as_of_date"] = frame["as_of_date"].map(_date_value)
    frame["evidence_date"] = frame["evidence_date"].map(_date_value)
    frame["source_title"] = frame["source_title"].map(_safe_text)
    frame["source_id"] = frame["source_id"].map(_safe_text)
    frame["source_url"] = frame["source_url"].map(_safe_text)
    frame["as_of_safe"] = frame["as_of_safe"].map(_bool_value)
    frame["metadata"] = frame["metadata_json"].map(_metadata)
    frame["report_period"] = frame["metadata"].map(lambda item: _date_value(item.get("report_period")))
    frame["publish_date"] = frame["metadata"].map(lambda item: _date_value(item.get("publish_date")))
    frame["publish_date"] = frame["publish_date"].where(frame["publish_date"].notna(), frame["evidence_date"])
    frame["source_document_id"] = frame["metadata"].map(lambda item: _safe_text(item.get("source_document_id")))
    frame["source_document_url"] = frame["metadata"].map(lambda item: _safe_text(item.get("source_document_url")))
    frame["source_document_id"] = frame["source_document_id"].where(frame["source_document_id"].ne(""), frame["source_id"])
    frame["source_document_url"] = frame["source_document_url"].where(frame["source_document_url"].ne(""), frame["source_url"])
    return frame


def _empty_audit_row(run_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": _safe_text(run_id),
        "asset_id": candidate["asset_id"],
        "ts_code": candidate["ts_code"],
        "stock_name": candidate.get("stock_name", ""),
        "candidate_trade_date": candidate["candidate_trade_date"],
        "as_of_date": candidate["as_of_date"],
        "alignment_status": "",
        "alignment_reason": "",
        "has_pit_safe_product_evidence": False,
        "safe_product_evidence_count": 0,
        "unsafe_product_evidence_count": 0,
        "best_report_period": pd.NaT,
        "best_publish_date": pd.NaT,
        "best_disclosure_type": "",
        "best_source_document_id": "",
        "best_source_document_url": "",
        "best_source_title": "",
        "best_product_main_business_rows": 0,
        "best_manifest_rows": 0,
        "manifest_rows_for_asset": 0,
        "product_main_business_rows_for_asset": 0,
        "joinable_report_periods_for_asset": 0,
        "manifest_query_error_count_for_asset": 0,
        "max_safe_report_period": pd.NaT,
        "min_future_publish_date": pd.NaT,
        "days_until_first_future_disclosure": "",
        "recommended_action": "",
    }


def _finalize_row(row: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    row["alignment_status"] = status
    row["alignment_reason"] = reason
    row["recommended_action"] = RECOMMENDED_ACTION_BY_STATUS[status]
    return row


def _candidate_evidence_rows(evidence: pd.DataFrame, candidate: dict[str, Any]) -> pd.DataFrame:
    if evidence.empty:
        return evidence
    return evidence[
        evidence["asset_id"].eq(candidate["asset_id"])
        & evidence["candidate_trade_date"].eq(candidate["candidate_trade_date"])
        & evidence["as_of_date"].eq(candidate["as_of_date"])
    ].copy()


def _apply_evidence_details(row: dict[str, Any], evidence_rows: pd.DataFrame) -> None:
    safe_rows = evidence_rows[evidence_rows["as_of_safe"].eq(True)]
    unsafe_rows = evidence_rows[evidence_rows["as_of_safe"].eq(False)]
    row["safe_product_evidence_count"] = int(len(safe_rows))
    row["unsafe_product_evidence_count"] = int(len(unsafe_rows))
    row["has_pit_safe_product_evidence"] = bool(len(safe_rows) > 0)
    best = safe_rows.iloc[0] if not safe_rows.empty else unsafe_rows.sort_values("publish_date", kind="stable").iloc[0]
    row["best_report_period"] = best.get("report_period", pd.NaT)
    row["best_publish_date"] = best.get("publish_date", pd.NaT)
    row["best_source_document_id"] = best.get("source_document_id", "")
    row["best_source_document_url"] = best.get("source_document_url", "")
    row["best_source_title"] = best.get("source_title", "")
    future_publish = evidence_rows[evidence_rows["publish_date"] > row["as_of_date"]]
    if not future_publish.empty:
        first_publish = future_publish["publish_date"].min()
        row["min_future_publish_date"] = first_publish
        row["days_until_first_future_disclosure"] = int((first_publish - row["as_of_date"]).days)
    safe_periods = evidence_rows[
        evidence_rows["publish_date"].le(row["as_of_date"]) & evidence_rows["report_period"].le(row["as_of_date"])
    ]["report_period"].dropna()
    if not safe_periods.empty:
        row["max_safe_report_period"] = safe_periods.max()


def build_alignment_audit(
    *,
    candidates: pd.DataFrame,
    product_evidence: pd.DataFrame,
    disclosure_manifest: pd.DataFrame,
    product_join_diagnostics: pd.DataFrame,
    manifest_query_errors: pd.DataFrame,
    run_id: str,
) -> pd.DataFrame:
    normalized_candidates = normalize_alignment_candidates(candidates)
    evidence = _normalize_product_evidence(product_evidence)
    rows = []
    for candidate in normalized_candidates.to_dict("records"):
        row = _empty_audit_row(run_id, candidate)
        candidate_evidence = _candidate_evidence_rows(evidence, candidate)
        if not candidate_evidence.empty:
            _apply_evidence_details(row, candidate_evidence)
            if row["has_pit_safe_product_evidence"]:
                rows.append(
                    _finalize_row(
                        row,
                        "pit_safe_product_evidence_available",
                        "candidate row has strict PIT-safe official product evidence",
                    )
                )
            else:
                rows.append(
                    _finalize_row(
                        row,
                        "joinable_but_future_disclosure",
                        "official product evidence exists but publish_date is after candidate as_of_date",
                    )
                )
            continue
        rows.append(
            _finalize_row(
                row,
                "no_official_manifest_or_product_rows",
                "no official manifest or product rows are available for the asset in current artifacts",
            )
        )
    return pd.DataFrame(rows, columns=ALIGNMENT_AUDIT_COLUMNS)
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_product_data_alignment_audit.py -q
```

Expected: PASS for the three tests in this task.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/official_product_data_alignment_audit.py tests/test_official_product_data_alignment_audit.py
git commit -m "feat: add official product alignment evidence statuses"
```

---

### Task 2: Manifest/Product Coverage Fallback Statuses

**Files:**
- Modify: `src/stock_research/official_product_data_alignment_audit.py`
- Modify: `tests/test_official_product_data_alignment_audit.py`

- [ ] **Step 1: Add failing tests for join diagnostics and source fallback statuses**

Append these tests to `tests/test_official_product_data_alignment_audit.py`:

```python
def test_joinable_future_report_period_is_separated_from_future_disclosure():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "candidate_trade_date": "2025-05-09",
                "as_of_date": "2025-05-09",
            }
        ]
    )
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2025-06-30",
                "publish_date": "2025-08-28",
                "disclosure_type": "semiannual",
                "source_document_id": "122500",
                "source_document_url": "http://example.com/2025h1.pdf",
                "announcement_title": "2025年半年度报告",
                "product_main_business_rows": 5,
                "manifest_rows": 1,
                "join_status": "joinable",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "joinable_but_report_period_future"
    assert row["alignment_reason"] == "joinable official product period is after candidate as_of_date"
    assert row["best_report_period"] == pd.Timestamp("2025-06-30").date()
    assert row["best_publish_date"] == pd.Timestamp("2025-08-28").date()
    assert row["best_product_main_business_rows"] == 5
    assert row["best_manifest_rows"] == 1
    assert row["joinable_report_periods_for_asset"] == 1
    assert row["recommended_action"] == "ignore_future_period"


def test_manifest_and_product_rows_without_matching_period_recommends_historical_backfill():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "trade_date": "2025-05-09",
            }
        ]
    )
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "publish_date": "2025-04-25",
                "disclosure_type": "annual",
                "source_document_id": "121999",
                "source_document_url": "http://example.com/report.pdf",
                "announcement_title": "2024年年度报告",
                "product_main_business_rows": 0,
                "manifest_rows": 1,
                "join_status": "missing_product_rows",
            },
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "",
                "publish_date": "",
                "disclosure_type": "",
                "source_document_id": "",
                "source_document_url": "",
                "announcement_title": "",
                "product_main_business_rows": 4,
                "manifest_rows": 0,
                "join_status": "product_rows_without_manifest",
            },
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "manifest_available_no_joinable_product_period"
    assert row["manifest_rows_for_asset"] == 1
    assert row["product_main_business_rows_for_asset"] == 4
    assert row["recommended_action"] == "backfill_historical_product_rows"


def test_manifest_without_product_rows_recommends_product_table_backfill():
    candidates = pd.DataFrame([{"asset_id": "CN:SZ:000001", "ts_code": "000001.SZ", "trade_date": "2025-05-09"}])
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "publish_date": "2025-04-25",
                "disclosure_type": "annual",
                "source_document_id": "121999",
                "source_document_url": "http://example.com/report.pdf",
                "announcement_title": "2024年年度报告",
                "product_main_business_rows": 0,
                "manifest_rows": 1,
                "join_status": "missing_product_rows",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "manifest_available_no_product_rows"
    assert row["recommended_action"] == "backfill_product_table_source"


def test_product_rows_without_manifest_recommends_manifest_source_fix():
    candidates = pd.DataFrame([{"asset_id": "CN:SZ:000001", "ts_code": "000001.SZ", "trade_date": "2025-05-09"}])
    diagnostics = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "publish_date": "",
                "disclosure_type": "",
                "source_document_id": "",
                "source_document_url": "",
                "announcement_title": "",
                "product_main_business_rows": 3,
                "manifest_rows": 0,
                "join_status": "product_rows_without_manifest",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=diagnostics,
        manifest_query_errors=pd.DataFrame(),
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "product_rows_available_no_official_manifest"
    assert row["recommended_action"] == "extend_or_fix_manifest_source"


def test_manifest_query_error_is_not_treated_as_genuine_no_data():
    candidates = pd.DataFrame([{"asset_id": "CN:SZ:000001", "ts_code": "000001.SZ", "trade_date": "2025-05-09"}])
    errors = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "error_type": "TimeoutError",
                "error_message": "timed out",
            }
        ]
    )

    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=pd.DataFrame(),
        disclosure_manifest=pd.DataFrame(),
        product_join_diagnostics=pd.DataFrame(),
        manifest_query_errors=errors,
        run_id="unit",
    )

    row = audit.iloc[0].to_dict()
    assert row["alignment_status"] == "manifest_query_error"
    assert row["manifest_query_error_count_for_asset"] == 1
    assert row["recommended_action"] == "rerun_manifest_source"
```

- [ ] **Step 2: Run the expanded tests and verify fallback tests fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_product_data_alignment_audit.py -q
```

Expected: the Task 1 tests pass, and the new fallback-status tests fail because join diagnostics and source errors are not yet classified.

- [ ] **Step 3: Add artifact normalization and fallback classifiers**

Modify `src/stock_research/official_product_data_alignment_audit.py` by adding these functions below `_normalize_product_evidence`:

```python
def _normalize_join_diagnostics(product_join_diagnostics: pd.DataFrame) -> pd.DataFrame:
    frame = product_join_diagnostics.copy()
    for column in [
        "asset_id",
        "ts_code",
        "report_period",
        "publish_date",
        "disclosure_type",
        "source_document_id",
        "source_document_url",
        "announcement_title",
        "product_main_business_rows",
        "manifest_rows",
        "join_status",
    ]:
        if column not in frame.columns:
            frame[column] = ""
    if frame.empty:
        return frame
    frame["asset_id"] = frame["asset_id"].map(_safe_text)
    frame["ts_code"] = frame["ts_code"].map(_safe_text)
    frame["report_period"] = frame["report_period"].map(_date_value)
    frame["publish_date"] = frame["publish_date"].map(_date_value)
    frame["disclosure_type"] = frame["disclosure_type"].map(_safe_text)
    frame["source_document_id"] = frame["source_document_id"].map(_safe_text)
    frame["source_document_url"] = frame["source_document_url"].map(_safe_text)
    frame["announcement_title"] = frame["announcement_title"].map(_safe_text)
    frame["product_main_business_rows"] = pd.to_numeric(frame["product_main_business_rows"], errors="coerce").fillna(0).astype(int)
    frame["manifest_rows"] = pd.to_numeric(frame["manifest_rows"], errors="coerce").fillna(0).astype(int)
    frame["join_status"] = frame["join_status"].map(_safe_text)
    return frame


def _normalize_manifest_query_errors(manifest_query_errors: pd.DataFrame) -> pd.DataFrame:
    frame = manifest_query_errors.copy()
    for column in ["asset_id", "ts_code", "error_type", "error_message"]:
        if column not in frame.columns:
            frame[column] = ""
    if frame.empty:
        return frame
    frame["asset_id"] = frame["asset_id"].map(_safe_text)
    frame["ts_code"] = frame["ts_code"].map(_safe_text)
    frame["error_type"] = frame["error_type"].map(_safe_text)
    frame["error_message"] = frame["error_message"].map(_safe_text)
    return frame


def _asset_rows(frame: pd.DataFrame, candidate: dict[str, Any]) -> pd.DataFrame:
    if frame.empty or "asset_id" not in frame.columns:
        return frame
    return frame[frame["asset_id"].eq(candidate["asset_id"])].copy()


def _apply_asset_counts(row: dict[str, Any], diagnostics: pd.DataFrame, errors: pd.DataFrame) -> None:
    row["manifest_query_error_count_for_asset"] = int(len(errors))
    if diagnostics.empty:
        return
    row["manifest_rows_for_asset"] = int(diagnostics["manifest_rows"].sum())
    row["product_main_business_rows_for_asset"] = int(diagnostics["product_main_business_rows"].sum())
    row["joinable_report_periods_for_asset"] = int(diagnostics["join_status"].eq("joinable").sum())


def _apply_diagnostic_details(row: dict[str, Any], diagnostic_row: pd.Series) -> None:
    row["best_report_period"] = diagnostic_row.get("report_period", pd.NaT)
    row["best_publish_date"] = diagnostic_row.get("publish_date", pd.NaT)
    row["best_disclosure_type"] = diagnostic_row.get("disclosure_type", "")
    row["best_source_document_id"] = diagnostic_row.get("source_document_id", "")
    row["best_source_document_url"] = diagnostic_row.get("source_document_url", "")
    row["best_source_title"] = diagnostic_row.get("announcement_title", "")
    row["best_product_main_business_rows"] = int(diagnostic_row.get("product_main_business_rows", 0) or 0)
    row["best_manifest_rows"] = int(diagnostic_row.get("manifest_rows", 0) or 0)


def _classify_from_join_diagnostics(row: dict[str, Any], diagnostics: pd.DataFrame) -> tuple[str, str] | None:
    if diagnostics.empty:
        return None
    joinable = diagnostics[diagnostics["join_status"].eq("joinable")].copy()
    if not joinable.empty:
        joinable = joinable.sort_values(["report_period", "publish_date"], ascending=[False, True], kind="stable")
        safe_period = joinable[joinable["report_period"].le(row["as_of_date"])]
        if not safe_period.empty:
            first_future_publish = safe_period[safe_period["publish_date"] > row["as_of_date"]].sort_values(
                "publish_date",
                kind="stable",
            )
            if not first_future_publish.empty:
                selected = first_future_publish.iloc[0]
                _apply_diagnostic_details(row, selected)
                row["min_future_publish_date"] = selected["publish_date"]
                row["days_until_first_future_disclosure"] = int((selected["publish_date"] - row["as_of_date"]).days)
                return (
                    "joinable_but_future_disclosure",
                    "official manifest and product rows join, but publish_date is after candidate as_of_date",
                )
            selected = safe_period.iloc[0]
            _apply_diagnostic_details(row, selected)
            row["max_safe_report_period"] = selected["report_period"]
            return (
                "manifest_available_no_joinable_product_period",
                "join diagnostics contain a safe historical period but no candidate-scoped evidence row exists",
            )
        future_period = joinable.sort_values("report_period", kind="stable").iloc[0]
        _apply_diagnostic_details(row, future_period)
        return ("joinable_but_report_period_future", "joinable official product period is after candidate as_of_date")

    has_manifest = bool((diagnostics["manifest_rows"] > 0).any())
    has_product = bool((diagnostics["product_main_business_rows"] > 0).any())
    if has_manifest and has_product:
        selected = diagnostics.sort_values(["report_period", "publish_date"], ascending=[False, False], kind="stable").iloc[0]
        _apply_diagnostic_details(row, selected)
        return (
            "manifest_available_no_joinable_product_period",
            "official manifest and product rows exist but no matching report period joins",
        )
    if has_manifest:
        selected = diagnostics[diagnostics["manifest_rows"] > 0].sort_values(
            ["report_period", "publish_date"],
            ascending=[False, False],
            kind="stable",
        ).iloc[0]
        _apply_diagnostic_details(row, selected)
        return (
            "manifest_available_no_product_rows",
            "official manifest exists but no product-classified main business rows exist for the asset",
        )
    if has_product:
        selected = diagnostics[diagnostics["product_main_business_rows"] > 0].sort_values(
            "report_period",
            ascending=False,
            kind="stable",
        ).iloc[0]
        _apply_diagnostic_details(row, selected)
        return (
            "product_rows_available_no_official_manifest",
            "product rows exist but no supported official disclosure manifest exists for the asset",
        )
    return None
```

Then modify `build_alignment_audit()` so it normalizes diagnostics and errors before the loop:

```python
    diagnostics = _normalize_join_diagnostics(product_join_diagnostics)
    errors = _normalize_manifest_query_errors(manifest_query_errors)
```

Inside the candidate loop, after the no-evidence branch begins and before appending the no-data status, add:

```python
        asset_diagnostics = _asset_rows(diagnostics, candidate)
        asset_errors = _asset_rows(errors, candidate)
        _apply_asset_counts(row, asset_diagnostics, asset_errors)
        diagnostic_status = _classify_from_join_diagnostics(row, asset_diagnostics)
        if diagnostic_status is not None:
            status, reason = diagnostic_status
            rows.append(_finalize_row(row, status, reason))
            continue
        if not asset_errors.empty:
            rows.append(_finalize_row(row, "manifest_query_error", "official disclosure manifest query failed for the asset"))
            continue
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_product_data_alignment_audit.py -q
```

Expected: PASS for all Task 1 and Task 2 tests.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/official_product_data_alignment_audit.py tests/test_official_product_data_alignment_audit.py
git commit -m "feat: classify official product alignment gaps"
```

---

### Task 3: Artifact Writer And Status Summary

**Files:**
- Modify: `src/stock_research/official_product_data_alignment_audit.py`
- Modify: `tests/test_official_product_data_alignment_audit.py`

- [ ] **Step 1: Add failing tests for summary and artifact output**

Append these tests to `tests/test_official_product_data_alignment_audit.py`:

```python
from stock_research.official_product_data_alignment_audit import (
    build_alignment_status_summary,
    write_alignment_audit_artifacts,
)


def test_status_summary_groups_overall_month_status_and_action():
    audit = pd.DataFrame(
        [
            {
                "run_id": "unit",
                "asset_id": "CN:SZ:000001",
                "candidate_trade_date": pd.Timestamp("2025-05-09").date(),
                "alignment_status": "pit_safe_product_evidence_available",
                "recommended_action": "use_for_readiness",
            },
            {
                "run_id": "unit",
                "asset_id": "CN:SZ:000002",
                "candidate_trade_date": pd.Timestamp("2025-05-16").date(),
                "alignment_status": "joinable_but_future_disclosure",
                "recommended_action": "shift_test_window_later",
            },
        ]
    )

    summary = build_alignment_status_summary(audit, run_id="unit")

    overall = summary[(summary["group"] == "overall") & (summary["group_value"] == "all")].iloc[0].to_dict()
    assert overall["candidate_rows"] == 2
    assert overall["candidate_assets"] == 2
    assert overall["pit_safe_rows"] == 1
    assert overall["future_disclosure_rows"] == 1
    assert set(summary["group"]) == {"overall", "candidate_month", "alignment_status", "recommended_action"}


def test_write_alignment_audit_artifacts_creates_csv_json_and_markdown(tmp_path):
    audit = pd.DataFrame(
        [
            {
                "run_id": "unit",
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "candidate_trade_date": pd.Timestamp("2025-05-09").date(),
                "as_of_date": pd.Timestamp("2025-05-09").date(),
                "alignment_status": "joinable_but_future_disclosure",
                "alignment_reason": "official manifest and product rows join, but publish_date is after candidate as_of_date",
                "has_pit_safe_product_evidence": False,
                "safe_product_evidence_count": 0,
                "unsafe_product_evidence_count": 1,
                "best_report_period": pd.Timestamp("2024-12-31").date(),
                "best_publish_date": pd.Timestamp("2025-07-28").date(),
                "best_disclosure_type": "annual",
                "best_source_document_id": "121999",
                "best_source_document_url": "http://example.com/report.pdf",
                "best_source_title": "2024年年度报告",
                "best_product_main_business_rows": 4,
                "best_manifest_rows": 1,
                "manifest_rows_for_asset": 1,
                "product_main_business_rows_for_asset": 4,
                "joinable_report_periods_for_asset": 1,
                "manifest_query_error_count_for_asset": 0,
                "max_safe_report_period": pd.NaT,
                "min_future_publish_date": pd.Timestamp("2025-07-28").date(),
                "days_until_first_future_disclosure": 80,
                "recommended_action": "shift_test_window_later",
            }
        ],
        columns=ALIGNMENT_AUDIT_COLUMNS,
    )

    result = write_alignment_audit_artifacts(audit=audit, output_dir=tmp_path, run_id="unit")

    assert result.output_dir == tmp_path
    assert result.candidate_rows == 1
    assert result.future_disclosure_rows == 1
    assert (tmp_path / "alignment_audit.csv").exists()
    assert (tmp_path / "alignment_audit.json").exists()
    assert (tmp_path / "alignment_status_summary.csv").exists()
    assert (tmp_path / "alignment_summary.md").exists()
    assert "shift_test_window_later" in (tmp_path / "alignment_summary.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_product_data_alignment_audit.py -q
```

Expected: FAIL because summary and artifact writer functions are not implemented.

- [ ] **Step 3: Implement summary and artifact writer functions**

Append these functions to `src/stock_research/official_product_data_alignment_audit.py`:

```python
def _candidate_month(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m")


def _summary_row(run_id: str, group: str, group_value: str, frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "run_id": _safe_text(run_id),
        "group": group,
        "group_value": group_value,
        "candidate_rows": int(len(frame)),
        "candidate_assets": int(frame["asset_id"].nunique()) if "asset_id" in frame.columns and not frame.empty else 0,
        "pit_safe_rows": int(frame["alignment_status"].eq("pit_safe_product_evidence_available").sum()) if "alignment_status" in frame.columns else 0,
        "future_disclosure_rows": int(frame["alignment_status"].eq("joinable_but_future_disclosure").sum()) if "alignment_status" in frame.columns else 0,
        "missing_product_period_rows": int(frame["alignment_status"].eq("manifest_available_no_joinable_product_period").sum()) if "alignment_status" in frame.columns else 0,
        "manifest_query_error_rows": int(frame["alignment_status"].eq("manifest_query_error").sum()) if "alignment_status" in frame.columns else 0,
    }


def build_alignment_status_summary(audit: pd.DataFrame, run_id: str) -> pd.DataFrame:
    frame = audit.copy()
    rows = [_summary_row(run_id, "overall", "all", frame)]
    if not frame.empty:
        frame["candidate_month"] = frame["candidate_trade_date"].map(_candidate_month)
        for month, group in frame.groupby("candidate_month", sort=True):
            rows.append(_summary_row(run_id, "candidate_month", month, group))
        for status, group in frame.groupby("alignment_status", sort=True):
            rows.append(_summary_row(run_id, "alignment_status", status, group))
        for action, group in frame.groupby("recommended_action", sort=True):
            rows.append(_summary_row(run_id, "recommended_action", action, group))
    return pd.DataFrame(rows, columns=ALIGNMENT_STATUS_SUMMARY_COLUMNS)


def _alignment_summary_markdown(audit: pd.DataFrame, summary: pd.DataFrame) -> str:
    overall = summary[(summary["group"] == "overall") & (summary["group_value"] == "all")].iloc[0].to_dict()
    status_counts = audit["alignment_status"].value_counts().sort_index() if not audit.empty else pd.Series(dtype=int)
    action_counts = audit["recommended_action"].value_counts().sort_index() if not audit.empty else pd.Series(dtype=int)
    future_dates = audit.loc[audit["min_future_publish_date"].notna(), "min_future_publish_date"] if not audit.empty else pd.Series(dtype=object)
    earliest_future_month = ""
    if not future_dates.empty:
        earliest_future_month = pd.to_datetime(future_dates.min()).strftime("%Y-%m")
    lines = [
        "# Official Product Data Alignment Audit",
        "",
        f"- candidate_rows: {overall['candidate_rows']}",
        f"- candidate_assets: {overall['candidate_assets']}",
        f"- pit_safe_rows: {overall['pit_safe_rows']}",
        f"- future_disclosure_rows: {overall['future_disclosure_rows']}",
        f"- manifest_query_error_rows: {overall['manifest_query_error_rows']}",
        "",
        "## Alignment Status Counts",
    ]
    lines.extend([f"- {status}: {int(count)}" for status, count in status_counts.items()])
    lines.extend(["", "## Recommended Action Counts"])
    lines.extend([f"- {action}: {int(count)}" for action, count in action_counts.items()])
    lines.extend(["", "## Next Action"])
    if int(overall["pit_safe_rows"]) > 0:
        lines.append("- proceed_to_readiness_scoring")
    elif int(overall["future_disclosure_rows"]) > 0:
        lines.append(f"- shift_test_window_later: earliest_future_disclosure_month={earliest_future_month}")
    elif int(overall["missing_product_period_rows"]) > 0:
        lines.append("- backfill_historical_product_rows")
    elif int(overall["manifest_query_error_rows"]) > 0:
        lines.append("- rerun_manifest_source")
    else:
        lines.append("- investigate_source_coverage")
    lines.append("")
    return "\n".join(lines)


def write_alignment_audit_artifacts(
    *,
    audit: pd.DataFrame,
    output_dir: Path,
    run_id: str,
) -> OfficialProductDataAlignmentAuditResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit = audit.copy()
    summary = build_alignment_status_summary(audit, run_id=run_id)
    audit.to_csv(output_dir / "alignment_audit.csv", index=False)
    (output_dir / "alignment_audit.json").write_text(
        json.dumps(audit.to_dict("records"), ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )
    summary.to_csv(output_dir / "alignment_status_summary.csv", index=False)
    (output_dir / "alignment_summary.md").write_text(_alignment_summary_markdown(audit, summary), encoding="utf-8")
    return OfficialProductDataAlignmentAuditResult(
        output_dir=output_dir,
        candidate_rows=int(len(audit)),
        candidate_assets=int(audit["asset_id"].nunique()) if not audit.empty else 0,
        pit_safe_rows=int(audit["alignment_status"].eq("pit_safe_product_evidence_available").sum()) if not audit.empty else 0,
        future_disclosure_rows=int(audit["alignment_status"].eq("joinable_but_future_disclosure").sum()) if not audit.empty else 0,
        manifest_query_error_rows=int(audit["alignment_status"].eq("manifest_query_error").sum()) if not audit.empty else 0,
    )
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_product_data_alignment_audit.py -q
```

Expected: PASS for all alignment audit tests.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/official_product_data_alignment_audit.py tests/test_official_product_data_alignment_audit.py
git commit -m "feat: write official product alignment audit artifacts"
```

---

### Task 4: File Runner, CLI, And Runbook

**Files:**
- Modify: `src/stock_research/official_product_data_alignment_audit.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_official_product_data_alignment_audit.py`
- Modify: `docs/tech-bottleneck-discovery-runbook.md`

- [ ] **Step 1: Add failing tests for file runner and CLI dispatch**

Append these tests to `tests/test_official_product_data_alignment_audit.py`:

```python
from stock_research.cli import build_parser, main_for_args
from stock_research.official_product_data_alignment_audit import (
    OfficialProductDataAlignmentAuditResult,
    run_official_product_data_alignment_audit_from_files,
)


def test_file_runner_reads_backfill_artifacts_and_writes_audit(tmp_path):
    candidates_csv = tmp_path / "candidates.csv"
    backfill_dir = tmp_path / "official_product_backfill"
    output_dir = tmp_path / "alignment"
    backfill_dir.mkdir()
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "ts_code": "000001.SZ",
                "stock_name": "平安银行",
                "trade_date": "2025-04-18",
            }
        ]
    ).to_csv(candidates_csv, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000001",
                "candidate_trade_date": "2025-04-18",
                "as_of_date": "2025-04-18",
                "evidence_date": "2025-04-25",
                "source_title": "2024年年度报告",
                "source_id": "121999",
                "source_url": "http://example.com/report.pdf",
                "as_of_safe": False,
                "metadata_json": json.dumps({"report_period": "2024-12-31", "publish_date": "2025-04-25"}),
            }
        ]
    ).to_csv(backfill_dir / "product_evidence.csv", index=False)
    pd.DataFrame().to_csv(backfill_dir / "disclosure_manifest.csv", index=False)
    pd.DataFrame().to_csv(backfill_dir / "product_join_diagnostics.csv", index=False)
    pd.DataFrame().to_csv(backfill_dir / "manifest_query_errors.csv", index=False)

    result = run_official_product_data_alignment_audit_from_files(
        candidates_csv=candidates_csv,
        official_product_backfill_dir=backfill_dir,
        output_dir=output_dir,
        run_id="unit",
    )

    audit = pd.read_csv(output_dir / "alignment_audit.csv")
    assert result.candidate_rows == 1
    assert audit.loc[0, "alignment_status"] == "joinable_but_future_disclosure"


def test_cli_includes_official_product_data_alignment_audit_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "tech-bottleneck-official-product-data-alignment-audit",
            "--candidates-csv",
            "candidates.csv",
            "--official-product-backfill-dir",
            "official_product_backfill",
            "--output-dir",
            "alignment",
            "--run-id",
            "unit",
        ]
    )

    assert args.command == "tech-bottleneck-official-product-data-alignment-audit"
    assert args.candidates_csv == "candidates.csv"
    assert args.official_product_backfill_dir == "official_product_backfill"
    assert args.output_dir == "alignment"
    assert args.run_id == "unit"


def test_cli_dispatches_official_product_data_alignment_audit(monkeypatch, capsys):
    calls = {}

    def fake_runner(**kwargs):
        calls["kwargs"] = kwargs
        return OfficialProductDataAlignmentAuditResult(
            output_dir=Path("alignment"),
            candidate_rows=3,
            candidate_assets=2,
            pit_safe_rows=0,
            future_disclosure_rows=3,
            manifest_query_error_rows=0,
        )

    monkeypatch.setattr("stock_research.cli.run_official_product_data_alignment_audit_from_files", fake_runner)

    main_for_args(
        [
            "tech-bottleneck-official-product-data-alignment-audit",
            "--candidates-csv",
            "candidates.csv",
            "--official-product-backfill-dir",
            "official_product_backfill",
            "--output-dir",
            "alignment",
            "--run-id",
            "unit",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert calls["kwargs"] == {
        "candidates_csv": Path("candidates.csv"),
        "official_product_backfill_dir": Path("official_product_backfill"),
        "output_dir": Path("alignment"),
        "run_id": "unit",
    }
    assert payload["candidate_rows"] == 3
    assert payload["future_disclosure_rows"] == 3
```

- [ ] **Step 2: Run tests and verify file runner/CLI tests fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_product_data_alignment_audit.py -q
```

Expected: FAIL because the file runner and CLI command are not implemented.

- [ ] **Step 3: Implement file runner**

Append this function to `src/stock_research/official_product_data_alignment_audit.py`:

```python
def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def run_official_product_data_alignment_audit_from_files(
    *,
    candidates_csv: Path,
    official_product_backfill_dir: Path,
    output_dir: Path,
    run_id: str,
) -> OfficialProductDataAlignmentAuditResult:
    candidates = pd.read_csv(candidates_csv, dtype=str)
    product_evidence = _read_csv_if_exists(official_product_backfill_dir / "product_evidence.csv")
    disclosure_manifest = _read_csv_if_exists(official_product_backfill_dir / "disclosure_manifest.csv")
    product_join_diagnostics = _read_csv_if_exists(official_product_backfill_dir / "product_join_diagnostics.csv")
    manifest_query_errors = _read_csv_if_exists(official_product_backfill_dir / "manifest_query_errors.csv")
    audit = build_alignment_audit(
        candidates=candidates,
        product_evidence=product_evidence,
        disclosure_manifest=disclosure_manifest,
        product_join_diagnostics=product_join_diagnostics,
        manifest_query_errors=manifest_query_errors,
        run_id=run_id,
    )
    return write_alignment_audit_artifacts(audit=audit, output_dir=output_dir, run_id=run_id)
```

- [ ] **Step 4: Wire the CLI command**

Modify `src/stock_research/cli.py`.

Add this import near the existing tech bottleneck imports:

```python
from stock_research.official_product_data_alignment_audit import (
    run_official_product_data_alignment_audit_from_files,
)
```

Add this parser block near the existing `tech-bottleneck-official-disclosure-product-backfill` parser:

```python
    official_product_alignment_parser = subparsers.add_parser(
        "tech-bottleneck-official-product-data-alignment-audit",
        help="Audit PIT alignment of official product evidence for tech bottleneck candidates",
    )
    official_product_alignment_parser.add_argument("--candidates-csv", required=True)
    official_product_alignment_parser.add_argument("--official-product-backfill-dir", required=True)
    official_product_alignment_parser.add_argument("--output-dir", required=True)
    official_product_alignment_parser.add_argument("--run-id", required=True)
```

Add this dispatch branch near the existing tech bottleneck dispatch branches:

```python
    elif args.command == "tech-bottleneck-official-product-data-alignment-audit":
        result = run_official_product_data_alignment_audit_from_files(
            candidates_csv=Path(args.candidates_csv),
            official_product_backfill_dir=Path(args.official_product_backfill_dir),
            output_dir=Path(args.output_dir),
            run_id=args.run_id,
        )
        print(
            json.dumps(
                {
                    "output_dir": str(result.output_dir),
                    "candidate_rows": result.candidate_rows,
                    "candidate_assets": result.candidate_assets,
                    "pit_safe_rows": result.pit_safe_rows,
                    "future_disclosure_rows": result.future_disclosure_rows,
                    "manifest_query_error_rows": result.manifest_query_error_rows,
                },
                ensure_ascii=False,
            )
        )
```

- [ ] **Step 5: Update the runbook**

Add this section to `docs/tech-bottleneck-discovery-runbook.md` after the official product backfill command:

````markdown
## Official Product Data Alignment Audit

Run this before readiness scoring or return testing when `has_product_revenue_exposure` stays at zero after official product backfill. The audit explains whether the issue is a PIT timing mismatch, missing historical product rows, missing official manifests, or source query errors.

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  tech-bottleneck-official-product-data-alignment-audit \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --official-product-backfill-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit \
  --run-id pilot-top50-2025-official-product-alignment-audit
```

Primary outputs:

- `alignment_audit.csv`: one row per candidate with `alignment_status` and `recommended_action`.
- `alignment_status_summary.csv`: counts by overall, candidate month, status, and action.
- `alignment_summary.md`: concise conclusion for the next experiment decision.

Do not run return tests from a window where `pit_safe_product_evidence_available` is zero and the dominant action is `shift_test_window_later` or `backfill_historical_product_rows`.
````

- [ ] **Step 6: Run tests and verify they pass**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_product_data_alignment_audit.py tests/test_official_disclosure_product_backfill.py -q
```

Expected: PASS for the new alignment audit tests and the existing official backfill tests.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/stock_research/official_product_data_alignment_audit.py src/stock_research/cli.py tests/test_official_product_data_alignment_audit.py docs/tech-bottleneck-discovery-runbook.md
git commit -m "feat: expose official product alignment audit"
```

---

### Task 5: Pilot Run And Verification

**Files:**
- Read: `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv`
- Read: `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill/product_evidence.csv`
- Read: `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill/product_join_diagnostics.csv`
- Create: `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit/alignment_audit.csv`
- Create: `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit/alignment_audit.json`
- Create: `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit/alignment_status_summary.csv`
- Create: `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit/alignment_summary.md`

- [ ] **Step 1: Run the full focused verification suite**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_product_data_alignment_audit.py tests/test_official_disclosure_product_backfill.py tests/test_tech_bottleneck_readiness.py -q
```

Expected: PASS. Existing `py_mini_racer` deprecation warnings may appear and do not block this task.

- [ ] **Step 2: Run the pilot alignment audit**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  tech-bottleneck-official-product-data-alignment-audit \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --official-product-backfill-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit \
  --run-id pilot-top50-2025-official-product-alignment-audit
```

Expected JSON shape:

```json
{
  "output_dir": "outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit",
  "candidate_rows": 1100,
  "candidate_assets": 647,
  "pit_safe_rows": 0,
  "future_disclosure_rows": 0,
  "manifest_query_error_rows": 0
}
```

The exact `future_disclosure_rows` may be greater than zero because product evidence and join diagnostics already contain future-published official rows. `candidate_rows`, `candidate_assets`, and `pit_safe_rows` are the strict checks here; `pit_safe_rows` must remain zero unless the input evidence has `as_of_safe=True`.

- [ ] **Step 3: Inspect status and action counts**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'
import pandas as pd
base = "outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit"
audit = pd.read_csv(f"{base}/alignment_audit.csv")
print("rows", len(audit))
print("assets", audit["asset_id"].nunique())
print(audit["alignment_status"].value_counts(dropna=False).to_string())
print(audit["recommended_action"].value_counts(dropna=False).to_string())
print("min_future_publish_date", audit["min_future_publish_date"].dropna().min())
print("max_future_publish_date", audit["min_future_publish_date"].dropna().max())
PY
```

Expected:

- `rows 1100`
- `assets 647`
- `pit_safe_product_evidence_available` count is `0`
- dominant next action is either `shift_test_window_later`, `backfill_historical_product_rows`, or a mix of those two

- [ ] **Step 4: Verify strict PIT invariant**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'
import pandas as pd
base = "outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit"
audit = pd.read_csv(f"{base}/alignment_audit.csv")
bad = audit[
    audit["alignment_status"].eq("pit_safe_product_evidence_available")
    & ~audit["has_pit_safe_product_evidence"].eq(True)
]
print("bad_safe_rows", len(bad))
raise SystemExit(1 if len(bad) else 0)
PY
```

Expected:

```text
bad_safe_rows 0
```

- [ ] **Step 5: Commit pilot outputs if the repository tracks experiment artifacts**

Run:

```bash
git status --short outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit
```

If the output files are not ignored, run:

```bash
git add outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_alignment_audit
git commit -m "data: add official product alignment audit pilot"
```

If the output files are ignored, do not force-add them; report the local output directory in the final handoff.

---

## Final Verification

Run:

```bash
git diff --check
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_product_data_alignment_audit.py tests/test_official_disclosure_product_backfill.py tests/test_tech_bottleneck_readiness.py -q
```

Expected:

- `git diff --check` prints no whitespace errors.
- pytest reports all selected tests passing.
- Existing `py_mini_racer` deprecation warnings may remain.

## Acceptance Checklist

- [ ] `alignment_audit.csv` has exactly one row per candidate row.
- [ ] Every candidate has one non-empty `alignment_status`.
- [ ] `pit_safe_product_evidence_available` is assigned only when candidate-scoped evidence has `as_of_safe=True`.
- [ ] Future disclosures and future report periods are separated into different statuses.
- [ ] Manifest query errors are not mixed into genuine no-data statuses.
- [ ] `alignment_summary.md` recommends a next action based only on artifact evidence.
