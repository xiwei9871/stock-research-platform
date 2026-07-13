from io import StringIO


class FakeClock:
    def __init__(self, values):
        self.values = list(values)

    def monotonic(self):
        return self.values.pop(0)


class NonTtyStream(StringIO):
    def isatty(self):
        return False


class TtyStream(StringIO):
    def isatty(self):
        return True


def test_format_duration_uses_hh_mm_ss():
    from stock_research.cli_progress import format_duration

    assert format_duration(0) == "00:00:00"
    assert format_duration(65) == "00:01:05"
    assert format_duration(3661.8) == "01:01:01"


def test_estimate_eta_seconds_returns_none_until_progress_exists():
    from stock_research.cli_progress import estimate_eta_seconds

    assert estimate_eta_seconds(completed=0, total=10, elapsed_seconds=12) is None
    assert estimate_eta_seconds(completed=5, total=10, elapsed_seconds=20) == 20
    assert estimate_eta_seconds(completed=10, total=10, elapsed_seconds=20) == 0


def test_progress_renderer_writes_structured_lines_for_non_tty_stream():
    from stock_research.cli_progress import ProgressRenderer

    stream = NonTtyStream()
    clock = FakeClock([100.0, 125.0])
    renderer = ProgressRenderer("minute5_backfill", stream=stream, clock=clock.monotonic)

    renderer(
        {
            "event": "minute_backfill_progress",
            "completed_jobs": 25,
            "total_jobs": 100,
            "success_jobs": 24,
            "failed_jobs": 1,
            "rows": 1200,
        }
    )

    assert stream.getvalue() == (
        "progress|minute5_backfill|event|minute_backfill_progress|completed|25|"
        "total|100|pct|25.00|elapsed|00:00:25|eta|00:01:15|rows|1200|success|24|failed|1\n"
    )


def test_progress_renderer_rewrites_single_line_for_tty_stream_and_finishes_with_newline():
    from stock_research.cli_progress import ProgressRenderer

    stream = TtyStream()
    clock = FakeClock([10.0, 20.0, 30.0])
    renderer = ProgressRenderer("daily_bar", stream=stream, clock=clock.monotonic)

    renderer({"event": "daily_progress", "completed": 1, "total": 4, "rows": 100})
    renderer({"event": "daily_completed", "completed": 4, "total": 4, "rows": 400})

    output = stream.getvalue()
    assert "\rdaily_bar [######------------------] 1/4 25.00%" in output
    assert "eta=00:00:30" in output
    assert output.endswith("\n")
