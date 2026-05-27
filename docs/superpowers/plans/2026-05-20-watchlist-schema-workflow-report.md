# Watchlist Schema Workflow Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a database-backed watchlist layer that stores source-of-truth memberships, computes daily watchlist signals, and writes watchlist report artifacts through stable CLI entrypoints.

**Architecture:** Add a dedicated `watchlist` schema and a focused store module first so memberships and daily signal snapshots have a stable persistence contract. Build pure signal/risk functions on top of existing research inputs (`load_top_scores`, feature snapshots, market state, sector strength), then add a workflow orchestrator and a dedicated watchlist report writer that reuses the shared `run_card` layer.

**Tech Stack:** Python 3.14, pandas, PostgreSQL service `stock_research`, existing `stock_research.cli`, existing report helpers under `src/stock_research/reports/`, existing `run_card.py`.

---

### Task 1: Add Watchlist Schema And Store Primitives

**Files:**
- Modify: `src/stock_research/schema.py`
- Test: `tests/test_schema.py`
- Create: `src/stock_research/watchlist/store.py`
- Test: `tests/test_watchlist_store.py`

- [ ] **Step 1: Write the failing schema and store tests**

```python
from stock_research.schema import CREATE_RESEARCH_EXTENSION_SQL


def test_research_extension_creates_watchlist_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE SCHEMA IF NOT EXISTS watchlist;" in sql
    assert "CREATE TABLE IF NOT EXISTS watchlist.watchlist_item" in sql
    assert "CREATE TABLE IF NOT EXISTS watchlist.watchlist_daily_signal" in sql
```

```python
import pandas as pd

from stock_research.watchlist import store


def _context(conn):
    class _Manager:
        def __enter__(self):
            return conn

        def __exit__(self, exc_type, exc, tb):
            return False

    return _Manager()


def test_upsert_watchlist_items_writes_rows(monkeypatch):
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, sql, rows):
            calls.append((sql, list(rows)))

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(store, "connect", lambda service: _context(FakeConn()))
    frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "asset_id": "CN:SH:600000",
                "stock_code": "600000.SH",
                "stock_name": "PF Bank",
                "priority": 10,
                "active": True,
                "note": "core holding candidate",
                "source": "manual",
            }
        ]
    )

    count = store.upsert_watchlist_items(frame)

    assert count == 1
    assert "INSERT INTO watchlist.watchlist_item" in calls[0][0]
    assert calls[0][1][0]["watchlist_id"] == "core"
```

```python
def test_load_watchlist_items_filters_active_members(monkeypatch):
    monkeypatch.setattr(
        store,
        "fetch_all",
        lambda conn, sql, params=None: [
            {
                "watchlist_id": "core",
                "asset_id": "CN:SH:600000",
                "stock_code": "600000.SH",
                "stock_name": "PF Bank",
                "priority": 10,
                "active": True,
                "note": None,
                "source": "manual",
            }
        ],
    )
    monkeypatch.setattr(store, "connect", lambda service: _context(object()))

    frame = store.load_watchlist_items("core", active_only=True)

    assert list(frame["asset_id"]) == ["CN:SH:600000"]
```

```python
def test_store_watchlist_daily_signals_writes_json_fields(monkeypatch):
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, sql, rows):
            calls.append((sql, list(rows)))

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(store, "connect", lambda service: _context(FakeConn()))
    frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "CN:SH:600000",
                "stock_code": "600000.SH",
                "stock_name": "PF Bank",
                "priority": 10,
                "signal_score": 88.5,
                "primary_signal": "candidate",
                "signal_tags": ["candidate", "must_watch"],
                "risk_tags": [],
                "must_watch": True,
                "reason_json": {"score_rank": 1},
                "output_version": "v1",
            }
        ]
    )

    count = store.store_watchlist_daily_signals(frame)

    assert count == 1
    assert "INSERT INTO watchlist.watchlist_daily_signal" in calls[0][0]
    assert calls[0][1][0]["signal_tags"] == '["candidate", "must_watch"]'
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv/bin/pytest tests/test_schema.py tests/test_watchlist_store.py -q`

Expected: FAIL because `watchlist` schema/table SQL is missing and `stock_research.watchlist.store` does not exist yet.

- [ ] **Step 3: Implement the schema additions and store module**

```python
# src/stock_research/watchlist/store.py
import json

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


WATCHLIST_ITEM_COLUMNS = [
    "watchlist_id",
    "asset_id",
    "stock_code",
    "stock_name",
    "priority",
    "active",
    "note",
    "source",
]

WATCHLIST_SIGNAL_COLUMNS = [
    "watchlist_id",
    "trade_date",
    "asset_id",
    "stock_code",
    "stock_name",
    "priority",
    "signal_score",
    "primary_signal",
    "signal_tags",
    "risk_tags",
    "must_watch",
    "reason_json",
    "output_version",
]


def upsert_watchlist_items(
    items: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> int:
    if items.empty:
        return 0
    rows = items[WATCHLIST_ITEM_COLUMNS].to_dict("records")
    sql = """
    INSERT INTO watchlist.watchlist_item (
        watchlist_id, asset_id, stock_code, stock_name, priority, active, note, source
    )
    VALUES (
        %(watchlist_id)s, %(asset_id)s, %(stock_code)s, %(stock_name)s,
        %(priority)s, %(active)s, %(note)s, %(source)s
    )
    ON CONFLICT (watchlist_id, asset_id)
    DO UPDATE SET
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        priority = EXCLUDED.priority,
        active = EXCLUDED.active,
        note = EXCLUDED.note,
        source = EXCLUDED.source,
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)


def load_watchlist_items(
    watchlist_id: str,
    active_only: bool = True,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT
        watchlist_id,
        asset_id,
        stock_code,
        stock_name,
        priority,
        active,
        note,
        source
    FROM watchlist.watchlist_item
    WHERE watchlist_id = %s
    """
    params: list[object] = [watchlist_id]
    if active_only:
        sql += " AND active = true"
    sql += " ORDER BY priority, stock_code"
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, params))


def store_watchlist_daily_signals(
    signals: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> int:
    if signals.empty:
        return 0
    rows = signals.copy()
    rows["signal_tags"] = rows["signal_tags"].map(lambda value: json.dumps(value or [], ensure_ascii=False, sort_keys=True))
    rows["risk_tags"] = rows["risk_tags"].map(lambda value: json.dumps(value or [], ensure_ascii=False, sort_keys=True))
    rows["reason_json"] = rows["reason_json"].map(lambda value: json.dumps(value or {}, ensure_ascii=False, sort_keys=True))
    sql = """
    INSERT INTO watchlist.watchlist_daily_signal (
        watchlist_id, trade_date, asset_id, stock_code, stock_name, priority,
        signal_score, primary_signal, signal_tags, risk_tags, must_watch,
        reason_json, output_version
    )
    VALUES (
        %(watchlist_id)s, %(trade_date)s, %(asset_id)s, %(stock_code)s,
        %(stock_name)s, %(priority)s, %(signal_score)s, %(primary_signal)s,
        %(signal_tags)s::jsonb, %(risk_tags)s::jsonb, %(must_watch)s,
        %(reason_json)s::jsonb, %(output_version)s
    )
    ON CONFLICT (watchlist_id, trade_date, asset_id)
    DO UPDATE SET
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        priority = EXCLUDED.priority,
        signal_score = EXCLUDED.signal_score,
        primary_signal = EXCLUDED.primary_signal,
        signal_tags = EXCLUDED.signal_tags,
        risk_tags = EXCLUDED.risk_tags,
        must_watch = EXCLUDED.must_watch,
        reason_json = EXCLUDED.reason_json,
        output_version = EXCLUDED.output_version,
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows[WATCHLIST_SIGNAL_COLUMNS].to_dict("records"))
    return len(rows)


def load_watchlist_daily_signals(
    watchlist_id: str,
    trade_date: object,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
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
        reason_json,
        output_version
    FROM watchlist.watchlist_daily_signal
    WHERE watchlist_id = %s
      AND trade_date = %s
    ORDER BY must_watch DESC, priority, stock_code
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [watchlist_id, pd.Timestamp(trade_date).date().isoformat()]))
```

```sql
CREATE SCHEMA IF NOT EXISTS watchlist;

CREATE TABLE IF NOT EXISTS watchlist.watchlist_item (
    watchlist_id text NOT NULL,
    asset_id text NOT NULL,
    stock_code text NOT NULL,
    stock_name text NOT NULL,
    priority integer NOT NULL DEFAULT 100,
    active boolean NOT NULL DEFAULT true,
    note text,
    source text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (watchlist_id, asset_id)
);

CREATE TABLE IF NOT EXISTS watchlist.watchlist_daily_signal (
    watchlist_id text NOT NULL,
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    stock_code text NOT NULL,
    stock_name text NOT NULL,
    priority integer NOT NULL,
    signal_score numeric,
    primary_signal text NOT NULL,
    signal_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    risk_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
    must_watch boolean NOT NULL DEFAULT false,
    reason_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (watchlist_id, trade_date, asset_id)
);
```

Implementation notes:
- Normalize `signal_tags`, `risk_tags`, and `reason_json` to deterministic JSON strings before `executemany`, the same way `factor_store.py` normalizes `score_components`.
- Keep `load_watchlist_items()` sorted by `priority, stock_code`.
- Keep `load_watchlist_daily_signals()` sorted by `must_watch DESC, priority, stock_code`.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `.venv/bin/pytest tests/test_schema.py tests/test_watchlist_store.py -q`

Expected: PASS with the new watchlist schema and store helpers.

- [ ] **Step 5: Commit the schema/store foundation**

```bash
git add tests/test_schema.py tests/test_watchlist_store.py src/stock_research/schema.py src/stock_research/watchlist/store.py
git commit -m "feat: add watchlist storage schema"
```

### Task 2: Build Watchlist Signal And Risk Workflow

**Files:**
- Create: `src/stock_research/watchlist/signals.py`
- Create: `src/stock_research/watchlist/risk.py`
- Create: `src/stock_research/watchlist/workflow.py`
- Test: `tests/test_watchlist_signals.py`
- Test: `tests/test_watchlist_workflow.py`
- Reuse: `src/stock_research/factor_store.py`
- Reuse: `src/stock_research/reports/daily_research_report_cli.py`
- Reuse: `src/stock_research/reports/market_state_report.py`
- Reuse: `src/stock_research/reports/sector_strength_report.py`

- [ ] **Step 1: Write the failing signal and workflow tests**

```python
import pandas as pd

from stock_research.watchlist.signals import build_watchlist_signal_rows


def test_build_watchlist_signal_rows_marks_top_ranked_assets_as_must_watch():
    watchlist_items = pd.DataFrame(
        [
            {"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10},
            {"watchlist_id": "core", "asset_id": "B", "stock_code": "000002.SZ", "stock_name": "B", "priority": 20},
        ]
    )
    top_scores = [{"asset_id": "A", "rank": 1, "score_total": 88.0}]
    feature_snapshot = pd.DataFrame(
        [
            {"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.04},
            {"asset_id": "A", "feature_name": "ret_20d", "feature_value": 0.12},
        ]
    )
    market_state = {"market_state": "bullish", "entry_allowed": True}
    sector_strength = pd.DataFrame(
        [{"industry_code": "BANK", "strength_rank": 1, "strength_score": 80.0}]
    )
    industry_map = {"A": {"industry_code": "BANK", "industry_name": "Bank"}}

    frame = build_watchlist_signal_rows(
        watchlist_items=watchlist_items,
        top_scores=top_scores,
        feature_snapshot=feature_snapshot,
        market_state=market_state,
        sector_strength=sector_strength,
        industry_map=industry_map,
        output_version="v1",
    )

    row = frame.iloc[0]
    assert row["asset_id"] == "A"
    assert row["must_watch"] is True
    assert row["primary_signal"] == "candidate"
    assert row["signal_tags"] == ["candidate", "must_watch"]
```

```python
def test_build_watchlist_signal_rows_adds_overheat_and_breakdown_tags():
    watchlist_items = pd.DataFrame(
        [{"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10}]
    )
    top_scores = []
    feature_snapshot = pd.DataFrame(
        [
            {"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.18},
            {"asset_id": "A", "feature_name": "ret_20d", "feature_value": -0.05},
            {"asset_id": "A", "feature_name": "ma20_deviation", "feature_value": -0.04},
        ]
    )

    frame = build_watchlist_signal_rows(
        watchlist_items=watchlist_items,
        top_scores=top_scores,
        feature_snapshot=feature_snapshot,
        market_state={"market_state": "neutral", "entry_allowed": True},
        sector_strength=pd.DataFrame(),
        industry_map={},
        output_version="v1",
    )

    assert frame.iloc[0]["primary_signal"] == "breakdown"
    assert "overheat" in frame.iloc[0]["risk_tags"]
```

```python
from stock_research.watchlist.workflow import build_watchlist_snapshot


def test_build_watchlist_snapshot_loads_context_and_persists_signal_rows(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_watchlist_items",
        lambda *args, **kwargs: pd.DataFrame(
            [
                {"watchlist_id": "core", "asset_id": "A", "stock_code": "000001.SZ", "stock_name": "A", "priority": 10},
                {"watchlist_id": "core", "asset_id": "B", "stock_code": "000002.SZ", "stock_name": "B", "priority": 20},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_top_scores",
        lambda **kwargs: [{"asset_id": "A", "rank": 1, "score_total": 88.0}],
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_feature_snapshot",
        lambda **kwargs: pd.DataFrame(
            [
                {"asset_id": "A", "feature_name": "ret_5d", "feature_value": 0.04},
                {"asset_id": "A", "feature_name": "ret_20d", "feature_value": 0.12},
                {"asset_id": "B", "feature_name": "ret_5d", "feature_value": -0.02},
                {"asset_id": "B", "feature_name": "ret_20d", "feature_value": -0.05},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.load_industry_memberships",
        lambda **kwargs: {
            "A": {"industry_code": "BANK", "industry_name": "Bank"},
            "B": {"industry_code": "TECH", "industry_name": "Tech"},
        },
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_market_state",
        lambda **kwargs: {"market_state": "bullish", "entry_allowed": True},
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow._load_sector_strength",
        lambda **kwargs: pd.DataFrame(
            [
                {"industry_code": "BANK", "strength_rank": 1, "strength_score": 80.0},
                {"industry_code": "TECH", "strength_rank": 20, "strength_score": 20.0},
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.watchlist.workflow.store_watchlist_daily_signals",
        lambda frame, **kwargs: calls.append(frame) or len(frame),
    )

    frame = build_watchlist_snapshot(
        trade_date="2026-05-20",
        watchlist_id="core",
        score_version="manual_v1",
    )

    assert len(frame) == 2
    assert len(calls) == 1
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv/bin/pytest tests/test_watchlist_signals.py tests/test_watchlist_workflow.py -q`

Expected: FAIL because the signal/risk/workflow modules do not exist yet.

- [ ] **Step 3: Implement pure signal rules, risk tagging, and the workflow orchestrator**

```python
# src/stock_research/watchlist/risk.py
def classify_watchlist_risks(
    *,
    feature_values: dict[str, float],
    market_state: dict[str, object],
    sector_row: dict[str, object] | None,
) -> list[str]:
    risks: list[str] = []
    if market_state.get("entry_allowed") is False:
        risks.append("risk_excluded")
    if float(feature_values.get("ret_5d", 0.0) or 0.0) >= 0.15:
        risks.append("overheat")
    if float(feature_values.get("max_drawdown_20d", 0.0) or 0.0) <= -0.15:
        risks.append("risk_excluded")
    if sector_row is not None and int(sector_row.get("strength_rank", 0) or 0) >= 15:
        risks.append("sector_weakness")
    return sorted(set(risks))
```

```python
# src/stock_research/watchlist/signals.py
WATCHLIST_SIGNAL_OUTPUT_COLUMNS = [
    "watchlist_id",
    "trade_date",
    "asset_id",
    "stock_code",
    "stock_name",
    "priority",
    "signal_score",
    "primary_signal",
    "signal_tags",
    "risk_tags",
    "must_watch",
    "reason_json",
    "output_version",
]


def build_watchlist_signal_rows(
    *,
    watchlist_items: pd.DataFrame,
    top_scores: list[dict[str, object]],
    feature_snapshot: pd.DataFrame,
    market_state: dict[str, object],
    sector_strength: pd.DataFrame,
    industry_map: dict[str, dict[str, object]],
    output_version: str,
) -> pd.DataFrame:
    score_map = {str(row["asset_id"]): row for row in top_scores}
    feature_map = _feature_map(feature_snapshot)
    sector_map = {
        str(row["industry_code"]): row
        for row in sector_strength.to_dict("records")
        if row.get("industry_code")
    }
    rows: list[dict[str, object]] = []
    for item in watchlist_items.to_dict("records"):
        asset_id = str(item["asset_id"])
        feature_values = feature_map.get(asset_id, {})
        sector_row = sector_map.get(str(industry_map.get(asset_id, {}).get("industry_code") or ""))
        score_row = score_map.get(asset_id, {})
        signal_tags = _signal_tags(feature_values, score_row)
        risk_tags = classify_watchlist_risks(
            feature_values=feature_values,
            market_state=market_state,
            sector_row=sector_row,
        )
        rows.append(
            _signal_row(
                item=item,
                feature_values=feature_values,
                score_row=score_row,
                signal_tags=signal_tags,
                risk_tags=risk_tags,
                output_version=output_version,
            )
        )
    return pd.DataFrame(rows, columns=WATCHLIST_SIGNAL_OUTPUT_COLUMNS)
```

```python
# src/stock_research/watchlist/workflow.py
from pathlib import Path

from stock_research.factor_store import load_top_scores
from stock_research.reports.daily_research_report_cli import (
    load_feature_snapshot,
    load_industry_memberships,
)
from stock_research.reports.market_state_report import calc_market_state, load_market_state_bars
from stock_research.reports.sector_strength_report import calc_sector_strength, load_sector_strength_bars
from stock_research.watchlist.signals import build_watchlist_signal_rows
from stock_research.watchlist.store import (
    load_watchlist_daily_signals,
    load_watchlist_items,
    store_watchlist_daily_signals,
)


def build_watchlist_snapshot(
    *,
    trade_date: str,
    watchlist_id: str,
    score_version: str = "manual_v1",
    top_n: int = 30,
    output_version: str = "v1",
) -> pd.DataFrame:
    watchlist_items = load_watchlist_items(watchlist_id)
    top_scores = load_top_scores(
        trade_date=trade_date,
        score_version=score_version,
        top_n=top_n,
    )
    asset_ids = watchlist_items["asset_id"].astype(str).tolist()
    feature_snapshot = load_feature_snapshot(trade_date=trade_date, asset_ids=asset_ids)
    industry_map = load_industry_memberships(
        trade_date=trade_date,
        asset_ids=asset_ids,
        industry_system="csrc",
    )
    market_state = _load_market_state(trade_date=trade_date)
    sector_strength = _load_sector_strength(trade_date=trade_date)
    rows = build_watchlist_signal_rows(
        watchlist_items=watchlist_items,
        top_scores=top_scores,
        feature_snapshot=feature_snapshot,
        market_state=market_state,
        sector_strength=sector_strength,
        industry_map=industry_map,
        output_version=output_version,
    )
    rows["watchlist_id"] = watchlist_id
    rows["trade_date"] = trade_date
    store_watchlist_daily_signals(rows)
    return rows


def explain_watchlist_asset(
    *,
    trade_date: str,
    watchlist_id: str,
    asset_id: str,
) -> dict[str, object]:
    rows = load_watchlist_daily_signals(watchlist_id, trade_date)
    matched = rows[rows["asset_id"].astype(str) == str(asset_id)]
    if matched.empty:
        raise ValueError(f"watchlist asset not found: {watchlist_id} {trade_date} {asset_id}")
    return matched.iloc[0].to_dict()
```

Signal rules for the first version:
- `candidate`: asset is present in `top_scores[:top_n]`.
- `must_watch`: `candidate` and not tagged with `risk_excluded`.
- `pullback`: `ret_20d > 0` and `ma20_deviation < 0`.
- `breakdown`: `ret_20d < 0` and `ma20_deviation < 0`.
- `overheat`: `ret_5d >= 0.15` or `ma20_deviation >= 0.12`.
- `sector_weakness`: industry rank in bottom half of the available `sector_strength` frame.
- `risk_excluded`: `market_state["entry_allowed"]` is false or `max_drawdown_20d <= -0.15`.

Implementation notes:
- Keep signal generation missing-safe. If a feature is absent, skip only the specific rule instead of failing the whole row.
- `reason_json` must include enough structure for `watchlist-explain`: score rank, feature values used, sector context, and final tags.
- `build_watchlist_snapshot()` should store rows before returning them so `watchlist-report` can be a pure read path.
- Define local helpers in the same module:
  - `_feature_map(feature_snapshot: pd.DataFrame) -> dict[str, dict[str, float]]`
  - `_signal_tags(feature_values: dict[str, float], score_row: dict[str, object]) -> list[str]`
  - `_signal_row(item: dict[str, object], feature_values: dict[str, float], score_row: dict[str, object], signal_tags: list[str], risk_tags: list[str], output_version: str) -> dict[str, object]`

- [ ] **Step 4: Run the tests and verify they pass**

Run: `.venv/bin/pytest tests/test_watchlist_signals.py tests/test_watchlist_workflow.py -q`

Expected: PASS with deterministic signal rows and persisted daily snapshots.

- [ ] **Step 5: Commit the workflow layer**

```bash
git add tests/test_watchlist_signals.py tests/test_watchlist_workflow.py src/stock_research/watchlist/signals.py src/stock_research/watchlist/risk.py src/stock_research/watchlist/workflow.py
git commit -m "feat: add watchlist signal workflow"
```

### Task 3: Add Watchlist Report And CLI Entry Points

**Files:**
- Create: `src/stock_research/reports/watchlist_report.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_watchlist_report.py`
- Create: `tests/test_watchlist_cli.py`

- [ ] **Step 1: Write the failing report and CLI tests**

```python
from pathlib import Path

import pandas as pd

from stock_research.reports.watchlist_report import write_watchlist_report


def test_write_watchlist_report_writes_markdown_json_csv_and_must_watch(tmp_path):
    frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "A",
                "stock_code": "000001.SZ",
                "stock_name": "A",
                "priority": 10,
                "signal_score": 88.0,
                "primary_signal": "candidate",
                "signal_tags": ["candidate", "must_watch"],
                "risk_tags": [],
                "must_watch": True,
                "reason_json": {"score_rank": 1},
                "output_version": "v1",
            }
        ]
    )

    paths = write_watchlist_report(frame, output_dir=tmp_path)

    assert Path(paths["markdown_path"]).exists()
    assert Path(paths["json_path"]).exists()
    assert Path(paths["signals_csv_path"]).exists()
    assert Path(paths["must_watch_csv_path"]).exists()
```

```python
from stock_research.cli import build_parser


def test_cli_accepts_watchlist_commands():
    build_args = build_parser().parse_args(
        ["watchlist-build", "--trade-date", "2026-05-20", "--watchlist-id", "core", "--output-dir", "outputs/watchlist"]
    )
    report_args = build_parser().parse_args(
        ["watchlist-report", "--trade-date", "2026-05-20", "--watchlist-id", "core", "--output-dir", "outputs/watchlist"]
    )
    explain_args = build_parser().parse_args(
        ["watchlist-explain", "--trade-date", "2026-05-20", "--watchlist-id", "core", "--asset-id", "CN:SH:600000"]
    )

    assert build_args.command == "watchlist-build"
    assert report_args.command == "watchlist-report"
    assert explain_args.command == "watchlist-explain"
```

```python
def test_watchlist_build_cli_prints_summary_and_run_card(monkeypatch, capsys):
    monkeypatch.setattr(
        "stock_research.cli.build_watchlist_snapshot",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "watchlist_id": "core",
                    "trade_date": "2026-05-20",
                    "asset_id": "A",
                    "stock_code": "000001.SZ",
                    "stock_name": "A",
                    "priority": 10,
                    "signal_score": 88.0,
                    "primary_signal": "candidate",
                    "signal_tags": ["candidate", "must_watch"],
                    "risk_tags": [],
                    "must_watch": True,
                    "reason_json": {"score_rank": 1},
                    "output_version": "v1",
                },
                {
                    "watchlist_id": "core",
                    "trade_date": "2026-05-20",
                    "asset_id": "B",
                    "stock_code": "000002.SZ",
                    "stock_name": "B",
                    "priority": 20,
                    "signal_score": 55.0,
                    "primary_signal": "breakdown",
                    "signal_tags": ["breakdown"],
                    "risk_tags": ["sector_weakness"],
                    "must_watch": False,
                    "reason_json": {"score_rank": None},
                    "output_version": "v1",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        "stock_research.cli.write_watchlist_report",
        lambda *args, **kwargs: {
            "markdown_path": "/tmp/watchlist.md",
            "json_path": "/tmp/watchlist.json",
            "signals_csv_path": "/tmp/signals.csv",
            "must_watch_csv_path": "/tmp/must_watch.csv",
        },
    )
    monkeypatch.setattr("stock_research.cli.write_run_card", lambda **kwargs: {"run_card_json_path": "/tmp/run_card.json"})

    cli.main_for_args(
        [
            "watchlist-build",
            "--trade-date",
            "2026-05-20",
            "--watchlist-id",
            "core",
            "--output-dir",
            "/tmp/watchlist",
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert "watchlist_build|watchlist_id|core" in lines
    assert "watchlist_build|members|2" in lines
    assert "watchlist_build|must_watch|1" in lines
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv/bin/pytest tests/test_watchlist_report.py tests/test_watchlist_cli.py -q`

Expected: FAIL because the report writer and watchlist CLI commands are not implemented yet.

- [ ] **Step 3: Implement the watchlist report writer and CLI dispatch**

```python
# src/stock_research/reports/watchlist_report.py
import json
from pathlib import Path

import pandas as pd


def write_watchlist_report(
    signal_rows: pd.DataFrame,
    *,
    output_dir: str | Path,
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    normalized = signal_rows.copy()
    normalized["signal_tags"] = normalized["signal_tags"].map(lambda value: json.dumps(value or [], ensure_ascii=False, sort_keys=True))
    normalized["risk_tags"] = normalized["risk_tags"].map(lambda value: json.dumps(value or [], ensure_ascii=False, sort_keys=True))
    normalized["reason_json"] = normalized["reason_json"].map(lambda value: json.dumps(value or {}, ensure_ascii=False, sort_keys=True))
    markdown_path = path / "watchlist_report.md"
    json_path = path / "watchlist_report.json"
    signals_csv_path = path / "watchlist_signals.csv"
    must_watch_csv_path = path / "must_watch.csv"
    normalized.to_csv(signals_csv_path, index=False)
    normalized[normalized["must_watch"]].to_csv(must_watch_csv_path, index=False)
    json_path.write_text(normalized.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_watchlist_markdown(normalized), encoding="utf-8")
    return {
        "markdown_path": str(markdown_path),
        "json_path": str(json_path),
        "signals_csv_path": str(signals_csv_path),
        "must_watch_csv_path": str(must_watch_csv_path),
    }
```

```python
# src/stock_research/cli.py
watchlist_build = subparsers.add_parser("watchlist-build")
watchlist_build.add_argument("--trade-date", required=True)
watchlist_build.add_argument("--watchlist-id", required=True)
watchlist_build.add_argument("--score-version", default="manual_v1")
watchlist_build.add_argument("--top-n", type=int, default=30)
watchlist_build.add_argument("--output-dir", required=True)

watchlist_report = subparsers.add_parser("watchlist-report")
watchlist_report.add_argument("--trade-date", required=True)
watchlist_report.add_argument("--watchlist-id", required=True)
watchlist_report.add_argument("--output-dir", required=True)

watchlist_explain = subparsers.add_parser("watchlist-explain")
watchlist_explain.add_argument("--trade-date", required=True)
watchlist_explain.add_argument("--watchlist-id", required=True)
watchlist_explain.add_argument("--asset-id", required=True)
```

```python
elif args.command == "watchlist-build":
    rows = build_watchlist_snapshot(
        trade_date=args.trade_date,
        watchlist_id=args.watchlist_id,
        score_version=args.score_version,
        top_n=args.top_n,
    )
    report_paths = write_watchlist_report(rows, output_dir=args.output_dir)
    run_card = write_run_card(
        output_dir=Path(args.output_dir) / "run_card",
        run_type="watchlist_build",
        run_id=f"watchlist:{args.watchlist_id}:{args.trade_date}",
        title="Watchlist Build",
        config={
            "trade_date": args.trade_date,
            "watchlist_id": args.watchlist_id,
            "score_version": args.score_version,
            "top_n": args.top_n,
        },
        metrics={
            "rows": len(rows),
            "must_watch": int(rows["must_watch"].sum()) if not rows.empty else 0,
        },
        artifact_paths=report_paths,
    )
    print(f"watchlist_build|watchlist_id|{args.watchlist_id}")
    print(f"watchlist_build|members|{len(rows)}")
    print(f"watchlist_build|must_watch|{int(rows['must_watch'].sum())}")
    print(f"watchlist_build|report|{report_paths['markdown_path']}")
    print(f"watchlist_build|run_card|{run_card['run_card_json_path']}")
elif args.command == "watchlist-report":
    rows = load_watchlist_daily_signals(args.watchlist_id, args.trade_date)
    report_paths = write_watchlist_report(rows, output_dir=args.output_dir)
    print(f"watchlist_report|markdown|{report_paths['markdown_path']}")
elif args.command == "watchlist-explain":
    print(
        json.dumps(
            explain_watchlist_asset(
                trade_date=args.trade_date,
                watchlist_id=args.watchlist_id,
                asset_id=args.asset_id,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
```

Report outputs:
- `watchlist_report_<trade_date>_<watchlist_id>.md`
- `watchlist_report_<trade_date>_<watchlist_id>.json`
- `watchlist_signals_<trade_date>_<watchlist_id>.csv`
- `must_watch_<trade_date>_<watchlist_id>.csv`

Implementation notes:
- The markdown report should group rows into `Must Watch`, `Candidate`, and `Risk Excluded`.
- Keep the report writer pure: accept a DataFrame, normalize JSON/list columns, write files, return paths.
- `watchlist-build` is the only command that computes and stores new daily rows; `watchlist-report` must be read-only.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `.venv/bin/pytest tests/test_watchlist_report.py tests/test_watchlist_cli.py -q`

Expected: PASS with stable CLI output and all report artifacts present.

- [ ] **Step 5: Commit the report and CLI layer**

```bash
git add tests/test_watchlist_report.py tests/test_watchlist_cli.py src/stock_research/reports/watchlist_report.py src/stock_research/cli.py
git commit -m "feat: add watchlist report workflow"
```
