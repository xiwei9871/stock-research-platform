# P12 Shadow Watchlist Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a review-only P12 shadow watchlist candidate layer from P11 replay evidence without writing production watchlist, scoring, scheduler, or trading state.

**Architecture:** P12 follows the P10/P11 pattern: artifact contract, CLI, read-model import, dashboard read-only panel, smoke, runbook, completion review. It uses independent `ops.operator_shadow_watchlist_*` tables and local JSON/CSV/Markdown artifacts so shadow evidence is queryable but cannot be confused with production `watchlist.watchlist_daily_signal`.

**Tech Stack:** Python, pandas, argparse CLI, PostgreSQL SQL strings in `schema.py`, FastAPI dashboard API, React/Vite dashboard, Vitest, Playwright, pytest.

---

## File Structure

Create:

- `src/stock_research/operator_decision/shadow_watchlist.py`: P12 artifact contract, validation, writer, Markdown rendering.
- `tests/test_operator_shadow_watchlist.py`: contract and artifact writer tests.
- `src/stock_research/operator_decision/shadow_watchlist_read_model.py`: P12 JSON artifact loader and idempotent read-model importer.
- `tests/test_operator_shadow_watchlist_read_model.py`: importer/read-model tests.
- `src/stock_research/operator_decision/p12_smoke.py`: synthetic P10/P11/P12 smoke.
- `tests/test_p12_shadow_watchlist_smoke.py`: smoke test.
- `src/stock_research/dashboard/shadow_watchlist.py`: dashboard read-only query.
- `tests/test_dashboard_shadow_watchlist.py`: dashboard backend query tests.
- `dashboard/src/components/ShadowWatchlistPanel.tsx`: read-only panel.
- `docs/quant_system/43_p12_shadow_watchlist_scope_freeze.md`: P12 scope freeze.
- `docs/quant_system/44_p12_shadow_watchlist_runbook.md`: P12 runbook.
- `docs/quant_system/45_p12_shadow_watchlist_completion.md`: P12 completion review.

Modify:

- `src/stock_research/cli.py`: add `p12-shadow-watchlist` and `p12-import-shadow-watchlist`, staging only P12 hunks because this file has unrelated dirty changes.
- `src/stock_research/schema.py`: add `ops.operator_shadow_watchlist_run` and `ops.operator_shadow_watchlist_candidate` plus indexes.
- `tests/test_schema.py`: assert P12 tables/indexes.
- `tests/test_factor_cli.py`: CLI parser/dispatch tests.
- `src/stock_research/dashboard/app.py`: add `GET /api/shadow-watchlist`.
- `tests/test_dashboard_app.py`: route test.
- `dashboard/src/api/types.ts`: add `ShadowWatchlistRow`.
- `dashboard/src/api/client.ts`: add `fetchShadowWatchlist`.
- `dashboard/src/App.tsx`: load and render P12 panel.
- `dashboard/tests/client.test.ts`: client test.
- `dashboard/tests/app-shell.test.tsx`: app panel/loading/empty tests.
- `dashboard/tests/app-smoke.spec.ts`: browser smoke route/mock/assertions.

Do not modify:

- `watchlist.watchlist_daily_signal` write paths.
- `factor.stock_score_daily` write paths.
- `factor.factor_approval` write paths.
- scheduler wrappers.
- trading/broker/order/account/position modules.
- unrelated watchlist/trend/factor dirty files.

---

### Task 0: P12 Scope Freeze

**Files:**

- Create: `docs/quant_system/43_p12_shadow_watchlist_scope_freeze.md`

- [ ] **Step 1: Write the scope freeze document**

Create `docs/quant_system/43_p12_shadow_watchlist_scope_freeze.md` with this structure:

```markdown
# P12 Shadow Watchlist Experiment Scope Freeze

Date: 2026-06-01

## Status

P12 scope is frozen around **Shadow Watchlist Experiment Read Model**.

## Why This Scope

P11 produced offline replay evidence for approved P10 proposals. The next useful step is a review-only shadow watchlist candidate layer, not a production watchlist write path.

## In Scope

- Shadow watchlist candidate artifact contract.
- CLI to generate JSON/CSV/Markdown artifacts from P11 replay evidence.
- Read-model tables under `ops`.
- Import helper and CLI using idempotent upserts.
- Read-only dashboard API and panel.
- Synthetic smoke, runbook, and completion review.

## Out Of Scope

- Writing `watchlist.watchlist_daily_signal`.
- Writing `factor.stock_score_daily`.
- Writing `factor.factor_approval`.
- Changing ranking/scoring logic.
- Changing production watchlist generation logic.
- Scheduler automation.
- Broker, order, execution, account, cash, or position state.
- Treating `shadow_ready` or `shadow_observe` as production approval.

## Safety Fields

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`
```

- [ ] **Step 2: Verify document exists**

Run:

```bash
test -s docs/quant_system/43_p12_shadow_watchlist_scope_freeze.md
```

Expected: exit code `0`.

- [ ] **Step 3: Commit**

Run:

```bash
git add docs/quant_system/43_p12_shadow_watchlist_scope_freeze.md
git commit -m "docs: freeze p12 shadow watchlist scope"
```

---

### Task 1: Shadow Watchlist Candidate Contract

**Files:**

- Create: `src/stock_research/operator_decision/shadow_watchlist.py`
- Create: `tests/test_operator_shadow_watchlist.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_operator_shadow_watchlist.py`:

```python
import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.operator_decision.shadow_watchlist import (
    SHADOW_WATCHLIST_STATUSES,
    build_shadow_watchlist_candidates_from_frames,
    build_shadow_watchlist_review,
    write_shadow_watchlist_review,
)


def _replay_results() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "replay_result_id": "p11-replay:001",
                "run_id": "p11-replay-run-2026-06-30",
                "proposal_id": "p10-proposal:001",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "replay_start_date": "2026-01-01",
                "replay_end_date": "2026-06-30",
                "replay_input_artifact_paths": ["inputs/p11/replay_candidates.csv"],
                "replay_status": "passed_offline_replay",
                "metric_summary": {"win_rate": 0.75},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_write_enabled": False,
            }
        ]
    )


def _candidate_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
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
                "candidate_reason": "Passed replay with acceptable drawdown.",
                "evidence_artifact_paths": json.dumps(["outputs/p11/replay.json"]),
                "metric_summary": json.dumps({"win_rate": 0.75}),
                "reviewer_id": "reviewer-a",
                "status": "shadow_ready",
                "review_notes": "Observe in shadow list only.",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]
    )


def test_shadow_watchlist_candidates_preserve_replay_sources_and_safety_fields():
    candidates = build_shadow_watchlist_candidates_from_frames(
        replay_results=_replay_results(),
        candidate_events=_candidate_rows(),
    )

    assert set(SHADOW_WATCHLIST_STATUSES) == {
        "shadow_ready",
        "shadow_observe",
        "shadow_rejected",
        "needs_more_data",
        "blocked",
    }
    row = candidates.iloc[0]
    assert row["shadow_candidate_id"] == "p12-shadow:001"
    assert row["replay_result_id"] == "p11-replay:001"
    assert row["source_p11_replay_run_id"] == "p11-replay-run-2026-06-30"
    assert row["source_p10_proposal_run_id"] == "p10-proposals-2026-06-30"
    assert row["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"
    assert row["asset_id"] == "000001.SZ"
    assert row["evidence_artifact_paths"] == ["outputs/p11/replay.json"]
    assert row["metric_summary"] == {"win_rate": 0.75}
    assert row["manual_review_required"] is True
    assert row["auto_trade_enabled"] is False
    assert row["production_watchlist_enabled"] is False
    assert row["production_write_enabled"] is False


def test_shadow_watchlist_review_summarizes_statuses():
    review = build_shadow_watchlist_review(
        replay_results=_replay_results(),
        candidate_events=_candidate_rows(),
        run_id="p12-shadow-watchlist-2026-06-30",
        review_date="2026-06-30",
    )

    assert review["run_id"] == "p12-shadow-watchlist-2026-06-30"
    assert review["review_date"] == "2026-06-30"
    assert review["status"] == "shadow_watchlist_review_ready"
    assert review["candidate_count"] == 1
    assert review["status_counts"] == {"shadow_ready": 1}
    assert review["manual_review_required"] is True
    assert review["auto_trade_enabled"] is False
    assert review["production_watchlist_enabled"] is False
    assert review["production_write_enabled"] is False


def test_shadow_watchlist_rejects_invalid_or_unsafe_inputs():
    invalid = _candidate_rows().copy()
    invalid.loc[0, "status"] = "write_to_watchlist"
    with pytest.raises(ValueError, match="invalid_shadow_status"):
        build_shadow_watchlist_candidates_from_frames(
            replay_results=_replay_results(),
            candidate_events=invalid,
        )

    missing_evidence = _candidate_rows().copy()
    missing_evidence.loc[0, "evidence_artifact_paths"] = json.dumps([])
    with pytest.raises(ValueError, match="evidence_artifact_required"):
        build_shadow_watchlist_candidates_from_frames(
            replay_results=_replay_results(),
            candidate_events=missing_evidence,
        )

    production = _candidate_rows().copy()
    production.loc[0, "production_watchlist_enabled"] = True
    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_watchlist_candidates_from_frames(
            replay_results=_replay_results(),
            candidate_events=production,
        )

    unsafe = _candidate_rows().copy()
    unsafe["order_id"] = ["order-1"]
    with pytest.raises(ValueError, match="unsafe_execution_field: order_id"):
        build_shadow_watchlist_candidates_from_frames(
            replay_results=_replay_results(),
            candidate_events=unsafe,
        )


def test_write_shadow_watchlist_review_outputs_review_only_artifacts(tmp_path):
    review = build_shadow_watchlist_review(
        replay_results=_replay_results(),
        candidate_events=_candidate_rows(),
        run_id="p12-shadow-watchlist-2026-06-30",
        review_date="2026-06-30",
    )

    paths = write_shadow_watchlist_review(review, tmp_path)

    assert set(paths) == {"json_path", "candidates_csv_path", "markdown_path"}
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["manual_review_required"] is True
    assert payload["auto_trade_enabled"] is False
    assert payload["production_watchlist_enabled"] is False
    assert payload["production_write_enabled"] is False
    assert payload["candidates"][0]["asset_id"] == "000001.SZ"

    csv_rows = pd.read_csv(paths["candidates_csv_path"])
    assert csv_rows.loc[0, "shadow_candidate_id"] == "p12-shadow:001"

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "P12 Shadow Watchlist Review" in markdown
    assert "production_watchlist_enabled: false" in markdown
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_watchlist.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'stock_research.operator_decision.shadow_watchlist'`.

- [ ] **Step 3: Implement contract module**

Create `src/stock_research/operator_decision/shadow_watchlist.py` with functions:

```python
SHADOW_WATCHLIST_STATUSES = [
    "shadow_ready",
    "shadow_observe",
    "shadow_rejected",
    "needs_more_data",
    "blocked",
]

SHADOW_COLUMNS = [
    "shadow_candidate_id",
    "replay_result_id",
    "source_p11_replay_run_id",
    "source_p10_proposal_run_id",
    "source_p9_analytics_run_id",
    "candidate_date",
    "asset_id",
    "stock_code",
    "stock_name",
    "shadow_layer",
    "candidate_reason",
    "evidence_artifact_paths",
    "metric_summary",
    "reviewer_id",
    "status",
    "review_notes",
    "manual_review_required",
    "auto_trade_enabled",
    "production_watchlist_enabled",
    "production_write_enabled",
]
```

Implement:

- `build_shadow_watchlist_candidates_from_frames(replay_results, candidate_events) -> pd.DataFrame`
- `build_shadow_watchlist_review(replay_results, candidate_events, run_id=None, review_date=None) -> dict`
- `write_shadow_watchlist_review(review, output_dir) -> dict[str, str]`

Validation rules:

- candidate `replay_result_id` must exist in replay rows.
- replay row must have `replay_status == "passed_offline_replay"`.
- candidate source P11/P10/P9 values must match replay row values.
- `asset_id`, `shadow_candidate_id`, `candidate_date`, `shadow_layer`, `candidate_reason`, `reviewer_id`, and `status` are required.
- `evidence_artifact_paths` must parse to a non-empty list.
- `status` must be in `SHADOW_WATCHLIST_STATUSES`.
- reject columns named `order_id`, `trade_id`, `execution_id`, `broker`, `quantity`, `shares`, `price`, `notional`, `account_id`, `cash`, `position_id`, `side`, `order_side`, `limit_price`, or `stop_price` when populated.
- normalize safety fields to `True/False/False/False`.

Writer filenames:

- `operator_shadow_watchlist_<review_date>.json`
- `operator_shadow_watchlist_<review_date>_candidates.csv`
- `operator_shadow_watchlist_<review_date>.md`

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_watchlist.py -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/operator_decision/shadow_watchlist.py tests/test_operator_shadow_watchlist.py
git commit -m "feat: add p12 shadow watchlist contract"
```

---

### Task 2: Shadow Artifact CLI

**Files:**

- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

Because `src/stock_research/cli.py` has unrelated dirty hunks, stage only P12 hunks with a custom `git apply --cached` patch or `git add -p`. Do not stage unrelated watchlist/trend CLI changes.

- [ ] **Step 1: Write failing CLI tests**

Add to `tests/test_factor_cli.py` near P11 tests:

```python
def _write_p12_replay_json(path):
    payload = {
        "run_id": "p11-replay-run-2026-06-30",
        "replay_start_date": "2026-01-01",
        "replay_end_date": "2026-06-30",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_write_enabled": False,
        "results": [
            {
                "replay_result_id": "p11-replay:001",
                "run_id": "p11-replay-run-2026-06-30",
                "proposal_id": "p10-proposal:001",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "replay_status": "passed_offline_replay",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_write_enabled": False,
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_p12_candidates_csv(path, **overrides):
    row = {
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
        "candidate_reason": "Passed replay with acceptable drawdown.",
        "evidence_artifact_paths": json.dumps(["outputs/p11/replay.json"]),
        "metric_summary": json.dumps({"win_rate": 0.75}),
        "reviewer_id": "reviewer-a",
        "status": "shadow_ready",
        "review_notes": "Observe only.",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
    }
    row.update(overrides)
    pd.DataFrame([row]).to_csv(path, index=False)


def test_cli_accepts_p12_shadow_watchlist_command():
    args = cli.build_parser().parse_args(
        [
            "p12-shadow-watchlist",
            "--replay-json",
            "replay.json",
            "--candidates-csv",
            "candidates.csv",
            "--review-date",
            "2026-06-30",
            "--output-dir",
            "out",
        ]
    )

    assert args.command == "p12-shadow-watchlist"
    assert args.review_date == "2026-06-30"


def test_p12_shadow_watchlist_cli_outputs_review_only_artifacts(capsys, tmp_path):
    replay_json = tmp_path / "operator_experiment_replay_2026-01-01_2026-06-30.json"
    candidates_csv = tmp_path / "shadow_candidates.csv"
    _write_p12_replay_json(replay_json)
    _write_p12_candidates_csv(candidates_csv)

    cli.main_for_args(
        [
            "p12-shadow-watchlist",
            "--replay-json",
            str(replay_json),
            "--candidates-csv",
            str(candidates_csv),
            "--review-date",
            "2026-06-30",
            "--run-id",
            "p12-shadow-watchlist-2026-06-30",
            "--output-dir",
            str(tmp_path),
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "p12_shadow_watchlist|status|shadow_watchlist_review_ready"
    assert lines[1] == "p12_shadow_watchlist|candidates|1"
    assert lines[2].startswith("p12_shadow_watchlist|json|")
    assert lines[3].startswith("p12_shadow_watchlist|candidates_csv|")
    assert lines[4].startswith("p12_shadow_watchlist|markdown|")

    payload = json.loads((tmp_path / "operator_shadow_watchlist_2026-06-30.json").read_text())
    assert payload["production_watchlist_enabled"] is False
    assert payload["production_write_enabled"] is False
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -k 'p12_shadow_watchlist' -q
```

Expected: fail because parser command does not exist.

- [ ] **Step 3: Add CLI wiring**

In `src/stock_research/cli.py`, import:

```python
from stock_research.operator_decision.shadow_watchlist import (
    build_shadow_watchlist_review,
    write_shadow_watchlist_review,
)
```

Add parser:

```python
p12_shadow_watchlist = subparsers.add_parser("p12-shadow-watchlist")
p12_shadow_watchlist.add_argument("--replay-json", required=True)
p12_shadow_watchlist.add_argument("--candidates-csv", required=True)
p12_shadow_watchlist.add_argument("--review-date", required=True)
p12_shadow_watchlist.add_argument("--run-id")
p12_shadow_watchlist.add_argument("--output-dir", required=True)
```

Add dispatch:

```python
elif args.command == "p12-shadow-watchlist":
    import pandas as pd

    replay_payload = json.loads(Path(args.replay_json).read_text(encoding="utf-8"))
    replay_results = pd.DataFrame(replay_payload.get("results", []))
    candidate_events = pd.read_csv(args.candidates_csv)
    review = build_shadow_watchlist_review(
        replay_results=replay_results,
        candidate_events=candidate_events,
        run_id=args.run_id,
        review_date=args.review_date,
    )
    paths = write_shadow_watchlist_review(review, args.output_dir)
    print(f"p12_shadow_watchlist|status|{review['status']}")
    print(f"p12_shadow_watchlist|candidates|{review['candidate_count']}")
    print(f"p12_shadow_watchlist|json|{paths['json_path']}")
    print(f"p12_shadow_watchlist|candidates_csv|{paths['candidates_csv_path']}")
    print(f"p12_shadow_watchlist|markdown|{paths['markdown_path']}")
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -k 'p12_shadow_watchlist' -q
```

Expected: P12 CLI tests pass.

- [ ] **Step 5: Commit only P12 CLI hunks**

Run:

```bash
git diff -- src/stock_research/cli.py
git add tests/test_factor_cli.py
git add -p src/stock_research/cli.py
git diff --cached -- src/stock_research/cli.py
git commit -m "feat: add p12 shadow watchlist artifact cli"
```

Expected staged CLI diff contains only P12 import/parser/dispatch hunks.

---

### Task 3: Shadow Read Model

**Files:**

- Create: `src/stock_research/operator_decision/shadow_watchlist_read_model.py`
- Create: `tests/test_operator_shadow_watchlist_read_model.py`
- Modify: `src/stock_research/schema.py`
- Modify: `tests/test_schema.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing read-model tests**

Create `tests/test_operator_shadow_watchlist_read_model.py` using the P10/P11 fake cursor pattern:

```python
import json

import pytest

from stock_research.operator_decision.shadow_watchlist_read_model import (
    import_shadow_watchlist_review,
    load_shadow_watchlist_read_model_rows,
)


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
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

    def __exit__(self, exc_type, exc, tb):
        return False


def _payload() -> dict:
    return {
        "run_id": "p12-shadow-watchlist-2026-06-30",
        "review_date": "2026-06-30",
        "status": "shadow_watchlist_review_ready",
        "candidate_count": 1,
        "status_counts": {"shadow_ready": 1},
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
                "candidate_reason": "Passed replay with acceptable drawdown.",
                "evidence_artifact_paths": ["outputs/p11/replay.json"],
                "metric_summary": {"win_rate": 0.75},
                "reviewer_id": "reviewer-a",
                "status": "shadow_ready",
                "review_notes": "Observe only.",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ],
    }


def test_load_shadow_watchlist_rows_preserves_sources_and_safety(tmp_path):
    json_path = tmp_path / "operator_shadow_watchlist_2026-06-30.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")

    rows = load_shadow_watchlist_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p12-shadow-watchlist-2026-06-30"
    assert rows["run"]["json_path"] == str(json_path)
    assert rows["run"]["candidates_csv_path"].endswith("_candidates.csv")
    assert rows["run"]["production_watchlist_enabled"] is False
    candidate = rows["candidates"][0]
    assert candidate["shadow_candidate_id"] == "p12-shadow:001"
    assert candidate["source_p11_replay_run_id"] == "p11-replay-run-2026-06-30"
    assert candidate["source_p10_proposal_run_id"] == "p10-proposals-2026-06-30"
    assert candidate["source_p9_analytics_run_id"] == "p9-outcome-analytics-2026-05-01-2026-05-31"
    assert candidate["shadow_artifact_path"] == str(json_path)
    assert candidate["production_watchlist_enabled"] is False


def test_load_shadow_watchlist_rows_rejects_production_enabled_artifact(tmp_path):
    payload = _payload()
    payload["production_watchlist_enabled"] = True
    json_path = tmp_path / "operator_shadow_watchlist_2026-06-30.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        load_shadow_watchlist_read_model_rows(json_path)


def test_import_shadow_watchlist_review_upserts_run_and_candidates(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_watchlist_read_model

    json_path = tmp_path / "operator_shadow_watchlist_2026-06-30.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_watchlist_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_watchlist_review(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["candidate_count"] == 1
    assert result["run_ids"] == ["p12-shadow-watchlist-2026-06-30"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_shadow_watchlist_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    candidate_sql, candidate_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_shadow_watchlist_candidate" in candidate_sql
    assert "ON CONFLICT (shadow_candidate_id)" in candidate_sql
    assert candidate_params["shadow_candidate_id"] == "p12-shadow:001"
```

- [ ] **Step 2: Add schema test**

Add to `tests/test_schema.py`:

```python
def test_research_extension_includes_operator_shadow_watchlist_read_model_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_run" in sql
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_candidate" in sql
    assert "PRIMARY KEY (shadow_candidate_id)" in sql
    assert "source_p11_replay_run_id text NOT NULL" in sql
    assert "production_watchlist_enabled boolean NOT NULL DEFAULT false" in sql
    assert "idx_ops_operator_shadow_watchlist_run_date" in sql
    assert "idx_ops_operator_shadow_watchlist_status_date" in sql
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_watchlist_read_model.py tests/test_schema.py -k 'shadow_watchlist' -q
```

Expected: read-model module missing or schema assertions fail.

- [ ] **Step 4: Implement read model and schema**

Implement `shadow_watchlist_read_model.py` with the same structure as `experiment_replay_read_model.py`:

- `load_shadow_watchlist_read_model_rows(path)`
- `import_shadow_watchlist_review(path, service=SETTINGS.research_service)`
- `_shadow_paths(path)` matching `operator_shadow_watchlist_*.json`
- `_upsert_run(cur, row)`
- `_upsert_candidate(cur, row)`

Add schema tables to `CREATE_RESEARCH_EXTENSION_SQL`:

```sql
CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_run (
    run_id text NOT NULL,
    review_date date NOT NULL,
    status text NOT NULL,
    candidate_count integer NOT NULL DEFAULT 0,
    status_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    json_path text NOT NULL,
    candidates_csv_path text NOT NULL,
    markdown_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id)
);

CREATE TABLE IF NOT EXISTS ops.operator_shadow_watchlist_candidate (
    shadow_candidate_id text NOT NULL,
    run_id text NOT NULL REFERENCES ops.operator_shadow_watchlist_run(run_id),
    replay_result_id text NOT NULL,
    source_p11_replay_run_id text NOT NULL,
    source_p10_proposal_run_id text NOT NULL,
    source_p9_analytics_run_id text NOT NULL,
    candidate_date date NOT NULL,
    asset_id text NOT NULL,
    stock_code text NOT NULL,
    stock_name text NOT NULL,
    shadow_layer text NOT NULL,
    candidate_reason text NOT NULL,
    evidence_artifact_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
    metric_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    reviewer_id text NOT NULL,
    status text NOT NULL,
    review_notes text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    shadow_artifact_path text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (shadow_candidate_id)
);
```

Add indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_watchlist_run_date
    ON ops.operator_shadow_watchlist_run (review_date DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_watchlist_status_date
    ON ops.operator_shadow_watchlist_candidate (status, candidate_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_watchlist_asset_date
    ON ops.operator_shadow_watchlist_candidate (asset_id, candidate_date DESC);

CREATE INDEX IF NOT EXISTS idx_ops_operator_shadow_watchlist_source_replay
    ON ops.operator_shadow_watchlist_candidate (replay_result_id, source_p11_replay_run_id);
```

- [ ] **Step 5: Add import CLI test and wiring**

Add to `tests/test_factor_cli.py`:

```python
def test_p12_import_shadow_watchlist_cli_prints_summary(monkeypatch, capsys, tmp_path):
    import_path = tmp_path / "operator_shadow_watchlist_2026-06-30.json"
    import_path.write_text("{}", encoding="utf-8")

    def fake_import(path, *, service):
        assert path == import_path
        assert service == "stock_research_test"
        return {
            "imported_count": 1,
            "candidate_count": 2,
            "run_ids": ["p12-shadow-watchlist-2026-06-30"],
        }

    monkeypatch.setattr(cli, "import_shadow_watchlist_review", fake_import)

    cli.main_for_args(
        [
            "p12-import-shadow-watchlist",
            "--path",
            str(import_path),
            "--service",
            "stock_research_test",
        ]
    )

    assert capsys.readouterr().out.splitlines() == [
        "p12_shadow_watchlist_import|imported|1",
        "p12_shadow_watchlist_import|candidates|2",
        "p12_shadow_watchlist_import|run_id|p12-shadow-watchlist-2026-06-30",
    ]
```

In `cli.py`, import:

```python
from stock_research.operator_decision.shadow_watchlist_read_model import import_shadow_watchlist_review
```

Add parser:

```python
p12_import_shadow_watchlist = subparsers.add_parser("p12-import-shadow-watchlist")
p12_import_shadow_watchlist.add_argument("--path", required=True)
p12_import_shadow_watchlist.add_argument("--service", default="stock_research")
```

Add dispatch:

```python
elif args.command == "p12-import-shadow-watchlist":
    result = import_shadow_watchlist_review(Path(args.path), service=args.service)
    print(f"p12_shadow_watchlist_import|imported|{result['imported_count']}")
    print(f"p12_shadow_watchlist_import|candidates|{result['candidate_count']}")
    for run_id in result["run_ids"]:
        print(f"p12_shadow_watchlist_import|run_id|{run_id}")
```

- [ ] **Step 6: Run tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_watchlist_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'shadow_watchlist' -q
```

Expected: all P12 read-model/schema/CLI tests pass.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/stock_research/operator_decision/shadow_watchlist_read_model.py tests/test_operator_shadow_watchlist_read_model.py src/stock_research/schema.py tests/test_schema.py tests/test_factor_cli.py
git add -p src/stock_research/cli.py
git diff --cached -- src/stock_research/cli.py
git commit -m "feat: add p12 shadow watchlist read model"
```

---

### Task 4: Dashboard Read-Only Shadow Summary

**Files:**

- Create: `src/stock_research/dashboard/shadow_watchlist.py`
- Create: `tests/test_dashboard_shadow_watchlist.py`
- Create: `dashboard/src/components/ShadowWatchlistPanel.tsx`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_app.py`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/tests/client.test.ts`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Modify: `dashboard/tests/app-smoke.spec.ts`

- [ ] **Step 1: Write failing backend dashboard tests**

Create `tests/test_dashboard_shadow_watchlist.py`:

```python
from stock_research.dashboard import shadow_watchlist


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_shadow_watchlist_summary_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
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
                "evidence_artifact_paths": ["outputs/p11/replay.json"],
                "metric_summary": {"win_rate": 0.75},
                "reviewer_id": "reviewer-a",
                "status": "shadow_ready",
                "review_notes": "Observe only.",
                "shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(shadow_watchlist, "connect", fake_connect)
    monkeypatch.setattr(shadow_watchlist, "fetch_all", fake_fetch_all)

    result = shadow_watchlist.load_shadow_watchlist_summary(
        start_date="2026-06-01",
        end_date="2026-06-30",
        status="shadow_ready",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_shadow_watchlist_candidate" in captured["sql"]
    assert "status = %s" in captured["sql"]
    assert "ORDER BY candidate_date DESC" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-06-30", "shadow_ready", 10]
    assert captured["service"] == "stock_research_test"
    assert result[0]["shadow_candidate_id"] == "p12-shadow:001"
    assert result[0]["production_watchlist_enabled"] is False
```

- [ ] **Step 2: Write failing route test**

Add to `tests/test_dashboard_app.py`:

```python
def test_shadow_watchlist_route_returns_read_only_summary(monkeypatch):
    captured = {}

    def fake_load_shadow(start_date, end_date, status, limit):
        captured["args"] = [start_date, end_date, status, limit]
        return [
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
                "evidence_artifact_paths": ["outputs/p11/replay.json"],
                "metric_summary": {"win_rate": 0.75},
                "reviewer_id": "reviewer-a",
                "status": "shadow_ready",
                "review_notes": "Observe only.",
                "shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(dashboard_app, "load_shadow_watchlist_summary", fake_load_shadow)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-watchlist"
        "?start_date=2026-06-01"
        "&end_date=2026-06-30"
        "&status=shadow_ready"
        "&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-06-30", "shadow_ready", 10]
    assert response.json()["items"][0]["shadow_candidate_id"] == "p12-shadow:001"
    assert response.json()["items"][0]["production_watchlist_enabled"] is False
```

- [ ] **Step 3: Run backend tests to verify RED**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_shadow_watchlist.py tests/test_dashboard_app.py -k 'shadow_watchlist' -q
```

Expected: fail because dashboard module/route does not exist.

- [ ] **Step 4: Implement backend route**

Create `src/stock_research/dashboard/shadow_watchlist.py` with:

- `load_shadow_watchlist_summary(start_date, end_date, status=None, limit=20, service=SETTINGS.research_service)`
- SQL selecting from `ops.operator_shadow_watchlist_candidate`
- optional `AND status = %s`
- `ORDER BY candidate_date DESC, status, shadow_candidate_id`
- normalization of JSON/list fields
- safety booleans forced to `True/False/False/False`

Modify `src/stock_research/dashboard/app.py`:

```python
from stock_research.dashboard.shadow_watchlist import load_shadow_watchlist_summary
```

Add route:

```python
@app.get("/api/shadow-watchlist")
def shadow_watchlist(
    start_date: str,
    end_date: str,
    status: str | None = None,
    limit: int = 20,
):
    return {
        "start_date": start_date,
        "end_date": end_date,
        "items": load_shadow_watchlist_summary(start_date, end_date, status, limit),
    }
```

- [ ] **Step 5: Run backend tests to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_shadow_watchlist.py tests/test_dashboard_app.py -k 'shadow_watchlist' -q
```

Expected: dashboard P12 backend tests pass.

- [ ] **Step 6: Add frontend tests first**

Modify `dashboard/tests/client.test.ts` to import `fetchShadowWatchlist` and add:

```typescript
it('fetches shadow watchlist summary with optional status and limit', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ items: [{ shadow_candidate_id: 'p12-shadow:001', status: 'shadow_ready' }] })
  });
  vi.stubGlobal('fetch', fetchMock);

  const result = await fetchShadowWatchlist('2026-06-01', '2026-06-30', {
    status: 'shadow_ready',
    limit: 12
  });

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/shadow-watchlist?start_date=2026-06-01&end_date=2026-06-30' +
      '&limit=12&status=shadow_ready'
  );
  expect(result[0].shadow_candidate_id).toBe('p12-shadow:001');
});
```

Modify `dashboard/tests/app-shell.test.tsx`:

- add `ShadowWatchlistRow` import
- add `fetchShadowWatchlist: vi.fn()` to API mock
- add `makeShadowWatchlist()`
- set default mock to `makeShadowWatchlist()`
- assert `Shadow Watchlist` and `shadow_ready` render
- assert no `/promote/i`, `/trade/i`, or `/write/i` controls render
- add loading text `Loading shadow watchlist...`
- add empty text `No shadow watchlist candidates for selected range.`

- [ ] **Step 7: Run frontend tests to verify RED**

Run:

```bash
cd dashboard
pnpm test
```

Expected: fail because `fetchShadowWatchlist`, `ShadowWatchlistRow`, or panel does not exist.

- [ ] **Step 8: Implement frontend**

Add type to `dashboard/src/api/types.ts`:

```typescript
export type ShadowWatchlistRow = {
  shadow_candidate_id: string;
  run_id: string;
  replay_result_id: string;
  source_p11_replay_run_id: string;
  source_p10_proposal_run_id: string;
  source_p9_analytics_run_id: string;
  candidate_date: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  shadow_layer: string;
  candidate_reason: string;
  evidence_artifact_paths: string[];
  metric_summary: Record<string, number | string | boolean | null>;
  reviewer_id: string;
  status: string;
  review_notes: string;
  shadow_artifact_path: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_watchlist_enabled: boolean;
  production_write_enabled: boolean;
};
```

Add API client:

```typescript
export async function fetchShadowWatchlist(
  startDate: string,
  endDate: string,
  options: { status?: string; limit?: number } = {}
): Promise<ShadowWatchlistRow[]> {
  const limit = options.limit ?? 20;
  const status = options.status ? `&status=${encodeURIComponent(options.status)}` : '';
  const payload = await getJson<{ items: ShadowWatchlistRow[] }>(
    `/api/shadow-watchlist?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}${status}`
  );
  return payload.items;
}
```

Create `dashboard/src/components/ShadowWatchlistPanel.tsx`:

```tsx
import type { ShadowWatchlistRow } from '../api/types';

type ShadowWatchlistPanelProps = {
  rows: ShadowWatchlistRow[];
  isLoading?: boolean;
};

export function ShadowWatchlistPanel({ rows, isLoading = false }: ShadowWatchlistPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Shadow Watchlist</h2>
      {isLoading ? (
        <p className="muted">Loading shadow watchlist...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No shadow watchlist candidates for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => (
            <article className="decision-row analytics-row" key={row.shadow_candidate_id}>
              <div>
                <strong>{row.stock_name || row.asset_id}</strong>
                <span>{row.status}</span>
              </div>
              <div className="outcome-metrics">
                <span>{row.candidate_date}</span>
                <span>{row.shadow_layer}</span>
                <span>{row.asset_id}</span>
              </div>
              <p>{row.candidate_reason}</p>
              <p>{row.source_p11_replay_run_id}</p>
              <p>{row.source_p10_proposal_run_id}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
```

Modify `dashboard/src/App.tsx` to load `fetchShadowWatchlist(startDate, tradeDate, { limit: 20 })`, store rows/loading state, and render `<ShadowWatchlistPanel rows={shadowWatchlist} isLoading={shadowWatchlistLoading} />` in the inspector.

- [ ] **Step 9: Update Playwright smoke**

Modify `dashboard/tests/app-smoke.spec.ts`:

- route `/api/shadow-watchlist**` with one `shadow_ready` row
- assert heading `Shadow Watchlist`
- assert text `shadow_ready`
- keep mobile horizontal overflow assertion

- [ ] **Step 10: Run dashboard verification**

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

- [ ] **Step 11: Commit**

Run:

```bash
git add src/stock_research/dashboard/shadow_watchlist.py tests/test_dashboard_shadow_watchlist.py src/stock_research/dashboard/app.py tests/test_dashboard_app.py dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/components/ShadowWatchlistPanel.tsx dashboard/src/App.tsx dashboard/tests/client.test.ts dashboard/tests/app-shell.test.tsx dashboard/tests/app-smoke.spec.ts
git commit -m "feat: add p12 shadow watchlist dashboard summary"
```

---

### Task 5: P12 Smoke, Runbook, And Completion Review

**Files:**

- Create: `src/stock_research/operator_decision/p12_smoke.py`
- Create: `tests/test_p12_shadow_watchlist_smoke.py`
- Create: `docs/quant_system/44_p12_shadow_watchlist_runbook.md`
- Create: `docs/quant_system/45_p12_shadow_watchlist_completion.md`

- [ ] **Step 1: Write failing smoke test**

Create `tests/test_p12_shadow_watchlist_smoke.py`:

```python
from pathlib import Path

from stock_research.operator_decision.p12_smoke import build_p12_shadow_watchlist_smoke


def test_p12_smoke_builds_shadow_artifacts_and_read_model_rows(tmp_path):
    result = build_p12_shadow_watchlist_smoke(tmp_path)

    assert Path(result["p11_replay_json_path"]).exists()
    assert Path(result["p12_shadow_json_path"]).exists()
    assert Path(result["p12_shadow_candidates_csv_path"]).exists()
    assert Path(result["p12_shadow_markdown_path"]).exists()
    assert result["candidate_count"] == 1
    assert result["read_model_candidate_count"] == 1
    assert result["status_counts"] == {"shadow_ready": 1}
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
.venv/bin/pytest tests/test_p12_shadow_watchlist_smoke.py -q
```

Expected: fail because `stock_research.operator_decision.p12_smoke` does not exist.

- [ ] **Step 3: Implement smoke**

Create `src/stock_research/operator_decision/p12_smoke.py`:

- call `build_p11_experiment_replay_smoke(output_dir)`
- load P11 replay read-model rows
- build one shadow candidate CSV/DataFrame with asset `000001.SZ`
- call `build_shadow_watchlist_review`
- call `write_shadow_watchlist_review`
- call `load_shadow_watchlist_read_model_rows`
- return artifact paths, counts, source run IDs, and safety fields

Use run IDs:

- `p12-smoke-shadow-watchlist-2026-06-30`
- source P11 run from P11 smoke: `p11-smoke-replay-2026-06-30`
- source P10 run from P10 smoke: `p10-smoke-proposals-2026-06-30`

- [ ] **Step 4: Run smoke test to verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_p12_shadow_watchlist_smoke.py tests/test_p11_experiment_replay_smoke.py -q
```

Expected: P12/P11 smoke tests pass.

- [ ] **Step 5: Run actual smoke command and capture output**

Run:

```bash
rm -rf /tmp/stock_research_p12_smoke
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p12_smoke import build_p12_shadow_watchlist_smoke

result = build_p12_shadow_watchlist_smoke(Path('/tmp/stock_research_p12_smoke'))
print(f"p12_smoke|p11_replay|{result['p11_replay_json_path']}")
print(f"p12_smoke|p12_shadow|{result['p12_shadow_json_path']}")
print(f"p12_smoke|candidates_csv|{result['p12_shadow_candidates_csv_path']}")
print(f"p12_smoke|markdown|{result['p12_shadow_markdown_path']}")
print(f"p12_smoke|candidate_count|{result['candidate_count']}")
print(f"p12_smoke|read_model_candidates|{result['read_model_candidate_count']}")
print(f"p12_smoke|source_p11_runs|{','.join(result['source_p11_replay_run_ids'])}")
print(f"p12_smoke|source_p10_runs|{','.join(result['source_p10_proposal_run_ids'])}")
print(f"p12_smoke|source_p9_runs|{','.join(result['source_p9_analytics_run_ids'])}")
print(f"p12_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p12_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p12_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p12_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Expected output includes:

```text
p12_smoke|candidate_count|1
p12_smoke|read_model_candidates|1
p12_smoke|manual_review_required|True
p12_smoke|auto_trade_enabled|False
p12_smoke|production_watchlist_enabled|False
p12_smoke|production_write_enabled|False
```

- [ ] **Step 6: Write runbook**

Create `docs/quant_system/44_p12_shadow_watchlist_runbook.md` with:

- scope statement
- candidate CSV columns
- allowed statuses
- `stock-research p12-shadow-watchlist` command
- `stock-research p12-import-shadow-watchlist` command
- dashboard review instructions
- synthetic smoke command and observed output
- verification commands

- [ ] **Step 7: Write completion review**

Create `docs/quant_system/45_p12_shadow_watchlist_completion.md` with:

- P12 status
- P12-0 through P12-5 delivered capabilities
- smoke output
- acceptance criteria table
- verification evidence
- safety review explicitly stating no production watchlist/scoring/scheduler/trading path was added
- known non-P12 dirty files note

- [ ] **Step 8: Run full P12 verification**

Run:

```bash
.venv/bin/pytest tests/test_operator_shadow_watchlist.py tests/test_operator_shadow_watchlist_read_model.py tests/test_p12_shadow_watchlist_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_watchlist.py tests/test_dashboard_app.py -k 'shadow_watchlist or p12_shadow_watchlist or p12_import_shadow_watchlist or dashboard' -q
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

Expected:

- Python P12-focused tests pass
- Vitest passes
- Vite build passes
- Playwright passes

- [ ] **Step 9: Update completion review with exact verification results**

Replace the provisional verification result lines in `docs/quant_system/45_p12_shadow_watchlist_completion.md` with the exact counts from Step 8.

- [ ] **Step 10: Commit**

Run:

```bash
git add src/stock_research/operator_decision/p12_smoke.py tests/test_p12_shadow_watchlist_smoke.py docs/quant_system/44_p12_shadow_watchlist_runbook.md docs/quant_system/45_p12_shadow_watchlist_completion.md
git commit -m "docs: complete p12 shadow watchlist governance"
```

---

## Final Verification Before P12 Completion Claim

Run from repo root:

```bash
.venv/bin/pytest tests/test_operator_shadow_watchlist.py tests/test_operator_shadow_watchlist_read_model.py tests/test_p12_shadow_watchlist_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_watchlist.py tests/test_dashboard_app.py -k 'shadow_watchlist or p12_shadow_watchlist or p12_import_shadow_watchlist or dashboard' -q
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

- P12 commits appear on top of `factor-scoring-daily-pipeline`.
- Existing unrelated watchlist/trend/factor dirty files remain uncommitted.
- No P12 commit includes unrelated non-P12 dirty files.

## Self-Review Checklist

- Spec requirement "review-only bridge" maps to Tasks 0, 1, 3, 4, and 5.
- Spec requirement "artifact contract" maps to Task 1.
- Spec requirement "artifact CLI" maps to Task 2.
- Spec requirement "read model" maps to Task 3.
- Spec requirement "dashboard read-only summary" maps to Task 4.
- Spec requirement "smoke/runbook/completion" maps to Task 5.
- No task writes production watchlist, scoring, scheduler, or trading state.
- `cli.py` staging instructions explicitly protect unrelated dirty hunks.
