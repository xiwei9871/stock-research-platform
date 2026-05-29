import pandas as pd

from stock_research.operator_decision.outcome import (
    OUTCOME_HORIZONS,
    build_decision_outcomes_from_frames,
    summarize_decision_outcomes,
)


def _decision_events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "event_id": "operator_decision:p8-smoke:0:aaa",
                "review_session_id": "p8-smoke",
                "review_date": "2026-01-01",
                "asset_id": "A",
                "stock_code": "000001.SH",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "evidence_artifact_id": "dashboard:topn:2026-01-01",
                "evidence_path": "outputs/p6/topn.json",
                "source_context": "dashboard_topn",
                "requires_follow_up": True,
                "follow_up_note": "check next close strength",
                "notes": "strong score",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "source_artifact_path": "outputs/p7/journal.json",
            },
            {
                "event_id": "operator_decision:p8-smoke:1:bbb",
                "review_session_id": "p8-smoke",
                "review_date": "2026-01-01",
                "asset_id": "B",
                "stock_code": "000002.SZ",
                "stock_name": "Beta",
                "decision_label": "caution",
                "evidence_artifact_id": "watchlist:2026-01-01",
                "evidence_path": "outputs/p5/watchlist.json",
                "source_context": "watchlist",
                "requires_follow_up": False,
                "follow_up_note": "",
                "notes": "risk active",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "source_artifact_path": "outputs/p7/journal.json",
            },
        ]
    )


def _bars() -> pd.DataFrame:
    rows = []
    for asset_id, base_close in [("A", 10.0), ("B", 20.0)]:
        for offset in range(0, 21):
            close = base_close + offset if asset_id == "A" else base_close - offset * 0.5
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": (pd.Timestamp("2026-01-01") + pd.Timedelta(days=offset)).strftime("%Y-%m-%d"),
                    "close": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                }
            )
    return pd.DataFrame(rows)


def test_build_decision_outcomes_computes_forward_returns_and_drawdowns():
    result = build_decision_outcomes_from_frames(
        decision_events=_decision_events(),
        bars=_bars(),
        horizons=[1, 3, 5, 10, 20],
    )

    outcomes = result.set_index("event_id")
    candidate = outcomes.loc["operator_decision:p8-smoke:0:aaa"]
    assert candidate["outcome_status"] == "complete"
    assert round(float(candidate["forward_1d_return"]), 6) == 0.1
    assert round(float(candidate["forward_20d_return"]), 6) == 2.0
    assert round(float(candidate["max_high_return_20d"]), 6) == 2.1
    assert round(float(candidate["max_low_drawdown_20d"]), 6) == 0.0
    assert candidate["decision_label"] == "candidate"
    assert candidate["evidence_artifact_id"] == "dashboard:topn:2026-01-01"
    assert candidate["manual_review_required"] is True
    assert candidate["auto_trade_enabled"] is False

    caution = outcomes.loc["operator_decision:p8-smoke:1:bbb"]
    assert round(float(caution["forward_5d_return"]), 6) == -0.125
    assert round(float(caution["max_low_drawdown_20d"]), 6) == -0.55


def test_build_decision_outcomes_marks_insufficient_future_data_without_zero_fill():
    short_bars = _bars()[lambda frame: frame["trade_date"].le("2026-01-05")]

    result = build_decision_outcomes_from_frames(
        decision_events=_decision_events().iloc[:1],
        bars=short_bars,
        horizons=OUTCOME_HORIZONS,
    )

    row = result.iloc[0]
    assert row["outcome_status"] == "insufficient_data"
    assert pd.isna(row["forward_10d_return"])
    assert pd.isna(row["max_high_return_60d"])
    assert row["available_future_bars"] == 4


def test_build_decision_outcomes_rejects_execution_enabled_events():
    unsafe = _decision_events().copy()
    unsafe.loc[0, "auto_trade_enabled"] = True

    try:
        build_decision_outcomes_from_frames(decision_events=unsafe, bars=_bars())
    except ValueError as exc:
        assert "auto_trade_not_allowed" in str(exc)
    else:
        raise AssertionError("expected unsafe decision event to be rejected")


def test_summarize_decision_outcomes_groups_by_label_and_source_context():
    outcomes = build_decision_outcomes_from_frames(
        decision_events=_decision_events(),
        bars=_bars(),
        horizons=[1, 5, 20],
    )

    summary = summarize_decision_outcomes(outcomes)
    by_label = summary[
        (summary["summary_level"] == "decision_label")
        & (summary["decision_label"] == "candidate")
    ].iloc[0]

    assert by_label["sample_count"] == 1
    assert by_label["complete_count"] == 1
    assert by_label["forward_20d_return_mean"] == 2.0
    assert by_label["follow_up_required_rate"] == 1.0

    by_context = summary[
        (summary["summary_level"] == "source_context")
        & (summary["source_context"] == "watchlist")
    ].iloc[0]
    assert by_context["decision_label"] == ""
    assert by_context["sample_count"] == 1
