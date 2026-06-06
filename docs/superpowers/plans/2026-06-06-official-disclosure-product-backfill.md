# Official Disclosure Product Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated, candidate-scoped official-disclosure product revenue backfill so `tech-bottleneck-discovery` can produce strict PIT-safe `has_product_revenue_exposure` evidence before alpha testing.

**Architecture:** Add a focused product backfill module that queries or loads official disclosure manifests, joins them to existing `finance.main_business_composition` rows, emits normalized `product_revenue_exposure` evidence, and writes audit artifacts. Keep all external disclosure access behind an injectable client so tests are deterministic and live source drift becomes a measurable source gap rather than silent bad evidence.

**Tech Stack:** Python 3, pandas, psycopg, stdlib `urllib`, existing `stock_research` CLI and tech bottleneck evidence/readiness modules.

---

## File Structure

- Create `src/stock_research/official_disclosure_product_backfill.py`
  - Owns disclosure manifest normalization, official disclosure client, main-business join, PIT safety rules, artifact writing, and file/DB runner.
- Modify `src/stock_research/cli.py`
  - Adds `tech-bottleneck-official-disclosure-product-backfill`.
- Create `tests/test_official_disclosure_product_backfill.py`
  - Unit tests for title filtering, manifest normalization, PIT-safe evidence generation, artifact output, and HTTP client parsing with fake opener.
- Modify `docs/runbooks/tech_bottleneck_discovery.md`
  - Adds the official product backfill step before readiness rerun.
- Create `examples/tech_bottleneck_official_disclosure_manifest.csv`
  - Small fixture-style manifest for offline smoke runs.

---

### Task 1: Manifest Normalization And Product Evidence Builder

**Files:**
- Create: `src/stock_research/official_disclosure_product_backfill.py`
- Create: `tests/test_official_disclosure_product_backfill.py`

- [ ] **Step 1: Write failing tests for disclosure filtering and PIT-safe product evidence**

Add these tests to `tests/test_official_disclosure_product_backfill.py`:

```python
import pandas as pd

from stock_research.official_disclosure_product_backfill import (
    build_product_evidence_rows,
    is_supported_product_disclosure,
    normalize_disclosure_manifest,
)


def test_supported_product_disclosure_title_filter():
    assert is_supported_product_disclosure("2024年年度报告")
    assert is_supported_product_disclosure("2024年半年度报告")
    assert is_supported_product_disclosure("2024年年度报告（更正后）")
    assert not is_supported_product_disclosure("2024年年度报告摘要")
    assert not is_supported_product_disclosure("关于召开股东大会的公告")
    assert not is_supported_product_disclosure("Annual Report 2024")


def test_manifest_normalization_preserves_official_trace():
    rows = [
        {
            "asset_id": 1,
            "ts_code": "000001.SZ",
            "publish_date": "2025-04-25",
            "report_period": "2024-12-31",
            "announcement_title": "2024年年度报告",
            "source_document_id": "121999",
            "source_document_url": "http://example.com/report.pdf",
        }
    ]

    manifest = normalize_disclosure_manifest(rows)

    assert manifest.to_dict("records") == [
        {
            "asset_id": 1,
            "ts_code": "000001.SZ",
            "publish_date": pd.Timestamp("2025-04-25").date(),
            "report_period": pd.Timestamp("2024-12-31").date(),
            "announcement_title": "2024年年度报告",
            "source_document_id": "121999",
            "source_document_url": "http://example.com/report.pdf",
            "disclosure_type": "annual",
            "is_supported_product_disclosure": True,
        }
    ]


def test_product_evidence_requires_publish_date_visible_to_candidate():
    candidates = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "candidate_trade_date": "2025-05-09",
                "as_of_date": "2025-05-09",
            },
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "candidate_trade_date": "2025-04-18",
                "as_of_date": "2025-04-18",
            },
        ]
    )
    manifest = normalize_disclosure_manifest(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "publish_date": "2025-04-25",
                "report_period": "2024-12-31",
                "announcement_title": "2024年年度报告",
                "source_document_id": "121999",
                "source_document_url": "http://example.com/report.pdf",
            }
        ]
    )
    main_business = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "先进封装设备",
                "revenue": 123456789.0,
                "revenue_ratio": 42.5,
                "cost": 90000000.0,
                "gross_profit": 33456789.0,
                "gross_margin": 27.1,
                "source": "akshare.stock_zygc_em",
            }
        ]
    )

    evidence = build_product_evidence_rows(candidates, manifest, main_business)

    records = evidence.sort_values("as_of_date").to_dict("records")
    assert records[0]["as_of_safe"] is False
    assert records[0]["candidate_trade_date"] == pd.Timestamp("2025-04-18").date()
    assert records[1]["as_of_safe"] is True
    assert records[1]["candidate_trade_date"] == pd.Timestamp("2025-05-09").date()
    assert records[1]["evidence_type"] == "product_revenue_exposure"
    assert records[1]["source_confidence"] == "strong"
    assert records[1]["is_proxy"] is False
    assert records[1]["evidence_date"] == pd.Timestamp("2025-04-25").date()
    assert records[1]["metadata"]["item_name"] == "先进封装设备"
    assert records[1]["metadata"]["source_document_id"] == "121999"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_disclosure_product_backfill.py -q
```

Expected: import failure for `stock_research.official_disclosure_product_backfill`.

- [ ] **Step 3: Implement manifest normalization and evidence builder**

Create `src/stock_research/official_disclosure_product_backfill.py`:

```python
"""Official disclosure product revenue evidence backfill for tech bottleneck discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from stock_research.tech_bottleneck_evidence_backfill import normalize_evidence_rows

PRODUCT_DISCLOSURE_COLUMNS = [
    "asset_id",
    "ts_code",
    "publish_date",
    "report_period",
    "announcement_title",
    "source_document_id",
    "source_document_url",
    "disclosure_type",
    "is_supported_product_disclosure",
]


def _to_date(value: Any) -> date | None:
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def is_supported_product_disclosure(title: str | None) -> bool:
    text = str(title or "").strip()
    if not text:
        return False
    excluded = ("摘要", "英文", "取消", "社会责任", "环境", "问询", "回复")
    if any(token in text for token in excluded):
        return False
    return "年度报告" in text or "半年度报告" in text


def _infer_disclosure_type(title: str | None) -> str:
    text = str(title or "")
    if "半年度报告" in text:
        return "semiannual"
    if "年度报告" in text:
        return "annual"
    return "other"


def normalize_disclosure_manifest(rows: Iterable[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(rows).copy()
    if frame.empty:
        return pd.DataFrame(columns=PRODUCT_DISCLOSURE_COLUMNS)

    for column in ["asset_id", "ts_code", "publish_date", "report_period", "announcement_title"]:
        if column not in frame.columns:
            frame[column] = None

    frame["asset_id"] = pd.to_numeric(frame["asset_id"], errors="coerce").astype("Int64")
    frame["ts_code"] = frame["ts_code"].astype("string").str.strip()
    frame["publish_date"] = frame["publish_date"].map(_to_date)
    frame["report_period"] = frame["report_period"].map(_to_date)
    frame["announcement_title"] = frame["announcement_title"].astype("string").fillna("")
    frame["source_document_id"] = frame.get("source_document_id", "").astype("string").fillna("")
    frame["source_document_url"] = frame.get("source_document_url", "").astype("string").fillna("")
    frame["disclosure_type"] = frame["announcement_title"].map(_infer_disclosure_type)
    frame["is_supported_product_disclosure"] = frame["announcement_title"].map(is_supported_product_disclosure)
    frame = frame.dropna(subset=["asset_id", "ts_code", "publish_date", "report_period"])
    frame["asset_id"] = frame["asset_id"].astype(int)
    return frame[PRODUCT_DISCLOSURE_COLUMNS].sort_values(
        ["asset_id", "report_period", "publish_date", "source_document_id"]
    ).reset_index(drop=True)


def _normalize_candidate_dates(candidates: pd.DataFrame) -> pd.DataFrame:
    frame = candidates.copy()
    frame["asset_id"] = pd.to_numeric(frame["asset_id"], errors="coerce").astype("Int64")
    frame["ts_code"] = frame.get("ts_code", "").astype("string").str.strip()
    frame["candidate_trade_date"] = frame["candidate_trade_date"].map(_to_date)
    frame["as_of_date"] = frame["as_of_date"].map(_to_date)
    frame = frame.dropna(subset=["asset_id", "candidate_trade_date", "as_of_date"])
    frame["asset_id"] = frame["asset_id"].astype(int)
    return frame


def _normalize_main_business(main_business: pd.DataFrame) -> pd.DataFrame:
    frame = main_business.copy()
    if frame.empty:
        return frame
    frame["asset_id"] = pd.to_numeric(frame["asset_id"], errors="coerce").astype("Int64")
    frame["ts_code"] = frame.get("ts_code", "").astype("string").str.strip()
    frame["report_period"] = frame["report_period"].map(_to_date)
    frame["classify_type"] = frame.get("classify_type", "").astype("string").fillna("")
    frame["item_name"] = frame.get("item_name", "").astype("string").fillna("")
    frame = frame.dropna(subset=["asset_id", "report_period", "item_name"])
    frame["asset_id"] = frame["asset_id"].astype(int)
    return frame[frame["classify_type"].str.contains("产品", na=False)].copy()


def build_product_evidence_rows(
    candidates: pd.DataFrame,
    disclosure_manifest: pd.DataFrame,
    main_business: pd.DataFrame,
) -> pd.DataFrame:
    candidate_frame = _normalize_candidate_dates(candidates)
    manifest = normalize_disclosure_manifest(disclosure_manifest)
    product_rows = _normalize_main_business(main_business)
    if candidate_frame.empty or manifest.empty or product_rows.empty:
        return normalize_evidence_rows([])

    manifest = manifest[manifest["is_supported_product_disclosure"]].copy()
    joined = product_rows.merge(
        manifest,
        on=["asset_id", "ts_code", "report_period"],
        how="inner",
        suffixes=("", "_disclosure"),
    )
    joined = candidate_frame.merge(joined, on=["asset_id", "ts_code"], how="inner")

    evidence_rows: list[dict[str, Any]] = []
    for row in joined.to_dict("records"):
        publish_date = row["publish_date"]
        report_period = row["report_period"]
        as_of_date = row["as_of_date"]
        safe = publish_date <= as_of_date and report_period <= as_of_date
        metadata = {
            "report_period": report_period.isoformat(),
            "publish_date": publish_date.isoformat(),
            "classify_type": row.get("classify_type", ""),
            "item_name": row.get("item_name", ""),
            "revenue": row.get("revenue"),
            "revenue_ratio": row.get("revenue_ratio"),
            "cost": row.get("cost"),
            "gross_profit": row.get("gross_profit"),
            "gross_margin": row.get("gross_margin"),
            "source": row.get("source", ""),
            "source_document_id": row.get("source_document_id", ""),
            "source_document_url": row.get("source_document_url", ""),
            "extraction_method": "official_manifest_join_main_business_composition",
            "extraction_confidence": "strong",
        }
        evidence_rows.append(
            {
                "asset_id": row["asset_id"],
                "ts_code": row["ts_code"],
                "candidate_trade_date": row["candidate_trade_date"],
                "as_of_date": as_of_date,
                "evidence_type": "product_revenue_exposure",
                "evidence_date": publish_date,
                "source": "official_disclosure_product_backfill",
                "source_confidence": "strong",
                "is_proxy": False,
                "as_of_safe": bool(safe),
                "evidence_text": f"{row.get('announcement_title', '')} 产品收入: {row.get('item_name', '')}",
                "metadata": metadata,
            }
        )
    return normalize_evidence_rows(evidence_rows)
```

- [ ] **Step 4: Run Task 1 tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_disclosure_product_backfill.py -q
```

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/stock_research/official_disclosure_product_backfill.py tests/test_official_disclosure_product_backfill.py
git commit -m "feat: add official disclosure product evidence builder"
```

---

### Task 2: Official Disclosure Index Client

**Files:**
- Modify: `src/stock_research/official_disclosure_product_backfill.py`
- Modify: `tests/test_official_disclosure_product_backfill.py`

- [ ] **Step 1: Write failing tests for fake HTTP parsing**

Append this test:

```python
import json
from urllib.parse import parse_qs, urlparse

from stock_research.official_disclosure_product_backfill import CninfoDisclosureIndexClient


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def test_cninfo_client_parses_supported_announcements():
    requests = []

    def opener(request, timeout):
        requests.append(request)
        parsed = urlparse(request.full_url)
        body = parse_qs(request.data.decode("utf-8"))
        assert parsed.path.endswith("/new/hisAnnouncement/query")
        assert body["stock"] == ["000001,SZ"]
        return FakeResponse(
            {
                "announcements": [
                    {
                        "announcementTitle": "2024年年度报告",
                        "announcementTime": 1745510400000,
                        "announcementId": "121999",
                        "adjunctUrl": "finalpage/2025-04-25/121999.PDF",
                        "secCode": "000001",
                        "secName": "示例公司",
                    },
                    {
                        "announcementTitle": "2024年年度报告摘要",
                        "announcementTime": 1745510400000,
                        "announcementId": "122000",
                        "adjunctUrl": "finalpage/2025-04-25/122000.PDF",
                        "secCode": "000001",
                        "secName": "示例公司",
                    },
                ]
            }
        )

    client = CninfoDisclosureIndexClient(opener=opener)
    manifest = client.query_asset(
        asset_id=1,
        ts_code="000001.SZ",
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert len(requests) == 2
    assert manifest.to_dict("records") == [
        {
            "asset_id": 1,
            "ts_code": "000001.SZ",
            "publish_date": pd.Timestamp("2025-04-25").date(),
            "report_period": pd.Timestamp("2024-12-31").date(),
            "announcement_title": "2024年年度报告",
            "source_document_id": "121999",
            "source_document_url": "http://static.cninfo.com.cn/finalpage/2025-04-25/121999.PDF",
            "disclosure_type": "annual",
            "is_supported_product_disclosure": True,
        }
    ]
```

- [ ] **Step 2: Run test and verify it fails**

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_disclosure_product_backfill.py::test_cninfo_client_parses_supported_announcements -q
```

Expected: import failure for `CninfoDisclosureIndexClient`.

- [ ] **Step 3: Implement the client with stdlib urllib and deterministic filtering**

Add these imports and code to `src/stock_research/official_disclosure_product_backfill.py`:

```python
from datetime import datetime
from urllib import parse, request

CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_BASE_URL = "http://static.cninfo.com.cn/"
CNINFO_CATEGORIES = ("category_ndbg_szsh", "category_bndbg_szsh")


def _exchange_suffix(ts_code: str) -> str:
    code = str(ts_code).split(".")[0]
    suffix = str(ts_code).split(".")[-1].upper()
    if suffix in {"SH", "SSE"}:
        return code, "SH"
    return code, "SZ"


def _announcement_time_to_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000).date()
    except (TypeError, ValueError, OSError):
        return _to_date(value)


def _infer_report_period_from_title(title: str, publish_date: date) -> date | None:
    years = [int(token) for token in __import__("re").findall(r"(20\d{2})", title or "")]
    if not years:
        return None
    year = years[0]
    if "半年度报告" in title:
        return date(year, 6, 30)
    if "年度报告" in title:
        return date(year, 12, 31)
    return None


class CninfoDisclosureIndexClient:
    def __init__(self, opener=None, timeout_seconds: int = 20):
        self._opener = opener or request.urlopen
        self._timeout_seconds = timeout_seconds

    def query_asset(
        self,
        *,
        asset_id: int,
        ts_code: str,
        start_date: str | date,
        end_date: str | date,
    ) -> pd.DataFrame:
        code, exchange = _exchange_suffix(ts_code)
        rows: list[dict[str, Any]] = []
        for category in CNINFO_CATEGORIES:
            body = parse.urlencode(
                {
                    "stock": f"{code},{exchange}",
                    "tabName": "fulltext",
                    "pageSize": "30",
                    "pageNum": "1",
                    "column": "sse" if exchange == "SH" else "szse",
                    "category": category,
                    "plate": "",
                    "seDate": f"{_to_date(start_date).isoformat()}~{_to_date(end_date).isoformat()}",
                    "isHLtitle": "true",
                }
            ).encode("utf-8")
            req = request.Request(
                CNINFO_QUERY_URL,
                data=body,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
                },
                method="POST",
            )
            with self._opener(req, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            for item in payload.get("announcements", []) or []:
                title = item.get("announcementTitle", "")
                publish_date = _announcement_time_to_date(item.get("announcementTime"))
                report_period = _infer_report_period_from_title(title, publish_date) if publish_date else None
                if not publish_date or not report_period:
                    continue
                adjunct = str(item.get("adjunctUrl") or "")
                url = adjunct if adjunct.startswith("http") else CNINFO_STATIC_BASE_URL + adjunct.lstrip("/")
                rows.append(
                    {
                        "asset_id": asset_id,
                        "ts_code": ts_code,
                        "publish_date": publish_date,
                        "report_period": report_period,
                        "announcement_title": title,
                        "source_document_id": str(item.get("announcementId") or ""),
                        "source_document_url": url,
                    }
                )
        manifest = normalize_disclosure_manifest(rows)
        return manifest[manifest["is_supported_product_disclosure"]].drop_duplicates(
            ["asset_id", "ts_code", "report_period", "source_document_id"]
        ).reset_index(drop=True)
```

- [ ] **Step 4: Run Task 2 tests**

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_disclosure_product_backfill.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/stock_research/official_disclosure_product_backfill.py tests/test_official_disclosure_product_backfill.py
git commit -m "feat: add cninfo disclosure manifest client"
```

---

### Task 3: Runner, Artifacts, And Source Gap Report

**Files:**
- Modify: `src/stock_research/official_disclosure_product_backfill.py`
- Modify: `tests/test_official_disclosure_product_backfill.py`

- [ ] **Step 1: Write failing artifact runner test**

Append this test:

```python
from pathlib import Path

from stock_research.official_disclosure_product_backfill import (
    OfficialDisclosureProductBackfillResult,
    run_official_disclosure_product_backfill,
)


class FakeManifestClient:
    def query_asset(self, *, asset_id, ts_code, start_date, end_date):
        return normalize_disclosure_manifest(
            [
                {
                    "asset_id": asset_id,
                    "ts_code": ts_code,
                    "publish_date": "2025-04-25",
                    "report_period": "2024-12-31",
                    "announcement_title": "2024年年度报告",
                    "source_document_id": "121999",
                    "source_document_url": "http://example.com/report.pdf",
                }
            ]
        )


def test_runner_writes_product_backfill_artifacts(tmp_path: Path):
    candidates_csv = tmp_path / "candidates.csv"
    candidates_csv.write_text(
        "asset_id,ts_code,candidate_trade_date,as_of_date\n"
        "1,000001.SZ,2025-05-09,2025-05-09\n",
        encoding="utf-8",
    )
    main_business = pd.DataFrame(
        [
            {
                "asset_id": 1,
                "ts_code": "000001.SZ",
                "report_period": "2024-12-31",
                "classify_type": "按产品分类",
                "item_name": "先进封装设备",
                "revenue": 123456789.0,
                "revenue_ratio": 42.5,
                "source": "fixture",
            }
        ]
    )

    result = run_official_disclosure_product_backfill(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        run_id="unit",
        manifest_client=FakeManifestClient(),
        main_business_loader=lambda asset_ids, start, end: main_business,
        start_date="2025-01-01",
        end_date="2025-12-31",
    )

    assert isinstance(result, OfficialDisclosureProductBackfillResult)
    assert result.evidence_rows == 1
    assert result.safe_evidence_rows == 1
    assert (tmp_path / "out" / "product_evidence.csv").exists()
    assert (tmp_path / "out" / "disclosure_manifest.csv").exists()
    assert (tmp_path / "out" / "document_cache_index.csv").exists()
    assert (tmp_path / "out" / "coverage_summary.md").read_text(encoding="utf-8").startswith("# Official Disclosure Product Backfill")
    gaps = pd.read_csv(tmp_path / "out" / "source_gap_report.csv")
    assert gaps.loc[0, "assets_with_safe_product_evidence"] == 1
```

- [ ] **Step 2: Run test and verify it fails**

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_disclosure_product_backfill.py::test_runner_writes_product_backfill_artifacts -q
```

Expected: import failure for `run_official_disclosure_product_backfill`.

- [ ] **Step 3: Implement runner and artifact writing**

Append this code to `src/stock_research/official_disclosure_product_backfill.py`:

```python
@dataclass(frozen=True)
class OfficialDisclosureProductBackfillResult:
    output_dir: Path
    candidate_rows: int
    candidate_assets: int
    manifest_rows: int
    evidence_rows: int
    safe_evidence_rows: int
    assets_with_safe_product_evidence: int


def _load_main_business_from_db(asset_ids: list[int], start_date: date, end_date: date, conn) -> pd.DataFrame:
    if conn is None or not asset_ids:
        return pd.DataFrame()
    sql = """
        SELECT asset_id, ts_code, report_period, classify_type, item_name,
               revenue, revenue_ratio, cost, gross_profit, gross_margin, source
        FROM finance.main_business_composition
        WHERE asset_id = ANY(%s)
          AND report_period BETWEEN %s AND %s
          AND classify_type LIKE '%%产品%%'
    """
    return pd.read_sql(sql, conn, params=(asset_ids, start_date, end_date))


def _collect_manifest(candidates: pd.DataFrame, client: Any, start_date: date, end_date: date) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    assets = candidates[["asset_id", "ts_code"]].drop_duplicates().sort_values(["asset_id", "ts_code"])
    for row in assets.to_dict("records"):
        rows.append(
            client.query_asset(
                asset_id=int(row["asset_id"]),
                ts_code=str(row["ts_code"]),
                start_date=start_date,
                end_date=end_date,
            )
        )
    if not rows:
        return normalize_disclosure_manifest([])
    return normalize_disclosure_manifest(pd.concat(rows, ignore_index=True))


def _write_artifacts(
    *,
    output_dir: Path,
    run_id: str,
    candidates: pd.DataFrame,
    manifest: pd.DataFrame,
    evidence: pd.DataFrame,
) -> OfficialDisclosureProductBackfillResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence.to_csv(output_dir / "product_evidence.csv", index=False)
    manifest.to_csv(output_dir / "disclosure_manifest.csv", index=False)
    document_cache = manifest[["asset_id", "ts_code", "source_document_id", "source_document_url"]].drop_duplicates()
    document_cache.to_csv(output_dir / "document_cache_index.csv", index=False)
    safe = evidence[evidence["as_of_safe"] == True] if not evidence.empty else evidence
    gap = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "candidate_rows": len(candidates),
                "candidate_assets": candidates["asset_id"].nunique() if not candidates.empty else 0,
                "manifest_rows": len(manifest),
                "evidence_rows": len(evidence),
                "safe_evidence_rows": len(safe),
                "assets_with_safe_product_evidence": safe["asset_id"].nunique() if not safe.empty else 0,
                "assets_without_safe_product_evidence": (candidates["asset_id"].nunique() if not candidates.empty else 0)
                - (safe["asset_id"].nunique() if not safe.empty else 0),
            }
        ]
    )
    gap.to_csv(output_dir / "source_gap_report.csv", index=False)
    (output_dir / "coverage_summary.md").write_text(
        "\n".join(
            [
                "# Official Disclosure Product Backfill",
                "",
                f"- run_id: `{run_id}`",
                f"- candidate_rows: {len(candidates)}",
                f"- candidate_assets: {gap.loc[0, 'candidate_assets']}",
                f"- manifest_rows: {len(manifest)}",
                f"- evidence_rows: {len(evidence)}",
                f"- safe_evidence_rows: {len(safe)}",
                f"- assets_with_safe_product_evidence: {gap.loc[0, 'assets_with_safe_product_evidence']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return OfficialDisclosureProductBackfillResult(
        output_dir=output_dir,
        candidate_rows=len(candidates),
        candidate_assets=int(gap.loc[0, "candidate_assets"]),
        manifest_rows=len(manifest),
        evidence_rows=len(evidence),
        safe_evidence_rows=len(safe),
        assets_with_safe_product_evidence=int(gap.loc[0, "assets_with_safe_product_evidence"]),
    )


def run_official_disclosure_product_backfill(
    *,
    candidates_csv: str | Path,
    output_dir: str | Path,
    run_id: str,
    start_date: str | date,
    end_date: str | date,
    manifest_client: Any | None = None,
    main_business_loader: Any | None = None,
    conn: Any | None = None,
) -> OfficialDisclosureProductBackfillResult:
    candidates = _normalize_candidate_dates(pd.read_csv(candidates_csv))
    start = _to_date(start_date)
    end = _to_date(end_date)
    client = manifest_client or CninfoDisclosureIndexClient()
    manifest = _collect_manifest(candidates, client, start, end)
    asset_ids = candidates["asset_id"].dropna().astype(int).unique().tolist()
    loader = main_business_loader or (lambda ids, s, e: _load_main_business_from_db(ids, s, e, conn))
    main_business = loader(asset_ids, date(start.year - 2, 1, 1), end)
    evidence = build_product_evidence_rows(candidates, manifest, main_business)
    return _write_artifacts(
        output_dir=Path(output_dir),
        run_id=run_id,
        candidates=candidates,
        manifest=manifest,
        evidence=evidence,
    )
```

- [ ] **Step 4: Run Task 3 tests**

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_disclosure_product_backfill.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/stock_research/official_disclosure_product_backfill.py tests/test_official_disclosure_product_backfill.py
git commit -m "feat: write official product backfill artifacts"
```

---

### Task 4: CLI, Example Manifest, And Runbook

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `docs/runbooks/tech_bottleneck_discovery.md`
- Create: `examples/tech_bottleneck_official_disclosure_manifest.csv`
- Modify: `tests/test_official_disclosure_product_backfill.py`

- [ ] **Step 1: Add CLI parser smoke test**

Append this test:

```python
from stock_research.cli import build_parser


def test_cli_includes_official_disclosure_product_backfill_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "tech-bottleneck-official-disclosure-product-backfill",
            "--candidates-csv",
            "candidates.csv",
            "--output-dir",
            "out",
            "--run-id",
            "unit",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-12-31",
        ]
    )

    assert args.command == "tech-bottleneck-official-disclosure-product-backfill"
    assert args.candidates_csv == "candidates.csv"
    assert args.output_dir == "out"
    assert args.run_id == "unit"
```

- [ ] **Step 2: Run CLI test and verify it fails**

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_disclosure_product_backfill.py::test_cli_includes_official_disclosure_product_backfill_command -q
```

Expected: parser rejects the new command.

- [ ] **Step 3: Wire CLI command**

In `src/stock_research/cli.py`, import and dispatch:

```python
from stock_research.official_disclosure_product_backfill import run_official_disclosure_product_backfill
```

Add the parser:

```python
official_product = subparsers.add_parser(
    "tech-bottleneck-official-disclosure-product-backfill",
    help="Backfill strict PIT product revenue evidence from official disclosures.",
)
official_product.add_argument("--candidates-csv", required=True)
official_product.add_argument("--output-dir", required=True)
official_product.add_argument("--run-id", required=True)
official_product.add_argument("--start-date", required=True)
official_product.add_argument("--end-date", required=True)
official_product.set_defaults(command="tech-bottleneck-official-disclosure-product-backfill")
```

Add dispatch near other command branches:

```python
if args.command == "tech-bottleneck-official-disclosure-product-backfill":
    result = run_official_disclosure_product_backfill(
        candidates_csv=args.candidates_csv,
        output_dir=args.output_dir,
        run_id=args.run_id,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(
        json.dumps(
            {
                "output_dir": str(result.output_dir),
                "candidate_rows": result.candidate_rows,
                "candidate_assets": result.candidate_assets,
                "manifest_rows": result.manifest_rows,
                "evidence_rows": result.evidence_rows,
                "safe_evidence_rows": result.safe_evidence_rows,
                "assets_with_safe_product_evidence": result.assets_with_safe_product_evidence,
            },
            ensure_ascii=False,
        )
    )
    return 0
```

If `cli.py` already imports `json`, reuse it. Otherwise add `import json`.

- [ ] **Step 4: Add example manifest fixture**

Create `examples/tech_bottleneck_official_disclosure_manifest.csv`:

```csv
asset_id,ts_code,publish_date,report_period,announcement_title,source_document_id,source_document_url
1,000001.SZ,2025-04-25,2024-12-31,2024年年度报告,121999,http://static.cninfo.com.cn/finalpage/2025-04-25/121999.PDF
```

- [ ] **Step 5: Update runbook with execution sequence**

Add this section to `docs/runbooks/tech_bottleneck_discovery.md`:

````markdown
## Official Product Revenue Backfill

Run this before a formal `tech-bottleneck-data-readiness-audit` when `has_product_revenue_exposure` is low or zero.

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  tech-bottleneck-official-disclosure-product-backfill \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill \
  --run-id pilot-top50-2025-official-product-backfill \
  --start-date 2025-01-01 \
  --end-date 2025-12-31
```

Then rerun readiness using the generated evidence:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  tech-bottleneck-data-readiness-audit \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --evidence-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill/product_evidence.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness_after_official_product_backfill \
  --run-id pilot-top50-2025-readiness-after-official-product-backfill \
  --lookback-days 365 \
  --service stock_research
```
````

- [ ] **Step 6: Run focused tests**

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_disclosure_product_backfill.py tests/test_tech_bottleneck_readiness.py tests/test_tech_bottleneck_evidence_backfill.py -q
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/stock_research/cli.py docs/runbooks/tech_bottleneck_discovery.md examples/tech_bottleneck_official_disclosure_manifest.csv tests/test_official_disclosure_product_backfill.py
git commit -m "feat: expose official product backfill cli"
```

---

### Task 5: Pilot Smoke And Readiness Rerun

**Files:**
- Generated artifacts under `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill/`
- Generated artifacts under `outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness_after_official_product_backfill/`

- [ ] **Step 1: Run a small live smoke on the existing pilot candidates**

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  tech-bottleneck-official-disclosure-product-backfill \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill \
  --run-id pilot-top50-2025-official-product-backfill \
  --start-date 2025-01-01 \
  --end-date 2025-12-31
```

Expected: command exits 0 and writes `product_evidence.csv`, `disclosure_manifest.csv`, `coverage_summary.md`, and `source_gap_report.csv`. If the live disclosure source rejects requests, keep the generated gap report and report the source failure instead of fabricating product evidence.

- [ ] **Step 2: Rerun readiness with official product evidence**

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  tech-bottleneck-data-readiness-audit \
  --candidates-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/candidates.csv \
  --evidence-csv outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/official_product_backfill/product_evidence.csv \
  --output-dir outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness_after_official_product_backfill \
  --run-id pilot-top50-2025-readiness-after-official-product-backfill \
  --lookback-days 365 \
  --service stock_research
```

Expected: command exits 0 and `has_product_revenue_exposure` increases from the strict-PIT baseline of 0/1100 if official manifests and DB product rows overlap.

- [ ] **Step 3: Inspect readiness delta**

```bash
python - <<'PY'
import pandas as pd

before = pd.read_csv("outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness_strict_pit_after_existing_db_backfill/readiness_audit.csv")
after = pd.read_csv("outputs/tech_bottleneck_discovery/pilot_top50_2025_20_60_120_250/readiness_after_official_product_backfill/readiness_audit.csv")
for col in ["has_product_revenue_exposure", "has_research_report", "has_bottleneck_keywords", "has_capacity_evidence", "has_customer_certification_evidence", "has_patent_or_technical_barrier", "has_news_or_announcement_catalyst", "has_invalidation_evidence"]:
    print(col, int(before[col].sum()), "->", int(after[col].sum()), "/", len(after))
print(after["coverage_status"].value_counts(dropna=False).to_string())
PY
```

Expected: product exposure coverage is the primary changed metric; other flags should remain stable unless readiness evidence merging intentionally changes.

- [ ] **Step 4: Run focused verification**

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_official_disclosure_product_backfill.py tests/test_tech_bottleneck_readiness.py tests/test_tech_bottleneck_evidence_backfill.py -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit generated docs-only updates if needed**

Generated pilot outputs are research artifacts. Do not commit large generated CSVs unless this repo already tracks that output directory. If the runbook or example fixture changed during the smoke, commit those changes:

```bash
git status --short
git add docs/runbooks/tech_bottleneck_discovery.md examples/tech_bottleneck_official_disclosure_manifest.csv
git commit -m "docs: document official product backfill pilot"
```

---

## Self-Review

**Spec coverage:** This plan implements the approved design: candidate-scoped official disclosure manifest, annual/semiannual filtering, strict `publish_date <= as_of_date` and `report_period <= as_of_date` PIT safety, strong non-proxy `product_revenue_exposure` evidence, artifact outputs, source gap reporting, CLI integration, and readiness rerun.

**Placeholder scan:** The plan contains no unresolved placeholder markers, no open-ended "add tests" instructions, and no unnamed implementation slots. The only live-source uncertainty is handled by an explicit injectable client and measurable source-gap behavior.

**Type consistency:** The same function names and dataclasses are used throughout: `normalize_disclosure_manifest`, `build_product_evidence_rows`, `CninfoDisclosureIndexClient`, `run_official_disclosure_product_backfill`, and `OfficialDisclosureProductBackfillResult`.
