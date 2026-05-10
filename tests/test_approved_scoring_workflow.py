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
    )

    assert list(result["trade_date"]) == ["2026-05-01", "2026-05-02"]
    assert list(result["score_rows"]) == [5, 5]
    assert calls[0]["approved_only"] is True
