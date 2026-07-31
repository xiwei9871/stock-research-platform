#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from stock_research.dashboard.auth_service import authenticate_user
from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research.theme_research_import import (
    NormalizedThemeResearchPackage,
    normalize_artifact_package,
    semantic_diff,
    validate_package_integrity,
)
from stock_research.theme_research_store import (
    bootstrap_package,
    dry_run_package,
    load_database_package,
    package_for_theme,
)


EXPECTED_CURRENT_THEME_IDS = {
    "ai_power_value_capture_v1",
    "humanoid_robotics_head_to_toe_v1",
}

PACKAGE_FAMILY_KEYS = {
    "themes": ("theme_id",),
    "nodes": ("node_id",),
    "sources": ("source_id",),
    "theme_sources": ("theme_id", "source_id", "link_reason"),
    "claims": ("claim_id",),
    "claim_sources": ("claim_id", "source_id"),
    "claim_nodes": ("claim_id", "node_id"),
    "assessments": ("assessment_id",),
    "assessment_evidence": ("assessment_id", "evidence_type", "evidence_id"),
    "company_mappings": ("mapping_id",),
    "mapping_evidence_items": ("evidence_id",),
    "company_mapping_evidence": ("mapping_id", "evidence_type", "evidence_id"),
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


def _row_identity(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    return "|".join(str(row[key]) for key in keys)


def build_additive_restore_package(
    *,
    current: NormalizedThemeResearchPackage,
    checkpoint: NormalizedThemeResearchPackage,
    expected_theme_ids: Iterable[str],
) -> NormalizedThemeResearchPackage:
    expected = {str(theme_id) for theme_id in expected_theme_ids}
    current_theme_ids = {row["theme_id"] for row in current.themes}
    checkpoint_theme_ids = {row["theme_id"] for row in checkpoint.themes}
    if not current_theme_ids <= expected or checkpoint_theme_ids != expected:
        raise ValueError("theme sets do not match the bounded additive restore")

    rows_by_family = {
        family: [dict(row) for row in getattr(current, family)]
        for family in PACKAGE_FAMILY_KEYS
    }
    identities = {
        family: {
            _row_identity(row, PACKAGE_FAMILY_KEYS[family]): row
            for row in rows
        }
        for family, rows in rows_by_family.items()
    }
    for theme_id in sorted(expected - current_theme_ids):
        selected = package_for_theme(checkpoint, theme_id)
        for family, keys in PACKAGE_FAMILY_KEYS.items():
            for row in getattr(selected, family):
                identity = _row_identity(row, keys)
                existing = identities[family].get(identity)
                if existing is not None:
                    if existing != row:
                        raise ValueError(f"identity collision: {family}:{identity}")
                    continue
                copied = dict(row)
                rows_by_family[family].append(copied)
                identities[family][identity] = copied

    return validate_package_integrity(
        NormalizedThemeResearchPackage.build(
            artifact_version=checkpoint.artifact_version,
            **rows_by_family,
        )
    )


def execute_additive_restore(
    *,
    current: NormalizedThemeResearchPackage,
    checkpoint: NormalizedThemeResearchPackage,
    expected_theme_ids: Iterable[str],
    actor_user_id: str,
    actor_role: str,
    expected_generation: int,
    idempotency_key: str,
    runtime_service: str,
) -> dict[str, Any]:
    desired = build_additive_restore_package(
        current=current,
        checkpoint=checkpoint,
        expected_theme_ids=expected_theme_ids,
    )
    diff = semantic_diff(current, desired)
    gate = evaluate_restore_gate(
        expected_theme_ids=expected_theme_ids,
        current_theme_ids=(row["theme_id"] for row in current.themes),
        semantic_diff=diff,
    )
    if not gate["allowed"]:
        raise ThemeResearchDomainError(
            "additive restore gate rejected execution",
            code="THEME_RESEARCH_ADDITIVE_RESTORE_REJECTED",
            details=gate,
        )
    return bootstrap_package(
        desired,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        expected_generation=expected_generation,
        idempotency_key=idempotency_key,
        service=runtime_service,
    )


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
    checkpoint = validate_package_integrity(
        normalize_artifact_package(
            theme_artifact_dir=artifact_dir,
            company_mapping_dir=company_mapping_dir,
        )
    )
    actual_theme_ids = {row["theme_id"] for row in checkpoint.themes}
    current = load_database_package(service=runtime_service)
    current_theme_ids = {row["theme_id"] for row in current.themes}
    desired = build_additive_restore_package(
        current=current,
        checkpoint=checkpoint,
        expected_theme_ids=expected_theme_ids,
    )
    dry_run = dry_run_package(desired, service=runtime_service)
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
        "artifact_package_sha256": checkpoint.package_sha256,
        "artifact_object_counts": _object_counts(checkpoint),
        "desired_package_sha256": desired.package_sha256,
        "desired_object_counts": _object_counts(desired),
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
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-generation", type=int)
    parser.add_argument("--admin-username")
    parser.add_argument("--auth-service", default=SETTINGS.research_service)
    parser.add_argument("--password-env", default="THEME_RESEARCH_ADMIN_PASSWORD")
    parser.add_argument("--idempotency-key", default="")
    args = parser.parse_args(argv)
    payload = build_preflight(
        artifact_dir=args.artifact_dir,
        company_mapping_dir=args.company_mapping_dir,
        expected_theme_ids_file=args.expected_theme_ids_file,
        runtime_service=args.runtime_service,
    )
    if not payload["allowed"]:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
        return 2
    if args.execute:
        if args.expected_generation is None or not args.admin_username or not args.idempotency_key:
            parser.error(
                "--execute requires --expected-generation, --admin-username, and --idempotency-key"
            )
        password = os.getenv(args.password_env, "")
        if not password:
            parser.error(f"password environment variable is empty: {args.password_env}")
        user = authenticate_user(
            args.admin_username,
            password,
            service=args.auth_service,
        )
        checkpoint = validate_package_integrity(
            normalize_artifact_package(
                theme_artifact_dir=args.artifact_dir,
                company_mapping_dir=args.company_mapping_dir,
            )
        )
        current = load_database_package(service=args.runtime_service)
        payload["execution"] = execute_additive_restore(
            current=current,
            checkpoint=checkpoint,
            expected_theme_ids=payload["expected_theme_ids"],
            actor_user_id=user.user_id,
            actor_role=user.role,
            expected_generation=args.expected_generation,
            idempotency_key=args.idempotency_key,
            runtime_service=args.runtime_service,
        )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
