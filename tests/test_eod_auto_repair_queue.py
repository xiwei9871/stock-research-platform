import json

from stock_research.eod_auto_repair_queue import (
    load_pending_dates,
    record_repair_result,
    select_pending_trade_dates,
)


def _write_summary(root, trade_date, *, status, blockers=None):
    output_dir = root / "research" / "eod_auto_repair" / trade_date
    output_dir.mkdir(parents=True)
    (output_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "trade_date": trade_date,
                "final_status": status,
                "remaining_blockers": blockers or [],
            }
        ),
        encoding="utf-8",
    )


def test_select_pending_trade_dates_bootstraps_old_failures_and_appends_current(tmp_path):
    _write_summary(tmp_path, "2026-07-28", status="failed", blockers=["strategy_publish"])
    _write_summary(tmp_path, "2026-07-29", status="degraded")
    (tmp_path / "research" / "eod_auto_repair" / "exploratory").mkdir(parents=True)

    selected = select_pending_trade_dates(
        tmp_path,
        current_trade_date="2026-07-31",
        pending_date_limit=3,
    )

    assert selected == ["2026-07-31", "2026-07-28"]
    queue = load_pending_dates(tmp_path)
    assert [item["trade_date"] for item in queue["items"]] == ["2026-07-28", "2026-07-31"]
    assert queue["items"][0]["remaining_blockers"] == ["strategy_publish"]


def test_select_pending_trade_dates_is_oldest_first_and_bounded(tmp_path):
    for trade_date in ("2026-07-25", "2026-07-26", "2026-07-27", "2026-07-28"):
        _write_summary(tmp_path, trade_date, status="failed", blockers=[trade_date])

    selected = select_pending_trade_dates(
        tmp_path,
        current_trade_date="2026-07-31",
        pending_date_limit=2,
    )

    assert selected == ["2026-07-31", "2026-07-25", "2026-07-26"]


def test_record_repair_result_removes_resolved_date_and_retains_failed_date(tmp_path):
    select_pending_trade_dates(tmp_path, current_trade_date="2026-07-31", pending_date_limit=0)

    record_repair_result(
        tmp_path,
        {
            "trade_date": "2026-07-31",
            "final_status": "failed",
            "remaining_blockers": ["review_queue"],
            "error_summary": "review queue invalid",
        },
    )
    queue = load_pending_dates(tmp_path)
    assert queue["items"][0]["attempts"] == 1
    assert queue["items"][0]["last_status"] == "failed"

    record_repair_result(
        tmp_path,
        {
            "trade_date": "2026-07-31",
            "final_status": "degraded",
            "remaining_blockers": [],
        },
    )
    assert load_pending_dates(tmp_path)["items"] == []
    assert not (tmp_path / "research" / "eod_auto_repair" / "pending_dates.json.tmp").exists()
