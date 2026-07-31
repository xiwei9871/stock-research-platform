from __future__ import annotations

import json

import pytest

from stock_research.strategy_data_policy import (
    DataGap,
    StrategyRuntimeBudget,
    StrategyRuntimeTimeout,
    assert_db_only_source,
    write_backfill_request,
)


def test_db_only_policy_rejects_external_source_attempt():
    with pytest.raises(ValueError, match="db_only"):
        assert_db_only_source("baostock")


def test_gap_request_is_deterministic_and_contains_strategy_context(tmp_path):
    request = write_backfill_request(
        tmp_path,
        strategy="consumer_oversold_weekly",
        trade_date="2026-07-29",
        ranking_version="v2",
        gaps=[
            DataGap(
                "daily_bars",
                "A",
                "2026-07-29",
                "2026-07-29",
                1,
                0,
                "missing",
            )
        ],
    )
    payload = json.loads(request.read_text(encoding="utf-8"))
    assert payload["data_source_policy"] == "db_only"
    assert payload["gaps"][0]["dataset"] == "daily_bars"
    assert payload["gaps"][0]["asset_id"] == "A"


def test_runtime_budget_records_stages_and_raises_after_deadline(monkeypatch):
    budget = StrategyRuntimeBudget(timeout_seconds=1.0)
    budget.start()
    budget.begin_stage("market")
    budget.end_stage("market")
    monkeypatch.setattr(
        "stock_research.strategy_data_policy.monotonic",
        lambda: budget.started_at + 2.0,
    )
    with pytest.raises(StrategyRuntimeTimeout, match="runtime budget"):
        budget.checkpoint("scoring")


def test_runtime_budget_metadata_has_non_negative_elapsed_and_stage_values():
    budget = StrategyRuntimeBudget(timeout_seconds=3600.0)
    budget.start()
    budget.begin_stage("market")
    budget.end_stage("market")
    metadata = budget.metadata()
    assert metadata["runtime_budget_seconds"] == 3600.0
    assert metadata["runtime_seconds"] >= 0.0
    assert metadata["stage_timings_seconds"]["market"] >= 0.0
