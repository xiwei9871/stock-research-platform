from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_STRATEGY_CONTRACT_PATH = Path(
    "/Users/xiwei/stock_research/outputs/research/"
    "official_strategy_contract_rescan_20260101_20260617_fresh_all/"
    "official_strategy_contracts.json"
)


@dataclass(frozen=True)
class StrategyContract:
    contract_id: str
    strategy_id: str
    profile: str
    engine: str
    variant: str
    top_n: int
    transaction_cost_bps: float
    adjust_type: str
    frequency: str | None = None
    protection_name: str | None = None
    benchmark_artifact_path: str = ""


@dataclass(frozen=True)
class ContractValidationResult:
    status: str
    reason: str = ""


def load_strategy_contracts(
    path: str | Path = DEFAULT_STRATEGY_CONTRACT_PATH,
    *,
    profile: str = "balanced",
) -> dict[str, StrategyContract]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    contracts: dict[str, StrategyContract] = {}
    for row in payload.get("profiles") or []:
        if str(row.get("selected_profile") or "") != profile:
            continue
        strategy_id = str(row.get("strategy_id") or "")
        if not strategy_id:
            continue
        contracts[strategy_id] = _contract_from_profile_row(row, profile=profile)
    return contracts


def strategy_contract_run_config(contract: StrategyContract) -> dict[str, Any]:
    config: dict[str, Any] = {
        "top_n": contract.top_n,
        "rebalance_frequency": contract.frequency,
        "transaction_cost_bps": contract.transaction_cost_bps,
        "adjust_type": contract.adjust_type,
        "contract_id": contract.contract_id,
        "contract_profile": contract.profile,
        "contract_variant": contract.variant,
    }
    if contract.strategy_id == "lhb_shortline":
        risk_profile = contract.variant.split(":", 1)[1] if ":" in contract.variant else contract.profile
        config["risk_profile"] = risk_profile
    if contract.strategy_id == "mid_trend":
        config["benchmark_variant"] = contract.variant
    if contract.strategy_id == "tech_bottleneck" and contract.protection_name:
        config["protection_name"] = contract.protection_name
    return {key: value for key, value in config.items() if value is not None}


def validate_strategy_summary_against_contract(
    summary: dict[str, Any],
    contract: StrategyContract,
) -> ContractValidationResult:
    checks = [
        ("engine", _summary_engine(summary), contract.engine),
        ("variant", _summary_variant(summary, contract), contract.variant),
        ("top_n", _optional_int(summary.get("top_n")), int(contract.top_n)),
        (
            "transaction_cost_bps",
            _optional_float(summary.get("transaction_cost_bps")),
            float(contract.transaction_cost_bps),
        ),
        ("adjust_type", str(summary.get("adjust_type") or ""), contract.adjust_type),
    ]
    if contract.frequency:
        checks.append(("frequency", str(summary.get("frequency") or ""), contract.frequency))
    if contract.protection_name:
        checks.append(
            ("protection_name", str(summary.get("protection_name") or ""), contract.protection_name)
        )

    for field, actual, expected in checks:
        if actual != expected:
            return ContractValidationResult(
                status="failed",
                reason=f"{field} mismatch: expected {expected}, got {actual}",
            )
    return ContractValidationResult(status="success")


def _summary_engine(summary: dict[str, Any]) -> str:
    return str(summary.get("engine_version") or summary.get("engine") or summary.get("source_kind") or "")


def _summary_variant(summary: dict[str, Any], contract: StrategyContract) -> str:
    if contract.strategy_id == "lhb_shortline":
        strategy = str(summary.get("phase18c_strategy") or summary.get("strategy") or "")
        risk_profile = str(summary.get("risk_profile") or "")
        if strategy and risk_profile:
            return f"{strategy}:{risk_profile}"
    if contract.strategy_id == "tech_bottleneck":
        universe = str(summary.get("universe") or "")
        frequency = str(summary.get("frequency") or "")
        protection = str(summary.get("protection_name") or "")
        if universe and frequency and protection:
            return f"{universe}:{frequency}:{protection}"
    return str(
        summary.get("variant")
        or summary.get("variant_name")
        or summary.get("benchmark_variant")
        or summary.get("phase18c_strategy")
        or ""
    )


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _contract_from_profile_row(row: dict[str, Any], *, profile: str) -> StrategyContract:
    strategy_id = str(row.get("strategy_id") or "")
    variant = str(row.get("variant") or "")
    return StrategyContract(
        contract_id=f"{strategy_id}:{profile}:{variant}",
        strategy_id=strategy_id,
        profile=profile,
        engine=str(row.get("engine") or ""),
        variant=variant,
        top_n=int(row.get("top_n") or 0),
        transaction_cost_bps=float(row.get("transaction_cost_bps") or 0.0),
        adjust_type=str(row.get("adjust_type") or "hfq"),
        frequency=str(row.get("frequency") or "") or None,
        protection_name=str(row.get("protection_name") or "") or None,
        benchmark_artifact_path=str(row.get("benchmark_artifact_path") or ""),
    )
