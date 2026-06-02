import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.operator_decision.outcome_analytics import (
    build_decision_outcome_analytics,
    build_decision_outcome_analytics_from_frames,
    write_decision_outcome_analytics,
)


def _outcome_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "outcome_event_id": "outcome:1",
                "run_id": "p8-run",
                "decision_event_id": "decision:1",
                "review_session_id": "morning-review",
                "review_date": "2026-05-30",
                "asset_id": "CN:SH:600001",
                "stock_code": "600001.SH",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "source_context": "dashboard_topn",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "forward_returns": {"1": 0.10, "5": 0.20},
                "max_high_returns": {"1": 0.12, "5": 0.25},
                "max_low_drawdowns": {"1": 0.00, "5": -0.04},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "metadata": {"requires_follow_up": True},
            },
            {
                "outcome_event_id": "outcome:2",
                "run_id": "p8-run",
                "decision_event_id": "decision:2",
                "review_session_id": "morning-review",
                "review_date": "2026-05-30",
                "asset_id": "CN:SH:600002",
                "stock_code": "600002.SH",
                "stock_name": "Beta",
                "decision_label": "candidate",
                "source_context": "dashboard_topn",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "forward_returns": {"1": -0.02, "5": 0.10},
                "max_high_returns": {"1": 0.01, "5": 0.15},
                "max_low_drawdowns": {"1": -0.03, "5": -0.08},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "metadata": {"requires_follow_up": False},
            },
            {
                "outcome_event_id": "outcome:3",
                "run_id": "p8-run",
                "decision_event_id": "decision:3",
                "review_session_id": "afternoon-review",
                "review_date": "2026-05-31",
                "asset_id": "CN:SZ:000001",
                "stock_code": "000001.SZ",
                "stock_name": "Gamma",
                "decision_label": "caution",
                "source_context": "watchlist",
                "outcome_status": "insufficient_data",
                "available_future_bars": 1,
                "forward_returns": {"1": 0.01},
                "max_high_returns": {"1": 0.02},
                "max_low_drawdowns": {"1": -0.01},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "metadata": {"requires_follow_up": True},
            },
        ]
    )


def test_build_decision_outcome_analytics_groups_by_label_context_session_and_asset():
    analytics = build_decision_outcome_analytics_from_frames(
        outcome_events=_outcome_rows(),
        horizons=[1, 5],
    )

    by_label = analytics[
        (analytics["analytics_level"] == "decision_label")
        & (analytics["decision_label"] == "candidate")
    ].iloc[0]

    assert by_label["sample_count"] == 2
    assert by_label["complete_count"] == 2
    assert by_label["insufficient_data_count"] == 0
    assert by_label["follow_up_required_rate"] == 0.5
    assert by_label["forward_1d_return_mean"] == pytest.approx(0.04)
    assert by_label["forward_1d_return_median"] == pytest.approx(0.04)
    assert by_label["forward_1d_win_rate"] == 0.5
    assert by_label["forward_5d_return_mean"] == pytest.approx(0.15)
    assert by_label["forward_5d_win_rate"] == 1.0
    assert by_label["max_high_return_5d_mean"] == pytest.approx(0.20)
    assert by_label["max_low_drawdown_5d_mean"] == pytest.approx(-0.06)
    assert by_label["max_low_drawdown_5d_worst"] == pytest.approx(-0.08)

    assert set(analytics["analytics_level"]) == {
        "decision_label",
        "source_context",
        "review_session_id",
        "asset_id",
    }
    assert analytics[analytics["analytics_level"] == "source_context"]["source_context"].tolist() == [
        "dashboard_topn",
        "watchlist",
    ]


def test_build_decision_outcome_analytics_counts_insufficient_data_but_excludes_returns():
    analytics = build_decision_outcome_analytics_from_frames(
        outcome_events=_outcome_rows(),
        horizons=[1, 5],
    )

    caution = analytics[
        (analytics["analytics_level"] == "decision_label")
        & (analytics["decision_label"] == "caution")
    ].iloc[0]

    assert caution["sample_count"] == 1
    assert caution["complete_count"] == 0
    assert caution["insufficient_data_count"] == 1
    assert caution["follow_up_required_rate"] == 1.0
    assert pd.isna(caution["forward_1d_return_mean"])
    assert pd.isna(caution["forward_1d_win_rate"])


def test_build_decision_outcome_analytics_handles_empty_outcome_set():
    analytics = build_decision_outcome_analytics(
        start_date="2026-05-01",
        end_date="2026-06-30",
        outcome_events=pd.DataFrame(),
        horizons=[1, 5],
        run_id="p9-empty",
    )

    assert analytics["run_id"] == "p9-empty"
    assert analytics["review_start_date"] == "2026-05-01"
    assert analytics["review_end_date"] == "2026-06-30"
    assert analytics["status"] == "no_outcomes_recorded"
    assert analytics["manual_review_required"] is True
    assert analytics["auto_trade_enabled"] is False
    assert analytics["horizons"] == [1, 5]
    assert analytics["group_count"] == 0
    assert analytics["groups"] == []


def test_build_decision_outcome_analytics_preserves_run_metadata_and_safety_fields():
    analytics = build_decision_outcome_analytics(
        start_date="2026-05-01",
        end_date="2026-06-30",
        outcome_events=_outcome_rows(),
        horizons=[1, 5],
        run_id="p9-analytics-smoke",
    )

    assert analytics["run_id"] == "p9-analytics-smoke"
    assert analytics["review_start_date"] == "2026-05-01"
    assert analytics["review_end_date"] == "2026-06-30"
    assert analytics["status"] == "analytics_ready"
    assert analytics["manual_review_required"] is True
    assert analytics["auto_trade_enabled"] is False
    assert analytics["horizons"] == [1, 5]
    assert analytics["source_outcome_count"] == 3
    assert analytics["group_count"] == 9
    assert analytics["groups"][0]["analytics_level"] == "decision_label"


def test_write_decision_outcome_analytics_outputs_review_only_artifacts(tmp_path):
    analytics = build_decision_outcome_analytics(
        start_date="2026-05-01",
        end_date="2026-06-30",
        outcome_events=_outcome_rows(),
        horizons=[1, 5],
        run_id="p9-analytics-artifacts",
    )

    paths = write_decision_outcome_analytics(analytics, tmp_path)

    assert set(paths) == {"json_path", "groups_csv_path", "diagnostics_csv_path", "markdown_path"}
    payload = json.loads(Path(paths["json_path"]).read_text())
    assert payload["manual_review_required"] is True
    assert payload["auto_trade_enabled"] is False
    assert payload["diagnostic_count"] > 0

    groups = pd.read_csv(paths["groups_csv_path"])
    diagnostics = pd.read_csv(paths["diagnostics_csv_path"])
    assert set(groups["analytics_level"]) == {
        "decision_label",
        "source_context",
        "review_session_id",
        "asset_id",
    }
    assert {"diagnostic_type", "horizon", "analytics_level", "group_value", "metric_value"}.issubset(
        diagnostics.columns
    )
    assert diagnostics["diagnostic_type"].tolist()[:2] == [
        "top_forward_return",
        "bottom_forward_return",
    ]
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    assert "manual_review_required: true" in markdown
    assert "auto_trade_enabled: false" in markdown


def test_write_decision_outcome_analytics_handles_empty_outcome_set(tmp_path):
    analytics = build_decision_outcome_analytics(
        start_date="2026-05-01",
        end_date="2026-06-30",
        outcome_events=pd.DataFrame(),
        horizons=[1, 5],
        run_id="p9-empty",
    )

    paths = write_decision_outcome_analytics(analytics, tmp_path)

    payload = json.loads(Path(paths["json_path"]).read_text())
    assert payload["status"] == "no_outcomes_recorded"
    assert payload["diagnostic_count"] == 0
    assert pd.read_csv(paths["groups_csv_path"]).empty
    assert pd.read_csv(paths["diagnostics_csv_path"]).empty
    assert "No outcome groups recorded." in Path(paths["markdown_path"]).read_text(encoding="utf-8")
