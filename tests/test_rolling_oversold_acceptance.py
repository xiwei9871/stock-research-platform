from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from stock_research.rolling_oversold import pipeline
from stock_research.rolling_oversold.contracts import RollingOversoldConfig
from stock_research.rolling_oversold.preflight import PreflightResult


ANCHORS = [date(2026, 7, 21), date(2026, 7, 22), date(2026, 7, 23)]


def _sector_rows(family: str) -> pd.DataFrame:
    if family == "industry":
        return pd.DataFrame(
            [
                {
                    "sector_system": "sw",
                    "sector_code": "I1",
                    "sector_name": "芯片",
                    "sector_oversold_score": 92.0,
                    "sector_repairability_score": 78.0,
                    "sector_direction_score": 70.0,
                    "sector_recovery_state": "fresh_oversold",
                    "sector_gate_status": "confirmed",
                },
                {
                    "sector_system": "sw",
                    "sector_code": "I2",
                    "sector_name": "未映射行业",
                    "sector_oversold_score": 0.0,
                    "sector_repairability_score": 0.0,
                    "sector_direction_score": 0.0,
                    "sector_recovery_state": "unknown",
                    "sector_gate_status": "blocked",
                },
            ]
        )
    return pd.DataFrame(
        [
            {
                "sector_system": "theme",
                "sector_code": "C1",
                "sector_name": "消费",
                "sector_oversold_score": 86.0,
                "sector_repairability_score": 74.0,
                "sector_direction_score": 68.0,
                "sector_recovery_state": "repairing",
                "sector_gate_status": "watch",
            }
        ]
    )


def _candidate_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "000001",
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "芯片",
                "sector_oversold_score": 92.0,
                "sector_repairability_score": 78.0,
                "sector_direction_score": 70.0,
                "sector_recovery_state": "fresh_oversold",
                "sector_gate_status": "confirmed",
                "stock_score": 91.0,
                "stock_rank": 1,
                "stock_lifecycle": "expected_repair",
                "anchor_close": 100.0,
                "adjusted_close_source": "qfq",
            }
        ]
    )


@pytest.fixture
def acceptance_fixture(monkeypatch):
    observed_cutoffs: list[date] = []
    all_stock_bars = pd.DataFrame(
        [
            {
                "asset_id": "000001",
                "trade_date": current.isoformat(),
                "close": 100.0 + (current - ANCHORS[0]).days,
                "amount": 1_000_000.0,
            }
            for current in [date(2026, 7, 20) + timedelta(days=offset) for offset in range(12)]
        ]
    )

    def fake_load_inputs(*, anchor_date: date, **kwargs):
        observed_cutoffs.append(anchor_date)
        frozen = all_stock_bars.loc[
            pd.to_datetime(all_stock_bars["trade_date"]).dt.date <= anchor_date
        ].copy()
        return SimpleNamespace(
            data_cutoff_date=anchor_date,
            stock_bars=frozen,
            stock_status=pd.DataFrame(),
            industry_bars=pd.DataFrame({"industry_system": ["sw"]}),
            concept_bars=pd.DataFrame({"concept_system": ["theme"]}),
            industry_membership=pd.DataFrame(),
            concept_membership=pd.DataFrame(),
        )

    def fake_preflight(inputs, *, anchor_date, **kwargs):
        return PreflightResult(
            blocked=False,
            data_cutoff_date=anchor_date,
            checked_datasets=(),
            coverage_rows=(),
            gaps=(),
        )

    def fake_sector_score(bars, **kwargs):
        family = "industry" if "industry_system" in bars.columns else "concept"
        return _sector_rows(family)

    def fake_features(inputs, *, anchor_date, **kwargs):
        # This assertion is the acceptance guard against future bars entering
        # feature construction for an earlier anchor.
        dates = pd.to_datetime(inputs.stock_bars["trade_date"]).dt.date
        assert dates.le(anchor_date).all()
        return pd.DataFrame(
            [
                {
                    "asset_id": "000001",
                    "sector_system": "sw",
                    "sector_code": "I1",
                    "sector_name": "芯片",
                }
            ]
        )

    def fake_stock_score(*args, **kwargs):
        return _candidate_rows()

    def fake_evaluation_bars(*, anchor_date, evaluation_cutoff, **kwargs):
        rows = []
        current = anchor_date + timedelta(days=1)
        while current <= evaluation_cutoff:
            rows.append(
                {
                    "asset_id": "000001",
                    "trade_date": current.isoformat(),
                    "close": 101.0,
                }
            )
            current += timedelta(days=1)
        return pd.DataFrame(rows, columns=["asset_id", "trade_date", "close"])

    monkeypatch.setattr(pipeline, "_load_complete_anchor_sessions", lambda **kwargs: ANCHORS)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", fake_load_inputs)
    monkeypatch.setattr(pipeline, "run_rolling_preflight", fake_preflight)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "neutral"},
    )
    monkeypatch.setattr(pipeline, "score_sector_states", fake_sector_score)
    monkeypatch.setattr(pipeline, "_build_stock_features", fake_features)
    monkeypatch.setattr(pipeline, "score_rolling_stock_candidates", fake_stock_score)
    monkeypatch.setattr(pipeline, "_load_evaluation_bars", fake_evaluation_bars)
    return SimpleNamespace(observed_cutoffs=observed_cutoffs)


def test_acceptance_snapshot_is_reproducible_and_outcomes_are_delayed(
    tmp_path, acceptance_fixture
):
    config = RollingOversoldConfig(
        anchor_start_date=ANCHORS[0],
        anchor_end_date=ANCHORS[-1],
        sector_top_n=30,
        stock_top_n=20,
    )

    first = pipeline.run_rolling_replay(
        config=config,
        output_dir=tmp_path / "first",
        service="research-test",
    )
    second = pipeline.run_rolling_replay(
        config=config,
        output_dir=tmp_path / "second",
        service="research-test",
    )

    assert first["snapshot_ids"] == second["snapshot_ids"]
    assert first["future_rows_used_for_scoring"] == 0
    assert bool(first["all_sector_rows_have_status"]) is True
    assert acceptance_fixture.observed_cutoffs == ANCHORS * 2

    first_manifest = Path(first["anchors"][0]["paths"]["snapshot_manifest"])
    second_manifest = Path(second["anchors"][0]["paths"]["snapshot_manifest"])
    assert json.loads(first_manifest.read_text(encoding="utf-8"))["snapshot_id"] == json.loads(
        second_manifest.read_text(encoding="utf-8")
    )["snapshot_id"]
    sector_states = pd.read_csv(first["anchors"][0]["paths"]["sector_states"])
    assert sector_states["sector_gate_status"].isin(
        {"confirmed", "watch", "blocked", "unknown"}
    ).all()


def test_acceptance_does_not_report_5d_hit_before_fifth_session(
    tmp_path, acceptance_fixture
):
    result = pipeline.run_rolling_daily(
        trade_date=ANCHORS[-1],
        config=RollingOversoldConfig(anchor_start_date=ANCHORS[0]),
        output_dir=tmp_path,
        service="research-test",
    )

    detail = pd.read_csv(result["paths"]["evaluation"])
    fifth = detail.loc[detail["forward_horizon_days"].eq(5)]
    assert not fifth.empty
    assert fifth["evaluation_status"].eq("pending").all()
    assert fifth["forward_Nd_status"].eq("pending").all()
