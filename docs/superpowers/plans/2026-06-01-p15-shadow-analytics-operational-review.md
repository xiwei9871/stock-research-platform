# P15 Shadow Analytics Operational Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a review-only P15 operational review layer that consumes P14 shadow outcome analytics and records conservative group-level review statuses without writing production watchlist, scoring, scheduler, or trading state.

**Architecture:** P15 follows the P12-P14 artifact/read-model/dashboard pattern. It writes local JSON/CSV/Markdown review artifacts, imports compact group review rows into independent `ops.operator_shadow_analytics_review_*` tables, and exposes a read-only dashboard summary.

**Tech Stack:** Python, pandas, argparse CLI, PostgreSQL SQL strings in `schema.py`, FastAPI dashboard API, React/Vite dashboard, Vitest, Playwright, pytest.

---

## File Structure

Create:

- `src/stock_research/operator_decision/shadow_analytics_review.py`: P15 review contract, triage rules, artifact writer, Markdown renderer.
- `tests/test_operator_shadow_analytics_review.py`: contract, safety, triage, and artifact tests.
- `src/stock_research/operator_decision/shadow_analytics_review_read_model.py`: P15 artifact loader and idempotent read-model importer.
- `tests/test_operator_shadow_analytics_review_read_model.py`: importer/read-model tests.
- `src/stock_research/operator_decision/p15_smoke.py`: synthetic P14-to-P15 smoke.
- `tests/test_p15_shadow_analytics_review_smoke.py`: smoke test.
- `src/stock_research/dashboard/shadow_analytics_review.py`: dashboard read-only query.
- `tests/test_dashboard_shadow_analytics_review.py`: dashboard backend query tests.
- `dashboard/src/components/ShadowAnalyticsReviewPanel.tsx`: read-only P15 panel.
- `docs/quant_system/53_p15_shadow_analytics_operational_review_runbook.md`: P15 runbook.
- `docs/quant_system/54_p15_shadow_analytics_operational_review_completion.md`: P15 completion review.

Modify:

- `src/stock_research/cli.py`: add `p15-shadow-analytics-review` and `p15-import-shadow-analytics-review`.
- `src/stock_research/schema.py`: add `ops.operator_shadow_analytics_review_run`, `ops.operator_shadow_analytics_review_group`, and indexes.
- `tests/test_schema.py`: assert P15 tables/indexes.
- `tests/test_factor_cli.py`: CLI parser/dispatch tests.
- `src/stock_research/dashboard/app.py`: add `GET /api/shadow-analytics-review`.
- `tests/test_dashboard_app.py`: route test.
- `dashboard/src/api/types.ts`: add `ShadowAnalyticsReviewRow`.
- `dashboard/src/api/client.ts`: add `fetchShadowAnalyticsReview`.
- `dashboard/src/App.tsx`: load and render P15 panel.
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

### Task 0: P15 Scope Freeze Commit

**Files:**

- Existing: `docs/quant_system/52_p15_shadow_analytics_operational_review_scope_freeze.md`

- [ ] **Step 1: Verify the scope freeze document exists**

Run:

```bash
test -s docs/quant_system/52_p15_shadow_analytics_operational_review_scope_freeze.md
```

Expected: exit code `0`.

- [ ] **Step 2: Verify the design document exists**

Run:

```bash
test -s docs/superpowers/specs/2026-06-01-p15-shadow-analytics-operational-review-design.md
```

Expected: exit code `0`.

- [ ] **Step 3: Commit if not already committed**

Run:

```bash
git status --short docs/quant_system/52_p15_shadow_analytics_operational_review_scope_freeze.md docs/superpowers/specs/2026-06-01-p15-shadow-analytics-operational-review-design.md
```

If either file is staged or unstaged, run:

```bash
git add docs/quant_system/52_p15_shadow_analytics_operational_review_scope_freeze.md docs/superpowers/specs/2026-06-01-p15-shadow-analytics-operational-review-design.md
git commit -m "docs: add p15 shadow analytics operational review design"
```

Expected if already committed: clean output for both files.

---

### Task 1: Shadow Analytics Review Contract

**Files:**

- Create: `src/stock_research/operator_decision/shadow_analytics_review.py`
- Create: `tests/test_operator_shadow_analytics_review.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_operator_shadow_analytics_review.py`:

```python
import json
from pathlib import Path

import pytest

from stock_research.operator_decision.shadow_analytics_review import (
    DEFAULT_SHADOW_ANALYTICS_REVIEW_THRESHOLDS,
    REVIEW_STATUSES,
    build_shadow_analytics_review,
    build_shadow_analytics_review_from_rows,
    write_shadow_analytics_review,
)


def _group(**overrides):
    row = {
        "analytics_group_id": "operator_shadow_outcome_analytics:p14:trend-ready",
        "run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
        "review_start_date": "2026-06-30",
        "review_end_date": "2026-08-29",
        "group_key": "trend_shadow|shadow_ready",
        "shadow_layer": "trend_shadow",
        "shadow_status": "shadow_ready",
        "sample_count": 30,
        "complete_count": 28,
        "insufficient_data_count": 2,
        "source_p12_shadow_run_count": 1,
        "source_p11_replay_run_count": 1,
        "source_p10_proposal_run_count": 1,
        "source_p9_analytics_run_count": 1,
        "horizon_metrics": {
            "20": {
                "forward_return_mean": 0.08,
                "forward_win_rate": 0.62,
                "max_low_drawdown_worst": -0.08,
            }
        },
        "analytics_artifact_path": "outputs/p14/operator_shadow_outcome_analytics.json",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
    }
    row.update(overrides)
    return row


def test_build_shadow_analytics_review_assigns_conservative_statuses():
    rows = [
        _group(),
        _group(
            analytics_group_id="operator_shadow_outcome_analytics:p14:low-sample",
            group_key="risk_shadow|shadow_observe",
            shadow_layer="risk_shadow",
            shadow_status="shadow_observe",
            sample_count=3,
            complete_count=2,
            insufficient_data_count=1,
        ),
        _group(
            analytics_group_id="operator_shadow_outcome_analytics:p14:data-quality",
            group_key="event_shadow|shadow_ready",
            shadow_layer="event_shadow",
            sample_count=20,
            complete_count=5,
            insufficient_data_count=15,
        ),
        _group(
            analytics_group_id="operator_shadow_outcome_analytics:p14:weak",
            group_key="weak_shadow|shadow_ready",
            shadow_layer="weak_shadow",
            sample_count=20,
            complete_count=20,
            insufficient_data_count=0,
            horizon_metrics={"20": {"forward_return_mean": -0.04, "max_low_drawdown_worst": -0.22}},
        ),
        _group(
            analytics_group_id="operator_shadow_outcome_analytics:p14:observe",
            group_key="neutral_shadow|shadow_ready",
            shadow_layer="neutral_shadow",
            sample_count=20,
            complete_count=18,
            insufficient_data_count=2,
            horizon_metrics={"20": {"forward_return_mean": 0.01, "max_low_drawdown_worst": -0.10}},
        ),
    ]

    review = build_shadow_analytics_review_from_rows(
        rows,
        run_id="p15-shadow-analytics-review-2026-06-30-2026-08-29",
        review_start_date="2026-06-30",
        review_end_date="2026-08-29",
        reviewer_id="operator",
    )

    groups = {row["group_key"]: row for row in review["groups"]}
    assert groups["trend_shadow|shadow_ready"]["review_status"] == "research_follow_up_candidate"
    assert groups["risk_shadow|shadow_observe"]["review_status"] == "needs_more_data"
    assert groups["event_shadow|shadow_ready"]["review_status"] == "investigate_data_quality"
    assert groups["weak_shadow|shadow_ready"]["review_status"] == "deprioritize_review"
    assert groups["neutral_shadow|shadow_ready"]["review_status"] == "continue_observing"
    assert groups["trend_shadow|shadow_ready"]["review_bucket"] == "follow_up"
    assert groups["trend_shadow|shadow_ready"]["manual_review_required"] is True
    assert groups["trend_shadow|shadow_ready"]["auto_trade_enabled"] is False
    assert groups["trend_shadow|shadow_ready"]["production_watchlist_enabled"] is False
    assert groups["trend_shadow|shadow_ready"]["production_write_enabled"] is False


def test_build_shadow_analytics_review_preserves_run_metadata_and_writes_artifacts(tmp_path):
    review = build_shadow_analytics_review(
        p14_analytics={"groups": [_group()]},
        run_id="p15-shadow-analytics-review-2026-06-30-2026-08-29",
        review_start_date="2026-06-30",
        review_end_date="2026-08-29",
        reviewer_id="operator",
    )

    assert review["status"] == "shadow_analytics_review_ready"
    assert review["source_p14_analytics_run_ids"] == ["p14-shadow-outcome-analytics-2026-06-30-2026-08-29"]
    assert review["reviewer_id"] == "operator"
    assert review["group_count"] == 1
    paths = write_shadow_analytics_review(review, tmp_path)
    assert Path(paths["json_path"]).exists()
    assert Path(paths["groups_csv_path"]).exists()
    assert Path(paths["markdown_path"]).exists()
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["groups"][0]["review_status"] == "research_follow_up_candidate"
    assert "research_follow_up_candidate" in Path(paths["markdown_path"]).read_text(encoding="utf-8")


def test_build_shadow_analytics_review_rejects_production_enabled_group():
    row = _group(production_watchlist_enabled=True)

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_analytics_review_from_rows(
            [row],
            run_id="p15-shadow-analytics-review-2026-06-30-2026-08-29",
            review_start_date="2026-06-30",
            review_end_date="2026-08-29",
            reviewer_id="operator",
        )


def test_build_shadow_analytics_review_rejects_unsafe_execution_fields():
    row = _group(order_id="unsafe")

    with pytest.raises(ValueError, match="unsafe_execution_field"):
        build_shadow_analytics_review_from_rows(
            [row],
            run_id="p15-shadow-analytics-review-2026-06-30-2026-08-29",
            review_start_date="2026-06-30",
            review_end_date="2026-08-29",
            reviewer_id="operator",
        )


def test_review_status_constants_are_scope_frozen():
    assert REVIEW_STATUSES == [
        "continue_observing",
        "needs_more_data",
        "investigate_data_quality",
        "deprioritize_review",
        "research_follow_up_candidate",
    ]
    assert DEFAULT_SHADOW_ANALYTICS_REVIEW_THRESHOLDS["min_sample_count"] == 10
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_analytics_review.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'stock_research.operator_decision.shadow_analytics_review'`.

- [ ] **Step 3: Implement the contract**

Create `src/stock_research/operator_decision/shadow_analytics_review.py` with these public constants and functions:

```python
REVIEW_STATUSES = [
    "continue_observing",
    "needs_more_data",
    "investigate_data_quality",
    "deprioritize_review",
    "research_follow_up_candidate",
]

DEFAULT_SHADOW_ANALYTICS_REVIEW_THRESHOLDS = {
    "min_sample_count": 10,
    "max_insufficient_data_rate": 0.40,
    "follow_up_forward_return_mean": 0.03,
    "deprioritize_forward_return_mean": -0.02,
    "max_controlled_drawdown_worst": -0.15,
    "deprioritize_drawdown_worst": -0.20,
    "primary_horizon": "20",
}

def build_shadow_analytics_review_from_rows(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    review_start_date: str,
    review_end_date: str,
    reviewer_id: str,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a JSON-serializable P15 operational review payload."""

def build_shadow_analytics_review(
    *,
    p14_analytics: dict[str, Any],
    run_id: str,
    review_start_date: str,
    review_end_date: str,
    reviewer_id: str,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a P15 review payload from one P14 analytics artifact payload."""

def write_shadow_analytics_review(review: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write JSON, groups CSV, and Markdown P15 review artifacts."""
```

Implementation requirements:

- Artifact stem: `operator_shadow_analytics_review_{review_start_date}_{review_end_date}`.
- `status`: `shadow_analytics_review_ready` when groups exist, otherwise `no_shadow_analytics_groups_recorded`.
- Force safety fields to `True/False/False/False`.
- Validate top-level and group-level safety fields.
- Reject unsafe execution-like fields using a set that includes `order_id`, `trade_id`, `broker`, `account_id`, `position_id`, `quantity`, `shares`, `price`, `notional`, `cash`, `execution_id`, `fill_id`.
- Preserve `source_p14_analytics_group_id` from `analytics_group_id`.
- Preserve `source_p14_analytics_run_id` from P14 `run_id`.
- Derive `review_group_id` as `operator_shadow_analytics_review:{run_id}:{sha256(source_p14_analytics_group_id|review_status)[:16]}`.
- Use the primary horizon from thresholds, default `"20"`.
- Triage order must be:
  1. low sample -> `needs_more_data`
  2. high insufficient-data rate -> `investigate_data_quality`
  3. negative forward mean or severe drawdown -> `deprioritize_review`
  4. adequate sample, positive forward mean, controlled drawdown -> `research_follow_up_candidate`
  5. otherwise -> `continue_observing`
- `review_bucket` mapping:
  - `continue_observing` -> `observe`
  - `needs_more_data` -> `data_needed`
  - `investigate_data_quality` -> `data_quality`
  - `deprioritize_review` -> `deprioritize`
  - `research_follow_up_candidate` -> `follow_up`
- `evidence_summary`, `risk_notes`, and `next_research_question` must be non-empty strings.

- [ ] **Step 4: Run contract tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_analytics_review.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/operator_decision/shadow_analytics_review.py tests/test_operator_shadow_analytics_review.py
git commit -m "feat: add p15 shadow analytics review contract"
```

---

### Task 2: Artifact CLI

**Files:**

- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_factor_cli.py`:

```python
def test_p15_shadow_analytics_review_parser_accepts_required_args():
    args = cli.build_parser().parse_args(
        [
            "p15-shadow-analytics-review",
            "--p14-analytics-json",
            "outputs/p14/operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json",
            "--run-id",
            "p15-shadow-analytics-review-2026-06-30-2026-08-29",
            "--review-start-date",
            "2026-06-30",
            "--review-end-date",
            "2026-08-29",
            "--reviewer-id",
            "operator",
            "--output-dir",
            "outputs/p15",
        ]
    )

    assert args.command == "p15-shadow-analytics-review"
    assert args.p14_analytics_json.endswith(".json")
    assert args.reviewer_id == "operator"


def test_p15_shadow_analytics_review_dispatches_to_builder(monkeypatch, tmp_path, capsys):
    json_path = tmp_path / "operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json"
    json_path.write_text('{"groups": []}', encoding="utf-8")
    output_dir = tmp_path / "p15"
    captured = {}

    def fake_build_shadow_analytics_review(**kwargs):
        captured["build"] = kwargs
        return {
            "status": "shadow_analytics_review_ready",
            "group_count": 1,
            "groups": [],
        }

    def fake_write_shadow_analytics_review(review, output_dir_arg):
        captured["write"] = {"review": review, "output_dir": output_dir_arg}
        return {
            "json_path": str(output_dir / "review.json"),
            "groups_csv_path": str(output_dir / "groups.csv"),
            "markdown_path": str(output_dir / "review.md"),
        }

    monkeypatch.setattr(cli, "build_shadow_analytics_review", fake_build_shadow_analytics_review)
    monkeypatch.setattr(cli, "write_shadow_analytics_review", fake_write_shadow_analytics_review)

    cli.main_for_args(
        [
            "p15-shadow-analytics-review",
            "--p14-analytics-json",
            str(json_path),
            "--run-id",
            "p15-shadow-analytics-review-2026-06-30-2026-08-29",
            "--review-start-date",
            "2026-06-30",
            "--review-end-date",
            "2026-08-29",
            "--reviewer-id",
            "operator",
            "--output-dir",
            str(output_dir),
        ]
    )

    output = capsys.readouterr().out
    assert "p15_shadow_analytics_review|status|shadow_analytics_review_ready" in output
    assert "p15_shadow_analytics_review|groups|1" in output
    assert "p15_shadow_analytics_review|json|" in output
    assert "p15_shadow_analytics_review|groups_csv|" in output
    assert "p15_shadow_analytics_review|markdown|" in output
    assert captured["build"]["run_id"] == "p15-shadow-analytics-review-2026-06-30-2026-08-29"
    assert captured["build"]["reviewer_id"] == "operator"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_factor_cli.py -k 'p15_shadow_analytics_review' -q
```

Expected: FAIL because parser/dispatch does not exist.

- [ ] **Step 3: Wire CLI**

Modify `src/stock_research/cli.py`:

```python
from stock_research.operator_decision.shadow_analytics_review import (
    build_shadow_analytics_review,
    write_shadow_analytics_review,
)
```

Add parser:

```python
p15_shadow_analytics_review = subparsers.add_parser("p15-shadow-analytics-review")
p15_shadow_analytics_review.add_argument("--p14-analytics-json", required=True)
p15_shadow_analytics_review.add_argument("--run-id", required=True)
p15_shadow_analytics_review.add_argument("--review-start-date", required=True)
p15_shadow_analytics_review.add_argument("--review-end-date", required=True)
p15_shadow_analytics_review.add_argument("--reviewer-id", required=True)
p15_shadow_analytics_review.add_argument("--output-dir", required=True)
```

Add dispatch:

```python
elif args.command == "p15-shadow-analytics-review":
    p14_payload = json.loads(Path(args.p14_analytics_json).read_text(encoding="utf-8"))
    review = build_shadow_analytics_review(
        p14_analytics=p14_payload,
        run_id=args.run_id,
        review_start_date=args.review_start_date,
        review_end_date=args.review_end_date,
        reviewer_id=args.reviewer_id,
    )
    paths = write_shadow_analytics_review(review, args.output_dir)
    print(f"p15_shadow_analytics_review|status|{review['status']}")
    print(f"p15_shadow_analytics_review|groups|{review['group_count']}")
    print(f"p15_shadow_analytics_review|json|{paths['json_path']}")
    print(f"p15_shadow_analytics_review|groups_csv|{paths['groups_csv_path']}")
    print(f"p15_shadow_analytics_review|markdown|{paths['markdown_path']}")
    return
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_analytics_review.py tests/test_factor_cli.py -k 'shadow_analytics_review or p15_shadow_analytics_review' -q
```

Expected: selected tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add p15 shadow analytics review cli"
```

---

### Task 3: Read Model And Import CLI

**Files:**

- Create: `src/stock_research/operator_decision/shadow_analytics_review_read_model.py`
- Create: `tests/test_operator_shadow_analytics_review_read_model.py`
- Modify: `src/stock_research/schema.py`
- Modify: `tests/test_schema.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing read-model tests**

Create `tests/test_operator_shadow_analytics_review_read_model.py`:

```python
import json

import pytest

from stock_research.operator_decision.shadow_analytics_review_read_model import (
    import_shadow_analytics_review,
    load_shadow_analytics_review_read_model_rows,
)


def _payload() -> dict:
    return {
        "run_id": "p15-shadow-analytics-review-2026-06-30-2026-08-29",
        "review_start_date": "2026-06-30",
        "review_end_date": "2026-08-29",
        "status": "shadow_analytics_review_ready",
        "reviewer_id": "operator",
        "source_p14_analytics_run_ids": ["p14-shadow-outcome-analytics-2026-06-30-2026-08-29"],
        "thresholds": {"min_sample_count": 10, "primary_horizon": "20"},
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "group_count": 1,
        "groups": [
            {
                "review_group_id": "operator_shadow_analytics_review:p15:abc",
                "source_p14_analytics_group_id": "operator_shadow_outcome_analytics:p14:trend-ready",
                "source_p14_analytics_run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 30,
                "complete_count": 28,
                "insufficient_data_count": 2,
                "horizon_metrics": {"20": {"forward_return_mean": 0.08}},
                "review_status": "research_follow_up_candidate",
                "review_bucket": "follow_up",
                "evidence_summary": "20d forward mean is positive.",
                "risk_notes": "Drawdown is controlled.",
                "next_research_question": "Review this group in future research.",
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


def test_load_shadow_analytics_review_rows_preserves_safety_and_metrics(tmp_path):
    json_path = tmp_path / "operator_shadow_analytics_review_2026-06-30_2026-08-29.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")

    rows = load_shadow_analytics_review_read_model_rows(json_path)

    assert rows["run"]["run_id"] == "p15-shadow-analytics-review-2026-06-30-2026-08-29"
    assert rows["run"]["group_count"] == 1
    assert rows["run"]["production_write_enabled"] is False
    group = rows["groups"][0]
    assert group["review_group_id"].startswith("operator_shadow_analytics_review:")
    assert group["source_p14_analytics_group_id"] == "operator_shadow_outcome_analytics:p14:trend-ready"
    assert group["horizon_metrics"]["20"]["forward_return_mean"] == 0.08
    assert group["review_status"] == "research_follow_up_candidate"


def test_load_shadow_analytics_review_rows_rejects_production_enabled_artifact(tmp_path):
    payload = _payload()
    payload["production_write_enabled"] = True
    json_path = tmp_path / "operator_shadow_analytics_review_2026-06-30_2026-08-29.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="production_write_not_allowed"):
        load_shadow_analytics_review_read_model_rows(json_path)


def test_import_shadow_analytics_review_upserts_run_and_groups(monkeypatch, tmp_path):
    from stock_research.operator_decision import shadow_analytics_review_read_model

    json_path = tmp_path / "operator_shadow_analytics_review_2026-06-30_2026-08-29.json"
    json_path.write_text(json.dumps(_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(shadow_analytics_review_read_model, "connect", lambda service: _Context(conn))

    result = import_shadow_analytics_review(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["group_count"] == 1
    assert result["run_ids"] == ["p15-shadow-analytics-review-2026-06-30-2026-08-29"]
    run_sql, run_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_shadow_analytics_review_run" in run_sql
    assert "ON CONFLICT (run_id)" in run_sql
    assert run_params["json_path"] == str(json_path)
    group_sql, group_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_shadow_analytics_review_group" in group_sql
    assert "ON CONFLICT (review_group_id)" in group_sql
    assert group_params["review_status"] == "research_follow_up_candidate"
```

- [ ] **Step 2: Write failing schema and import CLI tests**

Append to `tests/test_schema.py`:

```python
def test_p15_shadow_analytics_review_tables_exist():
    ddl = schema.SCHEMA_SQL

    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_analytics_review_run" in ddl
    assert "CREATE TABLE IF NOT EXISTS ops.operator_shadow_analytics_review_group" in ddl
    assert "idx_operator_shadow_analytics_review_group_date" in ddl
    assert "idx_operator_shadow_analytics_review_group_status" in ddl
```

Append to `tests/test_factor_cli.py`:

```python
def test_p15_import_shadow_analytics_review_parser_accepts_path():
    args = cli.build_parser().parse_args(
        ["p15-import-shadow-analytics-review", "--path", "outputs/p15"]
    )

    assert args.command == "p15-import-shadow-analytics-review"
    assert args.path == "outputs/p15"


def test_p15_import_shadow_analytics_review_dispatches(monkeypatch, capsys):
    captured = {}

    def fake_import_shadow_analytics_review(path, service):
        captured["path"] = path
        captured["service"] = service
        return {"imported_count": 2, "group_count": 3, "run_ids": ["p15-a", "p15-b"]}

    monkeypatch.setattr(cli, "import_shadow_analytics_review", fake_import_shadow_analytics_review)

    cli.main_for_args(
        [
            "p15-import-shadow-analytics-review",
            "--path",
            "outputs/p15",
            "--service",
            "stock_research_test",
        ]
    )

    output = capsys.readouterr().out
    assert "p15_import_shadow_analytics_review|imported|2" in output
    assert "p15_import_shadow_analytics_review|groups|3" in output
    assert "p15_import_shadow_analytics_review|runs|p15-a,p15-b" in output
    assert captured == {"path": "outputs/p15", "service": "stock_research_test"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_analytics_review_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'shadow_analytics_review or p15_import_shadow_analytics_review' -q
```

Expected: FAIL because read-model module, schema tables, and import CLI do not exist.

- [ ] **Step 4: Implement read model, schema, and import CLI**

Implement `src/stock_research/operator_decision/shadow_analytics_review_read_model.py` with:

```python
def load_shadow_analytics_review_read_model_rows(path: str | Path) -> dict[str, Any]:
    """Load one P15 JSON artifact into run and group read-model rows."""

def import_shadow_analytics_review(path: str | Path, *, service: str = SETTINGS.research_service) -> dict[str, Any]:
    """Import one artifact or a directory of P15 artifacts into ops tables."""
```

Requirements:

- Directory imports should load `operator_shadow_analytics_review_*.json`.
- Validate top-level and group-level safety fields.
- `review_group_id` must be run-scoped and derived from `run_id|source_p14_analytics_group_id|review_status`; ignore artifact-provided IDs that are not run-scoped.
- Run upsert conflict target: `(run_id)`.
- Group upsert conflict target: `(review_group_id)`.
- Store `source_p14_analytics_run_ids`, `thresholds`, `horizon_metrics`, and `metadata` as JSONB.

Add schema DDL:

```sql
CREATE TABLE IF NOT EXISTS ops.operator_shadow_analytics_review_run (
    run_id text PRIMARY KEY,
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    status text NOT NULL,
    reviewer_id text NOT NULL,
    source_p14_analytics_run_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    thresholds jsonb NOT NULL DEFAULT '{}'::jsonb,
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

CREATE TABLE IF NOT EXISTS ops.operator_shadow_analytics_review_group (
    review_group_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ops.operator_shadow_analytics_review_run(run_id) ON DELETE CASCADE,
    review_start_date date NOT NULL,
    review_end_date date NOT NULL,
    source_p14_analytics_group_id text NOT NULL,
    source_p14_analytics_run_id text NOT NULL,
    group_key text NOT NULL,
    shadow_layer text NOT NULL,
    shadow_status text NOT NULL,
    sample_count integer NOT NULL DEFAULT 0,
    complete_count integer NOT NULL DEFAULT 0,
    insufficient_data_count integer NOT NULL DEFAULT 0,
    horizon_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    review_status text NOT NULL,
    review_bucket text NOT NULL,
    evidence_summary text NOT NULL,
    risk_notes text NOT NULL,
    next_research_question text NOT NULL,
    review_artifact_path text NOT NULL,
    manual_review_required boolean NOT NULL DEFAULT true,
    auto_trade_enabled boolean NOT NULL DEFAULT false,
    production_watchlist_enabled boolean NOT NULL DEFAULT false,
    production_write_enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_analytics_review_group_date
    ON ops.operator_shadow_analytics_review_group (review_end_date DESC, review_status, sample_count DESC);

CREATE INDEX IF NOT EXISTS idx_operator_shadow_analytics_review_group_status
    ON ops.operator_shadow_analytics_review_group (review_status, review_end_date DESC);
```

Wire import CLI:

```python
from stock_research.operator_decision.shadow_analytics_review_read_model import import_shadow_analytics_review

p15_import_shadow_analytics_review = subparsers.add_parser("p15-import-shadow-analytics-review")
p15_import_shadow_analytics_review.add_argument("--path", required=True)
p15_import_shadow_analytics_review.add_argument("--service", default=SETTINGS.research_service)

elif args.command == "p15-import-shadow-analytics-review":
    result = import_shadow_analytics_review(args.path, service=args.service)
    print(f"p15_import_shadow_analytics_review|imported|{result['imported_count']}")
    print(f"p15_import_shadow_analytics_review|groups|{result['group_count']}")
    print(f"p15_import_shadow_analytics_review|runs|{','.join(result['run_ids'])}")
    return
```

- [ ] **Step 5: Run read-model tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_analytics_review.py tests/test_operator_shadow_analytics_review_read_model.py tests/test_schema.py tests/test_factor_cli.py -k 'shadow_analytics_review or p15_import_shadow_analytics_review' -q
```

Expected: selected tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/stock_research/operator_decision/shadow_analytics_review_read_model.py src/stock_research/schema.py src/stock_research/cli.py tests/test_operator_shadow_analytics_review_read_model.py tests/test_schema.py tests/test_factor_cli.py
git commit -m "feat: add p15 shadow analytics review read model"
```

---

### Task 4: Dashboard Read-Only Review View

**Files:**

- Create: `src/stock_research/dashboard/shadow_analytics_review.py`
- Create: `tests/test_dashboard_shadow_analytics_review.py`
- Create: `dashboard/src/components/ShadowAnalyticsReviewPanel.tsx`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_app.py`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/tests/client.test.ts`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Modify: `dashboard/tests/app-smoke.spec.ts`

- [ ] **Step 1: Write failing backend dashboard tests**

Create `tests/test_dashboard_shadow_analytics_review.py`:

```python
from psycopg import errors as psycopg_errors

from stock_research.dashboard import shadow_analytics_review


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_shadow_analytics_review_summary_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "review_group_id": "operator_shadow_analytics_review:p15:abc",
                "run_id": "p15-shadow-analytics-review-2026-06-30-2026-08-29",
                "review_start_date": "2026-06-30",
                "review_end_date": "2026-08-29",
                "source_p14_analytics_group_id": "operator_shadow_outcome_analytics:p14:trend-ready",
                "source_p14_analytics_run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 30,
                "complete_count": 28,
                "insufficient_data_count": 2,
                "horizon_metrics": {"20": {"forward_return_mean": 0.08}},
                "review_status": "research_follow_up_candidate",
                "review_bucket": "follow_up",
                "evidence_summary": "20d forward mean is positive.",
                "risk_notes": "Drawdown is controlled.",
                "next_research_question": "Review this group in future research.",
                "manual_review_required": False,
                "auto_trade_enabled": True,
                "production_watchlist_enabled": True,
                "production_write_enabled": True,
            }
        ]

    monkeypatch.setattr(shadow_analytics_review, "connect", fake_connect)
    monkeypatch.setattr(shadow_analytics_review, "fetch_all", fake_fetch_all)

    result = shadow_analytics_review.load_shadow_analytics_review_summary(
        start_date="2026-06-01",
        end_date="2026-08-31",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_shadow_analytics_review_group" in captured["sql"]
    assert "review_end_date BETWEEN %s AND %s" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-08-31", 10]
    assert result[0]["review_status"] == "research_follow_up_candidate"
    assert result[0]["horizon_metrics"]["20"]["forward_return_mean"] == 0.08
    assert result[0]["manual_review_required"] is True
    assert result[0]["auto_trade_enabled"] is False
    assert result[0]["production_watchlist_enabled"] is False
    assert result[0]["production_write_enabled"] is False


def test_load_shadow_analytics_review_summary_returns_empty_when_table_missing(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        raise psycopg_errors.UndefinedTable("missing P15 table")

    monkeypatch.setattr(shadow_analytics_review, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(shadow_analytics_review, "fetch_all", fake_fetch_all)

    assert shadow_analytics_review.load_shadow_analytics_review_summary(
        start_date="2026-06-01",
        end_date="2026-08-31",
    ) == []
```

Append to `tests/test_dashboard_app.py`:

```python
def test_shadow_analytics_review_route_returns_read_only_summary(monkeypatch):
    rows = [
        {
            "review_group_id": "operator_shadow_analytics_review:p15:abc",
            "run_id": "p15-shadow-analytics-review-2026-06-30-2026-08-29",
            "review_start_date": "2026-06-30",
            "review_end_date": "2026-08-29",
            "group_key": "trend_shadow|shadow_ready",
            "shadow_layer": "trend_shadow",
            "shadow_status": "shadow_ready",
            "sample_count": 30,
            "complete_count": 28,
            "insufficient_data_count": 2,
            "horizon_metrics": {"20": {"forward_return_mean": 0.08}},
            "review_status": "research_follow_up_candidate",
            "review_bucket": "follow_up",
            "evidence_summary": "20d forward mean is positive.",
            "risk_notes": "Drawdown is controlled.",
            "next_research_question": "Review this group in future research.",
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
        }
    ]
    captured = {}

    def fake_load_review(start_date, end_date, limit):
        captured["args"] = [start_date, end_date, limit]
        return rows

    monkeypatch.setattr(dashboard_app, "load_shadow_analytics_review_summary", fake_load_review)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/shadow-analytics-review?start_date=2026-06-01&end_date=2026-08-31&limit=10"
    )

    assert response.status_code == 200
    assert captured["args"] == ["2026-06-01", "2026-08-31", 10]
    assert response.json() == {"items": rows}
```

- [ ] **Step 2: Run backend tests to verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_shadow_analytics_review.py tests/test_dashboard_app.py -k 'shadow_analytics_review' -q
```

Expected: FAIL because module/route is missing.

- [ ] **Step 3: Implement backend query and route**

Create `src/stock_research/dashboard/shadow_analytics_review.py`:

```python
def load_shadow_analytics_review_summary(
    start_date: str,
    end_date: str,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    """Return read-only P15 shadow analytics review rows."""
```

Requirements:

- Query `ops.operator_shadow_analytics_review_group`.
- Filter `review_end_date BETWEEN %s AND %s`.
- Order by `review_end_date DESC, review_status, sample_count DESC, group_key`.
- Catch `psycopg.errors.UndefinedTable` and `psycopg.errors.InvalidSchemaName`, returning `[]`.
- Normalize `horizon_metrics` from dict or JSON string.
- Force safety fields to `True/False/False/False`.

Add route in `src/stock_research/dashboard/app.py`:

```python
@app.get("/api/shadow-analytics-review")
def shadow_analytics_review(start_date: str, end_date: str, limit: int = 20):
    return {
        "items": load_shadow_analytics_review_summary(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    }
```

- [ ] **Step 4: Run backend dashboard tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_shadow_analytics_review.py tests/test_dashboard_app.py -k 'shadow_analytics_review' -q
```

Expected: selected tests pass.

- [ ] **Step 5: Write failing frontend tests**

Modify `dashboard/src/api/types.ts` with:

```ts
export type ShadowAnalyticsReviewRow = {
  review_group_id: string;
  run_id: string;
  review_start_date: string;
  review_end_date: string;
  group_key: string;
  shadow_layer: string;
  shadow_status: string;
  sample_count: number;
  complete_count: number;
  insufficient_data_count: number;
  horizon_metrics: Record<string, Record<string, number | null>>;
  review_status: string;
  review_bucket: string;
  evidence_summary: string;
  risk_notes: string;
  next_research_question: string;
  manual_review_required: boolean;
  auto_trade_enabled: boolean;
  production_watchlist_enabled: boolean;
  production_write_enabled: boolean;
};
```

Add client test to `dashboard/tests/client.test.ts`:

```ts
it('fetches shadow analytics review', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ items: [{ review_group_id: 'p15:1', review_status: 'continue_observing' }] })
  });
  vi.stubGlobal('fetch', fetchMock);

  const result = await fetchShadowAnalyticsReview('2026-06-01', '2026-08-31', { limit: 20 });

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/shadow-analytics-review?start_date=2026-06-01&end_date=2026-08-31&limit=20'
  );
  expect(result[0].review_status).toBe('continue_observing');
});
```

Add app shell assertions in `dashboard/tests/app-shell.test.tsx`:

```ts
expect(screen.getByText('Shadow Analytics Review')).toBeVisible();
expect(screen.getByText('research_follow_up_candidate')).toBeVisible();
expect(screen.queryByRole('button', { name: /promote|trade|write watchlist|scheduler/i })).not.toBeInTheDocument();
```

Update `dashboard/tests/app-smoke.spec.ts` mocks so `/api/shadow-analytics-review` returns one row and assert the panel title appears on desktop and no mobile overflow occurs.

- [ ] **Step 6: Run frontend tests to verify they fail**

Run:

```bash
cd dashboard
pnpm test
```

Expected: FAIL because `fetchShadowAnalyticsReview` and `ShadowAnalyticsReviewPanel` are missing.

- [ ] **Step 7: Implement frontend client, component, and App wiring**

Modify `dashboard/src/api/client.ts`:

```ts
export async function fetchShadowAnalyticsReview(
  startDate: string,
  endDate: string,
  options: { limit?: number } = {}
): Promise<ShadowAnalyticsReviewRow[]> {
  const limit = options.limit ?? 20;
  const payload = await getJson<{ items: ShadowAnalyticsReviewRow[] }>(
    `/api/shadow-analytics-review?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}`
  );
  return payload.items;
}
```

Create `dashboard/src/components/ShadowAnalyticsReviewPanel.tsx`:

```tsx
import type { ShadowAnalyticsReviewRow } from '../api/types';

type ShadowAnalyticsReviewPanelProps = {
  rows: ShadowAnalyticsReviewRow[];
  isLoading?: boolean;
};

export function ShadowAnalyticsReviewPanel({ rows, isLoading = false }: ShadowAnalyticsReviewPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Shadow Analytics Review</h2>
      {isLoading ? (
        <p className="muted">Loading shadow analytics review...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No shadow analytics review rows for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => {
            const twentyDay = row.horizon_metrics['20'] ?? {};
            return (
              <article className="decision-row analytics-row" key={row.review_group_id}>
                <div>
                  <strong>{row.shadow_layer}</strong>
                  <span>{row.shadow_status}</span>
                </div>
                <div className="outcome-metrics">
                  <span>{row.review_status}</span>
                  <span>{row.review_bucket}</span>
                  <span>N {row.sample_count}</span>
                </div>
                <p className="muted">{row.evidence_summary}</p>
                <p className="muted">{row.risk_notes}</p>
                <p className="muted">{row.next_research_question}</p>
                <div className="outcome-metrics">
                  <span>20D {formatPercent(twentyDay.forward_return_mean)}</span>
                  <span>DD {formatPercent(twentyDay.max_low_drawdown_worst)}</span>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'n/a';
  }
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(1)}%`;
}
```

Wire it into `dashboard/src/App.tsx` using the same loading/error pattern as `ShadowOutcomeAnalyticsPanel`.

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
git add src/stock_research/dashboard/shadow_analytics_review.py tests/test_dashboard_shadow_analytics_review.py src/stock_research/dashboard/app.py tests/test_dashboard_app.py dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/App.tsx dashboard/src/components/ShadowAnalyticsReviewPanel.tsx dashboard/tests/client.test.ts dashboard/tests/app-shell.test.tsx dashboard/tests/app-smoke.spec.ts
git commit -m "feat: add p15 shadow analytics review dashboard"
```

---

### Task 5: Smoke, Runbook, Completion Review

**Files:**

- Create: `src/stock_research/operator_decision/p15_smoke.py`
- Create: `tests/test_p15_shadow_analytics_review_smoke.py`
- Create: `docs/quant_system/53_p15_shadow_analytics_operational_review_runbook.md`
- Create: `docs/quant_system/54_p15_shadow_analytics_operational_review_completion.md`

- [ ] **Step 1: Write failing smoke test**

Create `tests/test_p15_shadow_analytics_review_smoke.py`:

```python
from pathlib import Path

from stock_research.operator_decision.p15_smoke import build_p15_shadow_analytics_review_smoke


def test_p15_smoke_builds_shadow_analytics_review_artifacts_and_read_model_rows(tmp_path):
    result = build_p15_shadow_analytics_review_smoke(tmp_path)

    assert Path(result["p14_shadow_outcome_analytics_json_path"]).exists()
    assert Path(result["p15_shadow_analytics_review_json_path"]).exists()
    assert Path(result["p15_shadow_analytics_review_groups_csv_path"]).exists()
    assert Path(result["p15_shadow_analytics_review_markdown_path"]).exists()
    assert result["source_group_count"] == 1
    assert result["review_group_count"] == 1
    assert result["read_model_group_count"] == 1
    assert result["review_statuses"] == ["needs_more_data"]
    assert result["review_buckets"] == ["data_needed"]
    assert result["group_keys"] == ["trend_shadow|shadow_ready"]
    assert result["manual_review_required"] is True
    assert result["auto_trade_enabled"] is False
    assert result["production_watchlist_enabled"] is False
    assert result["production_write_enabled"] is False
```

- [ ] **Step 2: Run smoke test to verify it fails**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_p15_shadow_analytics_review_smoke.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'stock_research.operator_decision.p15_smoke'`.

- [ ] **Step 3: Implement P15 smoke**

Create `src/stock_research/operator_decision/p15_smoke.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from stock_research.operator_decision.p14_smoke import build_p14_shadow_outcome_analytics_smoke
from stock_research.operator_decision.shadow_analytics_review import (
    build_shadow_analytics_review,
    write_shadow_analytics_review,
)
from stock_research.operator_decision.shadow_analytics_review_read_model import (
    load_shadow_analytics_review_read_model_rows,
)


def build_p15_shadow_analytics_review_smoke(output_dir: str | Path) -> dict[str, Any]:
    output_path = Path(output_dir)
    p14_result = build_p14_shadow_outcome_analytics_smoke(output_path)
    p15_dir = output_path / "p15"
    p15_dir.mkdir(parents=True, exist_ok=True)

    p14_json_path = Path(p14_result["p14_shadow_outcome_analytics_json_path"])
    p14_payload = json.loads(p14_json_path.read_text(encoding="utf-8"))
    review = build_shadow_analytics_review(
        p14_analytics=p14_payload,
        run_id="p15-smoke-shadow-analytics-review-2026-06-30-2026-08-29",
        review_start_date="2026-06-30",
        review_end_date="2026-08-29",
        reviewer_id="operator",
    )
    review_paths = write_shadow_analytics_review(review, p15_dir)
    read_rows = load_shadow_analytics_review_read_model_rows(review_paths["json_path"])
    run = read_rows["run"]
    groups = read_rows["groups"]
    return {
        "p14_shadow_outcome_analytics_json_path": str(p14_json_path),
        "p15_shadow_analytics_review_json_path": review_paths["json_path"],
        "p15_shadow_analytics_review_groups_csv_path": review_paths["groups_csv_path"],
        "p15_shadow_analytics_review_markdown_path": review_paths["markdown_path"],
        "source_group_count": int(p14_payload["group_count"]),
        "review_group_count": int(run["group_count"]),
        "read_model_group_count": len(groups),
        "review_statuses": sorted({str(row["review_status"]) for row in groups}),
        "review_buckets": sorted({str(row["review_bucket"]) for row in groups}),
        "group_keys": sorted({str(row["group_key"]) for row in groups}),
        "manual_review_required": bool(run["manual_review_required"]),
        "auto_trade_enabled": bool(run["auto_trade_enabled"]),
        "production_watchlist_enabled": bool(run["production_watchlist_enabled"]),
        "production_write_enabled": bool(run["production_write_enabled"]),
    }
```

Ensure the module imports `json`.

- [ ] **Step 4: Run smoke tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_p15_shadow_analytics_review_smoke.py tests/test_p14_shadow_outcome_analytics_smoke.py -q
```

Expected: selected tests pass.

- [ ] **Step 5: Run actual smoke command**

Run:

```bash
rm -rf /tmp/stock_research_p15_smoke
/Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p15_smoke import build_p15_shadow_analytics_review_smoke
result = build_p15_shadow_analytics_review_smoke(Path('/tmp/stock_research_p15_smoke'))
print(f"p15_smoke|p14_shadow_outcome_analytics|{result['p14_shadow_outcome_analytics_json_path']}")
print(f"p15_smoke|p15_shadow_analytics_review|{result['p15_shadow_analytics_review_json_path']}")
print(f"p15_smoke|groups_csv|{result['p15_shadow_analytics_review_groups_csv_path']}")
print(f"p15_smoke|markdown|{result['p15_shadow_analytics_review_markdown_path']}")
print(f"p15_smoke|source_group_count|{result['source_group_count']}")
print(f"p15_smoke|review_group_count|{result['review_group_count']}")
print(f"p15_smoke|read_model_groups|{result['read_model_group_count']}")
print(f"p15_smoke|review_statuses|{','.join(result['review_statuses'])}")
print(f"p15_smoke|review_buckets|{','.join(result['review_buckets'])}")
print(f"p15_smoke|group_keys|{','.join(result['group_keys'])}")
print(f"p15_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p15_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p15_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p15_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Record the exact output in `docs/quant_system/54_p15_shadow_analytics_operational_review_completion.md`.

- [ ] **Step 6: Write runbook and completion review**

Create `docs/quant_system/53_p15_shadow_analytics_operational_review_runbook.md` with:

- purpose and review-only boundary
- artifact command
- import command
- dashboard endpoint
- smoke command
- safety notes

Create `docs/quant_system/54_p15_shadow_analytics_operational_review_completion.md` with:

- delivered capabilities for P15-0 through P15-5
- actual smoke output from Step 5
- final verification command list and exact pass counts
- safety review
- known non-P15 workspace dirty file note

- [ ] **Step 7: Final verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_analytics_review.py tests/test_operator_shadow_analytics_review_read_model.py tests/test_p15_shadow_analytics_review_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_analytics_review.py tests/test_dashboard_app.py -k 'shadow_analytics_review or p15_shadow_analytics_review or p15_import_shadow_analytics_review or dashboard' -q
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```

Expected: Python focused tests pass, Vitest passes, build passes, Playwright passes.

- [ ] **Step 8: Commit**

Run:

```bash
git add src/stock_research/operator_decision/p15_smoke.py tests/test_p15_shadow_analytics_review_smoke.py docs/quant_system/53_p15_shadow_analytics_operational_review_runbook.md docs/quant_system/54_p15_shadow_analytics_operational_review_completion.md
git commit -m "docs: complete p15 shadow analytics operational review governance"
```

---

## Final Review And Integration

- [ ] **Step 1: Final code review**

Dispatch a final code reviewer for the whole P15 branch. Review for:

- review-only boundary
- no candidate ranking or production promotion recommendation
- no production watchlist/factor/scheduler/trading writes
- correct source scope: consumes P14 group analytics only
- P14 lineage preserved through source P14 IDs
- idempotent run-scoped read-model IDs
- missing-table dashboard behavior
- dashboard has no action controls
- runbook commands match CLI output

- [ ] **Step 2: Final verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_analytics_review.py tests/test_operator_shadow_analytics_review_read_model.py tests/test_p15_shadow_analytics_review_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_analytics_review.py tests/test_dashboard_app.py -k 'shadow_analytics_review or p15_shadow_analytics_review or p15_import_shadow_analytics_review or dashboard' -q
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
