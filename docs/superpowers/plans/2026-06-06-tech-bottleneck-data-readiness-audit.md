# tech-bottleneck Data Readiness Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `tech-bottleneck-data-readiness-audit`, a CSV topN + Postgres audit that reports bottleneck evidence completeness per candidate before any scoring or return test.

**Architecture:** Add one pure-Python module that normalizes candidate rows, builds per-asset text/evidence context, computes deterministic readiness flags, writes JSON/CSV/Markdown artifacts, and exposes a DB-backed runner. Add a thin CLI command beside the existing `tech-bottleneck-discovery` commands. Keep v1 file-output only and avoid new persistent database tables.

**Tech Stack:** Python 3, pandas, psycopg via existing `stock_research.db.connect/fetch_all`, pytest, argparse CLI.

---

## File Structure

- Create `src/stock_research/tech_bottleneck_readiness.py`
  - Owns constants, keyword groups, candidate normalization, text evidence normalization, flag computation, status classification, artifact writing, SQL loaders, and file/DB runner.
- Create `tests/test_tech_bottleneck_readiness.py`
  - Unit tests for pure logic and artifact writing. Use in-memory DataFrames; no DB dependency.
- Modify `src/stock_research/cli.py`
  - Import `run_tech_bottleneck_readiness_audit_from_files`.
  - Register `tech-bottleneck-data-readiness-audit`.
  - Dispatch command and print JSON artifact paths.
- Modify `docs/tech-bottleneck-discovery-runbook.md`
  - Add the readiness audit command as the required pre-scoring step.
- Create `data/manual/tech_bottleneck_readiness_candidates_example.csv`
  - Tiny example candidate pool for CLI smoke.

## Data Contracts

### Candidate CSV

Required:

- `asset_id`

Optional:

- `stock_name`
- `trade_date`
- `candidate_source`
- `rank`

### Output Columns

`readiness.csv` must include:

```python
READINESS_COLUMNS = [
    "run_id",
    "asset_id",
    "stock_name",
    "trade_date",
    "candidate_source",
    "rank",
    "as_of_date",
    "lookback_days",
    "has_industry_context",
    "has_product_revenue_exposure",
    "has_research_report",
    "has_bottleneck_keywords",
    "has_capacity_evidence",
    "has_customer_certification_evidence",
    "has_patent_or_technical_barrier",
    "has_news_or_announcement_catalyst",
    "has_invalidation_evidence",
    "coverage_score",
    "coverage_status",
    "missing_flags",
    "proxy_flags",
    "source_gap_flags",
]
```

## Task 1: Pure Readiness Logic

**Files:**
- Create: `src/stock_research/tech_bottleneck_readiness.py`
- Create: `tests/test_tech_bottleneck_readiness.py`

- [ ] **Step 1: Write failing tests for candidate normalization and status classification**

Add this to `tests/test_tech_bottleneck_readiness.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.tech_bottleneck_readiness import (
    READINESS_FLAGS,
    build_readiness_audit,
    normalize_readiness_candidates,
)


def test_normalize_readiness_candidates_requires_asset_id() -> None:
    with pytest.raises(ValueError, match="asset_id"):
        normalize_readiness_candidates(
            pd.DataFrame([{"stock_name": "缺少代码"}]),
            run_date="2026-06-06",
            as_of_date=None,
            lookback_days=365,
        )


def test_normalize_readiness_candidates_fills_optional_columns_and_dates() -> None:
    candidates = normalize_readiness_candidates(
        pd.DataFrame(
            [
                {"asset_id": "CN:SH:688001", "stock_name": "示例光电", "trade_date": "2026-06-05", "rank": 1},
                {"asset_id": "CN:SZ:300001"},
            ]
        ),
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
    )

    rows = candidates.set_index("asset_id")
    assert rows.loc["CN:SH:688001", "as_of_date"] == "2026-06-05"
    assert rows.loc["CN:SZ:300001", "as_of_date"] == "2026-06-06"
    assert rows.loc["CN:SZ:300001", "stock_name"] == ""
    assert rows.loc["CN:SZ:300001", "candidate_source"] == ""
    assert rows.loc["CN:SZ:300001", "lookback_days"] == 365
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing functions.

- [ ] **Step 3: Implement constants and candidate normalization**

Create `src/stock_research/tech_bottleneck_readiness.py` with:

```python
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.db import connect, fetch_all


READINESS_FLAGS = [
    "has_industry_context",
    "has_product_revenue_exposure",
    "has_research_report",
    "has_bottleneck_keywords",
    "has_capacity_evidence",
    "has_customer_certification_evidence",
    "has_patent_or_technical_barrier",
    "has_news_or_announcement_catalyst",
    "has_invalidation_evidence",
]

FOUNDATION_FLAGS = [
    "has_industry_context",
    "has_product_revenue_exposure",
    "has_research_report",
]

READINESS_COLUMNS = [
    "run_id",
    "asset_id",
    "stock_name",
    "trade_date",
    "candidate_source",
    "rank",
    "as_of_date",
    "lookback_days",
    *READINESS_FLAGS,
    "coverage_score",
    "coverage_status",
    "missing_flags",
    "proxy_flags",
    "source_gap_flags",
]

BOTTLENECK_KEYWORDS = [
    "卡脖子",
    "瓶颈",
    "稀缺",
    "国产替代",
    "自主可控",
    "关键材料",
    "关键设备",
    "核心零部件",
    "供应链安全",
    "受限",
    "进口替代",
    "bottleneck",
    "chokepoint",
    "scarce",
    "shortage",
    "localization",
    "substitution",
    "critical material",
    "critical equipment",
]

CAPACITY_KEYWORDS = [
    "产能",
    "扩产",
    "爬坡",
    "良率",
    "交付周期",
    "供给受限",
    "供需缺口",
    "满产",
    "达产",
    "建设周期",
    "瓶颈产线",
    "capacity",
    "ramp",
    "yield",
    "lead time",
    "supply constraint",
    "utilization",
]

CUSTOMER_CERTIFICATION_KEYWORDS = [
    "客户认证",
    "客户验证",
    "导入",
    "定点",
    "合格供应商",
    "供应商认证",
    "批量供货",
    "订单",
    "在手订单",
    "客户突破",
    "qualification",
    "qualified supplier",
    "design win",
    "certification",
    "customer validation",
    "order backlog",
]

TECHNICAL_BARRIER_KEYWORDS = [
    "专利",
    "技术壁垒",
    "工艺壁垒",
    "配方",
    "know-how",
    "核心技术",
    "自研",
    "高精度",
    "高可靠",
    "高纯",
    "先进制程",
    "patent",
    "process know-how",
    "technical barrier",
    "proprietary",
    "high purity",
    "advanced process",
]

INVALIDATION_KEYWORDS = [
    "降价",
    "替代",
    "需求不及预期",
    "产能过剩",
    "客户流失",
    "毛利下滑",
    "延期",
    "减值",
    "竞争加剧",
    "路线变化",
    "技术替代",
    "price cut",
    "substitution",
    "demand miss",
    "oversupply",
    "customer loss",
    "margin pressure",
    "delay",
    "impairment",
    "route change",
]


def normalize_readiness_candidates(
    candidates: pd.DataFrame,
    *,
    run_date: str,
    as_of_date: str | None,
    lookback_days: int,
) -> pd.DataFrame:
    if "asset_id" not in candidates.columns:
        raise ValueError("readiness candidates must include asset_id")

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
    explicit_as_of = _date_text(as_of_date)
    normalized["as_of_date"] = normalized["trade_date"].map(
        lambda value: explicit_as_of or value or _date_text(run_date)
    )
    normalized["lookback_days"] = int(lookback_days)
    return normalized[
        ["asset_id", "stock_name", "trade_date", "candidate_source", "rank", "as_of_date", "lookback_days"]
    ]


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _date_text(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")
```

- [ ] **Step 4: Run tests and verify normalization tests pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: normalization tests PASS; later tests are not present yet.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/tech_bottleneck_readiness.py tests/test_tech_bottleneck_readiness.py
git commit -m "feat: add tech bottleneck readiness candidate normalization"
```

## Task 2: Compute Coverage Flags From Evidence Frames

**Files:**
- Modify: `src/stock_research/tech_bottleneck_readiness.py`
- Modify: `tests/test_tech_bottleneck_readiness.py`

- [ ] **Step 1: Add failing tests for all readiness flags and statuses**

Append to `tests/test_tech_bottleneck_readiness.py`:

```python
def _candidate_pool() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688001",
                "stock_name": "示例光电",
                "trade_date": "2026-06-05",
                "candidate_source": "industry-focus",
                "rank": 1,
            },
            {
                "asset_id": "CN:SZ:300001",
                "stock_name": "缺主营科技",
                "trade_date": "2026-06-05",
                "candidate_source": "industry-focus",
                "rank": 2,
            },
            {
                "asset_id": "CN:SH:688002",
                "stock_name": "新闻缺口",
                "trade_date": "2026-06-05",
                "candidate_source": "industry-focus",
                "rank": 3,
            },
        ]
    )


def _context_frames() -> dict[str, pd.DataFrame]:
    return {
        "industry": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "industry_system": "申万",
                    "industry_code": "801080",
                    "industry_name": "电子",
                    "level": 1,
                },
                {
                    "asset_id": "CN:SH:688002",
                    "industry_system": "申万",
                    "industry_code": "801080",
                    "industry_name": "电子",
                    "level": 1,
                },
            ]
        ),
        "main_business": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_period": "2026-03-31",
                    "classify_type": "按产品分类",
                    "item_name": "AI 光模块关键材料",
                    "revenue": 100,
                    "revenue_ratio": 45,
                    "gross_margin": 35,
                },
                {
                    "asset_id": "CN:SH:688002",
                    "report_period": "2026-03-31",
                    "classify_type": "按产品分类",
                    "item_name": "高纯关键材料",
                    "revenue": 80,
                    "revenue_ratio": 40,
                    "gross_margin": 30,
                },
            ]
        ),
        "reports": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "report_id": "r1",
                    "report_date": "2026-05-20",
                    "report_title": "关键材料国产替代加速",
                    "raw_summary": "客户验证推进，扩产建设周期长，技术壁垒高，存在需求不及预期风险。",
                    "company_view": "公司是关键材料供应商。",
                    "industry_view": "供给受限。",
                    "risk_summary": "客户导入延期。",
                    "source_type": "public_web_search_result",
                    "broker": "示例证券",
                },
                {
                    "asset_id": "CN:SH:688002",
                    "report_id": "r2",
                    "report_date": "2026-05-20",
                    "report_title": "关键材料供应商",
                    "raw_summary": "技术壁垒较高。",
                    "company_view": "",
                    "industry_view": "",
                    "risk_summary": "",
                    "source_type": "public_web_search_result",
                    "broker": "示例证券",
                },
            ]
        ),
        "report_features": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "trade_date": "2026-06-05",
                    "report_count_90d": 2,
                    "source_count": 2,
                },
                {
                    "asset_id": "CN:SH:688002",
                    "trade_date": "2026-06-05",
                    "report_count_90d": 1,
                    "source_count": 1,
                },
            ]
        ),
        "events": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688001",
                    "event_type": "institution_survey",
                    "event_date": "2026-05-30",
                    "summary": "在手订单增长，合格供应商认证推进。",
                }
            ]
        ),
        "news": pd.DataFrame(),
    }


def test_build_readiness_audit_flags_statuses_and_source_gaps() -> None:
    audit = build_readiness_audit(
        candidates=_candidate_pool(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        source_tables_empty={"news": True},
        **_context_frames(),
    )

    rows = audit.summary.set_index("asset_id")
    ready = rows.loc["CN:SH:688001"]
    blocked = rows.loc["CN:SZ:300001"]
    source_gap = rows.loc["CN:SH:688002"]

    for flag in READINESS_FLAGS:
        assert flag in rows.columns

    assert ready["coverage_status"] == "ready_for_scoring"
    assert ready["coverage_score"] >= 7
    assert ready["has_industry_context"] is True
    assert ready["has_product_revenue_exposure"] is True
    assert ready["has_research_report"] is True
    assert ready["has_bottleneck_keywords"] is True
    assert ready["has_capacity_evidence"] is True
    assert ready["has_customer_certification_evidence"] is True
    assert ready["has_patent_or_technical_barrier"] is True
    assert ready["has_news_or_announcement_catalyst"] is True
    assert ready["has_invalidation_evidence"] is True
    assert "has_patent_or_technical_barrier" in ready["proxy_flags"]

    assert blocked["coverage_status"] == "data_blocked"
    assert blocked["has_product_revenue_exposure"] is False
    assert "has_product_revenue_exposure" in blocked["missing_flags"]

    assert source_gap["coverage_status"] == "source_gap"
    assert source_gap["has_news_or_announcement_catalyst"] is False
    assert "has_news_or_announcement_catalyst" in source_gap["source_gap_flags"]

    detail = {row["asset_id"]: row for row in audit.details}
    assert detail["CN:SH:688001"]["evidence_counts"]["reports"] == 1
    assert detail["CN:SH:688001"]["flag_details"]["has_capacity_evidence"][0]["keyword"] == "扩产"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: FAIL because `build_readiness_audit` does not exist.

- [ ] **Step 3: Implement audit result, text corpus, keyword matching, scoring, and status**

Append the following implementation to `src/stock_research/tech_bottleneck_readiness.py`:

```python
class ReadinessAuditResult:
    def __init__(self, *, summary: pd.DataFrame, details: list[dict[str, Any]]) -> None:
        self.summary = summary
        self.details = details


def build_readiness_audit(
    *,
    candidates: pd.DataFrame,
    run_id: str,
    run_date: str,
    as_of_date: str | None,
    lookback_days: int,
    industry: pd.DataFrame,
    main_business: pd.DataFrame,
    reports: pd.DataFrame,
    report_features: pd.DataFrame,
    events: pd.DataFrame,
    news: pd.DataFrame,
    source_tables_empty: dict[str, bool] | None = None,
) -> ReadinessAuditResult:
    normalized = normalize_readiness_candidates(
        candidates,
        run_date=run_date,
        as_of_date=as_of_date,
        lookback_days=lookback_days,
    )
    empty_sources = source_tables_empty or {}
    lookups = {
        "industry": _rows_by_asset(industry),
        "main_business": _rows_by_asset(main_business),
        "reports": _rows_by_asset(reports),
        "report_features": _rows_by_asset(report_features),
        "events": _rows_by_asset(events),
        "news": _rows_by_asset(news),
    }

    summary_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for candidate in normalized.to_dict("records"):
        asset_id = candidate["asset_id"]
        corpus = _build_text_corpus(
            asset_id=asset_id,
            reports=lookups["reports"].get(asset_id, []),
            events=lookups["events"].get(asset_id, []),
            news=lookups["news"].get(asset_id, []),
            main_business=lookups["main_business"].get(asset_id, []),
        )
        flag_details: dict[str, list[dict[str, Any]]] = {flag: [] for flag in READINESS_FLAGS}
        proxy_flags: list[str] = []
        source_gap_flags: list[str] = []

        industry_rows = lookups["industry"].get(asset_id, [])
        main_business_rows = [
            row
            for row in lookups["main_business"].get(asset_id, [])
            if _safe_text(row.get("classify_type")) == "按产品分类" and _safe_text(row.get("item_name"))
        ]
        report_rows = lookups["reports"].get(asset_id, [])
        report_feature_rows = [
            row
            for row in lookups["report_features"].get(asset_id, [])
            if _safe_number(row.get("report_count_90d")) > 0 or _safe_number(row.get("source_count")) > 0
        ]
        event_rows = lookups["events"].get(asset_id, [])
        news_rows = lookups["news"].get(asset_id, [])

        flags = {
            "has_industry_context": bool(industry_rows),
            "has_product_revenue_exposure": bool(main_business_rows),
            "has_research_report": bool(report_rows or report_feature_rows),
            "has_bottleneck_keywords": False,
            "has_capacity_evidence": False,
            "has_customer_certification_evidence": False,
            "has_patent_or_technical_barrier": False,
            "has_news_or_announcement_catalyst": bool(news_rows or event_rows),
            "has_invalidation_evidence": False,
        }

        flag_details["has_industry_context"] = _sample_rows(industry_rows, "industry")
        flag_details["has_product_revenue_exposure"] = _sample_rows(main_business_rows, "main_business")
        flag_details["has_research_report"] = _sample_rows(report_rows or report_feature_rows, "reports")
        flag_details["has_news_or_announcement_catalyst"] = _sample_rows(news_rows or event_rows, "events")

        keyword_specs = [
            ("has_bottleneck_keywords", BOTTLENECK_KEYWORDS),
            ("has_capacity_evidence", CAPACITY_KEYWORDS),
            ("has_customer_certification_evidence", CUSTOMER_CERTIFICATION_KEYWORDS),
            ("has_patent_or_technical_barrier", TECHNICAL_BARRIER_KEYWORDS),
            ("has_invalidation_evidence", INVALIDATION_KEYWORDS),
        ]
        for flag, keywords in keyword_specs:
            matches = _keyword_matches(corpus, keywords)
            if matches:
                flags[flag] = True
                flag_details[flag] = matches[:3]

        if flags["has_patent_or_technical_barrier"]:
            proxy_flags.append("has_patent_or_technical_barrier")
        if flags["has_bottleneck_keywords"] and all(item.get("proxy_only") for item in flag_details["has_bottleneck_keywords"]):
            proxy_flags.append("has_bottleneck_keywords")
        if not flags["has_news_or_announcement_catalyst"] and empty_sources.get("news"):
            source_gap_flags.append("has_news_or_announcement_catalyst")

        missing_flags = [flag for flag in READINESS_FLAGS if not flags[flag]]
        coverage_score = _coverage_score(flags)
        status = _coverage_status(
            flags=flags,
            coverage_score=coverage_score,
            source_gap_flags=source_gap_flags,
        )
        row = {
            "run_id": run_id,
            **candidate,
            **flags,
            "coverage_score": coverage_score,
            "coverage_status": status,
            "missing_flags": missing_flags,
            "proxy_flags": proxy_flags,
            "source_gap_flags": source_gap_flags,
        }
        summary_rows.append(row)
        details.append(
            {
                "run_id": run_id,
                "asset_id": asset_id,
                "stock_name": candidate.get("stock_name", ""),
                "as_of_date": candidate.get("as_of_date", ""),
                "flags": flags,
                "coverage_score": coverage_score,
                "coverage_status": status,
                "missing_flags": missing_flags,
                "proxy_flags": proxy_flags,
                "source_gap_flags": source_gap_flags,
                "evidence_counts": {
                    "industry": len(industry_rows),
                    "main_business": len(main_business_rows),
                    "reports": len(report_rows),
                    "report_features": len(report_feature_rows),
                    "events": len(event_rows),
                    "news": len(news_rows),
                },
                "flag_details": flag_details,
            }
        )

    summary = pd.DataFrame(summary_rows, columns=READINESS_COLUMNS)
    return ReadinessAuditResult(summary=summary, details=details)


def _rows_by_asset(frame: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if frame.empty or "asset_id" not in frame.columns:
        return {}
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in frame.to_dict("records"):
        asset_id = _safe_text(row.get("asset_id"))
        if asset_id:
            rows[asset_id].append(row)
    return dict(rows)


def _build_text_corpus(
    *,
    asset_id: str,
    reports: list[dict[str, Any]],
    events: list[dict[str, Any]],
    news: list[dict[str, Any]],
    main_business: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in reports:
        for field in ["report_title", "raw_summary", "company_view", "industry_view", "risk_summary"]:
            _append_text(records, row, source_table="reports", field_name=field, proxy_only=False)
    for row in events:
        _append_text(records, row, source_table="events", field_name="summary", proxy_only=False)
    for row in news:
        for field in ["title", "content"]:
            _append_text(records, row, source_table="news", field_name=field, proxy_only=False)
    for row in main_business:
        _append_text(records, row, source_table="main_business", field_name="item_name", proxy_only=True)
    return records


def _append_text(
    records: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    source_table: str,
    field_name: str,
    proxy_only: bool,
) -> None:
    text = _safe_text(row.get(field_name))
    if not text:
        return
    records.append(
        {
            "source_table": source_table,
            "source_id": _safe_text(row.get("report_id") or row.get("event_id") or row.get("source_event_id")),
            "source_date": _date_text(row.get("report_date") or row.get("event_date") or row.get("published_at") or row.get("report_period")),
            "field_name": field_name,
            "text": text,
            "proxy_only": proxy_only,
        }
    )


def _keyword_matches(corpus: list[dict[str, Any]], keywords: list[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for record in corpus:
        text = _safe_text(record.get("text"))
        lowered = text.lower()
        for keyword in keywords:
            key = keyword.lower()
            if key and key in lowered:
                matches.append(
                    {
                        "source_table": record.get("source_table", ""),
                        "source_id": record.get("source_id", ""),
                        "source_date": record.get("source_date", ""),
                        "field_name": record.get("field_name", ""),
                        "keyword": keyword,
                        "snippet": _snippet(text, keyword),
                        "proxy_only": bool(record.get("proxy_only")),
                    }
                )
                break
    return matches


def _coverage_score(flags: dict[str, bool]) -> int:
    return (
        2 * int(flags["has_industry_context"])
        + 2 * int(flags["has_product_revenue_exposure"])
        + 2 * int(flags["has_research_report"])
        + sum(int(flags[flag]) for flag in READINESS_FLAGS if flag not in FOUNDATION_FLAGS)
    )


def _coverage_status(
    *,
    flags: dict[str, bool],
    coverage_score: int,
    source_gap_flags: list[str],
) -> str:
    if not flags["has_industry_context"] or not flags["has_product_revenue_exposure"]:
        return "data_blocked"
    if (
        flags["has_industry_context"]
        and flags["has_product_revenue_exposure"]
        and flags["has_research_report"]
        and flags["has_bottleneck_keywords"]
        and coverage_score >= 7
    ):
        return "ready_for_scoring"
    if source_gap_flags:
        return "source_gap"
    if all(flags[flag] for flag in FOUNDATION_FLAGS):
        return "needs_evidence_backfill"
    return "needs_evidence_backfill"


def _sample_rows(rows: list[dict[str, Any]], source_table: str) -> list[dict[str, Any]]:
    samples = []
    for row in rows[:3]:
        samples.append(
            {
                "source_table": source_table,
                "source_date": _date_text(
                    row.get("report_date")
                    or row.get("trade_date")
                    or row.get("event_date")
                    or row.get("report_period")
                ),
                "summary": _safe_text(
                    row.get("industry_name")
                    or row.get("item_name")
                    or row.get("report_title")
                    or row.get("summary")
                ),
            }
        )
    return samples


def _snippet(text: str, keyword: str) -> str:
    lowered = text.lower()
    index = lowered.find(keyword.lower())
    if index < 0:
        return text[:120]
    start = max(0, index - 40)
    end = min(len(text), index + len(keyword) + 40)
    return text[start:end]


def _safe_number(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0
```

- [ ] **Step 4: Run tests and fix deterministic ordering if needed**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: all current readiness tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/tech_bottleneck_readiness.py tests/test_tech_bottleneck_readiness.py
git commit -m "feat: compute tech bottleneck readiness flags"
```

## Task 3: Artifact Writing And Markdown Summary

**Files:**
- Modify: `src/stock_research/tech_bottleneck_readiness.py`
- Modify: `tests/test_tech_bottleneck_readiness.py`

- [ ] **Step 1: Add failing artifact tests**

Append to `tests/test_tech_bottleneck_readiness.py`:

```python
from stock_research.tech_bottleneck_readiness import write_readiness_artifacts


def test_write_readiness_artifacts_writes_csv_json_and_summary(tmp_path: Path) -> None:
    audit = build_readiness_audit(
        candidates=_candidate_pool(),
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        source_tables_empty={"news": True},
        **_context_frames(),
    )

    paths = write_readiness_artifacts(audit=audit, output_dir=tmp_path)

    assert paths["csv"] == tmp_path / "readiness.csv"
    assert paths["json"] == tmp_path / "readiness.json"
    assert paths["summary"] == tmp_path / "summary.md"
    assert paths["csv"].exists()
    assert paths["json"].exists()
    assert paths["summary"].exists()

    csv_text = paths["csv"].read_text(encoding="utf-8")
    assert "ready_for_scoring" in csv_text
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["candidate_count"] == 3
    assert payload["candidates"][0]["run_id"] == "readiness-test"
    markdown = paths["summary"].read_text(encoding="utf-8")
    assert "# tech-bottleneck data readiness audit" in markdown
    assert "ready_for_scoring" in markdown
    assert "has_news_or_announcement_catalyst" in markdown
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: FAIL because `write_readiness_artifacts` does not exist.

- [ ] **Step 3: Implement artifact writing**

Append to `src/stock_research/tech_bottleneck_readiness.py`:

```python
def write_readiness_artifacts(*, audit: ReadinessAuditResult, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "readiness.csv"
    json_path = output_dir / "readiness.json"
    summary_path = output_dir / "summary.md"

    csv_frame = audit.summary.copy()
    for column in ["missing_flags", "proxy_flags", "source_gap_flags"]:
        if column in csv_frame.columns:
            csv_frame[column] = csv_frame[column].map(lambda value: json.dumps(value, ensure_ascii=False))
    csv_frame.to_csv(csv_path, index=False)

    payload = {
        "candidate_count": int(len(audit.summary)),
        "status_counts": audit.summary["coverage_status"].value_counts().to_dict() if not audit.summary.empty else {},
        "flag_coverage": _flag_coverage(audit.summary),
        "candidates": audit.details,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    summary_path.write_text(render_readiness_summary(audit), encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "summary": summary_path}


def render_readiness_summary(audit: ReadinessAuditResult) -> str:
    lines = ["# tech-bottleneck data readiness audit", ""]
    lines.append(f"- Candidates: {len(audit.summary)}")
    if audit.summary.empty:
        return "\n".join(lines) + "\n"

    lines.extend(["", "## Status Counts", ""])
    for status, count in audit.summary["coverage_status"].value_counts().sort_index().items():
        lines.append(f"- `{status}`: {int(count)}")

    lines.extend(["", "## Flag Coverage", ""])
    coverage = _flag_coverage(audit.summary)
    for flag in READINESS_FLAGS:
        info = coverage[flag]
        lines.append(f"- `{flag}`: {info['true_count']}/{info['candidate_count']} ({info['coverage_rate']:.1%})")

    lines.extend(["", "## Ready Candidates", ""])
    ready = audit.summary[audit.summary["coverage_status"] == "ready_for_scoring"]
    if ready.empty:
        lines.append("- None")
    else:
        for row in ready.to_dict("records"):
            lines.append(f"- `{row['asset_id']}` {row.get('stock_name', '')} score={row['coverage_score']}")

    lines.extend(["", "## Blocked Candidates", ""])
    blocked = audit.summary[audit.summary["coverage_status"].isin(["data_blocked", "source_gap"])]
    if blocked.empty:
        lines.append("- None")
    else:
        for row in blocked.to_dict("records"):
            lines.append(
                f"- `{row['asset_id']}` {row.get('stock_name', '')} "
                f"status={row['coverage_status']} missing={','.join(row.get('missing_flags', []))}"
            )

    return "\n".join(lines) + "\n"


def _flag_coverage(summary: pd.DataFrame) -> dict[str, dict[str, Any]]:
    candidate_count = int(len(summary))
    result: dict[str, dict[str, Any]] = {}
    for flag in READINESS_FLAGS:
        true_count = int(summary[flag].sum()) if flag in summary.columns and candidate_count else 0
        result[flag] = {
            "true_count": true_count,
            "candidate_count": candidate_count,
            "coverage_rate": true_count / candidate_count if candidate_count else 0.0,
        }
    return result
```

- [ ] **Step 4: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: all readiness tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/tech_bottleneck_readiness.py tests/test_tech_bottleneck_readiness.py
git commit -m "feat: write tech bottleneck readiness artifacts"
```

## Task 4: DB Loaders And File Runner

**Files:**
- Modify: `src/stock_research/tech_bottleneck_readiness.py`
- Modify: `tests/test_tech_bottleneck_readiness.py`

- [ ] **Step 1: Add failing tests for runner with injected loader**

Append to `tests/test_tech_bottleneck_readiness.py`:

```python
from stock_research.tech_bottleneck_readiness import run_readiness_audit_from_files


def test_run_readiness_audit_from_files_uses_loader_and_writes_artifacts(tmp_path: Path) -> None:
    candidates_csv = tmp_path / "candidates.csv"
    _candidate_pool().to_csv(candidates_csv, index=False)

    def fake_loader(candidates: pd.DataFrame, *, lookback_days: int, service: str) -> dict[str, pd.DataFrame]:
        assert set(candidates["asset_id"]) == {"CN:SH:688001", "CN:SZ:300001", "CN:SH:688002"}
        assert lookback_days == 365
        assert service == "stock_research"
        return _context_frames() | {"source_tables_empty": {"news": True}}

    paths = run_readiness_audit_from_files(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="readiness-test",
        run_date="2026-06-06",
        as_of_date=None,
        lookback_days=365,
        service="stock_research",
        context_loader=fake_loader,
    )

    assert paths["csv"].exists()
    assert paths["json"].exists()
    assert paths["summary"].exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: FAIL because runner does not exist.

- [ ] **Step 3: Implement runner and DB context loader**

Append to `src/stock_research/tech_bottleneck_readiness.py`:

```python
def run_readiness_audit_from_files(
    *,
    candidates_csv: Path,
    output_dir: Path,
    run_id: str,
    run_date: str,
    as_of_date: str | None,
    lookback_days: int,
    service: str,
    context_loader: Any | None = None,
) -> dict[str, Path]:
    candidates = pd.read_csv(candidates_csv)
    normalized = normalize_readiness_candidates(
        candidates,
        run_date=run_date,
        as_of_date=as_of_date,
        lookback_days=lookback_days,
    )
    loader = context_loader or load_readiness_context_from_db
    context = loader(normalized, lookback_days=lookback_days, service=service)
    source_tables_empty = context.pop("source_tables_empty", {})
    audit = build_readiness_audit(
        candidates=normalized,
        run_id=run_id,
        run_date=run_date,
        as_of_date=as_of_date,
        lookback_days=lookback_days,
        source_tables_empty=source_tables_empty,
        **context,
    )
    return write_readiness_artifacts(audit=audit, output_dir=output_dir)


def load_readiness_context_from_db(
    candidates: pd.DataFrame,
    *,
    lookback_days: int,
    service: str,
) -> dict[str, pd.DataFrame | dict[str, bool]]:
    asset_ids = sorted({str(value) for value in candidates["asset_id"].dropna().tolist() if str(value).strip()})
    if not asset_ids:
        return _empty_context()
    min_as_of = candidates["as_of_date"].min()
    max_as_of = candidates["as_of_date"].max()

    with connect(service) as conn:
        industry = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT asset_id, industry_system, industry_code, industry_name, level, start_date, end_date
                FROM core.industry_membership
                WHERE asset_id = ANY(%s)
                  AND start_date <= %s::date
                  AND (end_date IS NULL OR end_date >= %s::date)
                """,
                (asset_ids, max_as_of, min_as_of),
            )
        )
        main_business = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT asset_id, report_period, classify_type, item_name, revenue, revenue_ratio, gross_margin
                FROM finance.main_business_composition
                WHERE asset_id = ANY(%s)
                  AND report_period <= %s::date
                """,
                (asset_ids, max_as_of),
            )
        )
        reports = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT
                    e.asset_id,
                    e.report_id,
                    e.report_date,
                    s.report_title,
                    s.raw_summary,
                    e.company_view,
                    e.industry_view,
                    e.risk_summary,
                    s.source_type,
                    s.broker
                FROM research.stock_report_event e
                LEFT JOIN research.stock_report_source s ON s.report_id = e.report_id
                WHERE e.asset_id = ANY(%s)
                  AND e.report_date BETWEEN (%s::date - (%s::int * interval '1 day')) AND %s::date
                """,
                (asset_ids, max_as_of, int(lookback_days), max_as_of),
            )
        )
        report_features = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT asset_id, trade_date, report_count_90d, source_count
                FROM research.stock_report_feature_daily
                WHERE asset_id = ANY(%s)
                  AND trade_date BETWEEN (%s::date - (%s::int * interval '1 day')) AND %s::date
                """,
                (asset_ids, max_as_of, int(lookback_days), max_as_of),
            )
        )
        events = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT asset_id, 'institution_survey' AS event_type, survey_date AS event_date, summary
                FROM event.institution_survey
                WHERE asset_id = ANY(%s)
                  AND survey_date BETWEEN (%s::date - (%s::int * interval '1 day')) AND %s::date
                UNION ALL
                SELECT asset_id, 'earnings_forecast' AS event_type, announcement_date AS event_date, summary
                FROM event.earnings_forecast
                WHERE asset_id = ANY(%s)
                  AND announcement_date BETWEEN (%s::date - (%s::int * interval '1 day')) AND %s::date
                UNION ALL
                SELECT asset_id, 'earnings_express' AS event_type, announcement_date AS event_date, '' AS summary
                FROM event.earnings_express
                WHERE asset_id = ANY(%s)
                  AND announcement_date BETWEEN (%s::date - (%s::int * interval '1 day')) AND %s::date
                """,
                (
                    asset_ids,
                    max_as_of,
                    int(lookback_days),
                    max_as_of,
                    asset_ids,
                    max_as_of,
                    int(lookback_days),
                    max_as_of,
                    asset_ids,
                    max_as_of,
                    int(lookback_days),
                    max_as_of,
                ),
            )
        )
        news = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT
                    m.asset_id,
                    m.source_event_id,
                    s.published_at AS event_date,
                    s.title,
                    s.content
                FROM research.news_event_mention m
                JOIN research.news_event_source s ON s.source_event_id = m.source_event_id
                WHERE m.asset_id = ANY(%s)
                  AND m.trade_date BETWEEN (%s::date - (%s::int * interval '1 day')) AND %s::date
                """,
                (asset_ids, max_as_of, int(lookback_days), max_as_of),
            )
        )
        news_count = fetch_all(conn, "SELECT count(*) AS count FROM research.news_event_source")

    return {
        "industry": industry,
        "main_business": main_business,
        "reports": reports,
        "report_features": report_features,
        "events": events,
        "news": news,
        "source_tables_empty": {"news": int(news_count[0]["count"]) == 0 if news_count else True},
    }


def _empty_context() -> dict[str, pd.DataFrame | dict[str, bool]]:
    return {
        "industry": pd.DataFrame(),
        "main_business": pd.DataFrame(),
        "reports": pd.DataFrame(),
        "report_features": pd.DataFrame(),
        "events": pd.DataFrame(),
        "news": pd.DataFrame(),
        "source_tables_empty": {"news": True},
    }
```

- [ ] **Step 4: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: all readiness tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/tech_bottleneck_readiness.py tests/test_tech_bottleneck_readiness.py
git commit -m "feat: load tech bottleneck readiness context"
```

## Task 5: CLI Command And Example Input

**Files:**
- Modify: `src/stock_research/cli.py`
- Create: `data/manual/tech_bottleneck_readiness_candidates_example.csv`
- Modify: `tests/test_tech_bottleneck_readiness.py`

- [ ] **Step 1: Add CLI/import smoke test**

Append to `tests/test_tech_bottleneck_readiness.py`:

```python
def test_readiness_module_exports_runner() -> None:
    from stock_research.tech_bottleneck_readiness import run_readiness_audit_from_files

    assert callable(run_readiness_audit_from_files)
```

- [ ] **Step 2: Add CLI import and parser**

In `src/stock_research/cli.py`, add this import near the existing tech bottleneck imports:

```python
from stock_research.tech_bottleneck_readiness import run_readiness_audit_from_files
```

Add parser registration immediately before `tech-bottleneck-discovery`:

```python
    tech_bottleneck_readiness = subparsers.add_parser(
        "tech-bottleneck-data-readiness-audit",
        help="Audit tech bottleneck evidence completeness for an existing topN candidate CSV.",
    )
    tech_bottleneck_readiness.add_argument("--candidates-csv", required=True)
    tech_bottleneck_readiness.add_argument("--output-dir", required=True)
    tech_bottleneck_readiness.add_argument("--run-id", required=True)
    tech_bottleneck_readiness.add_argument("--as-of-date")
    tech_bottleneck_readiness.add_argument("--lookback-days", type=int, default=365)
    tech_bottleneck_readiness.add_argument("--service", default="stock_research")
```

Add dispatch immediately before `elif args.command == "tech-bottleneck-discovery":`

```python
    elif args.command == "tech-bottleneck-data-readiness-audit":
        run_date = pd.Timestamp.today().strftime("%Y-%m-%d")
        paths = run_readiness_audit_from_files(
            candidates_csv=Path(args.candidates_csv),
            output_dir=Path(args.output_dir),
            run_id=str(args.run_id),
            run_date=run_date,
            as_of_date=args.as_of_date,
            lookback_days=int(args.lookback_days),
            service=str(args.service),
        )
        print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
```

- [ ] **Step 3: Add example candidate CSV**

Create `data/manual/tech_bottleneck_readiness_candidates_example.csv`:

```csv
asset_id,stock_name,trade_date,candidate_source,rank
CN:SH:688001,示例光电,2026-06-05,industry-focus,1
CN:SZ:300001,普通科技,2026-06-05,industry-focus,2
```

- [ ] **Step 4: Run unit tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py -q
```

Expected: all readiness tests PASS.

- [ ] **Step 5: Run CLI help**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli tech-bottleneck-data-readiness-audit --help
```

Expected: help text includes `--candidates-csv`, `--output-dir`, `--run-id`, `--lookback-days`, and `--service`.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/cli.py tests/test_tech_bottleneck_readiness.py data/manual/tech_bottleneck_readiness_candidates_example.csv
git commit -m "feat: add tech bottleneck readiness cli"
```

## Task 6: Runbook And Verification

**Files:**
- Modify: `docs/tech-bottleneck-discovery-runbook.md`

- [ ] **Step 1: Update runbook**

Insert after the opening paragraph in `docs/tech-bottleneck-discovery-runbook.md`:

```markdown
## Data Readiness Audit

Run this before generating research packets. It checks whether an existing topN candidate pool has enough industry, product, report, bottleneck, capacity, customer, technical-barrier, catalyst, and invalidation evidence.

```bash
stock-research tech-bottleneck-data-readiness-audit \
  --candidates-csv data/manual/tech_bottleneck_readiness_candidates_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/readiness_example \
  --run-id tech-bottleneck-readiness-example \
  --lookback-days 365 \
  --service stock_research
```

Outputs:

- `readiness.csv`: one row per candidate with boolean coverage flags.
- `readiness.json`: structured evidence counts and snippets.
- `summary.md`: pool-level coverage gaps and status counts.

Only candidates with `coverage_status=ready_for_scoring` should move into `tech-bottleneck-discovery` packet generation.
```
```

- [ ] **Step 2: Run final unit tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_readiness.py tests/test_tech_bottleneck_discovery.py tests/test_tech_bottleneck_experiment.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 3: Run DB-backed example smoke**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli tech-bottleneck-data-readiness-audit \
  --candidates-csv data/manual/tech_bottleneck_readiness_candidates_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/readiness_example \
  --run-id tech-bottleneck-readiness-example \
  --lookback-days 365 \
  --service stock_research
```

Expected: command prints JSON paths for `readiness.csv`, `readiness.json`, and `summary.md`. It does not run any return test.

- [ ] **Step 4: Inspect output summary**

Run:

```bash
sed -n '1,220p' outputs/tech_bottleneck_discovery/readiness_example/summary.md
```

Expected: summary includes candidate count, status counts, flag coverage, ready candidates, and blocked candidates.

- [ ] **Step 5: Check git diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files modified.

- [ ] **Step 6: Commit**

```bash
git add docs/tech-bottleneck-discovery-runbook.md
git commit -m "docs: add tech bottleneck readiness runbook"
```

## Self-Review Checklist

- Spec coverage: The plan implements CSV topN input, Postgres-backed audit, all nine flags, readiness statuses, CSV/JSON/Markdown outputs, source-gap handling, and no-return-test boundary.
- Placeholder scan: The plan contains no placeholder tasks or unspecified tests.
- Type consistency: Public functions are `normalize_readiness_candidates`, `build_readiness_audit`, `write_readiness_artifacts`, `load_readiness_context_from_db`, and `run_readiness_audit_from_files`.
- Scope check: The plan does not add persistent DB tables, LLM inference, full-market scanning, or return testing.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-06-tech-bottleneck-data-readiness-audit.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
