# P13 Shadow Watchlist Outcome Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a review-only P13 per-candidate outcome tracking layer for P12 shadow watchlist candidates without writing production watchlist, scoring, scheduler, or trading state.

**Architecture:** P13 mirrors P8 decision outcome review, but the measured entity is a P12 shadow candidate. It writes local JSON/CSV/Markdown artifacts, imports compact read-model rows into independent `ops.operator_shadow_watchlist_outcome_*` tables, and exposes read-only dashboard summaries.

**Tech Stack:** Python, pandas, argparse CLI, PostgreSQL SQL strings in `schema.py`, FastAPI dashboard API, React/Vite dashboard, Vitest, Playwright, pytest.

---

## File Structure

Create:

- `src/stock_research/operator_decision/shadow_outcomes.py`: P13 outcome contract, metric builder, artifact writer, Markdown rendering.
- `tests/test_operator_shadow_outcomes.py`: contract and artifact writer tests.
- `src/stock_research/operator_decision/shadow_outcomes_read_model.py`: P13 artifact loader and idempotent read-model importer.
- `tests/test_operator_shadow_outcomes_read_model.py`: importer/read-model tests.
- `src/stock_research/operator_decision/p13_smoke.py`: synthetic P12/P13 smoke.
- `tests/test_p13_shadow_outcomes_smoke.py`: smoke test.
- `src/stock_research/dashboard/shadow_outcomes.py`: dashboard read-only query.
- `tests/test_dashboard_shadow_outcomes.py`: dashboard backend query tests.
- `dashboard/src/components/ShadowOutcomesPanel.tsx`: read-only panel.
- `docs/quant_system/46_p13_shadow_outcome_tracking_scope_freeze.md`: P13 scope freeze.
- `docs/quant_system/47_p13_shadow_outcome_tracking_runbook.md`: P13 runbook.
- `docs/quant_system/48_p13_shadow_outcome_tracking_completion.md`: P13 completion review.

Modify:

- `src/stock_research/cli.py`: add `p13-shadow-outcome-review` and `p13-import-shadow-outcomes`, staging only P13 hunks because this file has unrelated dirty changes.
- `src/stock_research/schema.py`: add `ops.operator_shadow_watchlist_outcome_run` and `ops.operator_shadow_watchlist_outcome_candidate` plus indexes.
- `tests/test_schema.py`: assert P13 tables/indexes.
- `tests/test_factor_cli.py`: CLI parser/dispatch tests.
- `src/stock_research/dashboard/app.py`: add `GET /api/shadow-outcomes`.
- `tests/test_dashboard_app.py`: route test.
- `dashboard/src/api/types.ts`: add `ShadowOutcomeRow`.
- `dashboard/src/api/client.ts`: add `fetchShadowOutcomes`.
- `dashboard/src/App.tsx`: load and render P13 panel.
- `dashboard/tests/client.test.ts`: client test.
- `dashboard/tests/app-shell.test.tsx`: app panel/loading/empty tests.
- `dashboard/tests/app-smoke.spec.ts`: browser smoke route/mock/assertions.

Do not modify:

- `watchlist.watchlist_daily_signal` write paths.
- `factor.stock_score_daily` write paths.
- `factor.factor_approval` write paths.
- scheduler wrappers.
- trading/broker/order/account/position modules.
- unrelated watchlist/trend/factor/strong-winner/mid-trend dirty files.

---

### Task 0: P13 Scope Freeze

**Files:**

- Create: `docs/quant_system/46_p13_shadow_outcome_tracking_scope_freeze.md`

- [ ] **Step 1: Write the scope freeze document**

Create `docs/quant_system/46_p13_shadow_outcome_tracking_scope_freeze.md`:

```markdown
# P13 Shadow Watchlist Outcome Tracking Scope Freeze

Date: 2026-06-01

## Status

P13 scope is frozen around **Shadow Watchlist Outcome Tracking**.

## Why This Scope

P12 produced review-only shadow watchlist candidates. The next useful step is to
measure each candidate's later market outcome, not to promote candidates or
write production watchlist state.

## In Scope

- Per-shadow-candidate outcome metric contract.
- CLI to generate JSON/CSV/Markdown outcome artifacts from P12 candidates and
  daily bars.
- Read-model tables under `ops`.
- Import helper and CLI using idempotent upserts.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

## Out Of Scope

- Aggregating outcomes across layers, statuses, proposals, or replay sources.
- Promotion recommendations.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing ranking/scoring logic.
- Changing production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating P13 outcome status as production approval.

## Safety Fields

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`
```

- [ ] **Step 2: Verify document exists**

Run:

```bash
test -s docs/quant_system/46_p13_shadow_outcome_tracking_scope_freeze.md
```

Expected: exit code `0`.

- [ ] **Step 3: Commit**

Run:

```bash
git add docs/quant_system/46_p13_shadow_outcome_tracking_scope_freeze.md
git commit -m "docs: freeze p13 shadow outcome tracking scope"
```

---

### Task 1: Shadow Candidate Outcome Contract

**Files:**

- Create: `src/stock_research/operator_decision/shadow_outcomes.py`
- Create: `tests/test_operator_shadow_outcomes.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_operator_shadow_outcomes.py`:

```python
import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.operator_decision.shadow_outcomes import (
    SHADOW_OUTCOME_HORIZONS,
    build_shadow_outcome_review,
    build_shadow_outcomes_from_frames,
    write_shadow_outcome_review,
)


def _shadow_candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "shadow_candidate_id": "p12-shadow:001",
                "run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "candidate_reason": "Passed replay with acceptable drawdown.",
                "status": "shadow_ready",
                "shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            },
            {
                "shadow_candidate_id": "p12-shadow:002",
                "run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:002",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000002.SZ",
                "stock_code": "000002",
                "stock_name": "Vanke",
                "shadow_layer": "risk_shadow",
                "candidate_reason": "Observe risk-controlled candidate.",
                "status": "shadow_observe",
                "shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            },
        ]
    )


def _bars() -> pd.DataFrame:
    rows = []
    for asset_id, base_close in [("000001.SZ", 10.0), ("000002.SZ", 20.0)]:
        for offset in range(0, 21):
            close = base_close + offset if asset_id == "000001.SZ" else base_close - offset * 0.5
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": (pd.Timestamp("2026-06-30") + pd.Timedelta(days=offset)).strftime("%Y-%m-%d"),
                    "close": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                }
            )
    return pd.DataFrame(rows)


def test_build_shadow_outcomes_computes_forward_returns_and_drawdowns():
    result = build_shadow_outcomes_from_frames(
        shadow_candidates=_shadow_candidates(),
        bars=_bars(),
        horizons=[1, 5, 20],
    )

    outcomes = result.set_index("shadow_candidate_id")
    ready = outcomes.loc["p12-shadow:001"]
    assert ready["outcome_status"] == "complete"
    assert ready["source_p12_shadow_run_id"] == "p12-shadow-watchlist-2026-06-30"
    assert ready["source_p11_replay_run_id"] == "p11-replay-run-2026-06-30"
    assert round(float(ready["forward_1d_return"]), 6) == 0.1
    assert round(float(ready["forward_20d_return"]), 6) == 2.0
    assert round(float(ready["max_high_return_20d"]), 6) == 2.1
    assert round(float(ready["max_low_drawdown_20d"]), 6) == 0.0
    assert ready["manual_review_required"] is True
    assert ready["auto_trade_enabled"] is False
    assert ready["production_watchlist_enabled"] is False
    assert ready["production_write_enabled"] is False

    observe = outcomes.loc["p12-shadow:002"]
    assert observe["shadow_status"] == "shadow_observe"
    assert round(float(observe["forward_5d_return"]), 6) == -0.125
    assert round(float(observe["max_low_drawdown_20d"]), 6) == -0.55


def test_build_shadow_outcomes_marks_insufficient_future_data_without_zero_fill():
    short_bars = _bars()[lambda frame: frame["trade_date"].le("2026-07-04")]

    result = build_shadow_outcomes_from_frames(
        shadow_candidates=_shadow_candidates().iloc[:1],
        bars=short_bars,
        horizons=SHADOW_OUTCOME_HORIZONS,
    )

    row = result.iloc[0]
    assert row["outcome_status"] == "insufficient_data"
    assert pd.isna(row["forward_10d_return"])
    assert pd.isna(row["max_high_return_60d"])
    assert row["available_future_bars"] == 4


def test_build_shadow_outcomes_rejects_unsafe_or_production_enabled_candidates():
    unsafe = _shadow_candidates().copy()
    unsafe.loc[0, "production_watchlist_enabled"] = True
    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_outcomes_from_frames(shadow_candidates=unsafe, bars=_bars())

    execution_like = _shadow_candidates().copy()
    execution_like["order_id"] = ["order-1", ""]
    with pytest.raises(ValueError, match="unsafe_execution_field: order_id"):
        build_shadow_outcomes_from_frames(shadow_candidates=execution_like, bars=_bars())


def test_build_shadow_outcome_review_preserves_review_only_artifact_contract():
    review = build_shadow_outcome_review(
        review_date="2026-07-31",
        shadow_candidates=_shadow_candidates(),
        bars=_bars(),
        horizons=[1, 5, 20],
        run_id="p13-shadow-outcomes-2026-07-31",
    )

    assert review["run_id"] == "p13-shadow-outcomes-2026-07-31"
    assert review["review_date"] == "2026-07-31"
    assert review["status"] == "shadow_outcome_review_ready"
    assert review["manual_review_required"] is True
    assert review["auto_trade_enabled"] is False
    assert review["production_watchlist_enabled"] is False
    assert review["production_write_enabled"] is False
    assert review["outcome_count"] == 2
    assert review["horizons"] == [1, 5, 20]
    assert review["outcomes"][0]["shadow_candidate_id"] == "p12-shadow:001"
    assert review["outcomes"][0]["source_p12_shadow_run_id"] == "p12-shadow-watchlist-2026-06-30"


def test_write_shadow_outcome_review_outputs_json_csv_and_markdown(tmp_path):
    review = build_shadow_outcome_review(
        review_date="2026-07-31",
        shadow_candidates=_shadow_candidates().iloc[:1],
        bars=_bars()[lambda frame: frame["trade_date"].le("2026-07-04")],
        horizons=[1, 10],
        run_id="p13-short",
    )

    paths = write_shadow_outcome_review(review, tmp_path)

    assert set(paths) == {"json_path", "details_csv_path", "markdown_path"}
    assert Path(paths["json_path"]).name == "operator_shadow_outcomes_2026-07-31.json"
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["auto_trade_enabled"] is False
    assert payload["production_watchlist_enabled"] is False
    assert payload["outcomes"][0]["forward_10d_return"] is None

    details = pd.read_csv(paths["details_csv_path"])
    assert details.loc[0, "outcome_status"] == "insufficient_data"
    assert pd.isna(details.loc[0, "forward_10d_return"])

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "P13 Shadow Watchlist Outcome Tracking" in markdown
    assert "manual_review_required: true" in markdown
    assert "production_watchlist_enabled: false" in markdown
    assert "p12-shadow:001" in markdown
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcomes.py -q
```

Expected: fail because `stock_research.operator_decision.shadow_outcomes` does not exist.

- [ ] **Step 3: Implement outcome contract**

Create `src/stock_research/operator_decision/shadow_outcomes.py` with:

- `SHADOW_OUTCOME_HORIZONS = [1, 3, 5, 10, 20, 60]`
- `build_shadow_outcomes_from_frames(shadow_candidates, bars, horizons=None)`
- `build_shadow_outcome_review(review_date, shadow_candidates, bars, horizons=None, run_id=None)`
- `write_shadow_outcome_review(review, output_dir)`

Implementation rules:

- Follow `stock_research.operator_decision.outcome` for return math and artifact writing.
- Use flat detail columns such as `forward_5d_return`, `max_high_return_5d`, and `max_low_drawdown_5d`.
- Preserve source references: P12 shadow run, P11 replay run, P10 proposal run, P9 analytics run.
- Force review-only safety fields.
- Reject unsafe execution-like fields.
- Raise `ValueError("base_bar_required: <shadow_candidate_id>")` when the base candidate date bar is missing.
- Mark `insufficient_data` when `available_future_bars < max(horizons)`.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcomes.py -q
```

Expected: all P13 outcome contract tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/operator_decision/shadow_outcomes.py tests/test_operator_shadow_outcomes.py
git commit -m "feat: add p13 shadow outcome contract"
```

---

### Task 2: Shadow Outcome Artifact CLI

**Files:**

- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add to `tests/test_factor_cli.py`:

```python
def test_p13_shadow_outcome_review_cli_writes_artifacts(tmp_path):
    shadow_json = tmp_path / "operator_shadow_watchlist_2026-06-30.json"
    shadow_json.write_text(
        json.dumps(
            {
                "run_id": "p12-shadow-watchlist-2026-06-30",
                "review_date": "2026-06-30",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
                "candidates": [
                    {
                        "shadow_candidate_id": "p12-shadow:001",
                        "replay_result_id": "p11-replay:001",
                        "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                        "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                        "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                        "candidate_date": "2026-06-30",
                        "asset_id": "000001.SZ",
                        "stock_code": "000001",
                        "stock_name": "Ping An Bank",
                        "shadow_layer": "trend_shadow",
                        "status": "shadow_ready",
                        "manual_review_required": True,
                        "auto_trade_enabled": False,
                        "production_watchlist_enabled": False,
                        "production_write_enabled": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    bars_csv = tmp_path / "bars.csv"
    rows = []
    for offset in range(0, 11):
        rows.append(
            {
                "asset_id": "000001.SZ",
                "trade_date": (pd.Timestamp("2026-06-30") + pd.Timedelta(days=offset)).strftime("%Y-%m-%d"),
                "close": 10.0 + offset,
                "high": 11.0 + offset,
                "low": 9.0 + offset,
            }
        )
    pd.DataFrame(rows).to_csv(bars_csv, index=False)
    output_dir = tmp_path / "out"

    cli.main_for_args(
        [
            "p13-shadow-outcome-review",
            "--shadow-json",
            str(shadow_json),
            "--bars-csv",
            str(bars_csv),
            "--review-date",
            "2026-07-31",
            "--run-id",
            "p13-shadow-outcomes-2026-07-31",
            "--output-dir",
            str(output_dir),
        ]
    )

    payload = json.loads((output_dir / "operator_shadow_outcomes_2026-07-31.json").read_text())
    assert payload["run_id"] == "p13-shadow-outcomes-2026-07-31"
    assert payload["outcome_count"] == 1
    assert payload["production_watchlist_enabled"] is False
```

- [ ] **Step 2: Run CLI tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -k 'p13_shadow_outcome' -q
```

Expected: fail because parser command does not exist.

- [ ] **Step 3: Wire CLI**

Modify `src/stock_research/cli.py`:

- import `build_shadow_outcome_review`
- import `write_shadow_outcome_review`
- import `load_shadow_watchlist_read_model_rows`
- add parser `p13-shadow-outcome-review`
- load P12 candidates from `load_shadow_watchlist_read_model_rows(args.shadow_json)["candidates"]`
- load bars CSV with `pd.read_csv(args.bars_csv)`
- call builder/writer
- print:

```text
p13_shadow_outcome|status|...
p13_shadow_outcome|outcomes|...
p13_shadow_outcome|json|...
p13_shadow_outcome|details_csv|...
p13_shadow_outcome|markdown|...
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcomes.py tests/test_factor_cli.py -k 'shadow_outcome or p13_shadow_outcome' -q
```

Expected: P13 contract and artifact CLI tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add tests/test_factor_cli.py
git add -p src/stock_research/cli.py
git diff --cached -- src/stock_research/cli.py
git commit -m "feat: add p13 shadow outcome artifact cli"
```

---

### Task 3: Shadow Outcome Read Model

**Files:**

- Create: `src/stock_research/operator_decision/shadow_outcomes_read_model.py`
- Create: `tests/test_operator_shadow_outcomes_read_model.py`
- Modify: `src/stock_research/schema.py`
- Modify: `tests/test_schema.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing read-model tests**

Create `tests/test_operator_shadow_outcomes_read_model.py`:

```python
import json

import pytest

from stock_research.operator_decision.shadow_outcomes_read_model import (
    import_shadow_outcome_review,
    load_shadow_outcome_read_model_rows,
)


def _payload() -> dict:
    return {
        "run_id": "p13-shadow-outcomes-2026-07-31",
        "review_date": "2026-07-31",
        "status": "shadow_outcome_review_ready",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "horizons": [1, 5],
        "outcome_count": 1,
        "outcomes": [
            {
                "shadow_candidate_id": "p12-shadow:001",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "base_trade_date": "2026-06-30",
                "base_close": 10.0,
                "available_future_bars": 5,
                "outcome_status": "complete",
                "forward_1d_return": 0.1,
                "forward_5d_return": 0.5,
                "max_high_return_5d": 0.6,
                "max_low_drawdown_5d": -0.1,
                "source_shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ],
    }


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_shadow_outcome_rows_preserves_sources_metrics_and_safety(tmp_path):
    json_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")

    rows = load_shadow_outcome_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p13-shadow-outcomes-2026-07-31"
    assert rows["run"]["json_path"] == str(json_path)
    assert rows["run"]["details_csv_path"].endswith("_details.csv")
    assert rows["run"]["production_watchlist_enabled"] is False
    candidate = rows["candidates"][0]
    assert candidate["shadow_candidate_id"] == "p12-shadow:001"
    assert candidate["source_p12_shadow_run_id"] == "p12-shadow-watchlist-2026-06-30"
    assert candidate["source_p11_replay_run_id"] == "p11-replay-run-2026-06-30"
    assert candidate["source_p10_proposal_run_id"] == "p10-proposals-2026-06-30"
    assert candidate["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"
    assert candidate["forward_returns"] == {"1": 0.1, "5": 0.5}
    assert candidate["max_high_returns"] == {"5": 0.6}
    assert candidate["max_low_drawdowns"] == {"5": -0.1}
    assert candidate["production_write_enabled"] is False


def test_load_shadow_outcome_rows_rejects_production_enabled_artifact(tmp_path):
    payload = _payload()
    payload["production_watchlist_enabled"] = True
    json_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        load_shadow_outcome_read_model_rows(json_path)


def test_import_shadow_outcome_review_upserts_run_and_candidates(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_outcomes_read_model

    json_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_outcomes_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_outcome_review(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["candidate_count"] == 1
    assert result["run_ids"] == ["p13-shadow-outcomes-2026-07-31"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_shadow_watchlist_outcome_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    candidate_sql, candidate_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_shadow_watchlist_outcome_candidate" in candidate_sql
    assert "ON CONFLICT (shadow_outcome_id)" in candidate_sql
    assert candidate_params["shadow_candidate_id"] == "p12-shadow:001"
```

- [ ] **Step 2: Add schema test**

Add to `tests/test_schema.py`:

```python
def test_research_extension_includes_operator_shadow_outcome_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_candidate" in sql
    assert "PRIMARY KEY (shadow_outcome_id)" in sql
    assert "source_p12_shadow_run_id text NOT NULL" in sql
    assert "production_watchlist_enabled boolean NOT NULL DEFAULT false" in sql
    assert "idx_ops_operator_shadow_outcome_run_date" in sql
    assert "idx_ops_operator_shadow_outcome_asset_date" in sql
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcomes_read_model.py tests/test_schema.py -k 'shadow_outcome' -q
```

Expected: read-model module missing or schema assertions fail.

- [ ] **Step 4: Implement read model and schema**

Implement `shadow_outcomes_read_model.py` with:

- `load_shadow_outcome_read_model_rows(path)`
- `import_shadow_outcome_review(path, service=SETTINGS.research_service)`
- directory glob `operator_shadow_outcomes_*.json`
- `_upsert_run(cur, row)`
- `_upsert_candidate(cur, row)`

Add schema tables:

- `ops.operator_shadow_watchlist_outcome_run`
- `ops.operator_shadow_watchlist_outcome_candidate`

Required indexes:

- `idx_ops_operator_shadow_outcome_run_date`
- `idx_ops_operator_shadow_outcome_status_date`
- `idx_ops_operator_shadow_outcome_asset_date`
- `idx_ops_operator_shadow_outcome_source_candidate`

- [ ] **Step 5: Add import CLI test and wiring**

Add to `tests/test_factor_cli.py`:

```python
def test_p13_import_shadow_outcomes_cli_prints_summary(monkeypatch, capsys, tmp_path):
    import_path = tmp_path / "operator_shadow_outcomes_2026-07-31.json"
    import_path.write_text("{}", encoding="utf-8")

    def fake_import(path, *, service):
        assert path == import_path
        assert service == "stock_research_test"
        return {
            "imported_count": 1,
            "candidate_count": 2,
            "run_ids": ["p13-shadow-outcomes-2026-07-31"],
        }

    monkeypatch.setattr(cli, "import_shadow_outcome_review", fake_import)

    cli.main_for_args(
        [
            "p13-import-shadow-outcomes",
            "--path",
            str(import_path),
            "--service",
            "stock_research_test",
        ]
    )

    assert capsys.readouterr().out.splitlines() == [
        "p13_shadow_outcome_import|imported|1",
        "p13_shadow_outcome_import|candidates|2",
        "p13_shadow_outcome_import|run_id|p13-shadow-outcomes-2026-07-31",
    ]
```

- [ ] **Step 6: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcomes_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'shadow_outcome or p13_shadow_outcome or p13_import_shadow_outcomes' -q
```

Expected: all P13 read-model/schema/CLI tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/stock_research/operator_decision/shadow_outcomes_read_model.py tests/test_operator_shadow_outcomes_read_model.py src/stock_research/schema.py tests/test_schema.py tests/test_factor_cli.py
git add -p src/stock_research/cli.py
git diff --cached -- src/stock_research/cli.py
git commit -m "feat: add p13 shadow outcome read model"
```

---

### Task 4: Dashboard Read-Only Shadow Outcomes

**Files:**

- Create: `src/stock_research/dashboard/shadow_outcomes.py`
- Create: `tests/test_dashboard_shadow_outcomes.py`
- Create: `dashboard/src/components/ShadowOutcomesPanel.tsx`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_app.py`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/tests/client.test.ts`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Modify: `dashboard/tests/app-smoke.spec.ts`

- [ ] **Step 1: Write failing backend dashboard tests**

Create `tests/test_dashboard_shadow_outcomes.py`:

```python
from stock_research.dashboard import shadow_outcomes


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_shadow_outcomes_summary_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:001",
                "run_id": "p13-shadow-outcomes-2026-07-31",
                "shadow_candidate_id": "p12-shadow:001",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "base_trade_date": "2026-06-30",
                "base_close": 10.0,
                "forward_returns": {"5": 0.5},
                "max_high_returns": {"5": 0.6},
                "max_low_drawdowns": {"5": -0.1},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(shadow_outcomes, "connect", fake_connect)
    monkeypatch.setattr(shadow_outcomes, "fetch_all", fake_fetch_all)

    result = shadow_outcomes.load_shadow_outcomes_summary(
        start_date="2026-06-01",
        end_date="2026-07-31",
        outcome_status="complete",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_shadow_watchlist_outcome_candidate" in captured["sql"]
    assert "outcome_status = %s" in captured["sql"]
    assert "ORDER BY candidate_date DESC" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-07-31", "complete", 10]
    assert captured["service"] == "stock_research_test"
    assert result[0]["shadow_candidate_id"] == "p12-shadow:001"
    assert result[0]["forward_returns"] == {"5": 0.5}
    assert result[0]["production_watchlist_enabled"] is False
```

- [ ] **Step 2: Write failing route test**

Add to `tests/test_dashboard_app.py`:

```python
def test_shadow_outcomes_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_shadow_outcomes(start_date, end_date, outcome_status, limit):
        captured["args"] = [start_date, end_date, outcome_status, limit]
        return [
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:001",
                "run_id": "p13-shadow-outcomes-2026-07-31",
                "shadow_candidate_id": "p12-shadow:001",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "base_trade_date": "2026-06-30",
                "base_close": 10.0,
                "forward_returns": {"5": 0.5},
                "max_high_returns": {"5": 0.6},
                "max_low_drawdowns": {"5": -0.1},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_shadow_outcomes_summary", fake_load_shadow_outcomes)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-outcomes"
        "?start_date=2026-06-01"
        "&end_date=2026-07-31"
        "&outcome_status=complete"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-07-31", "complete", 10]
    assert response.json()["items"][0]["shadow_candidate_id"] == "p12-shadow:001"
    assert response.json()["items"][0]["production_watchlist_enabled"] is False
```

- [ ] **Step 3: Run backend tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_shadow_outcomes.py tests/test_dashboard_app.py -k 'shadow_outcomes' -q
```

Expected: fail because dashboard module/route does not exist.

- [ ] **Step 4: Implement backend route**

Create `src/stock_research/dashboard/shadow_outcomes.py` with:

- `load_shadow_outcomes_summary(start_date, end_date, outcome_status=None, limit=20, service=SETTINGS.research_service)`
- SQL selecting from `ops.operator_shadow_watchlist_outcome_candidate`
- optional `AND outcome_status = %s`
- `ORDER BY candidate_date DESC, outcome_status, shadow_outcome_id`
- normalization of JSON metric maps and safety booleans

Modify `src/stock_research/dashboard/app.py` to add `GET /api/shadow-outcomes`.

- [ ] **Step 5: Add frontend tests first**

Modify frontend tests with these expectations:

- `ShadowOutcomeRow` type in app-shell tests.
- API mock `fetchShadowOutcomes`.
- `makeShadowOutcomes()`.
- assertions for `Shadow Outcomes`, `complete`, `+50.0%`, no `/promote/i`, `/trade/i`, `/write/i`.
- loading text `Loading shadow outcomes...`.
- empty text `No shadow outcomes for selected range.`
- Playwright mock route `/api/shadow-outcomes**`.

- [ ] **Step 6: Run frontend tests to verify RED**

Run:

```bash
cd dashboard
pnpm test
```

Expected: fail because `fetchShadowOutcomes`, `ShadowOutcomeRow`, or panel does not exist.

- [ ] **Step 7: Implement frontend**

Implement these frontend pieces:

- `ShadowOutcomeRow` to `dashboard/src/api/types.ts`.
- `fetchShadowOutcomes(startDate, endDate, options={ outcomeStatus?: string; limit?: number })` to `dashboard/src/api/client.ts`.
- `dashboard/src/components/ShadowOutcomesPanel.tsx`.
- App state/load/render after `ShadowWatchlistPanel`.

Panel behavior:

- heading `Shadow Outcomes`
- loading and empty states
- rows show asset/name, outcome status, shadow status/layer, available future bars, 5D return, 20D return, 20D drawdown, source P12/P11 refs
- no buttons/actions

- [ ] **Step 8: Run dashboard verification**

Run:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

Expected:

- Vitest passes
- Vite build passes
- Playwright passes

- [ ] **Step 9: Commit**

Run:

```bash
git add src/stock_research/dashboard/shadow_outcomes.py tests/test_dashboard_shadow_outcomes.py src/stock_research/dashboard/app.py tests/test_dashboard_app.py dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/components/ShadowOutcomesPanel.tsx dashboard/src/App.tsx dashboard/tests/client.test.ts dashboard/tests/app-shell.test.tsx dashboard/tests/app-smoke.spec.ts
git commit -m "feat: add p13 shadow outcome dashboard summary"
```

---

### Task 5: P13 Smoke, Runbook, And Completion Review

**Files:**

- Create: `src/stock_research/operator_decision/p13_smoke.py`
- Create: `tests/test_p13_shadow_outcomes_smoke.py`
- Create: `docs/quant_system/47_p13_shadow_outcome_tracking_runbook.md`
- Create: `docs/quant_system/48_p13_shadow_outcome_tracking_completion.md`

- [ ] **Step 1: Write failing smoke test**

Create `tests/test_p13_shadow_outcomes_smoke.py`:

```python
from pathlib import Path

from stock_research.operator_decision.p13_smoke import build_p13_shadow_outcome_smoke


def test_p13_smoke_builds_shadow_outcome_artifacts_and_read_model_rows(tmp_path):
    result = build_p13_shadow_outcome_smoke(tmp_path)

    assert Path(result["p12_shadow_json_path"]).exists()
    assert Path(result["p13_shadow_outcome_json_path"]).exists()
    assert Path(result["p13_shadow_outcome_details_csv_path"]).exists()
    assert Path(result["p13_shadow_outcome_markdown_path"]).exists()
    assert result["outcome_count"] == 1
    assert result["read_model_candidate_count"] == 1
    assert result["outcome_statuses"] == ["complete"]
    assert result["source_p12_shadow_run_ids"] == ["p12-smoke-shadow-watchlist-2026-06-30"]
    assert result["source_p11_replay_run_ids"] == ["p11-smoke-replay-2026-06-30"]
    assert result["source_p10_proposal_run_ids"] == ["p10-smoke-proposals-2026-06-30"]
    assert result["source_p9_analytics_run_ids"] == ["p9-smoke-analytics-2026-05-30-2026-06-30"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_watchlist_enabled"] is False
    assert result["production_write_enabled"] is False
```

- [ ] **Step 2: Run smoke test to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_p13_shadow_outcomes_smoke.py -q
```

Expected: fail because `stock_research.operator_decision.p13_smoke` does not exist.

- [ ] **Step 3: Implement smoke**

Create `src/stock_research/operator_decision/p13_smoke.py`:

- call `build_p12_shadow_watchlist_smoke(output_dir)`
- load P12 shadow candidates via `load_shadow_watchlist_read_model_rows`
- create synthetic bars for `000001.SZ` from `2026-06-30` through at least 60 calendar days
- call `build_shadow_outcome_review`
- call `write_shadow_outcome_review`
- call `load_shadow_outcome_read_model_rows`
- return artifact paths, counts, source run IDs, outcome statuses, and safety fields

- [ ] **Step 4: Run smoke test to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_p13_shadow_outcomes_smoke.py tests/test_p12_shadow_watchlist_smoke.py -q
```

Expected: P13/P12 smoke tests pass.

- [ ] **Step 5: Run actual smoke command and capture output**

Run:

```bash
rm -rf /tmp/stock_research_p13_smoke
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p13_smoke import build_p13_shadow_outcome_smoke

result = build_p13_shadow_outcome_smoke(Path('/tmp/stock_research_p13_smoke'))
print(f"p13_smoke|p12_shadow|{result['p12_shadow_json_path']}")
print(f"p13_smoke|p13_shadow_outcome|{result['p13_shadow_outcome_json_path']}")
print(f"p13_smoke|details_csv|{result['p13_shadow_outcome_details_csv_path']}")
print(f"p13_smoke|markdown|{result['p13_shadow_outcome_markdown_path']}")
print(f"p13_smoke|outcome_count|{result['outcome_count']}")
print(f"p13_smoke|read_model_candidates|{result['read_model_candidate_count']}")
print(f"p13_smoke|outcome_statuses|{','.join(result['outcome_statuses'])}")
print(f"p13_smoke|source_p12_runs|{','.join(result['source_p12_shadow_run_ids'])}")
print(f"p13_smoke|source_p11_runs|{','.join(result['source_p11_replay_run_ids'])}")
print(f"p13_smoke|source_p10_runs|{','.join(result['source_p10_proposal_run_ids'])}")
print(f"p13_smoke|source_p9_runs|{','.join(result['source_p9_analytics_run_ids'])}")
print(f"p13_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p13_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p13_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p13_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Expected output includes:

```text
p13_smoke|outcome_count|1
p13_smoke|read_model_candidates|1
p13_smoke|outcome_statuses|complete
p13_smoke|manual_review_required|True
p13_smoke|auto_trade_enabled|False
p13_smoke|production_watchlist_enabled|False
p13_smoke|production_write_enabled|False
```

- [ ] **Step 6: Write runbook**

Create `docs/quant_system/47_p13_shadow_outcome_tracking_runbook.md` with:

- scope statement
- outcome horizons and metrics
- `stock-research p13-shadow-outcome-review` command
- `stock-research p13-import-shadow-outcomes` command
- dashboard review instructions
- synthetic smoke command and observed output
- verification commands

- [ ] **Step 7: Write completion review**

Create `docs/quant_system/48_p13_shadow_outcome_tracking_completion.md` with:

- P13 status
- P13-0 through P13-5 delivered capabilities
- smoke output
- acceptance criteria table
- verification evidence
- safety review explicitly stating no production watchlist/scoring/scheduler/trading path was added
- known non-P13 dirty files note

- [ ] **Step 8: Run full P13 verification**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcomes.py tests/test_operator_shadow_outcomes_read_model.py tests/test_p13_shadow_outcomes_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_outcomes.py tests/test_dashboard_app.py -k 'shadow_outcome or p13_shadow_outcome or p13_import_shadow_outcomes or dashboard' -q
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

Expected:

- Python P13-focused tests pass
- Vitest passes
- Vite build passes
- Playwright passes

- [ ] **Step 9: Update completion review with exact verification results**

Replace provisional verification result lines in `docs/quant_system/48_p13_shadow_outcome_tracking_completion.md` with the exact counts from Step 8.

- [ ] **Step 10: Commit**

Run:

```bash
git add src/stock_research/operator_decision/p13_smoke.py tests/test_p13_shadow_outcomes_smoke.py docs/quant_system/47_p13_shadow_outcome_tracking_runbook.md docs/quant_system/48_p13_shadow_outcome_tracking_completion.md
git commit -m "docs: complete p13 shadow outcome tracking governance"
```

---

## Final Verification Before P13 Completion Claim

Run from repo root:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcomes.py tests/test_operator_shadow_outcomes_read_model.py tests/test_p13_shadow_outcomes_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_outcomes.py tests/test_dashboard_app.py -k 'shadow_outcome or p13_shadow_outcome or p13_import_shadow_outcomes or dashboard' -q
```

Run from `dashboard/`:

```bash
pnpm test
pnpm build
pnpm test:e2e
```

Then verify staged/uncommitted state:

```bash
git status --short
git log --oneline -8
```

Expected:

- P13 commits appear on top of `factor-scoring-daily-pipeline`.
- Existing unrelated watchlist/trend/factor/strong-winner/mid-trend dirty files remain uncommitted.
- No P13 commit includes unrelated non-P13 dirty files.

## Self-Review Checklist

- Spec requirement "per-candidate outcome tracking" maps to Task 1.
- Spec requirement "artifact CLI" maps to Task 2.
- Spec requirement "read model" maps to Task 3.
- Spec requirement "dashboard read-only view" maps to Task 4.
- Spec requirement "smoke/runbook/completion" maps to Task 5.
- No task aggregates shadow outcomes into promotion recommendations.
- No task writes production watchlist, scoring, scheduler, or trading state.
- `cli.py` staging instructions explicitly protect unrelated dirty hunks.
