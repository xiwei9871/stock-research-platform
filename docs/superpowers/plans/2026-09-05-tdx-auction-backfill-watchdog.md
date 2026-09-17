# TDX Auction Backfill Watchdog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Use TongDaXin (TDX) historical 09:25 opening-match data to fill `market.stock_auction_bar` for every open trading date from 2018-02-14 through 2024-12-31, with resumable watchdog execution and one Feishu report whenever a calendar month becomes complete.

**Architecture:** Add a versioned `eltdx` adapter that converts TDX opening-match ticks into raw staging and canonical `source='tdx'` rows without overwriting existing Tushare rows. Store one daily task in the existing ingest control plane, let a watchdog claim/retry tasks, and persist a small local ledger so monthly Feishu notifications are idempotent.

**Tech Stack:** Python 3, `eltdx` TDX protocol client, PostgreSQL/psycopg, existing `ingest.backfill_task` watchdog framework, pytest, launchd, OpenClaw Feishu sender.

---

### Task 1: Define the TDX data contract and dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/stock_research/schema.py`
- Create: `tests/test_tdx_auction_schema.py`

- [x] **Step 1: Write failing schema/contract tests** for the `eltdx` dependency, `staging.tdx_stock_auction_bar`, and the canonical source check accepting both `tushare` and `tdx`.
- [x] **Step 2: Run the focused tests and confirm they fail because the TDX schema/adapter is absent.**
- [x] **Step 3: Add the pinned `eltdx==3.1.3` dependency and idempotent schema DDL, including raw payload/provenance and `order_count`; update compatibility migration for an existing database.
- [x] **Step 4: Run the focused tests and the schema apply smoke test.**

### Task 2: Implement pure TDX conversion and daily persistence

**Files:**
- Create: `src/stock_research/tdx_auction_backfill.py`
- Create: `tests/test_tdx_auction_backfill.py`

- [x] **Step 1: Write failing tests** for exchange-code conversion, 09:25 tick normalization (volume remains in hands and amount is `price * volume * 100`), safe missing/error classification, daily universe selection, and idempotent row construction.
- [x] **Step 2: Run the focused tests and confirm the expected missing-symbol failures.**
- [x] **Step 3: Implement the minimal adapter:** map `SH/SZ/BJ` symbols to TDX codes, query `opening_match_history`, retry individual symbols, write TDX raw rows plus canonical `source='tdx'` rows, and return requested/matched/missing/failed counts.
- [x] **Step 4: Run focused tests, including a fake TDX client, and verify they pass.**

### Task 3: Add the resumable watchdog and monthly Feishu reporting

**Files:**
- Create: `src/stock_research/tdx_auction_watchdog.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_tdx_auction_watchdog.py`

- [x] **Step 1: Write failing tests** for daily task initialization, stale-task reset, claimed-task execution, contiguous frontier calculation, month-completion detection, and idempotent report-ledger behavior.
- [x] **Step 2: Run the focused tests and confirm the watchdog command/adapter is missing.**
- [x] **Step 3: Implement the adapter and CLI command `tdx-auction-backfill-watchdog` with configurable dates, max jobs, TDX hosts, workers, retries, stale timeout, and Feishu target; report newly completed months only.
- [x] **Step 4: Run focused watchdog tests and a `--dry-run` CLI smoke test.**

### Task 4: Add the host runner and launchd schedule

**Files:**
- Create: `scripts/run_tdx_auction_backfill_watchdog_host.sh`
- Create: `deploy/launchd/com.stockresearch.tdx-auction-backfill-watchdog.plist`
- Create: `tests/test_tdx_auction_host_runner.py`

- [x] **Step 1: Write a failing shell-contract test** for lock acquisition, environment defaults, log redirection, and forwarding the date range to the CLI.
- [x] **Step 2: Run it and confirm the host runner/plist are absent.**
- [x] **Step 3: Add the locked host runner and a one-minute launchd retry interval; process four daily tasks per invocation and keep all runtime settings overridable by environment variables.
- [x] **Step 4: Run the shell-contract test and `bash -n`; install/bootstrap the job only after the dry run passes.**

### Task 5: Run staged production verification and begin the backfill

**Files:**
- Modify: `outputs/research/tdx_auction_backfill_watchdog/reported_months.json` (runtime ledger only)
- Modify: runtime PostgreSQL tables through the existing schema/backfill command

- [x] **Step 1: Apply the schema and run a single known-date TDX smoke fetch for `000001.SZ` on 2018-02-14, checking the 09:25 price, volume, order count, and raw provenance.
- [x] **Step 2: Run the watchdog with one daily task and `--report-dry-run`, then verify task status, canonical `source='tdx'`, and no Tushare-row overwrite.
- [x] **Step 3: Start the launchd-backed watchdog for the full 2018-02-14–2024-12-31 range and capture the initial status/log path.
- [x] **Step 4: Run fresh database, watchdog, and shell verification commands; report actual completed dates/months, failures, and the next resumable frontier.**

**Runtime handoff:** launchd label `com.stockresearch.tdx-auction-backfill-watchdog` is loaded with a 60-second interval, `max_jobs=4`, and four TDX server slots across a four-endpoint failover pool. The universe query now limits requests to symbols with positive raw daily volume and records currently inactive historical symbols as an explicit exclusion metric. Deterministic `invalid historical ticks payload` responses stop retrying immediately and are classified as unsupported payloads. PostgreSQL task state remains the source of truth, so the process resumes safely after every run.

**Incident finding (2026-09-06):** the observed 2018-03 completion time was dominated by the old `max_jobs=1` plus 900-second launchd interval (roughly 3.5 minutes of TDX work followed by up to 15 minutes idle per day). The 242 reported request errors were 11 fixed currently-inactive symbols repeated across 22 days; all reproduced as the same malformed TDX `0x0fc6` payload on multiple hosts. They are excluded from normal requests and counted separately because TDX does not expose recoverable historical ticks for those symbols.

**Incident remediation (2026-09-06):** the scheduler now runs four dates per invocation every 60 seconds with four TDX slots. A live batch completed four dates in 3m37s with `failed_symbols=0`; the next batch also completed four dates in 4m07s with `failed_symbols=0`. Ten pre-fix dates (110 symbol-level errors) were reclassified to `unsupported_payload` in task metadata without changing canonical rows, and a Feishu correction was sent for the affected February/April summaries. The launchd job was reloaded from the absolute plist path and verified with `TDX_AUCTION_WATCHDOG_SERVER_COUNT=4`.

**Latest checkpoint (2026-09-06 08:47):** 73 of 1,668 daily tasks are successful, 1,595 remain pending, and none are failed. February through May 2018 are complete and have been reported to Feishu; June 1–7 are complete and the next resumable frontier is June 8. TDX canonical rows are `source='tdx'`, `volume_unit='hand'`, and the existing Tushare rows remain unchanged.
