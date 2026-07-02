# EOD Auto Repair Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make EOD auto repair recover the full daily close chain after missing minute bars, scores, watchlists, market monitor data, and interrupted strategy publication, while always producing an actionable report.

**Architecture:** Keep the existing check/action modules, then add a small staged orchestration layer. The orchestrator runs checks by dependency stage, isolates action exceptions, writes summaries in all failure paths, and uses one publishable-readiness contract for auto repair and strategy publish.

**Tech Stack:** Python, pytest, PostgreSQL through existing `stock_research.db`, existing daily close/strategy/dashboard builders, shell cron wrapper.

---

## File Structure

- Modify `scripts/run_eod_auto_repair_cron.sh`
  - Remove `flock`; use the project cron guard or a portable lock path.
- Modify `tests/test_eod_auto_repair_scripts.py`
  - Prove the wrapper does not depend on `flock`.
- Modify `src/stock_research/eod_auto_repair_models.py`
  - Add stage results and remaining blocker/non-blocker fields to `RepairRunSummary`.
- Modify `src/stock_research/eod_auto_repair.py`
  - Add stage definitions, safe check execution, safe action execution, always-write report behavior, and staged orchestration.
- Modify `src/stock_research/eod_auto_repair_actions.py`
  - Add score, watchlist, technical features, reports, snapshots, and quality refresh action wrappers with injected runners.
- Modify `tests/test_eod_auto_repair.py`
  - Add staged orchestration, exception isolation, and incident-flow tests.
- Modify `tests/test_eod_auto_repair_actions.py`
  - Add injected-runner tests for new actions.
- Modify `src/stock_research/strategy_eod_publish.py`
  - Make base data gate accept publishable degraded checks and carry warnings into manifest entries.
- Modify `tests/test_strategy_eod_publish.py` or the existing strategy publish test file if different
  - Add coverage for degraded daily bars being publishable and blocker base data still stopping publish.
- Modify `README.md`
  - Document the staged repair workflow and expected summary/report paths.

---

### Task 1: Make Cron Locking Portable

**Files:**
- Modify: `scripts/run_eod_auto_repair_cron.sh`
- Modify: `tests/test_eod_auto_repair_scripts.py`

- [ ] **Step 1: Write the failing script test**

Replace `tests/test_eod_auto_repair_scripts.py` with:

```python
from pathlib import Path


def test_eod_auto_repair_cron_uses_module_entrypoint_and_portable_lock():
    script = Path("scripts/run_eod_auto_repair_cron.sh").read_text()

    assert "python -m stock_research.eod_auto_repair" in script
    assert "flock" not in script
    assert "stock_cron_guard.sh" in script or "noclobber" in script
    assert "--mode repair" in script
    assert "logs/eod_auto_repair" in script
    assert "run_summary.json" in script
    assert "run_report.md" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_scripts.py -q
```

Expected: FAIL because the script still contains `flock`.

- [ ] **Step 3: Replace `flock` in the cron wrapper**

Update `scripts/run_eod_auto_repair_cron.sh` to:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_RESEARCH_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_RESEARCH_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${1:-$(date +%F)}"
LOG_DIR="$ROOT/logs/eod_auto_repair"
OUTPUT_DIR="$ROOT/outputs/research/eod_auto_repair/$TRADE_DATE"
LOCK_FILE="$ROOT/.locks/eod_auto_repair.lock"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$(dirname "$LOCK_FILE")"

if ! (set -o noclobber; echo "$$" > "$LOCK_FILE") 2>/dev/null; then
  echo "eod_auto_repair|locked|$LOCK_FILE" | tee -a "$LOG_DIR/$TRADE_DATE.log"
  exit 0
fi
trap 'rm -f "$LOCK_FILE"' EXIT

cd "$ROOT"
set +e
{
  echo "=== eod auto repair start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  rtk "$PYTHON" -m stock_research.eod_auto_repair \
    --trade-date "$TRADE_DATE" \
    --output-dir "$OUTPUT_DIR" \
    --mode repair
  rc=$?
  echo "eod_auto_repair|summary|$OUTPUT_DIR/run_summary.json"
  echo "eod_auto_repair|report|$OUTPUT_DIR/run_report.md"
  echo "=== eod auto repair end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} 2>&1 | tee -a "$LOG_DIR/$TRADE_DATE.log"
rc=${PIPESTATUS[0]}
set -e
exit "$rc"
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_scripts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
rtk git add scripts/run_eod_auto_repair_cron.sh tests/test_eod_auto_repair_scripts.py
rtk git commit -m "fix: make eod auto repair cron portable"
```

---

### Task 2: Extend Models For Stages And Remaining Issues

**Files:**
- Modify: `src/stock_research/eod_auto_repair_models.py`
- Modify: `tests/test_eod_auto_repair_models.py`

- [ ] **Step 1: Write the failing model test**

Append to `tests/test_eod_auto_repair_models.py`:

```python
from stock_research.eod_auto_repair_models import RepairStageResult


def test_repair_summary_serializes_stages_and_remaining_issues():
    summary = RepairRunSummary(
        trade_date="2026-07-01",
        mode="repair",
        final_status=RepairStatus.DEGRADED,
        stages=[
            RepairStageResult(
                name="base_bars",
                checks_before=[
                    RepairCheckResult(
                        "minute5_bars",
                        RepairStatus.FAILED,
                        "minute5 missing",
                        blocker=True,
                    )
                ],
                actions=[
                    RepairActionResult(
                        "repair_minute5_bars",
                        RepairStatus.SUCCESS,
                        "minute5 repaired",
                    )
                ],
                checks_after=[
                    RepairCheckResult("minute5_bars", RepairStatus.SUCCESS, "ready")
                ],
                remaining_blockers=[],
            )
        ],
        remaining_blockers=[],
        remaining_non_blockers=["reports"],
        next_actions=["Generate reports for 2026-07-01"],
    )

    payload = summary.to_dict()

    assert payload["stages"][0]["name"] == "base_bars"
    assert payload["remaining_non_blockers"] == ["reports"]
    assert payload["next_actions"] == ["Generate reports for 2026-07-01"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_models.py -q
```

Expected: FAIL because `RepairStageResult` does not exist.

- [ ] **Step 3: Add the stage model**

Update `src/stock_research/eod_auto_repair_models.py`:

```python
@dataclass(frozen=True)
class RepairStageResult:
    name: str
    checks_before: list[RepairCheckResult] = field(default_factory=list)
    actions: list[RepairActionResult] = field(default_factory=list)
    checks_after: list[RepairCheckResult] = field(default_factory=list)
    remaining_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "checks_before": [check.to_dict() for check in self.checks_before],
            "actions": [action.to_dict() for action in self.actions],
            "checks_after": [check.to_dict() for check in self.checks_after],
            "remaining_blockers": self.remaining_blockers,
        }
```

Extend `RepairRunSummary`:

```python
@dataclass(frozen=True)
class RepairRunSummary:
    trade_date: str
    mode: str
    final_status: RepairStatus
    checks_before: list[RepairCheckResult] = field(default_factory=list)
    actions: list[RepairActionResult] = field(default_factory=list)
    checks_after: list[RepairCheckResult] = field(default_factory=list)
    stages: list[RepairStageResult] = field(default_factory=list)
    remaining_blockers: list[str] = field(default_factory=list)
    remaining_non_blockers: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "mode": self.mode,
            "final_status": self.final_status.value,
            "checks_before": [check.to_dict() for check in self.checks_before],
            "actions": [action.to_dict() for action in self.actions],
            "checks_after": [check.to_dict() for check in self.checks_after],
            "stages": [stage.to_dict() for stage in self.stages],
            "remaining_blockers": self.remaining_blockers,
            "remaining_non_blockers": self.remaining_non_blockers,
            "next_actions": self.next_actions,
        }
```

- [ ] **Step 4: Run model tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```bash
rtk git add src/stock_research/eod_auto_repair_models.py tests/test_eod_auto_repair_models.py
rtk git commit -m "feat: add staged auto repair summary model"
```

---

### Task 3: Isolate Action Exceptions And Always Write Reports

**Files:**
- Modify: `src/stock_research/eod_auto_repair.py`
- Modify: `tests/test_eod_auto_repair.py`

- [ ] **Step 1: Write the failing exception/report tests**

Append to `tests/test_eod_auto_repair.py`:

```python
def test_run_eod_auto_repair_records_action_exception_and_writes_report(tmp_path):
    def check_plan_builder(trade_date):
        results = [
            RepairCheckResult("strategy_publish", RepairStatus.FAILED, "missing", blocker=True),
            RepairCheckResult("strategy_publish", RepairStatus.FAILED, "still missing", blocker=True),
        ]

        def run_check():
            return results.pop(0)

        return [SimpleNamespace(name="strategy_publish", run=run_check)]

    def broken_action(trade_date, output_dir):
        raise RuntimeError("base data checks did not all pass")

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={"strategy_publish": broken_action},
        write_reports=True,
    )

    assert summary.final_status == RepairStatus.FAILED
    assert summary.actions[0].status == RepairStatus.FAILED
    assert "RuntimeError" in summary.actions[0].message
    assert (tmp_path / "run_summary.json").exists()
    assert (tmp_path / "run_report.md").exists()


def test_run_eod_auto_repair_writes_report_when_check_raises(tmp_path):
    def check_plan_builder(trade_date):
        def run_check():
            raise RuntimeError("database unavailable")

        return [SimpleNamespace(name="daily_bars", run=run_check)]

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
        write_reports=True,
    )

    assert summary.final_status == RepairStatus.FAILED
    assert summary.checks_before[0].name == "daily_bars"
    assert summary.checks_before[0].blocker is True
    assert "RuntimeError" in summary.checks_before[0].message
    assert (tmp_path / "run_summary.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py -q
```

Expected: FAIL because action/check exceptions still escape.

- [ ] **Step 3: Add safe execution helpers**

In `src/stock_research/eod_auto_repair.py`, add:

```python
def _safe_run_check(check) -> RepairCheckResult:
    try:
        return check.run()
    except Exception as exc:  # noqa: BLE001 - report must survive diagnostic failures.
        return RepairCheckResult(
            name=str(getattr(check, "name", "check_plan")),
            status=RepairStatus.FAILED,
            message=f"{type(exc).__name__}: {exc}",
            metrics={},
            blocker=True,
        )


def _safe_run_action(name: str, runner: ActionRunner, trade_date: str, output_dir: Path) -> RepairActionResult:
    try:
        return runner(trade_date, output_dir)
    except Exception as exc:  # noqa: BLE001 - action failures belong in the report.
        return RepairActionResult(
            name=name,
            status=RepairStatus.FAILED,
            message=f"{type(exc).__name__}: {exc}",
        )
```

Change check collection from:

```python
checks_before = [check.run() for check in check_plan_builder(trade_date)]
```

to:

```python
checks_before = [_safe_run_check(check) for check in check_plan_builder(trade_date)]
```

Change action execution from:

```python
actions.append(runner(trade_date, out))
```

to:

```python
actions.append(_safe_run_action(check.name, runner, trade_date, out))
```

Change recheck collection to use `_safe_run_check`.

- [ ] **Step 4: Make report writing unconditional inside the function**

Keep the public `write_reports` switch, but build `summary` before returning and write after summary creation. All safe errors are now data, so report writing must execute for check and action failures.

Add remaining issue helpers:

```python
def _remaining_blockers(checks: list[RepairCheckResult]) -> list[str]:
    return [check.name for check in checks if check.blocker and check.status != RepairStatus.SUCCESS]


def _remaining_non_blockers(checks: list[RepairCheckResult]) -> list[str]:
    return [
        check.name
        for check in checks
        if not check.blocker and check.status not in {RepairStatus.SUCCESS, RepairStatus.DEGRADED}
    ]


def _next_actions(checks: list[RepairCheckResult]) -> list[str]:
    blockers = _remaining_blockers(checks)
    if blockers:
        return [f"Resolve blocking checks: {', '.join(blockers)}"]
    non_blockers = _remaining_non_blockers(checks)
    if non_blockers:
        return [f"Review non-blocking gaps: {', '.join(non_blockers)}"]
    return []
```

Pass these fields into `RepairRunSummary`.

- [ ] **Step 5: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py tests/test_eod_auto_repair_models.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
rtk git add src/stock_research/eod_auto_repair.py tests/test_eod_auto_repair.py
rtk git commit -m "fix: preserve auto repair reports on failures"
```

---

### Task 4: Add Stage Graph And Prerequisite Gating

**Files:**
- Modify: `src/stock_research/eod_auto_repair.py`
- Modify: `tests/test_eod_auto_repair.py`

- [ ] **Step 1: Write failing staged-flow tests**

Append to `tests/test_eod_auto_repair.py`:

```python
def test_run_eod_auto_repair_runs_stages_in_dependency_order(tmp_path):
    calls = []
    check_state = {
        "minute5_bars": [RepairStatus.FAILED, RepairStatus.SUCCESS],
        "score_topn": [RepairStatus.FAILED, RepairStatus.SUCCESS],
        "watchlist": [RepairStatus.FAILED, RepairStatus.SUCCESS],
        "strategy_publish": [RepairStatus.FAILED, RepairStatus.SUCCESS],
    }

    def check_plan_builder(trade_date):
        checks = []
        for name in ["minute5_bars", "score_topn", "watchlist", "strategy_publish"]:
            def run_check(check_name=name):
                status = check_state[check_name][0]
                return RepairCheckResult(
                    check_name,
                    status,
                    "ready" if status == RepairStatus.SUCCESS else "missing",
                    blocker=status == RepairStatus.FAILED,
                )

            checks.append(SimpleNamespace(name=name, run=run_check))
        return checks

    def make_action(name):
        def action(trade_date, output_dir):
            calls.append(name)
            check_name = {
                "repair_minute5_bars": "minute5_bars",
                "repair_score_topn": "score_topn",
                "repair_watchlist": "watchlist",
                "repair_strategy_publish": "strategy_publish",
            }[name]
            check_state[check_name].pop(0)
            return RepairActionResult(name, RepairStatus.SUCCESS, "fixed")

        return action

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={
            "minute5_bars": make_action("repair_minute5_bars"),
            "score_topn": make_action("repair_score_topn"),
            "watchlist": make_action("repair_watchlist"),
            "strategy_publish": make_action("repair_strategy_publish"),
        },
    )

    assert calls == [
        "repair_minute5_bars",
        "repair_score_topn",
        "repair_watchlist",
        "repair_strategy_publish",
    ]
    assert summary.final_status == RepairStatus.SUCCESS
    assert [stage.name for stage in summary.stages] == [
        "base_bars",
        "scores_and_watchlists",
        "strategy_eod",
    ]


def test_run_eod_auto_repair_stops_downstream_stage_when_prerequisite_blocker_remains(tmp_path):
    calls = []

    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="minute5_bars",
                run=lambda: RepairCheckResult("minute5_bars", RepairStatus.FAILED, "missing", blocker=True),
            ),
            SimpleNamespace(
                name="score_topn",
                run=lambda: RepairCheckResult("score_topn", RepairStatus.FAILED, "missing", blocker=True),
            ),
        ]

    def minute_action(trade_date, output_dir):
        calls.append("repair_minute5_bars")
        return RepairActionResult("repair_minute5_bars", RepairStatus.FAILED, "still missing")

    def score_action(trade_date, output_dir):
        calls.append("repair_score_topn")
        return RepairActionResult("repair_score_topn", RepairStatus.SUCCESS, "fixed")

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={"minute5_bars": minute_action, "score_topn": score_action},
    )

    assert calls == ["repair_minute5_bars"]
    assert summary.final_status == RepairStatus.FAILED
    assert summary.remaining_blockers == ["minute5_bars", "score_topn"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py -q
```

Expected: FAIL because the current loop has no stage graph.

- [ ] **Step 3: Add stage definitions**

In `src/stock_research/eod_auto_repair.py`, add:

```python
STAGE_CHECKS: list[tuple[str, tuple[str, ...]]] = [
    ("base_bars", ("daily_bars", "minute5_bars")),
    ("features", ("technical_features", "lhb_source", "lhb_features")),
    ("scores_and_watchlists", ("score_topn", "watchlist")),
    ("market_monitor", ("market_monitor",)),
    ("strategy_eod", ("strategy_publish", "review_queue", "strategy_score_audit")),
    ("presentation", ("reports", "review_evidence_snapshots", "ops_health", "dashboard_surface_freshness")),
]


def _checks_by_name(checks: list[RepairCheckResult]) -> dict[str, RepairCheckResult]:
    return {check.name: check for check in checks}


def _stage_checks(checks: list[RepairCheckResult], names: tuple[str, ...]) -> list[RepairCheckResult]:
    by_name = _checks_by_name(checks)
    return [by_name[name] for name in names if name in by_name]


def _has_blocker(checks: list[RepairCheckResult]) -> bool:
    return any(check.blocker and check.status != RepairStatus.SUCCESS for check in checks)
```

- [ ] **Step 4: Change repair mode to stage-by-stage execution**

Inside `run_eod_auto_repair`, after the initial `checks_before`, use:

```python
current_checks = checks_before
stages: list[RepairStageResult] = []
actions: list[RepairActionResult] = []

if mode != "check":
    for stage_name, check_names in STAGE_CHECKS:
        before = _stage_checks(current_checks, check_names)
        if not before:
            continue
        stage_actions: list[RepairActionResult] = []
        if _has_blocker(before) or any(check.status != RepairStatus.SUCCESS for check in before):
            for check in before:
                if check.status == RepairStatus.SUCCESS:
                    continue
                runner = registry.get(check.name)
                if runner is None:
                    continue
                action = _safe_run_action(check.name, runner, trade_date, out)
                stage_actions.append(action)
                actions.append(action)
        current_checks = [_safe_run_check(check) for check in check_plan_builder(trade_date)]
        after = _stage_checks(current_checks, check_names)
        stages.append(
            RepairStageResult(
                name=stage_name,
                checks_before=before,
                actions=stage_actions,
                checks_after=after,
                remaining_blockers=_remaining_blockers(after),
            )
        )
        if _has_blocker(after):
            break

checks_after = current_checks if actions else checks_before
```

Preserve check mode behavior: check mode should not append stages.

- [ ] **Step 5: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
rtk git add src/stock_research/eod_auto_repair.py tests/test_eod_auto_repair.py
rtk git commit -m "feat: run auto repair by dependency stage"
```

---

### Task 5: Add Missing Repair Actions

**Files:**
- Modify: `src/stock_research/eod_auto_repair_actions.py`
- Modify: `src/stock_research/eod_auto_repair.py`
- Modify: `tests/test_eod_auto_repair_actions.py`
- Modify: `tests/test_eod_auto_repair.py`

- [ ] **Step 1: Write action tests for new wrappers**

Append to `tests/test_eod_auto_repair_actions.py`:

```python
from stock_research.eod_auto_repair_actions import (
    repair_generated_reports,
    repair_review_evidence_snapshots,
    repair_score_topn,
    repair_technical_features,
    repair_watchlist,
)


def test_repair_technical_features_passes_trade_date_to_runner():
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"stored_rows": 5187}

    result = repair_technical_features("2026-07-01", runner=runner)

    assert result.status == RepairStatus.SUCCESS
    assert captured["trade_date"] == "2026-07-01"
    assert captured["adjust_type"] == "hfq"
    assert result.metrics["stored_rows"] == 5187


def test_repair_score_topn_passes_manual_v1_to_runner():
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"score_rows": 5187}

    result = repair_score_topn("2026-07-01", output_dir="/tmp/out", runner=runner)

    assert result.status == RepairStatus.SUCCESS
    assert captured["trade_date"] == "2026-07-01"
    assert captured["score_version"] == "manual_v1"
    assert result.metrics["score_rows"] == 5187


def test_repair_watchlist_builds_default_and_diagnostics():
    calls = []

    def runner(**kwargs):
        calls.append(kwargs)
        return {"members": 50}

    result = repair_watchlist("2026-07-01", runner=runner)

    assert result.status == RepairStatus.SUCCESS
    assert [call["watchlist_id"] for call in calls] == ["default", "diagnostics"]
    assert result.metrics == {"default_rows": 50, "diagnostics_rows": 50}


def test_repair_generated_reports_wraps_runner_output():
    result = repair_generated_reports(
        "2026-07-01",
        runner=lambda **kwargs: {"generated_reports": 2, "output_dir": "/tmp/reports"},
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["generated_reports"] == 2
    assert result.artifact_paths == ["/tmp/reports"]


def test_repair_review_evidence_snapshots_wraps_runner_output():
    result = repair_review_evidence_snapshots(
        "2026-07-01",
        runner=lambda **kwargs: {"snapshot_rows": 28, "output_dir": "/tmp/snapshots"},
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["snapshot_rows"] == 28
    assert result.artifact_paths == ["/tmp/snapshots"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_actions.py -q
```

Expected: FAIL because the new action functions do not exist.

- [ ] **Step 3: Add new action wrappers**

Add to `src/stock_research/eod_auto_repair_actions.py`:

```python
def repair_technical_features(
    trade_date: str,
    *,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = runner(
        trade_date=trade_date,
        lookback_bars=260,
        adjust_type="hfq",
        build_strategy="latest_only",
    )
    return RepairActionResult(
        name="repair_technical_features",
        status=RepairStatus.SUCCESS,
        message="technical features rebuilt",
        metrics=dict(result or {}),
    )


def repair_score_topn(
    trade_date: str,
    *,
    output_dir: str | Path,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = runner(
        trade_date=trade_date,
        score_version="manual_v1",
        output_dir=output_dir,
    )
    return RepairActionResult(
        name="repair_score_topn",
        status=RepairStatus.SUCCESS,
        message="score topn rebuilt",
        metrics=dict(result or {}),
    )


def repair_watchlist(
    trade_date: str,
    *,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    default_result = runner(trade_date=trade_date, watchlist_id="default")
    diagnostics_result = runner(trade_date=trade_date, watchlist_id="diagnostics")
    return RepairActionResult(
        name="repair_watchlist",
        status=RepairStatus.SUCCESS,
        message="watchlists rebuilt",
        metrics={
            "default_rows": int(default_result.get("members") or default_result.get("row_count") or 0),
            "diagnostics_rows": int(diagnostics_result.get("members") or diagnostics_result.get("row_count") or 0),
        },
    )


def repair_generated_reports(
    trade_date: str,
    *,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = runner(trade_date=trade_date)
    output_dir = str(result.get("output_dir") or "")
    return RepairActionResult(
        name="repair_generated_reports",
        status=RepairStatus.SUCCESS,
        message="generated reports refreshed",
        metrics=dict(result or {}),
        artifact_paths=[output_dir] if output_dir else [],
    )


def repair_review_evidence_snapshots(
    trade_date: str,
    *,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = runner(trade_date=trade_date)
    output_dir = str(result.get("output_dir") or "")
    return RepairActionResult(
        name="repair_review_evidence_snapshots",
        status=RepairStatus.SUCCESS,
        message="review evidence snapshots refreshed",
        metrics=dict(result or {}),
        artifact_paths=[output_dir] if output_dir else [],
    )
```

- [ ] **Step 4: Wire default registry**

In `src/stock_research/eod_auto_repair.py`, update `build_default_action_registry` imports:

```python
from stock_research.eod_auto_repair_actions import (
    repair_generated_reports,
    repair_lhb_source_and_features,
    repair_market_monitor,
    repair_minute5_bars,
    repair_review_evidence_snapshots,
    repair_score_topn,
    repair_strategy_publish,
    repair_technical_features,
    repair_watchlist,
)
```

Add concrete action closures using existing project functions. Use the correct existing function names from the codebase when implementing; keep injected wrappers testable:

```python
def technical_features_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
    from stock_research.technical_feature_store import build_and_store_stock_technical_features_daily

    return repair_technical_features(trade_date, runner=build_and_store_stock_technical_features_daily)


def score_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
    from stock_research.daily_factor_pipeline import run_daily_factor_pipeline

    return repair_score_topn(trade_date, output_dir=output_dir, runner=run_daily_factor_pipeline)


def watchlist_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
    from stock_research.watchlist_builder import build_watchlist_for_dashboard

    return repair_watchlist(trade_date, runner=build_watchlist_for_dashboard)


def reports_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
    from stock_research.strategy_eod_publish import build_generated_reports

    return repair_generated_reports(trade_date, runner=build_generated_reports)


def snapshots_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
    from stock_research.review_evidence_snapshots import run_eod_review_evidence_snapshots

    return repair_review_evidence_snapshots(trade_date, runner=run_eod_review_evidence_snapshots)
```

Before writing this exact import block, verify the real function names with `rtk rg -n "def run_daily_factor|def build_watchlist|def build_generated|def run_eod_review" src/stock_research`. If a function name differs, adapt only the closure import, not the wrapper signatures.

Extend returned registry:

```python
return {
    "minute5_bars": minute_action,
    "technical_features": technical_features_action,
    "lhb_source": lhb_action,
    "lhb_features": lhb_action,
    "score_topn": score_action,
    "watchlist": watchlist_action,
    "market_monitor": market_monitor_action,
    "strategy_publish": strategy_action,
    "review_queue": strategy_action,
    "reports": reports_action,
    "review_evidence_snapshots": snapshots_action,
}
```

- [ ] **Step 5: Update registry test**

In `tests/test_eod_auto_repair.py`, extend `test_default_action_registry_contains_repairable_checks`:

```python
assert "score_topn" in registry
assert "watchlist" in registry
assert "reports" in registry
assert "review_evidence_snapshots" in registry
```

- [ ] **Step 6: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py tests/test_eod_auto_repair_actions.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
rtk git add src/stock_research/eod_auto_repair.py src/stock_research/eod_auto_repair_actions.py tests/test_eod_auto_repair.py tests/test_eod_auto_repair_actions.py
rtk git commit -m "feat: add missing eod repair actions"
```

---

### Task 6: Align Strategy Publish With Degraded Readiness

**Files:**
- Modify: `src/stock_research/strategy_eod_publish.py`
- Modify: `tests/test_strategy_eod_publish.py` or the existing strategy publish test file in this repo.
- Modify: `src/stock_research/eod_auto_repair_checks.py` if a shared helper is cleaner.

- [ ] **Step 1: Locate the strategy publish tests**

Run:

```bash
rtk rg -n "publish_strategy_eod|base data checks did not all pass|strategy_daily_eod" tests
```

Use the file that already covers `publish_strategy_eod`. If no direct file exists, create `tests/test_strategy_eod_publish.py`.

- [ ] **Step 2: Write failing tests for degraded base data**

Add tests shaped like:

```python
from datetime import datetime, timezone

from stock_research import strategy_eod_publish


def test_base_manifest_entries_marks_small_daily_gap_degraded_publishable(monkeypatch):
    def fake_load_base_check_rows(trade_date):
        return {
            "daily_bars": {
                "row_count": 15561,
                "asset_count": 5187,
                "latest_trade_date": trade_date,
                "missing_count": 66,
                "expected_count": 15627,
            },
            "technical_features": {
                "row_count": 5187,
                "asset_count": 5187,
                "latest_trade_date": trade_date,
            },
            "score_topn": {
                "row_count": 5187,
                "asset_count": 5187,
                "latest_trade_date": trade_date,
            },
            "lhb_features": {
                "row_count": 104,
                "asset_count": 104,
                "latest_trade_date": trade_date,
            },
        }

    monkeypatch.setattr(strategy_eod_publish, "_load_base_check_rows", fake_load_base_check_rows)

    entries = strategy_eod_publish._build_base_manifest_entries(
        run_id="run-1",
        trade_date="2026-07-01",
        started_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    daily = next(entry for entry in entries if entry["module"] == "daily_bars")
    assert daily["status"] == "partial"
    assert "degraded" in " ".join(daily["warnings"])
    assert strategy_eod_publish._base_entries_publishable(entries) is True


def test_base_manifest_entries_blocks_missing_score_topn(monkeypatch):
    def fake_load_base_check_rows(trade_date):
        return {
            "daily_bars": {"row_count": 5187, "asset_count": 5187, "latest_trade_date": trade_date},
            "technical_features": {"row_count": 5187, "asset_count": 5187, "latest_trade_date": trade_date},
            "score_topn": {"row_count": 0, "asset_count": 0, "latest_trade_date": ""},
            "lhb_features": {"row_count": 104, "asset_count": 104, "latest_trade_date": trade_date},
        }

    monkeypatch.setattr(strategy_eod_publish, "_load_base_check_rows", fake_load_base_check_rows)

    entries = strategy_eod_publish._build_base_manifest_entries(
        run_id="run-1",
        trade_date="2026-07-01",
        started_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    assert strategy_eod_publish._base_entries_publishable(entries) is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run the selected test file:

```bash
rtk .venv/bin/pytest tests/test_strategy_eod_publish.py -q
```

Expected: FAIL because `_base_entries_publishable` does not exist and all non-success entries are fatal.

- [ ] **Step 4: Implement shared publishable base gate**

In `src/stock_research/strategy_eod_publish.py`, add:

```python
PUBLISHABLE_BASE_STATUSES = {"success", "partial"}


def _base_entries_publishable(entries: list[dict[str, Any]]) -> bool:
    return all(str(entry.get("status") or "") in PUBLISHABLE_BASE_STATUSES for entry in entries)
```

In `_build_base_manifest_entries`, classify small daily bar gaps as `partial`:

```python
def _base_status_and_warnings(module: str, row: dict[str, Any], trade_date: str) -> tuple[str, list[str]]:
    row_count = int(row.get("row_count") or 0)
    latest_trade_date = str(row.get("latest_trade_date") or "")
    if row_count <= 0 or latest_trade_date != trade_date:
        return "unavailable", [f"{module} missing for {trade_date}"]
    if module == "daily_bars":
        expected = int(row.get("expected_count") or 0)
        missing = int(row.get("missing_count") or 0)
        if expected > 0 and missing > 0 and missing / expected <= 0.01:
            return "partial", [f"daily_bars degraded within tolerance: missing={missing} expected={expected}"]
    return "success", []
```

Use that helper in `_build_base_manifest_entries`.

In `publish_strategy_eod`, replace:

```python
if any(entry["status"] != "success" for entry in entries):
```

with:

```python
if not _base_entries_publishable(entries):
```

- [ ] **Step 5: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_strategy_eod_publish.py tests/test_eod_auto_repair.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
rtk git add src/stock_research/strategy_eod_publish.py tests/test_strategy_eod_publish.py
rtk git commit -m "fix: share publishable degraded readiness"
```

---

### Task 7: Improve Reports And Incident Regression

**Files:**
- Modify: `src/stock_research/eod_auto_repair.py`
- Modify: `tests/test_eod_auto_repair.py`
- Modify: `README.md`

- [ ] **Step 1: Write report content test**

Append to `tests/test_eod_auto_repair.py`:

```python
def test_run_report_contains_stage_blockers_actions_and_next_steps(tmp_path):
    def check_plan_builder(trade_date):
        return [
            SimpleNamespace(
                name="reports",
                run=lambda: RepairCheckResult("reports", RepairStatus.FAILED, "generated reports missing", blocker=False),
            )
        ]

    run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
        write_reports=True,
    )

    report = (tmp_path / "run_report.md").read_text()
    assert "Final status" in report
    assert "Remaining non-blockers" in report
    assert "reports" in report
    assert "Next actions" in report
```

- [ ] **Step 2: Write incident-flow regression test**

Append to `tests/test_eod_auto_repair.py`:

```python
def test_20260701_incident_flow_repairs_minute_score_watchlist_then_degrades_on_reports(tmp_path):
    state = {
        "minute5_bars": RepairStatus.FAILED,
        "score_topn": RepairStatus.FAILED,
        "watchlist": RepairStatus.FAILED,
        "strategy_publish": RepairStatus.FAILED,
        "reports": RepairStatus.FAILED,
    }
    blockers = {
        "minute5_bars": True,
        "score_topn": True,
        "watchlist": True,
        "strategy_publish": True,
        "reports": False,
    }
    calls = []

    def check_plan_builder(trade_date):
        checks = []
        for name in ["minute5_bars", "score_topn", "watchlist", "strategy_publish", "reports"]:
            def run_check(check_name=name):
                return RepairCheckResult(
                    check_name,
                    state[check_name],
                    "ready" if state[check_name] == RepairStatus.SUCCESS else "missing",
                    blocker=blockers[check_name],
                )

            checks.append(SimpleNamespace(name=name, run=run_check))
        return checks

    def action_for(check_name):
        def action(trade_date, output_dir):
            calls.append(check_name)
            if check_name != "reports":
                state[check_name] = RepairStatus.SUCCESS
            return RepairActionResult(f"repair_{check_name}", RepairStatus.SUCCESS, "ran")

        return action

    summary = run_eod_auto_repair(
        trade_date="2026-07-01",
        output_dir=tmp_path,
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={
            "minute5_bars": action_for("minute5_bars"),
            "score_topn": action_for("score_topn"),
            "watchlist": action_for("watchlist"),
            "strategy_publish": action_for("strategy_publish"),
            "reports": action_for("reports"),
        },
        write_reports=True,
    )

    assert calls[:4] == ["minute5_bars", "score_topn", "watchlist", "strategy_publish"]
    assert summary.final_status == RepairStatus.DEGRADED
    assert summary.remaining_blockers == []
    assert summary.remaining_non_blockers == ["reports"]
```

- [ ] **Step 3: Run tests to verify they fail if report is still too thin**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py -q
```

Expected: FAIL until report content and final non-blocking aggregation are complete.

- [ ] **Step 4: Improve `_write_summary_files`**

Update `src/stock_research/eod_auto_repair.py` report lines to include:

```python
lines = [
    f"# EOD Auto Repair Report {summary.trade_date}",
    "",
    f"- Mode: {summary.mode}",
    f"- Final status: {summary.final_status.value}",
    f"- Remaining blockers: {', '.join(summary.remaining_blockers) if summary.remaining_blockers else 'none'}",
    f"- Remaining non-blockers: {', '.join(summary.remaining_non_blockers) if summary.remaining_non_blockers else 'none'}",
    "",
    "## Stages",
]
for stage in summary.stages:
    lines.append(f"- {stage.name}: blockers={', '.join(stage.remaining_blockers) if stage.remaining_blockers else 'none'}")
    for action in stage.actions:
        lines.append(f"  - action {action.name}: {action.status.value} {action.message}")
lines.extend(["", "## Checks Before"])
```

Add a final section:

```python
lines.append("")
lines.append("## Next actions")
if summary.next_actions:
    lines.extend(f"- {item}" for item in summary.next_actions)
else:
    lines.append("- none")
```

- [ ] **Step 5: Update final status aggregation for non-blocking failures**

In `_final_status`, ensure non-blocking failed checks produce `DEGRADED` when no blockers remain:

```python
failed = [check for check in checks if check.status == RepairStatus.FAILED]
if failed:
    return RepairStatus.DEGRADED
```

This comes after blocker detection.

- [ ] **Step 6: Update README**

In `README.md`, replace the EOD Auto Repair section with:

```markdown
## EOD Auto Repair

Run diagnostics only:

```bash
rtk .venv/bin/python -m stock_research.eod_auto_repair \
  --trade-date YYYY-MM-DD \
  --output-dir outputs/research/eod_auto_repair/YYYY-MM-DD-check \
  --mode check
```

Run staged repair:

```bash
rtk .venv/bin/python -m stock_research.eod_auto_repair \
  --trade-date YYYY-MM-DD \
  --output-dir outputs/research/eod_auto_repair/YYYY-MM-DD \
  --mode repair
```

The repair command runs dependency stages in this order: base bars, features, scores/watchlists, market monitor, strategy EOD, presentation freshness. It stops before downstream stages when a blocker remains.

Important safety rule: Baostock minute repair is always single-worker. Do not bypass this in cron or manual runs.

Primary outputs:

- `outputs/research/eod_auto_repair/YYYY-MM-DD/run_summary.json`
- `outputs/research/eod_auto_repair/YYYY-MM-DD/run_report.md`
- `outputs/research/strategy_daily_eod/YYYY-MM-DD/review_queue_strategy_manifest.csv`
```

- [ ] **Step 7: Run focused verification**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py tests/test_eod_auto_repair_actions.py tests/test_eod_auto_repair_models.py tests/test_eod_auto_repair_scripts.py -q
rtk git diff --check
```

Expected: all tests PASS and diff check has no output.

- [ ] **Step 8: Commit**

Run:

```bash
rtk git add src/stock_research/eod_auto_repair.py tests/test_eod_auto_repair.py README.md
rtk git commit -m "docs: improve eod repair operator report"
```

---

## Final Verification

After all tasks are complete, run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py tests/test_eod_auto_repair_actions.py tests/test_eod_auto_repair_checks.py tests/test_eod_auto_repair_models.py tests/test_eod_auto_repair_scripts.py -q
rtk .venv/bin/pytest tests/test_strategy_eod_publish.py -q
rtk .venv/bin/python -m stock_research.eod_auto_repair --trade-date 2026-07-01 --output-dir /private/tmp/eod_auto_repair_20260701_check --mode check
rtk git diff --check
```

Expected:

- focused pytest commands pass
- `2026-07-01` check exits `0` and final status is `success` or `degraded`
- `git diff --check` exits `0`

## Self-Review

- Spec coverage: portable cron, always-write reports, exception isolation, staged dependency graph, missing action coverage, shared degraded readiness, and operator output are covered.
- Placeholder scan: no placeholder tokens are used.
- Type consistency: `RepairStageResult`, `RepairRunSummary.stages`, `remaining_blockers`, `remaining_non_blockers`, and `next_actions` are introduced before later tasks use them.
- Scope: the plan is one implementation stream and produces a working, testable auto repair hardening release.
