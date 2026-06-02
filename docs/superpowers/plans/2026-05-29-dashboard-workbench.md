# Dashboard Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only dashboard workbench that visualizes the existing stock research platform outputs with searchable assets, K-line charts, TopN, watchlist signals, risk tags, and report links.

**Architecture:** Add a thin dashboard layer on top of the existing PostgreSQL-backed research system. The Python backend exposes read-only dashboard DTOs and a FastAPI app; the frontend is a Vite/React workspace that consumes those APIs and renders Lightweight Charts without changing the factor, watchlist, backtest, or report generation pipelines.

**Tech Stack:** Python 3.11+, psycopg, pandas where already used, FastAPI, uvicorn, pytest, TypeScript, React, Vite, lightweight-charts, Vitest, Playwright.

---

## Scope

The first implementation is a read-only MVP:

- Search assets from `core.asset_master`.
- Show daily and minute OHLCV bars from `market_daily_bar` and `market.stock_minute_bar`.
- Show TopN rows from `factor.stock_score_daily`.
- Show watchlist signals from `watchlist.watchlist_daily_signal`.
- Show report artifact links from existing local report/run-card output directories.
- Render an operator workbench with one selected trade date, one selected asset, TopN list, watchlist list, chart, scoring panel, signal panel, and report panel.

Explicit non-goals:

- No automatic trading.
- No broker API.
- No TradingView private Charting Library dependency in MVP.
- No writes to factor, backtest, watchlist, or report tables.
- No new research signal logic.

## File Structure

Create backend package:

```text
src/stock_research/dashboard/
├── __init__.py
├── api.py
├── app.py
├── bars.py
├── overview.py
├── reports.py
├── schemas.py
├── scores.py
└── watchlist.py
```

Backend responsibilities:

- `schemas.py`: small dataclasses for API DTOs; no database access.
- `bars.py`: read daily/minute bars and normalize chart payloads.
- `scores.py`: asset search, asset detail, TopN, selected asset score.
- `watchlist.py`: watchlist signal read models.
- `reports.py`: report artifact index.
- `overview.py`: one-page aggregate read model.
- `app.py`: FastAPI app and route definitions.
- `api.py`: CLI runner for local dashboard API.

Create frontend workspace:

```text
dashboard/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── styles.css
│   ├── api/client.ts
│   ├── api/types.ts
│   ├── charts/AssetChart.tsx
│   ├── charts/chartData.ts
│   ├── components/ReportPanel.tsx
│   ├── components/ScorePanel.tsx
│   ├── components/TopNList.tsx
│   └── components/WatchlistList.tsx
└── tests/
    ├── chartData.test.ts
    └── app-smoke.spec.ts
```

Testing files:

```text
tests/test_dashboard_bars.py
tests/test_dashboard_scores.py
tests/test_dashboard_watchlist.py
tests/test_dashboard_reports.py
tests/test_dashboard_app.py
```

---

### Task 1: Add Dashboard Backend Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add a dashboard optional dependency group**

Modify `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
  "pytest",
]
dashboard = [
  "fastapi",
  "uvicorn",
]
```

Keep the existing `dev` group unchanged and add only the `dashboard` group.

- [ ] **Step 2: Validate package metadata**

Run:

```bash
python -m pip install -e ".[dashboard,dev]"
```

Expected: package installs successfully. If network access is unavailable in the execution environment, record the failure and continue with tests that do not import FastAPI until dependencies are installed.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add dashboard backend dependencies"
```

---

### Task 2: Define Dashboard DTO Schemas

**Files:**
- Create: `src/stock_research/dashboard/__init__.py`
- Create: `src/stock_research/dashboard/schemas.py`
- Test: `tests/test_dashboard_schemas.py`

- [ ] **Step 1: Write schema tests**

Create `tests/test_dashboard_schemas.py`:

```python
from stock_research.dashboard.schemas import BarPoint, ScoreRow, WatchlistSignalRow


def test_bar_point_to_dict_uses_chart_time_key():
    point = BarPoint(
        time="2026-05-29",
        open=10.0,
        high=11.0,
        low=9.5,
        close=10.5,
        volume=123000.0,
        amount=456000.0,
    )

    assert point.to_dict() == {
        "time": "2026-05-29",
        "open": 10.0,
        "high": 11.0,
        "low": 9.5,
        "close": 10.5,
        "volume": 123000.0,
        "amount": 456000.0,
    }


def test_score_row_preserves_components():
    row = ScoreRow(
        trade_date="2026-05-29",
        asset_id="000001.SZ",
        rank=3,
        score_total=88.5,
        score_version="manual_v1",
        score_components={"momentum": 90},
    )

    assert row.to_dict()["score_components"] == {"momentum": 90}


def test_watchlist_signal_row_preserves_tags():
    row = WatchlistSignalRow(
        watchlist_id="default",
        trade_date="2026-05-29",
        asset_id="000001.SZ",
        stock_code="000001",
        stock_name="平安银行",
        priority=10,
        signal_score=75.0,
        primary_signal="observe",
        signal_tags=["trend_ok"],
        risk_tags=["high_volatility"],
        must_watch=True,
        reason_json={"reason": "score"},
    )

    assert row.to_dict()["must_watch"] is True
    assert row.to_dict()["risk_tags"] == ["high_volatility"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_schemas.py -q
```

Expected: FAIL because `stock_research.dashboard.schemas` does not exist.

- [ ] **Step 3: Implement schemas**

Create `src/stock_research/dashboard/__init__.py`:

```python
"""Read-only dashboard adapters for the stock research platform."""
```

Create `src/stock_research/dashboard/schemas.py`:

```python
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AssetSummary:
    asset_id: str
    symbol: str
    name: str
    exchange: str
    board: str | None
    is_active: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BarPoint:
    time: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    amount: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScoreRow:
    trade_date: str
    asset_id: str
    rank: int
    score_total: float
    score_version: str
    score_components: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WatchlistSignalRow:
    watchlist_id: str
    trade_date: str
    asset_id: str
    stock_code: str
    stock_name: str
    priority: int
    signal_score: float | None
    primary_signal: str
    signal_tags: list[str]
    risk_tags: list[str]
    must_watch: bool
    reason_json: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReportLink:
    report_type: str
    title: str
    path: str
    format: str
    trade_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

- [ ] **Step 4: Run schema tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_schemas.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/__init__.py src/stock_research/dashboard/schemas.py tests/test_dashboard_schemas.py
git commit -m "feat: add dashboard DTO schemas"
```

---

### Task 3: Add Asset Search and Score Read Models

**Files:**
- Create: `src/stock_research/dashboard/scores.py`
- Test: `tests/test_dashboard_scores.py`

- [ ] **Step 1: Write tests with monkeypatched database access**

Create `tests/test_dashboard_scores.py`:

```python
from stock_research.dashboard import scores


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_search_assets_limits_and_maps_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "asset_id": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "exchange": "SZ",
                "board": "main",
                "is_active": True,
            }
        ]

    monkeypatch.setattr(scores, "connect", fake_connect)
    monkeypatch.setattr(scores, "fetch_all", fake_fetch_all)

    result = scores.search_assets("平安", limit=5, service="stock_research")

    assert captured["params"] == ["%平安%", "%平安%", "%平安%", 5]
    assert result == [
        {
            "asset_id": "000001.SZ",
            "symbol": "000001",
            "name": "平安银行",
            "exchange": "SZ",
            "board": "main",
            "is_active": True,
        }
    ]


def test_load_top_scores_returns_ranked_rows(monkeypatch):
    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        return [
            {
                "trade_date": "2026-05-29",
                "asset_id": "000001.SZ",
                "rank": 1,
                "score_total": 91.2,
                "score_version": "manual_v1",
                "score_components": {"trend": 88},
            }
        ]

    monkeypatch.setattr(scores, "connect", fake_connect)
    monkeypatch.setattr(scores, "fetch_all", fake_fetch_all)

    result = scores.load_top_scores_for_dashboard("2026-05-29", "manual_v1", 20)

    assert result[0]["asset_id"] == "000001.SZ"
    assert result[0]["score_total"] == 91.2
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_scores.py -q
```

Expected: FAIL because `stock_research.dashboard.scores` does not exist.

- [ ] **Step 3: Implement score read models**

Create `src/stock_research/dashboard/scores.py`:

```python
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import AssetSummary, ScoreRow
from stock_research.db import connect, fetch_all


def search_assets(
    query: str,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    term = f"%{query.strip()}%"
    sql = """
    SELECT asset_id, symbol, name, exchange, board, is_active
    FROM core.asset_master
    WHERE asset_id ILIKE %s
       OR symbol ILIKE %s
       OR name ILIKE %s
    ORDER BY is_active DESC, asset_id
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [term, term, term, limit])
    return [
        AssetSummary(
            asset_id=str(row["asset_id"]),
            symbol=str(row["symbol"]),
            name=str(row["name"]),
            exchange=str(row["exchange"]),
            board=row.get("board"),
            is_active=bool(row["is_active"]),
        ).to_dict()
        for row in rows
    ]


def load_asset_detail(
    asset_id: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT asset_id, symbol, name, exchange, board, is_active
    FROM core.asset_master
    WHERE asset_id = %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id])
    if not rows:
        return None
    row = rows[0]
    return AssetSummary(
        asset_id=str(row["asset_id"]),
        symbol=str(row["symbol"]),
        name=str(row["name"]),
        exchange=str(row["exchange"]),
        board=row.get("board"),
        is_active=bool(row["is_active"]),
    ).to_dict()


def load_top_scores_for_dashboard(
    trade_date: str,
    score_version: str,
    top_n: int,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT trade_date, asset_id, rank, score_total, score_version, score_components
    FROM factor.stock_score_daily
    WHERE trade_date = %s
      AND score_version = %s
    ORDER BY rank, asset_id
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, score_version, top_n])
    return [_score_row(row).to_dict() for row in rows]


def load_asset_score_for_dashboard(
    asset_id: str,
    trade_date: str,
    score_version: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT trade_date, asset_id, rank, score_total, score_version, score_components
    FROM factor.stock_score_daily
    WHERE asset_id = %s
      AND trade_date = %s
      AND score_version = %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id, trade_date, score_version])
    if not rows:
        return None
    return _score_row(rows[0]).to_dict()


def _score_row(row: dict[str, Any]) -> ScoreRow:
    return ScoreRow(
        trade_date=str(row["trade_date"]),
        asset_id=str(row["asset_id"]),
        rank=int(row["rank"]),
        score_total=float(row["score_total"]),
        score_version=str(row["score_version"]),
        score_components=dict(row.get("score_components") or {}),
    )
```

- [ ] **Step 4: Run score tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_scores.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/scores.py tests/test_dashboard_scores.py
git commit -m "feat: add dashboard score read models"
```

---

### Task 4: Add Bar Read Models

**Files:**
- Create: `src/stock_research/dashboard/bars.py`
- Test: `tests/test_dashboard_bars.py`

- [ ] **Step 1: Write bar read model tests**

Create `tests/test_dashboard_bars.py`:

```python
from stock_research.dashboard import bars


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_daily_bars_uses_market_daily_bar(monkeypatch):
    captured = {}

    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "time": "2026-05-29",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 1000,
                "amount": 2000,
            }
        ]

    monkeypatch.setattr(bars, "connect", fake_connect)
    monkeypatch.setattr(bars, "fetch_all", fake_fetch_all)

    result = bars.load_daily_bars("000001.SZ", "2026-01-01", "2026-05-29", "qfq")

    assert "FROM market_daily_bar" in captured["sql"]
    assert captured["params"] == ["000001.SZ", "2026-01-01", "2026-05-29", "qfq"]
    assert result[0]["time"] == "2026-05-29"


def test_load_minute_bars_uses_partitioned_minute_table(monkeypatch):
    captured = {}

    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(bars, "connect", fake_connect)
    monkeypatch.setattr(bars, "fetch_all", fake_fetch_all)

    result = bars.load_minute_bars(
        asset_id="000001.SZ",
        start_time="2026-05-29T09:30:00",
        end_time="2026-05-29T15:00:00",
        freq="5min",
        adjust_type="qfq",
    )

    assert "FROM market.stock_minute_bar" in captured["sql"]
    assert captured["params"] == [
        "000001.SZ",
        "2026-05-29T09:30:00",
        "2026-05-29T15:00:00",
        "5min",
        "qfq",
    ]
    assert result == []
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_bars.py -q
```

Expected: FAIL because `stock_research.dashboard.bars` does not exist.

- [ ] **Step 3: Implement bar read models**

Create `src/stock_research/dashboard/bars.py`:

```python
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import BarPoint
from stock_research.db import connect, fetch_all


def load_daily_bars(
    asset_id: str,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT
        trade_date::text AS time,
        open,
        high,
        low,
        close,
        volume,
        amount
    FROM market_daily_bar
    WHERE asset_id = %s
      AND trade_date BETWEEN %s AND %s
      AND adjust_type = %s
    ORDER BY trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id, start_date, end_date, adjust_type])
    return [_bar_point(row).to_dict() for row in rows]


def load_minute_bars(
    asset_id: str,
    start_time: str,
    end_time: str,
    freq: str = "5min",
    adjust_type: str = "qfq",
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT
        trade_time::text AS time,
        open,
        high,
        low,
        close,
        volume,
        amount
    FROM market.stock_minute_bar
    WHERE asset_id = %s
      AND trade_time BETWEEN %s AND %s
      AND freq = %s
      AND adjust_type = %s
    ORDER BY trade_time
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id, start_time, end_time, freq, adjust_type])
    return [_bar_point(row).to_dict() for row in rows]


def _bar_point(row: dict[str, Any]) -> BarPoint:
    return BarPoint(
        time=str(row["time"]),
        open=_float_or_none(row.get("open")),
        high=_float_or_none(row.get("high")),
        low=_float_or_none(row.get("low")),
        close=_float_or_none(row.get("close")),
        volume=_float_or_none(row.get("volume")),
        amount=_float_or_none(row.get("amount")),
    )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
```

- [ ] **Step 4: Run bar tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_bars.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/bars.py tests/test_dashboard_bars.py
git commit -m "feat: add dashboard bar read models"
```

---

### Task 5: Add Watchlist Signal Read Models

**Files:**
- Create: `src/stock_research/dashboard/watchlist.py`
- Test: `tests/test_dashboard_watchlist.py`

- [ ] **Step 1: Write watchlist tests**

Create `tests/test_dashboard_watchlist.py`:

```python
from stock_research.dashboard import watchlist


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_watchlist_signals_maps_json_tags(monkeypatch):
    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        return [
            {
                "watchlist_id": "default",
                "trade_date": "2026-05-29",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "平安银行",
                "priority": 10,
                "signal_score": 81.5,
                "primary_signal": "observe",
                "signal_tags": ["trend_ok"],
                "risk_tags": ["overheated"],
                "must_watch": True,
                "reason_json": {"score": 81.5},
            }
        ]

    monkeypatch.setattr(watchlist, "connect", fake_connect)
    monkeypatch.setattr(watchlist, "fetch_all", fake_fetch_all)

    result = watchlist.load_watchlist_signals_for_dashboard("default", "2026-05-29")

    assert result[0]["asset_id"] == "000001.SZ"
    assert result[0]["signal_tags"] == ["trend_ok"]
    assert result[0]["must_watch"] is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_watchlist.py -q
```

Expected: FAIL because `stock_research.dashboard.watchlist` does not exist.

- [ ] **Step 3: Implement watchlist read model**

Create `src/stock_research/dashboard/watchlist.py`:

```python
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import WatchlistSignalRow
from stock_research.db import connect, fetch_all


def load_watchlist_signals_for_dashboard(
    watchlist_id: str,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT
        watchlist_id,
        trade_date,
        asset_id,
        stock_code,
        stock_name,
        priority,
        signal_score,
        primary_signal,
        signal_tags,
        risk_tags,
        must_watch,
        reason_json
    FROM watchlist.watchlist_daily_signal
    WHERE watchlist_id = %s
      AND trade_date = %s
    ORDER BY must_watch DESC, priority ASC, signal_score DESC NULLS LAST, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [watchlist_id, trade_date])
    return [_signal_row(row).to_dict() for row in rows]


def load_asset_watchlist_signals_for_dashboard(
    asset_id: str,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT
        watchlist_id,
        trade_date,
        asset_id,
        stock_code,
        stock_name,
        priority,
        signal_score,
        primary_signal,
        signal_tags,
        risk_tags,
        must_watch,
        reason_json
    FROM watchlist.watchlist_daily_signal
    WHERE asset_id = %s
      AND trade_date = %s
    ORDER BY must_watch DESC, priority ASC, signal_score DESC NULLS LAST, watchlist_id
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id, trade_date])
    return [_signal_row(row).to_dict() for row in rows]


def _signal_row(row: dict[str, Any]) -> WatchlistSignalRow:
    return WatchlistSignalRow(
        watchlist_id=str(row["watchlist_id"]),
        trade_date=str(row["trade_date"]),
        asset_id=str(row["asset_id"]),
        stock_code=str(row["stock_code"]),
        stock_name=str(row["stock_name"]),
        priority=int(row["priority"]),
        signal_score=_float_or_none(row.get("signal_score")),
        primary_signal=str(row["primary_signal"]),
        signal_tags=list(row.get("signal_tags") or []),
        risk_tags=list(row.get("risk_tags") or []),
        must_watch=bool(row["must_watch"]),
        reason_json=dict(row.get("reason_json") or {}),
    )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
```

- [ ] **Step 4: Run watchlist tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_watchlist.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/watchlist.py tests/test_dashboard_watchlist.py
git commit -m "feat: add dashboard watchlist read models"
```

---

### Task 6: Add Report Link Index

**Files:**
- Create: `src/stock_research/dashboard/reports.py`
- Test: `tests/test_dashboard_reports.py`

- [ ] **Step 1: Write report index tests**

Create `tests/test_dashboard_reports.py`:

```python
from pathlib import Path

from stock_research.dashboard.reports import load_report_links


def test_load_report_links_finds_trade_date_files(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "daily_topn_2026-05-29_manual_v1.md").write_text("# topn", encoding="utf-8")
    (reports_dir / "watchlist_report_2026-05-29.md").write_text("# watchlist", encoding="utf-8")
    (reports_dir / "old_2026-05-28.md").write_text("# old", encoding="utf-8")

    result = load_report_links("2026-05-29", reports_dirs=[reports_dir])

    paths = [row["path"] for row in result]
    assert str(reports_dir / "daily_topn_2026-05-29_manual_v1.md") in paths
    assert str(reports_dir / "watchlist_report_2026-05-29.md") in paths
    assert str(reports_dir / "old_2026-05-28.md") not in paths
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_reports.py -q
```

Expected: FAIL because `stock_research.dashboard.reports` does not exist.

- [ ] **Step 3: Implement file-based report link index**

Create `src/stock_research/dashboard/reports.py`:

```python
from pathlib import Path
from typing import Any

from stock_research.dashboard.schemas import ReportLink


DEFAULT_REPORTS_DIR = Path("/Users/xiwei/stock_research/reports")


def load_report_links(
    trade_date: str,
    reports_dirs: list[str | Path] | None = None,
) -> list[dict[str, Any]]:
    dirs = [Path(path) for path in (reports_dirs or [DEFAULT_REPORTS_DIR])]
    links: list[ReportLink] = []
    for directory in dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.glob(f"*{trade_date}*")):
            if path.suffix.lower() not in {".md", ".csv", ".json", ".html"}:
                continue
            links.append(
                ReportLink(
                    report_type=_report_type(path.name),
                    title=path.name,
                    path=str(path),
                    format=path.suffix.lower().lstrip("."),
                    trade_date=trade_date,
                )
            )
    return [link.to_dict() for link in links]


def _report_type(filename: str) -> str:
    lowered = filename.lower()
    if "watchlist" in lowered:
        return "watchlist_report"
    if "topn" in lowered or "top20" in lowered:
        return "daily_topn_report"
    if "risk" in lowered:
        return "risk_report"
    if "portfolio" in lowered or "retention" in lowered:
        return "simulation_report"
    return "generic_report"
```

- [ ] **Step 4: Run report tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_reports.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/reports.py tests/test_dashboard_reports.py
git commit -m "feat: add dashboard report link index"
```

---

### Task 7: Add Overview Aggregator

**Files:**
- Create: `src/stock_research/dashboard/overview.py`
- Test: `tests/test_dashboard_overview.py`

- [ ] **Step 1: Write overview tests**

Create `tests/test_dashboard_overview.py`:

```python
from stock_research.dashboard import overview


def test_build_dashboard_overview_combines_read_models(monkeypatch):
    monkeypatch.setattr(
        overview,
        "load_top_scores_for_dashboard",
        lambda trade_date, score_version, top_n: [{"asset_id": "000001.SZ"}],
    )
    monkeypatch.setattr(
        overview,
        "load_watchlist_signals_for_dashboard",
        lambda watchlist_id, trade_date: [{"asset_id": "000002.SZ"}],
    )
    monkeypatch.setattr(
        overview,
        "load_report_links",
        lambda trade_date: [{"title": "daily_topn_2026-05-29.md"}],
    )

    result = overview.build_dashboard_overview(
        trade_date="2026-05-29",
        score_version="manual_v1",
        watchlist_id="default",
        top_n=20,
    )

    assert result["trade_date"] == "2026-05-29"
    assert result["top_scores"] == [{"asset_id": "000001.SZ"}]
    assert result["watchlist_signals"] == [{"asset_id": "000002.SZ"}]
    assert result["reports"] == [{"title": "daily_topn_2026-05-29.md"}]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_overview.py -q
```

Expected: FAIL because `stock_research.dashboard.overview` does not exist.

- [ ] **Step 3: Implement overview aggregator**

Create `src/stock_research/dashboard/overview.py`:

```python
from typing import Any

from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.scores import load_top_scores_for_dashboard
from stock_research.dashboard.watchlist import load_watchlist_signals_for_dashboard


def build_dashboard_overview(
    trade_date: str,
    score_version: str = "manual_v1",
    watchlist_id: str = "default",
    top_n: int = 30,
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "score_version": score_version,
        "watchlist_id": watchlist_id,
        "top_scores": load_top_scores_for_dashboard(trade_date, score_version, top_n),
        "watchlist_signals": load_watchlist_signals_for_dashboard(watchlist_id, trade_date),
        "reports": load_report_links(trade_date),
    }
```

- [ ] **Step 4: Run overview tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_overview.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/overview.py tests/test_dashboard_overview.py
git commit -m "feat: add dashboard overview read model"
```

---

### Task 8: Add FastAPI Routes

**Files:**
- Create: `src/stock_research/dashboard/app.py`
- Create: `src/stock_research/dashboard/api.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_dashboard_app.py`

- [ ] **Step 1: Write FastAPI route tests**

Create `tests/test_dashboard_app.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def test_overview_route_returns_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_dashboard_overview",
        lambda trade_date, score_version, watchlist_id, top_n: {
            "trade_date": trade_date,
            "score_version": score_version,
            "watchlist_id": watchlist_id,
            "top_scores": [],
            "watchlist_signals": [],
            "reports": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/dashboard/overview?trade_date=2026-05-29")

    assert response.status_code == 200
    assert response.json()["trade_date"] == "2026-05-29"


def test_asset_detail_route_returns_404_for_missing_asset(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_asset_detail", lambda asset_id: None)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/assets/000001.SZ")

    assert response.status_code == 404
    assert response.json()["detail"] == "asset not found"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_app.py -q
```

Expected: FAIL because `stock_research.dashboard.app` does not exist or FastAPI is not installed.

- [ ] **Step 3: Implement FastAPI app**

Create `src/stock_research/dashboard/app.py`:

```python
from fastapi import FastAPI, HTTPException

from stock_research.dashboard.bars import load_daily_bars, load_minute_bars
from stock_research.dashboard.overview import build_dashboard_overview
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.scores import (
    load_asset_detail,
    load_asset_score_for_dashboard,
    load_top_scores_for_dashboard,
    search_assets,
)
from stock_research.dashboard.watchlist import (
    load_asset_watchlist_signals_for_dashboard,
    load_watchlist_signals_for_dashboard,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Research Dashboard API")

    @app.get("/api/dashboard/overview")
    def dashboard_overview(
        trade_date: str,
        score_version: str = "manual_v1",
        watchlist_id: str = "default",
        top_n: int = 30,
    ):
        return build_dashboard_overview(trade_date, score_version, watchlist_id, top_n)

    @app.get("/api/assets/search")
    def assets_search(q: str, limit: int = 20):
        return {"items": search_assets(q, limit)}

    @app.get("/api/assets/{asset_id}")
    def asset_detail(asset_id: str):
        asset = load_asset_detail(asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset not found")
        return asset

    @app.get("/api/assets/{asset_id}/bars")
    def asset_daily_bars(
        asset_id: str,
        start_date: str,
        end_date: str,
        adjust_type: str = "qfq",
    ):
        return {
            "asset_id": asset_id,
            "resolution": "1D",
            "items": load_daily_bars(asset_id, start_date, end_date, adjust_type),
        }

    @app.get("/api/assets/{asset_id}/minute-bars")
    def asset_minute_bars(
        asset_id: str,
        start_time: str,
        end_time: str,
        freq: str = "5min",
        adjust_type: str = "qfq",
    ):
        return {
            "asset_id": asset_id,
            "resolution": freq,
            "items": load_minute_bars(asset_id, start_time, end_time, freq, adjust_type),
        }

    @app.get("/api/assets/{asset_id}/scores")
    def asset_score(asset_id: str, trade_date: str, score_version: str = "manual_v1"):
        return {
            "asset_id": asset_id,
            "item": load_asset_score_for_dashboard(asset_id, trade_date, score_version),
        }

    @app.get("/api/assets/{asset_id}/signals")
    def asset_signals(asset_id: str, trade_date: str):
        return {
            "asset_id": asset_id,
            "items": load_asset_watchlist_signals_for_dashboard(asset_id, trade_date),
        }

    @app.get("/api/topn")
    def topn(trade_date: str, score_version: str = "manual_v1", top_n: int = 30):
        return {
            "trade_date": trade_date,
            "score_version": score_version,
            "items": load_top_scores_for_dashboard(trade_date, score_version, top_n),
        }

    @app.get("/api/watchlists/{watchlist_id}")
    def watchlist_signals(watchlist_id: str, trade_date: str):
        return {
            "watchlist_id": watchlist_id,
            "trade_date": trade_date,
            "items": load_watchlist_signals_for_dashboard(watchlist_id, trade_date),
        }

    @app.get("/api/reports")
    def reports(trade_date: str):
        return {"trade_date": trade_date, "items": load_report_links(trade_date)}

    return app


app = create_app()
```

Create `src/stock_research/dashboard/api.py`:

```python
def run_dashboard_api(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    uvicorn.run("stock_research.dashboard.app:app", host=host, port=port, reload=False)
```

- [ ] **Step 4: Add CLI command**

Modify `src/stock_research/cli.py`:

Add import near the other imports:

```python
from stock_research.dashboard.api import run_dashboard_api
```

Add parser near other operational commands:

```python
    dashboard_api = subparsers.add_parser("dashboard-api")
    dashboard_api.add_argument("--host", default="127.0.0.1")
    dashboard_api.add_argument("--port", type=int, default=8765)
```

Add command handling in the existing command dispatch:

```python
    if args.command == "dashboard-api":
        run_dashboard_api(host=args.host, port=args.port)
        return
```

- [ ] **Step 5: Run backend route tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_app.py -q
```

Expected: PASS.

- [ ] **Step 6: Run focused backend suite**

Run:

```bash
.venv/bin/pytest \
  tests/test_dashboard_schemas.py \
  tests/test_dashboard_scores.py \
  tests/test_dashboard_bars.py \
  tests/test_dashboard_watchlist.py \
  tests/test_dashboard_reports.py \
  tests/test_dashboard_overview.py \
  tests/test_dashboard_app.py \
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/dashboard/app.py src/stock_research/dashboard/api.py src/stock_research/cli.py tests/test_dashboard_app.py
git commit -m "feat: add dashboard API routes"
```

---

### Task 9: Scaffold Frontend Workspace

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/vite.config.ts`
- Create: `dashboard/index.html`
- Create: `dashboard/src/main.tsx`
- Create: `dashboard/src/App.tsx`
- Create: `dashboard/src/styles.css`

- [ ] **Step 1: Create package file**

Create `dashboard/package.json`:

```json
{
  "name": "stock-research-dashboard",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 127.0.0.1 --port 5174",
    "build": "tsc && vite build",
    "test": "vitest run",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^5.0.0",
    "vite": "^7.0.0",
    "typescript": "^5.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "lightweight-charts": "^5.0.0",
    "lucide-react": "^0.468.0"
  },
  "devDependencies": {
    "@playwright/test": "^1.50.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "vitest": "^3.0.0",
    "jsdom": "^25.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0"
  }
}
```

- [ ] **Step 2: Create TypeScript and Vite config**

Create `dashboard/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src", "tests", "vite.config.ts"]
}
```

Create `dashboard/vite.config.ts`:

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    proxy: {
      '/api': 'http://127.0.0.1:8765'
    }
  },
  test: {
    environment: 'jsdom'
  }
});
```

- [ ] **Step 3: Create app shell**

Create `dashboard/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Stock Research Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `dashboard/src/main.tsx`:

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

Create `dashboard/src/App.tsx`:

```typescript
export function App() {
  return (
    <main className="workbench">
      <aside className="sidebar">
        <div className="panel-title">Stock Research</div>
      </aside>
      <section className="workspace">
        <header className="toolbar">
          <input type="date" defaultValue="2026-05-29" aria-label="trade date" />
          <input defaultValue="000001.SZ" aria-label="asset id" />
        </header>
        <section className="chart-panel">Chart loading area</section>
      </section>
      <aside className="inspector">
        <div className="panel-title">Review</div>
      </aside>
    </main>
  );
}
```

Create `dashboard/src/styles.css`:

```css
:root {
  color: #18202a;
  background: #f4f6f8;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
}

.workbench {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr) minmax(260px, 340px);
  min-height: 100vh;
}

.sidebar,
.inspector {
  background: #ffffff;
  border-right: 1px solid #d9dee7;
  padding: 16px;
}

.inspector {
  border-right: 0;
  border-left: 1px solid #d9dee7;
}

.workspace {
  min-width: 0;
  display: grid;
  grid-template-rows: auto 1fr;
}

.toolbar {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid #d9dee7;
  background: #ffffff;
}

.toolbar input {
  height: 32px;
  border: 1px solid #c4cbd6;
  border-radius: 6px;
  padding: 0 8px;
}

.chart-panel {
  min-height: 420px;
  padding: 12px;
}

.panel-title {
  font-size: 13px;
  font-weight: 700;
}

@media (max-width: 900px) {
  .workbench {
    grid-template-columns: 1fr;
  }

  .sidebar,
  .inspector {
    border: 0;
    border-bottom: 1px solid #d9dee7;
  }
}
```

- [ ] **Step 4: Install frontend dependencies**

Run:

```bash
cd dashboard
pnpm install
```

Expected: dependencies install and `pnpm-lock.yaml` is created or updated. If the repo standardizes on another package manager before implementation, use that one consistently and update this plan step in the implementation branch.

- [ ] **Step 5: Build frontend**

Run:

```bash
cd dashboard
pnpm build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard pnpm-lock.yaml
git commit -m "feat: scaffold dashboard frontend"
```

If `pnpm-lock.yaml` is created inside `dashboard/`, use:

```bash
git add dashboard
git commit -m "feat: scaffold dashboard frontend"
```

---

### Task 10: Add Frontend API Client and Types

**Files:**
- Create: `dashboard/src/api/types.ts`
- Create: `dashboard/src/api/client.ts`
- Test: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write API client test**

Create `dashboard/tests/client.test.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest';
import { fetchOverview } from '../src/api/client';

describe('dashboard API client', () => {
  it('fetches overview with query params', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ trade_date: '2026-05-29', top_scores: [], watchlist_signals: [], reports: [] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchOverview({
      tradeDate: '2026-05-29',
      scoreVersion: 'manual_v1',
      watchlistId: 'default',
      topN: 20
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/dashboard/overview?trade_date=2026-05-29&score_version=manual_v1&watchlist_id=default&top_n=20'
    );
    expect(result.trade_date).toBe('2026-05-29');
  });
});
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd dashboard
pnpm test -- client.test.ts
```

Expected: FAIL because `src/api/client.ts` does not exist.

- [ ] **Step 3: Add types**

Create `dashboard/src/api/types.ts`:

```typescript
export type AssetSummary = {
  asset_id: string;
  symbol: string;
  name: string;
  exchange: string;
  board: string | null;
  is_active: boolean;
};

export type BarPoint = {
  time: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  amount: number | null;
};

export type ScoreRow = {
  trade_date: string;
  asset_id: string;
  rank: number;
  score_total: number;
  score_version: string;
  score_components: Record<string, unknown>;
};

export type WatchlistSignalRow = {
  watchlist_id: string;
  trade_date: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  priority: number;
  signal_score: number | null;
  primary_signal: string;
  signal_tags: string[];
  risk_tags: string[];
  must_watch: boolean;
  reason_json: Record<string, unknown>;
};

export type ReportLink = {
  report_type: string;
  title: string;
  path: string;
  format: string;
  trade_date: string | null;
};

export type DashboardOverview = {
  trade_date: string;
  score_version: string;
  watchlist_id: string;
  top_scores: ScoreRow[];
  watchlist_signals: WatchlistSignalRow[];
  reports: ReportLink[];
};
```

- [ ] **Step 4: Add client**

Create `dashboard/src/api/client.ts`:

```typescript
import type { BarPoint, DashboardOverview, ScoreRow, WatchlistSignalRow } from './types';

type OverviewParams = {
  tradeDate: string;
  scoreVersion: string;
  watchlistId: string;
  topN: number;
};

export async function fetchOverview(params: OverviewParams): Promise<DashboardOverview> {
  return getJson(
    `/api/dashboard/overview?trade_date=${encodeURIComponent(params.tradeDate)}` +
      `&score_version=${encodeURIComponent(params.scoreVersion)}` +
      `&watchlist_id=${encodeURIComponent(params.watchlistId)}` +
      `&top_n=${params.topN}`
  );
}

export async function fetchDailyBars(
  assetId: string,
  startDate: string,
  endDate: string,
  adjustType = 'qfq'
): Promise<BarPoint[]> {
  const payload = await getJson<{ items: BarPoint[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/bars?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&adjust_type=${encodeURIComponent(adjustType)}`
  );
  return payload.items;
}

export async function fetchAssetScore(
  assetId: string,
  tradeDate: string,
  scoreVersion = 'manual_v1'
): Promise<ScoreRow | null> {
  const payload = await getJson<{ item: ScoreRow | null }>(
    `/api/assets/${encodeURIComponent(assetId)}/scores?trade_date=${encodeURIComponent(tradeDate)}` +
      `&score_version=${encodeURIComponent(scoreVersion)}`
  );
  return payload.item;
}

export async function fetchAssetSignals(assetId: string, tradeDate: string): Promise<WatchlistSignalRow[]> {
  const payload = await getJson<{ items: WatchlistSignalRow[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/signals?trade_date=${encodeURIComponent(tradeDate)}`
  );
  return payload.items;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`GET ${url} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}
```

- [ ] **Step 5: Run client tests**

Run:

```bash
cd dashboard
pnpm test -- client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/api dashboard/tests/client.test.ts
git commit -m "feat: add dashboard frontend API client"
```

---

### Task 11: Add Chart Data Conversion and Lightweight Chart Component

**Files:**
- Create: `dashboard/src/charts/chartData.ts`
- Create: `dashboard/src/charts/AssetChart.tsx`
- Test: `dashboard/tests/chartData.test.ts`

- [ ] **Step 1: Write chart data conversion tests**

Create `dashboard/tests/chartData.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { toCandlestickData, toVolumeData } from '../src/charts/chartData';

describe('chart data conversion', () => {
  it('drops rows without complete OHLC values', () => {
    const result = toCandlestickData([
      { time: '2026-05-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 },
      { time: '2026-05-29', open: null, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }
    ]);

    expect(result).toEqual([{ time: '2026-05-28', open: 10, high: 11, low: 9, close: 10.5 }]);
  });

  it('maps volume color from close versus open', () => {
    const result = toVolumeData([
      { time: '2026-05-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 },
      { time: '2026-05-29', open: 10, high: 10.5, low: 9, close: 9.5, volume: 200, amount: 1000 }
    ]);

    expect(result[0].color).toBe('#1f9d55');
    expect(result[1].color).toBe('#d64545');
  });
});
```

- [ ] **Step 2: Run chart tests to verify failure**

Run:

```bash
cd dashboard
pnpm test -- chartData.test.ts
```

Expected: FAIL because `src/charts/chartData.ts` does not exist.

- [ ] **Step 3: Implement chart data conversion**

Create `dashboard/src/charts/chartData.ts`:

```typescript
import type { BarPoint } from '../api/types';

export type CandlePoint = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type VolumePoint = {
  time: string;
  value: number;
  color: string;
};

export function toCandlestickData(points: BarPoint[]): CandlePoint[] {
  return points
    .filter((point) => point.open !== null && point.high !== null && point.low !== null && point.close !== null)
    .map((point) => ({
      time: point.time,
      open: point.open as number,
      high: point.high as number,
      low: point.low as number,
      close: point.close as number
    }));
}

export function toVolumeData(points: BarPoint[]): VolumePoint[] {
  return points
    .filter((point) => point.volume !== null && point.open !== null && point.close !== null)
    .map((point) => ({
      time: point.time,
      value: point.volume as number,
      color: (point.close as number) >= (point.open as number) ? '#1f9d55' : '#d64545'
    }));
}
```

- [ ] **Step 4: Implement chart component**

Create `dashboard/src/charts/AssetChart.tsx`:

```typescript
import { createChart, type IChartApi } from 'lightweight-charts';
import { useEffect, useRef } from 'react';
import type { BarPoint } from '../api/types';
import { toCandlestickData, toVolumeData } from './chartData';

type AssetChartProps = {
  bars: BarPoint[];
};

export function AssetChart({ bars }: AssetChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const chart = createChart(containerRef.current, {
      height: 460,
      layout: {
        background: { color: '#ffffff' },
        textColor: '#202936'
      },
      grid: {
        vertLines: { color: '#eef1f5' },
        horzLines: { color: '#eef1f5' }
      },
      rightPriceScale: {
        borderColor: '#d9dee7'
      },
      timeScale: {
        borderColor: '#d9dee7'
      }
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#1f9d55',
      downColor: '#d64545',
      borderVisible: false,
      wickUpColor: '#1f9d55',
      wickDownColor: '#d64545'
    });
    candleSeries.setData(toCandlestickData(bars));

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: ''
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0
      }
    });
    volumeSeries.setData(toVolumeData(bars));

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [bars]);

  return <div className="asset-chart" ref={containerRef} />;
}
```

- [ ] **Step 5: Run chart tests and build**

Run:

```bash
cd dashboard
pnpm test -- chartData.test.ts
pnpm build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/charts dashboard/tests/chartData.test.ts
git commit -m "feat: add dashboard asset chart"
```

---

### Task 12: Build Workbench UI Against API

**Files:**
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/src/styles.css`
- Create: `dashboard/src/components/TopNList.tsx`
- Create: `dashboard/src/components/WatchlistList.tsx`
- Create: `dashboard/src/components/ScorePanel.tsx`
- Create: `dashboard/src/components/ReportPanel.tsx`

- [ ] **Step 1: Create TopN list component**

Create `dashboard/src/components/TopNList.tsx`:

```typescript
import type { ScoreRow } from '../api/types';

type TopNListProps = {
  rows: ScoreRow[];
  selectedAssetId: string;
  onSelectAsset: (assetId: string) => void;
};

export function TopNList({ rows, selectedAssetId, onSelectAsset }: TopNListProps) {
  return (
    <section className="list-section">
      <h2>TopN</h2>
      <div className="dense-list">
        {rows.map((row) => (
          <button
            key={row.asset_id}
            className={row.asset_id === selectedAssetId ? 'list-row active' : 'list-row'}
            onClick={() => onSelectAsset(row.asset_id)}
          >
            <span>{row.rank}</span>
            <strong>{row.asset_id}</strong>
            <span>{row.score_total.toFixed(1)}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Create watchlist list component**

Create `dashboard/src/components/WatchlistList.tsx`:

```typescript
import type { WatchlistSignalRow } from '../api/types';

type WatchlistListProps = {
  rows: WatchlistSignalRow[];
  selectedAssetId: string;
  onSelectAsset: (assetId: string) => void;
};

export function WatchlistList({ rows, selectedAssetId, onSelectAsset }: WatchlistListProps) {
  return (
    <section className="list-section">
      <h2>Watchlist</h2>
      <div className="dense-list">
        {rows.map((row) => (
          <button
            key={`${row.watchlist_id}-${row.asset_id}`}
            className={row.asset_id === selectedAssetId ? 'list-row active' : 'list-row'}
            onClick={() => onSelectAsset(row.asset_id)}
          >
            <span>{row.must_watch ? '必看' : row.priority}</span>
            <strong>{row.stock_name || row.asset_id}</strong>
            <span>{row.primary_signal}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Create score and report panels**

Create `dashboard/src/components/ScorePanel.tsx`:

```typescript
import type { ScoreRow, WatchlistSignalRow } from '../api/types';

type ScorePanelProps = {
  score: ScoreRow | null;
  signals: WatchlistSignalRow[];
};

export function ScorePanel({ score, signals }: ScorePanelProps) {
  return (
    <section className="inspector-section">
      <h2>Asset Review</h2>
      {score ? (
        <div className="metric-grid">
          <span>Rank</span>
          <strong>{score.rank}</strong>
          <span>Score</span>
          <strong>{score.score_total.toFixed(1)}</strong>
        </div>
      ) : (
        <p className="muted">No score for selected date.</p>
      )}
      <div className="tag-stack">
        {signals.flatMap((signal) =>
          signal.risk_tags.map((tag) => (
            <span className="risk-tag" key={`${signal.watchlist_id}-${tag}`}>
              {tag}
            </span>
          ))
        )}
      </div>
    </section>
  );
}
```

Create `dashboard/src/components/ReportPanel.tsx`:

```typescript
import type { ReportLink } from '../api/types';

type ReportPanelProps = {
  reports: ReportLink[];
};

export function ReportPanel({ reports }: ReportPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Reports</h2>
      <div className="report-list">
        {reports.map((report) => (
          <a key={report.path} href={report.path}>
            <span>{report.report_type}</span>
            <strong>{report.title}</strong>
          </a>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Wire App to API and chart**

Modify `dashboard/src/App.tsx`:

```typescript
import { useEffect, useMemo, useState } from 'react';
import { fetchAssetScore, fetchAssetSignals, fetchDailyBars, fetchOverview } from './api/client';
import type { BarPoint, DashboardOverview, ScoreRow, WatchlistSignalRow } from './api/types';
import { AssetChart } from './charts/AssetChart';
import { ReportPanel } from './components/ReportPanel';
import { ScorePanel } from './components/ScorePanel';
import { TopNList } from './components/TopNList';
import { WatchlistList } from './components/WatchlistList';

const DEFAULT_TRADE_DATE = '2026-05-29';
const DEFAULT_ASSET_ID = '000001.SZ';

export function App() {
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [selectedAssetId, setSelectedAssetId] = useState(DEFAULT_ASSET_ID);
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [bars, setBars] = useState<BarPoint[]>([]);
  const [score, setScore] = useState<ScoreRow | null>(null);
  const [signals, setSignals] = useState<WatchlistSignalRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const startDate = useMemo(() => {
    const date = new Date(`${tradeDate}T00:00:00`);
    date.setDate(date.getDate() - 180);
    return date.toISOString().slice(0, 10);
  }, [tradeDate]);

  useEffect(() => {
    setError(null);
    fetchOverview({
      tradeDate,
      scoreVersion: 'manual_v1',
      watchlistId: 'default',
      topN: 30
    })
      .then(setOverview)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [tradeDate]);

  useEffect(() => {
    setError(null);
    Promise.all([
      fetchDailyBars(selectedAssetId, startDate, tradeDate),
      fetchAssetScore(selectedAssetId, tradeDate),
      fetchAssetSignals(selectedAssetId, tradeDate)
    ])
      .then(([barRows, scoreRow, signalRows]) => {
        setBars(barRows);
        setScore(scoreRow);
        setSignals(signalRows);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, [selectedAssetId, startDate, tradeDate]);

  return (
    <main className="workbench">
      <aside className="sidebar">
        <div className="panel-title">Stock Research</div>
        <TopNList
          rows={overview?.top_scores ?? []}
          selectedAssetId={selectedAssetId}
          onSelectAsset={setSelectedAssetId}
        />
        <WatchlistList
          rows={overview?.watchlist_signals ?? []}
          selectedAssetId={selectedAssetId}
          onSelectAsset={setSelectedAssetId}
        />
      </aside>
      <section className="workspace">
        <header className="toolbar">
          <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
          <input value={selectedAssetId} onChange={(event) => setSelectedAssetId(event.target.value.trim())} />
          {error ? <span className="error-text">{error}</span> : null}
        </header>
        <section className="chart-panel">
          <AssetChart bars={bars} />
        </section>
      </section>
      <aside className="inspector">
        <ScorePanel score={score} signals={signals} />
        <ReportPanel reports={overview?.reports ?? []} />
      </aside>
    </main>
  );
}
```

- [ ] **Step 5: Extend CSS**

Append to `dashboard/src/styles.css`:

```css
.list-section,
.inspector-section {
  margin-top: 18px;
}

.list-section h2,
.inspector-section h2 {
  margin: 0 0 8px;
  font-size: 12px;
  text-transform: uppercase;
  color: #667085;
}

.dense-list {
  display: grid;
  gap: 4px;
}

.list-row {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  width: 100%;
  min-height: 34px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #202936;
  text-align: left;
  cursor: pointer;
}

.list-row:hover,
.list-row.active {
  border-color: #9ab3d5;
  background: #edf4ff;
}

.list-row strong,
.report-list strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  font-size: 13px;
}

.tag-stack {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.risk-tag {
  border-radius: 999px;
  background: #fff1f0;
  color: #b42318;
  padding: 3px 8px;
  font-size: 12px;
}

.report-list {
  display: grid;
  gap: 8px;
}

.report-list a {
  display: grid;
  gap: 2px;
  color: #205493;
  text-decoration: none;
  font-size: 12px;
}

.muted,
.error-text {
  color: #667085;
  font-size: 12px;
}

.error-text {
  color: #b42318;
}

.asset-chart {
  width: 100%;
  min-height: 460px;
}
```

- [ ] **Step 6: Build frontend**

Run:

```bash
cd dashboard
pnpm build
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/App.tsx dashboard/src/styles.css dashboard/src/components
git commit -m "feat: build dashboard workbench UI"
```

---

### Task 13: Add End-to-End Smoke Test

**Files:**
- Create: `dashboard/playwright.config.ts`
- Create: `dashboard/tests/app-smoke.spec.ts`

- [ ] **Step 1: Add Playwright config**

Create `dashboard/playwright.config.ts`:

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'on-first-retry'
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    }
  ],
  webServer: {
    command: 'pnpm dev',
    url: 'http://127.0.0.1:5174',
    reuseExistingServer: true,
    timeout: 120000
  }
});
```

- [ ] **Step 2: Add mocked browser smoke test**

Create `dashboard/tests/app-smoke.spec.ts`:

```typescript
import { expect, test } from '@playwright/test';

test('dashboard shell renders with mocked API responses', async ({ page }) => {
  await page.route('/api/dashboard/overview**', async (route) => {
    await route.fulfill({
      json: {
        trade_date: '2026-05-29',
        score_version: 'manual_v1',
        watchlist_id: 'default',
        top_scores: [
          {
            trade_date: '2026-05-29',
            asset_id: '000001.SZ',
            rank: 1,
            score_total: 91.2,
            score_version: 'manual_v1',
            score_components: {}
          }
        ],
        watchlist_signals: [],
        reports: []
      }
    });
  });
  await page.route('/api/assets/*/bars**', async (route) => {
    await route.fulfill({
      json: {
        asset_id: '000001.SZ',
        resolution: '1D',
        items: [
          { time: '2026-05-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }
        ]
      }
    });
  });
  await page.route('/api/assets/*/scores**', async (route) => {
    await route.fulfill({
      json: {
        item: {
          trade_date: '2026-05-29',
          asset_id: '000001.SZ',
          rank: 1,
          score_total: 91.2,
          score_version: 'manual_v1',
          score_components: {}
        }
      }
    });
  });
  await page.route('/api/assets/*/signals**', async (route) => {
    await route.fulfill({ json: { items: [] } });
  });

  await page.goto('/');

  await expect(page.getByText('Stock Research')).toBeVisible();
  await expect(page.getByText('000001.SZ')).toBeVisible();
  await expect(page.getByText('Asset Review')).toBeVisible();
});
```

- [ ] **Step 3: Run E2E smoke**

Run:

```bash
cd dashboard
pnpm test:e2e
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add dashboard/playwright.config.ts dashboard/tests/app-smoke.spec.ts
git commit -m "test: add dashboard browser smoke test"
```

---

### Task 14: Add Operator Documentation

**Files:**
- Create: `docs/dashboard-workbench-runbook.md`
- Modify: `README.md`

- [ ] **Step 1: Create runbook**

Create `docs/dashboard-workbench-runbook.md`:

```markdown
# Dashboard Workbench Runbook

The dashboard workbench is a read-only UI for the existing stock research platform.

## Start API

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

## Start Frontend

```bash
cd dashboard
pnpm dev
```

Open:

```text
http://127.0.0.1:5174
```

## Data Sources

- Daily bars: `market_daily_bar`
- Minute bars: `market.stock_minute_bar`
- TopN scores: `factor.stock_score_daily`
- Watchlist signals: `watchlist.watchlist_daily_signal`
- Report links: local `reports/` artifacts

## Operating Boundary

The dashboard does not create trading instructions. It only displays existing research outputs for human review.
```

- [ ] **Step 2: Link runbook from README**

Add to `README.md` after the daily research command section:

```markdown
## Dashboard Workbench

The dashboard workbench is a read-only UI for charting, TopN review, watchlist review, and report navigation.

See `docs/dashboard-workbench-runbook.md`.
```

- [ ] **Step 3: Run docs-adjacent smoke tests**

Run:

```bash
.venv/bin/pytest tests/test_agent_contracts.py tests/test_report_delivery.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/dashboard-workbench-runbook.md
git commit -m "docs: add dashboard workbench runbook"
```

---

### Task 15: Final Verification

**Files:**
- No new files unless fixes are needed.

- [ ] **Step 1: Run focused backend suite**

Run:

```bash
.venv/bin/pytest \
  tests/test_dashboard_schemas.py \
  tests/test_dashboard_scores.py \
  tests/test_dashboard_bars.py \
  tests/test_dashboard_watchlist.py \
  tests/test_dashboard_reports.py \
  tests/test_dashboard_overview.py \
  tests/test_dashboard_app.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests and build**

Run:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

Expected: PASS.

- [ ] **Step 3: Run a local API smoke**

Start API:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

In another terminal:

```bash
curl -sS "http://127.0.0.1:8765/api/dashboard/overview?trade_date=2026-05-29&score_version=manual_v1&watchlist_id=default&top_n=5"
```

Expected: JSON object with keys:

```json
{
  "trade_date": "2026-05-29",
  "score_version": "manual_v1",
  "watchlist_id": "default",
  "top_scores": [],
  "watchlist_signals": [],
  "reports": []
}
```

The arrays may be empty if the local database has no rows for that date.

- [ ] **Step 4: Start frontend for operator validation**

Run:

```bash
cd dashboard
pnpm dev
```

Open:

```text
http://127.0.0.1:5174
```

Expected:

- Workbench shell renders.
- TopN and watchlist panels render without overlap.
- Chart area is nonblank when API returns bars.
- Score and report panels show empty states instead of crashing.

- [ ] **Step 5: Commit any final fixes**

```bash
git status --short
git add docs/dashboard-workbench-runbook.md dashboard/src/App.tsx dashboard/src/styles.css
git commit -m "fix: harden dashboard workbench smoke"
```

Only commit actual fixes. If no fixes are needed, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage: backend API, frontend shell, Lightweight Charts, TopN, watchlist, report links, runbook, and verification are covered.
- Scope control: implementation is read-only and does not change research pipelines.
- Type consistency: backend DTO keys match frontend TypeScript types.
- Test coverage: each backend read model has unit tests; frontend has data conversion, client, build, and browser smoke tests.
- Known dependency risk: `fastapi`, `uvicorn`, and frontend packages require install access during implementation.
