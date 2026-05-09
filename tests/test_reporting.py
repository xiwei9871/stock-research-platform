from stock_research.reporting import format_daily_report


def test_format_daily_report_includes_selection_details():
    report = format_daily_report(
        trade_date="2026-05-06",
        quality=[{"check_name": "hfq_bar_count", "status": "ok", "metric_value": 5200}],
        selections=[
            {
                "rank": 1,
                "asset_id": "CN:SH:600000",
                "score": 12.3,
                "reasons": ["20日动量为正", "60日趋势为正", "20日平均成交额较高"],
                "risk_tags": ["high_volatility"],
            }
        ],
        log_path="/Users/xiwei/stock_research/logs/research_20260507.log",
    )

    assert "AI 盯盘与选股日报" in report
    assert "2026-05-06" in report
    assert "CN:SH:600000" in report
    assert "high_volatility" in report


def test_format_daily_report_marks_failed_quality_as_abnormal():
    report = format_daily_report(
        trade_date="2026-05-06",
        quality=[{"check_name": "hfq_bar_count", "status": "fail", "metric_value": 0}],
        selections=[],
        log_path="/Users/xiwei/stock_research/logs/research_20260507.log",
    )

    assert "数据状态：异常" in report


def test_format_daily_report_marks_empty_quality_as_abnormal():
    report = format_daily_report(
        trade_date="2026-05-06",
        quality=[],
        selections=[],
        log_path="/Users/xiwei/stock_research/logs/research_20260507.log",
    )

    assert "数据状态：异常" in report


def test_format_daily_report_uses_defaults_for_missing_quality_keys():
    report = format_daily_report(
        trade_date="2026-05-06",
        quality=[{}],
        selections=[],
        log_path="/Users/xiwei/stock_research/logs/research_20260507.log",
    )

    assert "- unknown_check：unknown，值=unknown" in report


def test_format_daily_report_prints_empty_selection_message():
    report = format_daily_report(
        trade_date="2026-05-06",
        quality=[{"check_name": "hfq_bar_count", "status": "ok", "metric_value": 5200}],
        selections=[],
        log_path="/Users/xiwei/stock_research/logs/research_20260507.log",
    )

    assert "- 无候选股票" in report


def test_format_daily_report_uses_defaults_for_missing_selection_keys():
    report = format_daily_report(
        trade_date="2026-05-06",
        quality=[{"check_name": "hfq_bar_count", "status": "ok", "metric_value": 5200}],
        selections=[{}],
        log_path="/Users/xiwei/stock_research/logs/research_20260507.log",
    )

    assert "-. UNKNOWN 评分：-" in report
    assert "入选原因：暂无入选原因" in report
    assert "风险标签：无明显风险标签" in report


def test_format_daily_report_prints_fallback_for_empty_reasons():
    report = format_daily_report(
        trade_date="2026-05-06",
        quality=[{"check_name": "hfq_bar_count", "status": "ok", "metric_value": 5200}],
        selections=[
            {
                "rank": 1,
                "asset_id": "CN:SH:600000",
                "score": 12.3,
                "reasons": [],
                "risk_tags": [],
            }
        ],
        log_path="/Users/xiwei/stock_research/logs/research_20260507.log",
    )

    assert "入选原因：暂无入选原因" in report


def test_format_daily_report_avoids_trading_instruction_language():
    report = format_daily_report(
        trade_date="2026-05-06",
        quality=[{"check_name": "hfq_bar_count", "status": "ok", "metric_value": 5200}],
        selections=[
            {
                "rank": 1,
                "asset_id": "CN:SH:600000",
                "score": 12.3,
                "reasons": ["20日动量为正"],
                "risk_tags": [],
            }
        ],
        log_path="/Users/xiwei/stock_research/logs/research_20260507.log",
    )

    assert "买入" not in report
    assert "卖出" not in report
    assert "仓位" not in report
