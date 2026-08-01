from __future__ import annotations

import ast
from datetime import date, timedelta
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from stock_research.rolling_oversold.contracts import RollingOversoldConfig
from stock_research.rolling_oversold import pipeline
from stock_research.rolling_oversold.preflight import PreflightResult
from stock_research.rolling_oversold.reporting import (
    load_rolling_oversold_snapshot,
    write_rolling_sector_oversold_report,
)
from stock_research.rolling_oversold.stock_scoring import StockScoringDataGap
from stock_research.strategy_data_policy import DataGap


def test_replay_processes_complete_sessions_ascending_and_links_previous_snapshot(
    monkeypatch, tmp_path
):
    config = RollingOversoldConfig(
        anchor_start_date=date(2026, 7, 21),
        anchor_end_date=date(2026, 7, 22),
    )
    monkeypatch.setattr(
        pipeline,
        "_load_complete_anchor_sessions",
        lambda **kwargs: [date(2026, 7, 22), date(2026, 7, 21)],
    )
    calls: list[tuple[date, object]] = []

    def fake_run_one_anchor(*, anchor_date, previous_snapshot, **kwargs):
        calls.append((anchor_date, previous_snapshot))
        snapshot = {
            "snapshot_id": f"rolling_oversold_v1|{anchor_date.isoformat()}",
            "sector_states": [],
        }
        return {
            "blocked": False,
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot": snapshot,
            "runtime_seconds": 0.01,
        }

    monkeypatch.setattr(pipeline, "run_one_anchor", fake_run_one_anchor)

    result = pipeline.run_rolling_replay(
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    assert [call[0] for call in calls] == [date(2026, 7, 21), date(2026, 7, 22)]
    assert calls[0][1] is None
    assert calls[1][1]["snapshot_id"] == "rolling_oversold_v1|2026-07-21"
    assert result["snapshot_ids"] == [
        "rolling_oversold_v1|2026-07-21",
        "rolling_oversold_v1|2026-07-22",
    ]
    assert result["anchors_processed"] == 2
    assert result["blocked"] == 0
    assert result["future_rows_used_for_scoring"] == 0
    assert result["all_sector_rows_have_status"] is True


def test_replay_stops_at_first_block_to_preserve_snapshot_lineage(monkeypatch, tmp_path):
    sessions = [date(2026, 7, 21), date(2026, 7, 22), date(2026, 7, 23)]
    config = RollingOversoldConfig(
        anchor_start_date=sessions[0],
        anchor_end_date=sessions[-1],
    )
    monkeypatch.setattr(pipeline, "_load_complete_anchor_sessions", lambda **kwargs: sessions)
    seen: list[date] = []

    def fake_run_one_anchor(*, anchor_date, previous_snapshot, **kwargs):
        seen.append(anchor_date)
        if anchor_date == sessions[1]:
            return {"blocked": True, "snapshot": None, "runtime_seconds": 0.01}
        snapshot = {
            "snapshot_id": f"rolling_oversold_v1|{anchor_date.isoformat()}",
            "sector_states": [],
        }
        return {"blocked": False, "snapshot": snapshot, "runtime_seconds": 0.01}

    monkeypatch.setattr(pipeline, "run_one_anchor", fake_run_one_anchor)

    result = pipeline.run_rolling_replay(
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    assert seen == sessions[:2]
    assert result["anchors_processed"] == 2
    assert result["blocked"] == 1
    assert result["snapshot_ids"] == ["rolling_oversold_v1|2026-07-21"]


def test_replay_refuses_blocked_anchor_before_configured_start(monkeypatch, tmp_path):
    blocked = date(2026, 7, 21)
    start = date(2026, 7, 22)
    end = date(2026, 7, 23)
    config = RollingOversoldConfig(anchor_start_date=start, anchor_end_date=end)
    blocked_dir = (
        tmp_path
        / "rolling_sector_oversold"
        / "blocked"
        / f"anchor={blocked.isoformat()}"
        / "version=rolling_oversold_v1"
    )
    blocked_dir.mkdir(parents=True)
    (blocked_dir / "preflight.json").write_text('{"blocked": true}\n', encoding="utf-8")
    monkeypatch.setattr(
        pipeline,
        "_load_complete_anchor_sessions",
        lambda **kwargs: [start, end],
    )
    monkeypatch.setattr(
        pipeline,
        "run_one_anchor",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not bridge blocked lineage")),
    )

    with pytest.raises(ValueError, match="unresolved blocked anchor"):
        pipeline.run_rolling_replay(
            config=config,
            output_dir=tmp_path,
            service="research-test",
        )


def test_preflight_blocked_stops_before_scoring_and_persists_gap_artifacts(
    monkeypatch, tmp_path
):
    anchor = date(2026, 7, 21)
    config = RollingOversoldConfig(anchor_start_date=anchor)
    gap = DataGap(
        dataset="market_daily_bar",
        asset_id="000001",
        start_date=anchor.isoformat(),
        end_date=anchor.isoformat(),
        expected_rows=1,
        actual_rows=0,
        reason="missing_cutoff_bar",
    )
    inputs = SimpleNamespace(data_cutoff_date=anchor)
    preflight = PreflightResult(
        blocked=True,
        data_cutoff_date=anchor,
        checked_datasets=("market_daily_bar",),
        coverage_rows=(),
        gaps=(gap,),
        status="blocked_missing_data",
    )
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs, raising=False)
    monkeypatch.setattr(
        pipeline,
        "run_rolling_preflight",
        lambda *args, **kwargs: preflight,
        raising=False,
    )

    def must_not_score(*args, **kwargs):
        raise AssertionError("scoring must not run after blocked preflight")

    monkeypatch.setattr(
        pipeline,
        "score_rolling_stock_candidates",
        must_not_score,
        raising=False,
    )

    result = pipeline.run_one_anchor(
        anchor_date=anchor,
        previous_snapshot=None,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    assert result["blocked"] is True
    assert result["snapshot"] is None
    assert result["stock_candidate_count"] == 0
    preflight_path = Path(result["paths"]["preflight"])
    backfill_path = Path(result["paths"]["backfill_requests"])
    policy_path = Path(result["paths"]["backfill_policy"])
    assert "blocked" in preflight_path.parts
    assert preflight_path.is_file()
    assert backfill_path.is_file()
    assert policy_path.is_file()
    assert json.loads(preflight_path.read_text(encoding="utf-8"))["blocked"] is True
    assert "market_daily_bar" in backfill_path.read_text(encoding="utf-8")


def test_run_one_passes_runtime_metadata_and_frozen_prices_to_snapshot_builder(
    monkeypatch, tmp_path
):
    anchor = date(2026, 7, 21)
    evaluation_cutoff = date(2026, 7, 24)
    config = RollingOversoldConfig(
        anchor_start_date=anchor,
        anchor_end_date=evaluation_cutoff,
        adjust_type="qfq",
    )
    inputs = SimpleNamespace(
        data_cutoff_date=anchor,
        industry_bars=pd.DataFrame({"family": ["industry"]}),
        concept_bars=pd.DataFrame({"family": ["concept"]}),
        industry_membership=pd.DataFrame({"family": ["industry"]}),
        concept_membership=pd.DataFrame({"family": ["concept"]}),
        stock_bars=pd.DataFrame(
            [{"asset_id": "000001", "trade_date": anchor.isoformat(), "close": 10.0}]
        ),
    )
    preflight = PreflightResult(
        blocked=False,
        data_cutoff_date=anchor,
        checked_datasets=(),
        coverage_rows=(),
        gaps=(),
    )
    sector = pd.DataFrame(
        [
            {
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
                "sector_oversold_score": 80.0,
                "sector_repairability_score": 70.0,
                "sector_direction_score": 60.0,
                "sector_recovery_state": "repairing",
                "sector_gate_status": "confirmed",
            }
        ]
    )
    features = pd.DataFrame(
        [
            {
                "asset_id": "000001",
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
            }
        ]
    )
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "000001",
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
                "sector_oversold_score": 80.0,
                "sector_repairability_score": 70.0,
                "sector_direction_score": 60.0,
                "sector_recovery_state": "repairing",
                "sector_gate_status": "confirmed",
                "stock_score": 90.0,
                "stock_rank": 1,
                "stock_lifecycle": "expected_repair",
            }
        ]
    )
    captured: dict[str, object] = {}
    db_only_sources: list[str] = []

    monkeypatch.setattr(pipeline, "assert_db_only_source", db_only_sources.append, raising=False)
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs, raising=False)
    monkeypatch.setattr(pipeline, "run_rolling_preflight", lambda *args, **kwargs: preflight, raising=False)
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
        raising=False,
    )
    monkeypatch.setattr(pipeline, "score_sector_states", lambda *args, **kwargs: sector, raising=False)
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: features, raising=False)
    monkeypatch.setattr(
        pipeline,
        "score_rolling_stock_candidates",
        lambda *args, **kwargs: candidates,
        raising=False,
    )

    def fake_build(**kwargs):
        captured.update(kwargs)
        return {
            "snapshot_id": "rolling_oversold_v1|2026-07-21",
            "anchor_date": anchor.isoformat(),
            "market_regime": kwargs["market_regime"],
            "sector_states": kwargs["sector_states"],
            "stock_candidates": kwargs["stock_candidates"],
            "runtime_metadata": kwargs["runtime_metadata"],
        }

    def fake_write(
        snapshot,
        *,
        output_dir,
        additional_artifacts=None,
        runtime_metadata_supplier=None,
    ):
        destination = Path(output_dir) / "snapshot"
        destination.mkdir(parents=True)
        manifest = destination / "manifest.json"
        runtime_metadata = (
            runtime_metadata_supplier()
            if runtime_metadata_supplier is not None
            else snapshot["runtime_metadata"]
        )
        manifest.write_text(
            json.dumps({"runtime_metadata": runtime_metadata}) + "\n",
            encoding="utf-8",
        )
        for name, contents in (additional_artifacts or {}).items():
            (destination / name).write_bytes(contents)
        return {"status": "created", "manifest_path": str(manifest)}

    monkeypatch.setattr(pipeline, "build_rolling_snapshot", fake_build, raising=False)
    monkeypatch.setattr(pipeline, "write_rolling_snapshot", fake_write, raising=False)
    evaluation_calls: dict[str, object] = {}
    monkeypatch.setattr(
        pipeline,
        "_load_evaluation_bars",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "asset_id": "000001",
                    "trade_date": "2026-07-22",
                    "close": 10.2,
                }
            ]
        ),
        raising=False,
    )
    monkeypatch.setattr(
        pipeline,
        "evaluate_snapshot",
        lambda *args, **kwargs: evaluation_calls.update(kwargs) or pd.DataFrame(),
        raising=False,
    )
    monkeypatch.setattr(
        pipeline,
        "summarize_rolling_evaluation",
        lambda detail: pd.DataFrame(),
        raising=False,
    )

    result = pipeline.run_one_anchor(
        anchor_date=anchor,
        previous_snapshot=None,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    assert db_only_sources == ["db_only"]
    assert result["blocked"] is False
    assert captured["runtime_metadata"]["runtime_budget_seconds"] == float(
        config.runtime_budget_seconds
    )
    timings = captured["runtime_metadata"]["stage_timings_seconds"]
    assert {"load", "preflight", "regime", "sector", "stock", "snapshot", "evaluation"}.issubset(
        timings
    )
    built_candidates = captured["stock_candidates"]
    assert built_candidates.loc[0, "anchor_close"] == 10.0
    assert built_candidates.loc[0, "adjusted_close_source"] == "qfq"
    assert built_candidates.loc[0, "market_regime"] == "risk_off"
    assert evaluation_calls["evaluation_cutoff"] == evaluation_cutoff
    assert evaluation_calls["bars"].loc[0, "qfq_close"] == 10.2
    persisted_metadata = json.loads(
        (Path(result["paths"]["snapshot_manifest"])).read_text(encoding="utf-8")
    )["runtime_metadata"]
    persisted_timings = persisted_metadata["stage_timings_seconds"]
    assert persisted_timings["snapshot"] > 0.0
    assert persisted_timings["evaluation"] > 0.0
    assert persisted_timings["publication"] > 0.0
    assert result["runtime_metadata"]["stage_timings_seconds"]["publication"] > 0.0
    assert Path(result["paths"]["evaluation"]).is_file()
    assert Path(result["paths"]["evaluation_summary"]).is_file()


def test_existing_snapshot_refreshes_delayed_evaluation_as_versioned_revision(
    monkeypatch, tmp_path
):
    anchor = date(2026, 7, 21)
    evaluation_cutoff = date(2026, 7, 28)
    config = RollingOversoldConfig(
        anchor_start_date=anchor,
        anchor_end_date=evaluation_cutoff,
        adjust_type="qfq",
    )
    score_version = config.score_version
    snapshot_dir = (
        tmp_path
        / "rolling_sector_oversold"
        / f"anchor={anchor.isoformat()}"
        / f"version={score_version}"
    )
    snapshot_dir.mkdir(parents=True)
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "000001",
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
                "sector_gate_status": "confirmed",
                "sector_recovery_state": "repairing",
                "stock_lifecycle": "expected_repair",
                "stock_rank": 1,
                "stock_score": 90.0,
                "anchor_close": 10.0,
                "adjusted_close_source": "qfq",
            }
        ]
    )
    snapshot = {
        "snapshot_id": f"{score_version}|{anchor.isoformat()}",
        "anchor_date": anchor.isoformat(),
        "data_cutoff_date": anchor.isoformat(),
        "score_version": score_version,
        "previous_snapshot_id": None,
        "market_regime": {"market_regime": "neutral"},
        "sector_states": pd.DataFrame(),
        "stock_candidates": candidates,
        "preflight": {},
        "backfill_requests": pd.DataFrame(),
        "manifest": {
            "runtime_metadata": {
                "runtime_budget_seconds": float(config.runtime_budget_seconds),
                "runtime_seconds": 0.01,
                "stage_timings_seconds": {},
            }
        },
    }
    immutable_manifest = {
        "snapshot_id": snapshot["snapshot_id"],
        "anchor_date": anchor.isoformat(),
        "data_cutoff_date": anchor.isoformat(),
        "score_version": score_version,
        "previous_snapshot_id": None,
        "runtime_metadata": snapshot["manifest"]["runtime_metadata"],
    }
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(immutable_manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    original_manifest = manifest_path.read_bytes()

    pending_detail = pipeline.evaluate_snapshot(
        snapshot,
        bars=pd.DataFrame(columns=["asset_id", "trade_date", "qfq_close"]),
        evaluation_cutoff=anchor,
        horizons=config.forecast_horizons,
    )
    pending_detail.to_csv(snapshot_dir / "evaluation_detail.csv", index=False)
    pipeline.summarize_rolling_evaluation(pending_detail).to_csv(
        snapshot_dir / "evaluation_summary.csv", index=False
    )

    monkeypatch.setattr(pipeline, "_load_existing_snapshot", lambda **kwargs: snapshot)
    monkeypatch.setattr(
        pipeline,
        "_load_evaluation_bars",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "asset_id": "000001",
                    "trade_date": (anchor + timedelta(days=offset)).isoformat(),
                    "close": 10.0 + offset,
                }
                for offset in range(1, 6)
            ]
        ),
    )

    result = pipeline.run_one_anchor(
        anchor_date=anchor,
        previous_snapshot=None,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    revision_dir = snapshot_dir / "evaluation_revision=0001"
    assert result["blocked"] is False
    assert result["evaluation_revision"] == 1
    assert Path(result["paths"]["evaluation"]) == revision_dir / "evaluation_detail.csv"
    assert revision_dir.is_dir()
    refreshed = pd.read_csv(revision_dir / "evaluation_detail.csv")
    assert refreshed["evaluation_status"].eq("complete").all()
    assert pd.read_csv(snapshot_dir / "evaluation_detail.csv")["evaluation_status"].eq("pending").all()
    assert manifest_path.read_bytes() == original_manifest

    evaluation_manifest = json.loads(
        (revision_dir / "evaluation_manifest.json").read_text(encoding="utf-8")
    )
    assert evaluation_manifest["snapshot_id"] == snapshot["snapshot_id"]
    assert evaluation_manifest["evaluation_cutoff"] == evaluation_cutoff.isoformat()
    assert evaluation_manifest["runtime_metadata"]["stage_timings_seconds"]["publication"] > 0.0

    report = write_rolling_sector_oversold_report(
        snapshot=snapshot,
        snapshot_dir=snapshot_dir,
        output_dir=tmp_path / "report",
    )
    report_text = report.read_text(encoding="utf-8")
    assert "1d: completed=1; pending=0" in report_text
    assert "3d: completed=1; pending=0" in report_text
    assert "5d: completed=1; pending=0" in report_text


def test_stock_scoring_gap_returns_blocked_policy_artifacts(monkeypatch, tmp_path):
    anchor = date(2026, 7, 21)
    config = RollingOversoldConfig(anchor_start_date=anchor)
    inputs = SimpleNamespace(
        data_cutoff_date=anchor,
        industry_bars=pd.DataFrame({"family": ["industry"]}),
        concept_bars=pd.DataFrame({"family": ["concept"]}),
        industry_membership=pd.DataFrame({"family": ["industry"]}),
        concept_membership=pd.DataFrame({"family": ["concept"]}),
    )
    preflight = PreflightResult(False, anchor, (), (), ())
    gap = DataGap(
        dataset="sector_context",
        asset_id="000001",
        start_date=anchor.isoformat(),
        end_date=anchor.isoformat(),
        expected_rows=1,
        actual_rows=0,
        reason="missing_sector_context:sw/I1",
    )
    sector = pd.DataFrame(
        [
            {
                "sector_system": "sw",
                "sector_code": "I1",
                "sector_name": "Industry one",
                "sector_oversold_score": 80.0,
                "sector_repairability_score": 70.0,
                "sector_direction_score": 60.0,
                "sector_recovery_state": "repairing",
                "sector_gate_status": "confirmed",
            }
        ]
    )
    monkeypatch.setattr(pipeline, "load_rolling_inputs", lambda **kwargs: inputs, raising=False)
    monkeypatch.setattr(pipeline, "run_rolling_preflight", lambda *args, **kwargs: preflight, raising=False)
    monkeypatch.setattr(pipeline, "compute_market_regime_features", lambda *args, **kwargs: {"market_regime": "neutral"}, raising=False)
    monkeypatch.setattr(pipeline, "score_sector_states", lambda *args, **kwargs: sector, raising=False)
    monkeypatch.setattr(pipeline, "_build_stock_features", lambda *args, **kwargs: pd.DataFrame({"asset_id": ["000001"], "sector_system": ["sw"], "sector_code": ["I1"]}), raising=False)
    monkeypatch.setattr(
        pipeline,
        "score_rolling_stock_candidates",
        lambda *args, **kwargs: (_ for _ in ()).throw(StockScoringDataGap(gap)),
        raising=False,
    )

    result = pipeline.run_one_anchor(
        anchor_date=anchor,
        previous_snapshot=None,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    assert result["blocked"] is True
    assert result["blocked_reason"] == "stock_scoring_data_gap"
    assert Path(result["paths"]["backfill_policy"]).is_file()


def test_daily_uses_latest_complete_session_at_or_before_explicit_trade_date(
    monkeypatch, tmp_path
):
    requested = date(2026, 7, 23)
    config = RollingOversoldConfig(anchor_start_date=requested)
    monkeypatch.setattr(
        pipeline,
        "_load_complete_anchor_sessions",
        lambda **kwargs: [date(2026, 7, 21), date(2026, 7, 22)],
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        pipeline,
        "run_one_anchor",
        lambda **kwargs: captured.update(kwargs) or {"blocked": False, "snapshot_id": "id"},
    )

    result = pipeline.run_rolling_daily(
        trade_date=requested,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    assert captured["anchor_date"] == date(2026, 7, 22)
    assert result["selected_anchor_date"] == "2026-07-22"
    assert result["requested_trade_date"] == "2026-07-23"


def test_daily_loads_existing_predecessor_for_revision_continuity(monkeypatch, tmp_path):
    requested = date(2026, 7, 23)
    selected = date(2026, 7, 22)
    config = RollingOversoldConfig(anchor_start_date=requested, anchor_end_date=requested)
    predecessor = {"snapshot_id": "rolling_oversold_v1|2026-07-21"}
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        pipeline,
        "_load_complete_anchor_sessions",
        lambda **kwargs: [date(2026, 7, 21), selected],
    )
    monkeypatch.setattr(
        pipeline,
        "_load_previous_snapshot",
        lambda **kwargs: predecessor,
        raising=False,
    )
    monkeypatch.setattr(
        pipeline,
        "run_one_anchor",
        lambda **kwargs: captured.update(kwargs) or {"blocked": False, "snapshot_id": "id"},
    )

    pipeline.run_rolling_daily(
        trade_date=requested,
        config=config,
        output_dir=tmp_path,
        service="research-test",
    )

    assert captured["previous_snapshot"] is predecessor
    assert captured["config"].anchor_end_date == requested


def test_daily_refuses_to_skip_an_unresolved_blocked_anchor(monkeypatch, tmp_path):
    requested = date(2026, 7, 23)
    prior = date(2026, 7, 21)
    blocked = date(2026, 7, 22)
    config = RollingOversoldConfig(anchor_start_date=requested, anchor_end_date=requested)
    blocked_dir = (
        tmp_path
        / "rolling_sector_oversold"
        / "blocked"
        / f"anchor={blocked.isoformat()}"
        / "version=rolling_oversold_v1"
    )
    blocked_dir.mkdir(parents=True)
    (blocked_dir / "preflight.json").write_text('{"blocked": true}\n', encoding="utf-8")
    monkeypatch.setattr(
        pipeline,
        "_load_complete_anchor_sessions",
        lambda **kwargs: [prior, blocked, requested],
    )
    monkeypatch.setattr(
        pipeline,
        "_load_previous_snapshot",
        lambda **kwargs: {"snapshot_id": f"rolling_oversold_v1|{prior.isoformat()}", "anchor_date": prior.isoformat()},
    )
    monkeypatch.setattr(
        pipeline,
        "run_one_anchor",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not skip the block")),
    )

    with pytest.raises(ValueError, match="unresolved blocked anchor"):
        pipeline.run_rolling_daily(
            trade_date=requested,
            config=config,
            output_dir=tmp_path,
            service="research-test",
        )


def test_daily_refuses_first_blocked_anchor_without_prior_manifest(monkeypatch, tmp_path):
    first = date(2026, 7, 21)
    requested = date(2026, 7, 22)
    config = RollingOversoldConfig(anchor_start_date=first, anchor_end_date=requested)
    blocked_dir = (
        tmp_path
        / "rolling_sector_oversold"
        / "blocked"
        / f"anchor={first.isoformat()}"
        / "version=rolling_oversold_v1"
    )
    blocked_dir.mkdir(parents=True)
    (blocked_dir / "preflight.json").write_text('{"blocked": true}\n', encoding="utf-8")
    monkeypatch.setattr(
        pipeline,
        "_load_complete_anchor_sessions",
        lambda **kwargs: [first, requested],
    )
    monkeypatch.setattr(pipeline, "_load_previous_snapshot", lambda **kwargs: None)
    monkeypatch.setattr(
        pipeline,
        "run_one_anchor",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must remain blocked")),
    )

    with pytest.raises(ValueError, match="unresolved blocked anchor"):
        pipeline.run_rolling_daily(
            trade_date=requested,
            config=config,
            output_dir=tmp_path,
            service="research-test",
        )


def test_replay_default_end_is_capped_at_today(monkeypatch):
    captured: dict[str, object] = {}

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(pipeline, "connect", lambda service: FakeConnection())
    monkeypatch.setattr(
        pipeline,
        "fetch_all",
        lambda connection, sql, params: captured.update(params=params) or [],
    )

    pipeline._load_complete_anchor_sessions(
        config=RollingOversoldConfig(anchor_start_date=date(2026, 7, 21)),
        service="research-test",
    )

    assert captured["params"][2] == date.today().isoformat()
    assert captured["params"][3] == date.today().isoformat()


def test_pipeline_has_no_external_market_imports():
    tree = ast.parse(inspect.getsource(pipeline))
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert not {"akshare", "baostock"} & imported_roots


def test_missing_status_flags_do_not_make_stock_feature_filter_raise():
    assert pipeline._is_ineligible_status(
        {"is_st": pd.NA, "is_suspended": pd.NA, "is_trade": pd.NA}
    ) is False


def test_report_includes_all_sector_statuses_and_focus_patterns(tmp_path):
    snapshot = {
        "snapshot_id": "rolling_oversold_v1|2026-07-21",
        "anchor_date": "2026-07-21",
        "data_cutoff_date": "2026-07-21",
        "market_regime": {"market_regime": "risk_off"},
        "sector_states": pd.DataFrame(
            [
                {
                    "sector_system": "sw",
                    "sector_code": "I1",
                    "sector_name": "Alpha Industry",
                    "sector_gate_status": "confirmed",
                    "sector_recovery_state": "repairing",
                    "sector_rank": 1,
                    "sector_recovery_state_delta": "fresh_oversold->repairing",
                },
                {
                    "sector_system": "theme",
                    "sector_code": "C1",
                    "sector_name": "Blocked Theme",
                    "sector_gate_status": "blocked",
                    "sector_recovery_state": "unknown",
                    "sector_rank": 2,
                    "sector_recovery_state_delta": "unknown->unknown",
                },
            ]
        ),
        "stock_candidates": pd.DataFrame(
            [
                {
                    "asset_id": "000001",
                    "sector_system": "sw",
                    "sector_code": "I1",
                    "sector_name": "Alpha Industry",
                    "stock_rank": 1,
                    "stock_score": 88.0,
                    "stock_lifecycle": "expected_repair",
                    "lifecycle_delta": "new_oversold->expected_repair",
                }
            ]
        ),
        "preflight": {
            "gaps": [
                {
                    "dataset": "market_daily_bar",
                    "asset_id": "000002",
                    "reason": "missing_cutoff_bar",
                }
            ]
        },
    }
    evaluation = pd.DataFrame(
        [
            {"forward_horizon_days": 1, "evaluation_status": "complete"},
            {"forward_horizon_days": 3, "evaluation_status": "pending"},
            {"forward_horizon_days": 5, "evaluation_status": "complete"},
        ]
    )

    path = write_rolling_sector_oversold_report(
        snapshot=snapshot,
        output_dir=tmp_path,
        evaluation_detail=evaluation,
        focus_patterns=("alpha",),
    )

    text = path.read_text(encoding="utf-8").casefold()
    assert "risk_off" in text
    assert "alpha industry" in text
    assert "blocked theme" in text
    assert "confirmed" in text
    assert "blocked" in text
    assert "focus patterns" in text
    assert "alpha" in text
    assert "missing_cutoff_bar" in text
    assert "fresh_oversold->repairing" in text


def test_report_loads_blocked_artifacts_without_snapshot_manifest(tmp_path):
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    (blocked_dir / "preflight.json").write_text(
        json.dumps(
            {
                "blocked": True,
                "status": "blocked_missing_data",
                "data_cutoff_date": "2026-07-21",
                "gaps": [
                    {
                        "dataset": "market_daily_bar",
                        "asset_id": "000001",
                        "reason": "missing_cutoff_bar",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "dataset": "market_daily_bar",
                "asset_id": "000001",
                "reason": "missing_cutoff_bar",
            }
        ]
    ).to_csv(blocked_dir / "backfill_requests.csv", index=False)

    snapshot = load_rolling_oversold_snapshot(blocked_dir)
    report = write_rolling_sector_oversold_report(
        snapshot=snapshot,
        snapshot_dir=blocked_dir,
        output_dir=tmp_path / "report",
    )

    assert snapshot["preflight"]["blocked"] is True
    assert "missing_cutoff_bar" in report.read_text(encoding="utf-8")


def test_snapshot_loader_preserves_existing_predecessor_for_replay_lineage(tmp_path):
    snapshot_dir = tmp_path / "rolling_sector_oversold" / "anchor=2026-07-22" / "version=rolling_oversold_v1"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(
            {
                "snapshot_id": "rolling_oversold_v1|2026-07-22",
                "anchor_date": "2026-07-22",
                "data_cutoff_date": "2026-07-22",
                "score_version": "rolling_oversold_v1",
                "previous_snapshot_id": "rolling_oversold_v1|2026-07-21",
            }
        ),
        encoding="utf-8",
    )

    loaded = load_rolling_oversold_snapshot(snapshot_dir)
    pipeline._assert_existing_snapshot_lineage(
        loaded,
        {"snapshot_id": "rolling_oversold_v1|2026-07-21"},
    )

    assert loaded["previous_snapshot_id"] == "rolling_oversold_v1|2026-07-21"
