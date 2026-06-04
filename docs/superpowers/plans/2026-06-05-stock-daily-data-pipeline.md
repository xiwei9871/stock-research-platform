# Stock Daily Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a scheduled daily A-share data pipeline wrapper that runs existing daily refresh commands, records per-step status, and sends Feishu progress reports through OpenClaw.

**Architecture:** Add a small orchestration module that owns the daily step contract and report rendering, plus a host shell script used by OpenClaw cron. The implementation should reuse existing CLI commands first and mark unavailable adapters as explicit skipped steps. OpenClaw `jobs.json` gets one daily cron job that calls the host script; weekly/monthly/quarterly jobs are outside this implementation plan and will reuse the same reporting module when they are implemented.

**Tech Stack:** Python 3.14, pandas where needed, existing `stock_research.cli`, existing `stock_research.feishu_notify.send_openclaw_feishu_message`, Bash host scripts, OpenClaw cron JSON.

---

## File Structure

- Create: `src/stock_research/daily_data_pipeline.py`
  - Owns step definitions, command execution, JSON summary writing, and Feishu message rendering.
- Create: `tests/test_daily_data_pipeline.py`
  - Unit tests for window calculation, step execution, summary shape, Feishu message rendering, and failure behavior.
- Create: `scripts/run_stock_daily_data_pipeline.sh`
  - Host wrapper used by OpenClaw cron. Sets environment defaults, runs the Python CLI, and writes host logs.
- Modify: `src/stock_research/cli.py`
  - Add `run-stock-daily-data-pipeline` parser and command dispatch.
- Modify: `/Users/xiwei/.openclaw/cron/jobs.json`
  - Add `stock-daily-data-pipeline` cron job.
- Modify: `tests/test_minute_backfill_watchdog.py`
  - Add an assertion that OpenClaw cron includes the new daily data job.
- Create: `docs/stock-daily-data-pipeline-runbook.md`
  - Operator runbook with dry-run, live-run, and Feishu-report examples.

## Task 1: Daily Pipeline Data Contracts

**Files:**
- Create: `src/stock_research/daily_data_pipeline.py`
- Test: `tests/test_daily_data_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Add:

```python
from pathlib import Path

from stock_research.daily_data_pipeline import (
    DailyPipelineStep,
    build_daily_pipeline_steps,
    derive_daily_windows,
    render_daily_pipeline_feishu_message,
)


def test_derive_daily_windows_uses_short_daily_lookbacks() -> None:
    windows = derive_daily_windows("2026-06-05")

    assert windows["trade_date"] == "2026-06-05"
    assert windows["market_start_date"] == "2026-05-31"
    assert windows["minute_start_date"] == "2026-05-31"
    assert windows["lhb_start_date"] == "2026-05-26"
    assert windows["announcement_start_date"] == "2026-05-22"
    assert windows["earnings_start_date"] == "2026-04-21"
    assert windows["repurchase_start_date"] == "2026-03-07"


def test_build_daily_pipeline_steps_lists_required_initial_steps() -> None:
    steps = build_daily_pipeline_steps(trade_date="2026-06-05", output_dir=Path("outputs/daily"))

    assert [step.name for step in steps] == [
        "start_report",
        "market_daily_refresh",
        "minute_incremental_refresh",
        "daily_event_refresh",
        "daily_feature_build",
        "daily_report_delivery",
    ]
    assert all(isinstance(step, DailyPipelineStep) for step in steps)
    assert steps[0].required is False
    assert steps[1].required is True


def test_render_daily_pipeline_feishu_message_is_mobile_sized() -> None:
    message = render_daily_pipeline_feishu_message(
        trade_date="2026-06-05",
        status="partial_failed",
        output_dir=Path("outputs/daily/20260605"),
        step_results=[
            {"step": "market_daily_refresh", "status": "success", "rows": 5200, "error": ""},
            {"step": "daily_event_refresh", "status": "partial_failed", "rows": 45, "error": "lhb failed"},
        ],
    )

    assert "A股日频数据任务" in message
    assert "2026-06-05" in message
    assert "market_daily_refresh: success rows=5200" in message
    assert "daily_event_refresh: partial_failed rows=45 error=lhb failed" in message
    assert "outputs/daily/20260605" in message
    assert len(message) < 1800
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/pytest -q tests/test_daily_data_pipeline.py
```

Expected: fail with `ModuleNotFoundError: No module named 'stock_research.daily_data_pipeline'`.

- [ ] **Step 3: Implement minimal data contracts**

Create `src/stock_research/daily_data_pipeline.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DailyPipelineStep:
    name: str
    command: list[str]
    required: bool = True
    timeout_seconds: int = 1800


def _date_minus_days(value: str, days: int) -> str:
    parsed = date.fromisoformat(value)
    return (parsed - timedelta(days=days)).isoformat()


def derive_daily_windows(trade_date: str) -> dict[str, str]:
    return {
        "trade_date": trade_date,
        "market_start_date": _date_minus_days(trade_date, 5),
        "minute_start_date": _date_minus_days(trade_date, 5),
        "lhb_start_date": _date_minus_days(trade_date, 10),
        "announcement_start_date": _date_minus_days(trade_date, 14),
        "earnings_start_date": _date_minus_days(trade_date, 45),
        "repurchase_start_date": _date_minus_days(trade_date, 90),
    }


def build_daily_pipeline_steps(*, trade_date: str, output_dir: Path) -> list[DailyPipelineStep]:
    windows = derive_daily_windows(trade_date)
    python = "./.venv/bin/python"
    return [
        DailyPipelineStep(name="start_report", command=[], required=False, timeout_seconds=60),
        DailyPipelineStep(
            name="market_daily_refresh",
            command=[
                python,
                "-m",
                "stock_research.cli",
                "run-daily-incremental",
                "--trade-date",
                trade_date,
                "--record-run",
                "--apply-daily-run-schema",
            ],
            timeout_seconds=3600,
        ),
        DailyPipelineStep(
            name="minute_incremental_refresh",
            command=[
                python,
                "-m",
                "stock_research.cli",
                "backfill-watchdog",
                "--adapter",
                "minute",
                "--start-date",
                windows["minute_start_date"],
                "--end-date",
                trade_date,
                "--freq",
                "5min",
                "--adjust-types",
                "raw,qfq",
                "--max-jobs",
                "400",
                "--workers",
                "4",
                "--run-timeout-seconds",
                "1800",
            ],
            timeout_seconds=2100,
        ),
        DailyPipelineStep(
            name="daily_event_refresh",
            command=[
                python,
                "-m",
                "stock_research.cli",
                "free-enrichment-backfill",
                "--dataset",
                "lhb",
                "--start-date",
                windows["lhb_start_date"],
                "--end-date",
                trade_date,
                "--output-dir",
                str(output_dir / "free_enrichment_lhb"),
                "--batch-size",
                "1",
                "--sleep-seconds",
                "0",
            ],
            timeout_seconds=1800,
        ),
        DailyPipelineStep(
            name="daily_feature_build",
            command=[
                python,
                "-m",
                "stock_research.cli",
                "run-daily-factor-pipeline",
                "--trade-date",
                trade_date,
                "--reports-dir",
                str(output_dir / "reports"),
            ],
            timeout_seconds=1800,
        ),
        DailyPipelineStep(name="daily_report_delivery", command=[], required=False, timeout_seconds=120),
    ]


def render_daily_pipeline_feishu_message(
    *,
    trade_date: str,
    status: str,
    output_dir: Path,
    step_results: list[dict[str, Any]],
) -> str:
    lines = [
        f"A股日频数据任务 {trade_date}",
        f"status: {status}",
        f"output: {output_dir}",
        "",
        "steps:",
    ]
    for item in step_results:
        line = f"- {item['step']}: {item['status']} rows={item.get('rows', 0)}"
        if item.get("error"):
            line += f" error={item['error']}"
        lines.append(line)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./.venv/bin/pytest -q tests/test_daily_data_pipeline.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/daily_data_pipeline.py tests/test_daily_data_pipeline.py
git commit -m "feat: add daily data pipeline contracts"
```

## Task 2: Step Runner and Summary Writer

**Files:**
- Modify: `src/stock_research/daily_data_pipeline.py`
- Test: `tests/test_daily_data_pipeline.py`

- [ ] **Step 1: Write failing tests for command execution and summary writing**

Append:

```python
import json

from stock_research.daily_data_pipeline import run_stock_daily_data_pipeline


def test_run_stock_daily_data_pipeline_records_success_and_failure(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(command: list[str], timeout_seconds: int) -> dict[str, object]:
        calls.append(command)
        if "free-enrichment-backfill" in command:
            return {"returncode": 1, "stdout": "failed output", "stderr": "lhb failed"}
        return {"returncode": 0, "stdout": "rows|12", "stderr": ""}

    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=fake_runner,
        send_feishu=False,
    )

    assert result["status"] == "partial_failed"
    assert len(result["steps"]) == 6
    assert any(step["step"] == "daily_event_refresh" and step["status"] == "failed" for step in result["steps"])
    assert calls
    summary = json.loads((tmp_path / "run_summary.json").read_text())
    assert summary["trade_date"] == "2026-06-05"
    assert summary["status"] == "partial_failed"


def test_run_stock_daily_data_pipeline_can_skip_feishu(tmp_path: Path) -> None:
    sent: list[str] = []

    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=lambda command, timeout_seconds: {"returncode": 0, "stdout": "", "stderr": ""},
        feishu_sender=lambda message: sent.append(message),
        send_feishu=False,
    )

    assert result["status"] == "success"
    assert sent == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/pytest -q tests/test_daily_data_pipeline.py::test_run_stock_daily_data_pipeline_records_success_and_failure tests/test_daily_data_pipeline.py::test_run_stock_daily_data_pipeline_can_skip_feishu
```

Expected: fail because `run_stock_daily_data_pipeline` is not defined.

- [ ] **Step 3: Implement minimal runner**

Add to `src/stock_research/daily_data_pipeline.py`:

```python
import json
import subprocess


def _default_command_runner(command: list[str], timeout_seconds: int) -> dict[str, object]:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds)
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _step_rows(stdout: str) -> int:
    rows = 0
    for token in stdout.replace("\n", "|").split("|"):
        if token.isdigit():
            rows = int(token)
    return rows


def run_stock_daily_data_pipeline(
    *,
    trade_date: str,
    output_dir: str | Path,
    command_runner: Any = None,
    feishu_sender: Any = None,
    send_feishu: bool = True,
) -> dict[str, Any]:
    resolved_output_dir = Path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    runner = command_runner or _default_command_runner
    steps = build_daily_pipeline_steps(trade_date=trade_date, output_dir=resolved_output_dir)
    step_results: list[dict[str, Any]] = []

    for step in steps:
        if not step.command:
            step_results.append({"step": step.name, "status": "skipped", "rows": 0, "error": ""})
            continue
        try:
            outcome = runner(step.command, step.timeout_seconds)
            returncode = int(outcome.get("returncode", 1))
            stdout = str(outcome.get("stdout", ""))
            stderr = str(outcome.get("stderr", ""))
            status = "success" if returncode == 0 else "failed"
            step_results.append(
                {
                    "step": step.name,
                    "status": status,
                    "rows": _step_rows(stdout),
                    "error": "" if status == "success" else (stderr or stdout)[-500:],
                    "returncode": returncode,
                }
            )
        except Exception as exc:
            step_results.append(
                {"step": step.name, "status": "failed", "rows": 0, "error": str(exc), "returncode": 1}
            )

    failed_required = [
        item
        for item, step in zip(step_results, steps)
        if step.required and item["status"] == "failed"
    ]
    status = "partial_failed" if failed_required else "success"
    summary = {
        "trade_date": trade_date,
        "status": status,
        "output_dir": str(resolved_output_dir),
        "steps": step_results,
    }
    (resolved_output_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    message = render_daily_pipeline_feishu_message(
        trade_date=trade_date,
        status=status,
        output_dir=resolved_output_dir,
        step_results=step_results,
    )
    (resolved_output_dir / "feishu_message.txt").write_text(message + "\n", encoding="utf-8")
    if send_feishu and feishu_sender is not None:
        feishu_sender(message)
    return summary
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./.venv/bin/pytest -q tests/test_daily_data_pipeline.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/daily_data_pipeline.py tests/test_daily_data_pipeline.py
git commit -m "feat: run daily data pipeline steps"
```

## Task 3: CLI Entry Point

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI parser and dispatch tests**

Add to `tests/test_factor_cli.py`:

```python
def test_cli_accepts_run_stock_daily_data_pipeline_command():
    args = build_parser().parse_args(
        [
            "run-stock-daily-data-pipeline",
            "--trade-date",
            "2026-06-05",
            "--output-dir",
            "outputs/daily/20260605",
            "--no-feishu",
        ]
    )

    assert args.command == "run-stock-daily-data-pipeline"
    assert args.trade_date == "2026-06-05"
    assert args.output_dir == "outputs/daily/20260605"
    assert args.no_feishu is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_factor_cli.py::test_cli_accepts_run_stock_daily_data_pipeline_command
```

Expected: fail because the command is not registered.

- [ ] **Step 3: Add parser and dispatch**

In `src/stock_research/cli.py`, import:

```python
from stock_research.daily_data_pipeline import run_stock_daily_data_pipeline
```

Near existing daily commands, add:

```python
    stock_daily_data_pipeline = subparsers.add_parser("run-stock-daily-data-pipeline")
    stock_daily_data_pipeline.add_argument("--trade-date", required=True)
    stock_daily_data_pipeline.add_argument("--output-dir", required=True)
    stock_daily_data_pipeline.add_argument("--feishu-target")
    stock_daily_data_pipeline.add_argument("--feishu-account", default="jarvis")
    stock_daily_data_pipeline.add_argument("--openclaw-bin", default="openclaw")
    stock_daily_data_pipeline.add_argument("--no-feishu", action="store_true")
```

In command dispatch, add:

```python
    elif args.command == "run-stock-daily-data-pipeline":
        def sender(message: str) -> None:
            if not args.feishu_target:
                return
            send_openclaw_feishu_message(
                message=message,
                target=args.feishu_target,
                account=args.feishu_account,
                openclaw_bin=args.openclaw_bin,
                dry_run=False,
            )

        result = run_stock_daily_data_pipeline(
            trade_date=args.trade_date,
            output_dir=args.output_dir,
            feishu_sender=sender,
            send_feishu=not args.no_feishu,
        )
        print(f"stock_daily_data_pipeline|status|{result['status']}")
        print(f"stock_daily_data_pipeline|summary|{args.output_dir}/run_summary.json")
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_factor_cli.py::test_cli_accepts_run_stock_daily_data_pipeline_command tests/test_daily_data_pipeline.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: expose stock daily data pipeline cli"
```

## Task 4: Host Script

**Files:**
- Create: `scripts/run_stock_daily_data_pipeline.sh`
- Test: `tests/test_stock_daily_data_pipeline_script.py`

- [ ] **Step 1: Write failing script test**

Create `tests/test_stock_daily_data_pipeline_script.py`:

```python
from pathlib import Path


def test_stock_daily_data_pipeline_host_script_uses_cli_entrypoint() -> None:
    script = Path("scripts/run_stock_daily_data_pipeline.sh").read_text()

    assert "run-stock-daily-data-pipeline" in script
    assert "STOCK_DAILY_PIPELINE_TRADE_DATE" in script
    assert "STOCK_DAILY_PIPELINE_FEISHU_TARGET" in script
    assert "logs/stock_daily_data_pipeline.host.log" in script
    assert "set -euo pipefail" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_stock_daily_data_pipeline_script.py
```

Expected: fail because the script does not exist.

- [ ] **Step 3: Create host script**

Create `scripts/run_stock_daily_data_pipeline.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_DAILY_PIPELINE_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_DAILY_PIPELINE_PYTHON:-$ROOT/.venv/bin/python}"
OPENCLAW_BIN="${STOCK_DAILY_PIPELINE_OPENCLAW_BIN:-/Users/xiwei/stock_research/scripts/openclaw_runtime_cli.sh}"
LOG_DIR="${STOCK_DAILY_PIPELINE_LOG_DIR:-$ROOT/logs}"
RUN_LOG="${STOCK_DAILY_PIPELINE_RUN_LOG:-$LOG_DIR/stock_daily_data_pipeline.host.log}"
TRADE_DATE="${STOCK_DAILY_PIPELINE_TRADE_DATE:-$(date +%F)}"
OUTPUT_DIR="${STOCK_DAILY_PIPELINE_OUTPUT_DIR:-$ROOT/outputs/research/stock_daily_data_pipeline/$TRADE_DATE}"
FEISHU_TARGET="${STOCK_DAILY_PIPELINE_FEISHU_TARGET:-chat:oc_82dd978138a0cde5864868c5b5b8e754}"
FEISHU_ACCOUNT="${STOCK_DAILY_PIPELINE_FEISHU_ACCOUNT:-jarvis}"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

{
  echo "=== stock daily data pipeline host run start: $(date '+%Y-%m-%d %H:%M:%S %z') ==="
  cd "$ROOT"
  "$PYTHON" -m stock_research.cli run-stock-daily-data-pipeline \
    --trade-date "$TRADE_DATE" \
    --output-dir "$OUTPUT_DIR" \
    --feishu-target "$FEISHU_TARGET" \
    --feishu-account "$FEISHU_ACCOUNT" \
    --openclaw-bin "$OPENCLAW_BIN"
  rc=$?
  echo "=== stock daily data pipeline host run end: $(date '+%Y-%m-%d %H:%M:%S %z') rc=$rc ==="
  exit "$rc"
} 2>&1 | tee -a "$RUN_LOG"
```

- [ ] **Step 4: Make executable and run tests**

Run:

```bash
chmod +x scripts/run_stock_daily_data_pipeline.sh
./.venv/bin/pytest -q tests/test_stock_daily_data_pipeline_script.py tests/test_daily_data_pipeline.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_stock_daily_data_pipeline.sh tests/test_stock_daily_data_pipeline_script.py
git commit -m "feat: add stock daily data pipeline host script"
```

## Task 5: OpenClaw Cron Job

**Files:**
- Modify: `/Users/xiwei/.openclaw/cron/jobs.json`
- Modify: `tests/test_minute_backfill_watchdog.py`

- [ ] **Step 1: Write failing cron test**

Add to `tests/test_minute_backfill_watchdog.py`:

```python
def test_cron_jobs_include_stock_daily_data_pipeline():
    jobs = json.loads(Path("/Users/xiwei/.openclaw/cron/jobs.json").read_text())["jobs"]
    job = next((item for item in jobs if item["name"] == "stock-daily-data-pipeline"), None)

    assert job is not None
    assert job["enabled"] is True
    assert job["agentId"] == "agent_jarvis"
    assert job["schedule"] == {
        "kind": "cron",
        "expr": "10 21 * * 1-5",
        "tz": "Asia/Shanghai",
    }
    assert job["delivery"] == {"mode": "none"}
    assert job["failureAlert"]["channel"] == "feishu"
    assert job["payload"]["kind"] == "agentTurn"
    assert job["payload"]["toolsAllow"] == ["exec"]
    assert job["payload"]["timeoutSeconds"] == 7200
    assert "/Users/xiwei/stock_research/scripts/run_stock_daily_data_pipeline.sh" in job["payload"]["message"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_minute_backfill_watchdog.py::test_cron_jobs_include_stock_daily_data_pipeline
```

Expected: fail because the job is absent.

- [ ] **Step 3: Backup and edit OpenClaw cron JSON**

Run:

```bash
cp /Users/xiwei/.openclaw/cron/jobs.json /Users/xiwei/.openclaw/cron/jobs.json.bak-stock-daily-data-pipeline-20260605
```

Add this object to the `jobs` array:

```json
{
  "id": "stock-daily-data-pipeline-20260605",
  "agentId": "agent_jarvis",
  "name": "stock-daily-data-pipeline",
  "enabled": true,
  "createdAtMs": 1780610400000,
  "schedule": {
    "kind": "cron",
    "expr": "10 21 * * 1-5",
    "tz": "Asia/Shanghai"
  },
  "sessionTarget": "isolated",
  "wakeMode": "now",
  "payload": {
    "kind": "agentTurn",
    "toolsAllow": ["exec"],
    "timeoutSeconds": 7200,
    "message": "你直接执行 A股日频数据管线。只运行 `/Users/xiwei/stock_research/scripts/run_stock_daily_data_pipeline.sh`。不要改代码，不要申请 approval，不要启动交互式任务。执行完成后只汇报脚本退出状态；飞书进度报告由脚本自己发送。"
  },
  "delivery": {
    "mode": "none"
  },
  "failureAlert": {
    "after": 1,
    "channel": "feishu",
    "to": "chat:oc_82dd978138a0cde5864868c5b5b8e754",
    "cooldownMs": 7200000,
    "mode": "announce",
    "accountId": "jarvis"
  },
  "state": {}
}
```

- [ ] **Step 4: Validate JSON and cron test**

Run:

```bash
python -m json.tool /Users/xiwei/.openclaw/cron/jobs.json >/tmp/openclaw-jobs.validated.json
./.venv/bin/pytest -q tests/test_minute_backfill_watchdog.py::test_cron_jobs_include_stock_daily_data_pipeline
```

Expected: both commands pass.

- [ ] **Step 5: Commit repo-side test**

The OpenClaw cron file is outside this repository and should not be committed here. Commit the repo test:

```bash
git add tests/test_minute_backfill_watchdog.py
git commit -m "test: assert stock daily pipeline cron job"
```

## Task 6: Runbook and Smoke Verification

**Files:**
- Create: `docs/stock-daily-data-pipeline-runbook.md`

- [ ] **Step 1: Write runbook**

Create:

````markdown
# Stock Daily Data Pipeline Runbook

## Dry Run Without Feishu

```bash
cd /Users/xiwei/stock_research
./.venv/bin/python -m stock_research.cli run-stock-daily-data-pipeline \
  --trade-date 2026-06-05 \
  --output-dir outputs/research/stock_daily_data_pipeline_smoke/2026-06-05 \
  --no-feishu
```

## Live Host Script

```bash
STOCK_DAILY_PIPELINE_TRADE_DATE=2026-06-05 \
STOCK_DAILY_PIPELINE_FEISHU_TARGET=chat:oc_82dd978138a0cde5864868c5b5b8e754 \
/Users/xiwei/stock_research/scripts/run_stock_daily_data_pipeline.sh
```

## Outputs

- `run_summary.json`
- `feishu_message.txt`
- `logs/stock_daily_data_pipeline.host.log`
- step-specific output directories under `outputs/research/stock_daily_data_pipeline/<trade_date>`

## Healthy Run

- `run_summary.json` has `status` equal to `success` or `partial_failed`.
- Required failed steps appear with `status=failed` and an error field.
- Feishu message includes the trade date, output directory, and every step status.
- No interactive process remains after the host script exits.

## Recovery

If the daily job fails before sending Feishu, OpenClaw `failureAlert` sends a failure notice. Inspect:

```bash
tail -100 /Users/xiwei/stock_research/logs/stock_daily_data_pipeline.host.log
cat /Users/xiwei/stock_research/outputs/research/stock_daily_data_pipeline/<trade-date>/run_summary.json
```
````

- [ ] **Step 2: Run smoke without Feishu**

Run:

```bash
./.venv/bin/python -m stock_research.cli run-stock-daily-data-pipeline \
  --trade-date 2026-06-05 \
  --output-dir outputs/research/stock_daily_data_pipeline_smoke/2026-06-05 \
  --no-feishu
```

Expected: exits 0 and writes `run_summary.json`. If data-source steps fail because a live endpoint is unavailable, `run_summary.json` should show `partial_failed` with the failed step error.

- [ ] **Step 3: Run final tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_daily_data_pipeline.py tests/test_stock_daily_data_pipeline_script.py tests/test_factor_cli.py::test_cli_accepts_run_stock_daily_data_pipeline_command tests/test_minute_backfill_watchdog.py::test_cron_jobs_include_stock_daily_data_pipeline
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add docs/stock-daily-data-pipeline-runbook.md
git commit -m "docs: add stock daily data pipeline runbook"
```

## Self-Review Checklist

- Spec coverage: daily cadence, OpenClaw cron, Feishu report, rolling windows, and low-frequency exclusions are covered by tasks.
- Placeholder scan: this plan uses concrete paths, commands, schedules, and code snippets.
- Type consistency: `DailyPipelineStep`, `derive_daily_windows`, `build_daily_pipeline_steps`, `render_daily_pipeline_feishu_message`, and `run_stock_daily_data_pipeline` are consistently named across tasks.
- Risk: `run-daily-incremental` may overlap with feature/factor commands. Keep the first implementation conservative; the smoke run and summary make duplicate or failed steps visible before enabling live cron.
