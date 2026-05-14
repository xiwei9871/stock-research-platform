import subprocess
import time
from pathlib import Path

ROOT = Path('/Users/xiwei/stock_research')
PY = ROOT / '.venv/bin/python'
LOG = ROOT / 'logs/minute_backfill_resume_202401.log'
STATUS_CMD = [
    str(PY), '-m', 'stock_research.cli', 'baostock-minute-backfill-status', '--output-dir', 'outputs/research'
]
RUN_CMD = [
    str(PY), '-m', 'stock_research.cli', 'run-baostock-minute-backfill',
    '--start-date', '2024-01-01',
    '--end-date', '2024-01-31',
    '--freq', '5min',
    '--adjust-types', 'raw,qfq',
    '--batch-by', 'month',
    '--max-jobs', '100',
    '--retry-failed',
    '--sleep-seconds', '0.05',
    '--workers', '1',
]


def run(cmd, timeout=None):
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def parse_status(text):
    data = {}
    for line in text.splitlines():
        if line.startswith('minute_backfill_status|'):
            _, key, value = line.split('|', 2)
            data[key] = value
    return data


with LOG.open('a') as log:
    log.write(f'=== resume start {time.strftime("%Y-%m-%d %H:%M:%S %z")} ===\n')
    while True:
        status = run(STATUS_CMD, timeout=120)
        log.write(status.stdout)
        if status.returncode != 0:
            log.write(status.stderr)
            break
        parsed = parse_status(status.stdout)
        pending = int(parsed.get('pending_jobs', '0'))
        failed = int(parsed.get('failed_jobs', '0'))
        running = int(parsed.get('running_jobs', '0'))
        success = int(parsed.get('success_jobs', '0'))
        log.write(f'status_snapshot|success={success}|pending={pending}|failed={failed}|running={running}\n')
        log.flush()
        if pending == 0 and failed == 0 and running == 0:
            break
        try:
            batch = run(RUN_CMD, timeout=1200)
            log.write(batch.stdout)
            log.write(batch.stderr)
            log.flush()
            if batch.returncode != 0:
                log.write(f'batch_returncode={batch.returncode}\n')
                time.sleep(5)
            else:
                time.sleep(2)
        except subprocess.TimeoutExpired as exc:
            if exc.stdout:
                log.write(exc.stdout)
            if exc.stderr:
                log.write(exc.stderr)
            log.write('batch_timeout_expired=1200\n')
            log.flush()
            time.sleep(5)
    log.write(f'=== resume end {time.strftime("%Y-%m-%d %H:%M:%S %z")} ===\n')
