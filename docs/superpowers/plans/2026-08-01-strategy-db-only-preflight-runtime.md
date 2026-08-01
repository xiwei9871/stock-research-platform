# Strategy DB-Only Preflight and Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make strategy runs database-only, fail closed on missing inputs with a separate backfill request, and publish auditable preflight/runtime metadata within a 60-minute budget.

**Architecture:** Add a small shared policy module for source enforcement, gap records, atomic gap artifacts, and runtime budgets. Add a consumer-specific preflight that runs after PIT universe construction and before scoring. Keep normal V1/V2 publication unchanged; use a separate blocked artifact set for missing data or runtime timeout.

**Tech Stack:** Python 3.12, dataclasses, pandas, JSON/Markdown artifacts, pytest, existing consumer CLI and atomic publication helpers.

---

## File structure

- Create `src/stock_research/strategy_data_policy.py`: DB-only policy constant, gap dataclass, runtime budget, deterministic gap request serialization.
- Create `src/stock_research/consumer_oversold/preflight.py`: consumer PIT frame coverage checks and gap construction.
- Modify `src/stock_research/consumer_oversold/pipeline.py`: run preflight before scoring, add stage timings/source policy, and return blocked diagnostics without normal ranking artifacts.
- Modify `src/stock_research/consumer_oversold/reporting.py`: write blocked data-gap/timeout artifacts without touching a previous `current` release.
- Modify `src/stock_research/cli.py`: accept blocked statuses and print blocked artifact paths without weakening normal path validation.
- Create `tests/test_strategy_data_policy.py`: shared policy, gap, runtime, and serialization tests.
- Create `tests/test_consumer_oversold_preflight.py`: complete/missing/short-history coverage tests.
- Modify `tests/test_consumer_oversold_pipeline.py`: DB-only guard, blocked runner, timing metadata, and unchanged normal path tests.
- Modify `tests/test_consumer_oversold_cli.py`: blocked machine-line tests and normal dispatch compatibility.

### Task 1: Add the shared DB-only policy and runtime primitives

**Files:**
- Create: `src/stock_research/strategy_data_policy.py`
- Create: `tests/test_strategy_data_policy.py`

- [x] **Step 1: Write failing tests**

```python
def test_db_only_policy_rejects_external_source_attempt():
    with pytest.raises(ValueError, match="db_only"):
        assert_db_only_source("baostock")


def test_gap_request_is_deterministic_and_contains_strategy_context(tmp_path):
    request = write_backfill_request(
        tmp_path,
        strategy="consumer_oversold_weekly",
        trade_date="2026-07-29",
        ranking_version="v2",
        gaps=[DataGap("daily_bars", "A", "2026-07-29", "2026-07-29", 1, 0, "missing")],
    )
    payload = json.loads(request.read_text())
    assert payload["data_source_policy"] == "db_only"
    assert payload["gaps"][0]["dataset"] == "daily_bars"


def test_runtime_budget_records_stages_and_raises_after_deadline(monkeypatch):
    budget = StrategyRuntimeBudget(timeout_seconds=1.0)
    budget.start()
    budget.begin_stage("market")
    budget.end_stage("market")
    monkeypatch.setattr("stock_research.strategy_data_policy.monotonic", lambda: budget.started_at + 2.0)
    with pytest.raises(StrategyRuntimeTimeout, match="3600|runtime budget"):
        budget.checkpoint("scoring")
```

- [x] **Step 2: Run tests and confirm the intended missing-symbol failures**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_data_policy.py -q`

Expected: FAIL because the policy module and its public types do not exist.

- [x] **Step 3: Implement the minimal primitives**

```python
DB_ONLY = "db_only"

@dataclass(frozen=True)
class DataGap:
    dataset: str
    asset_id: str
    start_date: str | None
    end_date: str | None
    expected_rows: int
    actual_rows: int
    reason: str

class StrategyRuntimeTimeout(RuntimeError):
    pass

def assert_db_only_source(source: str) -> None:
    if str(source or "").strip().casefold() not in {"", DB_ONLY, "database"}:
        raise ValueError("strategy data policy db_only rejects external source")
```

`StrategyRuntimeBudget` stores `started_at`, `stage_timings_seconds`, and `timeout_seconds`; `checkpoint(stage)` raises `StrategyRuntimeTimeout` when `monotonic() - started_at > timeout_seconds`. `write_backfill_request()` sorts gaps by `(dataset, asset_id, start_date, end_date, reason)`, writes `consumer_oversold_backfill_request.json` with UTF-8 JSON, and fsyncs through the existing atomic-write convention.

- [x] **Step 4: Run the shared tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_data_policy.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/stock_research/strategy_data_policy.py tests/test_strategy_data_policy.py
git commit -m "feat: add db-only strategy runtime contract"
```

### Task 2: Add consumer PIT preflight

**Files:**
- Create: `src/stock_research/consumer_oversold/preflight.py`
- Create: `tests/test_consumer_oversold_preflight.py`

- [x] **Step 1: Write failing tests**

```python
def test_complete_consumer_frames_pass_preflight():
    result = run_consumer_preflight(
        included=_included("A"),
        bars=_bars("A", 504),
        share_capacity=_shares("A"),
        finance=_finance("A"),
        valuation_history=_valuation("A"),
        trade_date="2026-07-29",
    )
    assert result.status == "passed"
    assert result.gaps == ()


@pytest.mark.parametrize("frame_name", ["bars", "share_capacity", "finance", "valuation_history"])
def test_missing_required_frame_blocks_and_reports_asset(frame_name):
    frames = _complete_frames("A")
    frames[frame_name] = frames[frame_name].iloc[0:0]
    result = run_consumer_preflight(**frames, trade_date="2026-07-29")
    assert result.status == "blocked_missing_data"
    assert result.gaps[0].asset_id == "A"
    assert result.gaps[0].dataset


def test_new_listing_short_history_is_not_reported_as_backfill_gap():
    result = run_consumer_preflight(
        included=_included("NEW", list_date="2026-07-01"),
        bars=_bars("NEW", 20),
        share_capacity=_shares("NEW"),
        finance=_finance("NEW"),
        valuation_history=_valuation("NEW"),
        trade_date="2026-07-29",
    )
    assert result.status == "passed"
```

- [x] **Step 2: Run the preflight tests and confirm failure**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_preflight.py -q`

Expected: FAIL because `run_consumer_preflight` is undefined.

- [x] **Step 3: Implement coverage checks**

`run_consumer_preflight()` normalizes asset IDs and checks, per included asset:

- daily bars have `asset_id`, `trade_date`, `close`, and at least `min(504, available sessions since list_date)` rows through the cutoff;
- share capacity has finite positive `float_share` and `total_share`;
- finance has at least one row with non-null report/announcement dates not after the cutoff;
- valuation history has at least one row with `valuation_date <= trade_date`.

Return `PreflightResult(status, gaps, checked_assets, checked_datasets)`. A short history is acceptable only when `list_date` is recent enough to explain it; an old asset with no current bar or missing required fundamentals produces a `DataGap`.

- [x] **Step 4: Run the preflight tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_preflight.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/stock_research/consumer_oversold/preflight.py tests/test_consumer_oversold_preflight.py
git commit -m "feat: preflight consumer database coverage"
```

### Task 3: Integrate preflight, timing, and timeout into the runner

**Files:**
- Modify: `src/stock_research/consumer_oversold/pipeline.py`
- Modify: `tests/test_consumer_oversold_pipeline.py`

- [x] **Step 1: Write failing integration tests**

```python
def test_runner_blocks_missing_market_data_and_writes_gap_request(monkeypatch, tmp_path):
    frames, evidence, _ = _frames()
    frames["bars"] = frames["bars"].iloc[0:0]
    _patch_runner_loaders(monkeypatch, frames)
    evidence_path = tmp_path / "evidence.csv"
    evidence.to_csv(evidence_path, index=False)
    result = run_consumer_oversold_weekly(
        trade_date=TRADE_DATE,
        evidence_path=evidence_path,
        output_dir=tmp_path / "out",
        service="test-service",
    )
    assert result["publication_status"] == "blocked_missing_data"
    assert Path(result["paths"]["backfill_request"]).is_file()
    assert not Path(result["paths"]["top20"]).exists()


def test_runner_records_db_only_policy_and_stage_timings(monkeypatch, tmp_path):
    frames, evidence, _ = _frames()
    _patch_runner_loaders(monkeypatch, frames)
    evidence_path = tmp_path / "evidence.csv"
    evidence.to_csv(evidence_path, index=False)
    result = run_consumer_oversold_weekly(
        trade_date=TRADE_DATE,
        evidence_path=evidence_path,
        output_dir=tmp_path / "out",
        service="test-service",
    )
    assert result["coverage"]["data_source_policy"] == "db_only"
    assert result["coverage"]["preflight_status"] == "passed"
    assert result["coverage"]["runtime_seconds"] >= 0.0
    assert result["coverage"]["stage_timings_seconds"]["preflight"] >= 0.0
```

- [x] **Step 2: Run the focused tests and verify red**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_pipeline.py -q -k 'gap_request or stage_timings'`

Expected: FAIL because the runner currently scores empty data and does not expose runtime metadata.

- [x] **Step 3: Integrate the minimal runner changes**

In `run_consumer_oversold_weekly()`:

1. Instantiate `StrategyRuntimeBudget(timeout_seconds=3600.0)` and call `start()`.
2. Wrap each existing loader/derivation/scoring/publishing block with `begin_stage()`/`end_stage()` and `checkpoint()`.
3. Build the PIT universe immediately after the universe loader, then run `run_consumer_preflight()` after all required frames are loaded.
4. On blocked preflight, call `write_consumer_oversold_data_gap_artifacts()` and return its payload without calling `build_consumer_oversold_weekly_from_frames()`.
5. On success, add `data_source_policy`, `preflight_status`, `runtime_budget_seconds`, `runtime_seconds`, and `stage_timings_seconds` to `coverage` before publication.
6. Catch `StrategyRuntimeTimeout` only around the top-level runner boundary, write timeout diagnostics, and return `publication_status="runtime_timeout"` without ranking files.

Normal frames and rank ordering remain untouched; only the boundary behavior and coverage metadata change.

- [x] **Step 4: Run all consumer pipeline tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_pipeline.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/stock_research/consumer_oversold/pipeline.py tests/test_consumer_oversold_pipeline.py
git commit -m "feat: enforce consumer db-only preflight and runtime budget"
```

### Task 4: Publish blocked diagnostics and update CLI reporting

**Files:**
- Modify: `src/stock_research/consumer_oversold/reporting.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_consumer_oversold_cli.py`

- [x] **Step 1: Write failing CLI/artifact tests**

```python
def test_blocked_result_prints_only_gap_artifacts(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_run_consumer_oversold_weekly", lambda **_: {
        "paths": {
            "coverage": "/tmp/gap/coverage.json",
            "backfill_request": "/tmp/gap/backfill.json",
            "report": "/tmp/gap/report.md",
        },
        "top20": [], "reserve": [], "preaudit": [],
        "as_of_trade_date": "2026-07-29",
        "date_mode": "explicit_backtest",
        "publication_status": "blocked_missing_data",
        "coverage": {"ranking_version": "v1", "publication_status": "blocked_missing_data"},
    })
    cli.main_for_args(
        [
            "consumer-oversold-weekly",
            "--trade-date",
            "2026-07-29",
            "--evidence-path",
            "/tmp/gap/evidence.csv",
            "--output-dir",
            "/tmp/gap",
        ]
    )
    assert "blocked_missing_data" in capsys.readouterr().out
```

- [x] **Step 2: Run the test and confirm red**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_cli.py -q -k blocked`

Expected: FAIL because the CLI only accepts normal publication statuses and fixed normal path keys.

- [x] **Step 3: Implement blocked artifact publication**

Add `write_consumer_oversold_data_gap_artifacts()` that writes three files under a unique diagnostic directory below `output_dir`, never replacing `output_dir/current`:

- `consumer_oversold_data_gap_coverage.json`
- `consumer_oversold_backfill_request.json`
- `consumer_oversold_data_gap_report.md`

Extend `_consumer_oversold_machine_lines()` with a blocked branch that validates exactly `coverage`, `backfill_request`, and `report`, accepts `blocked_missing_data` and `runtime_timeout`, and prints the status. Leave the existing normal path-key validation and statuses unchanged.

- [x] **Step 4: Run focused CLI and reporting tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_cli.py tests/test_consumer_oversold_reporting.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/stock_research/consumer_oversold/reporting.py src/stock_research/cli.py tests/test_consumer_oversold_cli.py
git commit -m "feat: publish and report blocked strategy data gaps"
```

### Task 5: Verify performance and regressions

**Files:**
- Modify: none unless verification exposes a regression.

- [x] **Step 1: Run the full consumer-focused suite**

Run: `rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_*.py tests/test_strategy_data_policy.py -q`

Observed: 254 consumer/policy tests passed; only the unrelated repository-wide suite has remaining environment/data fixture failures.

- [x] **Step 2: Run the frozen V2 smoke generation against DB-only inputs**

Run the existing `consumer-oversold-weekly --trade-date 2026-07-27 --ranking-version v2` command with the sealed evidence path and a temporary output directory. Confirmed `publication_status=ready`, `data_source_policy=db_only`, and the process used only the DB loaders.

- [x] **Step 3: Benchmark runtime and inspect stage timings**

Run the existing 2026-07-27 V2 generation under `/usr/bin/time -p`; observed `real 146.95s`, and persisted coverage contains non-negative timings for every declared stage, including `preflight=0.85s`.

- [ ] **Step 4: Run the repository regression suite**

Run: `rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest -q`

Observed: 5,508 passed, 23 skipped, 83 failures in unrelated generated-data/environment checks (missing `.venv` path, stale fixture row counts, absent `/Users/xiwei/.openclaw/cron/jobs.json`, and other pre-existing artifact assertions). No consumer/policy test failed.

- [x] **Step 5: Review the diff and commit any verification-only fixes**

Run: `rtk git status --short && rtk git diff --check && rtk git log -5 --oneline`. Do not claim completion until the focused suite, smoke run, and regression suite outputs have been read and match the acceptance criteria.
