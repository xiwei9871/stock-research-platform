from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_replay_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_pit_evidence_replay.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_pit_evidence_replay", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_empty_pit_evidence_uses_neutral_multiplier_and_degraded_status(tmp_path):
    module = _load_replay_module()
    base_snapshots = pd.DataFrame(
        [
            {"trade_date": "2025-01-03", "asset_id": "000001.SZ"},
            {"trade_date": "2025-01-03", "asset_id": "000002.SZ"},
        ]
    )

    result = module._build_pit_multiplier(
        base_snapshots=base_snapshots,
        evidence_seed=pd.DataFrame(),
        output_path=tmp_path / "pit.csv",
    )

    assert result["source_backed_field_count"].tolist() == [0, 0]
    assert result["evidence_confidence_multiplier"].tolist() == [1.0, 1.0]
    assert result["evidence_state"].tolist() == ["unverified", "unverified"]
    assert result["evidence_audit_status"].tolist() == ["degraded_no_pit_evidence", "degraded_no_pit_evidence"]
    assert result["latest_evidence_date"].tolist() == ["", ""]


def _load_impact_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_pit_evidence_impact_attribution.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_pit_evidence_impact_attribution", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_decision_ledger_identifies_entered_and_dropped_top5_due_to_evidence():
    module = _load_impact_module()
    before = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "A", "stock_name": "old", "bottleneck_rank": 5, "bottleneck_score": 0.50, "is_top5": True},
            {"trade_date": "2026-01-02", "asset_id": "B", "stock_name": "new", "bottleneck_rank": 6, "bottleneck_score": 0.49, "is_top5": False},
        ]
    )
    after = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "stock_name": "new",
                "bottleneck_rank": 5,
                "raw_bottleneck_score": 0.49,
                "bottleneck_score": 0.56,
                "is_top5": True,
                "evidence_confidence_multiplier": 1.15,
                "evidence_state": "E3_strong",
                "evidence_audit_status": "active_pit_evidence",
                "source_backed_field_count": 3,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "stock_name": "old",
                "bottleneck_rank": 6,
                "raw_bottleneck_score": 0.50,
                "bottleneck_score": 0.50,
                "is_top5": False,
                "evidence_confidence_multiplier": 1.0,
                "evidence_state": "unverified",
                "evidence_audit_status": "active_pit_evidence",
                "source_backed_field_count": 0,
            },
        ]
    )

    ledger = module.build_decision_ledger(before, after)

    entered = ledger[ledger["entered_top5_due_to_evidence"]]
    dropped = ledger[ledger["dropped_from_top5_due_to_evidence"]]
    assert entered["asset_id"].tolist() == ["B"]
    assert dropped["asset_id"].tolist() == ["A"]
    assert entered.iloc[0]["reason_code"] == "evidence_boost_entered_top5"
    assert dropped.iloc[0]["reason_code"] == "displaced_by_evidence_boost"


def test_evidence_events_only_become_active_on_or_after_source_date():
    module = _load_impact_module()
    events = pd.DataFrame(
        [
            {"asset_id": "A", "field": "revenue_exposure_bucket", "source_date": "2026-01-10", "source_type": "broker_report"}
        ]
    )
    active_before = module.active_evidence_event_ids(events, asset_id="A", trade_date="2026-01-09")
    active_on_date = module.active_evidence_event_ids(events, asset_id="A", trade_date="2026-01-10")

    assert active_before == []
    assert active_on_date == ["EV001"]


def _sample_ablation_candidates():
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "asset_id": "A",
                "stock_name": "top",
                "bottleneck_score": 1.000,
                "bottleneck_rank": 1,
                "is_top5": True,
                "evidence_state": "unverified",
                "source_backed_field_count": 0,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "B",
                "stock_name": "near",
                "bottleneck_score": 0.995,
                "bottleneck_rank": 2,
                "is_top5": True,
                "evidence_state": "E3_strong",
                "source_backed_field_count": 3,
            },
            {
                "trade_date": "2026-01-02",
                "asset_id": "C",
                "stock_name": "far",
                "bottleneck_score": 0.900,
                "bottleneck_rank": 3,
                "is_top5": True,
                "evidence_state": "E3_strong",
                "source_backed_field_count": 3,
            },
        ]
    )


def _load_ablation_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_evidence_usage_ablation.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_evidence_usage_ablation", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_tag_only_does_not_change_ranking():
    module = _load_ablation_module()
    result = module.apply_evidence_usage_variant(_sample_ablation_candidates(), "tag_only")

    assert result["asset_id"].tolist() == ["A", "B", "C"]
    assert result["bottleneck_rank"].tolist() == [1, 2, 3]
    assert result["evidence_usage_variant"].eq("tag_only").all()


def test_tie_breaker_only_changes_when_score_gap_is_within_threshold():
    module = _load_ablation_module()
    result = module.apply_evidence_usage_variant(_sample_ablation_candidates(), "tie_breaker_1pct")

    assert result["asset_id"].tolist()[:3] == ["B", "A", "C"]
    assert result.loc[result["asset_id"].eq("C"), "bottleneck_rank"].iloc[0] == 3


def test_rank_jump_cap_limits_rank_improvement():
    module = _load_ablation_module()
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": str(i), "stock_name": str(i), "bottleneck_score": 1.0 - i * 0.01, "bottleneck_rank": i + 1, "is_top5": i < 5, "evidence_state": "unverified", "source_backed_field_count": 0}
            for i in range(8)
        ]
    )
    candidates.loc[candidates["asset_id"].eq("7"), ["evidence_state", "source_backed_field_count"]] = ["E3_strong", 3]

    cap1 = module.apply_evidence_usage_variant(candidates, "rank_jump_cap_1")
    cap2 = module.apply_evidence_usage_variant(candidates, "rank_jump_cap_2")

    assert int(cap1.loc[cap1["asset_id"].eq("7"), "bottleneck_rank"].iloc[0]) == 7
    assert int(cap2.loc[cap2["asset_id"].eq("7"), "bottleneck_rank"].iloc[0]) == 6


def test_weak_multiplier_missing_evidence_is_neutral():
    module = _load_ablation_module()
    result = module.apply_evidence_usage_variant(_sample_ablation_candidates(), "weak_multiplier_1p01_1p03")

    assert result.loc[result["asset_id"].eq("A"), "evidence_confidence_multiplier"].iloc[0] == 1.0
    assert result.loc[result["asset_id"].eq("B"), "evidence_confidence_multiplier"].iloc[0] == 1.03
