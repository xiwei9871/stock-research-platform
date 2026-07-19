"""Registry and identity helpers for officially publishable strategy runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any, Callable, Mapping


IDENTITY_SCHEMA_VERSION = "strategy_publication_identity_v1"
_COMMON_IDENTITY_FIELDS = (
    "identity_schema_version",
    "strategy_id",
    "contract_id",
    "engine_version",
    "variant",
    "config_fingerprint",
    "publication_policy",
)
_MISSING = object()


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class StrategyPublicationContract:
    strategy_id: str
    profile: str
    contract_id: str
    engine_version: str
    variant: str
    normalized_run_config: Mapping[str, Any]
    publication_policy: Mapping[str, Any]
    identity_schema_version: str = IDENTITY_SCHEMA_VERSION
    acceptance_profile: str = "default"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "normalized_run_config",
            _freeze_json(self.normalized_run_config),
        )
        object.__setattr__(self, "publication_policy", _freeze_json(self.publication_policy))


def canonical_config_fingerprint(mapping: Mapping[str, Any]) -> str:
    """Return the SHA-256 digest of the contract's canonical JSON config."""

    serialized = json.dumps(
        _thaw_json(mapping),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def build_publication_identity(contract: StrategyPublicationContract) -> dict[str, Any]:
    return {
        "identity_schema_version": contract.identity_schema_version,
        "strategy_id": contract.strategy_id,
        "contract_id": contract.contract_id,
        "engine_version": contract.engine_version,
        "variant": contract.variant,
        "config_fingerprint": canonical_config_fingerprint(contract.normalized_run_config),
        "publication_policy": _thaw_json(contract.publication_policy),
    }


def validate_publication_identity(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return field-level differences between actual and expected identities."""

    mismatches: list[dict[str, Any]] = []
    fields = dict.fromkeys((*_COMMON_IDENTITY_FIELDS, *expected.keys(), *actual.keys()))
    for field in fields:
        expected_value = expected.get(field, _MISSING)
        actual_value = actual.get(field, _MISSING)
        if actual_value != expected_value:
            mismatches.append(
                {
                    "field": field,
                    "expected": None if expected_value is _MISSING else expected_value,
                    "actual": None if actual_value is _MISSING else actual_value,
                }
            )
    return mismatches


def _contract(
    strategy_id: str,
    *,
    engine_version: str,
    variant: str,
    frequency: str,
    strategy_config: Mapping[str, Any],
    publication_policy: Mapping[str, Any],
    acceptance_profile: str,
) -> StrategyPublicationContract:
    return StrategyPublicationContract(
        strategy_id=strategy_id,
        profile="balanced",
        contract_id=f"{strategy_id}:balanced:{variant}",
        engine_version=engine_version,
        variant=variant,
        normalized_run_config={
            "top_n": 5,
            "rebalance_frequency": frequency,
            "transaction_cost_bps": 10.0,
            "max_position_weight": 0.2,
            "adjust_type": "hfq",
            **dict(strategy_config),
        },
        publication_policy=publication_policy,
        acceptance_profile=acceptance_profile,
    )


_PUBLICATION_CONTRACTS: Mapping[tuple[str, str], StrategyPublicationContract] = (
    MappingProxyType(
        {
            ("lhb_shortline", "balanced"): _contract(
                "lhb_shortline",
                engine_version="lhb_shortline_v1",
                variant="auction_enhanced_rerank:balanced",
                frequency="daily",
                strategy_config={"risk_profile": "balanced"},
                publication_policy={
                    "strategy_version": "lhb_v1_stable_safe_top5",
                    "selection_policy": "phase18c_top5_then_eligibility_no_refill",
                    "market_regime_policy": "disabled_for_stable_strategy",
                },
                acceptance_profile="lhb_cash_account_v1",
            ),
            ("mid_trend", "balanced"): _contract(
                "mid_trend",
                engine_version="mid_trend_v1",
                variant="top5_weekly_max2_selective_trend_holding_protection_v1",
                frequency="weekly",
                strategy_config={
                    "benchmark_variant": (
                        "top5_weekly_max2_selective_trend_holding_protection_v1"
                    )
                },
                publication_policy={
                    "benchmark_variant": (
                        "top5_weekly_max2_selective_trend_holding_protection_v1"
                    )
                },
                acceptance_profile="mid_trend_weekly_control_v1",
            ),
            ("tech_bottleneck", "balanced"): _contract(
                "tech_bottleneck",
                engine_version="tech_bottleneck_v1",
                variant="strict_153_st_only_financial_state:biweekly:rank_exit_top10_1d",
                frequency="biweekly",
                strategy_config={
                    "universe": "strict_153_st_only_financial_state",
                    "protection_name": "rank_exit_top10_1d",
                },
                publication_policy={
                    "universe": "strict_153_st_only_financial_state",
                    "frequency": "biweekly",
                    "protection_name": "rank_exit_top10_1d",
                },
                acceptance_profile="tech_bottleneck_biweekly_v1",
            ),
        }
    )
)

OFFICIAL_STRATEGY_IDS = frozenset(
    strategy_id for strategy_id, _profile in _PUBLICATION_CONTRACTS
)


def iter_publication_contracts() -> tuple[StrategyPublicationContract, ...]:
    """Return every immutable publication contract in stable registry order."""

    return tuple(
        _PUBLICATION_CONTRACTS[key]
        for key in sorted(_PUBLICATION_CONTRACTS)
    )


def get_publication_contract(
    strategy_id: str,
    profile: str = "balanced",
) -> StrategyPublicationContract:
    try:
        return _PUBLICATION_CONTRACTS[(strategy_id, profile)]
    except KeyError as exc:
        raise KeyError(f"unknown strategy publication contract: {strategy_id}/{profile}") from exc


StrategyAcceptanceCallback = Callable[
    [Mapping[str, Any], Mapping[str, Any]],
    list[str],
]


def _summary(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("summary")
    return value if isinstance(value, Mapping) else {}


def _config(result: Mapping[str, Any]) -> Mapping[str, Any]:
    value = result.get("config")
    return value if isinstance(value, Mapping) else {}


def _rows(result: Mapping[str, Any], field: str) -> list[Mapping[str, Any]]:
    value = result.get(field)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _expected_policy(baseline: Mapping[str, Any]) -> Mapping[str, Any]:
    identity = baseline.get("publication_identity")
    if not isinstance(identity, Mapping):
        return {}
    policy = identity.get("publication_policy")
    return policy if isinstance(policy, Mapping) else {}


def _lhb_acceptance(result: Mapping[str, Any], _baseline: Mapping[str, Any]) -> list[str]:
    summary = _summary(result)
    config = _config(result)
    trades = _rows(result, "trades")
    positions = _rows(result, "positions")
    raw_candidates = result.get("candidates")
    candidates = (
        list(raw_candidates)
        if isinstance(raw_candidates, list)
        and raw_candidates
        and all(isinstance(row, Mapping) for row in raw_candidates)
        else []
    )
    acceptance_evidence = result.get("acceptance_evidence")
    rejected = (
        _rows(acceptance_evidence, "lhb_rejected_top5")
        if isinstance(acceptance_evidence, Mapping)
        else []
    )
    failures: list[str] = []
    if not isinstance(raw_candidates, list) or not raw_candidates:
        failures.append("LHB candidates collection missing or empty")
    elif any(not isinstance(row, Mapping) for row in raw_candidates):
        failures.append("LHB candidates collection contains malformed or mixed rows")
    if config.get("top_n") != 5 or config.get("rebalance_frequency") != "daily":
        failures.append("LHB acceptance requires daily safe top5 config")
    if config.get("risk_profile") != "balanced":
        failures.append("LHB acceptance requires balanced risk profile")
    if summary.get("selection_policy") != "phase18c_top5_then_eligibility_no_refill":
        failures.append("LHB acceptance requires top5 no-refill selection policy")
    if summary.get("phase18c_top_n") != 5:
        failures.append("LHB acceptance requires phase18c_top_n=5")
    for field in ("filled_trade_count", "cash_slot_count"):
        value = summary.get(field)
        if value is not None and (isinstance(value, bool) or int(value) < 0):
            failures.append(f"{field} must be a non-negative integer")
    if not trades or not positions or not candidates:
        failures.append("LHB acceptance evidence missing trades, positions, or candidates")
    if len(trades) != int(summary.get("filled_trade_count") or -1):
        failures.append("LHB filled_trade_count does not match trade rows")
    if positions != trades:
        failures.append("LHB positions must be the authoritative filled account trades")
    for location, rows in (("trade", trades), ("candidate", candidates)):
        for row in rows:
            rank = row.get("phase18c_selection_rank")
            try:
                valid_rank = int(rank) == float(rank) and 1 <= int(rank) <= 5
            except (TypeError, ValueError, OverflowError):
                valid_rank = False
            if not valid_rank:
                failures.append(f"LHB {location} rank must stay within approved top5")
            if row.get("backtest_entry_eligible") is not True or row.get("eligibility_status") != "eligible":
                failures.append(f"LHB {location} must contain only eligible evidence")
            if row.get("top5_eligible") is not True:
                failures.append(f"LHB {location} must be explicitly top5 eligible")
            if row.get("research_only") is True:
                failures.append(f"LHB {location} must not include research-only evidence")
            if str(row.get("buy_signal_status") or "") == "research_only":
                failures.append(f"LHB {location} filled evidence must not be research-only")
    if any(row.get("account_trade_status") != "filled" for row in trades):
        failures.append("LHB authoritative trade rows must all be filled")
    cash_slot_count = summary.get("cash_slot_count")
    if not isinstance(cash_slot_count, int) or isinstance(cash_slot_count, bool):
        failures.append("LHB cash_slot_count must be an integer")
    elif len(rejected) != cash_slot_count:
        failures.append(
            f"LHB cash_slot_count does not match rejected Top5 evidence: "
            f"summary={cash_slot_count}, rejected={len(rejected)}"
        )
    for row in rejected:
        rank = row.get("phase18c_selection_rank")
        try:
            valid_rank = int(rank) == float(rank) and 1 <= int(rank) <= 5
        except (TypeError, ValueError, OverflowError):
            valid_rank = False
        if not valid_rank:
            failures.append("LHB rejected cash-slot rank must stay within Top5")
        if row.get("backtest_entry_eligible") is not False:
            failures.append("LHB rejected cash-slot evidence must be explicitly ineligible")
        if row.get("top5_eligible") is not False:
            failures.append("LHB rejected cash-slot evidence must have top5_eligible=false")
        if str(row.get("buy_signal_status") or "") != "research_only":
            failures.append("LHB rejected cash-slot evidence must be research-only")
        if str(row.get("eligibility_status") or "") not in {"risk_watch", "hard_reject"}:
            failures.append("LHB rejected cash-slot eligibility_status is invalid")
        if "research_only" in row and row.get("research_only") is not True:
            failures.append("LHB rejected cash-slot research_only flag must be true")
    return failures


def _mid_trend_acceptance(
    result: Mapping[str, Any],
    _baseline: Mapping[str, Any],
) -> list[str]:
    summary = _summary(result)
    config = _config(result)
    positions = _rows(result, "positions")
    trades = _rows(result, "trades")
    failures: list[str] = []
    expected_variant = str(
        _baseline.get("publication_identity", {}).get("variant", "")
        if isinstance(_baseline.get("publication_identity"), Mapping)
        else ""
    )
    if config.get("rebalance_frequency") != "weekly":
        failures.append("Mid Trend acceptance requires weekly rebalance")
    if config.get("max_weekly_replacements") != 2:
        failures.append("Mid Trend acceptance requires max_weekly_replacements=2")
    if config.get("benchmark_variant") != expected_variant or summary.get("benchmark_variant") != expected_variant:
        failures.append("Mid Trend acceptance requires approved holding protection policy")
    if summary.get("position_rows") != len(positions):
        failures.append("Mid Trend position_rows does not match positions artifact")
    if summary.get("trade_rows") != len(trades):
        failures.append("Mid Trend trade_rows does not match trades artifact")
    if not positions or not trades:
        failures.append("Mid Trend acceptance evidence missing positions or trades")
    by_date: dict[str, int] = {}
    for row in positions:
        date = str(row.get("rebalance_date") or row.get("trade_date") or "")
        if not date:
            failures.append("Mid Trend position row missing rebalance date")
            break
        by_date[date] = by_date.get(date, 0) + 1
    if any(count > 5 for count in by_date.values()):
        failures.append("Mid Trend positions exceed approved top5 account size")
    invested_weight = summary.get("average_invested_weight")
    if invested_weight is not None and not 0.0 <= float(invested_weight) <= 1.0:
        failures.append("average_invested_weight must be between zero and one")
    return failures


def _tech_bottleneck_acceptance(
    result: Mapping[str, Any],
    _baseline: Mapping[str, Any],
) -> list[str]:
    summary = _summary(result)
    config = _config(result)
    positions = _rows(result, "positions")
    trades = _rows(result, "trades")
    policy = _expected_policy(_baseline)
    failures: list[str] = []
    expected_universe = policy.get("universe")
    expected_frequency = policy.get("frequency")
    expected_protection = policy.get("protection_name")
    if config.get("universe") != expected_universe or summary.get("universe") != expected_universe:
        failures.append("Tech Bottleneck universe does not match approved policy")
    if config.get("rebalance_frequency") != expected_frequency or summary.get("frequency") != expected_frequency:
        failures.append("Tech Bottleneck acceptance requires approved biweekly frequency")
    if config.get("protection_name") != expected_protection or summary.get("protection_name") != expected_protection:
        failures.append("Tech Bottleneck protection policy mismatch")
    coverage = summary.get("data_coverage")
    latest_snapshot = coverage.get("candidate_snapshot_latest_date") if isinstance(coverage, Mapping) else None
    calculation_date = _baseline.get("baseline_end_date")
    try:
        snapshot_date = date.fromisoformat(str(latest_snapshot))
        approved_calculation_date = date.fromisoformat(str(calculation_date))
        if snapshot_date > approved_calculation_date:
            failures.append("Tech Bottleneck candidate snapshot is future-dated")
    except ValueError:
        failures.append("Tech Bottleneck candidate snapshot date must be parseable")
    if summary.get("position_rows") != len(positions):
        failures.append("Tech Bottleneck position_rows does not match positions artifact")
    if summary.get("trade_rows") != len(trades):
        failures.append("Tech Bottleneck trade_rows does not match trades artifact")
    if not positions or not trades:
        failures.append("Tech Bottleneck acceptance evidence missing positions or trades")
    by_date: dict[str, int] = {}
    for row in positions:
        date_text = str(row.get("trade_date") or row.get("date") or "")
        if not date_text:
            failures.append("Tech Bottleneck position row missing trade date")
            break
        by_date[date_text] = by_date.get(date_text, 0) + 1
    if any(count > 5 for count in by_date.values()):
        failures.append("Tech Bottleneck positions exceed approved top5 account size")
    exposure = summary.get("avg_actual_exposure")
    if exposure is not None and not 0.0 <= float(exposure) <= 1.0:
        failures.append("avg_actual_exposure must be between zero and one")
    return failures


_STRATEGY_ACCEPTANCE_CALLBACKS: Mapping[str, StrategyAcceptanceCallback] = MappingProxyType(
    {
        "lhb_shortline": _lhb_acceptance,
        "mid_trend": _mid_trend_acceptance,
        "tech_bottleneck": _tech_bottleneck_acceptance,
    }
)


def get_strategy_acceptance_callback(strategy_id: str) -> StrategyAcceptanceCallback:
    """Return the registered strategy-specific replay acceptance callback."""

    try:
        return _STRATEGY_ACCEPTANCE_CALLBACKS[strategy_id]
    except KeyError as exc:
        raise KeyError(f"unknown strategy acceptance callback: {strategy_id}") from exc
