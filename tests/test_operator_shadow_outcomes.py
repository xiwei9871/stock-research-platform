import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.operator_decision.shadow_outcomes import (
    SHADOW_OUTCOME_HORIZONS,
    build_shadow_outcome_review,
    build_shadow_outcomes_from_frames,
    write_shadow_outcome_review,
)


def _shadow_candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "shadow_candidate_id": "p12-shadow:001",
                "run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "candidate_reason": "Passed replay with acceptable drawdown.",
                "status": "shadow_ready",
                "shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            },
            {
                "shadow_candidate_id": "p12-shadow:002",
                "run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:002",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000002.SZ",
                "stock_code": "000002",
                "stock_name": "Vanke",
                "shadow_layer": "risk_shadow",
                "candidate_reason": "Observe risk-controlled candidate.",
                "status": "shadow_observe",
                "shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            },
        ]
    )


def _bars() -> pd.DataFrame:
    rows = []
    for asset_id, base_close in [("000001.SZ", 10.0), ("000002.SZ", 20.0)]:
        for offset in range(0, 21):
            close = base_close + offset if asset_id == "000001.SZ" else base_close - offset * 0.5
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": (pd.Timestamp("2026-06-30") + pd.Timedelta(days=offset)).strftime("%Y-%m-%d"),
                    "close": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                }
            )
    return pd.DataFrame(rows)


def test_build_shadow_outcomes_computes_forward_returns_and_drawdowns():
    result = build_shadow_outcomes_from_frames(
        shadow_candidates=_shadow_candidates(),
        bars=_bars(),
        horizons=[1, 5, 20],
        run_id="p13-shadow-outcomes-2026-07-31",
    )

    outcomes = result.set_index("shadow_candidate_id")
    ready = outcomes.loc["p12-shadow:001"]
    assert ready["outcome_status"] == "complete"
    assert ready["run_id"] == "p13-shadow-outcomes-2026-07-31"
    assert ready["source_p12_shadow_run_id"] == "p12-shadow-watchlist-2026-06-30"
    assert ready["source_p11_replay_run_id"] == "p11-replay-run-2026-06-30"
    assert round(float(ready["forward_1d_return"]), 6) == 0.1
    assert round(float(ready["forward_20d_return"]), 6) == 2.0
    assert round(float(ready["max_high_return_20d"]), 6) == 2.1
    assert round(float(ready["max_low_drawdown_20d"]), 6) == 0.0
    assert ready["manual_review_required"] is True
    assert ready["auto_trade_enabled"] is False
    assert ready["production_watchlist_enabled"] is False
    assert ready["production_write_enabled"] is False

    observe = outcomes.loc["p12-shadow:002"]
    assert observe["shadow_status"] == "shadow_observe"
    assert round(float(observe["forward_5d_return"]), 6) == -0.125
    assert round(float(observe["max_low_drawdown_20d"]), 6) == -0.55


def test_build_shadow_outcomes_marks_insufficient_future_data_without_zero_fill():
    short_bars = _bars()[lambda frame: frame["trade_date"].le("2026-07-04")]

    result = build_shadow_outcomes_from_frames(
        shadow_candidates=_shadow_candidates().iloc[:1],
        bars=short_bars,
        horizons=SHADOW_OUTCOME_HORIZONS,
    )

    row = result.iloc[0]
    assert row["outcome_status"] == "insufficient_data"
    assert pd.isna(row["forward_10d_return"])
    assert pd.isna(row["max_high_return_60d"])
    assert row["available_future_bars"] == 4


def test_build_shadow_outcomes_rejects_unsafe_or_production_enabled_candidates():
    unsafe = _shadow_candidates().copy()
    unsafe.loc[0, "production_watchlist_enabled"] = True
    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_outcomes_from_frames(shadow_candidates=unsafe, bars=_bars())

    malformed_watchlist = _shadow_candidates().copy().astype({"production_watchlist_enabled": object})
    malformed_watchlist.loc[0, "production_watchlist_enabled"] = "maybe"
    with pytest.raises(ValueError, match="production_watchlist_enabled"):
        build_shadow_outcomes_from_frames(shadow_candidates=malformed_watchlist, bars=_bars())

    malformed_auto_trade = _shadow_candidates().copy().astype({"auto_trade_enabled": object})
    malformed_auto_trade.loc[0, "auto_trade_enabled"] = "maybe"
    with pytest.raises(ValueError, match="auto_trade_enabled"):
        build_shadow_outcomes_from_frames(shadow_candidates=malformed_auto_trade, bars=_bars())

    execution_like = _shadow_candidates().copy()
    execution_like["order_id"] = ["order-1", ""]
    with pytest.raises(ValueError, match="unsafe_execution_field: order_id"):
        build_shadow_outcomes_from_frames(shadow_candidates=execution_like, bars=_bars())


def test_build_shadow_outcome_review_preserves_review_only_artifact_contract():
    review = build_shadow_outcome_review(
        review_date="2026-07-31",
        shadow_candidates=_shadow_candidates(),
        bars=_bars(),
        horizons=[1, 5, 20],
        run_id="p13-shadow-outcomes-2026-07-31",
    )

    assert review["run_id"] == "p13-shadow-outcomes-2026-07-31"
    assert review["review_date"] == "2026-07-31"
    assert review["status"] == "shadow_outcome_review_ready"
    assert review["manual_review_required"] is True
    assert review["auto_trade_enabled"] is False
    assert review["production_watchlist_enabled"] is False
    assert review["production_write_enabled"] is False
    assert review["outcome_count"] == 2
    assert review["horizons"] == [1, 5, 20]
    assert review["outcomes"][0]["shadow_candidate_id"] == "p12-shadow:001"
    assert review["outcomes"][0]["run_id"] == "p13-shadow-outcomes-2026-07-31"
    assert review["outcomes"][0]["source_p12_shadow_run_id"] == "p12-shadow-watchlist-2026-06-30"


def test_build_shadow_outcome_review_scopes_outcome_ids_by_p13_run_id():
    first = build_shadow_outcome_review(
        review_date="2026-07-31",
        shadow_candidates=_shadow_candidates().iloc[:1],
        bars=_bars(),
        horizons=[1],
        run_id="p13-shadow-outcomes-2026-07-31",
    )
    second = build_shadow_outcome_review(
        review_date="2026-08-01",
        shadow_candidates=_shadow_candidates().iloc[:1],
        bars=_bars(),
        horizons=[1],
        run_id="p13-shadow-outcomes-2026-08-01",
    )

    first_id = first["outcomes"][0]["shadow_outcome_id"]
    second_id = second["outcomes"][0]["shadow_outcome_id"]
    assert first["outcomes"][0]["shadow_candidate_id"] == second["outcomes"][0]["shadow_candidate_id"]
    assert first_id != second_id
    assert first_id.startswith("operator_shadow_outcome:p13-shadow-outcomes-2026-07-31:")
    assert second_id.startswith("operator_shadow_outcome:p13-shadow-outcomes-2026-08-01:")


def test_write_shadow_outcome_review_outputs_json_csv_and_markdown(tmp_path):
    review = build_shadow_outcome_review(
        review_date="2026-07-31",
        shadow_candidates=_shadow_candidates().iloc[:1],
        bars=_bars()[lambda frame: frame["trade_date"].le("2026-07-04")],
        horizons=[1, 10],
        run_id="p13-short",
    )

    paths = write_shadow_outcome_review(review, tmp_path)

    assert set(paths) == {"json_path", "details_csv_path", "markdown_path"}
    assert Path(paths["json_path"]).name == "operator_shadow_outcomes_2026-07-31.json"
    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["auto_trade_enabled"] is False
    assert payload["production_watchlist_enabled"] is False
    assert payload["outcomes"][0]["forward_10d_return"] is None

    details = pd.read_csv(paths["details_csv_path"])
    assert details.loc[0, "run_id"] == "p13-short"
    assert details.loc[0, "outcome_status"] == "insufficient_data"
    assert pd.isna(details.loc[0, "forward_10d_return"])

    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "P13 Shadow Watchlist Outcome Tracking" in markdown
    assert "manual_review_required: true" in markdown
    assert "production_watchlist_enabled: false" in markdown
    assert "p12-shadow:001" in markdown


def test_write_empty_shadow_outcome_review_outputs_readable_details_header(tmp_path):
    review = build_shadow_outcome_review(
        review_date="2026-07-31",
        shadow_candidates=_shadow_candidates().iloc[:0],
        bars=_bars(),
        horizons=[1, 5],
        run_id="p13-empty",
    )

    paths = write_shadow_outcome_review(review, tmp_path)

    details = pd.read_csv(paths["details_csv_path"])
    assert details.empty
    assert list(details.columns) == [
        "shadow_outcome_id",
        "run_id",
        "shadow_candidate_id",
        "source_p12_shadow_run_id",
        "replay_result_id",
        "source_p11_replay_run_id",
        "source_p10_proposal_run_id",
        "source_p9_analytics_run_id",
        "candidate_date",
        "asset_id",
        "stock_code",
        "stock_name",
        "shadow_layer",
        "shadow_status",
        "candidate_reason",
        "source_shadow_artifact_path",
        "outcome_artifact_path",
        "manual_review_required",
        "auto_trade_enabled",
        "production_watchlist_enabled",
        "production_write_enabled",
        "outcome_status",
        "available_future_bars",
        "base_trade_date",
        "base_close",
        "forward_1d_return",
        "max_high_return_1d",
        "max_low_drawdown_1d",
        "forward_5d_return",
        "max_high_return_5d",
        "max_low_drawdown_5d",
    ]
