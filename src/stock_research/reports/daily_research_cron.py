from pathlib import Path


def build_daily_research_cron_entry(
    project_dir: str | Path = "/Users/xiwei/stock_research",
    trade_date_expr: str = "$(date +%F)",
    hour: int = 18,
    minute: int = 30,
    weekdays: str = "1-5",
    score_version: str = "manual_v1",
    top_n: int = 30,
    index_id: str = "CSI300",
    industry_system: str = "csrc",
    reports_dir: str = "reports",
    record_run: bool = True,
    log_path: str = "logs/daily_research_report.log",
) -> str:
    command_parts = [
        ".venv/bin/python",
        "-m",
        "stock_research.reports.daily_research_report_cli",
        "--trade-date",
        trade_date_expr,
        "--score-version",
        score_version,
        "--top-n",
        str(top_n),
        "--index-id",
        index_id,
        "--industry-system",
        industry_system,
        "--reports-dir",
        reports_dir,
    ]
    if record_run:
        command_parts.extend(["--apply-report-run-schema", "--record-run"])
    schedule = f"{minute} {hour} * * {weekdays}"
    command = " ".join(command_parts)
    return f"{schedule} cd {Path(project_dir)} && {command} >> {log_path} 2>&1"
