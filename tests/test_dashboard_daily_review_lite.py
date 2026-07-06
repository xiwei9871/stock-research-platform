from stock_research.dashboard.daily_review_lite import _sections


def test_sections_maps_current_market_and_strategy_payload_shapes():
    sections = _sections(
        selected_trade_date="2026-07-03",
        summary={
            "latest_market_date": "2026-07-03",
            "latest_factor_date": "2026-07-03",
            "latest_score_date": "2026-07-03",
        },
        market={
            "trade_date": "2026-07-03",
            "market_breadth": {"up_count": 3527, "down_count": 1581},
            "market_emotion": {
                "summary": {"score": 64.105},
                "limit_performance": {"limit_up_count": 105, "limit_down_count": 25},
            },
        },
        queue={
            "groups": [
                {"strategy_name": "LHB Shortline Combo", "count": 5},
                {"strategy_name": "Mid Trend Combo", "count": 5},
                {"strategy_name": "Tech Bottleneck Discovery", "count": 5},
            ]
        },
        artifacts=[],
        run={},
    )

    market_review = next(section for section in sections if section["key"] == "market_review")
    strategy_summaries = next(section for section in sections if section["key"] == "strategy_summaries")

    assert ("上涨/下跌", "3527 / 1581") in [(item["label"], item["value"]) for item in market_review["items"]]
    assert ("综合强度", "64.1") in [(item["label"], item["value"]) for item in market_review["items"]]
    assert [(item["label"], item["value"]) for item in strategy_summaries["items"]] == [
        ("LHB Shortline Combo", "5 只"),
        ("Mid Trend Combo", "5 只"),
        ("Tech Bottleneck Discovery", "5 只"),
    ]
