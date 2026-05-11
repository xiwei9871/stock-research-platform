from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def summarize_finance_coverage(
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    checks = [
        (
            "missing_balance_sheet",
            "blocked",
            """
            SELECT count(*) AS rows
            FROM finance.income_statement i
            LEFT JOIN finance.balance_sheet b
              ON b.asset_id = i.asset_id
             AND b.report_period = i.report_period
             AND b.report_type = i.report_type
            WHERE b.asset_id IS NULL
            """,
        ),
        (
            "missing_cash_flow",
            "blocked",
            """
            SELECT count(*) AS rows
            FROM finance.income_statement i
            LEFT JOIN finance.cash_flow c
              ON c.asset_id = i.asset_id
             AND c.report_period = i.report_period
             AND c.report_type = i.report_type
            WHERE c.asset_id IS NULL
            """,
        ),
        (
            "missing_announcement_date",
            "blocked",
            """
            SELECT count(*) AS rows
            FROM (
                SELECT 1 FROM finance.income_statement WHERE announcement_date IS NULL
                UNION ALL
                SELECT 1 FROM finance.balance_sheet WHERE announcement_date IS NULL
                UNION ALL
                SELECT 1 FROM finance.cash_flow WHERE announcement_date IS NULL
            ) missing_dates
            """,
        ),
        (
            "announcement_before_report_period",
            "warning",
            """
            SELECT count(*) AS rows
            FROM (
                SELECT 1 FROM finance.income_statement WHERE announcement_date < report_period
                UNION ALL
                SELECT 1 FROM finance.balance_sheet WHERE announcement_date < report_period
                UNION ALL
                SELECT 1 FROM finance.cash_flow WHERE announcement_date < report_period
            ) date_warnings
            """,
        ),
    ]

    results = []
    with connect(service) as conn:
        for check, nonzero_status, sql in checks:
            row = fetch_all(conn, sql)[0]
            rows = int(row["rows"] or 0)
            status = "ok" if rows == 0 else nonzero_status
            results.append({"check": check, "status": status, "rows": rows})
    return results


def format_finance_audit_line(row: dict[str, Any]) -> str:
    return f"finance_audit|{row['check']}|{row['status']}|rows|{row['rows']}"
