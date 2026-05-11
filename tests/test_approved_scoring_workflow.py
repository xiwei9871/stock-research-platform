from stock_research import approved_scoring_workflow


def test_score_approved_factors_range_scores_each_date(monkeypatch):
    calls = []
    monkeypatch.setattr(
        approved_scoring_workflow,
        "score_stored_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 5,
    )

    result = approved_scoring_workflow.score_approved_factors_range(
        start_date="2026-05-01",
        end_date="2026-05-02",
        score_version="manual_v1",
        trading_days_only=False,
    )

    assert list(result["trade_date"]) == ["2026-05-01", "2026-05-02"]
    assert list(result["score_rows"]) == [5, 5]
    assert calls[0]["approved_only"] is True


def test_score_approved_factors_range_uses_trading_dates_by_default(monkeypatch):
    calls = []

    monkeypatch.setattr(
        approved_scoring_workflow,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["2024-01-02", "2024-01-03"],
    )
    monkeypatch.setattr(
        approved_scoring_workflow,
        "score_stored_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 8,
    )

    result = approved_scoring_workflow.score_approved_factors_range(
        start_date="2024-01-01",
        end_date="2024-01-05",
        score_version="manual_v1",
    )

    assert list(result["trade_date"]) == ["2024-01-02", "2024-01-03"]
    assert list(result["score_rows"]) == [8, 8]
    assert calls[0]["trade_date"] == "2024-01-02"
    assert calls[0]["approved_only"] is True


def test_score_approved_factors_range_empty_trading_dates_keeps_columns(monkeypatch):
    calls = []

    monkeypatch.setattr(
        approved_scoring_workflow,
        "load_trade_dates_for_backfill",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        approved_scoring_workflow,
        "score_stored_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 8,
    )

    result = approved_scoring_workflow.score_approved_factors_range(
        start_date="2024-01-01",
        end_date="2024-01-05",
    )

    assert result.empty
    assert list(result.columns) == ["trade_date", "score_rows"]
    assert calls == []
