import json
from pathlib import Path

from stock_research.backfill_watchdog import BackfillSummary
from stock_research import technical_feature_watchdog
from stock_research.technical_feature_watchdog import TechnicalFeatureBackfillAdapter


def test_technical_feature_adapter_status_and_frontier(monkeypatch):
    monkeypatch.setattr(
        technical_feature_watchdog,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["1991-01-02", "1991-01-03", "1991-01-04"],
    )
    monkeypatch.setattr(
        technical_feature_watchdog,
        "load_complete_technical_feature_dates",
        lambda **kwargs: {"1991-01-02"},
    )
    monkeypatch.setattr(
        technical_feature_watchdog,
        "_load_technical_feature_row_counts",
        lambda **kwargs: {"1991-01-02": 100},
    )

    adapter = TechnicalFeatureBackfillAdapter(
        start_date="1991-01-01",
        end_date="2026-05-14",
    )
    rows = adapter.load_status_rows()

    assert rows == [
        {"trade_date": "1991-01-02", "status": "success", "row_count": 100},
        {"trade_date": "1991-01-03", "status": "pending", "row_count": 0},
        {"trade_date": "1991-01-04", "status": "pending", "row_count": 0},
    ]
    assert adapter.summarize_status(rows) == BackfillSummary(
        total_tasks=3,
        pending_tasks=2,
        running_tasks=0,
        success_tasks=1,
        failed_tasks=0,
        skipped_tasks=0,
        total_rows_written=100,
    )
    assert adapter.compute_frontier(rows) == {
        "completed_through": "1991-01-02",
        "currently_working_on": "1991-01-03",
    }


def test_technical_feature_adapter_run_once_uses_next_pending_batch(monkeypatch):
    adapter = TechnicalFeatureBackfillAdapter(
        start_date="1991-01-01",
        end_date="2026-05-14",
        adjust_type="qfq",
        source_data_version="market_daily_bar:qfq",
    )
    monkeypatch.setattr(
        TechnicalFeatureBackfillAdapter,
        "load_status_rows",
        lambda self: [
            {"trade_date": "1991-01-02", "status": "success", "row_count": 100},
            {"trade_date": "1991-01-03", "status": "pending", "row_count": 0},
            {"trade_date": "1991-01-04", "status": "pending", "row_count": 0},
            {"trade_date": "1991-01-07", "status": "pending", "row_count": 0},
        ],
    )
    calls = []

    class FakeFrame:
        empty = False

        def __len__(self):
            return 2

        def __getitem__(self, key):
            assert key == "feature_rows"
            return self

        def sum(self):
            return 250

    monkeypatch.setattr(
        technical_feature_watchdog,
        "backfill_technical_features_daily_range",
        lambda **kwargs: calls.append(kwargs) or FakeFrame(),
    )

    result = adapter.run_once(
        scope=adapter.load_scope(),
        max_jobs=2,
        workers=2,
        run_timeout_seconds=1800,
    )

    assert calls == [
        {
            "start_date": "1991-01-03",
            "end_date": "1991-01-04",
            "lookback_bars": 260,
            "adjust_type": "qfq",
            "source_data_version": "market_daily_bar:qfq",
            "trading_days_only": True,
            "workers": 2,
            "skip_complete": True,
        }
    ]
    assert result == {
        "attempted": 2,
        "success": 2,
        "failed": 0,
        "rows": 250,
        "status": "completed",
        "timed_out": False,
    }


def test_cron_jobs_include_technical_feature_backfill_watchdog():
    jobs = json.loads(Path("/Users/xiwei/.openclaw/cron/jobs.json").read_text())["jobs"]
    job = next(
        (item for item in jobs if item["name"] == "technical-feature-backfill-watchdog"),
        None,
    )

    assert job is not None
    assert job["agentId"] == "agent_jarvis"
    assert job["enabled"] is True
    assert job["schedule"] == {
        "kind": "cron",
        "expr": "*/30 * * * *",
        "tz": "Asia/Shanghai",
    }
    assert job["payload"]["kind"] == "agentTurn"
    assert job["payload"]["toolsAllow"] == ["exec"]
    assert job["payload"]["timeoutSeconds"] == 2100
    assert "/Users/xiwei/stock_research/scripts/run_technical_feature_backfill_watchdog_host.sh" in job["payload"]["message"]
    assert "cd /Users/xiwei/stock_research &&" not in job["payload"]["message"]
    assert "stock_research.cli backfill-watchdog" not in job["payload"]["message"]
    assert "/approval" not in job["payload"]["message"]
    assert "approval" not in job["payload"]["message"].lower()

    approvals = json.loads(Path("/Users/xiwei/.openclaw/exec-approvals.json").read_text())
    jarvis_allowlist = approvals["agents"]["agent_jarvis"]["allowlist"]
    assert any(
        item["pattern"]
        == "/Users/xiwei/stock_research/scripts/run_technical_feature_backfill_watchdog_host.sh"
        for item in jarvis_allowlist
    )
