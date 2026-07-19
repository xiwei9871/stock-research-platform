#!/usr/bin/env python3
"""Validate fixed-date fresh replays for every official strategy publication."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from stock_research.dashboard.backtests import run_fresh_backtest
from stock_research.strategy_publication_contracts import (
    build_publication_identity,
    get_publication_contract,
    get_strategy_acceptance_callback,
    iter_publication_contracts,
    validate_publication_identity,
)


BASELINE_SCHEMA_VERSION = "official_strategy_publication_baseline_v1"
DEFAULT_BASELINE_PATH = Path("tests/fixtures/official_strategy_publication_baselines.json")
_SUMMARY_FIELDS = (
    "total_return",
    "max_drawdown",
    "filled_trade_count",
    "cash_slot_count",
)
_FLOAT_FIELDS = frozenset({"total_return", "max_drawdown"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--strategy-id")
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--profile", default="balanced")
    parser.add_argument("--baseline-path", default=str(DEFAULT_BASELINE_PATH))
    parser.add_argument("--output")
    parser.add_argument("--emit-candidates")
    return parser


def load_baselines(path: str | Path) -> list[dict[str, Any]]:
    baseline_path = Path(path)
    try:
        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"baseline file unreadable: {baseline_path}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("baseline file malformed: root must be a mapping")
    if payload.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise ValueError("baseline file malformed: unsupported schema_version")
    rows = payload.get("baselines")
    if not isinstance(rows, list):
        raise ValueError("baseline file malformed: baselines must be a list")
    baselines = [dict(row) if isinstance(row, Mapping) else row for row in rows]
    seen: set[tuple[str, str]] = set()
    for row in baselines:
        if not isinstance(row, dict):
            raise ValueError("baseline file malformed: every baseline must be a mapping")
        _validate_baseline_schema(row)
        key = (row["strategy_id"], row["profile"])
        if key in seen:
            raise ValueError(f"baseline file malformed: duplicate {key[0]}/{key[1]}")
        seen.add(key)
    return baselines


def validate_result(
    result: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one fresh replay against an explicitly approved baseline."""

    _validate_baseline_schema(baseline)
    strategy_id = str(baseline["strategy_id"])
    profile = str(baseline["profile"])
    contract = get_publication_contract(strategy_id, profile)
    expected_identity = build_publication_identity(contract)
    failures: list[str] = []

    if baseline["acceptance_profile"] != contract.acceptance_profile:
        failures.append(
            "acceptance_profile expected "
            f"{contract.acceptance_profile!r}, got {baseline['acceptance_profile']!r}"
        )
    baseline_identity = baseline["publication_identity"]
    for mismatch in validate_publication_identity(baseline_identity, expected_identity):
        failures.append(f"baseline publication_identity.{mismatch['field']} mismatch")

    if result.get("strategy_id") != strategy_id:
        failures.append(
            f"strategy_id expected {strategy_id!r}, got {result.get('strategy_id')!r}"
        )
    summary = result.get("summary")
    config = result.get("config")
    if not isinstance(summary, Mapping):
        failures.append("summary missing or malformed")
        summary = {}
    if not isinstance(config, Mapping):
        failures.append("config missing or malformed")
        config = {}

    for location, identity in (
        ("result", result.get("publication_identity")),
        ("summary", summary.get("publication_identity")),
    ):
        if not isinstance(identity, Mapping):
            failures.append(f"{location} publication_identity missing or malformed")
            continue
        for mismatch in validate_publication_identity(identity, expected_identity):
            failures.append(
                f"{location} publication_identity.{mismatch['field']} acceptance mismatch"
            )

    _validate_dates(config, summary, baseline, failures)
    observed_summary = _observed_summary(result, failures)
    expected_summary = baseline["summary"]
    tolerances = baseline["tolerances"]
    for field in _SUMMARY_FIELDS:
        actual = observed_summary[field]
        expected = expected_summary[field]
        if field in _FLOAT_FIELDS:
            tolerance = float(tolerances[field])
            if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=tolerance):
                failures.append(
                    f"acceptance mismatch for {field}: expected {expected!r}, got {actual!r}"
                )
        elif actual != expected:
            failures.append(
                f"acceptance mismatch for {field}: expected {expected!r}, got {actual!r}"
            )

    _validate_account_safety(result, config, failures)
    observed_artifacts = _artifact_evidence(result, failures)
    if observed_artifacts != baseline["artifact_evidence"]:
        failures.append(
            "acceptance mismatch for artifact_evidence: expected "
            f"{baseline['artifact_evidence']!r}, got {observed_artifacts!r}"
        )

    callback = get_strategy_acceptance_callback(strategy_id)
    try:
        failures.extend(callback(result, baseline))
    except (TypeError, ValueError, OverflowError) as exc:
        failures.append(f"strategy acceptance callback failed closed: {exc}")

    if failures:
        raise ValueError("; ".join(failures))
    return {
        "status": "success",
        "strategy_id": strategy_id,
        "profile": profile,
        "observed": {
            "summary": observed_summary,
            "publication_identity": expected_identity,
            "artifact_evidence": observed_artifacts,
        },
    }


def build_candidate(
    result: Mapping[str, Any],
    *,
    template: Mapping[str, Any],
) -> dict[str, Any]:
    """Build an unapproved candidate without changing the approved baseline file."""

    strategy_id = str(template["strategy_id"])
    profile = str(template["profile"])
    contract = get_publication_contract(strategy_id, profile)
    failures: list[str] = []
    summary = _observed_summary(result, failures)
    artifacts = _artifact_evidence(result, failures)
    candidate = {
        "strategy_id": strategy_id,
        "profile": profile,
        "baseline_start_date": str(template["baseline_start_date"]),
        "baseline_end_date": str(template["baseline_end_date"]),
        "summary": summary,
        "tolerances": {
            "total_return": 1e-10,
            "max_drawdown": 1e-10,
        },
        "acceptance_profile": contract.acceptance_profile,
        "publication_identity": build_publication_identity(contract),
        "artifact_evidence": artifacts,
    }
    _validate_dates(
        result.get("config") if isinstance(result.get("config"), Mapping) else {},
        result.get("summary") if isinstance(result.get("summary"), Mapping) else {},
        candidate,
        failures,
    )
    _validate_account_safety(
        result,
        result.get("config") if isinstance(result.get("config"), Mapping) else {},
        failures,
    )
    expected_identity = candidate["publication_identity"]
    for location, identity in (
        ("result", result.get("publication_identity")),
        (
            "summary",
            result.get("summary", {}).get("publication_identity")
            if isinstance(result.get("summary"), Mapping)
            else None,
        ),
    ):
        if not isinstance(identity, Mapping):
            failures.append(f"{location} publication_identity missing or malformed")
        else:
            for mismatch in validate_publication_identity(identity, expected_identity):
                failures.append(f"{location} publication_identity.{mismatch['field']} mismatch")
    try:
        failures.extend(get_strategy_acceptance_callback(strategy_id)(result, candidate))
    except (TypeError, ValueError, OverflowError) as exc:
        failures.append(f"strategy acceptance callback failed closed: {exc}")
    if failures:
        raise ValueError("; ".join(failures))
    return candidate


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    baselines = load_baselines(args.baseline_path)
    by_key = {(row["strategy_id"], row["profile"]): row for row in baselines}
    contracts = [
        contract
        for contract in iter_publication_contracts()
        if contract.profile == args.profile
        and (args.all or contract.strategy_id == args.strategy_id)
    ]
    if not contracts:
        raise ValueError(f"no registered strategy selected for profile {args.profile!r}")

    reports: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for contract in contracts:
        key = (contract.strategy_id, contract.profile)
        baseline = by_key.get(key)
        if baseline is None:
            raise ValueError(f"approved baseline missing: {key[0]}/{key[1]}")
        result = run_fresh_backtest(_fresh_payload(contract, baseline))
        if args.emit_candidates:
            candidates.append(build_candidate(result, template=baseline))
        else:
            reports.append(validate_result(result, baseline=baseline))

    if args.emit_candidates:
        _write_json_exclusive(
            Path(args.emit_candidates),
            {"schema_version": BASELINE_SCHEMA_VERSION, "baselines": candidates},
        )
        reports = [
            {"status": "candidate_emitted", "strategy_id": row["strategy_id"], "profile": row["profile"]}
            for row in candidates
        ]
    report = {
        "status": "success",
        "validated_count": len(reports),
        "items": reports,
    }
    if args.output:
        _write_json(Path(args.output), report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


def _validate_baseline_schema(baseline: Mapping[str, Any]) -> None:
    required = {
        "strategy_id",
        "profile",
        "baseline_start_date",
        "baseline_end_date",
        "summary",
        "tolerances",
        "acceptance_profile",
        "publication_identity",
        "artifact_evidence",
    }
    missing = sorted(required - set(baseline))
    if missing:
        raise ValueError(f"baseline malformed: missing {', '.join(missing)}")
    if not all(isinstance(baseline[field], str) and baseline[field] for field in (
        "strategy_id", "profile", "baseline_start_date", "baseline_end_date", "acceptance_profile"
    )):
        raise ValueError("baseline malformed: identity and date fields must be non-empty strings")
    summary = baseline["summary"]
    tolerances = baseline["tolerances"]
    if not isinstance(summary, Mapping) or set(summary) != set(_SUMMARY_FIELDS):
        raise ValueError("baseline malformed: summary fields are incomplete or mixed")
    if not isinstance(tolerances, Mapping) or set(tolerances) != set(_FLOAT_FIELDS):
        raise ValueError("baseline malformed: tolerances fields are incomplete or mixed")
    for field in _FLOAT_FIELDS:
        _finite_number(summary[field], f"baseline {field}")
        tolerance = _finite_number(tolerances[field], f"baseline tolerance {field}")
        if tolerance < 0 or tolerance > 1e-6:
            raise ValueError(f"baseline malformed: tolerance for {field} is not tight")
    for field in ("filled_trade_count", "cash_slot_count"):
        if isinstance(summary[field], bool) or not isinstance(summary[field], int) or summary[field] < 0:
            raise ValueError(f"baseline malformed: {field} must be a non-negative integer")
    identity = baseline["publication_identity"]
    if not isinstance(identity, Mapping):
        raise ValueError("baseline malformed: publication_identity must be a mapping")
    _validate_artifact_schema(baseline["artifact_evidence"])


def _validate_artifact_schema(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError("baseline malformed: artifact evidence missing")
    names: set[str] = set()
    for row in value:
        if not isinstance(row, Mapping) or set(row) != {"name", "sha256", "record_count"}:
            raise ValueError(
                "baseline malformed: artifact evidence row must contain name, sha256, and record_count"
            )
        name = row["name"]
        digest = row["sha256"]
        record_count = row["record_count"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("baseline malformed: artifact evidence names must be unique")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            raise ValueError("baseline malformed: malformed artifact sha256")
        if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count <= 0:
            raise ValueError("baseline malformed: artifact record_count must be a positive integer")
        names.add(name)


def _validate_dates(
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    baseline: Mapping[str, Any],
    failures: list[str],
) -> None:
    for field in ("start_date", "end_date"):
        expected = baseline[f"baseline_{field}"]
        if config.get(field) != expected:
            failures.append(f"baseline_{field} expected {expected!r}, got config {config.get(field)!r}")
        aliases = (field, f"requested_{field}")
        declared = [summary[name] for name in aliases if summary.get(name) is not None]
        if any(str(value) != expected for value in declared):
            failures.append(f"baseline_{field} expected {expected!r}, got summary {declared!r}")


def _observed_summary(result: Mapping[str, Any], failures: list[str]) -> dict[str, Any]:
    summary = result.get("summary")
    if not isinstance(summary, Mapping):
        failures.append("summary missing or malformed")
        summary = {}
    observed: dict[str, Any] = {}
    for field in _FLOAT_FIELDS:
        try:
            observed[field] = _finite_number(summary.get(field), field)
        except ValueError as exc:
            failures.append(str(exc))
            observed[field] = 0.0
    observed["filled_trade_count"] = _count_filled_trades(result, summary, failures)
    observed["cash_slot_count"] = _count_cash_slots(result, summary, failures)
    return observed


def _count_filled_trades(
    result: Mapping[str, Any],
    summary: Mapping[str, Any],
    failures: list[str],
) -> int:
    declared = summary.get("filled_trade_count")
    if declared is not None:
        return _non_negative_int(declared, "filled_trade_count", failures)
    trades = result.get("trades")
    if not isinstance(trades, list):
        failures.append("trades missing or malformed")
        return 0
    status_fields = ("account_trade_status", "fill_status", "status")
    statuses = [
        str(row[field]).lower()
        for row in trades
        if isinstance(row, Mapping)
        for field in status_fields
        if row.get(field) is not None
    ]
    if statuses:
        return sum(status == "filled" for status in statuses)
    return len(trades)


def _count_cash_slots(
    result: Mapping[str, Any],
    summary: Mapping[str, Any],
    failures: list[str],
) -> int:
    declared = summary.get("cash_slot_count")
    if declared is not None:
        return _non_negative_int(declared, "cash_slot_count", failures)
    trades = result.get("trades")
    if not isinstance(trades, list):
        return 0
    return sum(
        str(row.get("account_trade_status", "")).lower() == "cash_skipped"
        or row.get("is_cash_slot") is True
        for row in trades
        if isinstance(row, Mapping)
    )


def _non_negative_int(value: Any, field: str, failures: list[str]) -> int:
    if isinstance(value, bool):
        failures.append(f"{field} must be a non-negative integer")
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        failures.append(f"{field} must be a non-negative integer")
        return 0
    if parsed < 0 or parsed != float(value):
        failures.append(f"{field} must be a non-negative integer")
        return 0
    return parsed


def _validate_account_safety(
    result: Mapping[str, Any],
    config: Mapping[str, Any],
    failures: list[str],
) -> None:
    summary = result.get("summary")
    if isinstance(summary, Mapping):
        try:
            if _finite_number(summary.get("total_return"), "total_return") <= -1.0:
                failures.append("account safety: total_return implies loss beyond account equity")
        except ValueError as exc:
            failures.append(f"account safety: {exc}")
        try:
            drawdown = _finite_number(summary.get("max_drawdown"), "max_drawdown")
            if drawdown < -1.0 or drawdown > 0.0:
                failures.append("account safety: max_drawdown must be between -1 and 0")
        except ValueError as exc:
            failures.append(f"account safety: {exc}")
    equity_curve = result.get("equity_curve")
    if not isinstance(equity_curve, list) or not equity_curve:
        failures.append("account safety: equity_curve missing or empty")
        return
    top_n = config.get("top_n")
    max_positions = config.get("max_positions") or top_n
    for index, row in enumerate(equity_curve):
        if not isinstance(row, Mapping):
            failures.append(f"account safety: equity row {index} malformed")
            continue
        if row.get("equity") is not None:
            try:
                equity = _finite_number(row["equity"], f"equity row {index}")
                if equity <= 0:
                    failures.append(f"account safety: equity row {index} is non-positive")
            except ValueError as exc:
                failures.append(f"account safety: {exc}")
        if row.get("cash") is not None:
            try:
                if _finite_number(row["cash"], f"cash row {index}") < -1e-12:
                    failures.append(f"account safety: negative cash at row {index}")
            except ValueError as exc:
                failures.append(f"account safety: {exc}")
        count = row.get("open_position_count")
        if count is not None and max_positions is not None:
            try:
                if int(count) > int(max_positions):
                    failures.append(f"account safety: max positions exceeded at row {index}")
            except (TypeError, ValueError, OverflowError):
                failures.append(f"account safety: open_position_count malformed at row {index}")


def _artifact_evidence(result: Mapping[str, Any], failures: list[str]) -> list[dict[str, Any]]:
    declared = result.get("artifact_evidence")
    if declared is not None:
        try:
            normalized = [dict(row) for row in declared]
            _validate_artifact_schema(normalized)
            return sorted(normalized, key=lambda row: row["name"])
        except (TypeError, ValueError) as exc:
            failures.append(f"artifact evidence malformed: {exc}")
            return []
    paths = result.get("source_artifacts")
    if paths is None:
        paths = result.get("source_paths")
    if paths is None:
        return _hash_result_artifacts(result, failures)
    if not isinstance(paths, list) or not paths:
        failures.append("artifact evidence missing")
        return []
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_path in paths:
        if not isinstance(raw_path, str) or not raw_path:
            failures.append("artifact evidence contains a malformed path")
            continue
        path = _resolve_artifact_path(raw_path)
        name = path.name
        if name in seen:
            failures.append(f"artifact evidence contains mixed duplicate name: {name}")
            continue
        try:
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            record_count = _file_record_count(path)
        except OSError as exc:
            failures.append(f"artifact evidence unreadable: {raw_path}: {exc}")
            continue
        except (csv.Error, json.JSONDecodeError, ValueError) as exc:
            failures.append(f"artifact evidence malformed: {raw_path}: {exc}")
            continue
        seen.add(name)
        evidence.append({"name": name, "sha256": digest, "record_count": record_count})
    return sorted(evidence, key=lambda row: row["name"])


def _hash_result_artifacts(
    result: Mapping[str, Any],
    failures: list[str],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for name in ("equity_curve", "positions", "trades"):
        records = result.get(name)
        if not isinstance(records, list):
            failures.append(f"artifact evidence missing: {name}")
            continue
        if not records:
            failures.append(f"artifact evidence {name} is empty")
            continue
        payload = json.dumps(
            records,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        evidence.append(
            {
                "name": f"{name}.json",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "record_count": len(records),
            }
        )
    return evidence


def _file_record_count(path: Path) -> int:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            count = sum(1 for _row in csv.reader(handle)) - 1
    elif suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        count = len(payload) if isinstance(payload, list) else 1
    else:
        raise ValueError(f"unsupported artifact format: {suffix or '<none>'}")
    if count <= 0:
        raise ValueError("artifact contains no records")
    return count


def _resolve_artifact_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute() or path.exists():
        return path
    repository_root = Path(__file__).resolve().parents[1]
    primary_checkout = repository_root
    if ".worktrees" in repository_root.parts:
        primary_checkout = Path(*repository_root.parts[: repository_root.parts.index(".worktrees")])
    candidate = primary_checkout / path
    return candidate if candidate.exists() else path


def _fresh_payload(contract: Any, baseline: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "strategy_id": contract.strategy_id,
        "start_date": baseline["baseline_start_date"],
        "end_date": baseline["baseline_end_date"],
        **_plain_mapping(contract.normalized_run_config),
    }


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    def thaw(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): thaw(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [thaw(child) for child in item]
        return item

    return thaw(value)


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"finite metric required for {field}")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"finite metric required for {field}") from exc
    if not math.isfinite(number):
        raise ValueError(f"finite metric required for {field}")
    return number


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"candidate output already exists: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
