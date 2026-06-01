# P14 Shadow Outcome Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a review-only P14 analytics layer that summarizes P13 shadow watchlist outcomes by `shadow_layer` and `shadow_status` without writing production watchlist, scoring, scheduler, or trading state.

**Architecture:** P14 mirrors P9 decision outcome analytics, but the input is P13 shadow outcome candidates. It writes local JSON/CSV/Markdown artifacts, imports compact group analytics rows into independent `ops.operator_shadow_watchlist_outcome_analytics_*` tables, and exposes a read-only dashboard summary.

**Tech Stack:** Python, pandas, argparse CLI, PostgreSQL SQL strings in `schema.py`, FastAPI dashboard API, React/Vite dashboard, Vitest, Playwright, pytest.

---

## File Structure

Create:

- `src/stock_research/operator_decision/shadow_outcome_analytics.py`: P14 analytics contract, group metric builder, artifact writer, Markdown renderer.
- `tests/test_operator_shadow_outcome_analytics.py`: contract and artifact writer tests.
- `src/stock_research/operator_decision/shadow_outcome_analytics_read_model.py`: P14 artifact loader and idempotent read-model importer.
- `tests/test_operator_shadow_outcome_analytics_read_model.py`: importer/read-model tests.
- `src/stock_research/operator_decision/p14_smoke.py`: synthetic P13/P14 smoke.
- `tests/test_p14_shadow_outcome_analytics_smoke.py`: smoke test.
- `src/stock_research/dashboard/shadow_outcome_analytics.py`: dashboard read-only query.
- `tests/test_dashboard_shadow_outcome_analytics.py`: dashboard backend query tests.
- `dashboard/src/components/ShadowOutcomeAnalyticsPanel.tsx`: read-only panel.
- `docs/quant_system/49_p14_shadow_outcome_analytics_scope_freeze.md`: P14 scope freeze.
- `docs/quant_system/50_p14_shadow_outcome_analytics_runbook.md`: P14 runbook.
- `docs/quant_system/51_p14_shadow_outcome_analytics_completion.md`: P14 completion review.

Modify:

- `src/stock_research/cli.py`: add `p14-shadow-outcome-analytics` and `p14-import-shadow-outcome-analytics`, staging only P14 hunks because this file has unrelated dirty changes in the main worktree.
- `src/stock_research/schema.py`: add `ops.operator_shadow_watchlist_outcome_analytics_run` and `ops.operator_shadow_watchlist_outcome_analytics_group` plus indexes.
- `tests/test_schema.py`: assert P14 tables/indexes.
- `tests/test_factor_cli.py`: CLI parser/dispatch tests.
- `src/stock_research/dashboard/app.py`: add `GET /api/shadow-outcome-analytics`.
- `tests/test_dashboard_app.py`: route test.
- `dashboard/src/api/types.ts`: add `ShadowOutcomeAnalyticsRow`.
- `dashboard/src/api/client.ts`: add `fetchShadowOutcomeAnalytics`.
- `dashboard/src/App.tsx`: load and render P14 panel.
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

### Task 0: P14 Scope Freeze

**Files:**

- Create: `docs/quant_system/49_p14_shadow_outcome_analytics_scope_freeze.md`

- [ ] **Step 1: Write the scope freeze document**

Create `docs/quant_system/49_p14_shadow_outcome_analytics_scope_freeze.md`:

```markdown
# P14 Shadow Outcome Analytics Scope Freeze

Date: 2026-06-01

## Status

P14 scope is frozen around **Shadow Outcome Analytics**.

## Why This Scope

P13 made each P12 shadow watchlist candidate measurable. The next useful step is
to summarize those outcomes by shadow layer and shadow status, not to rank
individual candidates or promote production watchlist logic.

## In Scope

- Group analytics by `shadow_layer` and `shadow_status`.
- JSON/CSV/Markdown analytics artifacts.
- Read-model tables under `ops`.
- Import helper and CLI using idempotent upserts.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

## Out Of Scope

- Candidate-level ranking diagnostics.
- Promotion recommendations.
- Aggregation by proposal, replay run, P9 analytics run, sector, industry, or asset.
- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing ranking/scoring logic.
- Changing production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating P14 analytics as production approval.

## Safety Fields

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`
```

- [ ] **Step 2: Verify document exists**

Run:

```bash
test -s docs/quant_system/49_p14_shadow_outcome_analytics_scope_freeze.md
```

Expected: exit code `0`.

- [ ] **Step 3: Commit**

Run:

```bash
git add docs/quant_system/49_p14_shadow_outcome_analytics_scope_freeze.md
git commit -m "docs: freeze p14 shadow outcome analytics scope"
```

---

### Task 1: Shadow Outcome Analytics Contract

**Files:**

- Create: `src/stock_research/operator_decision/shadow_outcome_analytics.py`
- Create: `tests/test_operator_shadow_outcome_analytics.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_operator_shadow_outcome_analytics.py`:

```python
import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.operator_decision.shadow_outcome_analytics import (
    DEFAULT_SHADOW_OUTCOME_ANALYTICS_HORIZONS,
    build_shadow_outcome_analytics,
    build_shadow_outcome_analytics_from_frames,
    write_shadow_outcome_analytics,
)


def _outcomes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:001",
                "run_id": "p13-shadow-outcomes-2026-08-29",
                "shadow_candidate_id": "p12-shadow:001",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-analytics-2026-05-30-2026-06-30",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "outcome_status": "complete",
                "available_future_bars": 60,
                "forward_5d_return": 0.10,
                "forward_20d_return": 0.20,
                "max_high_return_20d": 0.30,
                "max_low_drawdown_20d": -0.05,
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            },
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:002",
                "run_id": "p13-shadow-outcomes-2026-08-29",
                "shadow_candidate_id": "p12-shadow:002",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:002",
                "source_p11_replay_run_id": "p11-replay-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-analytics-2026-05-30-2026-06-30",
                "candidate_date": "2026-06-30",
                "asset_id": "000002.SZ",
                "stock_code": "000002",
                "stock_name": "Vanke",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "outcome_status": "complete",
                "available_future_bars": 60,
                "forward_5d_return": -0.02,
                "forward_20d_return": 0.04,
                "max_high_return_20d": 0.08,
                "max_low_drawdown_20d": -0.12,
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            },
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:003",
                "run_id": "p13-shadow-outcomes-2026-08-29",
                "shadow_candidate_id": "p12-shadow:003",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:003",
                "source_p11_replay_run_id": "p11-replay-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-analytics-2026-05-30-2026-06-30",
                "candidate_date": "2026-06-30",
                "asset_id": "000003.SZ",
                "shadow_layer": "risk_shadow",
                "shadow_status": "shadow_observe",
                "outcome_status": "insufficient_data",
                "available_future_bars": 3,
                "forward_5d_return": None,
                "forward_20d_return": None,
                "max_high_return_20d": None,
                "max_low_drawdown_20d": None,
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            },
        ]
    )


def test_build_shadow_outcome_analytics_groups_by_layer_and_status():
    result = build_shadow_outcome_analytics_from_frames(
        shadow_outcomes=_outcomes(),
        horizons=[5, 20],
    )

    groups = result.set_index("group_key")
    trend_ready = groups.loc["trend_shadow|shadow_ready"]
    assert trend_ready["shadow_layer"] == "trend_shadow"
    assert trend_ready["shadow_status"] == "shadow_ready"
    assert trend_ready["sample_count"] == 2
    assert trend_ready["complete_count"] == 2
    assert trend_ready["insufficient_data_count"] == 0
    assert trend_ready["source_p12_shadow_run_count"] == 1
    assert round(float(trend_ready["forward_5d_return_mean"]), 6) == 0.04
    assert round(float(trend_ready["forward_20d_return_median"]), 6) == 0.12
    assert round(float(trend_ready["forward_5d_win_rate"]), 6) == 0.5
    assert round(float(trend_ready["max_low_drawdown_20d_worst"]), 6) == -0.12
    assert trend_ready["manual_review_required"] is True
    assert trend_ready["auto_trade_enabled"] is False
    assert trend_ready["production_watchlist_enabled"] is False
    assert trend_ready["production_write_enabled"] is False

    observe = groups.loc["risk_shadow|shadow_observe"]
    assert observe["sample_count"] == 1
    assert observe["complete_count"] == 0
    assert observe["insufficient_data_count"] == 1
    assert pd.isna(observe["forward_5d_return_mean"])


def test_build_shadow_outcome_analytics_preserves_review_metadata_and_writes_artifacts(tmp_path):
    analytics = build_shadow_outcome_analytics(
        review_start_date="2026-06-30",
        review_end_date="2026-08-29",
        shadow_outcomes=_outcomes(),
        horizons=[5, 20],
        run_id="p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
    )
    paths = write_shadow_outcome_analytics(analytics, tmp_path)

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["run_id"] == "p14-shadow-outcome-analytics-2026-06-30-2026-08-29"
    assert payload["group_by"] == ["shadow_layer", "shadow_status"]
    assert payload["group_count"] == 2
    assert payload["manual_review_required"] is True
    assert payload["auto_trade_enabled"] is False
    assert Path(paths["groups_csv_path"]).exists()
    assert Path(paths["markdown_path"]).exists()


def test_build_shadow_outcome_analytics_rejects_production_enabled_rows():
    outcomes = _outcomes()
    outcomes.loc[0, "production_watchlist_enabled"] = True

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_outcome_analytics_from_frames(shadow_outcomes=outcomes)


def test_build_shadow_outcome_analytics_rejects_missing_lineage():
    outcomes = _outcomes()
    outcomes.loc[0, "source_p10_proposal_run_id"] = ""

    with pytest.raises(ValueError, match="required_field_missing: source_p10_proposal_run_id"):
        build_shadow_outcome_analytics_from_frames(shadow_outcomes=outcomes)


def test_default_horizons_are_positive_and_stable():
    assert DEFAULT_SHADOW_OUTCOME_ANALYTICS_HORIZONS == [1, 3, 5, 10, 20, 60]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcome_analytics.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'stock_research.operator_decision.shadow_outcome_analytics'`.

- [ ] **Step 3: Implement analytics module**

Create `src/stock_research/operator_decision/shadow_outcome_analytics.py` with these public functions and exact signatures:

```python
DEFAULT_SHADOW_OUTCOME_ANALYTICS_HORIZONS = [1, 3, 5, 10, 20, 60]

def build_shadow_outcome_analytics_from_frames(
    *,
    shadow_outcomes: pd.DataFrame,
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    """Return one row per shadow_layer + shadow_status group."""

def build_shadow_outcome_analytics(
    *,
    review_start_date: str,
    review_end_date: str,
    shadow_outcomes: pd.DataFrame,
    horizons: list[int] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Return the JSON-serializable P14 analytics artifact payload."""

def write_shadow_outcome_analytics(analytics: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write JSON, groups CSV, and Markdown artifacts."""
```

Implementation requirements:

- Normalize horizons as sorted positive integers.
- Required text fields: `shadow_layer`, `shadow_status`, `source_p12_shadow_run_id`, `replay_result_id`, `source_p11_replay_run_id`, `source_p10_proposal_run_id`, `source_p9_analytics_run_id`, `candidate_date`, `asset_id`, `outcome_status`.
- Reject unsafe execution-like columns using the same field list used by P13 `shadow_outcomes.py`.
- Reject malformed safety fields.
- Force returned safety fields to `True/False/False/False`.
- Group only by `shadow_layer` and `shadow_status`.
- `group_key` must be `"{shadow_layer}|{shadow_status}"`.
- `sample_count` counts every row in the group.
- `complete_count` counts `outcome_status == "complete"`.
- `insufficient_data_count` counts `outcome_status == "insufficient_data"`.
- Source run counts are distinct counts for P12/P11/P10/P9 source run IDs.
- Horizon metrics use complete rows only and must not fill unavailable metrics with zero.
- Artifact stem must be `operator_shadow_outcome_analytics_{review_start_date}_{review_end_date}`.
- Write JSON, `_groups.csv`, and Markdown.

- [ ] **Step 4: Run contract tests**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcome_analytics.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/operator_decision/shadow_outcome_analytics.py tests/test_operator_shadow_outcome_analytics.py
git commit -m "feat: add p14 shadow outcome analytics contract"
```

---

### Task 2: Shadow Outcome Analytics Artifact CLI

**Files:**

- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_factor_cli.py`:

```python
def test_p14_shadow_outcome_analytics_parser_accepts_required_args():
    args = cli.build_parser().parse_args(
        [
            "p14-shadow-outcome-analytics",
            "--shadow-outcomes-json",
            "outputs/p13/operator_shadow_outcomes_2026-08-29.json",
            "--run-id",
            "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
            "--review-start-date",
            "2026-06-30",
            "--review-end-date",
            "2026-08-29",
            "--output-dir",
            "outputs/p14",
        ]
    )

    assert args.command == "p14-shadow-outcome-analytics"
    assert args.shadow_outcomes_json == "outputs/p13/operator_shadow_outcomes_2026-08-29.json"
    assert args.run_id == "p14-shadow-outcome-analytics-2026-06-30-2026-08-29"
    assert args.review_start_date == "2026-06-30"
    assert args.review_end_date == "2026-08-29"
    assert args.output_dir == "outputs/p14"


def test_p14_shadow_outcome_analytics_dispatches_to_builder(monkeypatch, tmp_path, capsys):
    json_path = tmp_path / "operator_shadow_outcomes_2026-08-29.json"
    json_path.write_text(
        '{"run_id":"p13","review_date":"2026-08-29","outcome_count":0,"outcomes":[]}',
        encoding="utf-8",
    )
    captured = {}

    def fake_load_shadow_outcome_read_model_rows(path):
        captured["loaded_path"] = str(path)
        return {"candidates": []}

    def fake_build_shadow_outcome_analytics(**kwargs):
        captured["build"] = kwargs
        return {
            "run_id": kwargs["run_id"],
            "review_start_date": kwargs["review_start_date"],
            "review_end_date": kwargs["review_end_date"],
            "group_count": 0,
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
            "groups": [],
        }

    def fake_write_shadow_outcome_analytics(analytics, output_dir):
        captured["written"] = {"analytics": analytics, "output_dir": str(output_dir)}
        return {
            "json_path": str(tmp_path / "p14.json"),
            "groups_csv_path": str(tmp_path / "p14_groups.csv"),
            "markdown_path": str(tmp_path / "p14.md"),
        }

    monkeypatch.setattr(cli, "load_shadow_outcome_read_model_rows", fake_load_shadow_outcome_read_model_rows)
    monkeypatch.setattr(cli, "build_shadow_outcome_analytics", fake_build_shadow_outcome_analytics)
    monkeypatch.setattr(cli, "write_shadow_outcome_analytics", fake_write_shadow_outcome_analytics)

    cli.main_for_args(
        [
            "p14-shadow-outcome-analytics",
            "--shadow-outcomes-json",
            str(json_path),
            "--run-id",
            "p14-run",
            "--review-start-date",
            "2026-06-30",
            "--review-end-date",
            "2026-08-29",
            "--output-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out
    assert "p14_shadow_outcome_analytics|json|" in output
    assert "p14_shadow_outcome_analytics|groups_csv|" in output
    assert "p14_shadow_outcome_analytics|markdown|" in output
    assert "p14_shadow_outcome_analytics|group_count|0" in output
    assert captured["loaded_path"] == str(json_path)
    assert captured["build"]["run_id"] == "p14-run"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -k 'p14_shadow_outcome_analytics' -q
```

Expected: FAIL because parser rejects `p14-shadow-outcome-analytics` or CLI imports are missing.

- [ ] **Step 3: Wire CLI imports and parser**

In `src/stock_research/cli.py`, import:

```python
from stock_research.operator_decision.shadow_outcome_analytics import (
    build_shadow_outcome_analytics,
    write_shadow_outcome_analytics,
)
from stock_research.operator_decision.shadow_outcomes_read_model import load_shadow_outcome_read_model_rows
```

Add parser:

```python
p14_shadow_outcome_analytics = subparsers.add_parser("p14-shadow-outcome-analytics")
p14_shadow_outcome_analytics.add_argument("--shadow-outcomes-json", required=True)
p14_shadow_outcome_analytics.add_argument("--run-id", required=True)
p14_shadow_outcome_analytics.add_argument("--review-start-date", required=True)
p14_shadow_outcome_analytics.add_argument("--review-end-date", required=True)
p14_shadow_outcome_analytics.add_argument("--output-dir", required=True)
```

Add dispatch:

```python
if args.command == "p14-shadow-outcome-analytics":
    rows = load_shadow_outcome_read_model_rows(args.shadow_outcomes_json)
    analytics = build_shadow_outcome_analytics(
        review_start_date=args.review_start_date,
        review_end_date=args.review_end_date,
        shadow_outcomes=pd.DataFrame(rows["candidates"]),
        run_id=args.run_id,
    )
    paths = write_shadow_outcome_analytics(analytics, args.output_dir)
    print(f"p14_shadow_outcome_analytics|json|{paths['json_path']}")
    print(f"p14_shadow_outcome_analytics|groups_csv|{paths['groups_csv_path']}")
    print(f"p14_shadow_outcome_analytics|markdown|{paths['markdown_path']}")
    print(f"p14_shadow_outcome_analytics|group_count|{analytics['group_count']}")
    return
```

If `pd` is not already imported in `cli.py`, add `import pandas as pd` near existing third-party imports.

- [ ] **Step 4: Run CLI tests**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcome_analytics.py tests/test_factor_cli.py -k 'shadow_outcome_analytics or p14_shadow_outcome_analytics' -q
```

Expected: relevant tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add p14 shadow outcome analytics cli"
```

---

### Task 3: Shadow Outcome Analytics Read Model

**Files:**

- Create: `src/stock_research/operator_decision/shadow_outcome_analytics_read_model.py`
- Create: `tests/test_operator_shadow_outcome_analytics_read_model.py`
- Modify: `src/stock_research/schema.py`
- Modify: `tests/test_schema.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing read-model tests**

Create `tests/test_operator_shadow_outcome_analytics_read_model.py`:

```python
import json

import pytest

from stock_research.operator_decision.shadow_outcome_analytics_read_model import (
    import_shadow_outcome_analytics,
    load_shadow_outcome_analytics_read_model_rows,
)


def _payload() -> dict:
    return {
        "run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
        "review_start_date": "2026-06-30",
        "review_end_date": "2026-08-29",
        "status": "shadow_outcome_analytics_ready",
        "group_by": ["shadow_layer", "shadow_status"],
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "horizons": [5, 20],
        "source_outcome_count": 3,
        "group_count": 1,
        "groups": [
            {
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 2,
                "complete_count": 2,
                "insufficient_data_count": 0,
                "source_p12_shadow_run_count": 1,
                "source_p11_replay_run_count": 1,
                "source_p10_proposal_run_count": 1,
                "source_p9_analytics_run_count": 1,
                "forward_5d_return_mean": 0.04,
                "forward_5d_return_median": 0.04,
                "forward_5d_win_rate": 0.5,
                "max_high_return_20d_mean": 0.19,
                "max_low_drawdown_20d_mean": -0.085,
                "max_low_drawdown_20d_worst": -0.12,
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


def test_load_shadow_outcome_analytics_rows_preserves_group_metrics_and_safety(tmp_path):
    json_path = tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")

    rows = load_shadow_outcome_analytics_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p14-shadow-outcome-analytics-2026-06-30-2026-08-29"
    assert rows["run"]["group_count"] == 1
    assert rows["run"]["production_watchlist_enabled"] is False
    group = rows["groups"][0]
    assert group["analytics_group_id"].startswith("operator_shadow_outcome_analytics:")
    assert group["group_key"] == "trend_shadow|shadow_ready"
    assert group["horizon_metrics"]["5"]["forward_return_mean"] == 0.04
    assert group["horizon_metrics"]["20"]["max_low_drawdown_worst"] == -0.12
    assert group["production_write_enabled"] is False


def test_load_shadow_outcome_analytics_rows_rejects_production_enabled_artifact(tmp_path):
    payload = _payload()
    payload["production_watchlist_enabled"] = True
    json_path = tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        load_shadow_outcome_analytics_read_model_rows(json_path)


def test_import_shadow_outcome_analytics_upserts_run_and_groups(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_outcome_analytics_read_model

    json_path = tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_outcome_analytics_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_outcome_analytics(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["group_count"] == 1
    assert result["run_ids"] == ["p14-shadow-outcome-analytics-2026-06-30-2026-08-29"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_shadow_watchlist_outcome_analytics_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    group_sql, group_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_shadow_watchlist_outcome_analytics_group" in group_sql
    assert "ON CONFLICT (analytics_group_id)" in group_sql
    assert group_params["group_key"] == "trend_shadow|shadow_ready"
```

- [ ] **Step 2: Write failing schema and import CLI tests**

Append to `tests/test_schema.py`:

```python
def test_p14_shadow_outcome_analytics_tables_exist():
    ddl = schema.SCHEMA_SQL

    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_analytics_run" in ddl
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_analytics_group" in ddl
    assert "idx_operator_shadow_watchlist_outcome_analytics_group_date" in ddl
    assert "idx_operator_shadow_watchlist_outcome_analytics_group_key" in ddl
```

Append to `tests/test_factor_cli.py`:

```python
def test_p14_import_shadow_outcome_analytics_parser_accepts_path():
    args = cli.build_parser().parse_args(
        ["p14-import-shadow-outcome-analytics", "--path", "outputs/p14"]
    )

    assert args.command == "p14-import-shadow-outcome-analytics"
    assert args.path == "outputs/p14"


def test_p14_import_shadow_outcome_analytics_dispatches(monkeypatch, capsys):
    captured = {}

    def fake_import_shadow_outcome_analytics(path, service):
        captured["path"] = path
        captured["service"] = service
        return {"imported_count": 2, "group_count": 3, "run_ids": ["p14-a", "p14-b"]}

    monkeypatch.setattr(cli, "import_shadow_outcome_analytics", fake_import_shadow_outcome_analytics)

    cli.main_for_args(
        [
            "p14-import-shadow-outcome-analytics",
            "--path",
            "outputs/p14",
            "--service",
            "stock_research_test",
        ]
    )

    output = capsys.readouterr().out
    assert "p14_import_shadow_outcome_analytics|imported|2" in output
    assert "p14_import_shadow_outcome_analytics|groups|3" in output
    assert "p14_import_shadow_outcome_analytics|runs|p14-a,p14-b" in output
    assert captured == {"path": "outputs/p14", "service": "stock_research_test"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcome_analytics_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'shadow_outcome_analytics or p14_import_shadow_outcome_analytics' -q
```

Expected: FAIL because read-model module, schema tables, and import CLI do not exist.

- [ ] **Step 4: Implement read model, schema, and import CLI**

Implement `src/stock_research/operator_decision/shadow_outcome_analytics_read_model.py` with these exact public functions:

```python
def load_shadow_outcome_analytics_read_model_rows(path: str | Path) -> dict[str, Any]:
    """Load one P14 JSON artifact into run and group read-model rows."""

def import_shadow_outcome_analytics(path: str | Path, *, service: str = SETTINGS.research_service) -> dict[str, Any]:
    """Import one artifact or a directory of P14 artifacts into ops tables."""
```

Requirements:

- Directory imports should load `operator_shadow_outcome_analytics_*.json`.
- Validate top-level and group-level safety fields.
- `analytics_group_id` must be run-scoped: hash `run_id|group_key`.
- Run upsert conflict target: `(run_id)`.
- Group upsert conflict target: `(analytics_group_id)`.
- Store `horizon_metrics` and `metadata` as JSONB.

Add schema DDL:

```sql
CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_analytics_run (
    run_id text PRIMARY KEY,
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    status text NOT NULL,
    group_by jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_outcome_count integer NOT NULL DEFAULT 0,
    group_count integer NOT NULL DEFAULT 0,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    groups_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_outcome_analytics_group (
    analytics_group_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ops.operator_shadow_watchlist_outcome_analytics_run(run_id) ON DELETE CASCADE,
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    group_key text NOT NULL,
    shadow_layer text NOT NULL,
    shadow_status text NOT NULL,
    sample_count integer NOT NULL DEFAULT 0,
    complete_count integer NOT NULL DEFAULT 0,
    insufficient_data_count integer NOT NULL DEFAULT 0,
    source_p12_shadow_run_count integer NOT NULL DEFAULT 0,
    source_p11_replay_run_count integer NOT NULL DEFAULT 0,
    source_p10_proposal_run_count integer NOT NULL DEFAULT 0,
    source_p9_analytics_run_count integer NOT NULL DEFAULT 0,
    horizon_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    analytics_artifact_path text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_watchlist_outcome_analytics_group_date
    ON ops.operator_shadow_watchlist_outcome_analytics_group (review_end_date DESC, sample_count DESC);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_watchlist_outcome_analytics_group_key
    ON ops.operator_shadow_watchlist_outcome_analytics_group (group_key, review_end_date DESC);
```

Wire `p14-import-shadow-outcome-analytics` in `cli.py`:

```python
from stock_research.operator_decision.shadow_outcome_analytics_read_model import import_shadow_outcome_analytics

p14_import_shadow_outcome_analytics = subparsers.add_parser("p14-import-shadow-outcome-analytics")
p14_import_shadow_outcome_analytics.add_argument("--path", required=True)
p14_import_shadow_outcome_analytics.add_argument("--service", default=SETTINGS.research_service)

if args.command == "p14-import-shadow-outcome-analytics":
    result = import_shadow_outcome_analytics(args.path, service=args.service)
    print(f"p14_import_shadow_outcome_analytics|imported|{result['imported_count']}")
    print(f"p14_import_shadow_outcome_analytics|groups|{result['group_count']}")
    print(f"p14_import_shadow_outcome_analytics|runs|{','.join(result['run_ids'])}")
    return
```

- [ ] **Step 5: Run read-model tests**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcome_analytics.py tests/test_operator_shadow_outcome_analytics_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'shadow_outcome_analytics or p14_import_shadow_outcome_analytics' -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/stock_research/operator_decision/shadow_outcome_analytics_read_model.py src/stock_research/schema.py src/stock_research/cli.py tests/test_operator_shadow_outcome_analytics_read_model.py tests/test_schema.py tests/test_factor_cli.py
git commit -m "feat: add p14 shadow outcome analytics read model"
```

---

### Task 4: Dashboard Read-Only Analytics View

**Files:**

- Create: `src/stock_research/dashboard/shadow_outcome_analytics.py`
- Create: `tests/test_dashboard_shadow_outcome_analytics.py`
- Create: `dashboard/src/components/ShadowOutcomeAnalyticsPanel.tsx`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_app.py`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/tests/client.test.ts`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Modify: `dashboard/tests/app-smoke.spec.ts`

- [ ] **Step 1: Write failing backend dashboard tests**

Create `tests/test_dashboard_shadow_outcome_analytics.py`:

```python
from psycopg import errors as psycopg_errors

from stock_research.dashboard import shadow_outcome_analytics


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_shadow_outcome_analytics_summary_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
                "review_start_date": "2026-06-30",
                "review_end_date": "2026-08-29",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 2,
                "complete_count": 2,
                "insufficient_data_count": 0,
                "source_p12_shadow_run_count": 1,
                "source_p11_replay_run_count": 1,
                "source_p10_proposal_run_count": 1,
                "source_p9_analytics_run_count": 1,
                "horizon_metrics": {"20": {"forward_return_mean": 0.12, "forward_win_rate": 1.0}},
                "analytics_artifact_path": "outputs/p14/analytics.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(shadow_outcome_analytics, "connect", fake_connect)
    monkeypatch.setattr(shadow_outcome_analytics, "fetch_all", fake_fetch_all)

    result = shadow_outcome_analytics.load_shadow_outcome_analytics_summary(
        start_date="2026-06-01",
        end_date="2026-08-31",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_shadow_watchlist_outcome_analytics_group" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-08-31", 10]
    assert captured["service"] == "stock_research_test"
    assert result[0]["group_key"] == "trend_shadow|shadow_ready"
    assert result[0]["horizon_metrics"]["20"]["forward_return_mean"] == 0.12
    assert result[0]["production_write_enabled"] is False


def test_load_shadow_outcome_analytics_summary_returns_empty_when_table_missing(monkeypatch):
    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        raise psycopg_errors.UndefinedTable("missing P14 analytics table")

    monkeypatch.setattr(shadow_outcome_analytics, "connect", fake_connect)
    monkeypatch.setattr(shadow_outcome_analytics, "fetch_all", fake_fetch_all)

    assert shadow_outcome_analytics.load_shadow_outcome_analytics_summary(
        start_date="2026-06-01",
        end_date="2026-08-31",
    ) == []
```

Append to `tests/test_dashboard_app.py`:

```python
def test_shadow_outcome_analytics_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_analytics(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return [
            {
                "run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
                "review_start_date": "2026-06-30",
                "review_end_date": "2026-08-29",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 2,
                "complete_count": 2,
                "insufficient_data_count": 0,
                "source_p12_shadow_run_count": 1,
                "source_p11_replay_run_count": 1,
                "source_p10_proposal_run_count": 1,
                "source_p9_analytics_run_count": 1,
                "horizon_metrics": {"20": {"forward_return_mean": 0.12}},
                "analytics_artifact_path": "outputs/p14/analytics.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_shadow_outcome_analytics_summary", fake_load_analytics)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-outcome-analytics?start_date=2026-06-01&end_date=2026-08-31&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json()["items"][0]["group_key"] == "trend_shadow|shadow_ready"
    assert response.json()["items"][0]["production_watchlist_enabled"] is False
```

- [ ] **Step 2: Run backend tests to verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_shadow_outcome_analytics.py tests/test_dashboard_app.py -k 'shadow_outcome_analytics' -q
```

Expected: FAIL because module/route is missing.

- [ ] **Step 3: Implement backend dashboard query and route**

Create `src/stock_research/dashboard/shadow_outcome_analytics.py` with this exact public function:

```python
def load_shadow_outcome_analytics_summary(
    start_date: str,
    end_date: str,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    """Return read-only P14 analytics dashboard rows."""
```

Requirements:

- Query `ops.operator_shadow_watchlist_outcome_analytics_group`.
- Filter `review_end_date BETWEEN %s AND %s`.
- Order by `review_end_date DESC, sample_count DESC, group_key`.
- Catch `psycopg.errors.UndefinedTable` and `psycopg.errors.InvalidSchemaName`, returning `[]`.
- Normalize `horizon_metrics` from dict or JSON string.
- Force safety fields in returned rows to `True/False/False/False`.

In `src/stock_research/dashboard/app.py`, import the loader and add:

```python
@app.get("/api/shadow-outcome-analytics")
def shadow_outcome_analytics(
    start_date: str,
    end_date: str,
    limit: int = 20,
):
    return {
        "items": load_shadow_outcome_analytics_summary(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    }
```

- [ ] **Step 4: Run backend dashboard tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_shadow_outcome_analytics.py tests/test_dashboard_app.py -k 'shadow_outcome_analytics' -q
```

Expected: selected tests pass.

- [ ] **Step 5: Write failing frontend tests**

Modify `dashboard/src/api/types.ts`:

```ts
export interface ShadowOutcomeAnalyticsRow {
  run_id: string;
  review_start_date: string;
  review_end_date: string;
  group_key: string;
  shadow_layer: string;
  shadow_status: string;
  sample_count: number;
  complete_count: number;
  insufficient_data_count: number;
  source_p12_shadow_run_count: number;
  source_p11_replay_run_count: number;
  source_p10_proposal_run_count: number;
  source_p9_analytics_run_count: number;
  horizon_metrics: Record<string, Record<string, number | null>>;
  analytics_artifact_path: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_watchlist_enabled: boolean;
  production_write_enabled: boolean;
}
```

Append tests in `dashboard/tests/client.test.ts`:

```ts
it('fetches shadow outcome analytics', async () => {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    json: async () => ({ items: [{ group_key: 'trend_shadow|shadow_ready' }] }),
  })) as unknown as typeof fetch;

  const result = await fetchShadowOutcomeAnalytics(
    '2026-06-01',
    '2026-08-31',
    fetchMock,
  );

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/shadow-outcome-analytics?start_date=2026-06-01&end_date=2026-08-31&limit=20',
  );
  expect(result[0].group_key).toBe('trend_shadow|shadow_ready');
});
```

Add app shell assertions in `dashboard/tests/app-shell.test.tsx`:

```ts
expect(await screen.findByText('Shadow Outcome Analytics')).toBeInTheDocument();
expect(screen.getByText('trend_shadow')).toBeInTheDocument();
expect(screen.queryByRole('button', { name: /promote|trade|write watchlist/i })).not.toBeInTheDocument();
```

Update `dashboard/tests/app-smoke.spec.ts` mocks so `/api/shadow-outcome-analytics` returns one row and assert the panel title appears on desktop and no mobile overflow occurs.

- [ ] **Step 6: Run frontend tests to verify they fail**

Run:

```bash
cd dashboard
pnpm test
```

Expected: FAIL because `fetchShadowOutcomeAnalytics` and `ShadowOutcomeAnalyticsPanel` are missing.

- [ ] **Step 7: Implement frontend client, component, and app wiring**

Modify `dashboard/src/api/client.ts`:

```ts
export async function fetchShadowOutcomeAnalytics(
  startDate: string,
  endDate: string,
  fetcher: typeof fetch = fetch,
  limit = 20,
): Promise<ShadowOutcomeAnalyticsRow[]> {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    limit: String(limit),
  });
  const response = await fetcher(`/api/shadow-outcome-analytics?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch shadow outcome analytics: ${response.status}`);
  }
  const payload = await response.json() as { items: ShadowOutcomeAnalyticsRow[] };
  return payload.items;
}
```

Create `dashboard/src/components/ShadowOutcomeAnalyticsPanel.tsx`:

```tsx
import type { ShadowOutcomeAnalyticsRow } from '../api/types';

interface Props {
  rows: ShadowOutcomeAnalyticsRow[];
  loading: boolean;
}

function formatPercent(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : 'n/a';
}

export function ShadowOutcomeAnalyticsPanel({ rows, loading }: Props) {
  if (loading) {
    return <section className="panel"><h2>Shadow Outcome Analytics</h2><p>Loading</p></section>;
  }
  return (
    <section className="panel">
      <h2>Shadow Outcome Analytics</h2>
      {rows.length === 0 ? (
        <p>No shadow outcome analytics.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Layer</th>
                <th>Status</th>
                <th>Sample</th>
                <th>Complete</th>
                <th>20d Mean</th>
                <th>20d Win</th>
                <th>Worst DD</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const horizon = row.horizon_metrics['20'] ?? {};
                return (
                  <tr key={row.group_key}>
                    <td>{row.shadow_layer}</td>
                    <td>{row.shadow_status}</td>
                    <td>{row.sample_count}</td>
                    <td>{row.complete_count}</td>
                    <td>{formatPercent(horizon.forward_return_mean)}</td>
                    <td>{formatPercent(horizon.forward_win_rate)}</td>
                    <td>{formatPercent(horizon.max_low_drawdown_worst)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
```

Wire it into `dashboard/src/App.tsx` using existing dashboard loading/error patterns.

- [ ] **Step 8: Run frontend verification**

Run:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

Expected: Vitest passes, build passes, Playwright passes.

- [ ] **Step 9: Commit**

Run:

```bash
git add src/stock_research/dashboard/shadow_outcome_analytics.py tests/test_dashboard_shadow_outcome_analytics.py src/stock_research/dashboard/app.py tests/test_dashboard_app.py dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/App.tsx dashboard/src/components/ShadowOutcomeAnalyticsPanel.tsx dashboard/tests/client.test.ts dashboard/tests/app-shell.test.tsx dashboard/tests/app-smoke.spec.ts
git commit -m "feat: add p14 shadow outcome analytics dashboard"
```

---

### Task 5: Smoke, Runbook, Completion Review

**Files:**

- Create: `src/stock_research/operator_decision/p14_smoke.py`
- Create: `tests/test_p14_shadow_outcome_analytics_smoke.py`
- Create: `docs/quant_system/50_p14_shadow_outcome_analytics_runbook.md`
- Create: `docs/quant_system/51_p14_shadow_outcome_analytics_completion.md`

- [ ] **Step 1: Write failing smoke test**

Create `tests/test_p14_shadow_outcome_analytics_smoke.py`:

```python
from pathlib import Path

from stock_research.operator_decision.p14_smoke import build_p14_shadow_outcome_analytics_smoke


def test_p14_smoke_builds_shadow_outcome_analytics_artifacts_and_read_model_rows(tmp_path):
    result = build_p14_shadow_outcome_analytics_smoke(tmp_path)

    assert Path(result["p13_shadow_outcome_json_path"]).exists()
    assert Path(result["p14_shadow_outcome_analytics_json_path"]).exists()
    assert Path(result["p14_shadow_outcome_analytics_groups_csv_path"]).exists()
    assert Path(result["p14_shadow_outcome_analytics_markdown_path"]).exists()
    assert result["source_outcome_count"] == 1
    assert result["group_count"] == 1
    assert result["read_model_group_count"] == 1
    assert result["group_keys"] == ["trend_shadow|shadow_ready"]
    assert result["sample_counts"] == [1]
    assert result["complete_counts"] == [1]
    assert result["insufficient_data_counts"] == [0]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_watchlist_enabled"] is False
    assert result["production_write_enabled"] is False
```

- [ ] **Step 2: Run smoke test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_p14_shadow_outcome_analytics_smoke.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'stock_research.operator_decision.p14_smoke'`.

- [ ] **Step 3: Implement P14 smoke**

Create `src/stock_research/operator_decision/p14_smoke.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.operator_decision.p13_smoke import build_p13_shadow_outcome_smoke
from stock_research.operator_decision.shadow_outcome_analytics import (
    build_shadow_outcome_analytics,
    write_shadow_outcome_analytics,
)
from stock_research.operator_decision.shadow_outcome_analytics_read_model import (
    load_shadow_outcome_analytics_read_model_rows,
)
from stock_research.operator_decision.shadow_outcomes_read_model import (
    load_shadow_outcome_read_model_rows,
)


def build_p14_shadow_outcome_analytics_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p13_result = build_p13_shadow_outcome_smoke(output_path)
    p14_dir = output_path / "p14"
    p14_dir.mkdir(parents=True, exist_ok=True)

    outcome_rows = load_shadow_outcome_read_model_rows(p13_result["p13_shadow_outcome_json_path"])
    analytics = build_shadow_outcome_analytics(
        review_start_date="2026-06-30",
        review_end_date="2026-08-29",
        shadow_outcomes=pd.DataFrame(outcome_rows["candidates"]),
        run_id="p14-smoke-shadow-outcome-analytics-2026-06-30-2026-08-29",
    )
    analytics_paths = write_shadow_outcome_analytics(analytics, p14_dir)
    read_rows = load_shadow_outcome_analytics_read_model_rows(analytics_paths["json_path"])
    run = read_rows["run"]
    groups = read_rows["groups"]
    return {
        "p13_shadow_outcome_json_path": p13_result["p13_shadow_outcome_json_path"],
        "p14_shadow_outcome_analytics_json_path": analytics_paths["json_path"],
        "p14_shadow_outcome_analytics_groups_csv_path": analytics_paths["groups_csv_path"],
        "p14_shadow_outcome_analytics_markdown_path": analytics_paths["markdown_path"],
        "source_outcome_count": int(run["source_outcome_count"]),
        "group_count": int(run["group_count"]),
        "read_model_group_count": len(groups),
        "group_keys": sorted({str(row["group_key"]) for row in groups}),
        "sample_counts": sorted({int(row["sample_count"]) for row in groups}),
        "complete_counts": sorted({int(row["complete_count"]) for row in groups}),
        "insufficient_data_counts": sorted({int(row["insufficient_data_count"]) for row in groups}),
        "manual_review_required": bool(run["manual_review_required"]),
        "auto_trade_enabled": bool(run["auto_trade_enabled"]),
        "production_watchlist_enabled": bool(run["production_watchlist_enabled"]),
        "production_write_enabled": bool(run["production_write_enabled"]),
    }
```

- [ ] **Step 4: Run smoke tests**

Run:

```bash
.venv/bin/pytest tests/test_p14_shadow_outcome_analytics_smoke.py tests/test_p13_shadow_outcomes_smoke.py -q
```

Expected: selected tests pass.

- [ ] **Step 5: Run actual smoke command**

Run:

```bash
rm -rf /tmp/stock_research_p14_smoke
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p14_smoke import build_p14_shadow_outcome_analytics_smoke
result = build_p14_shadow_outcome_analytics_smoke(Path('/tmp/stock_research_p14_smoke'))
print(f"p14_smoke|p13_shadow_outcome|{result['p13_shadow_outcome_json_path']}")
print(f"p14_smoke|p14_shadow_outcome_analytics|{result['p14_shadow_outcome_analytics_json_path']}")
print(f"p14_smoke|groups_csv|{result['p14_shadow_outcome_analytics_groups_csv_path']}")
print(f"p14_smoke|markdown|{result['p14_shadow_outcome_analytics_markdown_path']}")
print(f"p14_smoke|source_outcome_count|{result['source_outcome_count']}")
print(f"p14_smoke|group_count|{result['group_count']}")
print(f"p14_smoke|read_model_groups|{result['read_model_group_count']}")
print(f"p14_smoke|group_keys|{','.join(result['group_keys'])}")
print(f"p14_smoke|sample_counts|{','.join(str(value) for value in result['sample_counts'])}")
print(f"p14_smoke|complete_counts|{','.join(str(value) for value in result['complete_counts'])}")
print(f"p14_smoke|insufficient_data_counts|{','.join(str(value) for value in result['insufficient_data_counts'])}")
print(f"p14_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p14_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p14_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p14_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Record the exact output in `docs/quant_system/51_p14_shadow_outcome_analytics_completion.md`.

- [ ] **Step 6: Write runbook and completion review**

Create `docs/quant_system/50_p14_shadow_outcome_analytics_runbook.md` with:

- purpose and review-only boundary
- artifact command
- import command
- dashboard endpoint
- smoke command
- safety notes

Create `docs/quant_system/51_p14_shadow_outcome_analytics_completion.md` with:

- delivered capabilities for P14-0 through P14-5
- actual smoke output from Step 5
- final verification command list and exact pass counts
- safety review
- known non-P14 workspace dirty file note

- [ ] **Step 7: Final verification**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcome_analytics.py tests/test_operator_shadow_outcome_analytics_read_model.py tests/test_p14_shadow_outcome_analytics_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_outcome_analytics.py tests/test_dashboard_app.py -k 'shadow_outcome_analytics or p14_shadow_outcome_analytics or p14_import_shadow_outcome_analytics or dashboard' -q
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

Expected: Python focused tests pass, Vitest passes, build passes, Playwright passes.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/stock_research/operator_decision/p14_smoke.py tests/test_p14_shadow_outcome_analytics_smoke.py docs/quant_system/50_p14_shadow_outcome_analytics_runbook.md docs/quant_system/51_p14_shadow_outcome_analytics_completion.md
git commit -m "docs: complete p14 shadow outcome analytics governance"
```

---

## Final Review And Integration

- [ ] **Step 1: Final code review**

Dispatch a final code-reviewer for the whole P14 branch. Review for:

- review-only boundary
- no candidate ranking or promotion recommendation
- no production watchlist/factor/scheduler/trading writes
- correct group-by scope: only `shadow_layer + shadow_status`
- source lineage preserved from P13 back to P12/P11/P10/P9
- idempotent run-scoped read-model IDs
- missing-table dashboard behavior
- dashboard has no action controls

- [ ] **Step 2: Final verification**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcome_analytics.py tests/test_operator_shadow_outcome_analytics_read_model.py tests/test_p14_shadow_outcome_analytics_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_outcome_analytics.py tests/test_dashboard_app.py -k 'shadow_outcome_analytics or p14_shadow_outcome_analytics or p14_import_shadow_outcome_analytics or dashboard' -q
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
git status --short --branch
git log --oneline -10
```

- [ ] **Step 3: Finish branch**

Use superpowers:finishing-a-development-branch after tests pass. Present the standard options:

1. Merge back to `factor-scoring-daily-pipeline` locally
2. Push and create a Pull Request
3. Keep the branch as-is
4. Discard this work
