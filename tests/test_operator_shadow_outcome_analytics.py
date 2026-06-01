import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research.operator_decision.shadow_outcome_analytics import (
    DEFAULT_SHADOW_OUTCOME_ANALYTICS_HORIZONS,
    build_shadow_outcome_analytics,
    build_shadow_outcome_analytics_from_frames,
    write_shadow_outcome_analytics,
)


def _outcomes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:001",
                "run_id": "p13-shadow-outcomes-2026-08-29",
                "shadow_candidate_id": "p12-shadow:001",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-analytics-2026-05-30-2026-06-30",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "outcome_status": "complete",
                "available_future_bars": 60,
                "forward_5d_return": 0.10,
                "forward_20d_return": 0.20,
                "max_high_return_20d": 0.30,
                "max_low_drawdown_20d": -0.05,
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            },
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:002",
                "run_id": "p13-shadow-outcomes-2026-08-29",
                "shadow_candidate_id": "p12-shadow:002",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:002",
                "source_p11_replay_run_id": "p11-replay-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-analytics-2026-05-30-2026-06-30",
                "candidate_date": "2026-06-30",
                "asset_id": "000002.SZ",
                "stock_code": "000002",
                "stock_name": "Vanke",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "outcome_status": "complete",
                "available_future_bars": 60,
                "forward_5d_return": -0.02,
                "forward_20d_return": 0.04,
                "max_high_return_20d": 0.08,
                "max_low_drawdown_20d": -0.12,
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            },
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:003",
                "run_id": "p13-shadow-outcomes-2026-08-29",
                "shadow_candidate_id": "p12-shadow:003",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:003",
                "source_p11_replay_run_id": "p11-replay-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-analytics-2026-05-30-2026-06-30",
                "candidate_date": "2026-06-30",
                "asset_id": "000003.SZ",
                "shadow_layer": "risk_shadow",
                "shadow_status": "shadow_observe",
                "outcome_status": "insufficient_data",
                "available_future_bars": 3,
                "forward_5d_return": None,
                "forward_20d_return": None,
                "max_high_return_20d": None,
                "max_low_drawdown_20d": None,
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            },
        ]
    )


def test_build_shadow_outcome_analytics_groups_by_layer_and_status():
    result = build_shadow_outcome_analytics_from_frames(
        shadow_outcomes=_outcomes(),
        horizons=[5, 20],
    )

    groups = result.set_index("group_key")
    trend_ready = groups.loc["trend_shadow|shadow_ready"]
    assert trend_ready["shadow_layer"] == "trend_shadow"
    assert trend_ready["shadow_status"] == "shadow_ready"
    assert trend_ready["sample_count"] == 2
    assert trend_ready["complete_count"] == 2
    assert trend_ready["insufficient_data_count"] == 0
    assert trend_ready["source_p12_shadow_run_count"] == 1
    assert round(float(trend_ready["forward_5d_return_mean"]), 6) == 0.04
    assert round(float(trend_ready["forward_20d_return_median"]), 6) == 0.12
    assert round(float(trend_ready["forward_5d_win_rate"]), 6) == 0.5
    assert round(float(trend_ready["max_low_drawdown_20d_worst"]), 6) == -0.12
    assert trend_ready["manual_review_required"] is True
    assert trend_ready["auto_trade_enabled"] is False
    assert trend_ready["production_watchlist_enabled"] is False
    assert trend_ready["production_write_enabled"] is False

    observe = groups.loc["risk_shadow|shadow_observe"]
    assert observe["sample_count"] == 1
    assert observe["complete_count"] == 0
    assert observe["insufficient_data_count"] == 1
    assert pd.isna(observe["forward_5d_return_mean"])


def test_build_shadow_outcome_analytics_preserves_review_metadata_and_writes_artifacts(tmp_path):
    analytics = build_shadow_outcome_analytics(
        review_start_date="2026-06-30",
        review_end_date="2026-08-29",
        shadow_outcomes=_outcomes(),
        horizons=[5, 20],
        run_id="p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
    )
    paths = write_shadow_outcome_analytics(analytics, tmp_path)

    payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
    assert payload["run_id"] == "p14-shadow-outcome-analytics-2026-06-30-2026-08-29"
    assert payload["group_by"] == ["shadow_layer", "shadow_status"]
    assert payload["group_count"] == 2
    assert payload["manual_review_required"] is True
    assert payload["auto_trade_enabled"] is False
    assert Path(paths["groups_csv_path"]).exists()
    assert Path(paths["markdown_path"]).exists()


def test_build_shadow_outcome_analytics_rejects_production_enabled_rows():
    outcomes = _outcomes()
    outcomes.loc[0, "production_watchlist_enabled"] = True

    with pytest.raises(ValueError, match="production_watchlist_not_allowed"):
        build_shadow_outcome_analytics_from_frames(shadow_outcomes=outcomes)


def test_build_shadow_outcome_analytics_rejects_missing_lineage():
    outcomes = _outcomes()
    outcomes.loc[0, "source_p10_proposal_run_id"] = ""

    with pytest.raises(ValueError, match="required_field_missing: source_p10_proposal_run_id"):
        build_shadow_outcome_analytics_from_frames(shadow_outcomes=outcomes)


def test_default_horizons_are_positive_and_stable():
    assert DEFAULT_SHADOW_OUTCOME_ANALYTICS_HORIZONS == [1, 3, 5, 10, 20, 60]
