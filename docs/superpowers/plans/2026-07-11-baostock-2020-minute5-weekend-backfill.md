# BaoStock 2020 Minute5 Weekend Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start and supervise a quota-bounded, resumable completion run for all remaining 2020 raw 5-minute BaoStock jobs while deriving qfq locally.

**Architecture:** Use the existing dedicated 2020 runner without changing production code. Perform authoritative preflight checks, reserve at most the observed 28,667 pending raw requests in the quota ledger, launch one detached serial process with a timestamped log, and verify early progress before handing the long run to ongoing monitoring.

**Tech Stack:** Python 3.14, PostgreSQL, BaoStock, Bash/nohup, pytest.

---

## File Map

- Execute `scripts/run_baostock_2020_minute5_raw_derive_backfill_today.py`: existing quota-aware raw backfill and local qfq derivation.
- Read `logs/baostock_minute_request_quota.json`: daily allocation/consumption ledger.
- Create one timestamped runtime log matching `logs/baostock_2020_minute5_backfill_20260711_*.log`.
- Create runtime PID file `logs/baostock_2020_minute5_backfill.pid`.
- Create runtime log-path file `logs/baostock_2020_minute5_backfill.logpath`.
- Update `docs/superpowers/specs/2026-07-11-baostock-2020-minute5-weekend-backfill-design.md`: record operational status after launch or completion.

No production source change is planned.

### Task 1: Preflight Safety and Regression Verification

**Files:**
- Read: `scripts/run_baostock_2020_minute5_raw_derive_backfill_today.py`
- Test: `tests/test_baostock_minute_backfill_watchdog.py`
- Test: `tests/test_minute_backfill.py`
- Test: `tests/test_minute_backfill_adapter.py`

- [ ] **Step 1: Verify the quota and backfill implementations**

Run:

```bash
rtk .venv/bin/pytest \
  tests/test_baostock_minute_backfill_watchdog.py \
  tests/test_minute_backfill.py \
  tests/test_minute_backfill_adapter.py \
  -q --disable-warnings
```

Expected: all selected tests pass.

- [ ] **Step 2: Confirm no competing minute process**

Run:

```bash
rtk ps aux | rtk rg 'minute_backfill|run_baostock_2020'
rtk launchctl list | rtk rg 'minute-backfill|baostock'
```

Expected: no active matching process or watchdog.

- [ ] **Step 3: Re-read exact pending counts**

Run:

```bash
rtk .venv/bin/python -c "from stock_research.minute_backfill import load_backfill_status_rows,summarize_backfill_status; s='2020-01-01'; e='2020-12-31'; print('raw',summarize_backfill_status(load_backfill_status_rows(start_date=s,end_date=e,freq='5min',adjust_types=['raw']))); print('qfq',summarize_backfill_status(load_backfill_status_rows(start_date=s,end_date=e,freq='5min',adjust_types=['qfq'])))"
```

Expected immediately before launch: raw pending is no more than 28,667, failed and running are zero; qfq pending is no more than 28,668.

- [ ] **Step 4: Confirm today's conservative budget**

Run:

```bash
rtk .venv/bin/python -c "from stock_research.baostock_minute_backfill_watchdog import *; n=load_active_baostock_asset_count(); print(calculate_baostock_minute_budget(active_asset_count=n,today_adjust_types=['raw']))"
rtk cat logs/baostock_minute_request_quota.json
```

Expected: `backfill_request_budget=40245`, with no existing 2026-07-11 consumption or active reservation.

### Task 2: Launch the Detached Completion Run

**Files:**
- Execute: `scripts/run_baostock_2020_minute5_raw_derive_backfill_today.py`
- Create: one file matching `logs/baostock_2020_minute5_backfill_20260711_*.log`
- Create: `logs/baostock_2020_minute5_backfill.pid`
- Create: `logs/baostock_2020_minute5_backfill.logpath`

- [ ] **Step 1: Confirm the fixed request ceiling**

Use `REQUESTED_REQUESTS=28667`. If fewer jobs remain at claim time, only available jobs are attempted and the finalizer releases the unused reservation.

- [ ] **Step 2: Launch one detached unbuffered process**

```bash
rtk zsh -lc 'ts="$(date +%Y%m%d_%H%M%S)"; log="logs/baostock_2020_minute5_backfill_20260711_${ts}.log"; nohup env BACKFILL_START_DATE=2020-01-01 BACKFILL_END_DATE=2020-12-31 QUOTA_DAY=2026-07-11 REQUESTED_REQUESTS=28667 REQUEST_LEDGER_PATH=logs/baostock_minute_request_quota.json .venv/bin/python -u scripts/run_baostock_2020_minute5_raw_derive_backfill_today.py >"$log" 2>&1 & pid=$!; echo "$pid" > logs/baostock_2020_minute5_backfill.pid; echo "$log" > logs/baostock_2020_minute5_backfill.logpath; echo "pid=$pid log=$log"'
```

Expected: one PID and one timestamped log path are printed.

- [ ] **Step 3: Verify process ownership and allocation**

Run:

```bash
rtk zsh -lc 'pid="$(<logs/baostock_2020_minute5_backfill.pid)"; ps -p "$pid" -o pid,etime,command'
rtk zsh -lc 'log="$(<logs/baostock_2020_minute5_backfill.logpath)"; tail -n 40 "$log"'
rtk cat logs/baostock_minute_request_quota.json
```

Expected: the process is alive; the log contains budget, allocation, and before-status records; today's active reservation equals the allocated request count.

### Task 3: Verify Early Raw/QFQ Progress

**Files:**
- Read: timestamped runtime log.
- Read: PostgreSQL backfill status.

- [ ] **Step 1: Wait for at least one 50-job progress checkpoint**

Poll the log without changing process state:

```bash
rtk zsh -lc 'log="$(<logs/baostock_2020_minute5_backfill.logpath)"; rg "minute5_2020_raw_backfill_today|baostock_2020_minute5_backfill" "$log" | tail -n 30'
```

Expected: progress shows at least 50 attempted jobs and no accumulating failures.

- [ ] **Step 2: Confirm both raw and qfq success counts increase**

Re-run the Task 1 status command and compare with the recorded baseline.

Expected: raw success increases; qfq success increases by the corresponding locally derived jobs; raw remote attempts alone consume quota.

- [ ] **Step 3: Check stop conditions**

Run:

```bash
rtk zsh -lc 'log="$(<logs/baostock_2020_minute5_backfill.logpath)"; rg -n "黑名单|daily.limit|quota|login failed|failed=[1-9]|Traceback|database" "$log"'
```

Expected: no blacklist, quota-limit, authentication, traceback, or database-write failure.

If a stop condition appears, send TERM to the recorded PID and verify the quota finalizer releases the reservation.

### Task 4: Long-Run Monitoring and Completion Audit

**Files:**
- Read: runtime log, quota ledger, PostgreSQL status.

- [ ] **Step 1: Monitor every 5–15 minutes while active**

Check PID, latest progress, failure patterns, and ledger consumption. Do not start a second runner while the PID is active.

- [ ] **Step 2: Capture terminal result**

Expected terminal log fields:

```text
baostock_2020_minute5_backfill|finalized_quota|...
baostock_2020_minute5_backfill|run_result|...
baostock_2020_minute5_backfill|after_raw|...
baostock_2020_minute5_backfill|after_qfq|...
```

- [ ] **Step 3: Audit final job state**

Expected: raw and qfq pending are zero or an exact retry list is recorded; running is zero; the ledger active reservation is zero.

- [ ] **Step 4: Audit database coverage**

Verify all 243 trading days are covered and sample/full aggregation confirms expected 5-minute session boundaries and bar-count quality for raw and qfq.

- [ ] **Step 5: Mark design status with evidence**

Update the design status to either `Running` with PID/log/progress evidence or `Completed and verified` with final counts. Commit only the design/plan status changes if needed; runtime logs and PID files remain untracked operational artifacts.
