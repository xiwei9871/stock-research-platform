from stock_research.backfill_watchdog import (
    BackfillSummary,
    BackfillWatchdogStatus,
    run_watchdog_once,
    build_watchdog_status,
    format_watchdog_message,
)


def test_build_watchdog_status_is_healthy_when_summary_progress_advances():
    status = build_watchdog_status(
        previous_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        current_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        pre_summary=BackfillSummary(
            total_tasks=120,
            pending_tasks=20,
            running_tasks=0,
            success_tasks=100,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=1_000_000,
        ),
        post_summary=BackfillSummary(
            total_tasks=140,
            pending_tasks=0,
            running_tasks=0,
            success_tasks=140,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=1_120_000,
        ),
        stale_tasks_reset=0,
        timed_out=False,
        running_jobs_present=False,
    )

    assert isinstance(status, BackfillWatchdogStatus)
    assert status.watchdog_action == "healthy"
    assert status.progress_advanced is True
    assert status.work_remaining is False


def test_format_watchdog_message_is_compact_and_readable():
    status = BackfillWatchdogStatus(
        watchdog_action="healthy",
        progress_advanced=True,
        work_remaining=True,
        stale_tasks_reset=0,
        timed_out=False,
        previous_frontier={
            "completed_through": "2024-03",
            "currently_working_on": "2024-04",
        },
        current_frontier={
            "completed_through": "2024-04",
            "currently_working_on": "2024-05",
        },
    )

    message = format_watchdog_message(
        task_name="minute_backfill",
        dataset="market.stock_minute_bar",
        run_id="minute-backfill:5min:raw,qfq:2024-01-01:2026-05-13",
        window="2024-01-01..2026-05-13",
        pre_summary=BackfillSummary(100, 20, 0, 70, 1, 9, 1_000_000),
        post_summary=BackfillSummary(100, 10, 1, 80, 1, 9, 1_120_000),
        run_result={
            "status": "completed",
            "attempted": 10,
            "success": 10,
            "failed": 0,
            "rows": 120_000,
        },
        status=status,
        extra_lines=[
            "run_status=completed",
            "run_attempted=10",
            "run_success=10",
            "run_failed=0",
            "run_rows=120000",
        ],
    )

    lines = message.splitlines()
    assert len(lines) <= 7
    assert lines[0] == "分钟线回填 watchdog: healthy"
    assert "完成至 2024-04，当前 2024-05" in message
    assert "成功 80(+10)" in message
    assert "新增行 120000" in message
    assert "run_id=" not in message
    assert "progress_advanced=" not in message


def test_build_watchdog_status_is_restarted_when_stale_tasks_reset():
    status = build_watchdog_status(
        previous_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        current_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        pre_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=10,
            running_tasks=1,
            success_tasks=9,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=10_000,
        ),
        post_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=11,
            running_tasks=0,
            success_tasks=9,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=10_000,
        ),
        stale_tasks_reset=2,
        timed_out=False,
        running_jobs_present=False,
    )

    assert status.watchdog_action == "restarted"
    assert status.progress_advanced is False
    assert status.work_remaining is True
    assert status.stale_tasks_reset == 2


def test_build_watchdog_status_is_stalled_when_no_progress_and_work_remains():
    status = build_watchdog_status(
        previous_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        current_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        pre_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=8,
            running_tasks=0,
            success_tasks=10,
            failed_tasks=2,
            skipped_tasks=0,
            total_rows_written=50_000,
        ),
        post_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=8,
            running_tasks=0,
            success_tasks=10,
            failed_tasks=2,
            skipped_tasks=0,
            total_rows_written=50_000,
        ),
        stale_tasks_reset=0,
        timed_out=False,
        running_jobs_present=False,
    )

    assert status.watchdog_action == "stalled_needs_manual_attention"
    assert status.progress_advanced is False
    assert status.work_remaining is True


def test_build_watchdog_status_keeps_timeout_with_running_tasks_healthy():
    status = build_watchdog_status(
        previous_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        current_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        pre_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=2,
            running_tasks=1,
            success_tasks=17,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=100_000,
        ),
        post_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=2,
            running_tasks=1,
            success_tasks=17,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=100_000,
        ),
        stale_tasks_reset=0,
        timed_out=True,
        running_jobs_present=True,
    )

    assert status.watchdog_action == "healthy"
    assert status.progress_advanced is False
    assert status.work_remaining is True


def test_build_watchdog_status_does_not_treat_timeout_as_healthy_without_current_running_tasks():
    status = build_watchdog_status(
        previous_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        current_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        pre_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=2,
            running_tasks=1,
            success_tasks=17,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=100_000,
        ),
        post_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=2,
            running_tasks=0,
            success_tasks=17,
            failed_tasks=1,
            skipped_tasks=0,
            total_rows_written=100_000,
        ),
        stale_tasks_reset=0,
        timed_out=True,
        running_jobs_present=True,
    )

    assert status.watchdog_action == "stalled_needs_manual_attention"
    assert status.progress_advanced is False
    assert status.work_remaining is True


def test_build_watchdog_status_treats_lock_busy_with_running_tasks_as_healthy():
    status = build_watchdog_status(
        previous_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        current_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        pre_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=2,
            running_tasks=1,
            success_tasks=17,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=100_000,
        ),
        post_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=2,
            running_tasks=1,
            success_tasks=17,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=100_000,
        ),
        stale_tasks_reset=0,
        timed_out=False,
        running_jobs_present=True,
        already_running=True,
    )

    assert status.watchdog_action == "healthy"
    assert status.progress_advanced is False
    assert status.work_remaining is True


def test_build_watchdog_status_treats_skipped_task_growth_as_progress():
    status = build_watchdog_status(
        previous_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        current_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        pre_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=3,
            running_tasks=0,
            success_tasks=15,
            failed_tasks=0,
            skipped_tasks=1,
            total_rows_written=100_000,
        ),
        post_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=2,
            running_tasks=0,
            success_tasks=15,
            failed_tasks=0,
            skipped_tasks=2,
            total_rows_written=100_000,
        ),
        stale_tasks_reset=0,
        timed_out=False,
        running_jobs_present=False,
    )

    assert status.watchdog_action == "healthy"
    assert status.progress_advanced is True
    assert status.work_remaining is True


def test_build_watchdog_status_treats_frontier_only_advance_as_progress():
    status = build_watchdog_status(
        previous_frontier={
            "completed_through": "2024-02-29",
            "currently_working_on": "2024-03-01",
        },
        current_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
        pre_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=3,
            running_tasks=1,
            success_tasks=15,
            failed_tasks=0,
            skipped_tasks=1,
            total_rows_written=100_000,
        ),
        post_summary=BackfillSummary(
            total_tasks=20,
            pending_tasks=3,
            running_tasks=1,
            success_tasks=15,
            failed_tasks=0,
            skipped_tasks=1,
            total_rows_written=100_000,
        ),
        stale_tasks_reset=0,
        timed_out=False,
        running_jobs_present=False,
    )

    assert status.watchdog_action == "healthy"
    assert status.progress_advanced is True
    assert status.work_remaining is True


def test_format_watchdog_message_uses_shared_message_shape():
    pre_summary = BackfillSummary(
        total_tasks=2,
        pending_tasks=1,
        running_tasks=1,
        success_tasks=0,
        failed_tasks=0,
        skipped_tasks=0,
        total_rows_written=100,
    )
    post_summary = BackfillSummary(
        total_tasks=2,
        pending_tasks=0,
        running_tasks=0,
        success_tasks=1,
        failed_tasks=0,
        skipped_tasks=0,
        total_rows_written=240,
    )
    status = BackfillWatchdogStatus(
        watchdog_action="restarted",
        progress_advanced=True,
        work_remaining=True,
        stale_tasks_reset=1,
        timed_out=False,
        previous_frontier={
            "completed_through": "2024-02-29",
            "currently_working_on": "2024-03-01",
        },
        current_frontier={
            "completed_through": "2024-02-29",
            "currently_working_on": "2024-03-01",
        },
    )

    message = format_watchdog_message(
        task_name="minute_backfill",
        dataset="market.stock_minute_bar",
        run_id="minute-bars-20240101-now",
        window="2024-01-01..2026-05-14",
        pre_summary=pre_summary,
        post_summary=post_summary,
        run_result={
            "attempted": 1,
            "success": 1,
            "failed": 0,
            "rows": 140,
            "status": "completed",
            "timed_out": False,
        },
        status=status,
        extra_lines=["task_detail=wave4"],
    )

    assert message == "\n".join(
        [
            "分钟线回填 watchdog: restarted",
            "进度: 完成至 2024-02-29，当前 2024-03-01",
            "任务: 成功 1(+1) / 待 0 / 运行 0 / 失败 0 / 跳过 0",
            "本轮: completed，尝试 1，成功 1，失败 0，新增行 140",
            "守护: reset 1，timeout false，剩余 true",
            "范围: 2024-01-01..2026-05-14 | 数据: market.stock_minute_bar",
        ]
    )


def test_format_watchdog_message_sanitizes_extra_lines_to_single_line_key_value_entries():
    pre_summary = BackfillSummary(
        total_tasks=20,
        pending_tasks=1,
        running_tasks=1,
        success_tasks=15,
        failed_tasks=0,
        skipped_tasks=1,
        total_rows_written=99_000,
    )
    post_summary = BackfillSummary(
        total_tasks=20,
        pending_tasks=0,
        running_tasks=0,
        success_tasks=16,
        failed_tasks=0,
        skipped_tasks=1,
        total_rows_written=100_000,
    )
    status = BackfillWatchdogStatus(
        watchdog_action="healthy",
        progress_advanced=True,
        work_remaining=False,
        stale_tasks_reset=0,
        timed_out=False,
        previous_frontier={
            "completed_through": "2024-02-29",
            "currently_working_on": "2024-03-01",
        },
        current_frontier={
            "completed_through": "2024-03-31",
            "currently_working_on": "2024-04-01",
        },
    )

    message = format_watchdog_message(
        task_name="minute_backfill",
        dataset="market.stock_minute_bar",
        run_id="minute-bars-20240101-now",
        window="2024-01-01..2026-05-14",
        pre_summary=pre_summary,
        post_summary=post_summary,
        run_result={
            "attempted": 1,
            "success": 1,
            "failed": 0,
            "rows": 1_000,
            "status": "completed",
            "timed_out": False,
        },
        status=status,
        extra_lines=[
            "custom_detail=2024-03-31\nwrapped=true",
            "not-a-key-value-line",
        ],
    )

    lines = message.splitlines()

    assert len(lines) == 6
    assert "进度: 完成至 2024-03-31，当前 2024-04-01" in lines
    assert "任务: 成功 16(+1) / 待 0 / 运行 0 / 失败 0 / 跳过 1" in lines
    assert "custom_detail=2024-03-31 wrapped=true" not in lines
    assert "detail=not-a-key-value-line" not in lines
    assert "not-a-key-value-line" not in lines


class FakeAdapter:
    task_name = "minute_backfill"
    dataset = "market.stock_minute_bar"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.run_once_kwargs: dict[str, object] | None = None
        self.scope = {
            "run_id": "minute-bars-20240101-now",
            "window": "2024-01-01..2026-05-14",
        }
        self.pre_rows = [{"batch": "2024-04", "status": "running"}]
        self.post_rows = [{"batch": "2024-04", "status": "success"}]
        self.pre_summary = BackfillSummary(
            total_tasks=2,
            pending_tasks=1,
            running_tasks=1,
            success_tasks=0,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=100,
        )
        self.post_summary = BackfillSummary(
            total_tasks=2,
            pending_tasks=0,
            running_tasks=0,
            success_tasks=1,
            failed_tasks=0,
            skipped_tasks=0,
            total_rows_written=240,
        )
        self.previous_frontier = {
            "completed_through": None,
            "currently_working_on": "2024-04-01",
        }
        self.current_frontier = {
            "completed_through": "2024-04-30",
            "currently_working_on": None,
        }
        self.run_result = {
            "attempted": 1,
            "success": 1,
            "failed": 0,
            "rows": 140,
            "status": "completed",
            "timed_out": False,
        }

    def load_scope(self) -> dict[str, str]:
        self.calls.append("load_scope")
        return dict(self.scope)

    def load_status_rows(self) -> list[dict[str, str]]:
        self.calls.append("load_status_rows")
        if self.calls.count("load_status_rows") == 1:
            return list(self.pre_rows)
        return list(self.post_rows)

    def summarize_status(self, rows: list[dict[str, str]]) -> BackfillSummary:
        self.calls.append("summarize_status")
        if rows == self.pre_rows:
            return self.pre_summary
        return self.post_summary

    def compute_frontier(self, rows: list[dict[str, str]]) -> dict[str, str | None]:
        self.calls.append("compute_frontier")
        if rows == self.pre_rows:
            return dict(self.previous_frontier)
        return dict(self.current_frontier)

    def reset_stale_tasks(self, stale_after_minutes: int) -> int:
        self.calls.append("reset_stale_tasks")
        assert stale_after_minutes == 20
        return 1

    def run_once(
        self,
        *,
        scope: dict[str, str],
        max_jobs: int,
        workers: int,
        run_timeout_seconds: int,
    ) -> dict[str, object]:
        self.calls.append("run_once")
        self.run_once_kwargs = {
            "scope": dict(scope),
            "max_jobs": max_jobs,
            "workers": workers,
            "run_timeout_seconds": run_timeout_seconds,
        }
        return dict(self.run_result)

    def format_extra_status_lines(
        self,
        *,
        rows: list[dict[str, str]],
        summary: BackfillSummary,
        scope: dict[str, str],
        run_result: dict[str, object],
        status: BackfillWatchdogStatus,
    ) -> list[str]:
        self.calls.append("format_extra_status_lines")
        assert rows == self.post_rows
        assert summary == self.post_summary
        assert scope == self.scope
        assert run_result == self.run_result
        assert status.current_frontier == self.current_frontier
        return ["task_detail=wave4"]


def test_run_watchdog_once_calls_adapter_in_expected_order():
    adapter = FakeAdapter()

    result = run_watchdog_once(
        adapter=adapter,
        stale_after_minutes=20,
        run_timeout_seconds=900,
    )

    assert adapter.calls == [
        "load_scope",
        "load_status_rows",
        "summarize_status",
        "compute_frontier",
        "reset_stale_tasks",
        "run_once",
        "load_status_rows",
        "summarize_status",
        "compute_frontier",
        "format_extra_status_lines",
    ]
    assert adapter.run_once_kwargs == {
        "scope": {
            "run_id": "minute-bars-20240101-now",
            "window": "2024-01-01..2026-05-14",
        },
        "max_jobs": 100,
        "workers": 2,
        "run_timeout_seconds": 900,
    }
    assert result["frontier"] == {
        "completed_through": "2024-04-30",
        "currently_working_on": None,
    }


def test_run_watchdog_once_sends_message_via_reporter():
    adapter = FakeAdapter()
    sent_messages: list[str] = []

    result = run_watchdog_once(
        adapter=adapter,
        stale_after_minutes=20,
        run_timeout_seconds=900,
        send_message=sent_messages.append,
    )

    assert sent_messages == [result["message"]]
    assert sent_messages[0].startswith("分钟线回填 watchdog: restarted")
    assert "数据: market.stock_minute_bar" in sent_messages[0]


def test_run_watchdog_once_returns_structured_result():
    adapter = FakeAdapter()

    result = run_watchdog_once(
        adapter=adapter,
        stale_after_minutes=20,
        run_timeout_seconds=900,
    )

    assert result["scope"] == {
        "run_id": "minute-bars-20240101-now",
        "window": "2024-01-01..2026-05-14",
    }
    assert result["pre_summary"] == adapter.pre_summary
    assert result["post_summary"] == adapter.post_summary
    assert result["previous_frontier"] == adapter.previous_frontier
    assert result["frontier"] == adapter.current_frontier
    assert result["stale_tasks_reset"] == 1
    assert result["run_result"] == adapter.run_result
    assert result["status"].watchdog_action == "restarted"
    assert result["status"].previous_frontier == adapter.previous_frontier
    assert result["status"].current_frontier == adapter.current_frontier
    assert result["message"] == "\n".join(
        [
            "分钟线回填 watchdog: restarted",
            "进度: 完成至 2024-04-30，当前 无",
            "任务: 成功 1(+1) / 待 0 / 运行 0 / 失败 0 / 跳过 0",
            "本轮: completed，尝试 1，成功 1，失败 0，新增行 140",
            "守护: reset 1，timeout false，剩余 true",
            "范围: 2024-01-01..2026-05-14 | 数据: market.stock_minute_bar",
        ]
    )


def test_run_watchdog_once_message_keeps_shared_frontier_fields_without_adapter_extras():
    adapter = FakeAdapter()

    def no_extra_lines(
        *,
        rows: list[dict[str, str]],
        summary: BackfillSummary,
        scope: dict[str, str],
        run_result: dict[str, object],
        status: BackfillWatchdogStatus,
    ) -> list[str]:
        return []

    adapter.format_extra_status_lines = no_extra_lines

    result = run_watchdog_once(
        adapter=adapter,
        stale_after_minutes=20,
        run_timeout_seconds=900,
    )

    assert "进度: 完成至 2024-04-30，当前 无" in result["message"]
    assert len(result["message"].splitlines()) == 6
