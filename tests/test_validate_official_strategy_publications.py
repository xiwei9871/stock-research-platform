from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

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


def _artifact(tmp_path: Path) -> tuple[Path, str]:
    path = tmp_path / "authoritative.csv"
    path.write_text("trade_date,equity\n2026-01-01,1.0\n", encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _baseline(tmp_path: Path, *, strategy_id: str = "mid_trend") -> dict:
    contract = get_publication_contract(strategy_id)
    artifact, digest = _artifact(tmp_path)
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
        "artifact_evidence": [{"name": artifact.name, "sha256": digest, "record_count": 1}],
    }


def _result(tmp_path: Path, *, strategy_id: str = "mid_trend") -> dict:
    baseline = _baseline(tmp_path, strategy_id=strategy_id)
    identity = deepcopy(baseline["publication_identity"])
    result = {
        "strategy_id": strategy_id,
        "config": {
            "strategy_id": strategy_id,
            "start_date": baseline["baseline_start_date"],
            "end_date": baseline["baseline_end_date"],
            "top_n": 5,
        },
        "publication_identity": identity,
        "summary": {
            **baseline["summary"],
            "start_date": baseline["baseline_start_date"],
            "end_date": baseline["baseline_end_date"],
            "publication_identity": deepcopy(identity),
        },
        "equity_curve": [
            {
                "trade_date": "2026-01-01",
                "equity": 1.0,
                "cash": 1.0,
                "open_position_count": 0,
            },
            {
                "trade_date": "2026-06-17",
                "equity": 1.1,
                "cash": 0.2,
                "open_position_count": 4,
            },
        ],
        "positions": [{"rebalance_date": "2026-06-17", "trade_date": "2026-06-17"}],
        "trades": [{"fill_status": "filled"}],
        "source_artifacts": [str(tmp_path / "authoritative.csv")],
    }
    if strategy_id == "lhb_shortline":
        row = {
            "account_trade_status": "filled",
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
            }
        )
        result["positions"] = [deepcopy(row)]
        result["trades"] = [deepcopy(row)]
        result["candidates"] = [deepcopy(row)]
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
                "data_coverage": {"candidate_snapshot_latest_date": baseline["baseline_end_date"]},
            }
        )
    return result


def test_validator_accepts_exact_identity_common_invariants_and_artifact_hashes(tmp_path):
    baseline = _baseline(tmp_path)
    report = validator.validate_result(_result(tmp_path), baseline=baseline)

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
    baseline = _baseline(tmp_path)
    result = _result(tmp_path)
    result["summary"][field] = value

    with pytest.raises(ValueError, match=f"acceptance mismatch.*{field}"):
        validator.validate_result(result, baseline=baseline)


def test_validator_rejects_identity_date_and_acceptance_profile_drift(tmp_path):
    baseline = _baseline(tmp_path)
    result = _result(tmp_path)
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
    baseline = _baseline(tmp_path)
    result = _result(tmp_path)
    result["summary"]["total_return"] = value

    with pytest.raises(ValueError, match="finite.*total_return"):
        validator.validate_result(result, baseline=baseline)


def test_validator_rejects_unsafe_account_rows(tmp_path):
    baseline = _baseline(tmp_path)
    result = _result(tmp_path)
    result["equity_curve"][-1]["cash"] = -0.01
    result["equity_curve"][-1]["open_position_count"] = 6

    with pytest.raises(ValueError) as exc_info:
        validator.validate_result(result, baseline=baseline)

    assert "negative cash" in str(exc_info.value)
    assert "max positions" in str(exc_info.value)


def test_validator_rejects_impossible_account_loss_even_when_baseline_matches(tmp_path):
    baseline = _baseline(tmp_path)
    result = _result(tmp_path)
    baseline["summary"]["total_return"] = -1.01
    baseline["summary"]["max_drawdown"] = -1.01
    result["summary"]["total_return"] = -1.01
    result["summary"]["max_drawdown"] = -1.01

    with pytest.raises(ValueError) as exc_info:
        validator.validate_result(result, baseline=baseline)

    assert "account safety: total_return" in str(exc_info.value)
    assert "account safety: max_drawdown" in str(exc_info.value)


def test_validator_fails_closed_for_missing_mixed_or_malformed_artifact_evidence(tmp_path):
    baseline = _baseline(tmp_path)
    missing = _result(tmp_path)
    missing["source_artifacts"] = []
    with pytest.raises(ValueError, match="artifact evidence missing"):
        validator.validate_result(missing, baseline=baseline)

    mixed = _result(tmp_path)
    Path(mixed["source_artifacts"][0]).write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact_evidence"):
        validator.validate_result(mixed, baseline=baseline)

    empty_fallback = _result(tmp_path)
    del empty_fallback["source_artifacts"]
    empty_fallback["positions"] = []
    with pytest.raises(ValueError, match="positions.*empty"):
        validator.build_candidate(empty_fallback, template=baseline)

    malformed = _baseline(tmp_path)
    malformed["artifact_evidence"][0]["sha256"] = "bad"
    with pytest.raises(ValueError, match="malformed.*sha256"):
        validator.validate_result(_result(tmp_path), baseline=malformed)


def test_every_registered_strategy_has_a_specific_acceptance_callback():
    callbacks = {
        contract.strategy_id: get_strategy_acceptance_callback(contract.strategy_id)
        for contract in iter_publication_contracts()
    }

    assert set(callbacks) == {"lhb_shortline", "mid_trend", "tech_bottleneck"}
    assert all(callable(callback) for callback in callbacks.values())


def test_lhb_acceptance_requires_safe_top5_eligible_filled_evidence(tmp_path):
    result = _result(tmp_path, strategy_id="lhb_shortline")
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
        _baseline(tmp_path, strategy_id="lhb_shortline"),
    )

    assert any("rank" in failure for failure in failures)
    assert any("eligible" in failure for failure in failures)
    assert any("research-only" in failure for failure in failures)


def test_mid_trend_acceptance_requires_weekly_max2_policy_and_matching_counts(tmp_path):
    result = _result(tmp_path)
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
        _baseline(tmp_path),
    )

    assert any("weekly" in failure for failure in failures)
    assert any("max_weekly_replacements" in failure for failure in failures)
    assert any("holding protection" in failure for failure in failures)
    assert any("position_rows" in failure for failure in failures)
    assert any("trade_rows" in failure for failure in failures)


def test_tech_acceptance_requires_policy_snapshot_coverage_and_matching_counts(tmp_path):
    result = _result(tmp_path, strategy_id="tech_bottleneck")
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
            "data_coverage": {"candidate_snapshot_latest_date": "2026-06-16"},
        }
    )

    failures = get_strategy_acceptance_callback("tech_bottleneck")(
        result,
        _baseline(tmp_path, strategy_id="tech_bottleneck"),
    )

    assert any("universe" in failure for failure in failures)
    assert any("biweekly" in failure for failure in failures)
    assert any("protection" in failure for failure in failures)
    assert any("snapshot" in failure for failure in failures)
    assert any("position_rows" in failure for failure in failures)
    assert any("trade_rows" in failure for failure in failures)


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
        lambda payload: _result(tmp_path, strategy_id=payload["strategy_id"]),
    )
    monkeypatch.setattr(
        validator,
        "load_baselines",
        lambda _path: [
            {
                **_baseline(tmp_path, strategy_id=contract.strategy_id),
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
