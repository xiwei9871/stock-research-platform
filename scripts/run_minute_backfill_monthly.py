import datetime as dt
import time
from pathlib import Path

from stock_research.config import SETTINGS
from stock_research.feishu_notify import send_openclaw_feishu_message
from stock_research.minute_backfill import (
    load_backfill_status_rows,
    month_ranges,
    plan_baostock_minute_backfill,
    run_baostock_minute_backfill,
    summarize_backfill_status,
    validate_minute_bars,
)

ROOT = Path('/Users/xiwei/stock_research')
LOG = ROOT / 'logs/minute_backfill_monthly.log'
START = dt.date(2024, 1, 1)
END = dt.date(2026, 5, 13)
FREQ = '5min'
ADJUST_TYPES = ['raw', 'qfq']
REPORT_TARGET = 'chat:oc_82dd978138a0cde5864868c5b5b8e754'


def month_label(start: dt.date) -> str:
    return start.strftime('%Y-%m')


def month_summary(start: dt.date, end: dt.date) -> dict:
    rows = load_backfill_status_rows(start_date=start, end_date=end, freq=FREQ, adjust_types=ADJUST_TYPES)
    return summarize_backfill_status(rows)


def send_month_report(summary: dict, validation: dict) -> None:
    month = summary['month']
    message = (
        f"minute_backfill_month_done|{month}\n"
        f"jobs_total={summary['job_summary']['total_jobs']}\n"
        f"jobs_success={summary['job_summary']['success_jobs']}\n"
        f"jobs_failed={summary['job_summary']['failed_jobs']}\n"
        f"market_rows={summary['job_summary']['total_market_rows']}\n"
        f"staging_rows={summary['job_summary']['total_staging_rows']}\n"
        f"validation_errors={validation['summary']['error_count']}"
    )
    send_openclaw_feishu_message(
        message=message,
        target=REPORT_TARGET,
        account='jarvis',
        openclaw_bin='openclaw',
        dry_run=False,
    )


def main() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a') as log:
        log.write(f'=== monthly backfill start: {time.strftime("%Y-%m-%d %H:%M:%S %z")} ===\n')
        for month_start, month_end in month_ranges(START, END):
            label = month_label(month_start)
            log.write(f'--- month {label} {month_start}..{month_end} ---\n')
            log.flush()
            plan_baostock_minute_backfill(
                start_date=month_start.isoformat(),
                end_date=month_end.isoformat(),
                freq=FREQ,
                adjust_types=ADJUST_TYPES,
                batch_by='month',
                output_dir='outputs/research',
            )
            while True:
                summary = month_summary(month_start, month_end)
                log.write(
                    f"status|{label}|success={summary['success_jobs']}|pending={summary['pending_jobs']}|failed={summary['failed_jobs']}|running={summary['running_jobs']}\n"
                )
                log.flush()
                if summary['pending_jobs'] == 0 and summary['failed_jobs'] == 0 and summary['running_jobs'] == 0:
                    break
                result = run_baostock_minute_backfill(
                    start_date=month_start.isoformat(),
                    end_date=month_end.isoformat(),
                    freq=FREQ,
                    adjust_types=ADJUST_TYPES,
                    batch_by='month',
                    max_jobs=100,
                    retry_failed=True,
                    sleep_seconds=0.05,
                    workers=1,
                )
                log.write(
                    f"run|{label}|attempted={result['attempted']}|success={result['success']}|failed={result['failed']}|rows={result['rows']}\n"
                )
                log.flush()
                if result['attempted'] == 0:
                    time.sleep(2)
            validation = validate_minute_bars(
                start_date=month_start.isoformat(),
                end_date=month_end.isoformat(),
                freq=FREQ,
                adjust_types=ADJUST_TYPES,
                output_dir='outputs/research',
            )
            report_summary = {
                'month': label,
                'start_date': month_start.isoformat(),
                'end_date': month_end.isoformat(),
                'job_summary': summary,
                'validation_summary': validation['summary'],
            }
            send_month_report(report_summary, validation)
            log.write(
                f"done|{label}|jobs={summary['total_jobs']}|success={summary['success_jobs']}|pending={summary['pending_jobs']}|failed={summary['failed_jobs']}|validation_errors={validation['summary']['error_count']}\n"
            )
            log.flush()
        log.write(f'=== monthly backfill end: {time.strftime("%Y-%m-%d %H:%M:%S %z")} ===\n')


if __name__ == '__main__':
    main()
