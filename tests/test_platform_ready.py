from pathlib import Path

from stock_research import platform_ready


def _prepare_strategy_daily_eod_ok(monkeypatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "strategy_daily_eod" / "2026-06-18"
    output_dir.mkdir(parents=True)
    for name in (
        "strategy_lhb_shortline_review.csv",
        "strategy_mid_trend_review.csv",
        "strategy_tech_bottleneck_review.csv",
        "strategy_eod_publish_summary.json",
    ):
        (output_dir / name).write_text("ok", encoding="utf-8")
    monkeypatch.setattr(
        platform_ready,
        "load_strategy_daily_eod_status",
        lambda *args, **kwargs: {
            "status": "success",
            "lhb_shortline_status": "success",
            "mid_trend_status": "success",
            "tech_bottleneck_status": "success",
            "output_dir": str(output_dir),
            "summary_path": str(output_dir / "strategy_eod_publish_summary.json"),
        },
    )


def test_platform_ready_check_fails_when_frontend_inputs_are_missing(monkeypatch, tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _prepare_strategy_daily_eod_ok(monkeypatch, tmp_path)

    responses = {
        "daily_quality": [{"status": "warning", "expected_count": 15627, "actual_count": 15564, "missing_count": 63, "abnormal_count": 0}],
        "minute5_quality": [{"status": "success", "expected_count": 5209, "actual_count": 5209, "missing_count": 0, "abnormal_count": 0}],
        "deps_job": [{"status": "success"}],
        "health_status": [{"pipeline_status": "ready", "latest_ready_trade_date": "2026-06-18"}],
        "score_count": [{"count": 30}],
        "nonzero_score_count": [{"count": 30}],
        "watchlist_count": [{"count": 0}],
        "diagnostics_count": [{"count": 0}],
        "market_monitor_sources": [{"emotion_rows": 1, "index_rows": 5, "industry_rows": 85, "fund_flow_rows": 85}],
    }

    def fake_fetch(_service, check_name, _trade_date, **_kwargs):
        return responses[check_name]

    monkeypatch.setattr(platform_ready, "_fetch_check_rows", fake_fetch)

    result = platform_ready.run_platform_ready_check(
        "2026-06-18",
        reports_dirs=[reports_dir],
        min_watchlist_rows=1,
        min_reports=1,
    )

    assert result["status"] == "not_ready"
    failed = {item["name"] for item in result["checks"] if item["status"] == "fail"}
    assert failed == {"watchlist_default", "watchlist_diagnostics", "reports"}


def test_platform_ready_check_passes_when_data_and_frontend_inputs_exist(
    monkeypatch, tmp_path: Path
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "daily_research_2026-06-18.md").write_text("ok", encoding="utf-8")
    _prepare_strategy_daily_eod_ok(monkeypatch, tmp_path)

    responses = {
        "daily_quality": [{"status": "success", "expected_count": 15627, "actual_count": 15627, "missing_count": 0, "abnormal_count": 0}],
        "minute5_quality": [{"status": "success", "expected_count": 5209, "actual_count": 5209, "missing_count": 0, "abnormal_count": 0}],
        "deps_job": [{"status": "success"}],
        "health_status": [{"pipeline_status": "ready", "latest_ready_trade_date": "2026-06-18"}],
        "score_count": [{"count": 30}],
        "nonzero_score_count": [{"count": 30}],
        "watchlist_count": [{"count": 30}],
        "diagnostics_count": [{"count": 12}],
        "market_monitor_sources": [
            {
                "emotion_rows": 1,
                "index_rows": 5,
                "industry_rows": 85,
                "fund_flow_rows": 85,
            }
        ],
    }

    def fake_fetch(_service, check_name, _trade_date, **_kwargs):
        return responses[check_name]

    monkeypatch.setattr(platform_ready, "_fetch_check_rows", fake_fetch)

    result = platform_ready.run_platform_ready_check(
        "2026-06-18",
        reports_dirs=[reports_dir],
        min_watchlist_rows=1,
        min_reports=1,
    )

    assert result["status"] == "ready"
    assert all(item["status"] == "pass" for item in result["checks"])
    market_monitor = [item for item in result["checks"] if item["name"] == "market_monitor"]
    assert market_monitor == [
        {
            "name": "market_monitor",
            "status": "pass",
            "detail": "emotion_rows=1 index_rows=5 industry_rows=85 fund_flow_rows=85",
        }
    ]


def test_platform_ready_check_fails_when_market_monitor_sources_are_missing(
    monkeypatch, tmp_path: Path
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "daily_research_2026-06-18.md").write_text("ok", encoding="utf-8")
    _prepare_strategy_daily_eod_ok(monkeypatch, tmp_path)

    responses = {
        "daily_quality": [{"status": "success", "expected_count": 15627, "actual_count": 15627, "missing_count": 0, "abnormal_count": 0}],
        "minute5_quality": [{"status": "success", "expected_count": 5209, "actual_count": 5209, "missing_count": 0, "abnormal_count": 0}],
        "deps_job": [{"status": "success"}],
        "health_status": [{"pipeline_status": "ready", "latest_ready_trade_date": "2026-06-18"}],
        "score_count": [{"count": 30}],
        "nonzero_score_count": [{"count": 30}],
        "watchlist_count": [{"count": 30}],
        "diagnostics_count": [{"count": 12}],
        "market_monitor_sources": [
            {
                "emotion_rows": 0,
                "index_rows": 3,
                "industry_rows": 0,
                "fund_flow_rows": 0,
            }
        ],
    }

    def fake_fetch(_service, check_name, _trade_date, **_kwargs):
        return responses[check_name]

    monkeypatch.setattr(platform_ready, "_fetch_check_rows", fake_fetch)

    result = platform_ready.run_platform_ready_check(
        "2026-06-18",
        reports_dirs=[reports_dir],
        min_watchlist_rows=1,
        min_reports=1,
    )

    assert result["status"] == "not_ready"
    assert {
        item["name"]: item["detail"]
        for item in result["checks"]
        if item["status"] == "fail"
    } == {
        "market_monitor": "missing market_emotion_state_daily,index_daily_bar>=5,industry_daily_bar,fund_flow_proxy"
    }


def test_platform_ready_check_can_allow_degraded_minute5(
    monkeypatch, tmp_path: Path
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "daily_research_2026-06-18.md").write_text("ok", encoding="utf-8")
    _prepare_strategy_daily_eod_ok(monkeypatch, tmp_path)

    responses = {
        "daily_quality": [{"status": "warning", "expected_count": 15627, "actual_count": 15564, "missing_count": 63, "abnormal_count": 0}],
        "minute5_quality": [{"status": "warning", "expected_count": 5209, "actual_count": 5188, "missing_count": 21, "abnormal_count": 0}],
        "deps_job": [{"status": "success"}],
        "health_status": [{"pipeline_status": "NOT_READY", "latest_ready_trade_date": ""}],
        "score_count": [{"count": 5188}],
        "nonzero_score_count": [{"count": 5187}],
        "watchlist_count": [{"count": 30}],
        "diagnostics_count": [{"count": 50}],
        "market_monitor_sources": [{"emotion_rows": 1, "index_rows": 5, "industry_rows": 85, "fund_flow_rows": 85}],
    }

    def fake_fetch(_service, check_name, _trade_date, **_kwargs):
        return responses[check_name]

    monkeypatch.setattr(platform_ready, "_fetch_check_rows", fake_fetch)

    result = platform_ready.run_platform_ready_check(
        "2026-06-18",
        reports_dirs=[reports_dir],
        min_watchlist_rows=1,
        min_reports=1,
        allow_degraded_minute5=True,
    )

    assert result["status"] == "degraded_ready"
    assert all(item["status"] == "pass" for item in result["checks"])
    degraded = {item["name"] for item in result["checks"] if item.get("degraded")}
    assert degraded == {"daily_bar", "minute5", "health"}


def test_platform_ready_check_accepts_external_data_quality_gap_under_one_percent(
    monkeypatch, tmp_path: Path
):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "daily_research_2026-06-18.md").write_text("ok", encoding="utf-8")
    _prepare_strategy_daily_eod_ok(monkeypatch, tmp_path)

    responses = {
        "daily_quality": [
            {
                "status": "warning",
                "expected_count": 15627,
                "actual_count": 15564,
                "missing_count": 63,
                "abnormal_count": 0,
            }
        ],
        "minute5_quality": [
            {
                "status": "warning",
                "expected_count": 5209,
                "actual_count": 5188,
                "missing_count": 21,
                "abnormal_count": 0,
            }
        ],
        "deps_job": [{"status": "success"}],
        "health_status": [{"pipeline_status": "DEGRADED_READY", "latest_ready_trade_date": "2026-06-18"}],
        "score_count": [{"count": 5188}],
            "nonzero_score_count": [{"count": 5187}],
            "watchlist_count": [{"count": 30}],
            "diagnostics_count": [{"count": 50}],
            "market_monitor_sources": [{"emotion_rows": 1, "index_rows": 5, "industry_rows": 85, "fund_flow_rows": 85}],
    }

    def fake_fetch(_service, check_name, _trade_date, **_kwargs):
        return responses[check_name]

    monkeypatch.setattr(platform_ready, "_fetch_check_rows", fake_fetch)

    result = platform_ready.run_platform_ready_check(
        "2026-06-18",
        reports_dirs=[reports_dir],
        min_watchlist_rows=1,
        min_reports=1,
    )

    assert result["status"] == "degraded_ready"
    assert all(item["status"] == "pass" for item in result["checks"])
    degraded = {item["name"] for item in result["checks"] if item.get("degraded")}
    assert degraded == {"daily_bar", "minute5"}


def test_render_ready_message_is_mobile_sized():
    message = platform_ready.render_platform_ready_message(
        {
            "trade_date": "2026-06-18",
            "status": "not_ready",
            "checks": [
                {"name": "daily_bar", "status": "pass", "detail": "actual=15564 expected=15627 missing=63"},
                {"name": "watchlist_default", "status": "fail", "detail": "rows=0 required>=1"},
            ],
        }
    )

    assert "平台数据状态：not_ready" in message
    assert "daily_bar: pass" in message
    assert "watchlist_default: fail" in message
    assert len(message) < 1800


def test_platform_ready_check_fails_when_strategy_daily_eod_is_missing(monkeypatch, tmp_path: Path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "daily_research_2026-06-18.md").write_text("ok", encoding="utf-8")

    responses = {
        "daily_quality": [{"status": "success", "expected_count": 15627, "actual_count": 15627, "missing_count": 0, "abnormal_count": 0}],
        "minute5_quality": [{"status": "success", "expected_count": 5209, "actual_count": 5209, "missing_count": 0, "abnormal_count": 0}],
        "deps_job": [{"status": "success"}],
        "health_status": [{"pipeline_status": "ready", "latest_ready_trade_date": "2026-06-18"}],
        "score_count": [{"count": 30}],
        "nonzero_score_count": [{"count": 30}],
        "watchlist_count": [{"count": 30}],
        "diagnostics_count": [{"count": 12}],
        "market_monitor_sources": [{"emotion_rows": 1, "index_rows": 5, "industry_rows": 85, "fund_flow_rows": 85}],
    }

    def fake_fetch(_service, check_name, _trade_date, **_kwargs):
        return responses[check_name]

    monkeypatch.setattr(platform_ready, "_fetch_check_rows", fake_fetch)
    monkeypatch.setattr(platform_ready, "load_strategy_daily_eod_status", lambda *args, **kwargs: None)

    result = platform_ready.run_platform_ready_check(
        "2026-06-18",
        reports_dirs=[reports_dir],
        min_watchlist_rows=1,
        min_reports=1,
    )

    assert result["status"] == "not_ready"
    assert any(item["name"] == "strategy_daily_eod" and item["status"] == "fail" for item in result["checks"])
