#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.theme_research_import import (
    normalize_artifact_package,
    validate_package_integrity,
)
from stock_research.theme_research_store import (
    dry_run_package,
    load_database_package,
)


EXPECTED_CURRENT_THEME_IDS = {
    "ai_power_value_capture_v1",
    "humanoid_robotics_head_to_toe_v1",
}


def evaluate_restore_gate(
    *,
    expected_theme_ids: Iterable[str],
    current_theme_ids: Iterable[str],
    semantic_diff: dict[str, Any],
) -> dict[str, Any]:
    expected = {str(theme_id) for theme_id in expected_theme_ids}
    current = {str(theme_id) for theme_id in current_theme_ids}
    families = semantic_diff.get("families", {})
    theme_diff = families.get("themes", {})
    inserted = list(theme_diff.get("insert", []))
    updated = list(theme_diff.get("update", []))
    deactivated = list(theme_diff.get("deactivate", []))
    violations: list[str] = []

    if len(expected) != 25:
        violations.append(f"expected_theme_count:{len(expected)}")
    if current != EXPECTED_CURRENT_THEME_IDS:
        violations.append("current_theme_ids_mismatch")
    if len(inserted) != 23:
        violations.append(f"theme_insert_count:{len(inserted)}")
    if set(inserted) != expected - EXPECTED_CURRENT_THEME_IDS:
        violations.append("theme_insert_ids_mismatch")
    if updated:
        violations.append(f"theme_update_count:{len(updated)}")
    if deactivated:
        violations.append(f"theme_deactivate_count:{len(deactivated)}")

    family_counts: dict[str, dict[str, int]] = {}
    for family, operations in sorted(families.items()):
        counts = {
            operation: len(operations.get(operation, []))
            for operation in ("insert", "update", "deactivate", "no_change")
        }
        family_counts[family] = counts
        if counts["update"]:
            violations.append(f"updates_present:{family}:{counts['update']}")
        if counts["deactivate"]:
            violations.append(
                f"deactivations_present:{family}:{counts['deactivate']}"
            )

    return {
        "allowed": not violations,
        "violations": violations,
        "theme_counts": {
            "expected": len(expected),
            "current": len(current),
            "insert": len(inserted),
            "update": len(updated),
            "deactivate": len(deactivated),
        },
        "family_counts": family_counts,
    }


def _object_counts(package: Any) -> dict[str, int]:
    return {
        family: len(getattr(package, family))
        for family in (
            "themes",
            "nodes",
            "sources",
            "theme_sources",
            "claims",
            "claim_sources",
            "claim_nodes",
            "assessments",
            "assessment_evidence",
            "company_mappings",
            "mapping_evidence_items",
            "company_mapping_evidence",
        )
    }


def _load_expected_theme_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(
        isinstance(theme_id, str) and theme_id for theme_id in payload
    ):
        raise ValueError("expected theme ID manifest must be a JSON string array")
    if len(payload) != len(set(payload)):
        raise ValueError("expected theme ID manifest contains duplicates")
    return set(payload)


def _load_store_evidence(service: str) -> dict[str, Any]:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT generation, package_sha256, artifact_version
                FROM research.theme_research_store_state
                WHERE state_id = true
                """
            )
            state = dict(cur.fetchone())
            cur.execute(
                """
                SELECT theme_id, theme_version, row_version, content_sha256
                FROM research.theme_research_theme
                WHERE theme_id = ANY(%s)
                ORDER BY theme_id
                """,
                (sorted(EXPECTED_CURRENT_THEME_IDS),),
            )
            fingerprints = [dict(row) for row in cur.fetchall()]
    return {
        "generation": int(state["generation"]),
        "package_sha256": str(state.get("package_sha256") or ""),
        "artifact_version": str(state.get("artifact_version") or ""),
        "original_theme_fingerprints": fingerprints,
    }


def build_preflight(
    *,
    artifact_dir: Path,
    company_mapping_dir: Path,
    expected_theme_ids_file: Path,
    runtime_service: str,
) -> dict[str, Any]:
    expected_theme_ids = _load_expected_theme_ids(expected_theme_ids_file)
    package = validate_package_integrity(
        normalize_artifact_package(
            theme_artifact_dir=artifact_dir,
            company_mapping_dir=company_mapping_dir,
        )
    )
    actual_theme_ids = {row["theme_id"] for row in package.themes}
    current = load_database_package(service=runtime_service)
    current_theme_ids = {row["theme_id"] for row in current.themes}
    dry_run = dry_run_package(package, service=runtime_service)
    gate = evaluate_restore_gate(
        expected_theme_ids=expected_theme_ids,
        current_theme_ids=current_theme_ids,
        semantic_diff=dry_run["semantic_diff"],
    )
    if actual_theme_ids != expected_theme_ids:
        gate["violations"].append("artifact_theme_ids_mismatch")
        gate["allowed"] = False
    evidence = _load_store_evidence(runtime_service)
    manifest_bytes = expected_theme_ids_file.read_bytes()
    return {
        **gate,
        "expected_theme_ids": sorted(expected_theme_ids),
        "current_theme_ids": sorted(current_theme_ids),
        "artifact_theme_ids": sorted(actual_theme_ids),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "artifact_package_sha256": package.package_sha256,
        "artifact_object_counts": _object_counts(package),
        "database_package_sha256": current.package_sha256,
        "database_object_counts": _object_counts(current),
        "semantic_diff": dry_run["semantic_diff"],
        **evidence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a bounded 25-theme production restore without writing."
    )
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--company-mapping-dir", type=Path, required=True)
    parser.add_argument("--expected-theme-ids-file", type=Path, required=True)
    parser.add_argument(
        "--runtime-service",
        default=SETTINGS.theme_research_runtime_service,
    )
    args = parser.parse_args(argv)
    payload = build_preflight(
        artifact_dir=args.artifact_dir,
        company_mapping_dir=args.company_mapping_dir,
        expected_theme_ids_file=args.expected_theme_ids_file,
        runtime_service=args.runtime_service,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if payload["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
