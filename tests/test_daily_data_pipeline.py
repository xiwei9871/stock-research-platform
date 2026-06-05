from pathlib import Path

from stock_research.daily_data_pipeline import (
    DailyPipelineStep,
    build_daily_pipeline_steps,
    derive_daily_windows,
    render_daily_pipeline_feishu_message,
)


def test_derive_daily_windows_uses_short_daily_lookbacks() -> None:
    windows = derive_daily_windows("2026-06-05")

    assert windows["trade_date"] == "2026-06-05"
    assert windows["market_start_date"] == "2026-05-31"
    assert windows["minute_start_date"] == "2026-05-31"
    assert windows["lhb_start_date"] == "2026-05-26"
    assert windows["announcement_start_date"] == "2026-05-22"
    assert windows["earnings_start_date"] == "2026-04-21"
    assert windows["repurchase_start_date"] == "2026-03-07"


def test_build_daily_pipeline_steps_lists_required_initial_steps() -> None:
    steps = build_daily_pipeline_steps(trade_date="2026-06-05", output_dir=Path("outputs/daily"))

    assert [step.name for step in steps] == [
        "start_report",
        "market_daily_refresh",
        "minute_incremental_refresh",
        "daily_event_refresh",
        "daily_feature_build",
        "daily_report_delivery",
    ]
    assert all(isinstance(step, DailyPipelineStep) for step in steps)
    assert steps[0].required is False
    assert steps[1].required is True


def test_build_daily_pipeline_steps_commands_parse_through_cli() -> None:
    from stock_research.cli import build_parser

    parser = build_parser()
    steps = build_daily_pipeline_steps(trade_date="2026-06-05", output_dir=Path("outputs/daily"))

    for step in steps:
        if step.command:
            parser.parse_args(step.command[3:])


def test_render_daily_pipeline_feishu_message_is_mobile_sized() -> None:
    message = render_daily_pipeline_feishu_message(
        trade_date="2026-06-05",
        status="partial_failed",
        output_dir=Path("outputs/daily/20260605"),
        step_results=[
            {"step": "market_daily_refresh", "status": "success", "rows": 5200, "error": ""},
            {"step": "daily_event_refresh", "status": "partial_failed", "rows": 45, "error": "lhb failed"},
        ],
    )

    assert "A股日频数据任务" in message
    assert "2026-06-05" in message
    assert "market_daily_refresh: success rows=5200" in message
    assert "daily_event_refresh: partial_failed rows=45 error=lhb failed" in message
    assert "outputs/daily/20260605" in message
    assert len(message) < 1800
