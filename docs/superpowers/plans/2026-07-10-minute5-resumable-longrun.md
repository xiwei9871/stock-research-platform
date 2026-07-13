# Minute5 Resumable Long-Run Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the daily BaoStock 5-minute ingest into a current-day, single-session, database-resumable long-running job with compact OpenClaw heartbeats, truthful interruption state, paired raw/qfq quality gates, and verified six-hour Cron safety limits.

**Status:** Implemented and operationally verified on 2026-07-10. The real full-market run completed with 5,190/5,190 raw and qfq assets, and the subsequent resume run made zero remote requests.

**Architecture:** The Python stage owns a synchronous BaoStock session and checkpoints each successful symbol immediately. Every attempt derives its pending set and final quality from PostgreSQL, while the shell wrapper independently emits compact heartbeats so OpenClaw can supervise the long run without receiving the full log. Downstream readiness requires paired persisted raw/qfq quality and treats older source-attempt failures as superseded only after both quality rows pass.

**Tech Stack:** Python 3.14, pytest, PostgreSQL/psycopg, Bash, BaoStock, OpenClaw command Cron.

---

## File Map

- Modify `src/stock_research/minute_data.py`: provide explicit safe BaoStock logout and keep retry/relogin synchronous.
- Modify `src/stock_research/daily_close_pipeline.py`: current-day fetch, session ownership, persisted resume, raw/qfq quality, stale-attempt cleanup, interruption handling, and paired-quality readiness.
- Modify `scripts/run_daily_close_pipeline_cron.sh`: child-process supervision and compact heartbeat output.
- Modify `src/stock_research/eod_auto_repair.py`: rederive qfq and persist both raw/qfq quality rows during repair.
- Modify `src/stock_research/eod_auto_repair_checks.py`: require paired raw/qfq quality in the minute5 repair gate.
- Modify `src/stock_research/platform_ready.py`: require paired raw/qfq quality for minute readiness.
- Modify `tests/test_minute_data.py`: session cleanup and synchronous retry behavior.
- Modify `tests/test_daily_close_pipeline.py`: current-day request, resume, session lifecycle, qfq quality, interruption state, and finalize behavior.
- Modify `tests/test_daily_close_scripts.py`: wrapper heartbeat, log retention, exit-code preservation, and cleanup.
- Modify `tests/test_eod_auto_repair.py`: paired-quality repair behavior.
- Modify `tests/test_platform_ready.py`: paired-quality readiness behavior.
- Modify OpenClaw job `3a2a36e5-c6da-46b3-aa5d-34b22bf4b2ff`: six-hour total timeout while retaining the 1,200-second no-output watchdog.

## Task 1: Adjustment-Aware Persisted Minute Quality

**Files:**
- Modify: `src/stock_research/daily_close_pipeline.py:590-640`
- Test: `tests/test_daily_close_pipeline.py`

- [ ] **Step 1: Write failing raw/qfq database-quality tests**

Add tests that capture the SQL adjustment filter and dataset-specific result:

```python
def test_inspect_minute5_quality_from_db_filters_requested_adjust_type(monkeypatch):
    captured = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(dcp, "connect", lambda _service: FakeConnection())

    def fake_fetch_all(_conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [{"ts_code": "600000.SH", "bar_count": 48, "has_morning": True, "has_afternoon": True}]

    monkeypatch.setattr(dcp, "fetch_all", fake_fetch_all)

    result = dcp.inspect_minute5_quality_from_db(
        "test",
        ["600000.SH"],
        date(2026, 7, 10),
        adjust_type="qfq",
    )

    assert "adjust_type = %s" in captured["sql"]
    assert captured["params"] == [date(2026, 7, 10), "qfq", ["600000.SH"]]
    assert result["status"] == "pass"
```

Add a second test with one absent symbol and one 20-bar symbol, asserting the absent symbol is in `missing_symbols` and the short symbol is in `abnormal_symbols`.

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_pipeline.py -k 'inspect_minute5_quality_from_db_filters_requested_adjust_type' -q
```

Expected: FAIL because `inspect_minute5_quality_from_db` does not accept `adjust_type` and the SQL is fixed to raw.

- [ ] **Step 3: Make persisted inspection adjustment-aware**

Change the function signature and SQL contract:

```python
def inspect_minute5_quality_from_db(
    service: str,
    expected_ts_codes: list[str],
    target_date: date,
    *,
    adjust_type: str = "raw",
) -> dict[str, Any]:
    sql = """
    SELECT
        ts_code,
        count(*) AS bar_count,
        bool_or(trade_time::time BETWEEN time '09:00' AND time '11:35') AS has_morning,
        bool_or(trade_time::time BETWEEN time '13:00' AND time '15:05') AS has_afternoon
    FROM market.stock_minute_bar
    WHERE trade_date = %s
      AND freq = '5min'
      AND adjust_type = %s
      AND ts_code = ANY(%s)
    GROUP BY ts_code
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [target_date, adjust_type, expected_ts_codes])
    return inspect_minute5_quality(rows, expected_ts_codes, target_date)
```

If the existing row shape differs from `inspect_minute5_quality`, retain the existing row-to-quality logic and change only the parameterized adjustment filter.

- [ ] **Step 4: Run the quality tests**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_pipeline.py -k 'minute5_quality' -q
```

Expected: PASS.

- [ ] **Step 5: Commit only Task 1 hunks**

```bash
git add -p src/stock_research/daily_close_pipeline.py tests/test_daily_close_pipeline.py
git commit -m "feat: inspect persisted minute quality by adjustment"
```

Do not stage pre-existing unrelated hunks in either file.

## Task 2: Current-Day Synchronous BaoStock Session

**Files:**
- Modify: `src/stock_research/minute_data.py:343-365,467-481`
- Modify: `src/stock_research/daily_close_pipeline.py:27-31,1011-1027,1493-1695`
- Test: `tests/test_minute_data.py`
- Test: `tests/test_daily_close_pipeline.py`

- [ ] **Step 1: Replace the old threaded-fetch expectation with a failing synchronous test**

Replace `test_fetch_baostock_minute5_rows_uses_call_with_timeout` with:

```python
def test_fetch_baostock_minute5_rows_calls_query_synchronously_for_target_day(monkeypatch):
    calls = []

    def fake_query(code, start_date, end_date, freq, adjust_type, timeout_seconds):
        calls.append((code, start_date, end_date, freq, adjust_type, timeout_seconds))
        return []

    monkeypatch.setattr(dcp, "query_baostock_minute_rows", fake_query)
    monkeypatch.setattr(
        dcp,
        "call_with_timeout",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("thread timeout must not be used")),
    )

    target = date(2026, 7, 10)
    assert dcp.fetch_baostock_minute5_rows(
        "600000.SH",
        start_date=target,
        end_date=target,
        timeout_seconds=30,
    ) == []
    assert calls == [("sh.600000", target, target, "5min", "raw", 30)]
```

- [ ] **Step 2: Add a failing stage session-lifecycle/current-day test**

```python
def test_minute5_stage_owns_one_session_and_fetches_only_target_date(monkeypatch):
    events = []
    fetch_calls = []
    target = date(2026, 7, 10)

    monkeypatch.setattr(dcp, "should_skip_for_holiday", lambda *_args, **_kwargs: (False, "open"))
    monkeypatch.setattr(dcp, "setup_stage_logger", lambda *_args: (Mock(), "/tmp/minute5.log"))
    monkeypatch.setattr(dcp, "upsert_job", lambda **_kwargs: None)
    monkeypatch.setattr(dcp, "upsert_quality", lambda **_kwargs: None)
    monkeypatch.setattr(dcp, "record_failed_symbol", lambda **_kwargs: None)
    monkeypatch.setattr(dcp, "baostock_login_or_raise", lambda **_kwargs: events.append("login"))
    monkeypatch.setattr(dcp, "baostock_logout_safely", lambda: events.append("logout"))
    monkeypatch.setattr(
        dcp,
        "inspect_minute5_quality_from_db",
        lambda *_args, adjust_type="raw", **_kwargs: {
            "status": "fail",
            "expected_count": 2,
            "actual_count": 0,
            "missing_symbols": ["600000.SH", "000001.SZ"],
            "abnormal_symbols": [],
            "check_summary": f"{adjust_type} missing=2",
        },
    )

    def fake_fetch(ts_code, *, start_date, end_date, timeout_seconds):
        fetch_calls.append((ts_code, start_date, end_date))
        return []

    dcp.run_minute5_stage(
        target,
        config=dcp.PipelineConfig(service="test", minute5_symbol_sleep_seconds=0),
        ts_codes=["600000.SH", "000001.SZ"],
        baostock_fetcher=fake_fetch,
        upserter=lambda *_args: 0,
        qfq_deriver=lambda *_args: {"raw_rows": 0, "inserted_rows": 0},
    )

    assert events == ["login", "logout"]
    assert fetch_calls == [
        ("600000.SH", target, target),
        ("000001.SZ", target, target),
    ]
```

- [ ] **Step 3: Run both tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_pipeline.py -k 'synchronously_for_target_day or owns_one_session' -q
```

Expected: FAIL because the fetcher uses `call_with_timeout`, the stage uses a lookback start, and no explicit session lifecycle exists.

- [ ] **Step 4: Add safe logout and remove the outer executor**

In `minute_data.py` add:

```python
def logout_safely() -> None:
    try:
        bs.logout()
    except Exception:
        pass
```

Use it from existing `finally` blocks. Import it in `daily_close_pipeline.py` as `baostock_logout_safely`.

Change the daily fetch adapter to call the socket-timeout-aware query directly:

```python
def fetch_baostock_minute5_rows(
    ts_code: str, *, start_date: date, end_date: date, timeout_seconds: int
) -> list[dict[str, Any]]:
    raw_rows = query_baostock_minute_rows(
        ts_code_to_baostock_code(ts_code),
        start_date,
        end_date,
        freq="5min",
        adjust_type="raw",
        timeout_seconds=timeout_seconds,
    )
    return [
        baostock_minute_market_row(row, freq="5min", adjust_type="raw")
        for row in raw_rows
    ]
```

- [ ] **Step 5: Own the session around the serial source loops**

Use the target date directly and wrap source execution:

```python
fetch_start = trade_date
baostock_login_or_raise(timeout_seconds=config.request_timeout_seconds)
try:
    for source in MINUTE5_SOURCES:
        _run_source(source, source_codes[source])
finally:
    baostock_logout_safely()
```

Pass `start_date=trade_date` and `end_date=trade_date` from `_one`. Do not use `minute5_lookback_days` in the daily stage.

- [ ] **Step 6: Run session and existing minute tests**

Run:

```bash
.venv/bin/pytest tests/test_minute_data.py tests/test_daily_close_pipeline.py -k 'baostock or minute5_stage' -q
```

Expected: PASS, including the existing global-serial test.

- [ ] **Step 7: Commit only Task 2 hunks**

```bash
git add -p src/stock_research/minute_data.py src/stock_research/daily_close_pipeline.py tests/test_minute_data.py tests/test_daily_close_pipeline.py
git commit -m "fix: use one synchronous baostock minute session"
```

## Task 3: Database-Backed Resume and Paired Quality

**Files:**
- Modify: `src/stock_research/daily_close_pipeline.py:1493-1705`
- Test: `tests/test_daily_close_pipeline.py`

- [ ] **Step 1: Write a failing resume test**

```python
def test_minute5_stage_fetches_only_persisted_missing_and_abnormal_symbols(monkeypatch):
    target = date(2026, 7, 10)
    fetched = []
    quality_calls = []

    monkeypatch.setattr(dcp, "should_skip_for_holiday", lambda *_args, **_kwargs: (False, "open"))
    monkeypatch.setattr(dcp, "setup_stage_logger", lambda *_args: (Mock(), "/tmp/minute5.log"))
    monkeypatch.setattr(dcp, "upsert_job", lambda **_kwargs: None)
    monkeypatch.setattr(dcp, "upsert_quality", lambda **kwargs: quality_calls.append(kwargs))
    monkeypatch.setattr(dcp, "record_failed_symbol", lambda **_kwargs: None)
    monkeypatch.setattr(dcp, "baostock_login_or_raise", lambda **_kwargs: None)
    monkeypatch.setattr(dcp, "baostock_logout_safely", lambda: None)

    inspections = iter([
        {
            "status": "warning",
            "expected_count": 3,
            "actual_count": 2,
            "missing_symbols": ["600001.SH"],
            "abnormal_symbols": ["000001.SZ"],
            "check_summary": "raw pending=2",
        },
        {
            "status": "pass",
            "expected_count": 3,
            "actual_count": 3,
            "missing_symbols": [],
            "abnormal_symbols": [],
            "check_summary": "raw pass",
        },
        {
            "status": "pass",
            "expected_count": 3,
            "actual_count": 3,
            "missing_symbols": [],
            "abnormal_symbols": [],
            "check_summary": "qfq pass",
        },
    ])
    monkeypatch.setattr(dcp, "inspect_minute5_quality_from_db", lambda *_args, **_kwargs: next(inspections))

    def fake_fetch(ts_code, **_kwargs):
        fetched.append(ts_code)
        return []

    result = dcp.run_minute5_stage(
        target,
        config=dcp.PipelineConfig(service="test", minute5_symbol_sleep_seconds=0),
        ts_codes=["600000.SH", "600001.SH", "000001.SZ"],
        baostock_fetcher=fake_fetch,
        upserter=lambda *_args: 0,
        qfq_deriver=lambda *_args: {"raw_rows": 144, "inserted_rows": 144},
    )

    assert fetched == ["600001.SH", "000001.SZ"]
    assert result["status"] == "success"
    assert {item["dataset_name"] for item in quality_calls} >= {"minute5_bar", "minute5_qfq_bar"}
```

- [ ] **Step 2: Write a failing raw-complete/qfq-rederive test**

Create a test where the first raw inspection is `pass`, no fetcher may be called, qfq derivation is recorded once, and the final qfq inspection passes.

```python
def forbidden_fetch(*_args, **_kwargs):
    raise AssertionError("raw-complete resume must not contact BaoStock")
```

Assert login is also skipped when there are no pending raw symbols.

- [ ] **Step 3: Run the resume tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_pipeline.py -k 'persisted_missing_and_abnormal or raw_complete' -q
```

Expected: FAIL because the current stage always fetches the full source universe and final quality is in-memory/raw-only.

- [ ] **Step 4: Build the pending set from persisted raw quality**

At stage startup:

```python
initial_raw_quality = inspect_minute5_quality_from_db(
    config.service,
    expected_ts_codes,
    trade_date,
    adjust_type="raw",
)
pending_ts_codes = sorted(
    set(initial_raw_quality["missing_symbols"])
    | set(initial_raw_quality["abnormal_symbols"])
)
source_codes = split_minute5_sources(pending_ts_codes)
```

Use `len(pending_ts_codes)` as the current attempt total while keeping expected coverage counts in quality messages. Skip login and source loops when the pending set is empty.

- [ ] **Step 5: Always derive qfq and persist final paired quality**

After raw fetching:

```python
qfq_result = qfq_deriver(config.service, trade_date)
raw_quality = inspect_minute5_quality_from_db(
    config.service, expected_ts_codes, trade_date, adjust_type="raw"
)
qfq_quality = inspect_minute5_quality_from_db(
    config.service, expected_ts_codes, trade_date, adjust_type="qfq"
)
upsert_quality(
    service=config.service,
    trade_date=trade_date,
    dataset_name="minute5_bar",
    **raw_quality,
)
upsert_quality(
    service=config.service,
    trade_date=trade_date,
    dataset_name="minute5_qfq_bar",
    **qfq_quality,
)
status = "success" if raw_quality["status"] == qfq_quality["status"] == "pass" else "failed"
```

Retain partial source statistics, but do not report overall success unless both persisted datasets pass.

- [ ] **Step 6: Run resume and derivation tests**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_pipeline.py -k 'minute5_stage or derive_qfq' -q
```

Expected: PASS.

- [ ] **Step 7: Commit only Task 3 hunks**

```bash
git add -p src/stock_research/daily_close_pipeline.py tests/test_daily_close_pipeline.py
git commit -m "feat: resume minute ingest from persisted coverage"
```

## Task 4: Stale-Running Cleanup and Interrupt-Safe Terminal State

**Files:**
- Modify: `src/stock_research/daily_close_pipeline.py:300-400,1493-1705,2470-2490`
- Test: `tests/test_daily_close_pipeline.py`

- [ ] **Step 1: Write a failing stale-attempt cleanup test**

Add a helper-level test expecting one SQL update scoped to trade date, stage, job name, and `status='running'`:

```python
def test_mark_stale_running_jobs_interrupted_updates_only_owned_stage(monkeypatch):
    captured = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(dcp, "connect", lambda _service: FakeConnection())
    monkeypatch.setattr(
        dcp,
        "execute",
        lambda _conn, sql, payload: captured.update(sql=sql, payload=payload),
    )

    dcp.mark_stale_running_jobs_interrupted(
        service="test",
        trade_date=date(2026, 7, 10),
        stage="minute5",
        job_name="minute5_bar",
    )

    assert "status = 'running'" in captured["sql"]
    assert captured["payload"]["error_summary"] == "interrupted: stale running attempt superseded"
```

- [ ] **Step 2: Write a failing exception-terminal-state test**

Inject a fetcher that raises `KeyboardInterrupt` after one successful symbol. Capture `upsert_job` calls and assert both source rows finish as `failed`, have `finished_at`, and use an interruption summary. Also assert logout occurs.

- [ ] **Step 3: Run both tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_pipeline.py -k 'stale_running or terminal_state' -q
```

Expected: FAIL because no stale cleanup helper or common interruption-finalization path exists.

- [ ] **Step 4: Add stale-running cleanup**

Implement:

```python
def mark_stale_running_jobs_interrupted(
    *, service: str, trade_date: date, stage: str, job_name: str
) -> None:
    sql = """
    UPDATE ops.daily_pipeline_job
    SET status = 'failed',
        finished_at = now(),
        duration_seconds = EXTRACT(EPOCH FROM (now() - started_at)),
        error_summary = %(error_summary)s,
        updated_at = now()
    WHERE trade_date = %(trade_date)s
      AND stage = %(stage)s
      AND job_name = %(job_name)s
      AND status = 'running'
    """
    payload = {
        "trade_date": trade_date,
        "stage": stage,
        "job_name": job_name,
        "error_summary": "interrupted: stale running attempt superseded",
    }
    with connect(service) as conn:
        execute(conn, sql, payload)
```

Call it before inserting new `running` rows.

- [ ] **Step 5: Centralize abnormal-exit finalization**

Wrap source execution and derivation with `except BaseException as exc`. Before re-raising:

1. inspect and persist current raw quality;
2. update every source still owned by the current attempt to `failed`;
3. set `finished_at`, duration, missing count, and `error_summary=f"interrupted: {type(exc).__name__}: {exc}"`;
4. rely on the existing session `finally` for logout.

Install CLI-scoped signal handlers that raise `KeyboardInterrupt("SIGTERM")` and restore the previous handlers after the selected stage returns.

- [ ] **Step 6: Run interruption and full daily-pipeline tests**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit only Task 4 hunks**

```bash
git add -p src/stock_research/daily_close_pipeline.py tests/test_daily_close_pipeline.py
git commit -m "fix: close interrupted minute ingest attempts"
```

## Task 5: Compact Wrapper Heartbeats

**Files:**
- Modify: `scripts/run_daily_close_pipeline_cron.sh:1-86`
- Test: `tests/test_daily_close_scripts.py`

- [ ] **Step 1: Write a failing heartbeat test with a stub Python child**

Use the existing script-test helpers and a temporary executable that sleeps long enough for two short heartbeats:

```python
def test_daily_close_minute5_wrapper_emits_compact_heartbeat(tmp_path: Path) -> None:
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'progress|minute5_bar|event|minute5_progress|completed|50|total|100'\n"
        "sleep 2\n"
        "echo '{\"status\":\"success\",\"rows\":4800}'\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    log_dir = tmp_path / "logs"

    result = subprocess.run(
        ["scripts/run_daily_close_pipeline_cron.sh", "minute5"],
        cwd=PROJECT_ROOT,
        env={
            **os.environ,
            "PYTHON_BIN": str(fake_python),
            "DAILY_CLOSE_CRON_LOG_DIR": str(log_dir),
            "DAILY_CLOSE_HEARTBEAT_SECONDS": "1",
            "STOCK_CRON_GUARD_BYPASS": "1",
        },
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "daily_close_pipeline|started|stage=minute5" in result.stdout
    assert "daily_close_pipeline|heartbeat|stage=minute5" in result.stdout
    assert "completed|50|total|100" in result.stdout
    detail_log = next(log_dir.glob("daily_close_pipeline_minute5_*.log"))
    assert '"status":"success"' in detail_log.read_text(encoding="utf-8")
```

Adapt the guard-bypass environment name to the existing test helper if it differs.

- [ ] **Step 2: Add failing exit-code and cleanup tests**

Add one stub that prints progress and exits `7`; assert wrapper return code `7`, final failure summary, and detail-log path. Add one termination test that starts the wrapper with `Popen`, sends `SIGTERM`, waits, and asserts no heartbeat child remains.

- [ ] **Step 3: Run wrapper tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_scripts.py -k 'heartbeat or exit_code or termination' -q
```

Expected: FAIL because the wrapper waits synchronously and emits no output before completion.

- [ ] **Step 4: Supervise the child and emit heartbeats**

Refactor the stage execution around this contract:

```bash
HEARTBEAT_SECONDS="${DAILY_CLOSE_HEARTBEAT_SECONDS:-300}"

run_pipeline_child() {
  if [[ -n "$TRADE_DATE" ]]; then
    "$PYTHON_BIN" -m scripts.daily_pipeline --date "$TRADE_DATE" --stage "$STAGE" >>"$DETAIL_LOG" 2>&1 &
  else
    "$PYTHON_BIN" -m scripts.daily_pipeline --stage "$STAGE" >>"$DETAIL_LOG" 2>&1 &
  fi
  PIPELINE_PID=$!
}

cleanup_heartbeat() {
  if [[ -n "${HEARTBEAT_PID:-}" ]]; then
    kill "$HEARTBEAT_PID" 2>/dev/null || true
    wait "$HEARTBEAT_PID" 2>/dev/null || true
  fi
}

forward_signal() {
  if [[ -n "${PIPELINE_PID:-}" ]]; then
    kill -TERM "$PIPELINE_PID" 2>/dev/null || true
  fi
}

trap 'forward_signal; cleanup_heartbeat' TERM INT
trap 'cleanup_heartbeat' EXIT

echo "daily_close_pipeline|started|stage=$STAGE|trade_date=${TRADE_DATE:-auto}|detail_log=$DETAIL_LOG"
run_pipeline_child
(
  started_epoch=$(date +%s)
  while kill -0 "$PIPELINE_PID" 2>/dev/null; do
    sleep "$HEARTBEAT_SECONDS"
    kill -0 "$PIPELINE_PID" 2>/dev/null || break
    now_epoch=$(date +%s)
    last_progress=$(grep -E '^(progress\|minute5_bar|minute5\|progress)' "$DETAIL_LOG" | tail -n 1 || true)
    echo "daily_close_pipeline|heartbeat|stage=$STAGE|trade_date=${TRADE_DATE:-auto}|elapsed_seconds=$((now_epoch-started_epoch))|last_progress=${last_progress:-waiting}"
  done
) &
HEARTBEAT_PID=$!

set +e
wait "$PIPELINE_PID"
rc=$?
set -e
cleanup_heartbeat
```

Keep the existing business-failure detection and final summary after the child wait.

- [ ] **Step 5: Run all daily-close script tests**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_scripts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit only Task 5 files**

```bash
git add scripts/run_daily_close_pipeline_cron.sh tests/test_daily_close_scripts.py
git commit -m "fix: emit heartbeats for long minute close jobs"
```

## Task 6: Paired Raw/QFQ Repair and Readiness

**Files:**
- Modify: `src/stock_research/eod_auto_repair.py:840-910`
- Modify: `src/stock_research/eod_auto_repair_checks.py:115-143`
- Modify: `src/stock_research/platform_ready.py:35-60`
- Modify: `src/stock_research/daily_close_pipeline.py:2180-2285`
- Test: `tests/test_eod_auto_repair.py`
- Test: `tests/test_platform_ready.py`
- Test: `tests/test_daily_close_pipeline.py`

- [ ] **Step 1: Write failing paired-quality finalize tests**

Update the success fixture in `test_finalize_pipeline_status_hides_superseded_minute5_failures_when_quality_passes` to include both rows and add a missing-qfq case:

```python
def test_finalize_pipeline_status_requires_qfq_quality_pass(monkeypatch):
    monkeypatch.setattr(
        dcp,
        "load_pipeline_jobs",
        lambda *_args, **_kwargs: [
            {"stage": "daily", "job_name": "daily_bar", "source": "tushare", "status": "success"},
            {"stage": "minute5", "job_name": "minute5_bar", "source": "baostock_sh", "status": "success"},
            {"stage": "minute5", "job_name": "minute5_bar", "source": "baostock_sz", "status": "success"},
        ],
    )
    monkeypatch.setattr(
        dcp,
        "load_pipeline_quality",
        lambda *_args, **_kwargs: [
            {"dataset_name": "daily_bar", "status": "pass", "expected_count": 1, "actual_count": 1},
            {"dataset_name": "minute5_bar", "status": "pass", "expected_count": 1, "actual_count": 1},
            {"dataset_name": "minute5_qfq_bar", "status": "fail", "expected_count": 1, "actual_count": 0},
        ],
    )

    result = dcp.finalize_pipeline_status(date(2026, 7, 10), config=dcp.PipelineConfig(service="test"))
    assert result["minute5_status"] == "failed"
```

Use the existing helpers for calendar, dependency, and market-monitor fixtures.

- [ ] **Step 2: Write failing platform-ready and repair tests**

Add a platform-ready test where raw passes and qfq fails, asserting minute5 is not ready. Add an auto-repair test asserting the repair action persists both `minute5_bar` and `minute5_qfq_bar` after qfq derivation.

- [ ] **Step 3: Run paired-quality tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_pipeline.py tests/test_platform_ready.py tests/test_eod_auto_repair.py -k 'qfq_quality or minute5_quality' -q
```

Expected: FAIL because downstream code reads only `minute5_bar`.

- [ ] **Step 4: Require paired quality in finalize and platform-ready**

Load `minute5_qfq_bar` alongside existing datasets. Compute minute status with both rows:

```python
raw_minute_status = _quality_status("minute5", quality_by_dataset.get("minute5_bar"), config)
qfq_minute_status = _quality_status("minute5", quality_by_dataset.get("minute5_qfq_bar"), config)
minute5_status = combine_required_quality_statuses(raw_minute_status, qfq_minute_status)
```

`combine_required_quality_statuses` returns `failed` if either input is `failed`, `partial_success` if neither fails and either is partial, and `success` only when both succeed.

Apply the same paired check in `platform_ready.py`.

- [ ] **Step 5: Persist paired quality during auto-repair**

After raw repair and qfq derivation, inspect and upsert both adjustment types. The action reports success only when both pass; otherwise include raw and qfq missing/abnormal counts in the failure message.

- [ ] **Step 6: Run all affected suites**

Run:

```bash
.venv/bin/pytest tests/test_daily_close_pipeline.py tests/test_platform_ready.py tests/test_eod_auto_repair.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit only Task 6 hunks**

```bash
git add -p src/stock_research/eod_auto_repair.py src/stock_research/platform_ready.py src/stock_research/daily_close_pipeline.py tests/test_eod_auto_repair.py tests/test_platform_ready.py tests/test_daily_close_pipeline.py
git commit -m "fix: require paired minute raw and qfq quality"
```

## Task 7: OpenClaw Cron Rollout

**Files:**
- External state: OpenClaw job `3a2a36e5-c6da-46b3-aa5d-34b22bf4b2ff`
- Reference: `docs/superpowers/specs/2026-07-10-minute5-resumable-longrun-design.md`

- [ ] **Step 1: Capture the pre-change job configuration**

Run:

```bash
openclaw cron get 3a2a36e5-c6da-46b3-aa5d-34b22bf4b2ff
```

Expected: command job at `0 17 * * 1-5`, `noOutputTimeoutSeconds=1200`, and `timeoutSeconds=14400`.

- [ ] **Step 2: Update only the total timeout**

Run:

```bash
openclaw cron edit 3a2a36e5-c6da-46b3-aa5d-34b22bf4b2ff \
  --timeout-seconds 21600 \
  --no-output-timeout-seconds 1200 \
  --output-max-bytes 20000
```

Expected: success response with the same schedule, command, agent, delivery, and failure alert.

- [ ] **Step 3: Verify the post-change job configuration**

Run:

```bash
openclaw cron get 3a2a36e5-c6da-46b3-aa5d-34b22bf4b2ff
```

Expected: `timeoutSeconds=21600`, `noOutputTimeoutSeconds=1200`, `outputMaxBytes=20000`, schedule still 17:00 Asia/Shanghai, and Feishu account still `jarvis`.

## Task 8: Fault Injection and Completion Audit

**Files:**
- No new production files.
- Verify all files and external state listed above.

- [ ] **Step 1: Run focused automated verification**

Run:

```bash
.venv/bin/pytest \
  tests/test_minute_data.py \
  tests/test_daily_close_pipeline.py \
  tests/test_daily_close_scripts.py \
  tests/test_platform_ready.py \
  tests/test_eod_auto_repair.py \
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run the broader backend suite if focused tests pass**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all tests pass, or unrelated pre-existing failures are recorded with exact test names and evidence that the focused suites remain green.

- [ ] **Step 3: Verify wrapper heartbeat without remote data**

Run the dedicated heartbeat test with `-s` and confirm the captured stdout contains a start line and at least one heartbeat before the stub exits:

```bash
.venv/bin/pytest tests/test_daily_close_scripts.py -k 'minute5_wrapper_emits_compact_heartbeat' -q -s
```

Expected: PASS.

- [ ] **Step 4: Verify persisted resume with controlled source injection**

Run the resume tests individually:

```bash
.venv/bin/pytest tests/test_daily_close_pipeline.py -k 'persisted_missing_and_abnormal or raw_complete' -q
```

Expected: PASS and no remote BaoStock call.

- [ ] **Step 5: Inspect today's operational state before any real rerun**

Run:

```bash
psql service=stock_research -P pager=off -c "
SELECT trade_date, source, status, started_at, finished_at, missing_symbols_count, error_summary
FROM ops.daily_pipeline_job
WHERE trade_date = current_date AND stage = 'minute5'
ORDER BY source;

SELECT trade_date, dataset_name, status, expected_count, actual_count,
       jsonb_array_length(missing_symbols) AS missing_count,
       jsonb_array_length(abnormal_symbols) AS abnormal_count
FROM ops.daily_pipeline_quality
WHERE trade_date = current_date
  AND dataset_name IN ('minute5_bar', 'minute5_qfq_bar')
ORDER BY dataset_name;
"
```

Expected: evidence establishes whether a real retry is necessary. Do not contact BaoStock when paired quality already passes.

- [ ] **Step 6: Run one controlled real-date command only if data is incomplete**

Run:

```bash
TRADE_DATE=$(date +%F) DAILY_CLOSE_HEARTBEAT_SECONDS=60 scripts/run_daily_close_pipeline_cron.sh minute5
```

Expected: immediate start output, heartbeat within 60 seconds, only persisted missing/abnormal raw symbols requested, paired quality written, and terminal source rows not left running.

If paired quality already passes, use a past controlled date with a deliberately limited injected test path instead of refetching production data.

- [ ] **Step 7: Re-run PostgreSQL completion queries**

Expected evidence:

- `minute5_bar=pass`;
- `minute5_qfq_bar=pass`;
- raw and qfq expected/actual counts match;
- no source row remains `running` after command completion;
- first/last 5-minute times remain `09:35:00` and `15:00:00` for covered assets.

- [ ] **Step 8: Inspect final diff and working-tree ownership**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors. Do not discard or claim unrelated pre-existing dashboard, research, or pipeline changes.

- [ ] **Step 9: Final requirement-by-requirement audit**

Record authoritative evidence for every acceptance criterion in the design spec: current-day range, one session, no thread timeout, heartbeat, resume, qfq rederive, terminal states, paired quality, downstream readiness, Cron configuration, focused tests, and controlled runtime behavior. Do not mark the goal complete if any item lacks direct evidence.
