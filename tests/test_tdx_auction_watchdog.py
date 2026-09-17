from stock_research.tdx_auction_watchdog import (
    build_daily_partitions,
    completed_month_summaries,
    newly_completed_months,
    send_monthly_completion_reports,
)


def test_build_daily_partitions_keeps_one_task_per_trading_date():
    partitions = build_daily_partitions(["2018-02-14", "2018-02-15"])

    assert partitions == [
        {
            "partition_key": "2018-02-14",
            "start_date": "2018-02-14",
            "end_date": "2018-02-14",
        },
        {
            "partition_key": "2018-02-15",
            "start_date": "2018-02-15",
            "end_date": "2018-02-15",
        },
    ]


def test_completed_month_summaries_only_marks_month_when_all_days_succeed():
    rows = [
        {"trade_date": "2018-02-14", "status": "success", "rows_written": 2},
        {"trade_date": "2018-02-15", "status": "success", "rows_written": 3},
        {"trade_date": "2018-03-01", "status": "pending", "rows_written": 0},
    ]

    summaries = completed_month_summaries(rows)

    assert summaries == [
        {
            "month": "2018-02",
            "total_days": 2,
            "success_days": 2,
            "rows_written": 5,
        }
    ]


def test_completed_month_summaries_rolls_up_symbol_quality_metrics():
    rows = [
        {
            "trade_date": "2018-02-14",
            "status": "success",
            "rows_written": 2,
            "params": {"failed_symbols": 3, "missing_symbols": 4},
        },
    ]

    assert completed_month_summaries(rows) == [
        {
            "month": "2018-02",
            "total_days": 1,
            "success_days": 1,
            "rows_written": 2,
            "failed_symbols": 3,
            "missing_symbols": 4,
        }
    ]


def test_completed_month_summaries_rolls_up_unsupported_payload_metrics():
    rows = [
        {
            "trade_date": "2018-02-14",
            "status": "success",
            "rows_written": 2,
            "params": {"unsupported_symbols": 11, "excluded_symbols": 11},
        },
    ]

    assert completed_month_summaries(rows) == [
        {
            "month": "2018-02",
            "total_days": 1,
            "success_days": 1,
            "rows_written": 2,
            "excluded_symbols": 11,
            "unsupported_symbols": 11,
        }
    ]

def test_newly_completed_months_excludes_reported_months():
    rows = [
        {"trade_date": "2018-02-14", "status": "success", "rows_written": 2},
    ]

    assert newly_completed_months(rows, reported_months={"2018-01"}) == ["2018-02"]
    assert newly_completed_months(rows, reported_months={"2018-02"}) == []


def test_monthly_completion_report_is_idempotent(tmp_path):
    rows = [
        {
            "trade_date": "2018-02-14",
            "status": "success",
            "rows_written": 2,
            "params": {
                "requested_symbols": 100,
                "missing_symbols": 4,
                "unsupported_symbols": 11,
                "failed_symbols": 0,
                "excluded_symbols": 11,
            },
        },
    ]
    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs["message"])

    ledger = tmp_path / "reported_months.json"
    first = send_monthly_completion_reports(
        rows=rows,
        ledger_path=ledger,
        report_target="chat:test",
        send=fake_send,
    )
    second = send_monthly_completion_reports(
        rows=rows,
        ledger_path=ledger,
        report_target="chat:test",
        send=fake_send,
    )

    assert first[0]["sent"] is True
    assert "TDX格式不支持=11" in first[0]["message"]
    assert "请求异常=0" in first[0]["message"]
    assert "当前退市未请求=11" in first[0]["message"]
    assert second == []
    assert len(sent) == 1
