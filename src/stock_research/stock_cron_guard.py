from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import date

from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.daily_close_pipeline import (
    PipelineConfig,
    format_trade_date,
    load_local_tushare_token,
    parse_trade_date,
    trading_calendar_status,
)
from stock_research.dimensions import upsert_trading_calendar

SKIP_EXIT_CODE = 2


@dataclass(frozen=True)
class StockCronGuardDecision:
    trade_date: date
    calendar_status: str
    should_run: bool
    reason: str


def _truthy_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def decide_stock_cron_run(
    *,
    service: str,
    trade_date: date,
    exchanges: tuple[str, ...] = ("SH", "SZ"),
    force: bool = False,
    sync_missing_calendar: bool = True,
) -> StockCronGuardDecision:
    if force:
        return StockCronGuardDecision(
            trade_date=trade_date,
            calendar_status="forced",
            should_run=True,
            reason="forced",
        )
    status = trading_calendar_status(service, trade_date, exchanges=exchanges)
    if status == "unknown" and sync_missing_calendar:
        try:
            refresh_trading_calendar_from_tushare(
                service=service,
                trade_date=trade_date,
                exchanges=exchanges,
            )
        except Exception:  # noqa: BLE001 - cron guard should fail closed on source outages.
            pass
        status = trading_calendar_status(service, trade_date, exchanges=exchanges)
    if status == "open":
        return StockCronGuardDecision(
            trade_date=trade_date,
            calendar_status=status,
            should_run=True,
            reason="trading_day",
        )
    if status == "closed":
        reason = "non_trading_day"
    else:
        reason = "missing_trading_calendar_row"
    return StockCronGuardDecision(
        trade_date=trade_date,
        calendar_status=status,
        should_run=False,
        reason=reason,
    )


def refresh_trading_calendar_from_tushare(
    *,
    service: str,
    trade_date: date,
    exchanges: tuple[str, ...],
    token: str | None = None,
) -> int:
    actual_token = token or os.getenv("TUSHARE_TOKEN") or load_local_tushare_token()
    if not actual_token:
        return 0

    import tushare as ts

    pro = ts.pro_api(actual_token)
    df = pro.trade_cal(
        exchange="",
        start_date=format_trade_date(trade_date),
        end_date=format_trade_date(trade_date),
    )
    if df is None or df.empty:
        return 0

    rows = []
    for row in df.to_dict("records"):
        if str(row.get("cal_date")) != format_trade_date(trade_date):
            continue
        is_open = str(row.get("is_open")) == "1"
        for exchange in exchanges:
            rows.append(
                {
                    "exchange": exchange,
                    "trade_date": trade_date.isoformat(),
                    "is_open": is_open,
                    "source": "tushare",
                    "source_version": "tushare_trade_cal_v1",
                }
            )
    if not rows:
        return 0
    with connect(service) as conn:
        return upsert_trading_calendar(conn, rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guard stock cron tasks with the trading calendar."
    )
    parser.add_argument("--date", dest="trade_date")
    parser.add_argument("--service", default=SETTINGS.research_service)
    parser.add_argument("--timezone", default=PipelineConfig().timezone)
    parser.add_argument("--exchanges", default="SH,SZ")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even when the trading calendar is closed or missing.",
    )
    parser.add_argument(
        "--no-sync-missing-calendar",
        action="store_true",
        help="Do not fetch Tushare trade_cal when the local calendar row is missing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    trade_date = parse_trade_date(args.trade_date, args.timezone)
    exchanges = tuple(part.strip().upper() for part in args.exchanges.split(",") if part.strip())
    force = args.force or _truthy_env(os.getenv("STOCK_CRON_FORCE_RUN"))
    decision = decide_stock_cron_run(
        service=args.service,
        trade_date=trade_date,
        exchanges=exchanges or ("SH", "SZ"),
        force=force,
        sync_missing_calendar=not args.no_sync_missing_calendar,
    )
    action = "run" if decision.should_run else "skip"
    print(
        "stock_cron_guard|"
        f"action|{action}|"
        f"trade_date|{decision.trade_date.isoformat()}|"
        f"calendar_status|{decision.calendar_status}|"
        f"reason|{decision.reason}"
    )
    return 0 if decision.should_run else SKIP_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
