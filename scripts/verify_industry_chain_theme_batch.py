#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ARTIFACT_KEYS = (
    "theme",
    "company_mapping",
    "source_pack",
    "node_evidence_matrix",
)
NUMERIC_GATE_KEYS = (
    "min_accepted_sources",
    "min_primary_sources",
    "min_claims",
    "min_reviewed_mappings",
)


def load_theme_batch_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).expanduser()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Theme batch manifest does not exist: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in theme batch manifest {manifest_path}: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Theme batch manifest must contain a JSON object: {manifest_path}")
    _validate_manifest(payload, manifest_path)
    return payload


def build_theme_batch_report(
    manifest_path: str | Path,
    wave: str | None = None,
) -> dict[str, Any]:
    resolved_manifest_path = Path(manifest_path).expanduser().resolve()
    manifest = load_theme_batch_manifest(resolved_manifest_path)
    waves = manifest["waves"]
    if wave is not None and wave not in waves:
        raise ValueError(
            f"Unknown wave {wave!r}; expected one of: {', '.join(waves)}"
        )
    selected_waves = [wave] if wave is not None else list(waves)
    artifact_base = (
        resolved_manifest_path.parent / manifest.get("artifact_base", ".")
    ).resolve()
    gates = manifest["completion_gates"]
    primary_source_types = set(manifest["primary_source_types"])

    theme_results: list[dict[str, Any]] = []
    wave_results: dict[str, dict[str, Any]] = {}
    for wave_name in selected_waves:
        current_results = [
            _build_theme_result(
                chain_id=chain_id,
                wave_name=wave_name,
                metadata=manifest["themes"][chain_id],
                artifact_base=artifact_base,
                gates=gates,
                primary_source_types=primary_source_types,
            )
            for chain_id in waves[wave_name]
        ]
        theme_results.extend(current_results)
        ready_count = sum(row["ready"] for row in current_results)
        wave_results[wave_name] = {
            "theme_count": len(current_results),
            "ready_theme_count": ready_count,
            "not_ready_theme_count": len(current_results) - ready_count,
            "ready": ready_count == len(current_results),
            "theme_ids": [row["theme_id"] for row in current_results],
        }

    ready_theme_count = sum(row["ready"] for row in theme_results)
    all_ready = ready_theme_count == len(theme_results)
    return {
        "batch_id": manifest["batch_id"],
        "target_theme_count": manifest["target_theme_count"],
        "selected_waves": selected_waves,
        "evaluated_theme_count": len(theme_results),
        "ready_theme_count": ready_theme_count,
        "not_ready_theme_count": len(theme_results) - ready_theme_count,
        "wave_results": wave_results,
        "theme_results": theme_results,
        "completion_status": "ready" if all_ready else "not_ready",
    }


def assert_theme_batch_ready(report: dict[str, Any]) -> None:
    if report.get("completion_status") == "ready":
        return
    failures = []
    for row in report.get("theme_results", []):
        if row.get("ready"):
            continue
        failed_checks = [
            name for name, passed in row.get("checks", {}).items() if not passed
        ]
        detail = ", ".join(failed_checks) or "unknown readiness failure"
        if row.get("errors"):
            detail = f"{detail}; {'; '.join(row['errors'])}"
        failures.append(f"{row.get('chain_id', '<unknown>')}: {detail}")
    raise AssertionError(
        "Theme batch is not ready: " + (" | ".join(failures) or "no theme results")
    )


def _validate_manifest(manifest: dict[str, Any], path: Path) -> None:
    for key in (
        "batch_id",
        "target_theme_count",
        "waves",
        "themes",
        "primary_source_types",
        "completion_gates",
    ):
        if key not in manifest:
            raise ValueError(f"Theme batch manifest {path} is missing {key!r}")
    if not isinstance(manifest["batch_id"], str) or not manifest["batch_id"]:
        raise ValueError(f"Theme batch manifest {path} has an invalid batch_id")
    if not isinstance(manifest["waves"], dict) or not manifest["waves"]:
        raise ValueError(f"Theme batch manifest {path} must define non-empty waves")
    if not isinstance(manifest["themes"], dict) or not manifest["themes"]:
        raise ValueError(f"Theme batch manifest {path} must define non-empty themes")

    ordered_chain_ids: list[str] = []
    for wave_name, chain_ids in manifest["waves"].items():
        if not isinstance(wave_name, str) or not wave_name:
            raise ValueError(f"Theme batch manifest {path} has an invalid wave name")
        if not isinstance(chain_ids, list) or not chain_ids:
            raise ValueError(f"Theme batch manifest {path} wave {wave_name!r} is empty")
        if not all(isinstance(chain_id, str) and chain_id for chain_id in chain_ids):
            raise ValueError(
                f"Theme batch manifest {path} wave {wave_name!r} has invalid chain IDs"
            )
        ordered_chain_ids.extend(chain_ids)
    if len(ordered_chain_ids) != len(set(ordered_chain_ids)):
        raise ValueError(f"Theme batch manifest {path} repeats a chain across waves")

    theme_ids = set(manifest["themes"])
    wave_ids = set(ordered_chain_ids)
    if theme_ids != wave_ids:
        missing = sorted(theme_ids - wave_ids)
        unknown = sorted(wave_ids - theme_ids)
        raise ValueError(
            f"Theme batch manifest {path} wave/theme scope mismatch: "
            f"not_in_waves={missing}, missing_metadata={unknown}"
        )
    target_count = manifest["target_theme_count"]
    if not isinstance(target_count, int) or isinstance(target_count, bool):
        raise ValueError(f"Theme batch manifest {path} has an invalid target_theme_count")
    if target_count != len(theme_ids):
        raise ValueError(
            f"Theme batch manifest {path} target_theme_count={target_count} "
            f"does not match themes={len(theme_ids)}"
        )

    for chain_id, metadata in manifest["themes"].items():
        if not isinstance(metadata, dict) or not metadata.get("theme_id"):
            raise ValueError(
                f"Theme batch manifest {path} theme {chain_id!r} needs theme_id"
            )
        artifacts = metadata.get("artifacts")
        if not isinstance(artifacts, dict) or set(artifacts) != set(ARTIFACT_KEYS):
            raise ValueError(
                f"Theme batch manifest {path} theme {chain_id!r} must define artifacts "
                f"{list(ARTIFACT_KEYS)}"
            )
        if not all(isinstance(value, str) and value for value in artifacts.values()):
            raise ValueError(
                f"Theme batch manifest {path} theme {chain_id!r} has invalid artifact paths"
            )

    source_types = manifest["primary_source_types"]
    if not isinstance(source_types, list) or not source_types or not all(
        isinstance(value, str) and value for value in source_types
    ):
        raise ValueError(f"Theme batch manifest {path} has invalid primary_source_types")
    gates = manifest["completion_gates"]
    if not isinstance(gates, dict):
        raise ValueError(f"Theme batch manifest {path} has invalid completion_gates")
    for key in NUMERIC_GATE_KEYS:
        value = gates.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(
                f"Theme batch manifest {path} completion gate {key!r} must be non-negative"
            )
    sections = gates.get("required_readable_sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError(
            f"Theme batch manifest {path} must define required_readable_sections"
        )
    section_names = []
    for section in sections:
        if not isinstance(section, dict) or not section.get("name"):
            raise ValueError(f"Theme batch manifest {path} has an invalid readable section")
        requirements = section.get("non_empty")
        if not isinstance(requirements, list) or not requirements or not all(
            _valid_requirement(value) for value in requirements
        ):
            raise ValueError(
                f"Theme batch manifest {path} section {section['name']!r} "
                "must define artifact:path non_empty requirements"
            )
        section_names.append(section["name"])
    if len(section_names) != len(set(section_names)):
        raise ValueError(f"Theme batch manifest {path} repeats a readable section name")


def _valid_requirement(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    artifact_name, separator, field_path = value.partition(":")
    return bool(
        separator
        and artifact_name in ARTIFACT_KEYS
        and field_path
        and all(field_path.split("."))
    )


def _build_theme_result(
    *,
    chain_id: str,
    wave_name: str,
    metadata: dict[str, Any],
    artifact_base: Path,
    gates: dict[str, Any],
    primary_source_types: set[str],
) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any] | None] = {}
    artifact_paths: dict[str, str] = {}
    errors: list[str] = []
    for artifact_name in ARTIFACT_KEYS:
        path = (artifact_base / metadata["artifacts"][artifact_name]).resolve()
        artifact_paths[artifact_name] = str(path)
        payload, error = _load_json_artifact(path)
        artifacts[artifact_name] = payload
        if error:
            errors.append(error)

    expected_theme_id = metadata["theme_id"]
    source_rows = (artifacts["source_pack"] or {}).get("sources", [])
    source_rows = source_rows if isinstance(source_rows, list) else []
    accepted_sources = [
        row
        for row in source_rows
        if isinstance(row, dict) and row.get("review_status") == "accepted"
    ]
    primary_sources = [
        row for row in accepted_sources if row.get("source_type") in primary_source_types
    ]
    claims = (artifacts["theme"] or {}).get("claims", [])
    claims = claims if isinstance(claims, list) else []
    mappings = (artifacts["company_mapping"] or {}).get("company_mappings", [])
    mappings = mappings if isinstance(mappings, list) else []
    reviewed_mappings = [
        row
        for row in mappings
        if isinstance(row, dict) and row.get("review_status") == "reviewed"
    ]
    readable_sections = {
        section["name"]: all(
            _requirement_is_non_empty(requirement, artifacts)
            for requirement in section["non_empty"]
        )
        for section in gates["required_readable_sections"]
    }
    artifact_checks = {
        f"{artifact_name}_readable": artifacts[artifact_name] is not None
        for artifact_name in ARTIFACT_KEYS
    }
    identity_checks = {
        f"{artifact_name}_theme_id": _artifact_theme_id(artifact_name, payload)
        == expected_theme_id
        for artifact_name, payload in artifacts.items()
    }
    checks = {
        **artifact_checks,
        **identity_checks,
        "accepted_source_count": len(accepted_sources)
        >= gates["min_accepted_sources"],
        "primary_source_count": len(primary_sources) >= gates["min_primary_sources"],
        "claim_count": len(claims) >= gates["min_claims"],
        "reviewed_mapping_count": len(reviewed_mappings)
        >= gates["min_reviewed_mappings"],
        "required_sections_ready": all(readable_sections.values()),
    }
    return {
        "chain_id": chain_id,
        "theme_id": expected_theme_id,
        "wave": wave_name,
        "artifact_paths": artifact_paths,
        "counts": {
            "accepted_sources": len(accepted_sources),
            "primary_sources": len(primary_sources),
            "claims": len(claims),
            "reviewed_mappings": len(reviewed_mappings),
        },
        "readable_sections": readable_sections,
        "required_sections_ready": all(readable_sections.values()),
        "checks": checks,
        "errors": errors,
        "ready": all(checks.values()),
    }


def _load_json_artifact(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"{path} does not exist"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"{path} is not readable JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"{path} must contain a JSON object"
    return payload, None


def _artifact_theme_id(
    artifact_name: str,
    payload: dict[str, Any] | None,
) -> str | None:
    if payload is None:
        return None
    if artifact_name == "theme":
        theme = payload.get("theme")
        return theme.get("theme_id") if isinstance(theme, dict) else None
    value = payload.get("theme_id")
    return value if isinstance(value, str) else None


def _requirement_is_non_empty(
    requirement: str,
    artifacts: dict[str, dict[str, Any] | None],
) -> bool:
    artifact_name, _, field_path = requirement.partition(":")
    value: Any = artifacts.get(artifact_name)
    for key in field_path.split("."):
        if not isinstance(value, dict) or key not in value:
            return False
        value = value[key]
    if value is None or value is False:
        return False
    if isinstance(value, (str, list, dict, tuple, set)):
        return bool(value)
    return True


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Theme batch {report['batch_id']}: {report['completion_status']}",
        "",
        f"Ready themes: {report['ready_theme_count']}/{report['evaluated_theme_count']}",
        "",
    ]
    for wave_name, wave_result in report["wave_results"].items():
        status = "ready" if wave_result["ready"] else "not_ready"
        lines.extend(
            [
                f"## {wave_name}: {status}",
                "",
                f"Ready themes: {wave_result['ready_theme_count']}/{wave_result['theme_count']}",
                "",
            ]
        )
        for row in report["theme_results"]:
            if row["wave"] != wave_name:
                continue
            counts = row["counts"]
            lines.append(
                f"- {row['chain_id']}: {'ready' if row['ready'] else 'not_ready'} "
                f"({counts['accepted_sources']} accepted sources, "
                f"{counts['primary_sources']} primary sources, {counts['claims']} claims, "
                f"{counts['reviewed_mappings']} reviewed mappings)"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--wave")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    report = build_theme_batch_report(args.manifest, wave=args.wave)
    if args.format == "markdown":
        print(_render_markdown(report))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["completion_status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
