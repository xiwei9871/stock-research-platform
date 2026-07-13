from stock_research.dashboard import daily_review_lite
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
        theme_research={
            "status": "ready",
            "reviewed_theme_count": 1,
            "mapped_company_count": 4,
            "recent_reviewed_update_count": 2,
            "evidence_gap_count": 3,
            "incomplete_evidence_tracks": ["humanoid_robotics_source_pack_v1"],
        },
    )

    market_review = next(section for section in sections if section["key"] == "market_review")
    strategy_summaries = next(section for section in sections if section["key"] == "strategy_summaries")
    theme_research = next(section for section in sections if section["key"] == "theme_research")

    assert ("上涨/下跌", "3527 / 1581") in [(item["label"], item["value"]) for item in market_review["items"]]
    assert ("综合强度", "64.1") in [(item["label"], item["value"]) for item in market_review["items"]]
    assert [(item["label"], item["value"]) for item in strategy_summaries["items"]] == [
        ("LHB Shortline Combo", "5 只"),
        ("Mid Trend Combo", "5 只"),
        ("Tech Bottleneck Discovery", "5 只"),
    ]
    assert [(item["label"], item["value"]) for item in theme_research["items"]] == [
        ("已审核主题", "1"),
        ("映射公司", "4"),
        ("近期审核更新", "2"),
        ("证据缺口", "3"),
        ("未完成证据轨道", "humanoid_robotics_source_pack_v1"),
    ]


def test_theme_research_section_degrades_without_breaking_daily_review() -> None:
    sections = _sections(
        selected_trade_date="2026-07-03",
        summary={},
        market={},
        queue={},
        artifacts=[],
        run={},
        theme_research={
            "status": "partial",
            "reviewed_theme_count": 0,
            "mapped_company_count": 0,
            "recent_reviewed_update_count": 0,
            "evidence_gap_count": 0,
            "incomplete_evidence_tracks": [],
        },
    )

    theme_research = next(section for section in sections if section["key"] == "theme_research")
    assert theme_research["status"] == "partial"
    assert theme_research["items"][0] == {"label": "已审核主题", "value": "0"}


def test_fallback_preserves_theme_research_warning(monkeypatch) -> None:
    monkeypatch.setattr(
        daily_review_lite,
        "load_platform_summary",
        lambda service: {"latest_market_date": "2026-07-10"},
    )
    monkeypatch.setattr(
        daily_review_lite,
        "_latest_registered_run",
        lambda trade_date, service: None,
    )
    monkeypatch.setattr(
        daily_review_lite,
        "_generate_and_register_run",
        lambda trade_date, service: (_ for _ in ()).throw(OSError("read-only fixture")),
    )
    monkeypatch.setattr(
        daily_review_lite,
        "_build_live_daily_review_payload",
        lambda trade_date, service: {
            "trade_date": trade_date,
            "status": "partial",
            "run": {},
            "fallback": False,
            "sections": [],
            "artifacts": [],
            "theme_research": {"status": "partial"},
            "warnings": ["theme_research_digest_unavailable"],
        },
    )

    payload = daily_review_lite.build_daily_review_lite(service="test")

    assert payload["warnings"] == [
        "theme_research_digest_unavailable",
        "no registered daily review run selected",
    ]
