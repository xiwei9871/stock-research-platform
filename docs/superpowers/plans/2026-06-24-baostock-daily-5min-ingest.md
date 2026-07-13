# Baostock Daily 5min Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated daily Baostock `5min` ingest path that starts after market close, only fetches the current trading day, runs as a single instance with one session, and slows down safely under retry conditions instead of falling back to backfill-style concurrency.

**Architecture:** Keep the existing backfill code intact and add a separate daily ingest runner that reuses Baostock login, symbol-universe, and upsert helpers from `minute_data.py`. Introduce one new single-shot Baostock query primitive so the daily runner can own retry, relogin, cooldown, and output-artifact behavior without inheriting the existing “query failure -> immediate relogin” flow.

**Tech Stack:** Python 3.11, `python -m stock_research.cli`, existing `minute_data.py` helpers, bash cron wrappers, pytest

---

## File Map

- `/Users/xiwei/stock_research/src/stock_research/minute_data.py`
  - Keep the current backfill-facing retry wrapper.
  - Add a single-attempt minute-query helper for the new daily runner.
- `/Users/xiwei/stock_research/src/stock_research/minute_daily_ingest.py`
  - New dedicated daily ingest module.
  - Owns lock acquisition, trade-date gate, serialized fetch loop, retry queue, relogin threshold, cooldown, and output artifacts.
- `/Users/xiwei/stock_research/src/stock_research/cli.py`
  - Add a new `run-baostock-minute-daily` command wired to the daily ingest module.
- `/Users/xiwei/stock_research/scripts/run_baostock_minute_daily_cron.sh`
  - New cron wrapper that clears proxy env, runs the stock cron guard, and then invokes the CLI.
- `/Users/xiwei/stock_research/tests/test_minute_data.py`
  - Add tests for the new single-attempt Baostock query helper.
- `/Users/xiwei/stock_research/tests/test_minute_daily_ingest.py`
  - New unit tests for lock behavior, non-trading-day skip, same-day query windows, retry thresholds, cooldown, and artifact output.
- `/Users/xiwei/stock_research/tests/test_minute_daily_ingest_cli.py`
  - New CLI tests for command wiring and printed summary lines.
- `/Users/xiwei/stock_research/tests/test_minute_daily_scripts.py`
  - New shell-script tests for proxy clearing, cron guard invocation, and CLI invocation shape.

### Task 1: Add A Single-Attempt Minute Query Primitive

**Files:**
- Modify: `/Users/xiwei/stock_research/src/stock_research/minute_data.py`
- Modify: `/Users/xiwei/stock_research/tests/test_minute_data.py`

- [ ] **Step 1: Write the failing tests for the single-attempt Baostock query helper**

```python
import datetime as dt

from stock_research import minute_data


def test_query_baostock_minute_rows_once_returns_rows_without_retry(monkeypatch):
    class Result:
        error_code = "0"
        error_msg = "success"
        fields = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount"]

        def __init__(self):
            self.rows = [[
                "2024-01-02",
                "20240102093500000",
                "sh.600000",
                "6.6300",
                "6.6400",
                "6.6100",
                "6.6200",
                "1902300",
                "12603192.0000",
            ]]
            self.index = -1

        def next(self):
            self.index += 1
            return self.index < len(self.rows)

        def get_row_data(self):
            return self.rows[self.index]

    calls = []
    monkeypatch.setattr(
        minute_data.bs,
        "query_history_k_data_plus",
        lambda code, fields, **kwargs: calls.append((code, kwargs)) or Result(),
    )

    rows = minute_data.query_baostock_minute_rows_once(
        "sh.600000",
        dt.date(2024, 1, 2),
        dt.date(2024, 1, 2),
        freq="5min",
        adjust_type="raw",
    )

    assert len(rows) == 1
    assert calls == [
        (
            "sh.600000",
            {
                "start_date": "2024-01-02",
                "end_date": "2024-01-02",
                "frequency": "5",
                "adjustflag": "3",
            },
        )
    ]


def test_query_baostock_minute_rows_once_raises_without_triggering_relogin(monkeypatch):
    class Result:
        error_code = "10002007"
        error_msg = "网络接收错误"
        fields = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount"]

        def next(self):
            return False

        def get_row_data(self):
            raise AssertionError("should not be called")

    calls = {"query": 0, "login": 0, "logout": 0}
    monkeypatch.setattr(
        minute_data.bs,
        "query_history_k_data_plus",
        lambda *args, **kwargs: calls.__setitem__("query", calls["query"] + 1) or Result(),
    )
    monkeypatch.setattr(
        minute_data.bs,
        "login",
        lambda: calls.__setitem__("login", calls["login"] + 1),
    )
    monkeypatch.setattr(
        minute_data.bs,
        "logout",
        lambda: calls.__setitem__("logout", calls["logout"] + 1),
    )

    try:
        minute_data.query_baostock_minute_rows_once(
            "sh.600000",
            dt.date(2024, 1, 2),
            dt.date(2024, 1, 2),
            freq="5min",
            adjust_type="raw",
        )
    except RuntimeError as exc:
        assert "10002007" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    assert calls == {"query": 1, "login": 0, "logout": 0}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_minute_data.py::test_query_baostock_minute_rows_once_returns_rows_without_retry tests/test_minute_data.py::test_query_baostock_minute_rows_once_raises_without_triggering_relogin -q
```

Expected: FAIL with `AttributeError` because `query_baostock_minute_rows_once` does not exist yet.

- [ ] **Step 3: Implement the single-attempt helper and keep the old retry wrapper**

```python
def query_baostock_minute_rows_once(
    code: str,
    start_date: dt.date,
    end_date: dt.date,
    freq: str,
    adjust_type: str,
    timeout_seconds: float | None = None,
) -> list[dict[str, str]]:
    with temporary_baostock_proxy(), temporary_socket_timeout(timeout_seconds):
        rs = bs.query_history_k_data_plus(
            code,
            ",".join(MINUTE_FIELDS),
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            frequency=baostock_frequency(freq),
            adjustflag=adjustflag_for_adjust_type(adjust_type),
        )
    if rs.error_code != "0":
        raise RuntimeError(
            f"baostock minute query failed for {code}: {rs.error_code} {rs.error_msg}"
        )

    rows: list[dict[str, str]] = []
    while rs.next():
        rows.append(dict(zip(rs.fields, rs.get_row_data(), strict=True)))
    return rows


def query_baostock_minute_rows(
    code: str,
    start_date: dt.date,
    end_date: dt.date,
    freq: str,
    adjust_type: str,
    timeout_seconds: float | None = None,
) -> list[dict[str, str]]:
    return run_with_baostock_retry(
        lambda: query_baostock_minute_rows_once(
            code,
            start_date,
            end_date,
            freq=freq,
            adjust_type=adjust_type,
            timeout_seconds=timeout_seconds,
        ),
        timeout_seconds=timeout_seconds,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_minute_data.py::test_query_baostock_minute_rows_once_returns_rows_without_retry tests/test_minute_data.py::test_query_baostock_minute_rows_once_raises_without_triggering_relogin -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/minute_data.py tests/test_minute_data.py
git commit -m "feat: add single-attempt baostock minute query"
```

### Task 2: Build The Daily Runner Start Gate And Main Pass

**Files:**
- Create: `/Users/xiwei/stock_research/src/stock_research/minute_daily_ingest.py`
- Create: `/Users/xiwei/stock_research/tests/test_minute_daily_ingest.py`

- [ ] **Step 1: Write the failing tests for non-trading-day skip, lock skip, and same-day serialized fetch**

```python
import datetime as dt
from pathlib import Path

from stock_research import minute_daily_ingest


def test_run_baostock_minute_daily_skips_non_trading_day(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: type(
            "Decision",
            (),
            {"should_run": False, "reason": "non_trading_day", "calendar_status": "closed"},
        )(),
    )

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2026-06-27",
        output_dir=tmp_path,
    )

    assert result["status"] == "skipped_non_trading_day"
    assert result["trade_date"] == "2026-06-27"
    assert result["symbol_count"] == 0


def test_run_baostock_minute_daily_skips_when_lock_is_busy(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: type(
            "Decision",
            (),
            {"should_run": True, "reason": "trading_day", "calendar_status": "open"},
        )(),
    )
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: None)

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2026-06-24",
        output_dir=tmp_path,
    )

    assert result["status"] == "skipped_locked"
    assert result["trade_date"] == "2026-06-24"


def test_run_baostock_minute_daily_queries_one_trade_date_per_symbol(monkeypatch, tmp_path: Path):
    calls = {"login": 0, "logout": 0, "queries": [], "upserts": []}

    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: type(
            "Decision",
            (),
            {"should_run": True, "reason": "trading_day", "calendar_status": "open"},
        )(),
    )
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: object())
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(minute_daily_ingest, "load_active_baostock_codes", lambda limit_assets=None: ["sh.600000", "sz.000001"])
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda timeout_seconds=None: calls.__setitem__("login", calls["login"] + 1))
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: calls.__setitem__("logout", calls["logout"] + 1))
    monkeypatch.setattr(minute_daily_ingest.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "query_baostock_minute_rows_once",
        lambda code, start_date, end_date, freq, adjust_type, timeout_seconds=None: calls["queries"].append(
            (code, start_date, end_date, freq, adjust_type)
        ) or [{"code": code, "date": "2026-06-24", "time": "20260624150000000"}],
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "upsert_stock_minute_bars",
        lambda rows, freq, adjust_type, params=None: calls["upserts"].append((rows, freq, adjust_type, params)) or len(rows),
    )

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2026-06-24",
        sleep_seconds=1.0,
        output_dir=tmp_path,
    )

    assert result["status"] == "success"
    assert calls["login"] == 1
    assert calls["logout"] == 1
    assert calls["queries"] == [
        ("sh.600000", dt.date(2026, 6, 24), dt.date(2026, 6, 24), "5min", "raw"),
        ("sz.000001", dt.date(2026, 6, 24), dt.date(2026, 6, 24), "5min", "raw"),
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_skips_non_trading_day tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_skips_when_lock_is_busy tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_queries_one_trade_date_per_symbol -q
```

Expected: FAIL with `ModuleNotFoundError` because `minute_daily_ingest.py` does not exist yet.

- [ ] **Step 3: Implement the dedicated daily runner start gate and main pass**

```python
DEFAULT_MINUTE_DAILY_LOCK = Path("/tmp/stock_research_baostock_minute_daily.lock")
RELOGIN_FAILURE_THRESHOLD = 3


def _try_acquire_daily_lock(lock_path: str | Path) -> Any | None:
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return handle


def _release_daily_lock(handle: Any | None) -> None:
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def run_baostock_minute_daily(
    trade_date: str | None = None,
    freq: str = "5min",
    adjust_type: str = "raw",
    sleep_seconds: float = 1.0,
    retry_limit: int = 2,
    cooldown_seconds: int = 600,
    timeout_seconds: float | None = None,
    output_dir: str | Path = "outputs/research",
    lock_path: str | Path = DEFAULT_MINUTE_DAILY_LOCK,
    limit_assets: int | None = None,
) -> dict[str, Any]:
    target_date = parse_trade_date(trade_date, "Asia/Shanghai")
    decision = decide_stock_cron_run(
        service=SETTINGS.research_service,
        trade_date=target_date,
        exchanges=("SH", "SZ", "BJ"),
    )
    if not decision.should_run:
        return {
            "status": "skipped_non_trading_day",
            "trade_date": target_date.isoformat(),
            "symbol_count": 0,
            "success_count": 0,
            "empty_count": 0,
            "failed_count": 0,
            "retry_count": 0,
            "relogin_count": 0,
            "rows_written": 0,
            "failed_symbols": [],
        }

    lock_handle = _try_acquire_daily_lock(lock_path)
    if lock_handle is None:
        return {
            "status": "skipped_locked",
            "trade_date": target_date.isoformat(),
            "symbol_count": 0,
            "success_count": 0,
            "empty_count": 0,
            "failed_count": 0,
            "retry_count": 0,
            "relogin_count": 0,
            "rows_written": 0,
            "failed_symbols": [],
        }

    codes = load_active_baostock_codes(limit_assets=limit_assets)
    result = {
        "status": "success",
        "trade_date": target_date.isoformat(),
        "symbol_count": len(codes),
        "success_count": 0,
        "empty_count": 0,
        "failed_count": 0,
        "retry_count": 0,
        "relogin_count": 0,
        "rows_written": 0,
        "failed_symbols": [],
    }
    try:
        login_or_raise(timeout_seconds=timeout_seconds)
        for code in codes:
            rows = query_baostock_minute_rows_once(
                code,
                target_date,
                target_date,
                freq=freq,
                adjust_type=adjust_type,
                timeout_seconds=timeout_seconds,
            )
            params = {
                "source": "baostock_daily",
                "trade_date": target_date.isoformat(),
                "baostock_code": code,
            }
            inserted = upsert_stock_minute_bars(
                rows,
                freq=freq,
                adjust_type=adjust_type,
                params=params,
            )
            if inserted:
                result["success_count"] += 1
                result["rows_written"] += inserted
            else:
                result["empty_count"] += 1
            if sleep_seconds:
                time.sleep(sleep_seconds)
    finally:
        try:
            bs.logout()
        except Exception:
            pass
        _release_daily_lock(lock_handle)
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_skips_non_trading_day tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_skips_when_lock_is_busy tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_queries_one_trade_date_per_symbol -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/minute_daily_ingest.py tests/test_minute_daily_ingest.py
git commit -m "feat: add baostock minute daily runner"
```

### Task 3: Add Retry Queue, Relogin Threshold, Cooldown, And Artifacts

**Files:**
- Modify: `/Users/xiwei/stock_research/src/stock_research/minute_daily_ingest.py`
- Modify: `/Users/xiwei/stock_research/tests/test_minute_daily_ingest.py`

- [ ] **Step 1: Write the failing tests for retry policy, cooldown, partial status, and artifacts**

```python
import datetime as dt
import json
from pathlib import Path

from stock_research import minute_daily_ingest


def test_run_baostock_minute_daily_retries_same_session_before_relogin(monkeypatch, tmp_path: Path):
    state = {"calls": 0, "relogin": 0}
    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: type("Decision", (), {"should_run": True, "reason": "trading_day", "calendar_status": "open"})(),
    )
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: object())
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(minute_daily_ingest, "load_active_baostock_codes", lambda limit_assets=None: ["sh.600000"])
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda timeout_seconds=None: None)
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: None)
    monkeypatch.setattr(minute_daily_ingest.time, "sleep", lambda _: None)

    def fake_query(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] < 3:
            raise RuntimeError("baostock minute query failed for sh.600000: 10002007 网络接收错误")
        return [{"code": "sh.600000", "date": "2026-06-24", "time": "20260624150000000"}]

    monkeypatch.setattr(minute_daily_ingest, "query_baostock_minute_rows_once", fake_query)
    monkeypatch.setattr(
        minute_daily_ingest,
        "relogin_or_raise",
        lambda timeout_seconds=None: state.__setitem__("relogin", state["relogin"] + 1),
    )
    monkeypatch.setattr(minute_daily_ingest, "upsert_stock_minute_bars", lambda rows, freq, adjust_type, params=None: 1)

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2026-06-24",
        retry_limit=2,
        output_dir=tmp_path,
    )

    assert result["status"] == "success"
    assert result["retry_count"] == 2
    assert result["relogin_count"] == 0


def test_run_baostock_minute_daily_retries_failed_symbols_only_in_retry_queue(monkeypatch, tmp_path: Path):
    calls = []
    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: type("Decision", (), {"should_run": True, "reason": "trading_day", "calendar_status": "open"})(),
    )
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: object())
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(minute_daily_ingest, "load_active_baostock_codes", lambda limit_assets=None: ["sh.600000", "sz.000001"])
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda timeout_seconds=None: None)
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: None)
    monkeypatch.setattr(minute_daily_ingest.time, "sleep", lambda _: None)
    attempts = {"sz.000001": 0}
    def fake_query(code, *args, **kwargs):
        calls.append(code)
        if code == "sz.000001":
            attempts["sz.000001"] += 1
            if attempts["sz.000001"] == 1:
                raise RuntimeError("baostock minute query failed for sz.000001: 10002007 网络接收错误")
        return [{"code": code, "date": "2026-06-24", "time": "20260624150000000"}]

    monkeypatch.setattr(minute_daily_ingest, "query_baostock_minute_rows_once", fake_query)
    monkeypatch.setattr(minute_daily_ingest, "relogin_or_raise", lambda timeout_seconds=None: None)
    monkeypatch.setattr(minute_daily_ingest, "upsert_stock_minute_bars", lambda rows, freq, adjust_type, params=None: 1)

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2026-06-24",
        retry_limit=0,
        output_dir=tmp_path,
    )

    assert result["status"] == "success"
    assert calls == ["sh.600000", "sz.000001", "sz.000001"]
    assert result["failed_symbols"] == []


def test_run_baostock_minute_daily_relogins_after_three_consecutive_failed_symbols(monkeypatch, tmp_path: Path):
    state = {"relogin": 0}
    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: type("Decision", (), {"should_run": True, "reason": "trading_day", "calendar_status": "open"})(),
    )
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: object())
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(minute_daily_ingest, "load_active_baostock_codes", lambda limit_assets=None: ["sh.600000", "sz.000001", "bj.430047"])
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda timeout_seconds=None: None)
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: None)
    monkeypatch.setattr(minute_daily_ingest.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "query_baostock_minute_rows_once",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("baostock minute query failed for code: 10002007 网络接收错误")
        ),
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "relogin_or_raise",
        lambda timeout_seconds=None: state.__setitem__("relogin", state["relogin"] + 1),
    )

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2026-06-24",
        retry_limit=0,
        output_dir=tmp_path,
    )

    assert result["status"] == "partial"
    assert result["failed_count"] == 3
    assert result["relogin_count"] == 1
    assert state["relogin"] == 1


def test_run_baostock_minute_daily_enters_cooldown_after_failure_burst(monkeypatch, tmp_path: Path):
    sleeps = []
    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: type("Decision", (), {"should_run": True, "reason": "trading_day", "calendar_status": "open"})(),
    )
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: object())
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(minute_daily_ingest, "load_active_baostock_codes", lambda limit_assets=None: ["sh.600000", "sz.000001", "bj.430047"])
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda timeout_seconds=None: None)
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: None)
    monkeypatch.setattr(minute_daily_ingest.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        minute_daily_ingest,
        "query_baostock_minute_rows_once",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("baostock minute query failed for sh.600000: 10002007 网络接收错误")
        ),
    )
    monkeypatch.setattr(minute_daily_ingest, "relogin_or_raise", lambda timeout_seconds=None: None)

    minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2026-06-24",
        retry_limit=0,
        cooldown_seconds=600,
        output_dir=tmp_path,
    )

    assert 600 in sleeps


def test_run_baostock_minute_daily_writes_summary_and_failed_symbols(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: type("Decision", (), {"should_run": True, "reason": "trading_day", "calendar_status": "open"})(),
    )
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: object())
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(minute_daily_ingest, "load_active_baostock_codes", lambda limit_assets=None: ["sh.600000"])
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda timeout_seconds=None: None)
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: None)
    monkeypatch.setattr(minute_daily_ingest.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "query_baostock_minute_rows_once",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("baostock minute query failed for sh.600000: 10002007 网络接收错误")
        ),
    )
    monkeypatch.setattr(minute_daily_ingest, "relogin_or_raise", lambda timeout_seconds=None: None)

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2026-06-24",
        output_dir=tmp_path,
    )

    summary_path = tmp_path / "baostock_minute_daily" / "2026-06-24" / "summary.json"
    failed_path = tmp_path / "baostock_minute_daily" / "2026-06-24" / "failed_symbols.txt"
    assert result["status"] == "partial"
    assert json.loads(summary_path.read_text(encoding="utf-8"))["failed_symbols"] == ["sh.600000"]
    assert failed_path.read_text(encoding="utf-8").strip() == "sh.600000"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_retries_same_session_before_relogin tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_retries_failed_symbols_only_in_retry_queue tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_relogins_after_three_consecutive_failed_symbols tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_enters_cooldown_after_failure_burst tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_writes_summary_and_failed_symbols -q
```

Expected: FAIL because the current runner does not own retry thresholds, partial status, cooldown, or artifact output yet.

- [ ] **Step 3: Implement session-first retry, relogin threshold, cooldown, and artifact writing**

```python
def _write_daily_artifacts(result: dict[str, Any], output_dir: str | Path) -> None:
    day_dir = Path(output_dir) / "baostock_minute_daily" / str(result["trade_date"])
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (day_dir / "failed_symbols.txt").write_text(
        "\n".join(result["failed_symbols"]) + ("\n" if result["failed_symbols"] else ""),
        encoding="utf-8",
    )


def _fetch_symbol_with_policy(
    code: str,
    trade_date: dt.date,
    *,
    freq: str,
    adjust_type: str,
    retry_limit: int,
    timeout_seconds: float | None,
) -> tuple[list[dict[str, str]] | None, int, str | None]:
    retry_count = 0
    last_error: str | None = None
    for attempt in range(retry_limit + 1):
        try:
            return (
                query_baostock_minute_rows_once(
                    code,
                    trade_date,
                    trade_date,
                    freq=freq,
                    adjust_type=adjust_type,
                    timeout_seconds=timeout_seconds,
                ),
                retry_count,
                None,
            )
        except RuntimeError as exc:
            last_error = str(exc)
            if not is_retryable_baostock_error(last_error) or attempt >= retry_limit:
                return None, retry_count, last_error
            retry_count += 1
            time.sleep(float(retry_count))
    return None, retry_count, last_error


def _run_retry_queue(
    retry_queue: list[str],
    trade_date: dt.date,
    *,
    freq: str,
    adjust_type: str,
    retry_limit: int,
    timeout_seconds: float | None,
    result: dict[str, Any],
) -> tuple[list[str], int]:
    remaining: list[str] = []
    recovered = 0
    for code in retry_queue:
        rows, retry_count, error = _fetch_symbol_with_policy(
            code,
            trade_date,
            freq=freq,
            adjust_type=adjust_type,
            retry_limit=retry_limit,
            timeout_seconds=timeout_seconds,
        )
        result["retry_count"] += retry_count
        if error is None:
            params = {
                "source": "baostock_daily",
                "trade_date": trade_date.isoformat(),
                "baostock_code": code,
            }
            inserted = upsert_stock_minute_bars(
                rows or [],
                freq=freq,
                adjust_type=adjust_type,
                params=params,
            )
            if inserted:
                result["success_count"] += 1
                result["rows_written"] += inserted
            else:
                result["empty_count"] += 1
            recovered += 1
        else:
            result["last_error"] = error
            remaining.append(code)
    return remaining, recovered


def run_baostock_minute_daily(
    trade_date: str | None = None,
    freq: str = "5min",
    adjust_type: str = "raw",
    sleep_seconds: float = 1.0,
    retry_limit: int = 2,
    cooldown_seconds: int = 600,
    timeout_seconds: float | None = None,
    output_dir: str | Path = "outputs/research",
    lock_path: str | Path = DEFAULT_MINUTE_DAILY_LOCK,
    limit_assets: int | None = None,
) -> dict[str, Any]:
    target_date = parse_trade_date(trade_date, "Asia/Shanghai")
    decision = decide_stock_cron_run(
        service=SETTINGS.research_service,
        trade_date=target_date,
        exchanges=("SH", "SZ", "BJ"),
    )
    if not decision.should_run:
        result = {
            "status": "skipped_non_trading_day",
            "trade_date": target_date.isoformat(),
            "symbol_count": 0,
            "success_count": 0,
            "empty_count": 0,
            "failed_count": 0,
            "retry_count": 0,
            "relogin_count": 0,
            "rows_written": 0,
            "failed_symbols": [],
            "last_error": "",
        }
        _write_daily_artifacts(result, output_dir)
        return result

    lock_handle = _try_acquire_daily_lock(lock_path)
    if lock_handle is None:
        result = {
            "status": "skipped_locked",
            "trade_date": target_date.isoformat(),
            "symbol_count": 0,
            "success_count": 0,
            "empty_count": 0,
            "failed_count": 0,
            "retry_count": 0,
            "relogin_count": 0,
            "rows_written": 0,
            "failed_symbols": [],
            "last_error": "",
        }
        _write_daily_artifacts(result, output_dir)
        return result

    codes = load_active_baostock_codes(limit_assets=limit_assets)
    result = {
        "status": "success",
        "trade_date": target_date.isoformat(),
        "symbol_count": len(codes),
        "success_count": 0,
        "empty_count": 0,
        "failed_count": 0,
        "retry_count": 0,
        "relogin_count": 0,
        "rows_written": 0,
        "failed_symbols": [],
        "last_error": "",
    }
    consecutive_retryable_failures = 0
    retry_queue: list[str] = []
    try:
        login_or_raise(timeout_seconds=timeout_seconds)
        for code in codes:
            rows, retry_count, error = _fetch_symbol_with_policy(
                code,
                target_date,
                freq=freq,
                adjust_type=adjust_type,
                retry_limit=retry_limit,
                timeout_seconds=timeout_seconds,
            )
            result["retry_count"] += retry_count
            if error is None:
                consecutive_retryable_failures = 0
                params = {
                    "source": "baostock_daily",
                    "trade_date": target_date.isoformat(),
                    "baostock_code": code,
                }
                inserted = upsert_stock_minute_bars(
                    rows or [],
                    freq=freq,
                    adjust_type=adjust_type,
                    params=params,
                )
                if inserted:
                    result["success_count"] += 1
                    result["rows_written"] += inserted
                else:
                    result["empty_count"] += 1
            else:
                retry_queue.append(code)
                result["last_error"] = error
                if is_retryable_baostock_error(error):
                    consecutive_retryable_failures += 1
                if consecutive_retryable_failures >= RELOGIN_FAILURE_THRESHOLD:
                    relogin_or_raise(timeout_seconds=timeout_seconds)
                    result["relogin_count"] += 1
                    consecutive_retryable_failures = 0
                    time.sleep(cooldown_seconds)
            if sleep_seconds:
                time.sleep(sleep_seconds)
        if retry_queue:
            remaining_failures, recovered = _run_retry_queue(
                retry_queue,
                target_date,
                freq=freq,
                adjust_type=adjust_type,
                retry_limit=retry_limit,
                timeout_seconds=timeout_seconds,
                result=result,
            )
            result["failed_symbols"] = remaining_failures
            result["failed_count"] = len(remaining_failures)
        if result["failed_count"] > 0:
            result["status"] = "partial"
    finally:
        try:
            bs.logout()
        except Exception:
            pass
        _release_daily_lock(lock_handle)
        _write_daily_artifacts(result, output_dir)
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_retries_same_session_before_relogin tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_retries_failed_symbols_only_in_retry_queue tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_relogins_after_three_consecutive_failed_symbols tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_enters_cooldown_after_failure_burst tests/test_minute_daily_ingest.py::test_run_baostock_minute_daily_writes_summary_and_failed_symbols -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/minute_daily_ingest.py tests/test_minute_daily_ingest.py
git commit -m "feat: add baostock minute daily retry policy"
```

### Task 4: Add CLI Wiring And Cron Script

**Files:**
- Modify: `/Users/xiwei/stock_research/src/stock_research/cli.py`
- Create: `/Users/xiwei/stock_research/scripts/run_baostock_minute_daily_cron.sh`
- Create: `/Users/xiwei/stock_research/tests/test_minute_daily_ingest_cli.py`
- Create: `/Users/xiwei/stock_research/tests/test_minute_daily_scripts.py`

- [ ] **Step 1: Write the failing CLI and shell-script tests**

```python
from types import SimpleNamespace
import os
import subprocess
from pathlib import Path

from stock_research import cli


def test_cli_run_baostock_minute_daily_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_baostock_minute_daily",
        lambda **kwargs: {
            "status": "success",
            "trade_date": "2026-06-24",
            "symbol_count": 2,
            "success_count": 2,
            "empty_count": 0,
            "failed_count": 0,
            "retry_count": 1,
            "relogin_count": 0,
            "rows_written": 96,
            "failed_symbols": [],
        },
    )

    rc = cli.main(["run-baostock-minute-daily", "--trade-date", "2026-06-24"])

    captured = capsys.readouterr()
    assert rc == 0
    assert "minute_daily|status|success" in captured.out
    assert "minute_daily|trade_date|2026-06-24" in captured.out
    assert "minute_daily|rows_written|96" in captured.out


def test_run_baostock_minute_daily_cron_script_clears_proxy_and_calls_cli(tmp_path: Path):
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"
    fake_python.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls_file}"
for name in HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy; do
  value="${{!name:-}}"
  if [[ -n "$value" ]]; then
    echo "proxy-leak:$name=$value" >&2
    exit 9
  fi
done
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": str(fake_python),
            "TRADE_DATE": "2026-06-24",
            "HTTP_PROXY": "http://127.0.0.1:7890",
            "HTTPS_PROXY": "http://127.0.0.1:7890",
            "ALL_PROXY": "socks5://127.0.0.1:7890",
            "http_proxy": "http://127.0.0.1:7890",
            "https_proxy": "http://127.0.0.1:7890",
            "all_proxy": "socks5://127.0.0.1:7890",
        }
    )

    result = subprocess.run(
        ["scripts/run_baostock_minute_daily_cron.sh"],
        cwd="/Users/xiwei/stock_research",
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.stock_cron_guard --date 2026-06-24" in calls
    assert "-m stock_research.cli run-baostock-minute-daily --trade-date 2026-06-24" in calls
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_minute_daily_ingest_cli.py::test_cli_run_baostock_minute_daily_prints_summary tests/test_minute_daily_scripts.py::test_run_baostock_minute_daily_cron_script_clears_proxy_and_calls_cli -q
```

Expected: FAIL because the CLI command and cron wrapper do not exist yet.

- [ ] **Step 3: Add the new CLI command and cron wrapper**

```python
# cli.py imports
from stock_research.minute_daily_ingest import run_baostock_minute_daily


# cli.py parser section
run_minute_daily = subparsers.add_parser("run-baostock-minute-daily")
run_minute_daily.add_argument("--trade-date")
run_minute_daily.add_argument("--freq", default="5min")
run_minute_daily.add_argument("--adjust-type", default="raw")
run_minute_daily.add_argument("--sleep-seconds", type=float, default=1.0)
run_minute_daily.add_argument("--retry-limit", type=int, default=2)
run_minute_daily.add_argument("--cooldown-seconds", type=int, default=600)
run_minute_daily.add_argument("--timeout-seconds", type=float)
run_minute_daily.add_argument("--output-dir", default="outputs/research")
run_minute_daily.add_argument("--limit-assets", type=int)


# cli.py dispatch section
elif args.command == "run-baostock-minute-daily":
    result = run_baostock_minute_daily(
        trade_date=args.trade_date,
        freq=args.freq,
        adjust_type=args.adjust_type,
        sleep_seconds=args.sleep_seconds,
        retry_limit=args.retry_limit,
        cooldown_seconds=args.cooldown_seconds,
        timeout_seconds=args.timeout_seconds,
        output_dir=args.output_dir,
        limit_assets=args.limit_assets,
    )
    for key, value in result.items():
        if key == "failed_symbols":
            print(f"minute_daily|{key}|{','.join(value)}")
        else:
            print(f"minute_daily|{key}|{value}")
```

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-}"
LOG_DIR="$ROOT/logs/minute_daily"
RUN_DATE="${TRADE_DATE:-$(date +%F)}"
LOG_FILE="$LOG_DIR/baostock_minute_daily_${RUN_DATE}.log"

mkdir -p "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env
stock_cron_guard_or_exit "$PYTHON_BIN" "$TRADE_DATE" "${RESEARCH_SERVICE:-}"

echo "minute_daily_cron|start|trade_date|${TRADE_DATE:-auto}"
if [[ -n "${TRADE_DATE}" ]]; then
  "$PYTHON_BIN" -m stock_research.cli run-baostock-minute-daily --trade-date "$TRADE_DATE"
else
  "$PYTHON_BIN" -m stock_research.cli run-baostock-minute-daily
fi
echo "minute_daily_cron|done|trade_date|${TRADE_DATE:-auto}"
```

- [ ] **Step 4: Run the tests and smoke checks to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_minute_daily_ingest_cli.py::test_cli_run_baostock_minute_daily_prints_summary tests/test_minute_daily_scripts.py::test_run_baostock_minute_daily_cron_script_clears_proxy_and_calls_cli tests/test_minute_daily_ingest.py tests/test_minute_data.py -q
```

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/python -m stock_research.cli run-baostock-minute-daily --help
```

Expected: pytest PASS, then CLI help prints the new `run-baostock-minute-daily` options.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/cli.py scripts/run_baostock_minute_daily_cron.sh tests/test_minute_daily_ingest_cli.py tests/test_minute_daily_scripts.py
git commit -m "feat: add baostock minute daily cli and cron wrapper"
```
