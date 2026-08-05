import json

import stock_research.eod_auto_repair as eod_auto_repair
from stock_research.eod_auto_repair import run_eod_auto_repair_batch
from stock_research.eod_auto_repair_models import RepairRunSummary, RepairStatus


def test_batch_continues_after_failed_date_and_updates_pending_queue(tmp_path, monkeypatch):
    failed_dir = tmp_path / "research" / "eod_auto_repair" / "2026-07-30"
    failed_dir.mkdir(parents=True)
    (failed_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "trade_date": "2026-07-30",
                "final_status": "failed",
                "remaining_blockers": ["strategy_publish"],
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        status = RepairStatus.FAILED if kwargs["trade_date"] == "2026-07-30" else RepairStatus.DEGRADED
        return RepairRunSummary(
            trade_date=kwargs["trade_date"],
            mode=kwargs["mode"],
            final_status=status,
            remaining_blockers=["strategy_publish"] if status == RepairStatus.FAILED else [],
        )

    monkeypatch.setattr(eod_auto_repair, "run_eod_auto_repair", fake_run)

    result = run_eod_auto_repair_batch(
        current_trade_date="2026-07-31",
        output_root=tmp_path,
        mode="loop",
        pending_date_limit=1,
    )

    assert result["trade_dates"] == ["2026-07-31", "2026-07-30"]
    assert [call["trade_date"] for call in calls] == result["trade_dates"]
    assert result["final_status"] == "degraded"
    assert result["backlog_failed_trade_dates"] == ["2026-07-30"]
    pending = json.loads(
        (tmp_path / "research" / "eod_auto_repair" / "pending_dates.json").read_text()
    )
    assert [item["trade_date"] for item in pending["items"]] == ["2026-07-30"]


def test_batch_returns_success_when_all_dates_are_blocker_free_degraded(tmp_path, monkeypatch):
    monkeypatch.setattr(
        eod_auto_repair,
        "run_eod_auto_repair",
        lambda **kwargs: RepairRunSummary(
            trade_date=kwargs["trade_date"],
            mode=kwargs["mode"],
            final_status=RepairStatus.DEGRADED,
        ),
    )

    result = run_eod_auto_repair_batch(
        current_trade_date="2026-07-31",
        output_root=tmp_path,
        mode="loop",
        pending_date_limit=0,
    )

    assert result["final_status"] == "degraded"
    assert result["results"][0]["final_status"] == "degraded"
    assert json.loads(
        (tmp_path / "research" / "eod_auto_repair" / "pending_dates.json").read_text()
    )["items"] == []


def test_batch_current_success_is_not_failed_by_backlog_blocker(tmp_path, monkeypatch):
    failed_dir = tmp_path / "research" / "eod_auto_repair" / "2026-07-30"
    failed_dir.mkdir(parents=True)
    (failed_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "trade_date": "2026-07-30",
                "final_status": "failed",
                "remaining_blockers": ["review_queue"],
            }
        ),
        encoding="utf-8",
    )

    def fake_run(**kwargs):
        status = RepairStatus.SUCCESS if kwargs["trade_date"] == "2026-07-31" else RepairStatus.FAILED
        return RepairRunSummary(
            trade_date=kwargs["trade_date"],
            mode=kwargs["mode"],
            final_status=status,
            remaining_blockers=[] if status == RepairStatus.SUCCESS else ["review_queue"],
        )

    monkeypatch.setattr(eod_auto_repair, "run_eod_auto_repair", fake_run)

    result = run_eod_auto_repair_batch(
        current_trade_date="2026-07-31",
        output_root=tmp_path,
        mode="loop",
        pending_date_limit=1,
    )

    assert result["final_status"] == "degraded"
    assert result["current_trade_date"] == "2026-07-31"
    assert result["current_result_status"] == "success"
    assert result["backlog_failed_trade_dates"] == ["2026-07-30"]
