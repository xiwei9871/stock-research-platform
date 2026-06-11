from stock_research.dashboard import market_monitor


def test_build_market_monitor_eod_uses_latest_complete_date(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-10",
            "latest_factor_date": "2026-06-10",
            "latest_score_date": "2026-06-10",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "topn_preview": [
                {
                    "trade_date": "2026-06-10",
                    "asset_id": "000001.SZ",
                    "rank": 1,
                    "score_total": 91.2,
                    "score_version": "manual_v1",
                    "score_components": {},
                }
            ],
        },
    )
    monkeypatch.setattr(
        market_monitor,
        "load_report_links",
        lambda trade_date: [
            {
                "report_type": "daily_topn_report",
                "title": "daily_topn_2026-06-10_manual_v1.md",
                "path": "/reports/topn.md",
                "format": "md",
                "trade_date": trade_date,
            }
        ],
    )

    payload = market_monitor.build_market_monitor_eod()

    assert payload["trade_date"] == "2026-06-10"
    assert payload["freshness"]["mode"] == "eod"
    assert payload["freshness"]["is_realtime"] is False
    assert payload["coverage"]["market_assets"] == 5300
    assert payload["strategy_signal_summary"]["topn_preview_count"] == 1
    assert payload["generated_reports"][0]["report_type"] == "daily_topn_report"


def test_build_market_monitor_eod_returns_warning_without_market_date(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": None,
            "latest_factor_date": None,
            "latest_score_date": None,
            "market_asset_count": 0,
            "score_asset_count": 0,
            "factor_count": 0,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])

    payload = market_monitor.build_market_monitor_eod()

    assert payload["trade_date"] == ""
    assert "latest complete market date is unavailable" in payload["warnings"]


def test_build_market_monitor_eod_warns_without_market_date_when_trade_date_explicit(
    monkeypatch,
):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": None,
            "latest_factor_date": None,
            "latest_score_date": None,
            "market_asset_count": 0,
            "score_asset_count": 0,
            "factor_count": 0,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])

    payload = market_monitor.build_market_monitor_eod(trade_date="2026-06-10")

    assert payload["trade_date"] == "2026-06-10"
    assert "latest complete market date is unavailable" in payload["warnings"]


def test_build_market_monitor_eod_warns_when_score_or_factor_dates_differ(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-10",
            "latest_factor_date": "2026-06-08",
            "latest_score_date": "2026-06-09",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])

    payload = market_monitor.build_market_monitor_eod(trade_date="2026-06-10")

    assert payload["freshness"]["latest_factor_date"] == "2026-06-08"
    assert payload["freshness"]["latest_score_date"] == "2026-06-09"
    assert (
        "latest score date 2026-06-09 differs from market monitor trade date 2026-06-10"
        in payload["warnings"]
    )
    assert (
        "latest factor date 2026-06-08 differs from market monitor trade date 2026-06-10"
        in payload["warnings"]
    )
