from stock_research.backfill_watchdog import BackfillSummary, BackfillWatchdogStatus
from stock_research import factor_gate_watchdog
from stock_research.factor_gate_watchdog import FactorGateBatchWatchdogAdapter


def test_factor_gate_adapter_status_and_frontier(monkeypatch, tmp_path):
    monkeypatch.setattr(
        factor_gate_watchdog,
        "candidate_factor_names",
        lambda: ["ret_20", "qlib_ret_5", "ret_60"],
    )
    monkeypatch.setattr(
        factor_gate_watchdog,
        "_load_factor_gate_approval_rows",
        lambda **kwargs: [
            {
                "factor_name": "ret_20",
                "status": "approved",
                "reason": "passed_thresholds",
                "eval_run_id": "run-ret-20",
            }
        ],
    )

    adapter = FactorGateBatchWatchdogAdapter(
        start_date="1991-06-24",
        end_date="2026-04-28",
        validation_start_date="2018-01-01",
        log_path=tmp_path / "factor-gate.log",
    )
    rows = adapter.load_status_rows()

    assert rows == [
        {
            "factor_name": "ret_20",
            "status": "success",
            "approval_status": "approved",
            "reason": "passed_thresholds",
            "eval_run_id": "run-ret-20",
            "row_count": 1,
        },
        {
            "factor_name": "qlib_ret_5",
            "status": "pending",
            "approval_status": None,
            "reason": None,
            "eval_run_id": None,
            "row_count": 0,
        },
        {
            "factor_name": "ret_60",
            "status": "pending",
            "approval_status": None,
            "reason": None,
            "eval_run_id": None,
            "row_count": 0,
        },
    ]
    assert adapter.summarize_status(rows) == BackfillSummary(
        total_tasks=3,
        pending_tasks=2,
        running_tasks=0,
        success_tasks=1,
        failed_tasks=0,
        skipped_tasks=0,
        total_rows_written=1,
    )
    assert adapter.compute_frontier(rows) == {
        "completed_through": "ret_20",
        "currently_working_on": "qlib_ret_5",
    }


def test_factor_gate_adapter_run_once_evaluates_next_pending_batch(monkeypatch, tmp_path):
    monkeypatch.setattr(
        FactorGateBatchWatchdogAdapter,
        "load_status_rows",
        lambda self: [
            {"factor_name": "ret_20", "status": "success", "row_count": 1},
            {"factor_name": "qlib_ret_5", "status": "pending", "row_count": 0},
            {"factor_name": "ret_60", "status": "pending", "row_count": 0},
        ],
    )
    calls = []

    class FakeFrame:
        empty = False

        def __len__(self):
            return 1

    monkeypatch.setattr(
        factor_gate_watchdog,
        "run_factor_gate_batch",
        lambda **kwargs: calls.append(kwargs) or FakeFrame(),
    )

    log_path = tmp_path / "factor-gate.log"
    adapter = FactorGateBatchWatchdogAdapter(
        start_date="1991-06-24",
        end_date="2026-04-28",
        validation_start_date="2018-01-01",
        log_path=log_path,
    )

    result = adapter.run_once(
        scope=adapter.load_scope(),
        max_jobs=1,
        workers=1,
        run_timeout_seconds=1800,
    )

    assert calls == [
        {
            "factor_names": ["qlib_ret_5"],
            "start_date": "1991-06-24",
            "end_date": "2026-04-28",
            "horizons": [5, 10, 20, 60],
            "primary_horizon": 5,
            "calc_version": "v1",
            "score_version": "manual_v1",
            "quantiles": 5,
            "top_n": 30,
            "validation_start_date": "2018-01-01",
        }
    ]
    assert result["status"] == "completed"
    assert result["attempted"] == 1
    assert result["success"] == 1
    assert result["rows"] == 1


def test_run_factor_gate_batch_watchdog_sends_generic_message(monkeypatch, tmp_path):
    generic_calls = []
    sent = []

    def fake_run_watchdog_once(**kwargs):
        generic_calls.append(kwargs)
        return {
            "scope": {},
            "pre_rows": [],
            "post_rows": [],
            "pre_summary": BackfillSummary(0, 0, 0, 0, 0, 0, 0),
            "post_summary": BackfillSummary(1, 0, 0, 1, 0, 0, 1),
            "previous_frontier": {"completed_through": None, "currently_working_on": "ret_20"},
            "frontier": {"completed_through": "ret_20", "currently_working_on": None},
            "status": BackfillWatchdogStatus(
                watchdog_action="healthy",
                progress_advanced=True,
                work_remaining=False,
                stale_tasks_reset=0,
                timed_out=False,
                previous_frontier={"completed_through": None, "currently_working_on": "ret_20"},
                current_frontier={"completed_through": "ret_20", "currently_working_on": None},
            ),
            "stale_tasks_reset": 0,
            "run_result": {
                "attempted": 1,
                "success": 0,
                "failed": 0,
                "rows": 0,
                "status": "started",
                "timed_out": False,
            },
            "timed_out": False,
            "message": "factor_gate_batch watchdog: healthy",
        }

    monkeypatch.setattr(factor_gate_watchdog, "run_watchdog_once", fake_run_watchdog_once)
    monkeypatch.setattr(
        factor_gate_watchdog,
        "send_openclaw_feishu_message",
        lambda **kwargs: sent.append(kwargs),
    )

    result = factor_gate_watchdog.run_factor_gate_batch_watchdog(
        start_date="1991-06-24",
        end_date="2026-04-28",
        validation_start_date="2018-01-01",
        report_target="chat:test",
        report_account="jarvis",
        openclaw_bin="openclaw",
        report_dry_run=True,
        log_path=tmp_path / "factor-gate.log",
    )

    assert isinstance(generic_calls[0]["adapter"], FactorGateBatchWatchdogAdapter)
    assert sent == [
        {
            "message": "factor_gate_batch watchdog: healthy",
            "target": "chat:test",
            "account": "jarvis",
            "openclaw_bin": "openclaw",
            "dry_run": True,
        }
    ]
    assert result["message"] == "factor_gate_batch watchdog: healthy"
