from pathlib import Path

from stock_research.factor_backfill_watchdog import (
    CompletionSnapshot,
    ProgressSnapshot,
    build_status_message,
    parse_progress_line,
    read_completion,
    read_last_progress,
)


def test_parse_progress_line_parses_done_event():
    line = "factor_daily_backfill|done|2013-05-02|1975|4664|69325"

    snapshot = parse_progress_line(line)

    assert snapshot == ProgressSnapshot(
        trade_date="2013-05-02",
        index=1975,
        total=4664,
        factor_rows=69325,
    )


def test_parse_progress_line_ignores_other_lines():
    assert parse_progress_line("factor_daily_backfill|start|2013-05-02|1975|4664") is None
    assert parse_progress_line("random|line") is None


def test_read_last_progress_returns_last_done_entry(tmp_path: Path):
    log_path = tmp_path / "wave4-factor-daily-resume.txt"
    log_path.write_text(
        "\n".join(
            [
                "factor_daily_backfill|done|2013-01-08|1900|4664|64966",
                "noise",
                "factor_daily_backfill|done|2013-05-02|1975|4664|69325",
            ]
        ),
        encoding="utf-8",
    )

    snapshot = read_last_progress(log_path)

    assert snapshot == ProgressSnapshot(
        trade_date="2013-05-02",
        index=1975,
        total=4664,
        factor_rows=69325,
    )


def test_read_completion_reads_summary_lines(tmp_path: Path):
    log_path = tmp_path / "wave4-factor-daily-resume.txt"
    log_path.write_text(
        "\n".join(
            [
                "factor_daily_backfill|done|2026-05-11|4664|4664|81234",
                "factor_daily_backfill|dates|4664",
                "factor_daily_backfill|rows|51509029",
            ]
        ),
        encoding="utf-8",
    )

    summary = read_completion(log_path)

    assert summary == CompletionSnapshot(dates=4664, rows=51509029)


def test_build_status_message_includes_progress_and_log_path(tmp_path: Path):
    log_path = tmp_path / "wave4-factor-daily-resume.txt"

    message = build_status_message(
        title="Wave 4 factor_daily watchdog 30分钟状态",
        pid=12345,
        progress=ProgressSnapshot(
            trade_date="2013-05-02",
            index=1975,
            total=4664,
            factor_rows=69325,
        ),
        unchanged_minutes=30,
        log_path=log_path,
    )

    assert "Wave 4 factor_daily watchdog 30分钟状态" in message
    assert "pid: 12345" in message
    assert "2013-05-02 (1975/4664, rows=69325)" in message
    assert "无推进时长: 30 分钟" in message
    assert str(log_path) in message
