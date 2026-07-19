#!/usr/bin/env python3
"""Validate fixed-date fresh replays for every official strategy publication."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import tempfile
from datetime import date
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
    _validate_contract_and_identity(
        result,
        baseline=baseline,
        contract=contract,
        expected_identity=expected_identity,
        failures=failures,
    )
    observed_artifacts, audited_records = _audit_artifact_files(
        result,
        expected=baseline["artifact_evidence"],
        failures=failures,
    )
    audited_result = _with_audited_records(result, audited_records)
    summary = audited_result.get("summary") if isinstance(audited_result.get("summary"), Mapping) else {}
    config = audited_result.get("config") if isinstance(audited_result.get("config"), Mapping) else {}
    _validate_dates(config, summary, baseline, audited_result.get("equity_curve"), failures)
    observed_summary = _observed_summary(audited_result, failures)
    _validate_summary_against_baseline(observed_summary, baseline, failures)
    derived_metrics = _validate_account_safety(
        audited_result,
        config,
        tolerances=baseline["tolerances"],
        failures=failures,
    )
    _validate_evidence_date_bounds(audited_result, baseline, failures)
    _validate_holdings_reconciliation(strategy_id, audited_result, failures)
    _run_strategy_callback(strategy_id, audited_result, baseline, failures)
    if failures:
        raise ValueError("; ".join(failures))
    return {
        "status": "success",
        "strategy_id": strategy_id,
        "profile": profile,
        "observed": {
            "summary": observed_summary,
            "equity_metrics": derived_metrics,
            "publication_identity": expected_identity,
            "artifact_evidence": observed_artifacts,
            "actual_start_date": baseline["actual_start_date"],
            "actual_end_date": baseline["actual_end_date"],
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
    expected_identity = build_publication_identity(contract)
    failures: list[str] = []
    artifacts, audited_records = _audit_artifact_files(result, expected=None, failures=failures)
    audited_result = _with_audited_records(result, audited_records)
    summary = _observed_summary(audited_result, failures)
    actual_start_date, actual_end_date = _curve_boundaries(
        audited_result.get("equity_curve"),
        failures,
    )
    candidate = {
        "strategy_id": strategy_id,
        "profile": profile,
        "baseline_start_date": str(template["baseline_start_date"]),
        "baseline_end_date": str(template["baseline_end_date"]),
        "actual_start_date": actual_start_date,
        "actual_end_date": actual_end_date,
        "summary": summary,
        "tolerances": {
            "total_return": 1e-10,
            "max_drawdown": 1e-10,
        },
        "acceptance_profile": contract.acceptance_profile,
        "publication_identity": expected_identity,
        "artifact_evidence": artifacts,
    }
    _validate_contract_and_identity(
        audited_result,
        baseline=candidate,
        contract=contract,
        expected_identity=expected_identity,
        failures=failures,
    )
    config = audited_result.get("config") if isinstance(audited_result.get("config"), Mapping) else {}
    declared_summary = (
        audited_result.get("summary") if isinstance(audited_result.get("summary"), Mapping) else {}
    )
    _validate_dates(config, declared_summary, candidate, audited_result.get("equity_curve"), failures)
    _validate_account_safety(
        audited_result,
        config,
        tolerances=candidate["tolerances"],
        failures=failures,
    )
    _validate_evidence_date_bounds(audited_result, candidate, failures)
    _validate_holdings_reconciliation(strategy_id, audited_result, failures)
    _run_strategy_callback(strategy_id, audited_result, candidate, failures)
    if failures:
        raise ValueError("; ".join(failures))
    return candidate


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
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
        with tempfile.TemporaryDirectory(prefix="strategy-publication-acceptance-") as temp_root:
            for contract in contracts:
                key = (contract.strategy_id, contract.profile)
                baseline = by_key.get(key)
                if baseline is None:
                    raise ValueError(f"approved baseline missing: {key[0]}/{key[1]}")
                result = run_fresh_backtest(_fresh_payload(contract, baseline))
                prepared = materialize_result_artifacts(
                    result,
                    template=baseline,
                    output_dir=Path(temp_root) / contract.strategy_id / contract.profile,
                )
                if args.emit_candidates:
                    candidates.append(build_candidate(prepared, template=baseline))
                else:
                    reports.append(validate_result(prepared, baseline=baseline))

        if args.emit_candidates:
            _write_json_exclusive(
                Path(args.emit_candidates),
                {"schema_version": BASELINE_SCHEMA_VERSION, "baselines": candidates},
            )
            reports = [
                {
                    "status": "candidate_emitted",
                    "strategy_id": row["strategy_id"],
                    "profile": row["profile"],
                }
                for row in candidates
            ]
        report = {"status": "success", "validated_count": len(reports), "items": reports}
        if args.output:
            _write_json(Path(args.output), report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        report = {
            "status": "failed",
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
        if args.output:
            _write_json(Path(args.output), report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1


def materialize_result_artifacts(
    result: Mapping[str, Any],
    *,
    template: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Persist authoritative in-memory collections for byte-level acceptance auditing."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifact_files: dict[str, str] = {}
    materialized_records: dict[str, list[dict[str, Any]]] = {}
    for field in ("equity_curve", "positions", "trades"):
        records = _require_record_collection(result.get(field), field)
        materialized_records[field] = records
        name = f"{field}.json"
        path = output / name
        _write_canonical_records(path, records)
        artifact_files[name] = str(path)

    if str(template.get("strategy_id")) == "lhb_shortline":
        candidates = _require_record_collection(result.get("candidates"), "candidates")
        candidate_name = "candidates.json"
        candidate_path = output / candidate_name
        _write_canonical_records(candidate_path, candidates)
        artifact_files[candidate_name] = str(candidate_path)
        rejected = _load_lhb_rejected_top5(result, template=template)
        name = "lhb_rejected_top5.json"
        path = output / name
        _write_canonical_records(path, rejected)
        artifact_files[name] = str(path)

    prepared = dict(result)
    summary = dict(prepared.get("summary") or {})
    date_failures: list[str] = []
    actual_start, actual_end = _curve_boundaries(
        materialized_records["equity_curve"],
        date_failures,
    )
    if date_failures:
        raise ValueError("; ".join(date_failures))
    summary.setdefault("actual_start_date", actual_start)
    summary.setdefault("actual_end_date", actual_end)
    prepared["summary"] = summary
    prepared["artifact_files"] = artifact_files
    return prepared


def _require_record_collection(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} artifact missing or empty")
    records: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping):
            raise ValueError(f"{field} artifact contains malformed row {index}")
        records.append(dict(row))
    return records


def _load_lhb_rejected_top5(
    result: Mapping[str, Any],
    *,
    template: Mapping[str, Any],
) -> list[dict[str, Any]]:
    artifacts = result.get("artifacts")
    raw_path = (
        artifacts.get("pipeline_selected_rejected_trades")
        if isinstance(artifacts, Mapping)
        else None
    )
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("LHB rejected Top5 artifact path missing")
    path = _resolve_artifact_path(raw_path)
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except (OSError, csv.Error) as exc:
        raise ValueError(f"LHB rejected Top5 artifact unreadable: {raw_path}: {exc}") from exc
    start = _parse_date(template.get("baseline_start_date"), "baseline_start_date")
    end = _parse_date(template.get("baseline_end_date"), "baseline_end_date")
    rejected: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"LHB rejected Top5 artifact malformed row {index}")
        try:
            trade_date = _parse_date(row.get("trade_date"), "LHB rejected trade_date")
            top_n = int(str(row.get("top_n") or ""))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"LHB rejected Top5 artifact malformed row {index}: {exc}") from exc
        if row.get("strategy") != "auction_enhanced_rerank" or top_n != 5:
            continue
        if not start <= trade_date <= end:
            continue
        normalized = dict(row)
        normalized["top_n"] = top_n
        normalized["phase18c_selection_rank"] = int(
            str(row.get("phase18c_selection_rank") or "")
        )
        normalized["backtest_entry_eligible"] = _parse_bool(
            row.get("backtest_entry_eligible"),
            "backtest_entry_eligible",
        )
        normalized["top5_eligible"] = _parse_bool(
            row.get("top5_eligible"),
            "top5_eligible",
        )
        if "research_only" in row and str(row.get("research_only") or "").strip():
            normalized["research_only"] = _parse_bool(row.get("research_only"), "research_only")
        rejected.append(normalized)
    if not rejected:
        raise ValueError("LHB rejected Top5 artifact contains no fixed-window rows")
    return rejected


def _parse_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"{field} must be boolean")


def _write_canonical_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(
            records,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
        encoding="utf-8",
    )


def _audit_artifact_files(
    result: Mapping[str, Any],
    *,
    expected: Any,
    failures: list[str],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    artifact_files = result.get("artifact_files")
    if not isinstance(artifact_files, Mapping) or not artifact_files:
        failures.append("artifact files missing; declared artifact_evidence is not authoritative")
        return [], {}
    expected_names = (
        {str(row.get("name")) for row in expected if isinstance(row, Mapping)}
        if isinstance(expected, list)
        else set(artifact_files)
    )
    actual_names = {str(name) for name in artifact_files}
    if actual_names != expected_names:
        failures.append(
            f"artifact files mixed: expected {sorted(expected_names)!r}, got {sorted(actual_names)!r}"
        )
    evidence: list[dict[str, Any]] = []
    records_by_name: dict[str, list[dict[str, Any]]] = {}
    resolved_paths: set[Path] = set()
    for name in sorted(actual_names):
        raw_path = artifact_files.get(name)
        if not isinstance(raw_path, str) or not raw_path:
            failures.append(f"artifact file path malformed: {name}")
            continue
        path = Path(raw_path)
        try:
            resolved = path.resolve(strict=True)
            if resolved in resolved_paths or not resolved.is_file() or path.is_symlink():
                raise ValueError("path is duplicate, non-regular, or symlinked")
            content = resolved.read_bytes()
            payload = json.loads(content)
            records = _require_record_collection(payload, name)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            failures.append(f"artifact file unreadable or malformed: {name}: {exc}")
            continue
        resolved_paths.add(resolved)
        records_by_name[name] = records
        evidence.append(
            {
                "name": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "record_count": len(records),
            }
        )
    if expected is not None and evidence != expected:
        failures.append(
            f"acceptance mismatch for artifact_evidence: expected {expected!r}, got {evidence!r}"
        )
    return evidence, records_by_name


def _with_audited_records(
    result: Mapping[str, Any],
    records: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    audited = dict(result)
    for field in ("equity_curve", "positions", "trades"):
        audited[field] = records.get(f"{field}.json", [])
    if "candidates.json" in records:
        audited["candidates"] = records["candidates.json"]
    evidence = dict(audited.get("acceptance_evidence") or {})
    if "lhb_rejected_top5.json" in records:
        evidence["lhb_rejected_top5"] = records["lhb_rejected_top5.json"]
    audited["acceptance_evidence"] = evidence
    return audited


def _validate_contract_and_identity(
    result: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any],
    contract: Any,
    expected_identity: Mapping[str, Any],
    failures: list[str],
) -> None:
    if baseline.get("acceptance_profile") != contract.acceptance_profile:
        failures.append(
            "acceptance_profile expected "
            f"{contract.acceptance_profile!r}, got {baseline.get('acceptance_profile')!r}"
        )
    baseline_identity = baseline.get("publication_identity")
    if not isinstance(baseline_identity, Mapping):
        failures.append("baseline publication_identity missing or malformed")
    else:
        failures.extend(
            f"baseline publication_identity.{row['field']} mismatch"
            for row in validate_publication_identity(baseline_identity, expected_identity)
        )
    if result.get("strategy_id") != contract.strategy_id:
        failures.append(
            f"strategy_id expected {contract.strategy_id!r}, got {result.get('strategy_id')!r}"
        )
    summary = result.get("summary") if isinstance(result.get("summary"), Mapping) else {}
    for location, identity in (
        ("result", result.get("publication_identity")),
        ("summary", summary.get("publication_identity")),
    ):
        if not isinstance(identity, Mapping):
            failures.append(f"{location} publication_identity missing or malformed")
            continue
        failures.extend(
            f"{location} publication_identity.{row['field']} acceptance mismatch"
            for row in validate_publication_identity(identity, expected_identity)
        )


def _validate_summary_against_baseline(
    observed: Mapping[str, Any],
    baseline: Mapping[str, Any],
    failures: list[str],
) -> None:
    expected_summary = baseline["summary"]
    tolerances = baseline["tolerances"]
    for field in _SUMMARY_FIELDS:
        actual = observed[field]
        expected = expected_summary[field]
        if field in _FLOAT_FIELDS:
            if not math.isclose(
                float(actual),
                float(expected),
                rel_tol=0.0,
                abs_tol=float(tolerances[field]),
            ):
                failures.append(
                    f"acceptance mismatch for {field}: expected {expected!r}, got {actual!r}"
                )
        elif actual != expected:
            failures.append(
                f"acceptance mismatch for {field}: expected {expected!r}, got {actual!r}"
            )


def _run_strategy_callback(
    strategy_id: str,
    result: Mapping[str, Any],
    baseline: Mapping[str, Any],
    failures: list[str],
) -> None:
    try:
        failures.extend(get_strategy_acceptance_callback(strategy_id)(result, baseline))
    except (TypeError, ValueError, OverflowError) as exc:
        failures.append(f"strategy acceptance callback failed closed: {exc}")


def _validate_baseline_schema(baseline: Mapping[str, Any]) -> None:
    required = {
        "strategy_id",
        "profile",
        "baseline_start_date",
        "baseline_end_date",
        "actual_start_date",
        "actual_end_date",
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
        "strategy_id",
        "profile",
        "baseline_start_date",
        "baseline_end_date",
        "actual_start_date",
        "actual_end_date",
        "acceptance_profile",
    )):
        raise ValueError("baseline malformed: identity and date fields must be non-empty strings")
    requested_start = _parse_date(baseline["baseline_start_date"], "baseline_start_date")
    requested_end = _parse_date(baseline["baseline_end_date"], "baseline_end_date")
    actual_start = _parse_date(baseline["actual_start_date"], "actual_start_date")
    actual_end = _parse_date(baseline["actual_end_date"], "actual_end_date")
    if not requested_start <= actual_start <= actual_end <= requested_end:
        raise ValueError("baseline malformed: actual replay dates fall outside requested dates")
    if actual_end != requested_end:
        raise ValueError("baseline malformed: actual_end_date must equal approved baseline_end_date")
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
    equity_curve: Any,
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
    try:
        requested_start = _parse_date(baseline.get("baseline_start_date"), "baseline_start_date")
        requested_end = _parse_date(baseline.get("baseline_end_date"), "baseline_end_date")
        expected_actual_start = _parse_date(baseline.get("actual_start_date"), "actual_start_date")
        expected_actual_end = _parse_date(baseline.get("actual_end_date"), "actual_end_date")
    except ValueError as exc:
        failures.append(str(exc))
        return
    declared_actual: dict[str, date] = {}
    for field in ("actual_start_date", "actual_end_date"):
        try:
            declared_actual[field] = _parse_date(summary.get(field), field)
        except ValueError:
            failures.append(f"{field} must be present and parseable")
    if declared_actual.get("actual_start_date") != expected_actual_start:
        failures.append(
            f"actual_start_date expected {expected_actual_start.isoformat()!r}, "
            f"got {summary.get('actual_start_date')!r}"
        )
    if declared_actual.get("actual_end_date") != expected_actual_end:
        failures.append(
            f"actual_end_date expected {expected_actual_end.isoformat()!r}, "
            f"got {summary.get('actual_end_date')!r}"
        )
    if not requested_start <= expected_actual_start <= expected_actual_end <= requested_end:
        failures.append("actual replay date ordering falls outside requested baseline dates")
    if expected_actual_end != requested_end:
        failures.append("actual_end_date must equal approved baseline_end_date trading boundary")
    curve_start, curve_end = _curve_boundaries(equity_curve, failures)
    if curve_start and curve_start != expected_actual_start.isoformat():
        failures.append(
            f"curve actual start {curve_start!r} does not match actual_start_date "
            f"{expected_actual_start.isoformat()!r}"
        )
    if curve_end and curve_end != expected_actual_end.isoformat():
        failures.append(
            f"curve actual end {curve_end!r} does not match actual_end_date "
            f"{expected_actual_end.isoformat()!r}"
        )
    if curve_start and _parse_date(curve_start, "curve start") < requested_start:
        failures.append("curve actual start precedes baseline_start_date")


def _curve_boundaries(
    equity_curve: Any,
    failures: list[str],
) -> tuple[str, str]:
    if not isinstance(equity_curve, list) or not equity_curve:
        failures.append("equity curve missing or empty for actual date validation")
        return "", ""
    parsed_dates: list[date] = []
    for index, row in enumerate(equity_curve):
        if not isinstance(row, Mapping):
            failures.append(f"equity curve row {index} malformed")
            continue
        raw_date = row.get("trade_date") or row.get("date")
        try:
            parsed_dates.append(_parse_date(raw_date, f"equity curve row {index} date"))
        except ValueError as exc:
            failures.append(str(exc))
    if len(parsed_dates) != len(equity_curve):
        return "", ""
    if parsed_dates != sorted(parsed_dates) or len(set(parsed_dates)) != len(parsed_dates):
        failures.append("equity curve dates must be strictly increasing")
    return parsed_dates[0].isoformat(), parsed_dates[-1].isoformat()


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be present and parseable")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be parseable ISO date") from exc


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
    *,
    tolerances: Mapping[str, Any],
    failures: list[str],
) -> dict[str, float]:
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
        return {"total_return": 0.0, "max_drawdown": 0.0}
    top_n = config.get("top_n")
    max_positions = config.get("max_positions") or top_n
    equities: list[float] = []
    for index, row in enumerate(equity_curve):
        if not isinstance(row, Mapping):
            failures.append(f"account safety: equity row {index} malformed")
            continue
        try:
            equity = _finite_number(row.get("equity"), f"equity row {index}")
            equities.append(equity)
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
        count_fields = [
            field for field in ("open_position_count", "holdings_count") if field in row
        ]
        if not count_fields:
            failures.append(f"account safety: position count missing at equity row {index}")
        for field in count_fields:
            count = _integral_count(row.get(field), field, index, failures)
            if count is not None and max_positions is not None and count > int(max_positions):
                failures.append(f"account safety: max positions exceeded at row {index}")
    if len(equities) != len(equity_curve) or not equities:
        return {"total_return": 0.0, "max_drawdown": 0.0}
    initial_equity = equities[0]
    derived_total_return = equities[-1] / initial_equity - 1.0
    running_max = equities[0]
    derived_max_drawdown = 0.0
    for equity in equities:
        running_max = max(running_max, equity)
        derived_max_drawdown = min(derived_max_drawdown, equity / running_max - 1.0)
    if isinstance(summary, Mapping):
        for field, derived in (
            ("total_return", derived_total_return),
            ("max_drawdown", derived_max_drawdown),
        ):
            try:
                declared = _finite_number(summary.get(field), field)
                if not math.isclose(
                    declared,
                    derived,
                    rel_tol=0.0,
                    abs_tol=float(tolerances[field]),
                ):
                    failures.append(
                        f"equity curve {field} mismatch: summary {declared!r}, derived {derived!r}"
                    )
            except ValueError as exc:
                failures.append(str(exc))
    return {
        "total_return": derived_total_return,
        "max_drawdown": derived_max_drawdown,
    }


def _integral_count(
    value: Any,
    field: str,
    index: int,
    failures: list[str],
) -> int | None:
    if isinstance(value, bool):
        failures.append(f"account safety: {field} at row {index} must be non-negative integral")
        return None
    try:
        parsed = int(value)
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        failures.append(f"account safety: {field} at row {index} must be non-negative integral")
        return None
    if parsed < 0 or parsed != numeric:
        failures.append(f"account safety: {field} at row {index} must be non-negative integral")
        return None
    return parsed


def _validate_evidence_date_bounds(
    result: Mapping[str, Any],
    baseline: Mapping[str, Any],
    failures: list[str],
) -> None:
    try:
        requested_start = _parse_date(baseline.get("baseline_start_date"), "baseline_start_date")
        requested_end = _parse_date(baseline.get("baseline_end_date"), "baseline_end_date")
        actual_end = _parse_date(baseline.get("actual_end_date"), "actual_end_date")
    except ValueError as exc:
        failures.append(str(exc))
        return
    for collection, date_fields in (
        ("positions", ("rebalance_date", "trade_date", "date")),
        ("trades", ("trade_date",)),
    ):
        rows = result.get(collection)
        if not isinstance(rows, list) or not rows:
            failures.append(f"{collection} missing or empty for replay date bounds")
            continue
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                failures.append(f"{collection} row {index} malformed for replay date bounds")
                continue
            present_fields = [field for field in date_fields if row.get(field) not in (None, "")]
            if not present_fields:
                failures.append(f"{collection} row {index} action date missing")
                continue
            for field in present_fields:
                try:
                    action_date = _parse_date(
                        row.get(field),
                        f"{collection} row {index} {field}",
                    )
                except ValueError as exc:
                    failures.append(str(exc))
                    continue
                if not requested_start <= action_date <= requested_end:
                    failures.append(
                        f"{collection} row {index} {field} outside requested replay window: "
                        f"{action_date.isoformat()}"
                    )
                if action_date > actual_end:
                    failures.append(
                        f"{collection} row {index} {field} is later than actual curve end: "
                        f"{action_date.isoformat()}"
                    )


def _validate_holdings_reconciliation(
    strategy_id: str,
    result: Mapping[str, Any],
    failures: list[str],
) -> None:
    if strategy_id not in {"mid_trend", "tech_bottleneck"}:
        return
    equity = _require_audited_rows(result.get("equity_curve"), "equity_curve", failures)
    positions = _require_audited_rows(result.get("positions"), "positions", failures)
    trades = _require_audited_rows(result.get("trades"), "trades", failures)
    if not equity or not positions or not trades:
        return

    trade_events: dict[date, list[Mapping[str, Any]]] = {}
    for index, row in enumerate(trades):
        try:
            event_date = _parse_date(row.get("trade_date"), f"trades row {index} trade_date")
            asset_id = str(row.get("asset_id") or "")
            target_weight = _finite_number(row.get("target_weight"), f"trades row {index} target_weight")
            if not asset_id or target_weight < 0:
                raise ValueError("asset_id missing or target_weight negative")
        except ValueError as exc:
            failures.append(f"holdings reconciliation: {exc}")
            continue
        trade_events.setdefault(event_date, []).append(row)

    position_snapshots: dict[date, set[str]] = {}
    for index, row in enumerate(positions):
        raw_date = row.get("rebalance_date") or row.get("trade_date")
        try:
            snapshot_date = _parse_date(raw_date, f"positions row {index} date")
            asset_id = str(row.get("asset_id") or "")
            weight = _finite_number(row.get("weight"), f"positions row {index} weight")
            if not asset_id or weight <= 0:
                raise ValueError("asset_id missing or weight non-positive")
        except ValueError as exc:
            failures.append(f"holdings reconciliation: {exc}")
            continue
        position_snapshots.setdefault(snapshot_date, set()).add(asset_id)

    action_dates = sorted(set(trade_events) | set(position_snapshots))
    state: dict[str, float] = {}
    action_index = 0
    for curve_index, row in enumerate(equity):
        raw_date = row.get("trade_date") or row.get("date")
        try:
            curve_date = _parse_date(raw_date, f"equity row {curve_index} date")
        except ValueError as exc:
            failures.append(f"holdings reconciliation: {exc}")
            continue
        while action_index < len(action_dates):
            action_date = action_dates[action_index]
            applies = action_date <= curve_date if strategy_id == "mid_trend" else action_date < curve_date
            if not applies:
                break
            for event in trade_events.get(action_date, []):
                asset_id = str(event["asset_id"])
                target_weight = float(event["target_weight"])
                if target_weight > 1e-12:
                    state[asset_id] = target_weight
                else:
                    state.pop(asset_id, None)
            if action_date in position_snapshots:
                state = {asset_id: 1.0 for asset_id in position_snapshots[action_date]}
            action_index += 1
        count = _integral_count(
            row.get("holdings_count"),
            "holdings_count",
            curve_index,
            failures,
        )
        if count is not None and count != len(state):
            failures.append(
                f"holdings_count does not reconcile at {curve_date.isoformat()}: "
                f"curve={count}, replayed={len(state)}"
            )
        if len(state) > 5:
            failures.append(f"holdings reconciliation exceeds Top5 at {curve_date.isoformat()}")


def _require_audited_rows(
    value: Any,
    field: str,
    failures: list[str],
) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        failures.append(f"{field} missing or empty")
        return []
    if any(not isinstance(row, Mapping) for row in value):
        failures.append(f"{field} contains malformed or mixed rows")
        return []
    return list(value)


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
