from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from psycopg import OperationalError

from stock_research.strategy_publication_contracts import (
    build_publication_identity,
    get_publication_contract,
    get_strategy_acceptance_callback,
    iter_publication_contracts,
)


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_official_strategy_publications.py"
SPEC = importlib.util.spec_from_file_location("validate_official_strategy_publications", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def _template(*, strategy_id: str = "mid_trend") -> dict:
    contract = get_publication_contract(strategy_id)
    return {
        "strategy_id": strategy_id,
        "profile": "balanced",
        "baseline_start_date": "2026-01-01",
        "baseline_end_date": "2026-06-17",
        "summary": {
            "total_return": 0.1,
            "max_drawdown": -0.05,
            "filled_trade_count": 1,
            "cash_slot_count": 0,
        },
        "tolerances": {"total_return": 1e-10, "max_drawdown": 1e-10},
        "acceptance_profile": contract.acceptance_profile,
        "publication_identity": build_publication_identity(contract),
        "artifact_evidence": [
            {"name": "pending.json", "sha256": "0" * 64, "record_count": 1}
        ],
    }


def _raw_result(tmp_path: Path, *, strategy_id: str = "mid_trend") -> dict:
    template = _template(strategy_id=strategy_id)
    identity = deepcopy(template["publication_identity"])
    result = {
        "strategy_id": strategy_id,
        "config": {
            "strategy_id": strategy_id,
            "start_date": template["baseline_start_date"],
            "end_date": template["baseline_end_date"],
            "top_n": 5,
        },
        "publication_identity": identity,
        "summary": {
            **template["summary"],
            "start_date": template["baseline_start_date"],
            "end_date": template["baseline_end_date"],
            "actual_start_date": "2026-01-02",
            "actual_end_date": "2026-06-17",
            "publication_identity": deepcopy(identity),
        },
        "equity_curve": [
            {
                "trade_date": "2026-01-02",
                "equity": 1.0,
                "cash": 1.0,
                "open_position_count": 0,
                "holdings_count": 1,
            },
            {
                "trade_date": "2026-01-03",
                "equity": 0.95,
                "cash": 0.2,
                "open_position_count": 1,
                "holdings_count": 1,
            },
            {
                "trade_date": "2026-06-17",
                "equity": 1.1,
                "cash": 0.2,
                "open_position_count": 1,
                "holdings_count": 1,
            },
        ],
        "positions": [
            {
                "rebalance_date": "2026-01-02",
                "trade_date": "2026-01-02",
                "asset_id": "CN:SH:600000",
                "weight": 1.0,
            }
        ],
        "trades": [
            {
                "trade_date": "2026-01-02",
                "asset_id": "CN:SH:600000",
                "previous_weight": 0.0,
                "target_weight": 1.0,
                "fill_status": "filled",
            }
        ],
    }
    if strategy_id == "lhb_shortline":
        row = {
            "account_trade_status": "filled",
            "trade_date": "2026-01-02",
            "asset_id": "CN:SH:600000",
            "top_n": 5,
            "phase18c_selection_rank": 1,
            "backtest_entry_eligible": True,
            "eligibility_status": "eligible",
            "top5_eligible": True,
        }
        result["config"].update({"risk_profile": "balanced", "rebalance_frequency": "daily"})
        result["summary"].update(
            {
                "selection_policy": "phase18c_top5_then_eligibility_no_refill",
                "phase18c_top_n": 5,
                "cash_slot_count": 1,
            }
        )
        result["positions"] = [deepcopy(row)]
        result["trades"] = [deepcopy(row)]
        result["candidates"] = [deepcopy(row)]
        rejected_path = tmp_path / "lhb_phase18c_selected_rejected_trades_v1.csv"
        rejected_path.write_text(
            "trade_date,strategy,top_n,phase18c_selection_rank,backtest_entry_eligible,"
            "top5_eligible,buy_signal_status,eligibility_status,research_only\n"
            "2026-01-03,auction_enhanced_rerank,5,2,false,false,research_only,risk_watch,true\n",
            encoding="utf-8",
        )
        result["artifacts"] = {"pipeline_selected_rejected_trades": str(rejected_path)}
    elif strategy_id == "mid_trend":
        variant = identity["variant"]
        result["config"].update(
            {
                "rebalance_frequency": "weekly",
                "max_weekly_replacements": 2,
                "benchmark_variant": variant,
            }
        )
        result["summary"].update(
            {"benchmark_variant": variant, "position_rows": 1, "trade_rows": 1}
        )
    elif strategy_id == "tech_bottleneck":
        policy = identity["publication_policy"]
        result["config"].update(
            {
                "rebalance_frequency": policy["frequency"],
                "universe": policy["universe"],
                "protection_name": policy["protection_name"],
            }
        )
        result["summary"].update(
            {
                **policy,
                "position_rows": 1,
                "trade_rows": 1,
                "data_coverage": {"candidate_snapshot_latest_date": "2026-06-16"},
            }
        )
        result["positions"][0].pop("rebalance_date", None)
        result["positions"][0]["trade_date"] = "2026-01-01"
        result["trades"][0]["trade_date"] = "2026-01-01"
    return result


def _approved_pair(tmp_path: Path, *, strategy_id: str = "mid_trend") -> tuple[dict, dict]:
    template = _template(strategy_id=strategy_id)
    result = _raw_result(tmp_path, strategy_id=strategy_id)
    prepared = validator.materialize_result_artifacts(
        result,
        template=template,
        output_dir=tmp_path / f"artifacts-{strategy_id}",
    )
    baseline = validator.build_candidate(prepared, template=template)
    return baseline, prepared


def _rewrite_artifact_and_approve(
    result: dict,
    baseline: dict,
    *,
    name: str,
    rows: list,
) -> None:
    path = Path(result["artifact_files"][name])
    path.write_text(
        json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    evidence = next(row for row in baseline["artifact_evidence"] if row["name"] == name)
    evidence["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence["record_count"] = len(rows)


def test_validator_accepts_exact_identity_common_invariants_and_artifact_hashes(tmp_path):
    baseline, result = _approved_pair(tmp_path)
    report = validator.validate_result(result, baseline=baseline)

    assert report["status"] == "success"
    assert report["strategy_id"] == "mid_trend"
    assert report["observed"]["artifact_evidence"] == baseline["artifact_evidence"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("total_return", 0.2),
        ("max_drawdown", -0.2),
        ("filled_trade_count", 2),
        ("cash_slot_count", 2),
    ],
)
def test_validator_rejects_summary_drift(field, value, tmp_path):
    baseline, result = _approved_pair(tmp_path)
    result["summary"][field] = value

    with pytest.raises(ValueError, match=f"acceptance mismatch.*{field}"):
        validator.validate_result(result, baseline=baseline)


def test_validator_rejects_identity_date_and_acceptance_profile_drift(tmp_path):
    baseline, result = _approved_pair(tmp_path)
    result["summary"]["publication_identity"]["config_fingerprint"] = "0" * 64
    result["summary"]["end_date"] = "2026-06-18"
    baseline["acceptance_profile"] = "wrong-profile"

    with pytest.raises(ValueError) as exc_info:
        validator.validate_result(result, baseline=baseline)

    message = str(exc_info.value)
    assert "config_fingerprint" in message
    assert "baseline_end_date" in message
    assert "acceptance_profile" in message


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "not-a-number"])
def test_validator_rejects_non_finite_metrics(value, tmp_path):
    baseline, result = _approved_pair(tmp_path)
    result["summary"]["total_return"] = value

    with pytest.raises(ValueError, match="finite.*total_return"):
        validator.validate_result(result, baseline=baseline)


def test_validator_rejects_unsafe_account_rows(tmp_path):
    baseline, result = _approved_pair(tmp_path)
    rows = deepcopy(result["equity_curve"])
    rows[-1]["cash"] = -0.01
    rows[-1]["open_position_count"] = 6
    _rewrite_artifact_and_approve(result, baseline, name="equity_curve.json", rows=rows)

    with pytest.raises(ValueError) as exc_info:
        validator.validate_result(result, baseline=baseline)

    assert "negative cash" in str(exc_info.value)
    assert "max positions" in str(exc_info.value)


def test_validator_rejects_impossible_account_loss_even_when_baseline_matches(tmp_path):
    baseline, result = _approved_pair(tmp_path)
    baseline["summary"]["total_return"] = -1.01
    baseline["summary"]["max_drawdown"] = -1.01
    result["summary"]["total_return"] = -1.01
    result["summary"]["max_drawdown"] = -1.01

    with pytest.raises(ValueError) as exc_info:
        validator.validate_result(result, baseline=baseline)

    assert "account safety: total_return" in str(exc_info.value)
    assert "account safety: max_drawdown" in str(exc_info.value)


@pytest.mark.parametrize(("field", "value"), [("total_return", 0.2), ("max_drawdown", -0.2)])
def test_validator_reconciles_summary_metrics_to_authoritative_equity_curve(field, value, tmp_path):
    baseline, result = _approved_pair(tmp_path)
    baseline["summary"][field] = value
    result["summary"][field] = value

    with pytest.raises(ValueError, match=f"equity curve.*{field}"):
        validator.validate_result(result, baseline=baseline)


def test_validator_requires_integral_non_negative_position_counts_on_every_curve_row(tmp_path):
    baseline, result = _approved_pair(tmp_path)
    rows = deepcopy(result["equity_curve"])
    rows[1]["holdings_count"] = 1.5
    rows[1]["open_position_count"] = -1
    _rewrite_artifact_and_approve(result, baseline, name="equity_curve.json", rows=rows)

    with pytest.raises(ValueError) as exc_info:
        validator.validate_result(result, baseline=baseline)

    assert "holdings_count" in str(exc_info.value)
    assert "open_position_count" in str(exc_info.value)


def test_validator_requires_parseable_actual_dates_and_curve_boundaries(tmp_path):
    baseline, result = _approved_pair(tmp_path)
    result["summary"]["actual_start_date"] = "not-a-date"
    with pytest.raises(ValueError, match="actual_start_date.*parseable"):
        validator.validate_result(result, baseline=baseline)

    result["summary"]["actual_start_date"] = baseline["actual_start_date"]
    rows = deepcopy(result["equity_curve"])
    rows[0]["trade_date"] = "2025-12-31"
    _rewrite_artifact_and_approve(result, baseline, name="equity_curve.json", rows=rows)
    with pytest.raises(ValueError, match="curve.*baseline_start_date"):
        validator.validate_result(result, baseline=baseline)


def test_candidate_rejects_conflicting_equity_date_aliases(tmp_path):
    result = _raw_result(tmp_path)
    result["equity_curve"][0]["date"] = "2026-01-03"

    with pytest.raises(ValueError, match="equity curve row 0 date aliases disagree"):
        validator.materialize_result_artifacts(
            result,
            template=_template(),
            output_dir=tmp_path / "conflicting-equity-date",
        )


def test_validator_rejects_conflicting_position_date_aliases(tmp_path):
    baseline, result = _approved_pair(tmp_path)
    positions = deepcopy(result["positions"])
    positions[0]["trade_date"] = "2026-01-03"
    _rewrite_artifact_and_approve(result, baseline, name="positions.json", rows=positions)

    with pytest.raises(ValueError, match="positions row 0 date aliases disagree"):
        validator.validate_result(result, baseline=baseline)


def test_materializer_derives_missing_actual_dates_from_authoritative_curve(tmp_path):
    result = _raw_result(tmp_path, strategy_id="tech_bottleneck")
    result["summary"].pop("actual_start_date")
    result["summary"].pop("actual_end_date")

    prepared = validator.materialize_result_artifacts(
        result,
        template=_template(strategy_id="tech_bottleneck"),
        output_dir=tmp_path / "derive-dates",
    )

    assert prepared["summary"]["actual_start_date"] == "2026-01-02"
    assert prepared["summary"]["actual_end_date"] == "2026-06-17"


def test_materializer_rejects_malformed_or_mixed_strategy_rows(tmp_path):
    result = _raw_result(tmp_path)
    result["positions"].append("not-a-row")

    with pytest.raises(ValueError, match="positions.*malformed row"):
        validator.materialize_result_artifacts(
            result,
            template=_template(),
            output_dir=tmp_path / "mixed-rows",
        )


def test_validator_fails_closed_for_missing_mixed_or_malformed_artifact_evidence(tmp_path):
    baseline, prepared = _approved_pair(tmp_path)
    missing = deepcopy(prepared)
    missing.pop("artifact_files")
    missing["artifact_evidence"] = deepcopy(baseline["artifact_evidence"])
    with pytest.raises(ValueError, match="artifact files.*missing"):
        validator.validate_result(missing, baseline=baseline)

    mixed = deepcopy(prepared)
    Path(mixed["artifact_files"]["equity_curve.json"]).write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact.*(unreadable|malformed|sha256)"):
        validator.validate_result(mixed, baseline=baseline)

    empty_fallback = _raw_result(tmp_path)
    empty_fallback["positions"] = []
    with pytest.raises(ValueError, match="positions.*empty"):
        validator.materialize_result_artifacts(
            empty_fallback,
            template=_template(),
            output_dir=tmp_path / "empty",
        )

    malformed = deepcopy(baseline)
    malformed["artifact_evidence"][0]["sha256"] = "bad"
    with pytest.raises(ValueError, match="malformed.*sha256"):
        validator.validate_result(prepared, baseline=malformed)


def test_artifact_evidence_order_is_semantically_irrelevant(tmp_path):
    baseline, result = _approved_pair(tmp_path)
    baseline["artifact_evidence"] = list(reversed(baseline["artifact_evidence"]))

    assert validator.validate_result(result, baseline=baseline)["status"] == "success"


def test_artifact_audit_rejects_file_outside_declared_trusted_root(tmp_path):
    baseline, result = _approved_pair(tmp_path)
    outside = tmp_path / "outside-equity.json"
    outside.write_bytes(Path(result["artifact_files"]["equity_curve.json"]).read_bytes())
    result["artifact_files"]["equity_curve.json"] = str(outside)

    with pytest.raises(ValueError, match="outside trusted artifact_root"):
        validator.validate_result(result, baseline=baseline)


def test_artifact_audit_rejects_symlinked_parent_component(tmp_path):
    baseline, result = _approved_pair(tmp_path)
    root = Path(result["artifact_root"])
    external = tmp_path / "external"
    external.mkdir()
    target = external / "equity_curve.json"
    target.write_bytes(Path(result["artifact_files"]["equity_curve.json"]).read_bytes())
    link = root / "linked-parent"
    link.symlink_to(external, target_is_directory=True)
    result["artifact_files"]["equity_curve.json"] = str(link / "equity_curve.json")

    with pytest.raises(ValueError, match="symlink.*artifact path"):
        validator.validate_result(result, baseline=baseline)


def test_lhb_rejected_top5_evidence_reconciles_cash_slots_and_research_only_semantics(tmp_path):
    result = _raw_result(tmp_path, strategy_id="lhb_shortline")
    baseline = _template(strategy_id="lhb_shortline")
    rejected = {
        "trade_date": "2026-01-03",
        "phase18c_selection_rank": 2,
        "backtest_entry_eligible": False,
        "top5_eligible": False,
        "buy_signal_status": "research_only",
        "eligibility_status": "risk_watch",
    }
    result["acceptance_evidence"] = {"lhb_rejected_top5": [rejected]}
    failures = get_strategy_acceptance_callback("lhb_shortline")(result, baseline)
    assert not any("cash_slot" in failure or "research-only" in failure for failure in failures)

    result["acceptance_evidence"]["lhb_rejected_top5"] = []
    failures = get_strategy_acceptance_callback("lhb_shortline")(result, baseline)
    assert any("cash_slot_count" in failure for failure in failures)

    result["trades"][0]["buy_signal_status"] = "research_only"
    failures = get_strategy_acceptance_callback("lhb_shortline")(result, baseline)
    assert any("filled" in failure and "research-only" in failure for failure in failures)


@pytest.mark.parametrize("mutation", ["missing", "mixed"])
def test_lhb_materializer_rejects_missing_or_malformed_candidates(tmp_path, mutation):
    result = _raw_result(tmp_path, strategy_id="lhb_shortline")
    if mutation == "missing":
        result.pop("candidates")
    else:
        result["candidates"].append("malformed-candidate")

    with pytest.raises(ValueError, match="candidates.*(missing|malformed)"):
        validator.materialize_result_artifacts(
            result,
            template=_template(strategy_id="lhb_shortline"),
            output_dir=tmp_path / mutation,
        )


def test_lhb_candidates_are_materialized_and_audited(tmp_path):
    baseline, result = _approved_pair(tmp_path, strategy_id="lhb_shortline")

    evidence = {row["name"]: row for row in baseline["artifact_evidence"]}
    assert evidence["candidates.json"]["record_count"] == 1
    assert Path(result["artifact_files"]["candidates.json"]).is_file()


@pytest.mark.parametrize("strategy_id", ["mid_trend", "tech_bottleneck"])
def test_candidate_rejects_holdings_curve_reconciliation_drift_including_zero_days(
    tmp_path,
    strategy_id,
):
    result = _raw_result(tmp_path, strategy_id=strategy_id)
    result["equity_curve"][0]["holdings_count"] = 0
    prepared = validator.materialize_result_artifacts(
        result,
        template=_template(strategy_id=strategy_id),
        output_dir=tmp_path / f"holdings-{strategy_id}",
    )

    with pytest.raises(ValueError, match="holdings_count.*reconcile"):
        validator.build_candidate(
            prepared,
            template=_template(strategy_id=strategy_id),
        )


@pytest.mark.parametrize("bad_date", ["2025-12-31", "2026-06-18"])
def test_candidate_rejects_positions_and_trades_outside_fixed_replay_window(
    tmp_path,
    bad_date,
):
    result = _raw_result(tmp_path)
    result["positions"][0]["rebalance_date"] = bad_date
    result["positions"][0]["trade_date"] = bad_date
    result["trades"][0]["trade_date"] = bad_date
    prepared = validator.materialize_result_artifacts(
        result,
        template=_template(),
        output_dir=tmp_path / f"candidate-date-{bad_date}",
    )

    with pytest.raises(ValueError, match="(positions|trades).*outside requested replay window"):
        validator.build_candidate(prepared, template=_template())


@pytest.mark.parametrize("bad_date", ["2025-12-31", "2026-06-18"])
def test_validator_rejects_positions_and_trades_outside_fixed_replay_window(
    tmp_path,
    bad_date,
):
    baseline, result = _approved_pair(tmp_path)
    positions = deepcopy(result["positions"])
    trades = deepcopy(result["trades"])
    positions[0]["rebalance_date"] = bad_date
    positions[0]["trade_date"] = bad_date
    trades[0]["trade_date"] = bad_date
    _rewrite_artifact_and_approve(result, baseline, name="positions.json", rows=positions)
    _rewrite_artifact_and_approve(result, baseline, name="trades.json", rows=trades)

    with pytest.raises(ValueError, match="(positions|trades).*outside requested replay window"):
        validator.validate_result(result, baseline=baseline)


@pytest.mark.parametrize("bad_date", ["2025-12-31", "2026-07-16"])
def test_lhb_candidate_generation_rejects_candidates_outside_replay_window(
    tmp_path,
    bad_date,
):
    result = _raw_result(tmp_path, strategy_id="lhb_shortline")
    result["candidates"][0]["trade_date"] = bad_date
    prepared = validator.materialize_result_artifacts(
        result,
        template=_template(strategy_id="lhb_shortline"),
        output_dir=tmp_path / f"lhb-candidate-date-{bad_date}",
    )

    with pytest.raises(ValueError, match="candidates.*outside requested replay window"):
        validator.build_candidate(
            prepared,
            template=_template(strategy_id="lhb_shortline"),
        )


@pytest.mark.parametrize("bad_date", ["2025-12-31", "2026-07-16"])
def test_lhb_validation_rejects_candidates_outside_replay_window_after_hash_update(
    tmp_path,
    bad_date,
):
    baseline, result = _approved_pair(tmp_path, strategy_id="lhb_shortline")
    candidates = deepcopy(result["candidates"])
    candidates[0]["trade_date"] = bad_date
    _rewrite_artifact_and_approve(
        result,
        baseline,
        name="candidates.json",
        rows=candidates,
    )

    with pytest.raises(ValueError, match="candidates.*outside requested replay window"):
        validator.validate_result(result, baseline=baseline)


def test_every_registered_strategy_has_a_specific_acceptance_callback():
    callbacks = {
        contract.strategy_id: get_strategy_acceptance_callback(contract.strategy_id)
        for contract in iter_publication_contracts()
    }

    assert set(callbacks) == {"lhb_shortline", "mid_trend", "tech_bottleneck"}
    assert all(callable(callback) for callback in callbacks.values())


def test_filled_trade_count_uses_one_precedence_status_per_row(tmp_path):
    result = _raw_result(tmp_path)
    result["summary"].pop("filled_trade_count")
    result["trades"][0].update(
        {"account_trade_status": "filled", "fill_status": "filled", "status": "filled"}
    )
    prepared = validator.materialize_result_artifacts(
        result,
        template=_template(),
        output_dir=tmp_path / "same-statuses",
    )

    candidate = validator.build_candidate(prepared, template=_template())
    assert candidate["summary"]["filled_trade_count"] == 1


def test_filled_trade_count_rejects_conflicting_status_aliases(tmp_path):
    result = _raw_result(tmp_path)
    result["summary"].pop("filled_trade_count")
    result["trades"][0].update(
        {"account_trade_status": "filled", "fill_status": "rejected"}
    )
    prepared = validator.materialize_result_artifacts(
        result,
        template=_template(),
        output_dir=tmp_path / "conflicting-statuses",
    )

    with pytest.raises(ValueError, match="conflicting trade status aliases"):
        validator.build_candidate(prepared, template=_template())


def test_lhb_acceptance_requires_safe_top5_eligible_filled_evidence(tmp_path):
    result = _raw_result(tmp_path, strategy_id="lhb_shortline")
    result["config"].update({"risk_profile": "balanced", "rebalance_frequency": "daily"})
    result["summary"].update(
        {
            "selection_policy": "phase18c_top5_then_eligibility_no_refill",
            "phase18c_top_n": 5,
        }
    )
    result["trades"] = result["positions"] = [
        {
            "account_trade_status": "filled",
            "top_n": 5,
            "phase18c_selection_rank": 6,
            "backtest_entry_eligible": False,
            "eligibility_status": "ineligible",
            "top5_eligible": False,
            "research_only": True,
        }
    ]
    result["candidates"] = deepcopy(result["trades"])

    failures = get_strategy_acceptance_callback("lhb_shortline")(
        result,
        _template(strategy_id="lhb_shortline"),
    )

    assert any("rank" in failure for failure in failures)
    assert any("eligible" in failure for failure in failures)
    assert any("research-only" in failure for failure in failures)


def test_mid_trend_acceptance_requires_weekly_max2_policy_and_matching_counts(tmp_path):
    result = _raw_result(tmp_path)
    result["config"].update(
        {
            "rebalance_frequency": "daily",
            "max_weekly_replacements": 3,
            "benchmark_variant": "legacy",
        }
    )
    result["summary"].update({"position_rows": 2, "trade_rows": 2})

    failures = get_strategy_acceptance_callback("mid_trend")(
        result,
        _template(),
    )

    assert any("weekly" in failure for failure in failures)
    assert any("max_weekly_replacements" in failure for failure in failures)
    assert any("holding protection" in failure for failure in failures)
    assert any("position_rows" in failure for failure in failures)
    assert any("trade_rows" in failure for failure in failures)


def test_tech_acceptance_requires_policy_snapshot_coverage_and_matching_counts(tmp_path):
    result = _raw_result(tmp_path, strategy_id="tech_bottleneck")
    result["config"].update(
        {"rebalance_frequency": "weekly", "universe": "mixed", "protection_name": "none"}
    )
    result["summary"].update(
        {
            "universe": "mixed",
            "frequency": "weekly",
            "protection_name": "none",
            "position_rows": 2,
            "trade_rows": 2,
            "data_coverage": {"candidate_snapshot_latest_date": "2026-06-18"},
        }
    )

    failures = get_strategy_acceptance_callback("tech_bottleneck")(
        result,
        _template(strategy_id="tech_bottleneck"),
    )

    assert any("universe" in failure for failure in failures)
    assert any("biweekly" in failure for failure in failures)
    assert any("protection" in failure for failure in failures)
    assert any("future" in failure for failure in failures)
    assert any("position_rows" in failure for failure in failures)
    assert any("trade_rows" in failure for failure in failures)


def test_tech_acceptance_allows_parseable_snapshot_on_or_before_calculation_date(tmp_path):
    result = _raw_result(tmp_path, strategy_id="tech_bottleneck")
    baseline = _template(strategy_id="tech_bottleneck")

    for snapshot_date in ("2026-06-16", "2026-06-17"):
        result["summary"]["data_coverage"]["candidate_snapshot_latest_date"] = snapshot_date
        failures = get_strategy_acceptance_callback("tech_bottleneck")(result, baseline)
        assert not any("snapshot" in failure for failure in failures)

    result["summary"]["data_coverage"]["candidate_snapshot_latest_date"] = "not-a-date"
    failures = get_strategy_acceptance_callback("tech_bottleneck")(result, baseline)
    assert any("parseable" in failure for failure in failures)


def test_emit_candidates_is_separate_and_never_mutates_approved_fixture(tmp_path, monkeypatch):
    approved_path = tmp_path / "approved.json"
    approved = {"schema_version": "official_strategy_publication_baseline_v1", "baselines": []}
    approved_path.write_text(json.dumps(approved, indent=2), encoding="utf-8")
    original = approved_path.read_bytes()
    candidate_path = tmp_path / "candidates.json"

    contracts = iter_publication_contracts()
    monkeypatch.setattr(validator, "iter_publication_contracts", lambda: contracts)
    monkeypatch.setattr(
        validator,
        "run_fresh_backtest",
        lambda payload: _raw_result(tmp_path, strategy_id=payload["strategy_id"]),
    )
    monkeypatch.setattr(
        validator,
        "load_baselines",
        lambda _path: [
            {
                **_template(strategy_id=contract.strategy_id),
                "baseline_end_date": "2026-06-17",
            }
            for contract in contracts
        ],
    )

    exit_code = validator.main(
        [
            "--all",
            "--baseline-path",
            str(approved_path),
            "--emit-candidates",
            str(candidate_path),
        ]
    )

    assert exit_code == 0
    assert approved_path.read_bytes() == original
    candidates = json.loads(candidate_path.read_text(encoding="utf-8"))["baselines"]
    assert {(row["strategy_id"], row["profile"]) for row in candidates} == {
        (contract.strategy_id, contract.profile) for contract in contracts
    }


def test_cli_requires_one_strategy_or_all_and_supports_output_flag(tmp_path):
    with pytest.raises(SystemExit):
        validator.main(["--baseline-path", str(tmp_path / "missing.json")])

    parser = validator.build_parser()
    args = parser.parse_args(
        [
            "--strategy-id",
            "mid_trend",
            "--profile",
            "balanced",
            "--baseline-path",
            "baseline.json",
            "--output",
            "report.json",
        ]
    )
    assert args.output == "report.json"


def test_cli_expected_failure_emits_compact_json_and_returns_nonzero(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract = get_publication_contract("mid_trend")
    monkeypatch.setattr(validator, "iter_publication_contracts", lambda: (contract,))
    monkeypatch.setattr(validator, "load_baselines", lambda _path: [_template()])
    monkeypatch.setattr(
        validator,
        "run_fresh_backtest",
        lambda _payload: (_ for _ in ()).throw(ValueError("authoritative replay failed")),
    )
    output = tmp_path / "failure.json"

    exit_code = validator.main(
        [
            "--strategy-id",
            "mid_trend",
            "--baseline-path",
            str(tmp_path / "ignored.json"),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    stdout_payload = json.loads(capsys.readouterr().out)
    assert stdout_payload == json.loads(output.read_text(encoding="utf-8"))
    assert stdout_payload == {
        "status": "failed",
        "error": "authoritative replay failed",
        "error_type": "ValueError",
    }


def test_cli_converts_psycopg_operational_error_to_compact_json(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract = get_publication_contract("mid_trend")
    monkeypatch.setattr(validator, "iter_publication_contracts", lambda: (contract,))
    monkeypatch.setattr(validator, "load_baselines", lambda _path: [_template()])
    monkeypatch.setattr(
        validator,
        "run_fresh_backtest",
        lambda _payload: (_ for _ in ()).throw(OperationalError("database unavailable")),
    )

    exit_code = validator.main(
        ["--strategy-id", "mid_trend", "--baseline-path", str(tmp_path / "ignored")]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["error_type"] == "OperationalError"


def test_cli_does_not_catch_keyboard_interrupt(tmp_path, monkeypatch):
    contract = get_publication_contract("mid_trend")
    monkeypatch.setattr(validator, "iter_publication_contracts", lambda: (contract,))
    monkeypatch.setattr(validator, "load_baselines", lambda _path: [_template()])
    monkeypatch.setattr(
        validator,
        "run_fresh_backtest",
        lambda _payload: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    with pytest.raises(KeyboardInterrupt):
        validator.main(
            ["--strategy-id", "mid_trend", "--baseline-path", str(tmp_path / "ignored")]
        )


def test_cli_output_write_failure_is_attempted_once_and_reported_to_stdout(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract = get_publication_contract("mid_trend")
    monkeypatch.setattr(validator, "iter_publication_contracts", lambda: (contract,))
    monkeypatch.setattr(validator, "load_baselines", lambda _path: [_template()])
    monkeypatch.setattr(
        validator,
        "run_fresh_backtest",
        lambda _payload: (_ for _ in ()).throw(ValueError("primary failure")),
    )
    writes = []

    def fail_write(path, payload):
        writes.append((path, payload))
        raise OSError("output unavailable")

    monkeypatch.setattr(validator, "_write_json", fail_write)

    exit_code = validator.main(
        [
            "--strategy-id",
            "mid_trend",
            "--baseline-path",
            str(tmp_path / "ignored"),
            "--output",
            str(tmp_path / "report.json"),
        ]
    )

    assert exit_code == 1
    assert len(writes) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["error_type"] == "OSError"
    assert payload["error"] == "output unavailable"


def test_selected_candidate_bootstrap_does_not_require_approved_fixture(
    tmp_path,
    monkeypatch,
    capsys,
):
    contract = get_publication_contract("mid_trend")
    monkeypatch.setattr(validator, "iter_publication_contracts", lambda: (contract,))
    monkeypatch.setattr(
        validator,
        "load_baselines",
        lambda _path: (_ for _ in ()).throw(AssertionError("fixture must not be loaded")),
    )
    monkeypatch.setattr(
        validator,
        "run_fresh_backtest",
        lambda _payload: _raw_result(tmp_path),
    )
    output = tmp_path / "bootstrap-candidate.json"

    exit_code = validator.main(
        [
            "--strategy-id",
            "mid_trend",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-06-17",
            "--emit-candidates",
            str(output),
            "--baseline-path",
            str(tmp_path / "absent.json"),
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "success"
    candidate = json.loads(output.read_text(encoding="utf-8"))["baselines"][0]
    assert candidate["strategy_id"] == "mid_trend"
    assert candidate["baseline_start_date"] == "2026-01-01"
    assert candidate["baseline_end_date"] == "2026-06-17"


def test_script_entrypoint_has_success_and_compact_failure_protocol(tmp_path):
    help_run = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=SCRIPT_PATH.parents[1],
        env={"PYTHONPATH": "src"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert help_run.returncode == 0

    failed_run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--strategy-id",
            "mid_trend",
            "--baseline-path",
            str(tmp_path / "missing.json"),
        ],
        cwd=SCRIPT_PATH.parents[1],
        env={"PYTHONPATH": "src"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert failed_run.returncode == 1
    assert failed_run.stderr == ""
    assert json.loads(failed_run.stdout)["status"] == "failed"
