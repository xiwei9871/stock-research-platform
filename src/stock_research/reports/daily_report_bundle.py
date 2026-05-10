from pathlib import Path


REPORT_LABELS = {
    "topn": "TopN",
    "market_state": "Market State",
    "sector_strength": "Sector Strength",
    "risk_alerts": "Risk Alerts",
    "backtest_tearsheet": "Backtest Tear Sheet",
    "performance": "Performance",
}


def write_daily_report_bundle(
    trade_date: str,
    report_paths: dict[str, str | Path],
    output_dir: str | Path = "reports/daily",
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    date_text = _date_text(trade_date)
    markdown_path = output_path / f"daily_research_bundle_{date_text}.md"
    markdown_path.write_text(
        _render_bundle_markdown(date_text, report_paths),
        encoding="utf-8",
    )
    return {"markdown_path": markdown_path}


def _render_bundle_markdown(
    trade_date: str,
    report_paths: dict[str, str | Path],
) -> str:
    lines = [
        f"# {trade_date} Daily Research Bundle",
        "",
        "- 研究报告只作为人工复核入口，不构成交易指令。",
        "",
        "| Report | Status | Path |",
        "| --- | --- | --- |",
    ]
    for key in sorted(report_paths):
        label = REPORT_LABELS.get(key, _title_label(key))
        value = report_paths.get(key)
        if not value:
            lines.append(f"| {label} | missing |  |")
            continue
        path = Path(value)
        status = "available" if path.exists() else "pending"
        lines.append(f"| {label} | {status} | `{path}` |")
    return "\n".join(lines) + "\n"


def _title_label(value: str) -> str:
    return value.replace("_", " ").title()


def _date_text(value: object) -> str:
    return str(value)[:10]
