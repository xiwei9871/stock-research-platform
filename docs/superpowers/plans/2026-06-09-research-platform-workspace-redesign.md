# Research Platform Workspace Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the dashboard from a TopN-first review page into a quant research platform with Home, Data Explorer, Factor Lab, Backtest Lab, Strategy Validation, and Reports.

**Architecture:** Add focused read-only backend modules for platform summary, strategy catalog, factor library/score preview, asset profile, and TopN backtest execution. Add typed frontend API clients and split the current single `App.tsx` surface into task-oriented workspaces while reusing existing chart, inspector, reports, and Strategy Validation components.

**Tech Stack:** Python dataclasses, pandas, FastAPI/TestClient, pytest, React, TypeScript, Vite, lightweight-charts, Vitest, Playwright.

---

## File Structure

Backend files:

- Create `src/stock_research/dashboard/platform.py`
  - Builds `/api/platform/summary`.
  - Queries latest market/factor dates, stock/factor coverage, score versions, and recent TopN preview.
- Create `src/stock_research/dashboard/strategy_catalog.py`
  - Static catalog for built-in strategies and statuses.
  - Keeps runnable/replay-only metadata out of frontend constants.
- Create `src/stock_research/dashboard/factors.py`
  - Factor library read model from `factor_registry.py`, `factor.factor_daily`, `factor.stock_score_daily`, and `manual_v1_config`.
  - In-memory factor score preview for selected factors and weights.
- Create `src/stock_research/dashboard/asset_profile.py`
  - Asset profile endpoint combining asset master, coverage, score, score components, factor values, bars, signals, decisions, outcomes, and reports.
- Create `src/stock_research/dashboard/backtests.py`
  - Read-only TopN backtest adapter around `load_vectorized_topn_inputs` and `run_vectorized_topn_backtest`.
  - Normalizes result payloads for frontend charts and tables.
- Modify `src/stock_research/dashboard/app.py`
  - Adds read-only routes:
    - `GET /api/platform/summary`
    - `GET /api/strategies/catalog`
    - `GET /api/factors/library`
    - `GET /api/factors/score-preview`
    - `GET /api/assets/{asset_id}/profile`
    - `GET /api/backtests/strategies`
    - `POST /api/backtests/run`
- Add tests:
  - `tests/test_dashboard_platform.py`
  - `tests/test_dashboard_strategy_catalog.py`
  - `tests/test_dashboard_factors.py`
  - `tests/test_dashboard_asset_profile.py`
  - `tests/test_dashboard_backtests.py`

Frontend files:

- Modify `dashboard/src/api/types.ts`
  - Adds platform, strategy catalog, factor library, score preview, asset profile, and backtest types.
- Modify `dashboard/src/api/client.ts`
  - Adds fetch clients for the new routes.
- Create `dashboard/src/components/AppShell.tsx`
  - Owns main navigation and workspace mode.
- Create `dashboard/src/components/HomeCockpit.tsx`
  - New default landing workspace.
- Create `dashboard/src/components/DataExplorerWorkspace.tsx`
  - Refactors existing research page behavior into a named asset inspection workspace.
- Create `dashboard/src/components/FactorLabWorkspace.tsx`
  - Factor selection, weight controls, score preview, and TopN candidate preview.
- Create `dashboard/src/components/BacktestLabWorkspace.tsx`
  - Strategy selector, run form, summary/equity/drawdown/positions/trades views.
- Create `dashboard/src/components/ReportsWorkspace.tsx`
  - Report filtering surface using existing report links.
- Modify `dashboard/src/App.tsx`
  - Thin wrapper around `AppShell`.
- Modify `dashboard/src/styles.css`
  - Adds navigation, cockpit, cards, workspace grids, factor table, and backtest result styles.
- Add tests:
  - `dashboard/tests/platform-client.test.ts`
  - `dashboard/tests/home-cockpit.test.tsx`
  - `dashboard/tests/data-explorer-workspace.test.tsx`
  - `dashboard/tests/factor-lab-workspace.test.tsx`
  - `dashboard/tests/backtest-lab-workspace.test.tsx`
  - `dashboard/tests/platform-full-flow.spec.ts`

---

## Task 1: Backend Strategy Catalog

**Files:**
- Create: `src/stock_research/dashboard/strategy_catalog.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_strategy_catalog.py`

- [ ] **Step 1: Write failing catalog tests**

Create `tests/test_dashboard_strategy_catalog.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.strategy_catalog import list_strategy_catalog


def test_strategy_catalog_marks_only_manual_v1_topn_as_runnable():
    rows = list_strategy_catalog()

    by_id = {row["strategy_id"]: row for row in rows}
    assert by_id["manual_v1_topn_rotation"]["status"] == "runnable"
    assert by_id["manual_v1_topn_rotation"]["primary_action"] == "Run backtest"
    assert by_id["lhb_shortline"]["status"] == "replay_only"
    assert by_id["mid_trend"]["status"] == "replay_only"
    assert by_id["tech_bottleneck"]["status"] == "replay_only"
    assert by_id["position_control"]["status"] == "replay_only"
    assert "momentum" in by_id["manual_v1_topn_rotation"]["factor_groups"]


def test_strategy_catalog_route_returns_items():
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/strategies/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) >= 5
    assert payload["items"][0]["strategy_id"] == "manual_v1_topn_rotation"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_strategy_catalog.py -q
```

Expected: FAIL because `stock_research.dashboard.strategy_catalog` does not exist.

- [ ] **Step 3: Implement catalog module**

Create `src/stock_research/dashboard/strategy_catalog.py`:

```python
from typing import Any


def list_strategy_catalog() -> list[dict[str, Any]]:
    return [
        {
            "strategy_id": "manual_v1_topn_rotation",
            "strategy_name": "Manual V1 TopN Rotation",
            "status": "runnable",
            "description": "Rank stocks by manual_v1 factor score and rebalance a TopN basket.",
            "factor_groups": ["momentum", "trend", "volume_price", "risk", "sector"],
            "signal_inputs": ["factor.stock_score_daily", "market_daily_bar"],
            "default_parameters": {
                "score_version": "manual_v1",
                "top_n": 20,
                "rebalance_frequency": "weekly",
                "max_positions": 20,
                "transaction_cost_bps": 10,
                "adjust_type": "hfq",
            },
            "latest_evidence": "",
            "primary_action": "Run backtest",
        },
        {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline",
            "status": "replay_only",
            "description": "Inspect LHB support/follow signals and shortline replay artifacts.",
            "factor_groups": [],
            "signal_inputs": ["LHB events", "support/follow signals", "daily bars"],
            "default_parameters": {},
            "latest_evidence": "strategy_validation",
            "primary_action": "Inspect evidence",
        },
        {
            "strategy_id": "mid_trend",
            "strategy_name": "Mid Trend Shortline",
            "status": "replay_only",
            "description": "Inspect trend protection, drawdown diagnostics, and mid-trend evidence.",
            "factor_groups": ["trend", "risk"],
            "signal_inputs": ["trend protection", "drawdown diagnostics", "market state"],
            "default_parameters": {},
            "latest_evidence": "strategy_validation",
            "primary_action": "Inspect evidence",
        },
        {
            "strategy_id": "tech_bottleneck",
            "strategy_name": "Tech Bottleneck Discovery",
            "status": "replay_only",
            "description": "Inspect bottleneck rank and technical condition evidence.",
            "factor_groups": ["trend", "volume_price", "risk"],
            "signal_inputs": ["bottleneck rank", "technical condition buckets"],
            "default_parameters": {},
            "latest_evidence": "strategy_validation",
            "primary_action": "Inspect evidence",
        },
        {
            "strategy_id": "position_control",
            "strategy_name": "Position Control Overlay",
            "status": "replay_only",
            "description": "Inspect risk budgets, exposure caps, and position snapshots.",
            "factor_groups": ["risk"],
            "signal_inputs": ["exposure cap", "risk budget", "drawdown state"],
            "default_parameters": {},
            "latest_evidence": "strategy_validation",
            "primary_action": "Inspect evidence",
        },
    ]
```

- [ ] **Step 4: Add route**

Modify `src/stock_research/dashboard/app.py`:

```python
from stock_research.dashboard.strategy_catalog import list_strategy_catalog
```

Inside `create_app()` before `return app`:

```python
    @app.get("/api/strategies/catalog")
    def strategies_catalog():
        return {"items": list_strategy_catalog()}
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_strategy_catalog.py -q
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/dashboard/strategy_catalog.py src/stock_research/dashboard/app.py tests/test_dashboard_strategy_catalog.py
git commit -m "feat: add strategy catalog API"
```

---

## Task 2: Backend Platform Summary

**Files:**
- Create: `src/stock_research/dashboard/platform.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_platform.py`

- [ ] **Step 1: Write failing platform summary tests**

Create `tests/test_dashboard_platform.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import platform


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_platform_summary_combines_coverage_and_topn(monkeypatch):
    calls = []

    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params=None):
        calls.append(sql)
        if "max(trade_date) AS latest_market_date" in sql:
            return [{"latest_market_date": "2026-06-08", "market_asset_count": 5207}]
        if "max(trade_date) AS latest_score_date" in sql:
            return [{"latest_score_date": "2026-06-08", "score_asset_count": 5207}]
        if "count(DISTINCT factor_name)" in sql:
            return [{"factor_count": 43, "latest_factor_date": "2026-06-08"}]
        if "SELECT DISTINCT score_version" in sql:
            return [{"score_version": "manual_v1"}]
        if "FROM factor.stock_score_daily" in sql:
            return [
                {
                    "trade_date": "2026-06-08",
                    "asset_id": "CN:SZ:300951",
                    "rank": 1,
                    "score_total": 89.9,
                    "score_version": "manual_v1",
                    "score_components": {"ret_20_score": 97.4},
                }
            ]
        raise AssertionError(sql)

    monkeypatch.setattr(platform, "connect", fake_connect)
    monkeypatch.setattr(platform, "fetch_all", fake_fetch_all)

    result = platform.load_platform_summary()

    assert result["latest_market_date"] == "2026-06-08"
    assert result["latest_score_date"] == "2026-06-08"
    assert result["market_asset_count"] == 5207
    assert result["factor_count"] == 43
    assert result["score_versions"] == ["manual_v1"]
    assert result["topn_preview"][0]["asset_id"] == "CN:SZ:300951"


def test_platform_summary_route(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_platform_summary",
        lambda: {"latest_market_date": "2026-06-08", "topn_preview": []},
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary")

    assert response.status_code == 200
    assert response.json()["latest_market_date"] == "2026-06-08"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_platform.py -q
```

Expected: FAIL because `stock_research.dashboard.platform` does not exist.

- [ ] **Step 3: Implement platform summary**

Create `src/stock_research/dashboard/platform.py`:

```python
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.scores import load_top_scores_for_dashboard
from stock_research.db import connect, fetch_all


def load_platform_summary(
    score_version: str = "manual_v1",
    top_n: int = 5,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    with connect(service) as conn:
        market = fetch_all(
            conn,
            """
            SELECT max(trade_date)::text AS latest_market_date,
                   count(DISTINCT asset_id) AS market_asset_count
            FROM market_daily_bar
            WHERE adjust_type = 'qfq'
              AND trade_date = (SELECT max(trade_date) FROM market_daily_bar WHERE adjust_type = 'qfq')
            """,
        )[0]
        score = fetch_all(
            conn,
            """
            SELECT max(trade_date)::text AS latest_score_date,
                   count(DISTINCT asset_id) AS score_asset_count
            FROM factor.stock_score_daily
            WHERE score_version = %s
              AND trade_date = (
                SELECT max(trade_date)
                FROM factor.stock_score_daily
                WHERE score_version = %s
              )
            """,
            [score_version, score_version],
        )[0]
        factors = fetch_all(
            conn,
            """
            SELECT count(DISTINCT factor_name) AS factor_count,
                   max(trade_date)::text AS latest_factor_date
            FROM factor.factor_daily
            """,
        )[0]
        versions = fetch_all(
            conn,
            """
            SELECT DISTINCT score_version
            FROM factor.stock_score_daily
            ORDER BY score_version
            """,
        )
    latest_score_date = str(score.get("latest_score_date") or "")
    topn_preview = (
        load_top_scores_for_dashboard(latest_score_date, score_version, top_n, service=service)
        if latest_score_date
        else []
    )
    return {
        "latest_market_date": str(market.get("latest_market_date") or ""),
        "latest_score_date": latest_score_date,
        "latest_factor_date": str(factors.get("latest_factor_date") or ""),
        "market_asset_count": int(market.get("market_asset_count") or 0),
        "score_asset_count": int(score.get("score_asset_count") or 0),
        "factor_count": int(factors.get("factor_count") or 0),
        "score_versions": [str(row["score_version"]) for row in versions],
        "topn_preview": topn_preview,
    }
```

- [ ] **Step 4: Add route**

Modify `src/stock_research/dashboard/app.py`:

```python
from stock_research.dashboard.platform import load_platform_summary
```

Inside `create_app()`:

```python
    @app.get("/api/platform/summary")
    def platform_summary(score_version: str = "manual_v1", top_n: int = 5):
        return load_platform_summary(score_version=score_version, top_n=top_n)
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_platform.py tests/test_dashboard_app.py -q
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/dashboard/platform.py src/stock_research/dashboard/app.py tests/test_dashboard_platform.py
git commit -m "feat: add platform summary API"
```

---

## Task 3: Backend Factor Library and Score Preview

**Files:**
- Create: `src/stock_research/dashboard/factors.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_factors.py`

- [ ] **Step 1: Write failing factor tests**

Create `tests/test_dashboard_factors.py`:

```python
import pandas as pd
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import factors


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_list_factor_library_marks_manual_v1_weights(monkeypatch):
    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params=None):
        return [
            {
                "factor_name": "ret_20",
                "latest_available_date": "2026-06-08",
                "coverage_count": 5207,
                "approval_status": "rejected",
            }
        ]

    monkeypatch.setattr(factors, "connect", fake_connect)
    monkeypatch.setattr(factors, "fetch_all", fake_fetch_all)

    rows = factors.list_factor_library()
    ret_20 = next(row for row in rows if row["factor_name"] == "ret_20")

    assert ret_20["factor_group"] == "momentum"
    assert ret_20["direction"] == "higher"
    assert ret_20["manual_v1_weight"] == 0.15
    assert ret_20["used_in_manual_v1"] is True
    assert ret_20["latest_available_date"] == "2026-06-08"


def test_build_factor_score_preview_scores_selected_factors(monkeypatch):
    frame = pd.DataFrame(
        [
            {"trade_date": "2026-06-08", "asset_id": "A", "factor_name": "ret_20", "factor_value": 2.0},
            {"trade_date": "2026-06-08", "asset_id": "B", "factor_name": "ret_20", "factor_value": 1.0},
            {"trade_date": "2026-06-08", "asset_id": "A", "factor_name": "volatility_20", "factor_value": 5.0},
            {"trade_date": "2026-06-08", "asset_id": "B", "factor_name": "volatility_20", "factor_value": 1.0},
        ]
    )

    monkeypatch.setattr(factors, "_load_factor_rows", lambda *args, **kwargs: frame)

    result = factors.build_factor_score_preview(
        trade_date="2026-06-08",
        selected_factors=[
            {"factor_name": "ret_20", "direction": "higher", "weight": 1.0},
            {"factor_name": "volatility_20", "direction": "lower", "weight": 1.0},
        ],
        top_n=2,
    )

    assert result["items"][0]["asset_id"] == "A"
    assert result["items"][0]["rank"] == 1
    assert result["items"][0]["score_total"] == 50.0
    assert result["selected_factors"][1]["factor_name"] == "volatility_20"


def test_factor_routes(monkeypatch):
    monkeypatch.setattr(dashboard_app, "list_factor_library", lambda: [{"factor_name": "ret_20"}])
    monkeypatch.setattr(
        dashboard_app,
        "build_factor_score_preview",
        lambda **kwargs: {"items": [], "selected_factors": kwargs["selected_factors"]},
    )
    client = TestClient(dashboard_app.create_app())

    library = client.get("/api/factors/library")
    preview = client.get(
        "/api/factors/score-preview",
        params={"trade_date": "2026-06-08", "factors": "ret_20:higher:1.0", "top_n": 5},
    )

    assert library.json()["items"][0]["factor_name"] == "ret_20"
    assert preview.status_code == 200
    assert preview.json()["selected_factors"][0]["factor_name"] == "ret_20"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_factors.py -q
```

Expected: FAIL because `stock_research.dashboard.factors` does not exist.

- [ ] **Step 3: Implement factor library and preview**

Create `src/stock_research/dashboard/factors.py`:

```python
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import manual_v1_config
from stock_research.factor_registry import list_factor_metadata
from stock_research.scoring import composite_score, rank_score
from stock_research.scoring.base import normalize_trade_keys


def list_factor_library(service: str = SETTINGS.research_service) -> list[dict[str, Any]]:
    config = manual_v1_config()
    weights = dict(config["weights"])
    coverage = _factor_coverage(service)
    rows = []
    for meta in list_factor_metadata():
        score_name = f"{meta.factor_name}_score"
        coverage_row = coverage.get(meta.factor_name, {})
        rows.append(
            {
                "factor_name": meta.factor_name,
                "factor_group": meta.factor_group,
                "direction": meta.direction,
                "description": meta.description,
                "source": meta.source,
                "calc_version": meta.calc_version,
                "status": str(coverage_row.get("approval_status") or meta.status),
                "availability_start_date": meta.availability_start_date,
                "availability_reason": meta.availability_reason,
                "latest_available_date": coverage_row.get("latest_available_date"),
                "coverage_count": int(coverage_row.get("coverage_count") or 0),
                "used_in_manual_v1": score_name in weights,
                "manual_v1_weight": weights.get(score_name),
            }
        )
    return rows


def build_factor_score_preview(
    trade_date: str,
    selected_factors: list[dict[str, Any]],
    top_n: int = 30,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    normalized = _normalize_selected_factors(selected_factors)
    factor_names = [row["factor_name"] for row in normalized]
    factor_rows = _load_factor_rows(trade_date, factor_names, service=service)
    if factor_rows.empty:
        return {"trade_date": trade_date, "selected_factors": normalized, "items": []}
    wide = (
        normalize_trade_keys(factor_rows)
        .pivot_table(index=["trade_date", "asset_id"], columns="factor_name", values="factor_value", aggfunc="first")
        .reset_index()
        .rename_axis(None, axis=1)
    )
    scored = wide
    weights: dict[str, float] = {}
    for row in normalized:
        factor_name = row["factor_name"]
        score_col = f"{factor_name}_score"
        scored = rank_score.rank_score_by_date(
            scored,
            value_col=factor_name,
            ascending=row["direction"] == "lower",
            output_col=score_col,
        )
        weights[score_col] = float(row["weight"])
    composite = composite_score.build_composite_scores(scored, weights=weights, score_version="preview")
    component_cols = list(weights)
    composite = composite.sort_values(["rank", "asset_id"]).head(top_n).copy()
    composite["score_components"] = composite[component_cols].to_dict("records")
    items = composite[["trade_date", "asset_id", "rank", "score_total", "score_components"]].to_dict("records")
    return {"trade_date": trade_date, "selected_factors": normalized, "items": items}


def parse_factor_selection(text: str) -> list[dict[str, Any]]:
    rows = []
    for raw in [item.strip() for item in text.split(",") if item.strip()]:
        parts = raw.split(":")
        if len(parts) != 3:
            raise ValueError("factor selection must use factor_name:direction:weight")
        rows.append({"factor_name": parts[0], "direction": parts[1], "weight": float(parts[2])})
    return rows


def _factor_coverage(service: str) -> dict[str, dict[str, Any]]:
    sql = """
    SELECT
        daily.factor_name,
        max(daily.trade_date)::text AS latest_available_date,
        count(*) AS coverage_count,
        max(approval.status) AS approval_status
    FROM factor.factor_daily daily
    LEFT JOIN factor.factor_approval approval
      ON approval.factor_name = daily.factor_name
     AND approval.calc_version = daily.calc_version
    GROUP BY daily.factor_name
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql)
    return {str(row["factor_name"]): dict(row) for row in rows}


def _load_factor_rows(trade_date: str, factor_names: list[str], service: str = SETTINGS.research_service) -> pd.DataFrame:
    if not factor_names:
        return pd.DataFrame(columns=["trade_date", "asset_id", "factor_name", "factor_value"])
    parameter_slots = ",".join(["%s"] * len(factor_names))
    sql = f"""
    SELECT trade_date, asset_id, factor_name, factor_value
    FROM factor.factor_daily
    WHERE trade_date = %s
      AND factor_name IN ({parameter_slots})
    ORDER BY asset_id, factor_name
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, *factor_names])
    return pd.DataFrame(rows)


def _normalize_selected_factors(selected_factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in selected_factors:
        direction = str(row["direction"])
        if direction not in {"higher", "lower"}:
            raise ValueError("factor direction must be higher or lower")
        weight = float(row["weight"])
        if weight < 0:
            raise ValueError("factor weight must be non-negative")
        rows.append({"factor_name": str(row["factor_name"]), "direction": direction, "weight": weight})
    if not rows:
        raise ValueError("at least one factor is required")
    return rows
```

- [ ] **Step 4: Add routes**

Modify `src/stock_research/dashboard/app.py` imports:

```python
from stock_research.dashboard.factors import (
    build_factor_score_preview,
    list_factor_library,
    parse_factor_selection,
)
```

Inside `create_app()`:

```python
    @app.get("/api/factors/library")
    def factor_library():
        return {"items": list_factor_library()}

    @app.get("/api/factors/score-preview")
    def factor_score_preview(trade_date: str, factors: str, top_n: int = 30):
        return build_factor_score_preview(
            trade_date=trade_date,
            selected_factors=parse_factor_selection(factors),
            top_n=top_n,
        )
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_factors.py -q
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/dashboard/factors.py src/stock_research/dashboard/app.py tests/test_dashboard_factors.py
git commit -m "feat: add factor library and score preview API"
```

---

## Task 4: Backend Asset Profile

**Files:**
- Create: `src/stock_research/dashboard/asset_profile.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_asset_profile.py`

- [ ] **Step 1: Write failing asset profile tests**

Create `tests/test_dashboard_asset_profile.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import asset_profile


def test_build_asset_profile_combines_existing_read_models(monkeypatch):
    monkeypatch.setattr(asset_profile, "load_asset_detail", lambda asset_id: {"asset_id": asset_id, "name": "平安银行"})
    monkeypatch.setattr(asset_profile, "load_daily_bars", lambda *args, **kwargs: [{"time": "2026-06-03"}])
    monkeypatch.setattr(asset_profile, "load_asset_score_for_dashboard", lambda *args, **kwargs: {"score_total": 88.5, "score_components": {"ret_20_score": 90}})
    monkeypatch.setattr(asset_profile, "load_asset_watchlist_signals_for_dashboard", lambda *args, **kwargs: [{"primary_signal": "watch"}])
    monkeypatch.setattr(asset_profile, "load_asset_decision_history", lambda *args, **kwargs: [{"decision_label": "candidate"}])
    monkeypatch.setattr(asset_profile, "load_asset_outcome_history", lambda *args, **kwargs: [{"outcome_status": "complete"}])
    monkeypatch.setattr(asset_profile, "_load_factor_values", lambda *args, **kwargs: [{"factor_name": "ret_20"}])
    monkeypatch.setattr(asset_profile, "_load_data_coverage", lambda *args, **kwargs: {"daily_bars": {"min_date": "1991-04-03", "max_date": "2026-06-08"}})

    profile = asset_profile.build_asset_profile(
        asset_id="000001.SZ",
        trade_date="2026-06-08",
        start_date="2026-06-01",
        end_date="2026-06-08",
    )

    assert profile["asset"]["asset_id"] == "000001.SZ"
    assert profile["bars"][0]["time"] == "2026-06-03"
    assert profile["score"]["score_total"] == 88.5
    assert profile["factor_values"][0]["factor_name"] == "ret_20"


def test_asset_profile_route(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_asset_profile",
        lambda **kwargs: {"asset_id": kwargs["asset_id"], "bars": []},
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/assets/000001.SZ/profile",
        params={"trade_date": "2026-06-08", "start_date": "2026-06-01", "end_date": "2026-06-08"},
    )

    assert response.status_code == 200
    assert response.json()["asset_id"] == "000001.SZ"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_asset_profile.py -q
```

Expected: FAIL because `stock_research.dashboard.asset_profile` does not exist.

- [ ] **Step 3: Implement asset profile**

Create `src/stock_research/dashboard/asset_profile.py`:

```python
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.bars import load_daily_bars, normalize_market_asset_id
from stock_research.dashboard.decisions import load_asset_decision_history
from stock_research.dashboard.outcomes import load_asset_outcome_history
from stock_research.dashboard.scores import load_asset_detail, load_asset_score_for_dashboard
from stock_research.dashboard.watchlist import load_asset_watchlist_signals_for_dashboard
from stock_research.db import connect, fetch_all


def build_asset_profile(
    asset_id: str,
    trade_date: str,
    start_date: str,
    end_date: str,
    score_version: str = "manual_v1",
    adjust_type: str = "qfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "canonical_asset_id": normalize_market_asset_id(asset_id),
        "asset": load_asset_detail(normalize_market_asset_id(asset_id)) or load_asset_detail(asset_id),
        "bars": load_daily_bars(asset_id, start_date, end_date, adjust_type, service=service),
        "score": load_asset_score_for_dashboard(normalize_market_asset_id(asset_id), trade_date, score_version, service=service),
        "signals": load_asset_watchlist_signals_for_dashboard(asset_id, trade_date),
        "decisions": load_asset_decision_history(asset_id, start_date, end_date, limit=50),
        "outcomes": load_asset_outcome_history(asset_id, start_date, end_date, limit=50),
        "factor_values": _load_factor_values(normalize_market_asset_id(asset_id), trade_date, service=service),
        "coverage": _load_data_coverage(normalize_market_asset_id(asset_id), service=service),
    }


def _load_factor_values(asset_id: str, trade_date: str, service: str = SETTINGS.research_service) -> list[dict[str, Any]]:
    sql = """
    SELECT factor_name, factor_group, factor_value, calc_version, source, source_data_version
    FROM factor.factor_daily
    WHERE asset_id = %s
      AND trade_date = %s
    ORDER BY factor_group, factor_name
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, [asset_id, trade_date])


def _load_data_coverage(asset_id: str, service: str = SETTINGS.research_service) -> dict[str, Any]:
    sql = """
    SELECT min(trade_date)::text AS min_date,
           max(trade_date)::text AS max_date,
           count(*) AS row_count
    FROM market_daily_bar
    WHERE asset_id = %s
      AND adjust_type = 'qfq'
    """
    factor_sql = """
    SELECT max(trade_date)::text AS latest_factor_date,
           count(DISTINCT factor_name) AS factor_count
    FROM factor.factor_daily
    WHERE asset_id = %s
    """
    with connect(service) as conn:
        bars = fetch_all(conn, sql, [asset_id])[0]
        factors = fetch_all(conn, factor_sql, [asset_id])[0]
    return {"daily_bars": dict(bars), "factors": dict(factors)}
```

- [ ] **Step 4: Add route**

Modify `src/stock_research/dashboard/app.py` imports:

```python
from stock_research.dashboard.asset_profile import build_asset_profile
```

Inside `create_app()`:

```python
    @app.get("/api/assets/{asset_id}/profile")
    def asset_profile_route(
        asset_id: str,
        trade_date: str,
        start_date: str,
        end_date: str,
        score_version: str = "manual_v1",
        adjust_type: str = "qfq",
    ):
        return build_asset_profile(
            asset_id=asset_id,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            score_version=score_version,
            adjust_type=adjust_type,
        )
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_asset_profile.py tests/test_dashboard_bars.py -q
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/dashboard/asset_profile.py src/stock_research/dashboard/app.py tests/test_dashboard_asset_profile.py
git commit -m "feat: add asset profile API"
```

---

## Task 5: Backend Backtest Lab API

**Files:**
- Create: `src/stock_research/dashboard/backtests.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_backtests.py`

- [ ] **Step 1: Write failing backtest API tests**

Create `tests/test_dashboard_backtests.py`:

```python
import pandas as pd
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import backtests
from stock_research.vectorized_topn_backtest import VectorizedTopNConfig, VectorizedTopNResult


def test_list_backtest_strategies_only_marks_topn_runnable():
    rows = backtests.list_backtest_strategies()

    by_id = {row["strategy_id"]: row for row in rows}
    assert by_id["manual_v1_topn_rotation"]["status"] == "runnable"
    assert by_id["lhb_shortline"]["status"] == "replay_only"


def test_run_topn_backtest_returns_json_safe_payload(monkeypatch):
    result = VectorizedTopNResult(
        config=VectorizedTopNConfig(start_date="2026-06-01", end_date="2026-06-05", top_n=2),
        equity_curve=pd.DataFrame(
            [{"date": "2026-06-02", "equity": 1.02, "drawdown": 0.0, "turnover": 0.5, "net_return": 0.02}]
        ),
        positions=pd.DataFrame([{"rebalance_date": "2026-06-01", "asset_id": "A", "rank": 1, "score_total": 90, "weight": 0.5}]),
        trades=pd.DataFrame([{"execution_date": "2026-06-02", "asset_id": "A", "side": "buy", "executed_weight": 0.5}]),
        summary={"total_return": 0.02, "max_drawdown": 0.0, "average_turnover": 0.5, "periods": 1},
    )

    monkeypatch.setattr(backtests, "load_vectorized_topn_inputs", lambda **kwargs: (pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(backtests, "run_vectorized_topn_backtest", lambda scores, prices, config: result)

    payload = backtests.run_backtest(
        {
            "strategy_id": "manual_v1_topn_rotation",
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "top_n": 2,
            "rebalance_frequency": "daily",
            "transaction_cost_bps": 10,
            "max_positions": 2,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        }
    )

    assert payload["strategy_id"] == "manual_v1_topn_rotation"
    assert payload["summary"]["total_return"] == 0.02
    assert payload["equity_curve"][0]["equity"] == 1.02
    assert payload["read_only"] is True


def test_backtest_routes(monkeypatch):
    monkeypatch.setattr(dashboard_app, "list_backtest_strategies", lambda: [{"strategy_id": "manual_v1_topn_rotation"}])
    monkeypatch.setattr(dashboard_app, "run_backtest", lambda payload: {"strategy_id": payload["strategy_id"], "read_only": True})
    client = TestClient(dashboard_app.create_app())

    strategies = client.get("/api/backtests/strategies")
    result = client.post(
        "/api/backtests/run",
        json={
            "strategy_id": "manual_v1_topn_rotation",
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "top_n": 2,
            "rebalance_frequency": "daily",
            "transaction_cost_bps": 10,
            "max_positions": 2,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        },
    )

    assert strategies.status_code == 200
    assert result.json()["read_only"] is True
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_backtests.py -q
```

Expected: FAIL because `stock_research.dashboard.backtests` does not exist.

- [ ] **Step 3: Implement backtest adapter**

Create `src/stock_research/dashboard/backtests.py`:

```python
from typing import Any

import pandas as pd

from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    load_vectorized_topn_inputs,
    run_vectorized_topn_backtest,
)
from stock_research.dashboard.strategy_catalog import list_strategy_catalog


def list_backtest_strategies() -> list[dict[str, Any]]:
    return list_strategy_catalog()


def run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    strategy_id = str(payload["strategy_id"])
    if strategy_id != "manual_v1_topn_rotation":
        raise ValueError("only manual_v1_topn_rotation is runnable in this version")
    scores, prices = load_vectorized_topn_inputs(
        start_date=str(payload["start_date"]),
        end_date=str(payload["end_date"]),
        score_version=str(payload.get("score_version") or "manual_v1"),
        adjust_type=str(payload.get("adjust_type") or "hfq"),
    )
    config = VectorizedTopNConfig(
        start_date=str(payload["start_date"]),
        end_date=str(payload["end_date"]),
        top_n=int(payload.get("top_n") or 20),
        rebalance_frequency=str(payload.get("rebalance_frequency") or "weekly"),
        transaction_cost_bps=float(payload.get("transaction_cost_bps") or 0.0),
        max_positions=_optional_int(payload.get("max_positions")),
    )
    result = run_vectorized_topn_backtest(scores, prices, config)
    return {
        "strategy_id": strategy_id,
        "strategy_name": "Manual V1 TopN Rotation",
        "read_only": True,
        "config": {
            "start_date": str(config.start_date),
            "end_date": str(config.end_date),
            "score_version": str(payload.get("score_version") or "manual_v1"),
            "top_n": config.top_n,
            "rebalance_frequency": config.rebalance_frequency,
            "transaction_cost_bps": config.transaction_cost_bps,
            "max_positions": config.max_positions,
            "adjust_type": str(payload.get("adjust_type") or "hfq"),
        },
        "summary": _json_records(result.summary),
        "equity_curve": _frame_records(result.equity_curve),
        "positions": _frame_records(result.positions),
        "trades": _frame_records(result.trades),
    }


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [_json_records(row) for row in frame.to_dict("records")]


def _json_records(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_records(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_records(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
```

- [ ] **Step 4: Add routes**

Modify `src/stock_research/dashboard/app.py` imports:

```python
from stock_research.dashboard.backtests import list_backtest_strategies, run_backtest
```

Inside `create_app()`:

```python
    @app.get("/api/backtests/strategies")
    def backtest_strategies():
        return {"items": list_backtest_strategies()}

    @app.post("/api/backtests/run")
    def backtest_run(payload: dict):
        try:
            return run_backtest(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_backtests.py -q
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/dashboard/backtests.py src/stock_research/dashboard/app.py tests/test_dashboard_backtests.py
git commit -m "feat: add backtest lab API"
```

---

## Task 6: Frontend Types and API Clients

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Test: `dashboard/tests/platform-client.test.ts`

- [ ] **Step 1: Write failing client tests**

Create `dashboard/tests/platform-client.test.ts`:

```typescript
import { afterEach, describe, expect, it, vi } from 'vitest';

describe('platform API clients', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches platform summary and strategy catalog', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({ ok: true, json: async () => ({ latest_market_date: '2026-06-08' }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ strategy_id: 'manual_v1_topn_rotation' }] }) } as Response);
    const { fetchPlatformSummary, fetchStrategyCatalog } = await import('../src/api/client');

    const summary = await fetchPlatformSummary();
    const catalog = await fetchStrategyCatalog();

    expect(summary.latest_market_date).toBe('2026-06-08');
    expect(catalog[0].strategy_id).toBe('manual_v1_topn_rotation');
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/platform/summary');
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/strategies/catalog');
  });

  it('fetches factor library, score preview, asset profile, and backtest result', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ factor_name: 'ret_20' }] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ asset_id: 'A' }], selected_factors: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ asset_id: '000001.SZ', bars: [] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ strategy_id: 'manual_v1_topn_rotation' }] }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ strategy_id: 'manual_v1_topn_rotation', read_only: true }) } as Response);
    const {
      fetchFactorLibrary,
      fetchFactorScorePreview,
      fetchAssetProfile,
      fetchBacktestStrategies,
      runBacktest
    } = await import('../src/api/client');

    await fetchFactorLibrary();
    await fetchFactorScorePreview('2026-06-08', [{ factor_name: 'ret_20', direction: 'higher', weight: 1 }], 10);
    await fetchAssetProfile('000001.SZ', '2026-06-08', '2026-06-01', '2026-06-08');
    await fetchBacktestStrategies();
    const result = await runBacktest({
      strategy_id: 'manual_v1_topn_rotation',
      start_date: '2026-06-01',
      end_date: '2026-06-08',
      top_n: 20,
      rebalance_frequency: 'weekly',
      transaction_cost_bps: 10,
      max_positions: 20,
      score_version: 'manual_v1',
      adjust_type: 'hfq'
    });

    expect(result.read_only).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });
});
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd dashboard
pnpm vitest run tests/platform-client.test.ts
```

Expected: FAIL because the new client functions are not exported.

- [ ] **Step 3: Add TypeScript types**

Append to `dashboard/src/api/types.ts`:

```typescript
export type PlatformSummary = {
  latest_market_date: string;
  latest_score_date: string;
  latest_factor_date: string;
  market_asset_count: number;
  score_asset_count: number;
  factor_count: number;
  score_versions: string[];
  topn_preview: ScoreRow[];
};

export type StrategyCatalogItem = {
  strategy_id: string;
  strategy_name: string;
  status: 'runnable' | 'replay_only' | 'planned' | string;
  description: string;
  factor_groups: string[];
  signal_inputs: string[];
  default_parameters: Record<string, unknown>;
  latest_evidence: string;
  primary_action: string;
};

export type FactorLibraryRow = {
  factor_name: string;
  factor_group: string;
  direction: 'higher' | 'lower' | string;
  description: string;
  source: string;
  calc_version: string;
  status: string;
  availability_start_date: string | null;
  availability_reason: string | null;
  latest_available_date: string | null;
  coverage_count: number;
  used_in_manual_v1: boolean;
  manual_v1_weight: number | null;
};

export type FactorSelection = {
  factor_name: string;
  direction: 'higher' | 'lower';
  weight: number;
};

export type FactorScorePreview = {
  trade_date: string;
  selected_factors: FactorSelection[];
  items: Array<{
    trade_date: string;
    asset_id: string;
    rank: number;
    score_total: number;
    score_components: Record<string, number | null>;
  }>;
};

export type AssetProfile = {
  asset_id: string;
  canonical_asset_id: string;
  asset: AssetSummary | null;
  bars: BarPoint[];
  score: ScoreRow | null;
  signals: WatchlistSignalRow[];
  decisions: DecisionEventRow[];
  outcomes: DecisionOutcomeRow[];
  factor_values: Array<Record<string, unknown>>;
  coverage: Record<string, unknown>;
};

export type BacktestRunRequest = {
  strategy_id: string;
  start_date: string;
  end_date: string;
  score_version: string;
  top_n: number;
  rebalance_frequency: 'daily' | 'weekly';
  transaction_cost_bps: number;
  max_positions: number | null;
  adjust_type: string;
};

export type BacktestRunResult = {
  strategy_id: string;
  strategy_name: string;
  read_only: boolean;
  config: Record<string, unknown>;
  summary: Record<string, number | string | null>;
  equity_curve: Array<Record<string, number | string | null>>;
  positions: Array<Record<string, number | string | null>>;
  trades: Array<Record<string, number | string | null>>;
};
```

- [ ] **Step 4: Add API clients**

Modify `dashboard/src/api/client.ts` imports to include new types.

Append client functions before `getJson`:

```typescript
export async function fetchPlatformSummary(): Promise<PlatformSummary> {
  return getJson<PlatformSummary>('/api/platform/summary');
}

export async function fetchStrategyCatalog(): Promise<StrategyCatalogItem[]> {
  const payload = await getJson<{ items: StrategyCatalogItem[] }>('/api/strategies/catalog');
  return payload.items;
}

export async function fetchFactorLibrary(): Promise<FactorLibraryRow[]> {
  const payload = await getJson<{ items: FactorLibraryRow[] }>('/api/factors/library');
  return payload.items;
}

export async function fetchFactorScorePreview(
  tradeDate: string,
  factors: FactorSelection[],
  topN: number
): Promise<FactorScorePreview> {
  const encodedFactors = factors
    .map((factor) => `${factor.factor_name}:${factor.direction}:${factor.weight}`)
    .join(',');
  return getJson<FactorScorePreview>(
    `/api/factors/score-preview?trade_date=${encodeURIComponent(tradeDate)}` +
      `&factors=${encodeURIComponent(encodedFactors)}&top_n=${topN}`
  );
}

export async function fetchAssetProfile(
  assetId: string,
  tradeDate: string,
  startDate: string,
  endDate: string,
  scoreVersion = 'manual_v1',
  adjustType = 'qfq'
): Promise<AssetProfile> {
  return getJson<AssetProfile>(
    `/api/assets/${encodeURIComponent(assetId)}/profile?trade_date=${encodeURIComponent(tradeDate)}` +
      `&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}` +
      `&score_version=${encodeURIComponent(scoreVersion)}&adjust_type=${encodeURIComponent(adjustType)}`
  );
}

export async function fetchBacktestStrategies(): Promise<StrategyCatalogItem[]> {
  const payload = await getJson<{ items: StrategyCatalogItem[] }>('/api/backtests/strategies');
  return payload.items;
}

export async function runBacktest(request: BacktestRunRequest): Promise<BacktestRunResult> {
  const response = await fetch('/api/backtests/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!response.ok) {
    throw new Error(`POST /api/backtests/run failed with ${response.status}`);
  }
  return response.json() as Promise<BacktestRunResult>;
}
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
cd dashboard
pnpm vitest run tests/platform-client.test.ts
pnpm test
```

Expected: PASS.

Commit:

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/platform-client.test.ts
git commit -m "feat: add platform frontend API client"
```

---

## Task 7: Frontend App Shell and Home Cockpit

**Files:**
- Create: `dashboard/src/components/AppShell.tsx`
- Create: `dashboard/src/components/HomeCockpit.tsx`
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/home-cockpit.test.tsx`

- [ ] **Step 1: Write failing Home tests**

Create `dashboard/tests/home-cockpit.test.tsx`:

```typescript
import '@testing-library/jest-dom/vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from '../src/components/AppShell';

vi.mock('../src/api/client', () => ({
  fetchPlatformSummary: vi.fn(),
  fetchStrategyCatalog: vi.fn(),
  fetchOverview: vi.fn(),
  fetchDailyBars: vi.fn(),
  fetchAssetScore: vi.fn(),
  fetchAssetSignals: vi.fn(),
  fetchAssetDecisions: vi.fn(),
  fetchAssetOutcomes: vi.fn(),
  fetchOutcomeAnalytics: vi.fn(),
  fetchExperimentProposals: vi.fn(),
  fetchExperimentReplay: vi.fn(),
  fetchShadowWatchlist: vi.fn(),
  fetchShadowOutcomes: vi.fn(),
  fetchShadowOutcomeAnalytics: vi.fn(),
  fetchShadowAnalyticsReview: vi.fn(),
  fetchShadowReviewDecisions: vi.fn(),
  fetchShadowFollowUpQueue: vi.fn(),
  fetchShadowFollowUpResolution: vi.fn(),
  fetchStrategyValidationRuns: vi.fn(),
  fetchStrategyValidationReplay: vi.fn()
}));

import * as api from '../src/api/client';

describe('AppShell and HomeCockpit', () => {
  beforeEach(() => {
    vi.mocked(api.fetchPlatformSummary).mockResolvedValue({
      latest_market_date: '2026-06-08',
      latest_score_date: '2026-06-08',
      latest_factor_date: '2026-06-08',
      market_asset_count: 5207,
      score_asset_count: 5207,
      factor_count: 43,
      score_versions: ['manual_v1'],
      topn_preview: [{ trade_date: '2026-06-08', asset_id: 'CN:SZ:300951', rank: 1, score_total: 89.9, score_version: 'manual_v1', score_components: {} }]
    });
    vi.mocked(api.fetchStrategyCatalog).mockResolvedValue([
      {
        strategy_id: 'manual_v1_topn_rotation',
        strategy_name: 'Manual V1 TopN Rotation',
        status: 'runnable',
        description: 'TopN rotation',
        factor_groups: ['momentum'],
        signal_inputs: ['factor.stock_score_daily'],
        default_parameters: { top_n: 20 },
        latest_evidence: '',
        primary_action: 'Run backtest'
      }
    ]);
  });

  it('renders platform summary and strategy entry points', async () => {
    render(<AppShell />);

    expect(await screen.findByText('Research Cockpit')).toBeVisible();
    expect(screen.getByText('Latest Market Data')).toBeVisible();
    expect(screen.getByText('2026-06-08')).toBeVisible();
    expect(screen.getByText('Manual V1 TopN Rotation')).toBeVisible();
    expect(screen.getByText('candidate pool, not buy signal')).toBeVisible();
  });

  it('navigates to Data Explorer from Home', async () => {
    render(<AppShell />);
    await screen.findByText('Research Cockpit');

    await userEvent.click(screen.getByRole('button', { name: 'Data Explorer' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Data Explorer' })).toBeVisible());
  });
});
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd dashboard
pnpm vitest run tests/home-cockpit.test.tsx
```

Expected: FAIL because `AppShell` does not exist.

- [ ] **Step 3: Implement HomeCockpit**

Create `dashboard/src/components/HomeCockpit.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { fetchPlatformSummary, fetchStrategyCatalog } from '../api/client';
import type { PlatformSummary, StrategyCatalogItem } from '../api/types';

type HomeCockpitProps = {
  onNavigate: (mode: string) => void;
};

export function HomeCockpit({ onNavigate }: HomeCockpitProps) {
  const [summary, setSummary] = useState<PlatformSummary | null>(null);
  const [strategies, setStrategies] = useState<StrategyCatalogItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    Promise.all([fetchPlatformSummary(), fetchStrategyCatalog()])
      .then(([summaryPayload, strategyRows]) => {
        if (!ignore) {
          setSummary(summaryPayload);
          setStrategies(strategyRows);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <section className="home-cockpit">
      <header className="workspace-header">
        <h1>Research Cockpit</h1>
        <p className="muted">Read-only quant research workspace.</p>
      </header>
      <nav className="quick-actions" aria-label="platform workspaces">
        <button type="button" onClick={() => onNavigate('data')}>Data Explorer</button>
        <button type="button" onClick={() => onNavigate('factors')}>Factor Lab</button>
        <button type="button" onClick={() => onNavigate('backtests')}>Backtest Lab</button>
        <button type="button" onClick={() => onNavigate('strategy')}>Strategy Validation</button>
        <button type="button" onClick={() => onNavigate('reports')}>Reports</button>
      </nav>
      {error ? <p className="error-text">{error}</p> : null}
      <section className="cockpit-grid">
        <div className="metric-card"><span>Latest Market Data</span><strong>{summary?.latest_market_date ?? '-'}</strong></div>
        <div className="metric-card"><span>Latest Factor Score</span><strong>{summary?.latest_score_date ?? '-'}</strong></div>
        <div className="metric-card"><span>Stock Coverage</span><strong>{summary?.market_asset_count ?? '-'}</strong></div>
        <div className="metric-card"><span>Factor Coverage</span><strong>{summary?.factor_count ?? '-'}</strong></div>
      </section>
      <section className="workspace-band">
        <h2>Built-in Strategies</h2>
        <div className="strategy-card-grid">
          {strategies.map((strategy) => (
            <div className="strategy-summary-card" key={strategy.strategy_id}>
              <strong>{strategy.strategy_name}</strong>
              <span>{strategy.status}</span>
              <small>{strategy.description}</small>
              <small>{strategy.factor_groups.join(', ') || strategy.signal_inputs.join(', ')}</small>
            </div>
          ))}
        </div>
      </section>
      <section className="workspace-band">
        <h2>Recent TopN Preview</h2>
        <p className="muted">candidate pool, not buy signal</p>
        <div className="dense-list">
          {(summary?.topn_preview ?? []).map((row) => (
            <div className="list-row" key={row.asset_id}>
              <span>{row.rank}</span>
              <strong>{row.asset_id}</strong>
              <span>{row.score_total.toFixed(1)}</span>
            </div>
          ))}
        </div>
      </section>
    </section>
  );
}
```

- [ ] **Step 4: Implement AppShell and thin App wrapper**

Create `dashboard/src/components/AppShell.tsx`:

```tsx
import { useState } from 'react';
import { HomeCockpit } from './HomeCockpit';
import { StrategyValidationWorkspace } from './StrategyValidationWorkspace';

type WorkspaceMode = 'home' | 'data' | 'factors' | 'backtests' | 'strategy' | 'reports';

export function AppShell() {
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>('home');

  return (
    <main className="platform-shell">
      <aside className="platform-nav">
        <div className="panel-title">Stock Research</div>
        {[
          ['home', 'Home'],
          ['data', 'Data Explorer'],
          ['factors', 'Factor Lab'],
          ['backtests', 'Backtest Lab'],
          ['strategy', 'Strategy Validation'],
          ['reports', 'Reports']
        ].map(([mode, label]) => (
          <button
            type="button"
            key={mode}
            className={workspaceMode === mode ? 'active' : ''}
            onClick={() => setWorkspaceMode(mode as WorkspaceMode)}
          >
            {label}
          </button>
        ))}
      </aside>
      <section className="platform-workspace">
        {workspaceMode === 'home' ? <HomeCockpit onNavigate={(mode) => setWorkspaceMode(mode as WorkspaceMode)} /> : null}
        {workspaceMode === 'data' ? <h1>Data Explorer</h1> : null}
        {workspaceMode === 'factors' ? <h1>Factor Lab</h1> : null}
        {workspaceMode === 'backtests' ? <h1>Backtest Lab</h1> : null}
        {workspaceMode === 'strategy' ? <StrategyValidationWorkspace /> : null}
        {workspaceMode === 'reports' ? <h1>Reports</h1> : null}
      </section>
    </main>
  );
}
```

Replace `dashboard/src/App.tsx` with:

```tsx
import { AppShell } from './components/AppShell';

export function App() {
  return <AppShell />;
}
```

- [ ] **Step 5: Add minimum shell styles**

Append to `dashboard/src/styles.css`:

```css
.platform-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  background: #f7f8fa;
}

.platform-nav {
  border-right: 1px solid #d9dde3;
  background: #ffffff;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.platform-nav button,
.quick-actions button {
  border: 1px solid #cbd2dc;
  background: #ffffff;
  color: #172033;
  border-radius: 6px;
  padding: 8px 10px;
  text-align: left;
}

.platform-nav button.active {
  background: #172033;
  color: #ffffff;
}

.platform-workspace {
  min-width: 0;
  padding: 18px;
}

.workspace-header h1 {
  margin: 0 0 4px;
  font-size: 24px;
}

.quick-actions,
.cockpit-grid,
.strategy-card-grid {
  display: grid;
  gap: 10px;
}

.quick-actions {
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  margin: 14px 0;
}

.cockpit-grid {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.metric-card,
.workspace-band {
  background: #ffffff;
  border: 1px solid #d9dde3;
  border-radius: 6px;
  padding: 12px;
}

.metric-card {
  display: grid;
  gap: 4px;
}

.metric-card span {
  color: #667085;
  font-size: 12px;
}

.metric-card strong {
  font-size: 20px;
}

.workspace-band {
  margin-top: 14px;
}

@media (max-width: 760px) {
  .platform-shell {
    grid-template-columns: 1fr;
  }

  .platform-nav {
    position: static;
    border-right: 0;
    border-bottom: 1px solid #d9dde3;
  }
}
```

- [ ] **Step 6: Verify and commit**

Run:

```bash
cd dashboard
pnpm vitest run tests/home-cockpit.test.tsx
pnpm test
pnpm build
```

Expected: PASS.

Commit:

```bash
git add dashboard/src/App.tsx dashboard/src/components/AppShell.tsx dashboard/src/components/HomeCockpit.tsx dashboard/src/styles.css dashboard/tests/home-cockpit.test.tsx
git commit -m "feat: add research cockpit shell"
```

---

## Task 8: Frontend Data Explorer Workspace

**Files:**
- Create: `dashboard/src/components/DataExplorerWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/data-explorer-workspace.test.tsx`

- [ ] **Step 1: Write failing Data Explorer tests**

Create `dashboard/tests/data-explorer-workspace.test.tsx`:

```typescript
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DataExplorerWorkspace } from '../src/components/DataExplorerWorkspace';

vi.mock('../src/api/client', () => ({
  fetchAssetProfile: vi.fn()
}));

import { fetchAssetProfile } from '../src/api/client';

describe('DataExplorerWorkspace', () => {
  beforeEach(() => {
    vi.mocked(fetchAssetProfile).mockResolvedValue({
      asset_id: '000001.SZ',
      canonical_asset_id: 'CN:SZ:000001',
      asset: { asset_id: 'CN:SZ:000001', symbol: '000001', name: '平安银行', exchange: 'SZ', board: null, is_active: true },
      bars: [{ time: '2026-06-03', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }],
      score: { trade_date: '2026-06-08', asset_id: 'CN:SZ:000001', rank: 12, score_total: 88.5, score_version: 'manual_v1', score_components: { ret_20_score: 90 } },
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: [{ factor_group: 'momentum', factor_name: 'ret_20', factor_value: 0.12 }],
      coverage: { daily_bars: { min_date: '1991-04-03', max_date: '2026-06-08' } }
    });
  });

  it('loads one asset profile and shows data coverage, score, and factors', async () => {
    render(<DataExplorerWorkspace />);

    expect(await screen.findByRole('heading', { name: 'Data Explorer' })).toBeVisible();
    expect(await screen.findByText('平安银行')).toBeVisible();
    expect(screen.getByText('CN:SZ:000001')).toBeVisible();
    expect(screen.getByText('Score 88.5')).toBeVisible();
    expect(screen.getByText('ret_20')).toBeVisible();
    expect(screen.getByText('1991-04-03')).toBeVisible();
  });

  it('reloads when asset id changes', async () => {
    render(<DataExplorerWorkspace />);
    await screen.findByText('平安银行');

    await userEvent.clear(screen.getByLabelText('asset id'));
    await userEvent.type(screen.getByLabelText('asset id'), '600000.SH');
    await userEvent.click(screen.getByRole('button', { name: 'Load Asset' }));

    expect(fetchAssetProfile).toHaveBeenLastCalledWith('600000.SH', expect.any(String), expect.any(String), expect.any(String), 'manual_v1', 'qfq');
  });
});
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd dashboard
pnpm vitest run tests/data-explorer-workspace.test.tsx
```

Expected: FAIL because `DataExplorerWorkspace` does not exist.

- [ ] **Step 3: Implement workspace**

Create `dashboard/src/components/DataExplorerWorkspace.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react';
import { fetchAssetProfile } from '../api/client';
import type { AssetProfile } from '../api/types';
import { AssetChart } from '../charts/AssetChart';

const DEFAULT_ASSET_ID = '000001.SZ';
const DEFAULT_TRADE_DATE = '2026-06-08';

function dateNDaysBefore(dateText: string, days: number) {
  const [year, month, day] = dateText.split('-').map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() - days);
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
}

export function DataExplorerWorkspace() {
  const [assetId, setAssetId] = useState(DEFAULT_ASSET_ID);
  const [tradeDate, setTradeDate] = useState(DEFAULT_TRADE_DATE);
  const [adjustType, setAdjustType] = useState('qfq');
  const [profile, setProfile] = useState<AssetProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const startDate = useMemo(() => dateNDaysBefore(tradeDate, 180), [tradeDate]);

  function load() {
    setError(null);
    fetchAssetProfile(assetId, tradeDate, startDate, tradeDate, 'manual_v1', adjustType)
      .then(setProfile)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <section className="data-explorer">
      <header className="workspace-header">
        <h1>Data Explorer</h1>
        <p className="muted">Inspect one stock across bars, scores, factors, signals, decisions, and coverage.</p>
      </header>
      <div className="toolbar">
        <input aria-label="asset id" value={assetId} onChange={(event) => setAssetId(event.target.value.trim())} />
        <input aria-label="trade date" type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
        <select aria-label="adjust type" value={adjustType} onChange={(event) => setAdjustType(event.target.value)}>
          <option value="qfq">qfq</option>
          <option value="hfq">hfq</option>
        </select>
        <button type="button" onClick={load}>Load Asset</button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      {profile ? (
        <div className="data-grid">
          <section className="workspace-band">
            <h2>{profile.asset?.name ?? profile.asset_id}</h2>
            <p>{profile.canonical_asset_id}</p>
            <p>{profile.asset?.exchange ?? ''} {profile.asset?.symbol ?? ''}</p>
          </section>
          <section className="workspace-band">
            <h2>Score</h2>
            {profile.score ? <strong>Score {profile.score.score_total.toFixed(1)}</strong> : <p className="muted">No score.</p>}
            <pre>{JSON.stringify(profile.score?.score_components ?? {}, null, 2)}</pre>
          </section>
          <section className="workspace-band wide">
            <h2>Daily Bars</h2>
            {profile.bars.length > 0 ? <AssetChart bars={profile.bars} /> : <p className="muted">No bars for selected range.</p>}
          </section>
          <section className="workspace-band">
            <h2>Coverage</h2>
            <pre>{JSON.stringify(profile.coverage, null, 2)}</pre>
          </section>
          <section className="workspace-band">
            <h2>Factors</h2>
            <table className="strategy-table">
              <tbody>
                {profile.factor_values.map((row, index) => (
                  <tr key={`${row.factor_name}-${index}`}>
                    <td>{String(row.factor_group ?? '')}</td>
                    <td>{String(row.factor_name ?? '')}</td>
                    <td>{String(row.factor_value ?? '')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      ) : (
        <p className="muted">Loading asset profile...</p>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Wire into AppShell**

Modify `dashboard/src/components/AppShell.tsx`:

```tsx
import { DataExplorerWorkspace } from './DataExplorerWorkspace';
```

Replace the temporary Data Explorer heading:

```tsx
{workspaceMode === 'data' ? <DataExplorerWorkspace /> : null}
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
cd dashboard
pnpm vitest run tests/data-explorer-workspace.test.tsx
pnpm test
```

Expected: PASS.

Commit:

```bash
git add dashboard/src/components/DataExplorerWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/src/styles.css dashboard/tests/data-explorer-workspace.test.tsx
git commit -m "feat: add data explorer workspace"
```

---

## Task 9: Frontend Factor Lab Workspace

**Files:**
- Create: `dashboard/src/components/FactorLabWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/factor-lab-workspace.test.tsx`

- [ ] **Step 1: Write failing Factor Lab tests**

Create `dashboard/tests/factor-lab-workspace.test.tsx`:

```typescript
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FactorLabWorkspace } from '../src/components/FactorLabWorkspace';

vi.mock('../src/api/client', () => ({
  fetchFactorLibrary: vi.fn(),
  fetchFactorScorePreview: vi.fn()
}));

import { fetchFactorLibrary, fetchFactorScorePreview } from '../src/api/client';

describe('FactorLabWorkspace', () => {
  beforeEach(() => {
    vi.mocked(fetchFactorLibrary).mockResolvedValue([
      { factor_name: 'ret_20', factor_group: 'momentum', direction: 'higher', description: '20-day return', source: 'custom', calc_version: 'v1', status: 'validated', availability_start_date: null, availability_reason: null, latest_available_date: '2026-06-08', coverage_count: 5207, used_in_manual_v1: true, manual_v1_weight: 0.15 },
      { factor_name: 'volatility_20', factor_group: 'risk', direction: 'lower', description: '20-day volatility', source: 'custom', calc_version: 'v1', status: 'validated', availability_start_date: null, availability_reason: null, latest_available_date: '2026-06-08', coverage_count: 5207, used_in_manual_v1: true, manual_v1_weight: 0.1 }
    ]);
    vi.mocked(fetchFactorScorePreview).mockResolvedValue({
      trade_date: '2026-06-08',
      selected_factors: [{ factor_name: 'ret_20', direction: 'higher', weight: 1 }],
      items: [{ trade_date: '2026-06-08', asset_id: 'CN:SZ:300951', rank: 1, score_total: 100, score_components: { ret_20_score: 100 } }]
    });
  });

  it('shows factor library and runs selected factor preview', async () => {
    render(<FactorLabWorkspace />);

    expect(await screen.findByRole('heading', { name: 'Factor Lab' })).toBeVisible();
    expect(await screen.findByText('ret_20')).toBeVisible();
    await userEvent.click(screen.getByLabelText('select ret_20'));
    await userEvent.click(screen.getByRole('button', { name: 'Preview Scores' }));

    expect(fetchFactorScorePreview).toHaveBeenCalledWith('2026-06-08', [{ factor_name: 'ret_20', direction: 'higher', weight: 1 }], 30);
    expect(await screen.findByText('CN:SZ:300951')).toBeVisible();
  });
});
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd dashboard
pnpm vitest run tests/factor-lab-workspace.test.tsx
```

Expected: FAIL because `FactorLabWorkspace` does not exist.

- [ ] **Step 3: Implement workspace**

Create `dashboard/src/components/FactorLabWorkspace.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react';
import { fetchFactorLibrary, fetchFactorScorePreview } from '../api/client';
import type { FactorLibraryRow, FactorScorePreview, FactorSelection } from '../api/types';

export function FactorLabWorkspace() {
  const [tradeDate, setTradeDate] = useState('2026-06-08');
  const [topN, setTopN] = useState(30);
  const [library, setLibrary] = useState<FactorLibraryRow[]>([]);
  const [selected, setSelected] = useState<Record<string, FactorSelection>>({});
  const [preview, setPreview] = useState<FactorScorePreview | null>(null);
  const selectedRows = useMemo(() => Object.values(selected), [selected]);

  useEffect(() => {
    fetchFactorLibrary().then(setLibrary);
  }, []);

  function toggle(row: FactorLibraryRow, checked: boolean) {
    setSelected((current) => {
      const next = { ...current };
      if (checked) {
        next[row.factor_name] = { factor_name: row.factor_name, direction: row.direction === 'lower' ? 'lower' : 'higher', weight: row.manual_v1_weight ?? 1 };
      } else {
        delete next[row.factor_name];
      }
      return next;
    });
  }

  function previewScores() {
    fetchFactorScorePreview(tradeDate, selectedRows, topN).then(setPreview);
  }

  return (
    <section className="factor-lab">
      <header className="workspace-header">
        <h1>Factor Lab</h1>
        <p className="muted">Build a read-only factor scoring preview without creating a new score version.</p>
      </header>
      <div className="toolbar">
        <input aria-label="trade date" type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
        <input aria-label="top n" type="number" value={topN} onChange={(event) => setTopN(Number(event.target.value))} />
        <button type="button" onClick={previewScores} disabled={selectedRows.length === 0}>Preview Scores</button>
      </div>
      <section className="workspace-band">
        <h2>Factor Library</h2>
        <table className="strategy-table">
          <thead><tr><th>Select</th><th>Factor</th><th>Group</th><th>Direction</th><th>Manual V1</th><th>Coverage</th></tr></thead>
          <tbody>
            {library.map((row) => (
              <tr key={row.factor_name}>
                <td><input aria-label={`select ${row.factor_name}`} type="checkbox" onChange={(event) => toggle(row, event.target.checked)} /></td>
                <td>{row.factor_name}</td>
                <td>{row.factor_group}</td>
                <td>{row.direction}</td>
                <td>{row.manual_v1_weight ?? '-'}</td>
                <td>{row.latest_available_date ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="workspace-band">
        <h2>Score Preview</h2>
        {preview ? (
          <table className="strategy-table">
            <tbody>
              {preview.items.map((row) => (
                <tr key={row.asset_id}><td>{row.rank}</td><td>{row.asset_id}</td><td>{row.score_total.toFixed(1)}</td></tr>
              ))}
            </tbody>
          </table>
        ) : <p className="muted">Select factors and preview scores.</p>}
      </section>
    </section>
  );
}
```

- [ ] **Step 4: Wire into AppShell**

Modify `dashboard/src/components/AppShell.tsx`:

```tsx
import { FactorLabWorkspace } from './FactorLabWorkspace';
```

Replace the temporary Factor Lab heading:

```tsx
{workspaceMode === 'factors' ? <FactorLabWorkspace /> : null}
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
cd dashboard
pnpm vitest run tests/factor-lab-workspace.test.tsx
pnpm test
```

Expected: PASS.

Commit:

```bash
git add dashboard/src/components/FactorLabWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/src/styles.css dashboard/tests/factor-lab-workspace.test.tsx
git commit -m "feat: add factor lab workspace"
```

---

## Task 10: Frontend Backtest Lab Workspace

**Files:**
- Create: `dashboard/src/components/BacktestLabWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/backtest-lab-workspace.test.tsx`

- [ ] **Step 1: Write failing Backtest Lab tests**

Create `dashboard/tests/backtest-lab-workspace.test.tsx`:

```typescript
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BacktestLabWorkspace } from '../src/components/BacktestLabWorkspace';

vi.mock('../src/api/client', () => ({
  fetchBacktestStrategies: vi.fn(),
  runBacktest: vi.fn()
}));

import { fetchBacktestStrategies, runBacktest } from '../src/api/client';

describe('BacktestLabWorkspace', () => {
  beforeEach(() => {
    vi.mocked(fetchBacktestStrategies).mockResolvedValue([
      { strategy_id: 'manual_v1_topn_rotation', strategy_name: 'Manual V1 TopN Rotation', status: 'runnable', description: 'TopN', factor_groups: ['momentum'], signal_inputs: ['factor.stock_score_daily'], default_parameters: {}, latest_evidence: '', primary_action: 'Run backtest' },
      { strategy_id: 'lhb_shortline', strategy_name: 'LHB Shortline', status: 'replay_only', description: 'LHB', factor_groups: [], signal_inputs: ['LHB'], default_parameters: {}, latest_evidence: 'strategy_validation', primary_action: 'Inspect evidence' }
    ]);
    vi.mocked(runBacktest).mockResolvedValue({
      strategy_id: 'manual_v1_topn_rotation',
      strategy_name: 'Manual V1 TopN Rotation',
      read_only: true,
      config: {},
      summary: { total_return: 0.12, max_drawdown: -0.05 },
      equity_curve: [{ date: '2026-06-03', equity: 1.12, drawdown: -0.01 }],
      positions: [{ asset_id: 'CN:SZ:300951', weight: 0.05 }],
      trades: [{ asset_id: 'CN:SZ:300951', side: 'buy' }]
    });
  });

  it('runs a read-only TopN backtest and renders results', async () => {
    render(<BacktestLabWorkspace />);

    expect(await screen.findByText('Manual V1 TopN Rotation')).toBeVisible();
    expect(screen.getByText('LHB Shortline')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));

    expect(runBacktest).toHaveBeenCalledWith(expect.objectContaining({ strategy_id: 'manual_v1_topn_rotation' }));
    expect(await screen.findByText('Read-only backtest')).toBeVisible();
    expect(screen.getByText('total_return')).toBeVisible();
    expect(screen.getByText('CN:SZ:300951')).toBeVisible();
  });
});
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd dashboard
pnpm vitest run tests/backtest-lab-workspace.test.tsx
```

Expected: FAIL because `BacktestLabWorkspace` does not exist.

- [ ] **Step 3: Implement workspace**

Create `dashboard/src/components/BacktestLabWorkspace.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { fetchBacktestStrategies, runBacktest } from '../api/client';
import type { BacktestRunResult, StrategyCatalogItem } from '../api/types';

export function BacktestLabWorkspace() {
  const [strategies, setStrategies] = useState<StrategyCatalogItem[]>([]);
  const [strategyId, setStrategyId] = useState('manual_v1_topn_rotation');
  const [startDate, setStartDate] = useState('2026-01-01');
  const [endDate, setEndDate] = useState('2026-06-08');
  const [topN, setTopN] = useState(20);
  const [rebalanceFrequency, setRebalanceFrequency] = useState<'daily' | 'weekly'>('weekly');
  const [transactionCostBps, setTransactionCostBps] = useState(10);
  const [maxPositions, setMaxPositions] = useState(20);
  const [result, setResult] = useState<BacktestRunResult | null>(null);
  const selected = strategies.find((strategy) => strategy.strategy_id === strategyId);

  useEffect(() => {
    fetchBacktestStrategies().then((rows) => {
      setStrategies(rows);
      setStrategyId(rows.find((row) => row.status === 'runnable')?.strategy_id ?? rows[0]?.strategy_id ?? 'manual_v1_topn_rotation');
    });
  }, []);

  function submit() {
    runBacktest({
      strategy_id: strategyId,
      start_date: startDate,
      end_date: endDate,
      score_version: 'manual_v1',
      top_n: topN,
      rebalance_frequency: rebalanceFrequency,
      transaction_cost_bps: transactionCostBps,
      max_positions: maxPositions,
      adjust_type: 'hfq'
    }).then(setResult);
  }

  return (
    <section className="backtest-lab">
      <header className="workspace-header">
        <h1>Backtest Lab</h1>
        <p className="muted">Run built-in read-only strategy backtests. Custom strategy code is not supported.</p>
      </header>
      <div className="toolbar">
        <select aria-label="strategy" value={strategyId} onChange={(event) => setStrategyId(event.target.value)}>
          {strategies.map((strategy) => <option key={strategy.strategy_id} value={strategy.strategy_id}>{strategy.strategy_name}</option>)}
        </select>
        <input aria-label="start date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        <input aria-label="end date" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        <input aria-label="top n" type="number" value={topN} onChange={(event) => setTopN(Number(event.target.value))} />
        <select aria-label="rebalance frequency" value={rebalanceFrequency} onChange={(event) => setRebalanceFrequency(event.target.value as 'daily' | 'weekly')}>
          <option value="weekly">weekly</option>
          <option value="daily">daily</option>
        </select>
        <input aria-label="transaction cost bps" type="number" value={transactionCostBps} onChange={(event) => setTransactionCostBps(Number(event.target.value))} />
        <input aria-label="max positions" type="number" value={maxPositions} onChange={(event) => setMaxPositions(Number(event.target.value))} />
        <button type="button" onClick={submit} disabled={selected?.status !== 'runnable'}>Run Backtest</button>
      </div>
      <section className="workspace-band">
        <h2>Strategy Catalog</h2>
        <div className="strategy-card-grid">
          {strategies.map((strategy) => (
            <div className="strategy-summary-card" key={strategy.strategy_id}>
              <strong>{strategy.strategy_name}</strong>
              <span>{strategy.status}</span>
              <small>{strategy.description}</small>
            </div>
          ))}
        </div>
      </section>
      {result ? (
        <section className="workspace-band">
          <h2>Read-only backtest</h2>
          <table className="strategy-table"><tbody>{Object.entries(result.summary).map(([key, value]) => <tr key={key}><td>{key}</td><td>{String(value)}</td></tr>)}</tbody></table>
          <h3>Positions</h3>
          <table className="strategy-table"><tbody>{result.positions.slice(0, 20).map((row, index) => <tr key={index}><td>{String(row.asset_id)}</td><td>{String(row.weight ?? '')}</td></tr>)}</tbody></table>
          <h3>Trades</h3>
          <table className="strategy-table"><tbody>{result.trades.slice(0, 20).map((row, index) => <tr key={index}><td>{String(row.asset_id)}</td><td>{String(row.side ?? '')}</td></tr>)}</tbody></table>
        </section>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 4: Wire into AppShell**

Modify `dashboard/src/components/AppShell.tsx`:

```tsx
import { BacktestLabWorkspace } from './BacktestLabWorkspace';
```

Replace the temporary Backtest Lab heading:

```tsx
{workspaceMode === 'backtests' ? <BacktestLabWorkspace /> : null}
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
cd dashboard
pnpm vitest run tests/backtest-lab-workspace.test.tsx
pnpm test
```

Expected: PASS.

Commit:

```bash
git add dashboard/src/components/BacktestLabWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/src/styles.css dashboard/tests/backtest-lab-workspace.test.tsx
git commit -m "feat: add backtest lab workspace"
```

---

## Task 11: Reports Workspace and Navigation Polish

**Files:**
- Create: `dashboard/src/components/ReportsWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/home-cockpit.test.tsx`

- [ ] **Step 1: Extend navigation test**

Append to `dashboard/tests/home-cockpit.test.tsx`:

```typescript
  it('navigates to Reports workspace', async () => {
    render(<AppShell />);
    await screen.findByText('Research Cockpit');

    await userEvent.click(screen.getByRole('button', { name: 'Reports' }));

    expect(await screen.findByRole('heading', { name: 'Reports' })).toBeVisible();
    expect(screen.getByText('Local research artifacts and generated reports.')).toBeVisible();
  });
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd dashboard
pnpm vitest run tests/home-cockpit.test.tsx
```

Expected: FAIL because the temporary Reports heading lacks the expected explanatory text.

- [ ] **Step 3: Implement ReportsWorkspace**

Create `dashboard/src/components/ReportsWorkspace.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { fetchOverview } from '../api/client';
import type { ReportLink } from '../api/types';
import { ReportPanel } from './ReportPanel';

export function ReportsWorkspace() {
  const [tradeDate, setTradeDate] = useState('2026-06-08');
  const [reports, setReports] = useState<ReportLink[]>([]);

  function load() {
    fetchOverview({ tradeDate, scoreVersion: 'manual_v1', watchlistId: 'default', topN: 5 }).then((overview) => setReports(overview.reports));
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <section className="reports-workspace">
      <header className="workspace-header">
        <h1>Reports</h1>
        <p className="muted">Local research artifacts and generated reports.</p>
      </header>
      <div className="toolbar">
        <input aria-label="report trade date" type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
        <button type="button" onClick={load}>Load Reports</button>
      </div>
      <ReportPanel reports={reports} />
    </section>
  );
}
```

- [ ] **Step 4: Wire into AppShell**

Modify `dashboard/src/components/AppShell.tsx`:

```tsx
import { ReportsWorkspace } from './ReportsWorkspace';
```

Replace the temporary Reports heading:

```tsx
{workspaceMode === 'reports' ? <ReportsWorkspace /> : null}
```

- [ ] **Step 5: Verify and commit**

Run:

```bash
cd dashboard
pnpm vitest run tests/home-cockpit.test.tsx
pnpm test
```

Expected: PASS.

Commit:

```bash
git add dashboard/src/components/ReportsWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/src/styles.css dashboard/tests/home-cockpit.test.tsx
git commit -m "feat: add reports workspace"
```

---

## Task 12: Platform Full-Flow Playwright

**Files:**
- Create: `dashboard/tests/platform-full-flow.spec.ts`
- Modify: `dashboard/tests/app-smoke.spec.ts`

- [ ] **Step 1: Write full-flow Playwright test**

Create `dashboard/tests/platform-full-flow.spec.ts`:

```typescript
import { expect, test, type Page } from '@playwright/test';

async function mockPlatformApi(page: Page) {
  await page.route('/api/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/platform/summary') {
      await route.fulfill({ json: { latest_market_date: '2026-06-08', latest_score_date: '2026-06-08', latest_factor_date: '2026-06-08', market_asset_count: 5207, score_asset_count: 5207, factor_count: 43, score_versions: ['manual_v1'], topn_preview: [{ trade_date: '2026-06-08', asset_id: 'CN:SZ:300951', rank: 1, score_total: 89.9, score_version: 'manual_v1', score_components: {} }] } });
      return;
    }
    if (url.pathname === '/api/strategies/catalog' || url.pathname === '/api/backtests/strategies') {
      await route.fulfill({ json: { items: [{ strategy_id: 'manual_v1_topn_rotation', strategy_name: 'Manual V1 TopN Rotation', status: 'runnable', description: 'TopN rotation', factor_groups: ['momentum'], signal_inputs: ['factor.stock_score_daily'], default_parameters: {}, latest_evidence: '', primary_action: 'Run backtest' }, { strategy_id: 'lhb_shortline', strategy_name: 'LHB Shortline', status: 'replay_only', description: 'LHB replay', factor_groups: [], signal_inputs: ['LHB'], default_parameters: {}, latest_evidence: 'strategy_validation', primary_action: 'Inspect evidence' }] } });
      return;
    }
    if (url.pathname === '/api/factors/library') {
      await route.fulfill({ json: { items: [{ factor_name: 'ret_20', factor_group: 'momentum', direction: 'higher', description: '20-day return', source: 'custom', calc_version: 'v1', status: 'validated', availability_start_date: null, availability_reason: null, latest_available_date: '2026-06-08', coverage_count: 5207, used_in_manual_v1: true, manual_v1_weight: 0.15 }] } });
      return;
    }
    if (url.pathname === '/api/factors/score-preview') {
      await route.fulfill({ json: { trade_date: '2026-06-08', selected_factors: [{ factor_name: 'ret_20', direction: 'higher', weight: 1 }], items: [{ trade_date: '2026-06-08', asset_id: 'CN:SZ:300951', rank: 1, score_total: 100, score_components: { ret_20_score: 100 } }] } });
      return;
    }
    if (url.pathname.endsWith('/profile')) {
      await route.fulfill({ json: { asset_id: '000001.SZ', canonical_asset_id: 'CN:SZ:000001', asset: { asset_id: 'CN:SZ:000001', symbol: '000001', name: '平安银行', exchange: 'SZ', board: null, is_active: true }, bars: [{ time: '2026-06-03', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }], score: { trade_date: '2026-06-08', asset_id: 'CN:SZ:000001', rank: 12, score_total: 88.5, score_version: 'manual_v1', score_components: { ret_20_score: 90 } }, signals: [], decisions: [], outcomes: [], factor_values: [{ factor_group: 'momentum', factor_name: 'ret_20', factor_value: 0.12 }], coverage: { daily_bars: { min_date: '1991-04-03', max_date: '2026-06-08' } } } });
      return;
    }
    if (url.pathname === '/api/backtests/run') {
      await route.fulfill({ json: { strategy_id: 'manual_v1_topn_rotation', strategy_name: 'Manual V1 TopN Rotation', read_only: true, config: {}, summary: { total_return: 0.12, max_drawdown: -0.05 }, equity_curve: [{ date: '2026-06-03', equity: 1.12, drawdown: -0.01 }], positions: [{ asset_id: 'CN:SZ:300951', weight: 0.05 }], trades: [{ asset_id: 'CN:SZ:300951', side: 'buy' }] } });
      return;
    }
    if (url.pathname === '/api/dashboard/overview') {
      await route.fulfill({ json: { trade_date: '2026-06-08', score_version: 'manual_v1', watchlist_id: 'default', top_scores: [], watchlist_signals: [], reports: [{ report_type: 'daily', title: 'Daily TopN', path: '/reports/topn.md', format: 'md', trade_date: '2026-06-08' }] } });
      return;
    }
    if (url.pathname === '/api/strategy-validation/runs') {
      await route.fulfill({ json: { items: [{ run_id: 'lhb_shortline:fixture:phase16', strategy_id: 'lhb_shortline', strategy_name: 'LHB Shortline', strategy_version: 'phase16', run_type: 'replay', start_date: '2026-06-01', end_date: '2026-06-08', created_at: '2026-06-08T20:30:00+08:00', benchmark: '000300.SH', universe: 'a_share', data_window: {}, cost_config: {}, slippage_config: {}, risk_config: {}, position_config: {}, source_artifact_paths: [], summary_metrics: {}, warnings: [] }] } });
      return;
    }
    if (url.pathname.includes('/strategy-validation/runs/')) {
      await route.fulfill({ json: { run: null, asset_id: '000001.SZ', bars: [{ time: '2026-06-03', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }], signals: [{ run_id: 'lhb_shortline:fixture:phase16', strategy_id: 'lhb_shortline', asset_id: '000001.SZ', stock_code: '000001', stock_name: 'Ping An Bank', signal_time: '2026-06-03', trade_date: '2026-06-03', signal_type: 'support', signal_strength: 0.86, signal_bucket: 'support', risk_bucket: 'normal', rule_id: 'lhb_phase16_follow', reason: 'support confirmed', tags: ['lhb'], source_artifact_path: 'outputs/research/lhb.md' }], trades: [], positions: [], metrics: [], artifacts: [] } });
      return;
    }
    await route.fulfill({ json: { items: [] } });
  });
}

async function assertNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(overflow).toBe(false);
}

test('platform navigation covers home, data, factors, backtests, strategy validation, and reports', async ({ page }) => {
  await mockPlatformApi(page);
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
  await expect(page.getByText('Manual V1 TopN Rotation')).toBeVisible();

  await page.getByRole('button', { name: 'Data Explorer' }).click();
  await expect(page.getByText('平安银行')).toBeVisible();
  await expect(page.getByText('Score 88.5')).toBeVisible();

  await page.getByRole('button', { name: 'Factor Lab' }).click();
  await expect(page.getByText('ret_20')).toBeVisible();
  await page.getByLabel('select ret_20').check();
  await page.getByRole('button', { name: 'Preview Scores' }).click();
  await expect(page.getByText('CN:SZ:300951')).toBeVisible();

  await page.getByRole('button', { name: 'Backtest Lab' }).click();
  await expect(page.getByText('LHB Shortline')).toBeVisible();
  await page.getByRole('button', { name: 'Run Backtest' }).click();
  await expect(page.getByText('Read-only backtest')).toBeVisible();

  await page.getByRole('button', { name: 'Strategy Validation' }).click();
  await expect(page.getByText('support confirmed')).toBeVisible();

  await page.getByRole('button', { name: 'Reports' }).click();
  await expect(page.getByText('Daily TopN')).toBeVisible();

  await expect(page.getByRole('button', { name: /place order|auto trade|production write/i })).toHaveCount(0);
  await assertNoHorizontalOverflow(page);
});
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
cd dashboard
pnpm exec playwright test tests/platform-full-flow.spec.ts
```

Expected: FAIL until all prior frontend tasks are complete.

- [ ] **Step 3: Update existing smoke if needed**

If `dashboard/tests/app-smoke.spec.ts` still expects the old default TopN-first surface, update it to assert:

```typescript
await expect(page.getByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
await page.getByRole('button', { name: 'Data Explorer' }).click();
await expect(page.getByRole('heading', { name: 'Data Explorer' })).toBeVisible();
```

- [ ] **Step 4: Verify and commit**

Run:

```bash
cd dashboard
pnpm test:e2e
pnpm test
pnpm build
```

Expected:

- `pnpm test:e2e`: all Playwright specs pass.
- `pnpm test`: all Vitest tests pass.
- `pnpm build`: TypeScript and Vite build pass.

Commit:

```bash
git add dashboard/tests/platform-full-flow.spec.ts dashboard/tests/app-smoke.spec.ts
git commit -m "test: add platform workspace full flow"
```

---

## Task 13: Final Backend, Frontend, and Live Smoke Verification

**Files:**
- No source files expected unless verification exposes a bug.

- [ ] **Step 1: Run backend dashboard tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_platform.py \
  tests/test_dashboard_strategy_catalog.py \
  tests/test_dashboard_factors.py \
  tests/test_dashboard_asset_profile.py \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_app.py \
  tests/test_dashboard_bars.py \
  tests/test_dashboard_strategy_validation.py \
  tests/test_dashboard_schemas.py \
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

Expected: PASS for all commands.

- [ ] **Step 3: Run live local smoke**

Start API:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m uvicorn stock_research.dashboard.app:app --host 127.0.0.1 --port 8765
```

Start frontend:

```bash
cd dashboard
pnpm dev --host 127.0.0.1
```

Open:

```text
http://127.0.0.1:5174/
```

Manual checks:

- Home shows Research Cockpit and platform coverage.
- Data Explorer loads `000001.SZ` and shows `CN:SZ:000001`.
- Factor Lab lists `ret_20` and `manual_v1` weights.
- Backtest Lab runs `Manual V1 TopN Rotation` for a short range.
- Strategy Validation still loads LHB replay.
- Reports loads report links for a selected date.

- [ ] **Step 4: Commit fixes or final status**

If verification required fixes, commit them with focused messages.

If no fixes were needed, leave the branch clean and report the exact commands and pass counts.

---

## Self-Review

Spec coverage:

- Home / Research Cockpit: Tasks 2, 6, 7, 12.
- Data Explorer: Tasks 4, 6, 8, 12.
- Factor Lab: Tasks 3, 6, 9, 12.
- Backtest Lab: Tasks 5, 6, 10, 12.
- Strategy Validation retention: Tasks 1, 7, 12.
- Reports: Task 11.
- Read-only boundary: Tasks 1, 5, 7, 10, 12.
- Playwright full flow: Task 12.

Placeholder scan:

- The plan avoids unresolved sections and gives exact file paths, route names, and verification commands.

Type consistency:

- Backend route names match frontend client names.
- `strategy_id`, `factor_name`, `score_version`, and `asset_id` field names match existing API conventions.
- Backtest payload keys match `BacktestRunRequest`.
