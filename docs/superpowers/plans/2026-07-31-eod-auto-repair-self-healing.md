# EOD Auto Repair Self-Healing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make scheduled EOD repair use bounded multi-cycle recovery, retry unresolved recent trade dates across runs, accept safe LHB candidate attrition as degraded output, and keep the legacy strategy status writer compatible with the live database schema.

**Architecture:** Keep the existing check/action loop and add a strategy-specific publication contract plus a small filesystem-backed pending-date queue. The scheduled CLI will optionally run a bounded batch of old pending dates followed by the current date; each date remains independently reported and queued until it has no hard blockers. The legacy status store will use an additive schema migration and write the artifact status on every path.

**Tech Stack:** Python 3, pandas, PostgreSQL through the existing `stock_research.db` helpers, Bash cron wrappers, pytest, JSON/Markdown reports.

---

## File Structure

- Create: `src/stock_research/eod_auto_repair_queue.py`
  - Selects recent unresolved dates, merges durable queue state, and atomically persists retry records.
- Modify: `src/stock_research/strategy_eod_publish.py`
  - Replaces the global exact-five review check with strategy-specific validation and degraded metadata.
- Modify: `src/stock_research/eod_auto_repair_checks.py`
  - Classifies safe LHB attrition as degraded and malformed strategy groups as blockers.
- Modify: `src/stock_research/eod_auto_repair_actions.py`
  - Preserves degraded status and publisher warnings in the repair action result.
- Modify: `src/stock_research/eod_auto_repair.py`
  - Adds opt-in pending-date batch execution and CLI flags.
- Modify: `src/stock_research/strategy_daily_eod_store.py`
  - Adds the live `midtrend_artifacts_status` column and payload/query/upsert support.
- Modify: `src/stock_research/strategy_daily_eod.py`
  - Writes `midtrend_artifacts_status` for success and dependency-failure paths.
- Modify: `scripts/run_platform_ready_check_cron.sh`
  - Uses loop mode and pending-date processing in the actual scheduled entrypoint.
- Modify: `scripts/run_eod_auto_repair_cron.sh`
  - Uses the same loop and pending-date flags as the platform-ready entrypoint.
- Modify: `tests/test_strategy_eod_publish.py`
- Modify: `tests/test_eod_auto_repair_checks.py`
- Modify: `tests/test_eod_auto_repair_actions.py`
- Modify: `tests/test_strategy_daily_eod.py`
- Modify: `tests/test_platform_ready_scripts.py`
- Modify: `tests/test_eod_auto_repair_scripts.py`
- Modify: `tests/test_eod_auto_repair.py`
- Create: `tests/test_eod_auto_repair_queue.py`

## Task 1: Replace the global exact-five strategy contract

**Files:**
- Modify: `tests/test_strategy_eod_publish.py`
- Modify: `src/stock_research/strategy_eod_publish.py`
- Modify: `tests/test_eod_auto_repair_checks.py`
- Modify: `src/stock_research/eod_auto_repair_checks.py`
- Modify: `tests/test_eod_auto_repair_actions.py`
- Modify: `src/stock_research/eod_auto_repair_actions.py`

- [ ] **Step 1: Write the failing publisher regression test**

Replace the existing LHB four-row case in `tests/test_strategy_eod_publish.py` with a successful degraded case using the existing `_install_publish_contract_fakes` helper:

```python
def test_publish_strategy_eod_accepts_four_safe_lhb_rows_as_degraded(monkeypatch, tmp_path):
    strategy_assets = {
        "lhb_shortline": ["CN:SH:000001", "CN:SH:000002", "CN:SH:000003", "CN:SH:000004"],
        "mid_trend": [f"CN:SH:{index:06d}" for index in range(101, 106)],
        "tech_bottleneck": [f"CN:SH:{index:06d}" for index in range(201, 206)],
    }
    _install_publish_contract_fakes(monkeypatch, tmp_path, strategy_assets=strategy_assets)

    summary = strategy_eod_publish.publish_strategy_eod(
        trade_date="2026-07-30",
        output_root=tmp_path,
        runner=lambda payload: {"strategy_id": payload["strategy_id"]},
        manifest_upsert=lambda entry: None,
    )

    assert summary["publishable"] is True
    assert summary["review_rows"] == 14
    assert summary["strategy_counts"]["lhb_shortline"] == 4
    assert summary["degraded_strategies"] == ["lhb_shortline"]
    assert any("lhb_shortline" in warning for warning in summary["warnings"])
```

Keep the existing invalid cases for zero LHB rows, duplicate LHB assets, and six LHB rows. They must continue to raise the contract error.

- [ ] **Step 2: Run the publisher regression tests and confirm the expected red failure**

Run:

```bash
rtk .venv/bin/pytest tests/test_strategy_eod_publish.py::test_publish_strategy_eod_accepts_four_safe_lhb_rows_as_degraded -q
```

Expected: FAIL because the current publisher raises `RuntimeError` for four LHB rows.

- [ ] **Step 3: Implement strategy-specific contract validation**

In `src/stock_research/strategy_eod_publish.py`, replace `EXPECTED_STRATEGY_REVIEW_COUNTS` with:

```python
STRATEGY_REVIEW_CONTRACTS = {
    "lhb_shortline": {"min_rows": 1, "max_rows": 5, "target_rows": 5},
    "mid_trend": {"min_rows": 5, "max_rows": 5, "target_rows": 5},
    "tech_bottleneck": {"min_rows": 5, "max_rows": 5, "target_rows": 5},
}
```

Add `_validate_strategy_review_contract(unique_counts, row_counts)` returning `(degraded_strategies, errors)`. For each configured strategy, compare row count and unique-asset count. Add an error when the counts differ, the count is outside `min_rows`/`max_rows`, or a required strategy is absent. Add a degraded strategy when its count is below `target_rows` but still valid.

Use the helper immediately after `_write_review_queue`. Raise the existing `RuntimeError` only when `errors` is non-empty. When validation succeeds, include these fields in the final summary:

```python
"strategy_counts": strategy_counts,
"strategy_row_counts": strategy_row_counts,
"degraded_strategies": degraded_strategies,
"warnings": [
    f"{strategy_id} published {row_counts[strategy_id]} safe rows; target is {contract['target_rows']}"
    for strategy_id in degraded_strategies
],
"publishable": True,
```

Keep the review manifest manifest entry status as `success` for valid degraded LHB output so downstream publication checks see a publishable artifact.

- [ ] **Step 4: Write the failing review-queue classification tests**

Add to `tests/test_eod_auto_repair_checks.py`:

```python
def test_evaluate_review_queue_groups_marks_four_lhb_rows_degraded():
    payload = {
        "trade_date": "2026-07-30",
        "groups": [
            {"bucket": "strategy:lhb_shortline", "count": 4, "items": [{"asset_id": "A"}, {"asset_id": "B"}, {"asset_id": "C"}, {"asset_id": "D"}]},
            {"bucket": "strategy:mid_trend", "count": 5, "items": [{"asset_id": "E"}, {"asset_id": "F"}, {"asset_id": "G"}, {"asset_id": "H"}, {"asset_id": "I"}]},
            {"bucket": "strategy:tech_bottleneck", "count": 5, "items": [{"asset_id": "J"}, {"asset_id": "K"}, {"asset_id": "L"}, {"asset_id": "M"}, {"asset_id": "N"}]},
        ],
    }

    result = evaluate_review_queue_groups(payload, trade_date="2026-07-30")

    assert result.status == RepairStatus.DEGRADED
    assert result.blocker is False
    assert result.metrics["degraded_buckets"] == ["strategy:lhb_shortline"]


def test_evaluate_review_queue_groups_keeps_invalid_strategy_counts_blocking():
    payload = {
        "trade_date": "2026-07-30",
        "groups": [
            {"bucket": "strategy:lhb_shortline", "count": 0, "items": []},
            {"bucket": "strategy:mid_trend", "count": 4, "items": [{"asset_id": "A"}]},
            {"bucket": "strategy:tech_bottleneck", "count": 5, "items": [{"asset_id": "B"}]},
        ],
    }

    result = evaluate_review_queue_groups(payload, trade_date="2026-07-30")

    assert result.status == RepairStatus.FAILED
    assert result.blocker is True
    assert "lhb_shortline" in result.message
    assert "mid_trend" in result.message
```

- [ ] **Step 5: Run the new check tests and confirm they fail before implementation**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_checks.py::test_evaluate_review_queue_groups_marks_four_lhb_rows_degraded tests/test_eod_auto_repair_checks.py::test_evaluate_review_queue_groups_keeps_invalid_strategy_counts_blocking -q
```

Expected: FAIL because the current group evaluator only checks for a nonzero Tech group and never returns degraded status for LHB attrition.

- [ ] **Step 6: Implement review-queue status propagation**

Update `evaluate_review_queue_groups` to require all three strategy buckets, require LHB to have 1–5 rows, require Mid Trend and Tech Bottleneck to have exactly five rows, preserve the identical-LHB/Mid asset blocker, and return `RepairStatus.DEGRADED` only for valid LHB counts from 1 through 4. Update `check_review_queue` so a successful score check plus a degraded group check returns a non-blocking degraded result.

Update `repair_strategy_publish` so a publisher result with a non-empty `degraded_strategies` list returns `RepairStatus.DEGRADED`, includes `degraded_strategies` and `warnings` in `metrics`, and still records the output directory.

- [ ] **Step 7: Run the focused contract and action tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_strategy_eod_publish.py tests/test_eod_auto_repair_checks.py tests/test_eod_auto_repair_actions.py -q
```

Expected: PASS, including the preserved zero/duplicate/over-limit rejection cases.

- [ ] **Step 8: Commit the contract fix**

```bash
rtk git add src/stock_research/strategy_eod_publish.py src/stock_research/eod_auto_repair_checks.py src/stock_research/eod_auto_repair_actions.py tests/test_strategy_eod_publish.py tests/test_eod_auto_repair_checks.py tests/test_eod_auto_repair_actions.py
rtk git commit -m "fix: allow safe degraded lhb eod publication"
```

## Task 2: Repair the legacy strategy status schema drift

**Files:**
- Modify: `tests/test_strategy_daily_eod.py`
- Modify: `src/stock_research/strategy_daily_eod_store.py`
- Modify: `src/stock_research/strategy_daily_eod.py`

- [ ] **Step 1: Write failing schema/status tests**

Extend `test_status_payload_and_schema` with:

```python
    assert payload["midtrend_artifacts_status"] == "unknown"
    assert "midtrend_artifacts_status" in store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "ADD COLUMN IF NOT EXISTS midtrend_artifacts_status" in store.STRATEGY_DAILY_EOD_STATUS_SQL
```

Extend `test_run_strategy_daily_eod_writes_midtrend_v1_v2_and_review_artifacts` with:

```python
    assert captured["payload"]["midtrend_artifacts_status"] == "success"
```

Extend `test_run_strategy_daily_eod_skips_when_deps_fail` with:

```python
    assert captured["payload"]["midtrend_artifacts_status"] == "skipped"
```

- [ ] **Step 2: Run the schema/status tests and confirm they fail**

Run:

```bash
rtk .venv/bin/pytest tests/test_strategy_daily_eod.py -q
```

Expected: FAIL because the payload has no artifact status and the SQL has no compatibility migration.

- [ ] **Step 3: Implement additive schema migration and payload persistence**

In `strategy_daily_eod_store.py`:

1. Add `midtrend_artifacts_status text NOT NULL DEFAULT 'unknown'` to the create-table definition.
2. Add this exact additive migration after the create-table statement:

```sql
ALTER TABLE ops.strategy_daily_eod_status
    ADD COLUMN IF NOT EXISTS midtrend_artifacts_status text NOT NULL DEFAULT 'unknown';
```

3. Add `midtrend_artifacts_status` to `build_status_payload`, the INSERT column list, the VALUES mapping, the conflict-update list, and the SELECT list.
4. Keep the existing status values used by the live database accepted in the create-table definition: `success`, `failed`, `running`, `skipped`, `partial`, and `blocked`.

In `strategy_daily_eod.py`:

1. Pass `strategy_status["midtrend_artifacts"]` in the normal upsert.
2. Extend `_finalize_failure` with `midtrend_artifacts_status` and pass `"skipped"` from the dependency-failure branch.
3. Include `midtrend_artifacts` in the failure summary strategy-status map so the JSON and database status agree.

- [ ] **Step 4: Run the strategy status tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_strategy_daily_eod.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the schema-drift fix**

```bash
rtk git add src/stock_research/strategy_daily_eod_store.py src/stock_research/strategy_daily_eod.py tests/test_strategy_daily_eod.py
rtk git commit -m "fix: persist midtrend artifact eod status"
```

## Task 3: Add the durable unresolved-date queue

**Files:**
- Create: `src/stock_research/eod_auto_repair_queue.py`
- Create: `tests/test_eod_auto_repair_queue.py`

- [ ] **Step 1: Write failing queue tests**

Create `tests/test_eod_auto_repair_queue.py` with:

```python
import json
from pathlib import Path

from stock_research.eod_auto_repair_queue import (
    pending_queue_path,
    record_repair_result,
    select_pending_trade_dates,
)


def test_select_pending_trade_dates_bootstraps_recent_failed_summaries(tmp_path: Path):
    output_root = tmp_path / "outputs"
    for trade_date in ("2026-07-28", "2026-07-29"):
        run_dir = output_root / "research" / "eod_auto_repair" / trade_date
        run_dir.mkdir(parents=True)
        (run_dir / "run_summary.json").write_text(
            json.dumps({"trade_date": trade_date, "final_status": "failed", "remaining_blockers": ["strategy_publish"]}),
            encoding="utf-8",
        )
    old_dir = output_root / "research" / "eod_auto_repair" / "2026-07-01"
    old_dir.mkdir(parents=True)
    (old_dir / "run_summary.json").write_text(
        json.dumps({"trade_date": "2026-07-01", "final_status": "failed", "remaining_blockers": ["strategy_publish"]}),
        encoding="utf-8",
    )

    selected = select_pending_trade_dates(
        current_trade_date="2026-07-30",
        output_root=output_root,
        pending_date_limit=2,
        bootstrap_lookback_days=7,
    )

    assert selected == ["2026-07-28", "2026-07-29", "2026-07-30"]


def test_record_repair_result_removes_blocker_free_degraded_date(tmp_path: Path):
    output_root = tmp_path / "outputs"
    record_repair_result(
        output_root=output_root,
        summary={"trade_date": "2026-07-29", "final_status": "failed", "remaining_blockers": ["review_queue"], "actions": []},
    )
    record_repair_result(
        output_root=output_root,
        summary={"trade_date": "2026-07-29", "final_status": "degraded", "remaining_blockers": [], "actions": []},
    )

    queue_path = pending_queue_path(output_root)
    payload = json.loads(queue_path.read_text(encoding="utf-8"))

    assert payload["items"] == []
```

- [ ] **Step 2: Run the queue tests and confirm the expected red failure**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_queue.py -q
```

Expected: FAIL because the queue module does not exist.

- [ ] **Step 3: Implement queue selection and atomic persistence**

Create `src/stock_research/eod_auto_repair_queue.py` with these functions:

```python
def pending_queue_path(output_root: str | Path) -> Path:
    return Path(output_root) / "research" / "eod_auto_repair" / "pending_dates.json"


def select_pending_trade_dates(
    *,
    current_trade_date: str,
    output_root: str | Path,
    pending_date_limit: int = 3,
    bootstrap_lookback_days: int = 7,
) -> list[str]:
    """Return oldest queued dates, followed by current_trade_date exactly once."""


def record_repair_result(*, output_root: str | Path, summary: dict[str, Any]) -> dict[str, Any]:
    """Persist one date result and remove it only when no hard blockers remain."""
```

Implementation requirements:

1. Read an existing payload shaped as `{"version": 1, "items": [...]}`; treat a missing or malformed file as an empty queue.
2. Bootstrap only exact `YYYY-MM-DD` directories whose dates fall in the previous seven calendar days relative to `current_trade_date`, and import a summary when `final_status == "failed"` or `remaining_blockers` is non-empty.
3. Merge queue records by `trade_date`, sort dates ascending, select at most `pending_date_limit`, and append the current date if it is not selected.
4. Store `attempts`, `last_status`, `remaining_blockers`, the latest failed action message, and an ISO UTC `updated_at` value.
5. Write through `pending_dates.json.tmp` followed by `Path.replace` and create parent directories before writing.

- [ ] **Step 4: Run the queue tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_queue.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the queue module**

```bash
rtk git add src/stock_research/eod_auto_repair_queue.py tests/test_eod_auto_repair_queue.py
rtk git commit -m "feat: persist pending eod repair dates"
```

## Task 4: Integrate pending-date batch execution into the CLI

**Files:**
- Modify: `tests/test_eod_auto_repair.py`
- Modify: `src/stock_research/eod_auto_repair.py`

- [ ] **Step 1: Write the failing batch orchestration test**

Add a test that monkeypatches `run_eod_auto_repair` and verifies a failed old date does not prevent the current date from running:

```python
def test_run_eod_auto_repair_batch_continues_after_failed_date(tmp_path, monkeypatch):
    calls = []

    def fake_run_eod_auto_repair(**kwargs):
        calls.append(kwargs["trade_date"])
        status = RepairStatus.FAILED if kwargs["trade_date"] == "2026-07-29" else RepairStatus.SUCCESS
        blockers = ["strategy_publish"] if status == RepairStatus.FAILED else []
        return RepairRunSummary(
            trade_date=kwargs["trade_date"],
            mode="loop",
            final_status=status,
            remaining_blockers=blockers,
        )

    monkeypatch.setattr(eod, "run_eod_auto_repair", fake_run_eod_auto_repair)
    output_root = tmp_path / "outputs"
    queue_path = output_root / "research" / "eod_auto_repair" / "pending_dates.json"
    queue_path.parent.mkdir(parents=True)
    queue_path.write_text(
        json.dumps({"version": 1, "items": [{"trade_date": "2026-07-29", "attempts": 1}]}),
        encoding="utf-8",
    )

    summaries = eod.run_eod_auto_repair_batch(
        trade_date="2026-07-30",
        current_output_dir=tmp_path / "current",
        output_root=output_root,
        mode="loop",
        pending_date_limit=1,
        max_cycles=3,
        action_registry={},
        write_reports=False,
    )

    assert calls == ["2026-07-29", "2026-07-30"]
    assert [summary.trade_date for summary in summaries] == calls
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    assert [item["trade_date"] for item in queue["items"]] == ["2026-07-29"]
```

Add the required imports to `tests/test_eod_auto_repair.py`: `json`, `RepairRunSummary`, and `RepairStatus`.

- [ ] **Step 2: Run the batch test and confirm the expected red failure**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py::test_run_eod_auto_repair_batch_continues_after_failed_date -q
```

Expected: FAIL because `run_eod_auto_repair_batch` and the CLI flags do not exist.

- [ ] **Step 3: Implement batch execution and queue updates**

Add `run_eod_auto_repair_batch` to `src/stock_research/eod_auto_repair.py` with this signature:

```python
def run_eod_auto_repair_batch(
    *,
    trade_date: str,
    current_output_dir: str | Path,
    output_root: str | Path,
    mode: str,
    pending_date_limit: int,
    max_cycles: int,
    dry_run: bool,
    strict: bool,
    action_timeout_seconds: int | None,
    action_registry: dict[str, ActionRunner] | None = None,
    write_reports: bool = True,
) -> list[RepairRunSummary]:
```

Implementation behavior:

1. Call `select_pending_trade_dates` with `current_trade_date=trade_date`.
2. Build one default action registry and reuse it for every selected date.
3. Use `current_output_dir` for the current date and `output_root/research/eod_auto_repair/YYYY-MM-DD` for older dates.
4. Call `run_eod_auto_repair` once per date with `mode="loop"`, the configured cycle/timeout values, and `write_reports=True`.
5. Call `record_repair_result` immediately after each summary, then continue to the next selected date even if the summary is failed.
6. Write `output_root/research/eod_auto_repair/pending_run_summary.json` containing `version`, `selected_trade_dates`, and serialized summaries.

Extend `_main` with:

```python
parser.add_argument("--include-pending-dates", action="store_true")
parser.add_argument("--pending-date-limit", type=int, default=3)
```

When `--include-pending-dates` is absent, retain the current single-date path. When it is present, call `run_eod_auto_repair_batch` and return `0` only when every summary is `success` or `degraded` with no blockers; otherwise return `2`. Print the batch JSON payload rather than hiding the old-date results.

- [ ] **Step 4: Run the batch and existing orchestrator tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py tests/test_eod_auto_repair_queue.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the CLI queue integration**

```bash
rtk git add src/stock_research/eod_auto_repair.py tests/test_eod_auto_repair.py
rtk git commit -m "feat: retry pending eod dates in batch mode"
```

## Task 5: Align both cron wrappers with the self-healing CLI

**Files:**
- Modify: `tests/test_platform_ready_scripts.py`
- Modify: `scripts/run_platform_ready_check_cron.sh`
- Modify: `tests/test_eod_auto_repair_scripts.py`
- Modify: `scripts/run_eod_auto_repair_cron.sh`

- [ ] **Step 1: Write failing script assertions**

In the platform-ready script test, replace the `--mode repair` assertion with:

```python
    assert "--mode loop" in call
    assert "--max-cycles 3" in call
    assert "--include-pending-dates" in call
    assert "--pending-date-limit 3" in call
```

In the direct wrapper content test, add:

```python
    assert "--mode loop" in script
    assert "--include-pending-dates" in script
    assert "--pending-date-limit" in script
```

- [ ] **Step 2: Run the script tests and confirm the platform wrapper test fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_platform_ready_scripts.py::test_platform_ready_check_script_runs_eod_auto_repair_and_exits_with_status tests/test_eod_auto_repair_scripts.py -q
```

Expected: FAIL because the scheduled wrapper still passes `--mode repair` and has no pending-date flags.

- [ ] **Step 3: Update the platform-ready wrapper**

Add these variables near the existing heartbeat setting:

```bash
REPAIR_MAX_CYCLES="${PLATFORM_READY_REPAIR_MAX_CYCLES:-3}"
PENDING_DATE_LIMIT="${PLATFORM_READY_PENDING_DATE_LIMIT:-3}"
```

Change the module invocation to:

```bash
"$PYTHON" -m stock_research.eod_auto_repair \
  --trade-date "$TRADE_DATE" \
  --output-dir "$REPAIR_OUTPUT_DIR" \
  --output-root "$ROOT/outputs" \
  --mode loop \
  --max-cycles "$REPAIR_MAX_CYCLES" \
  --include-pending-dates \
  --pending-date-limit "$PENDING_DATE_LIMIT" >>"$RUN_LOG" 2>&1 &
```

Keep the existing heartbeat and child exit-code propagation unchanged.

- [ ] **Step 4: Update the direct wrapper**

Add:

```bash
MAX_CYCLES="${EOD_AUTO_REPAIR_MAX_CYCLES:-3}"
PENDING_DATE_LIMIT="${EOD_AUTO_REPAIR_PENDING_DATE_LIMIT:-3}"
```

Pass `--output-root "$ROOT/outputs"`, `--mode loop`, `--max-cycles "$MAX_CYCLES"`, `--include-pending-dates`, and `--pending-date-limit "$PENDING_DATE_LIMIT"` to the existing `rtk "$PYTHON" -m stock_research.eod_auto_repair` command.

- [ ] **Step 5: Run both script suites**

Run:

```bash
rtk .venv/bin/pytest tests/test_platform_ready_scripts.py tests/test_eod_auto_repair_scripts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the scheduled-entrypoint fix**

```bash
rtk git add scripts/run_platform_ready_check_cron.sh scripts/run_eod_auto_repair_cron.sh tests/test_platform_ready_scripts.py tests/test_eod_auto_repair_scripts.py
rtk git commit -m "fix: schedule eod auto repair loop with pending dates"
```

## Task 6: Full focused verification and controlled replay

**Files:**
- No source changes unless a verification test exposes a regression.

- [ ] **Step 1: Run all affected unit and script tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_strategy_eod_publish.py tests/test_eod_auto_repair_checks.py tests/test_eod_auto_repair_actions.py tests/test_strategy_daily_eod.py tests/test_eod_auto_repair_queue.py tests/test_eod_auto_repair.py tests/test_platform_ready_scripts.py tests/test_eod_auto_repair_scripts.py -q
```

Expected: exit code 0 with zero failures.

- [ ] **Step 2: Run repository diff and status checks**

Run:

```bash
rtk git diff --check
rtk git status --short --branch
```

Expected: no whitespace errors; only the intended source/test/docs commits plus the pre-existing user modifications are present.

- [ ] **Step 3: Run a read-only 2026-07-30 replay into temporary output**

Run:

```bash
rtk .venv/bin/python -m stock_research.eod_auto_repair \
  --trade-date 2026-07-30 \
  --output-dir /private/tmp/eod_auto_repair_20260730_check \
  --output-root /Users/xiwei/stock_research/outputs \
  --mode check
```

Expected: a JSON summary and Markdown report are written under `/private/tmp/eod_auto_repair_20260730_check`; the command does not run repair actions.

- [ ] **Step 4: Run the repaired 2026-07-30 loop**

Run only after Steps 1–3 pass:

```bash
rtk .venv/bin/python -m stock_research.eod_auto_repair \
  --trade-date 2026-07-30 \
  --output-dir /Users/xiwei/stock_research/outputs/research/eod_auto_repair/2026-07-30 \
  --output-root /Users/xiwei/stock_research/outputs \
  --mode loop \
  --max-cycles 3 \
  --include-pending-dates \
  --pending-date-limit 3 \
  --action-timeout-seconds 43200
```

Expected evidence:

- The summary reports `mode: loop`.
- LHB four-row safety attrition is `degraded`, not a strategy publisher exception.
- The legacy status upsert no longer fails on `midtrend_artifacts_status`.
- `pending_dates.json` contains only dates that still have hard blockers.
- The batch exits nonzero only if one of the selected dates remains blocked; the report lists the exact remaining blockers and latest action errors.

- [ ] **Step 5: Review generated artifacts without overwriting user-owned datasets**

Inspect only:

```bash
rtk jq '{mode, final_status, remaining_blockers, loop_stop_reason}' outputs/research/eod_auto_repair/2026-07-30/run_summary.json
rtk jq '{version, items}' outputs/research/eod_auto_repair/pending_dates.json
rtk rg -n "Mode:|Final status:|Remaining blockers|degraded|midtrend_artifacts_status|pending" outputs/research/eod_auto_repair/2026-07-30/run_report.md
```

Expected: the report explicitly distinguishes degraded LHB publication from hard blockers and shows the queue state.

- [ ] **Step 6: Make any verification-only correction with a new red-green test cycle**

If any expected result differs, stop claiming completion, add the smallest failing regression test for the observed mismatch, implement only that root-cause correction, rerun the affected tests, and commit the correction with an explicit message.

## Acceptance Checklist

- [ ] Scheduled platform-ready wrapper passes `--mode loop`.
- [ ] LHB four-row safe output publishes as degraded and remains visible.
- [ ] LHB zero/duplicate/over-limit outputs remain blocking failures.
- [ ] `midtrend_artifacts_status` is migrated, written, and loaded.
- [ ] Pending dates are selected oldest-first and removed only after blocker-free completion.
- [ ] A failed old date does not prevent the current date from running.
- [ ] Focused tests pass with fresh output.
- [ ] The 2026-07-30 replay produces evidence for the final status before any completion claim.
