# Technical Feature Stage-1 Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit the technical-feature backfill path, make low-risk watchdog/scheduling fixes, and add offline benchmarking without changing feature formulas.

**Architecture:** Keep the technical indicator math unchanged and focus on orchestration boundaries. Push timeout and sleep behavior into explicit technical-feature watchdog interfaces, expose batch metrics for observability, and add a fake-data benchmark helper that exercises `compute_daily_technical_features()` and store-level loops without touching PostgreSQL.

**Tech Stack:** Python 3.14, pandas, numpy, argparse, pytest, launchd host scripts/plists.

---

### Task 1: Audit and codify watchdog behavior

**Files:**
- Modify: `tests/test_technical_feature_watchdog.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing watchdog tests**
Add tests covering timeout propagation, explicit sleep configuration, and extra metrics fields in the watchdog adapter result.

- [ ] **Step 2: Run targeted tests to verify failures**
Run: `pytest tests/test_technical_feature_watchdog.py -q`
Expected: FAIL because timeout/sleep/metrics are not yet implemented.

- [ ] **Step 3: Write failing CLI/host configuration tests**
Add assertions for `--sleep-between-runs-seconds` parsing and watchdog dispatch wiring.

- [ ] **Step 4: Run targeted CLI tests to verify failures**
Run: `pytest tests/test_factor_cli.py -q -k technical_feature`
Expected: FAIL on the new sleep option expectations.

### Task 2: Implement low-risk watchdog scheduling fixes

**Files:**
- Modify: `src/stock_research/technical_feature_watchdog.py`
- Modify: `src/stock_research/technical_feature_backfill.py`
- Modify: `src/stock_research/cli.py`
- Modify: `scripts/run_technical_feature_backfill_watchdog_host.sh`
- Modify: `deploy/launchd/com.stockresearch.technical-feature-backfill-watchdog.plist`

- [ ] **Step 1: Thread timeout and metrics through the adapter**
Pass `run_timeout_seconds` into the technical-feature execution path instead of discarding it, and return batch metadata such as start/end date, batch size, compute seconds, rows written, days/hour, and rows/hour.

- [ ] **Step 2: Add explicit sleep configuration**
Introduce `sleep_between_runs_seconds` in the technical-feature watchdog CLI/entrypoint and surface it in logs/config. Preserve current behavior by keeping the launchd interval at 1800 seconds unless explicitly changed.

- [ ] **Step 3: Emit stable metrics lines**
Ensure the adapter produces key/value lines for batch/date/worker/sleep/throughput fields so host logs and Feishu messages can expose them without schema changes.

- [ ] **Step 4: Run focused tests**
Run: `pytest tests/test_technical_feature_watchdog.py tests/test_factor_cli.py -q`
Expected: PASS.

### Task 3: Add offline benchmark/profiling utility

**Files:**
- Create: `src/stock_research/technical_feature_benchmark.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_technical_feature_benchmark.py`

- [ ] **Step 1: Write failing benchmark tests**
Cover fake-data execution, JSON-serializable output, and required fields: `total_seconds`, `per_asset_seconds`, `rows_per_second`, `asset_count`, `bar_count`, `indicator_columns`.

- [ ] **Step 2: Run benchmark tests to verify failures**
Run: `pytest tests/test_technical_feature_benchmark.py -q`
Expected: FAIL because the module/CLI hook does not exist yet.

- [ ] **Step 3: Implement benchmark helper and optional CLI hook**
Provide a small synthetic bar generator and benchmark runner that measures the compute function and a store-style per-asset loop without database access.

- [ ] **Step 4: Run benchmark and CLI tests**
Run: `pytest tests/test_technical_feature_benchmark.py tests/test_factor_cli.py -q -k technical_feature`
Expected: PASS.

### Task 4: Document the stage-1 performance plan and verify no formula changes

**Files:**
- Create: `docs/quant_system/10_technical_feature_performance_plan.md`
- Modify: `tests/test_technical_features.py` (only if a regression guard is needed)

- [ ] **Step 1: Document current state, bottlenecks, stage-1 fixes, and later optimization options**
Include the confirmed 30-minute gap source, timeout fix, benchmark utility, and next-phase algorithm/vectorization ideas.

- [ ] **Step 2: Run technical feature regression tests**
Run: `pytest tests/test_technical_features.py tests/test_technical_feature_store.py tests/test_technical_feature_backfill.py -q`
Expected: PASS, confirming no indicator formula changes.

- [ ] **Step 3: Run final focused verification and inspect worktree**
Run: `pytest tests/test_technical_feature_watchdog.py tests/test_technical_feature_benchmark.py tests/test_factor_cli.py tests/test_technical_features.py tests/test_technical_feature_store.py tests/test_technical_feature_backfill.py -q`
Expected: PASS.

Run: `git status --short`
Expected: only intended files changed.
