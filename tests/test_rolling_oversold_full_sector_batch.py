from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from stock_research.rolling_oversold import pipeline
from stock_research.rolling_oversold.contracts import RollingOversoldConfig
from stock_research.rolling_oversold.reporting import load_rolling_oversold_snapshot
from stock_research.rolling_oversold.snapshots import (
    build_rolling_snapshot,
    write_rolling_snapshot,
)


ANCHOR = date(2026, 7, 31)


def _fixture_inputs(sector_count: int = 302) -> SimpleNamespace:
    sectors = [f"C{index:03d}" for index in range(sector_count)]
    names = [f"Concept {index:03d}" for index in range(sector_count)]
    dates = [ANCHOR - timedelta(days=offset) for offset in range(19, -1, -1)]
    bars: list[dict[str, object]] = []
    for sector_index, (code, name) in enumerate(zip(sectors, names, strict=True)):
        # The final sector intentionally has no bars, so the scored board must
        # retain it as blocked_data rather than silently dropping the row.
        if sector_index == sector_count - 1:
            continue
        for offset, trade_date in enumerate(dates):
            close = 100.0 - (12.0 if offset == 11 else 0.0) + max(0, offset - 11) * 1.2
            bars.append(
                {
                    "concept_system": "ths",
                    "concept_code": code,
                    "concept_name": name,
                    "trade_date": trade_date,
                    "close": close,
                    "preclose": close - 0.5,
                    "volume": 100.0 + offset * 5.0,
                    "amount": 1000.0 + offset * 50.0,
                }
            )
    membership = pd.DataFrame(
        {
            "asset_id": [f"A{index:03d}" for index in range(sector_count)],
            "concept_system": ["ths"] * sector_count,
            "concept_code": sectors,
            "concept_name": names,
            "start_date": [date(2020, 1, 1)] * sector_count,
            "end_date": [pd.NaT] * sector_count,
        }
    )
    empty = pd.DataFrame()
    return SimpleNamespace(
        anchor_date=ANCHOR,
        data_cutoff_date=ANCHOR,
        trading_dates=pd.DataFrame({"trade_date": dates}),
        index_bars=empty,
        stock_bars=empty,
        stock_status=empty,
        industry_membership=empty,
        concept_membership=membership,
        industry_bars=empty,
        concept_bars=pd.DataFrame(bars),
        finance=empty,
        valuation=empty,
        index_ids=("SSE_COMPOSITE",),
        score_version="rolling_oversold_v1",
    )


def _fake_stock_features() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index in range(301):
        code = f"C{index:03d}"
        for slot in range(2):
            rows.append(
                {
                    # The same asset intentionally belongs to two sectors;
                    # batch mode must not globally deduplicate it.
                    "asset_id": "SHARED" if index < 2 and slot == 0 else f"A{index:03d}-{slot}",
                    "sector_system": "ths",
                    "sector_code": code,
                    "sector_name": f"Concept {index:03d}",
                    "anchor_return": 0.02 + slot * 0.01,
                    "distance_to_252d_high": 0.25,
                    "oversold_depth": 0.25,
                    "stock_excess_return": 0.01,
                    "activity": 100.0 + slot,
                    "quality": 70.0,
                    "valuation": 60.0,
                    "size_elasticity": 10.0 + slot,
                    "anchor_close": 10.0 + slot,
                    "adjusted_close_source": "qfq",
                }
            )
    return pd.DataFrame(rows)


def test_config_defaults_and_validates_sector_output_top_n():
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    assert config.sector_output_top_n == 10
    with pytest.raises(ValueError, match="sector_output_top_n"):
        RollingOversoldConfig(anchor_start_date=ANCHOR, sector_output_top_n=0)
    with pytest.raises(ValueError, match="sector_output_top_n"):
        RollingOversoldConfig(anchor_start_date=ANCHOR, sector_output_top_n=True)


def test_full_sector_batch_has_independent_ranks_one_load_and_runtime_manifest(
    monkeypatch, tmp_path
):
    inputs = _fixture_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    load_calls = 0
    regime_calls = 0
    feature_calls = 0
    sector_calls = 0

    def fake_load(**kwargs):
        nonlocal load_calls
        load_calls += 1
        return inputs

    def fake_regime(*args, **kwargs):
        nonlocal regime_calls
        regime_calls += 1
        return {"market_regime": "risk_off"}

    def fake_features(*args, **kwargs):
        nonlocal feature_calls
        feature_calls += 1
        return _fake_stock_features()

    real_sector_score = pipeline.score_sector_states

    def fake_sector_score(*args, **kwargs):
        nonlocal sector_calls
        sector_calls += 1
        return real_sector_score(*args, **kwargs)

    monkeypatch.setattr(pipeline, "load_rolling_inputs", fake_load)
    monkeypatch.setattr(pipeline, "compute_market_regime_features", fake_regime)
    monkeypatch.setattr(pipeline, "score_sector_states", fake_sector_score)
    monkeypatch.setattr(pipeline, "_build_stock_features", fake_features)

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    assert load_calls == 1
    assert regime_calls == 1
    assert sector_calls == 1
    assert feature_calls == 1
    assert result["sector_count"] == 302
    board = result["sector_states"]
    candidates = result["stock_candidates"]
    assert len(board) == 302
    assert candidates.groupby(["sector_system", "sector_code"])["sector_stock_rank"].min().eq(1).all()
    assert candidates["asset_id"].eq("SHARED").sum() == 2
    blocked_code = "C301"
    assert board.loc[board["sector_code"].eq(blocked_code), "sector_research_eligibility"].iloc[0] == "blocked_data"
    assert not candidates["sector_code"].eq(blocked_code).any()
    timings = result["runtime_metadata"]["stage_timings_seconds"]
    assert {"load", "sector", "stock", "publication"}.issubset(timings)
    assert isinstance(result["batch_manifest"], dict)


def test_sector_batch_alias_artifacts_round_trip_sector_stock_rank(monkeypatch, tmp_path):
    inputs = _fixture_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: _fake_stock_features())

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )
    manifest_path = Path(result["paths"]["manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_dir = manifest_path.parent
    assert {"sector_daily_board.csv", "sector_stock_candidates.csv"}.issubset(
        manifest["artifact_hashes"]
    )
    assert (artifact_dir / "sector_daily_board.csv").read_bytes() == (
        artifact_dir / "sector_states.csv"
    ).read_bytes()
    assert (artifact_dir / "sector_stock_candidates.csv").read_bytes() == (
        artifact_dir / "stock_candidates.csv"
    ).read_bytes()
    loaded = load_rolling_oversold_snapshot(artifact_dir)
    assert "sector_stock_rank" in loaded["stock_candidates"]
    assert loaded["stock_candidates"]["sector_stock_rank"].notna().all()
    second = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )
    assert second["batch_manifest"] == manifest


def test_sector_batch_fast_path_rejects_requested_previous_snapshot_lineage(monkeypatch, tmp_path):
    inputs = _fixture_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: _fake_stock_features())

    pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    with pytest.raises(ValueError, match="predecessor does not match"):
        pipeline.run_sector_batch(
            anchor_date=ANCHOR,
            config=config,
            output_dir=tmp_path,
            inputs=inputs,
            previous_snapshot={"snapshot_id": "different|2026-07-30"},
            service="research-test",
        )


def test_sector_batch_fast_path_requires_intact_alias_artifacts(monkeypatch, tmp_path):
    inputs = _fixture_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: _fake_stock_features())

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )
    manifest_path = Path(result["paths"]["manifest"])
    alias_path = manifest_path.parent / "sector_stock_candidates.csv"
    alias_path.write_bytes(alias_path.read_bytes() + b"corruption")

    assert pipeline._load_existing_sector_batch_result(
        output_dir=tmp_path,
        anchor_date=ANCHOR,
        score_version=config.score_version,
        previous_snapshot=None,
    ) is None


def test_sector_batch_fast_path_requires_intact_canonical_artifacts(monkeypatch, tmp_path):
    inputs = _fixture_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: _fake_stock_features())

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )
    manifest_path = Path(result["paths"]["manifest"])
    canonical_path = manifest_path.parent / "sector_states.csv"
    canonical_path.write_bytes(canonical_path.read_bytes() + b"corruption")

    assert pipeline._load_existing_sector_batch_result(
        output_dir=tmp_path,
        anchor_date=ANCHOR,
        score_version=config.score_version,
    ) is None


def test_batch_snapshot_requires_positive_contiguous_sector_stock_ranks(monkeypatch):
    inputs = _fixture_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: _fake_stock_features())

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        service="research-test",
    )
    invalid = dict(result["snapshot"])
    invalid["stock_candidates"] = invalid["stock_candidates"].copy()
    invalid["stock_candidates"].loc[invalid["stock_candidates"].index[0], "sector_stock_rank"] = 0
    with pytest.raises(ValueError, match="sector_stock_rank"):
        build_rolling_snapshot(
            anchor_date=ANCHOR,
            data_cutoff_date=ANCHOR,
            market_regime={"market_regime": "risk_off"},
            sector_states=invalid["sector_states"],
            stock_candidates=invalid["stock_candidates"],
            previous_snapshot=None,
            score_version=config.score_version,
            batch_mode=True,
        )

    non_contiguous = dict(result["snapshot"])
    non_contiguous["stock_candidates"] = non_contiguous["stock_candidates"].copy()
    first_sector = non_contiguous["stock_candidates"]["sector_code"].iloc[0]
    sector_rows = non_contiguous["stock_candidates"]["sector_code"].eq(first_sector)
    non_contiguous["stock_candidates"].loc[sector_rows, "sector_stock_rank"] = [1, 3]
    with pytest.raises(ValueError, match="contiguous"):
        build_rolling_snapshot(
            anchor_date=ANCHOR,
            data_cutoff_date=ANCHOR,
            market_regime={"market_regime": "risk_off"},
            sector_states=non_contiguous["sector_states"],
            stock_candidates=non_contiguous["stock_candidates"],
            previous_snapshot=None,
            score_version=config.score_version,
            batch_mode=True,
        )


def test_batch_snapshot_missing_sector_stock_rank_is_rejected(monkeypatch):
    inputs = _fixture_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: _fake_stock_features())

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        service="research-test",
    )
    stock_candidates = result["snapshot"]["stock_candidates"].drop(columns=["sector_stock_rank"])
    with pytest.raises(ValueError, match="sector_stock_rank"):
        build_rolling_snapshot(
            anchor_date=ANCHOR,
            data_cutoff_date=ANCHOR,
            market_regime={"market_regime": "risk_off"},
            sector_states=result["snapshot"]["sector_states"],
            stock_candidates=stock_candidates,
            previous_snapshot=None,
            score_version=config.score_version,
            batch_mode=True,
        )


def test_batch_snapshot_rejects_exact_duplicate_composite_candidate(monkeypatch):
    inputs = _fixture_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: _fake_stock_features())

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        service="research-test",
    )
    stocks = result["snapshot"]["stock_candidates"]
    duplicate = pd.concat([stocks.iloc[[0]], stocks.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate composite"):
        build_rolling_snapshot(
            anchor_date=ANCHOR,
            data_cutoff_date=ANCHOR,
            market_regime={"market_regime": "risk_off"},
            sector_states=result["snapshot"]["sector_states"],
            stock_candidates=duplicate,
            previous_snapshot=None,
            score_version=config.score_version,
            batch_mode=True,
        )


def test_batch_snapshot_rejects_partial_explicit_v2_stock_repair_schema(monkeypatch, tmp_path):
    inputs = _fixture_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: _fake_stock_features())

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        service="research-test",
    )
    partial = dict(result["snapshot"])
    partial["stock_candidates"] = partial["stock_candidates"].drop(
        columns=["sector_volume_ratio_5_20"]
    )
    with pytest.raises(ValueError, match="sector_volume_ratio_5_20"):
        write_rolling_snapshot(
            partial,
            output_dir=tmp_path,
            batch_mode=True,
        )


def test_batch_snapshot_previous_duplicate_assets_use_sector_scoped_revisions(
    monkeypatch, tmp_path
):
    inputs = _fixture_inputs()
    config = RollingOversoldConfig(anchor_start_date=ANCHOR)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: _fake_stock_features())

    first = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        service="research-test",
    )["snapshot"]
    with pytest.raises(ValueError, match="duplicate asset_id SHARED"):
        build_rolling_snapshot(
            anchor_date=ANCHOR,
            data_cutoff_date=ANCHOR,
            market_regime={"market_regime": "risk_off"},
            sector_states=first["sector_states"],
            stock_candidates=first["stock_candidates"],
            previous_snapshot=None,
            score_version=config.score_version,
        )
    next_anchor = ANCHOR + timedelta(days=1)
    second = build_rolling_snapshot(
        anchor_date=next_anchor,
        data_cutoff_date=next_anchor,
        market_regime={
            "market_regime": "risk_off",
            "preflight": first["preflight"],
        },
        sector_states=first["sector_states"],
        stock_candidates=first["stock_candidates"],
        previous_snapshot=first,
        score_version=config.score_version,
        batch_mode=True,
    )
    shared = second["stock_candidates"].loc[
        second["stock_candidates"]["asset_id"].eq("SHARED")
    ]
    assert len(shared) == 2
    assert shared["lifecycle_delta"].notna().all()
    assert write_rolling_snapshot(
        second,
        output_dir=tmp_path,
        batch_mode=True,
    )["status"] == "created"
