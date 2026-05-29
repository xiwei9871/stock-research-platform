from __future__ import annotations

from pathlib import Path


def build_p4_scheduler_cron_entry(
    *,
    project_dir: str | Path = "/Users/xiwei/stock_research",
    trade_date_expr: str = "$(date +%F)",
    hour: int = 19,
    minute: int = 15,
    weekdays: str = "1-5",
    portfolio_id: str = "p2_smoke_demo",
    service: str = "stock_research",
    log_path: str = "logs/p4_scheduler_daily.log",
) -> str:
    schedule = f"{minute} {hour} * * {weekdays}"
    env = " ".join(
        [
            f"TRADE_DATE={trade_date_expr}",
            f"PORTFOLIO_ID={portfolio_id}",
            f"SERVICE={service}",
        ]
    )
    command = f"{env} scripts/run_p4_scheduler_daily.sh"
    return f"{schedule} cd {Path(project_dir)} && {command} >> {log_path} 2>&1"
