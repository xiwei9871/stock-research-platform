from stock_research.dashboard import overview


def test_build_dashboard_overview_combines_read_models(monkeypatch):
    monkeypatch.setattr(
        overview,
        "load_top_scores_for_dashboard",
        lambda trade_date, score_version, top_n: [{"asset_id": "000001.SZ"}],
    )
    monkeypatch.setattr(
        overview,
        "load_watchlist_signals_for_dashboard",
        lambda watchlist_id, trade_date: [{"asset_id": "000002.SZ"}],
    )
    monkeypatch.setattr(
        overview,
        "load_report_links",
        lambda trade_date: [{"title": "daily_topn_2026-05-29.md"}],
    )

    result = overview.build_dashboard_overview(
        trade_date="2026-05-29",
        score_version="manual_v1",
        watchlist_id="default",
        top_n=20,
    )

    assert result["trade_date"] == "2026-05-29"
    assert result["top_scores"] == [{"asset_id": "000001.SZ"}]
    assert result["watchlist_signals"] == [{"asset_id": "000002.SZ"}]
    assert result["reports"] == [{"title": "daily_topn_2026-05-29.md"}]
