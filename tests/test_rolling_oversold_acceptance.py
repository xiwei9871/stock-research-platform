from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from stock_research.rolling_oversold import pipeline
from stock_research.rolling_oversold.contracts import RollingOversoldConfig
from stock_research.rolling_oversold.outcomes import evaluate_sector_snapshot
from stock_research.rolling_oversold.preflight import PreflightResult


ANCHORS = [date(2026, 7, 21), date(2026, 7, 22), date(2026, 7, 23)]
WALK_FORWARD_ANCHORS = [date(2026, 7, day) for day in range(27, 32)]
WALK_FORWARD_CUTOFF = date(2026, 8, 3)
WALK_FORWARD_SECTOR_CODES = [
    "300238",
    *[f"{300300 + index:06d}" for index in range(301)],
]
WALK_FORWARD_GAP_CODE = "300600"


def _walk_forward_inputs(anchor_date: date) -> SimpleNamespace:
    """Return a point-in-time 302-sector fixture with one explicit gap."""

    history_dates = [anchor_date - timedelta(days=offset) for offset in range(19, -1, -1)]
    names = {"300238": "核电"}
    names.update({code: f"Concept {code}" for code in WALK_FORWARD_SECTOR_CODES if code != "300238"})
    bars: list[dict[str, object]] = []
    for sector_index, code in enumerate(WALK_FORWARD_SECTOR_CODES):
        # Membership remains in the frozen universe, while this sector's bars
        # are intentionally absent.  The batch must publish a blocked_data row
        # and a structured gap instead of silently reducing coverage.
        if code == WALK_FORWARD_GAP_CODE:
            continue
        for offset, trade_date in enumerate(history_dates):
            close = 100.0 - (12.0 if offset == 11 else 0.0) + max(0, offset - 11) * 1.2
            bars.append(
                {
                    "concept_system": "ths",
                    "concept_code": code,
                    "concept_name": names[code],
                    "trade_date": trade_date,
                    "close": close,
                    "preclose": close - 0.5,
                    "volume": 100.0 + offset * 5.0,
                    "amount": 1000.0 + offset * 50.0,
                }
            )
    membership = pd.DataFrame(
        {
            "asset_id": [f"WF{index:03d}" for index in range(len(WALK_FORWARD_SECTOR_CODES))],
            "concept_system": ["ths"] * len(WALK_FORWARD_SECTOR_CODES),
            "concept_code": WALK_FORWARD_SECTOR_CODES,
            "concept_name": [names[code] for code in WALK_FORWARD_SECTOR_CODES],
            "start_date": [date(2020, 1, 1)] * len(WALK_FORWARD_SECTOR_CODES),
            "end_date": [pd.NaT] * len(WALK_FORWARD_SECTOR_CODES),
        }
    )
    empty = pd.DataFrame()
    return SimpleNamespace(
        anchor_date=anchor_date,
        data_cutoff_date=anchor_date,
        trading_dates=pd.DataFrame({"trade_date": history_dates}),
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
        score_version="rolling_oversold_sector_v2",
    )


def _walk_forward_stock_features(anchor_date: date) -> pd.DataFrame:
    """Deterministic sector-local stock score inputs for the acceptance run."""

    rows: list[dict[str, object]] = []
    for index, code in enumerate(WALK_FORWARD_SECTOR_CODES):
        if code == WALK_FORWARD_GAP_CODE:
            continue
        rows.append(
            {
                "asset_id": f"WF{index:03d}",
                "sector_system": "ths",
                "sector_code": code,
                "sector_name": "核电" if code == "300238" else f"Concept {code}",
                "anchor_return": 0.02,
                "distance_to_252d_high": 0.25,
                "oversold_depth": 0.25,
                "stock_excess_return": 0.01,
                "activity": 100.0,
                "quality": 70.0,
                "valuation": 60.0,
                "size_elasticity": 10.0,
                "anchor_close": 10.0 + index / 1000.0,
                "adjusted_close_source": "qfq",
            }
        )
    return pd.DataFrame(rows)


def _walk_forward_bars() -> pd.DataFrame:
    sessions = [
        date(2026, 7, 28),
        date(2026, 7, 29),
        date(2026, 7, 30),
        date(2026, 7, 31),
        date(2026, 8, 3),
    ]
    rows: list[dict[str, object]] = []
    for index, code in enumerate(WALK_FORWARD_SECTOR_CODES):
        if code == WALK_FORWARD_GAP_CODE:
            continue
        asset_id = f"WF{index:03d}"
        for offset, trade_date in enumerate(sessions, start=1):
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": trade_date.isoformat(),
                    "qfq_close": 10.0 + index / 1000.0 + offset * 0.02,
                }
            )
    return pd.DataFrame(rows)


def _walk_forward_config() -> RollingOversoldConfig:
    return RollingOversoldConfig(
        anchor_start_date=WALK_FORWARD_ANCHORS[0],
        anchor_end_date=WALK_FORWARD_ANCHORS[-1],
        concept_systems=("ths",),
        concept_codes=tuple(WALK_FORWARD_SECTOR_CODES),
        score_version="rolling_oversold_sector_v2",
        sector_top_n=302,
        sector_output_top_n=10,
        stock_top_n=10,
        runtime_budget_seconds=3600,
    )


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


def test_sector_v2_acceptance_freezes_five_anchors_and_validates_future_states(
    monkeypatch, tmp_path
):
    """Exercise the complete 7/27--7/31 acceptance contract without a live DB."""

    config = _walk_forward_config()
    forward_bars = _walk_forward_bars()
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(
        pipeline,
        "_build_stock_features",
        lambda inputs, *, anchor_date, config, sector_selection=None: _walk_forward_stock_features(
            anchor_date
        ),
    )

    results: list[dict[str, object]] = []
    previous_snapshot: dict[str, object] | None = None
    for anchor in WALK_FORWARD_ANCHORS:
        inputs = _walk_forward_inputs(anchor)
        for frame_name in ("concept_bars", "stock_bars", "industry_bars"):
            frame = getattr(inputs, frame_name)
            if isinstance(frame, pd.DataFrame) and not frame.empty and "trade_date" in frame:
                assert pd.to_datetime(frame["trade_date"]).dt.date.le(anchor).all(), frame_name

        result = pipeline.run_sector_batch(
            anchor_date=anchor,
            config=config,
            inputs=inputs,
            previous_snapshot=previous_snapshot,
            output_dir=tmp_path,
            service="research-test",
        )
        assert result["blocked"] is False
        assert result["data_cutoff_date"] == anchor.isoformat()
        assert result["sector_count"] == 302
        board = result["sector_states"]
        assert isinstance(board, pd.DataFrame)
        assert len(board) == 302
        assert set(board["sector_system"]) == {"ths"}
        assert set(board["sector_code"]) == set(WALK_FORWARD_SECTOR_CODES)
        assert not board.duplicated(["sector_system", "sector_code"]).any()
        membership_counts = (
            inputs.concept_membership.groupby(
                ["concept_system", "concept_code"], dropna=False
            )
            .size()
        )
        assert all(
            membership_counts.get(("ths", code), 0) > 0
            for code in WALK_FORWARD_SECTOR_CODES
        )

        missing_sector = board.loc[board["sector_code"].eq(WALK_FORWARD_GAP_CODE)].iloc[0]
        assert missing_sector["sector_research_eligibility"] == "blocked_data"
        gaps = result["snapshot"]["preflight"]["gaps"]
        assert any(
            gap["dataset"] == "sector_features"
            and gap["asset_id"] == f"ths:{WALK_FORWARD_GAP_CODE}"
            for gap in gaps
        )

        if anchor == date(2026, 7, 31):
            nuclear = board.loc[
                board["sector_system"].eq("ths") & board["sector_code"].eq("300238")
            ]
            assert len(nuclear) == 1
            assert nuclear.iloc[0]["sector_name"] == "核电"

        detail = evaluate_sector_snapshot(
            result["snapshot"],
            bars=forward_bars,
            evaluation_cutoff=WALK_FORWARD_CUTOFF,
            horizons=(1, 3, 5),
        )
        assert not detail.empty
        assert {
            "sector_system",
            "sector_code",
            "sector_name",
            "sector_recovery_state",
            "sector_stock_rank",
            "sector_rank",
            "target_trade_date",
            "endpoint_close",
            "status",
        }.issubset(detail.columns)
        target_dates = pd.to_datetime(detail["target_trade_date"], errors="coerce")
        assert target_dates.dropna().gt(pd.Timestamp(anchor)).all()
        assert set(detail["status"].dropna()) <= {"complete", "pending"}
        assert set(detail["forward_Nd_status"].dropna()) <= {"complete", "pending"}
        results.append({"result": result, "detail": detail})
        previous_snapshot = result["snapshot"]

    assert len(results) == len(WALK_FORWARD_ANCHORS)
    all_statuses = pd.concat([entry["detail"]["status"] for entry in results], ignore_index=True)
    assert {"complete", "pending"}.issubset(set(all_statuses))
    assert [entry["result"]["anchor_date"] for entry in results] == [
        anchor.isoformat() for anchor in WALK_FORWARD_ANCHORS
    ]


def test_sector_v2_acceptance_keeps_historical_snapshots_immutable(
    monkeypatch, tmp_path
):
    config = _walk_forward_config()
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: {"market_regime": "risk_off"},
    )
    monkeypatch.setattr(
        pipeline,
        "_build_stock_features",
        lambda inputs, *, anchor_date, config, sector_selection=None: _walk_forward_stock_features(
            anchor_date
        ),
    )

    initial: list[dict[str, object]] = []
    previous_snapshot: dict[str, object] | None = None
    for anchor in WALK_FORWARD_ANCHORS:
        result = pipeline.run_sector_batch(
            anchor_date=anchor,
            config=config,
            inputs=_walk_forward_inputs(anchor),
            previous_snapshot=previous_snapshot,
            output_dir=tmp_path,
            service="research-test",
        )
        initial.append(result)
        previous_snapshot = result["snapshot"]

    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    # Fast-path loading must return the exact published manifests and must not
    # re-run scoring when historical inputs are replayed a second time.
    monkeypatch.setattr(
        pipeline,
        "compute_market_regime_features",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("recomputed regime")),
    )
    monkeypatch.setattr(
        pipeline,
        "_build_stock_features",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("recomputed stock features")),
    )
    previous_snapshot = None
    for anchor, original in zip(WALK_FORWARD_ANCHORS, initial, strict=True):
        rerun = pipeline.run_sector_batch(
            anchor_date=anchor,
            config=config,
            inputs=_walk_forward_inputs(anchor),
            previous_snapshot=previous_snapshot,
            output_dir=tmp_path,
            service="research-test",
        )
        assert rerun["batch_manifest"] == original["batch_manifest"]
        previous_snapshot = original["snapshot"]

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert before == after
