from dataclasses import dataclass

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


@dataclass(frozen=True)
class AuditDataset:
    dataset: str
    table: str
    date_column: str | None


AUDIT_DATASETS: list[AuditDataset] = [
    AuditDataset("market_daily_bar", "market_daily_bar", "trade_date"),
    AuditDataset("raw_baostock.daily_bar_payload", "raw_baostock.daily_bar_payload", "trade_date"),
    AuditDataset("market.index_daily_bar", "market.index_daily_bar", "trade_date"),
    AuditDataset("market.index_constituent", "market.index_constituent", "start_date"),
    AuditDataset("market.trading_calendar", "market.trading_calendar", "trade_date"),
    AuditDataset("market.adjustment_factor", "market.adjustment_factor", "trade_date"),
    AuditDataset("market.corporate_action", "market.corporate_action", "event_date"),
    AuditDataset("label_snapshot", "label_snapshot", "trade_date"),
    AuditDataset("factor.factor_daily", "factor.factor_daily", "trade_date"),
    AuditDataset("core.asset_lifecycle_event", "core.asset_lifecycle_event", "event_date"),
    AuditDataset("core.industry_membership", "core.industry_membership", "start_date"),
    AuditDataset("market.industry_daily_bar", "market.industry_daily_bar", "trade_date"),
    AuditDataset("finance.income_statement", "finance.income_statement", "report_period"),
    AuditDataset("finance.balance_sheet", "finance.balance_sheet", "report_period"),
    AuditDataset("finance.cash_flow", "finance.cash_flow", "report_period"),
    AuditDataset("factor.factor_approval", "factor.factor_approval", None),
    AuditDataset("ingest.batch_job", "ingest.batch_job", None),
]


def format_audit_line(row: dict) -> str:
    return (
        f"data_audit|{row['dataset']}|{row['status']}|rows|{int(row.get('rows') or 0)}|"
        f"dates|{int(row.get('date_count') or 0)}|"
        f"min|{_format_value(row.get('min_date'))}|max|{_format_value(row.get('max_date'))}"
    )


def run_data_audit(
    expected_start_date: str = "1990-12-01",
    datasets: list[str] | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict]:
    selected = [dataset for dataset in AUDIT_DATASETS if datasets is None or dataset.dataset in datasets]
    results: list[dict] = []
    with connect(service) as conn:
        for dataset in selected:
            if dataset.date_column is None:
                sql = f"SELECT count(*) AS rows FROM {dataset.table}"
                rows = fetch_all(conn, sql)
                row = rows[0] if rows else {}
                result = {
                    "dataset": dataset.dataset,
                    "status": "ok" if int(row.get("rows") or 0) > 0 else "empty",
                    "rows": int(row.get("rows") or 0),
                    "date_count": 0,
                    "min_date": None,
                    "max_date": None,
                }
                results.append(result)
                continue

            sql = f"""
            SELECT count(*) AS rows,
                   count(DISTINCT {dataset.date_column}) AS date_count,
                   min({dataset.date_column}) AS min_date,
                   max({dataset.date_column}) AS max_date
            FROM {dataset.table}
            """
            rows = fetch_all(conn, sql)
            row = rows[0] if rows else {}
            min_date = row.get("min_date")
            status = "ok"
            if int(row.get("rows") or 0) <= 0:
                status = "empty"
            elif min_date is not None and str(min_date)[:10] > expected_start_date:
                status = "short_history"
            results.append(
                {
                    "dataset": dataset.dataset,
                    "status": status,
                    "rows": int(row.get("rows") or 0),
                    "date_count": int(row.get("date_count") or 0),
                    "min_date": min_date,
                    "max_date": row.get("max_date"),
                }
            )
    return results


def _format_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)[:10]
