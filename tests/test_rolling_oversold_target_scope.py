from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from stock_research import cli
from stock_research.rolling_oversold import pipeline
from stock_research.rolling_oversold.contracts import RollingOversoldConfig
from stock_research.rolling_oversold.loaders import (
    _membership_params,
    _membership_sql,
    _sector_bar_params,
    _sector_bar_sql,
)


ANCHOR = date(2026, 7, 31)


def _target_states(*codes: str) -> pd.DataFrame:
    rows = []
    for rank, code in enumerate(codes, start=1):
        rows.append(
            {
                "sector_system": "ths",
                "sector_code": code,
                "sector_name": f"Concept {code}",
                "sector_gate_status": "confirmed",
                "sector_research_eligibility": "eligible",
                "sector_oversold_score": 80.0 + rank,
                "sector_repairability_score": 70.0,
                "sector_direction_score": 60.0,
                "sector_recovery_state": "fresh_oversold",
                "sector_low_date_20d": "2026-07-30",
                "sector_low_close_20d": 90.0,
                "sector_recovery_from_low_20d": 0.02,
                "sector_days_since_low_20d": 1,
                "sector_volume_ratio_5_20": 1.1,
                "sector_ma5_slope_5d": 0.01,
                "sector_ma10_slope_10d": 0.01,
            }
        )
    return pd.DataFrame(rows)


def _empty_inputs() -> SimpleNamespace:
    return SimpleNamespace(data_cutoff_date=ANCHOR)


def test_config_normalizes_and_validates_explicit_ths_concept_scope():
    config = RollingOversoldConfig(
        ANCHOR,
        None,
        (1, 3, 5),
        None,
        ("ths",),
        concept_codes=["300238", "300239"],
    )

    assert config.concept_codes == ("300238", "300239")
    with pytest.raises(ValueError, match="concept_codes"):
        RollingOversoldConfig(ANCHOR, concept_codes=["300238", "300238"])
    with pytest.raises(ValueError, match="concept_codes"):
        RollingOversoldConfig(ANCHOR, concept_codes=["300238", ""])
    with pytest.raises(ValueError, match="concept_codes"):
        RollingOversoldConfig(ANCHOR, concept_codes=["C1"])


def test_cli_target_code_file_accepts_csv_or_one_code_per_line_and_rejects_invalid(
    tmp_path,
):
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text("concept_code\n300238\n300239\n", encoding="utf-8")
    list_path = tmp_path / "targets.txt"
    list_path.write_text("300238\n300239\n", encoding="utf-8")

    assert cli._load_rolling_concept_codes_file(csv_path) == ("300238", "300239")
    assert cli._load_rolling_concept_codes_file(list_path) == ("300238", "300239")

    duplicate_path = tmp_path / "duplicate.csv"
    duplicate_path.write_text("concept_code\n300238\n300238\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        cli._load_rolling_concept_codes_file(duplicate_path)

    blank_path = tmp_path / "blank.txt"
    blank_path.write_text("300238\n\n", encoding="utf-8")
    with pytest.raises(ValueError, match="blank"):
        cli._load_rolling_concept_codes_file(blank_path)

    non_ths_path = tmp_path / "non_ths.csv"
    non_ths_path.write_text("concept_system,concept_code\nem,300238\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ths"):
        cli._load_rolling_concept_codes_file(non_ths_path)


def test_target_loader_sql_filters_concept_codes_without_affecting_industry_sql():
    membership_sql = _membership_sql(
        "core.concept_membership", "concept", ("ths",), ("300238", "300239")
    )
    assert "m.concept_system = ANY(%s)" in membership_sql
    assert "m.concept_code = ANY(%s)" in membership_sql
    assert _membership_params(
        "2026-07-31", ("ths",), ("300238", "300239")
    )[-2:] == [["ths"], ["300238", "300239"]]

    sector_sql = _sector_bar_sql("concept", ("ths",), ("300238", "300239"))
    assert "concept_system = ANY(%s)" in sector_sql
    assert "concept_code = ANY(%s)" in sector_sql
    assert _sector_bar_params(
        "2026-01-01", "2026-07-31", ("ths",), ("300238", "300239")
    ) == ["2026-01-01", "2026-07-31", ["ths"], ["300238", "300239"]]


def test_target_replay_forces_sector_v2_route_for_non_sector_score_version(tmp_path):
    codes_path = tmp_path / "targets.txt"
    codes_path.write_text("300238\n300239\n", encoding="utf-8")
    args = cli.build_parser().parse_args(
        [
            "rolling-sector-oversold-replay",
            "--anchor-start-date",
            "2026-07-31",
            "--output-dir",
            str(tmp_path / "replay"),
            "--score-version",
            "rolling_oversold_v1_custom",
            "--concept-codes-file",
            str(codes_path),
        ]
    )

    config = cli._rolling_oversold_config_from_args(
        args,
        anchor_date=ANCHOR,
        anchor_end_date=ANCHOR,
    )

    assert config.score_version.startswith("rolling_oversold_sector_")
    assert config.concept_systems == ("ths",)
    assert config.concept_codes == ("300238", "300239")


def test_scope_fingerprint_is_persisted_and_bidirectionally_isolates_cache(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *a, **k: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(
        pipeline,
        "_score_sector_batch_states",
        lambda *a, **k: pd.concat(
            [_target_states("300238", "300239"), _target_states("300240")],
            ignore_index=True,
        ),
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *a, **k: pd.DataFrame())

    unscoped_config = RollingOversoldConfig(
        anchor_start_date=ANCHOR,
        score_version="rolling_oversold_sector_v2",
    )
    target_config = RollingOversoldConfig(
        anchor_start_date=ANCHOR,
        score_version="rolling_oversold_sector_v2",
        concept_systems=("ths",),
        concept_codes=("300238", "300239"),
    )
    unscoped_dir = tmp_path / "unscoped"
    target_dir = tmp_path / "target"
    unscoped = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=unscoped_config,
        inputs=_empty_inputs(),
        output_dir=unscoped_dir,
        service="research-test",
    )
    target = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=target_config,
        inputs=_empty_inputs(),
        output_dir=target_dir,
        service="research-test",
    )

    unscoped_manifest = unscoped["batch_manifest"]
    target_manifest = target["batch_manifest"]
    assert unscoped_manifest["scope_fingerprint"] == "unscoped"
    assert target_manifest["scope_fingerprint"] == pipeline._scope_fingerprint(target_config)
    assert target_manifest["scope_fingerprint"] != unscoped_manifest["scope_fingerprint"]

    assert pipeline._load_existing_sector_batch_result(
        output_dir=unscoped_dir,
        anchor_date=ANCHOR,
        score_version=unscoped_config.score_version,
        expected_scope_fingerprint=pipeline._scope_fingerprint(target_config),
    ) is None
    assert pipeline._load_existing_sector_batch_result(
        output_dir=target_dir,
        anchor_date=ANCHOR,
        score_version=target_config.score_version,
        expected_scope_fingerprint=pipeline._scope_fingerprint(unscoped_config),
    ) is None


def test_target_batch_publishes_only_requested_ths_rows(monkeypatch, tmp_path):
    config = RollingOversoldConfig(
        anchor_start_date=ANCHOR,
        concept_systems=("ths",),
        concept_codes=("300238", "300239"),
    )
    monkeypatch.setattr(pipeline, "compute_market_regime_features", lambda *a, **k: {"market_regime": "risk_off"})
    monkeypatch.setattr(
        pipeline,
        "_score_sector_batch_states",
        lambda *a, **k: pd.concat(
            [_target_states("300238", "300239"), _target_states("300240")],
            ignore_index=True,
        ),
    )
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *a, **k: pd.DataFrame())

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        inputs=_empty_inputs(),
        output_dir=tmp_path,
        service="research-test",
    )

    assert result["blocked"] is False
    board = result["sector_states"]
    assert board["sector_system"].tolist() == ["ths", "ths"]
    assert set(board["sector_code"]) == {"300238", "300239"}


def test_target_batch_missing_code_fails_closed_without_snapshot(monkeypatch, tmp_path):
    config = RollingOversoldConfig(
        anchor_start_date=ANCHOR,
        concept_systems=("ths",),
        concept_codes=("300238", "300239"),
    )
    monkeypatch.setattr(pipeline, "compute_market_regime_features", lambda *a, **k: {"market_regime": "risk_off"})
    monkeypatch.setattr(pipeline, "_score_sector_batch_states", lambda *a, **k: _target_states("300238"))

    result = pipeline.run_sector_batch(
        anchor_date=ANCHOR,
        config=config,
        inputs=_empty_inputs(),
        output_dir=tmp_path,
        service="research-test",
    )

    assert result["blocked"] is True
    assert result["blocked_reason"] == "target_scope"
    assert result["snapshot"] is None
    assert any(gap["asset_id"] == "ths:300239" for gap in result["batch_manifest"]["backfill_requests"])
