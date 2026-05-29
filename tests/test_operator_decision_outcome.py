import json
from pathlib import Path

import pandas as pd

from stock_research.operator_decision.outcome import (
    OUTCOME_HORIZONS,
    build_decision_outcome_review,
    build_decision_outcomes_from_frames,
    summarize_decision_outcomes,
    write_decision_outcome_review,
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


def test_build_decision_outcome_review_preserves_review_only_artifact_contract():
    review = build_decision_outcome_review(
        start_date="2026-01-01",
        end_date="2026-01-31",
        decision_events=_decision_events(),
        bars=_bars(),
        horizons=[1, 5, 20],
        run_id="p8-smoke",
    )

    assert review["run_id"] == "p8-smoke"
    assert review["review_start_date"] == "2026-01-01"
    assert review["review_end_date"] == "2026-01-31"
    assert review["status"] == "review_ready"
    assert review["manual_review_required"] is True
    assert review["auto_trade_enabled"] is False
    assert review["outcome_count"] == 2
    assert review["summary_count"] == 4
    assert review["horizons"] == [1, 5, 20]

    first = review["outcomes"][0]
    assert first["event_id"] == "operator_decision:p8-smoke:0:aaa"
    assert first["evidence_artifact_id"] == "dashboard:topn:2026-01-01"
    assert first["manual_review_required"] is True
    assert first["auto_trade_enabled"] is False
    assert first["forward_20d_return"] == 2.0


def test_write_decision_outcome_review_outputs_json_csv_and_markdown(tmp_path):
    review = build_decision_outcome_review(
        start_date="2026-01-01",
        end_date="2026-01-31",
        decision_events=_decision_events().iloc[:1],
        bars=_bars()[lambda frame: frame["trade_date"].le("2026-01-05")],
        horizons=[1, 10],
        run_id="p8-short",
    )

    paths = write_decision_outcome_review(review, tmp_path)

    assert set(paths) == {"json_path", "details_csv_path", "summary_csv_path", "markdown_path"}
    assert Path(paths["json_path"]).name == "operator_decision_outcome_review_2026-01-01_2026-01-31.json"
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["auto_trade_enabled"] is False
    assert payload["manual_review_required"] is True
    assert payload["outcomes"][0]["forward_10d_return"] is None

    details = pd.read_csv(paths["details_csv_path"])
    assert details.loc[0, "outcome_status"] == "insufficient_data"
    assert pd.isna(details.loc[0, "forward_10d_return"])

    summary = pd.read_csv(paths["summary_csv_path"])
    assert set(summary["summary_level"]) == {"decision_label", "source_context"}

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "P8 Decision Outcome Review" in markdown
    assert "manual_review_required: true" in markdown
    assert "auto_trade_enabled: false" in markdown
    assert "operator_decision:p8-smoke:0:aaa" in markdown


def test_build_decision_outcome_review_handles_empty_decision_set():
    review = build_decision_outcome_review(
        start_date="2026-01-01",
        end_date="2026-01-31",
        decision_events=pd.DataFrame(),
        bars=_bars(),
        horizons=[1, 5],
    )

    assert review["status"] == "no_decisions_recorded"
    assert review["manual_review_required"] is True
    assert review["auto_trade_enabled"] is False
    assert review["outcome_count"] == 0
    assert review["summary_count"] == 0
    assert review["outcomes"] == []
    assert review["summary"] == []
