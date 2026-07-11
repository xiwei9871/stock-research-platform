from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from stock_research.theme_company_mapping import (
    THEME_COMPANY_MAPPING_DIR,
    load_theme_company_mapping_package,
)
from stock_research.theme_decomposition import ARTIFACT_DIR as THEME_ARTIFACT_DIR


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TECH_BOTTLENECK_CROSSWALK_DIR = (
    REPOSITORY_ROOT
    / "artifacts"
    / "theme_decomposition"
    / "tech_bottleneck_crosswalks"
)
MANUAL_OVERLAY_RELATIVE_PATH = Path(
    "outputs/research/tech_bottleneck_review_universe_manual_decision_overlay_v1/"
    "manual_decision_current_overlay.json"
)
CROSSWALK_ARTIFACT_VERSION = "theme_tech_bottleneck_crosswalk_v1"
REVIEWED_CONFIDENCE_THRESHOLD = 0.7

ARTIFACT_FIELDS = {
    "artifact_version",
    "theme_id",
    "universe_snapshot",
    "crosswalks",
    "coverage_gaps",
    "guardrails",
}
SNAPSHOT_FIELDS = {
    "dataset_path",
    "dataset_sha256",
    "evidence_index_path",
    "evidence_index_sha256",
    "source_index_path",
    "source_index_sha256",
    "expected_universe_count",
}
CROSSWALK_FIELDS = {
    "crosswalk_id",
    "theme_id",
    "theme_node_id",
    "company_code",
    "company_name",
    "mapping_id",
    "existing_review_universe_id",
    "existing_evidence_ids",
    "new_theme_evidence_ids",
    "relationship_type",
    "confidence",
    "review_status",
    "notes",
}
GAP_FIELDS = {
    "gap_id",
    "theme_id",
    "theme_node_id",
    "company_code",
    "company_name",
    "mapping_id",
    "new_theme_evidence_ids",
    "reason",
    "notes",
}
GUARDRAIL_FIELDS = {
    "readonly",
    "database_write_enabled",
    "csv_writeback_enabled",
    "manual_review_write_enabled",
    "used_for_signal",
    "used_for_admission",
    "auto_added_to_quality_pool",
}
FORBIDDEN_CROSSWALK_FIELDS = {
    "used_for_signal",
    "used_for_admission",
    "auto_added_to_quality_pool",
    "reviewer_decision",
    "reviewer_note",
}
RELATIONSHIP_TYPES = {"evidence_context_enrichment"}
CROSSWALK_REVIEW_STATUSES = {"reviewed", "draft", "blocked"}
GAP_REASONS = {"company_not_in_existing_review_universe"}
AUTHORITATIVE_INPUT_PATHS = {
    "dataset_path": (
        "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
        "tech_bottleneck_review_universe_frontend_dataset.csv"
    ),
    "evidence_index_path": (
        "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
        "tech_bottleneck_review_universe_frontend_evidence_index.csv"
    ),
    "source_index_path": (
        "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
        "tech_bottleneck_review_universe_frontend_source_index.csv"
    ),
}
UNIVERSE_REQUIRED_COLUMNS = {
    "stock_code",
    "stock_name",
    "review_universe_source",
    "current_layer_status",
    "manual_approval_status",
    "frontend_review_status",
    "reviewer_decision",
    "reviewer_note",
    "used_for_signal",
    "used_for_admission",
    "auto_added_to_quality_pool",
}
EVIDENCE_REQUIRED_COLUMNS = {
    "stock_code",
    "stock_name",
    "review_universe_source",
    "source_file",
    "source_type",
    "source_title",
    "page",
    "evidence_text",
    "evidence_claim_type",
    "citation_quality",
    "research_only",
    "used_for_signal",
    "used_for_admission",
}
SOURCE_REQUIRED_COLUMNS = {
    "stock_code",
    "stock_name",
    "review_universe_source",
    "source_file",
    "source_type",
    "source_title",
    "research_only",
    "used_for_signal",
    "used_for_admission",
}


class ThemeTechBottleneckCrosswalkValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


def normalize_company_code(value: Any) -> str:
    raw = str(value or "").strip().upper()
    numeric = raw.split(".")[0]
    return numeric.zfill(6) if numeric.isdigit() else numeric


def existing_review_universe_id(stock_code: Any) -> str:
    return f"tech_bottleneck_review_universe_v1:{normalize_company_code(stock_code)}"


def existing_evidence_id(row: dict[str, Any]) -> str:
    stock_code = normalize_company_code(row.get("stock_code"))
    digest = _stable_row_digest(
        row,
        ("stock_code", "source_file", "page", "evidence_claim_type", "evidence_text"),
    )
    return f"tech_bottleneck_evidence_v1:{stock_code}:{digest[:24]}"


def existing_source_id(row: dict[str, Any]) -> str:
    stock_code = normalize_company_code(row.get("stock_code"))
    digest = _stable_row_digest(
        row,
        ("stock_code", "source_file", "source_type", "source_title"),
    )
    return f"tech_bottleneck_source_v1:{stock_code}:{digest[:24]}"


def load_theme_tech_bottleneck_crosswalk_package(
    artifact_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
    theme_mapping_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir is not None else TECH_BOTTLENECK_CROSSWALK_DIR
    repository = Path(repository_root) if repository_root is not None else REPOSITORY_ROOT
    mapping_root = (
        Path(theme_mapping_dir)
        if theme_mapping_dir is not None
        else THEME_COMPANY_MAPPING_DIR
    )
    theme_root = (
        Path(theme_artifact_dir)
        if theme_artifact_dir is not None
        else THEME_ARTIFACT_DIR
    )
    if not root.exists():
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"crosswalk artifact directory not found: {root}",
            code="CROSSWALK_DIRECTORY_NOT_FOUND",
        )
    artifacts = [_load_json(path) for path in sorted(root.glob("*.json"))]
    if not artifacts:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"no crosswalk artifacts found in {root}",
            code="NO_CROSSWALK_ARTIFACTS_FOUND",
        )

    snapshot = _validate_artifact_headers(artifacts)
    input_paths = _resolve_and_verify_snapshot(snapshot, repository)
    universe_rows = _read_csv(
        input_paths["dataset_path"],
        required_columns=UNIVERSE_REQUIRED_COLUMNS,
        label="dataset",
    )
    evidence_rows = _read_csv(
        input_paths["evidence_index_path"],
        required_columns=EVIDENCE_REQUIRED_COLUMNS,
        label="evidence_index",
    )
    source_rows = _read_csv(
        input_paths["source_index_path"],
        required_columns=SOURCE_REQUIRED_COLUMNS,
        label="source_index",
    )
    universe_indexes = _build_universe_indexes(
        universe_rows,
        evidence_rows,
        source_rows,
        expected_count=snapshot["expected_universe_count"],
    )
    theme_mapping_package = load_theme_company_mapping_package(
        mapping_root,
        theme_root,
    )
    manual_overlay = _load_optional_overlay(repository / MANUAL_OVERLAY_RELATIVE_PATH)
    package = {
        "artifact_dir": str(root),
        "repository_root": str(repository),
        "artifacts": artifacts,
        "universe_snapshot": snapshot,
        "universe_rows": universe_rows,
        "existing_evidence_rows": evidence_rows,
        "existing_source_rows": source_rows,
        "theme_mapping_package": theme_mapping_package,
        "crosswalks": [
            row for artifact in artifacts for row in artifact["crosswalks"]
        ],
        "coverage_gaps": [
            row for artifact in artifacts for row in artifact["coverage_gaps"]
        ],
        "manual_review_overlay": manual_overlay,
        "indexes": universe_indexes,
    }
    _validate_package(package)
    return package


def summarize_theme_tech_bottleneck_crosswalk_package(
    package: dict[str, Any],
) -> dict[str, Any]:
    theme_ids = {artifact["theme_id"] for artifact in package["artifacts"]}
    p4_mappings = [
        mapping
        for mapping in package["theme_mapping_package"]["company_mappings"]
        if mapping["theme_id"] in theme_ids
    ]
    covered_mapping_ids = {
        row["mapping_id"] for row in package["crosswalks"] + package["coverage_gaps"]
    }
    p4_count = len(p4_mappings)
    return {
        "artifact_count": len(package["artifacts"]),
        "theme_count": len(theme_ids),
        "universe_count": len(package["indexes"]["universe_by_code"]),
        "p4_mapping_count": p4_count,
        "crosswalk_count": len(package["crosswalks"]),
        "linked_company_count": len(
            {row["company_code"] for row in package["crosswalks"]}
        ),
        "coverage_gap_count": len(package["coverage_gaps"]),
        "accounted_mapping_count": len(covered_mapping_ids),
        "mapping_coverage_rate": (
            round(len(covered_mapping_ids) / p4_count, 6) if p4_count else 1.0
        ),
        "existing_evidence_count": len(
            {
                evidence_id
                for row in package["crosswalks"]
                for evidence_id in row["existing_evidence_ids"]
            }
        ),
        "new_theme_evidence_count": len(
            {
                evidence_id
                for row in package["crosswalks"]
                for evidence_id in row["new_theme_evidence_ids"]
            }
        ),
    }


def load_theme_crosswalk_details(
    theme_id: str,
    artifact_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
    theme_mapping_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_tech_bottleneck_crosswalk_package(
        artifact_dir,
        repository_root,
        theme_mapping_dir,
        theme_artifact_dir,
    )
    rows = [
        row
        for row in package["crosswalks"] + package["coverage_gaps"]
        if row["theme_id"] == theme_id
    ]
    if not rows:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"theme crosswalk not found: {theme_id}",
            code="THEME_CROSSWALK_NOT_FOUND",
        )
    return _resolve_details(package, rows)


def load_company_crosswalk_details(
    company_code: str,
    artifact_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
    theme_mapping_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    query = str(company_code or "").strip().upper()
    normalized = normalize_company_code(query)
    has_market_suffix = "." in query
    package = load_theme_tech_bottleneck_crosswalk_package(
        artifact_dir,
        repository_root,
        theme_mapping_dir,
        theme_artifact_dir,
    )
    rows = [
        row
        for row in package["crosswalks"] + package["coverage_gaps"]
        if (
            str(row["company_code"]).strip().upper() == query
            if has_market_suffix
            else normalize_company_code(row["company_code"]) == normalized
        )
    ]
    if not rows:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"company crosswalk not found: {company_code}",
            code="COMPANY_CROSSWALK_NOT_FOUND",
        )
    return _resolve_details(package, rows)


def list_coverage_gap_details(
    artifact_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
    theme_mapping_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_tech_bottleneck_crosswalk_package(
        artifact_dir,
        repository_root,
        theme_mapping_dir,
        theme_artifact_dir,
    )
    return _resolve_details(package, package["coverage_gaps"])


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-tech-bottleneck-crosswalk")
    parser.add_argument("--artifact-dir", default=str(TECH_BOTTLENECK_CROSSWALK_DIR))
    parser.add_argument("--repository-root", default=str(REPOSITORY_ROOT))
    parser.add_argument("--theme-mapping-dir", default=str(THEME_COMPANY_MAPPING_DIR))
    parser.add_argument("--theme-artifact-dir", default=str(THEME_ARTIFACT_DIR))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("summary")
    show_theme = subparsers.add_parser("show-theme")
    show_theme.add_argument("--theme-id", required=True)
    show_company = subparsers.add_parser("show-company")
    show_company.add_argument("--company-code", required=True)
    subparsers.add_parser("coverage-gaps")
    args = parser.parse_args(argv)

    common = {
        "artifact_dir": args.artifact_dir,
        "repository_root": args.repository_root,
        "theme_mapping_dir": args.theme_mapping_dir,
        "theme_artifact_dir": args.theme_artifact_dir,
    }
    try:
        if args.command in {"validate", "summary"}:
            package = load_theme_tech_bottleneck_crosswalk_package(**common)
            summary = summarize_theme_tech_bottleneck_crosswalk_package(package)
            payload = {"status": "ok", **summary} if args.command == "validate" else summary
        elif args.command == "show-theme":
            payload = load_theme_crosswalk_details(args.theme_id, **common)
        elif args.command == "show-company":
            payload = load_company_crosswalk_details(args.company_code, **common)
        elif args.command == "coverage-gaps":
            payload = list_coverage_gap_details(**common)
        else:
            raise AssertionError(f"unhandled command: {args.command}")
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except ThemeTechBottleneckCrosswalkValidationError as exc:
        print(
            json.dumps(
                {"status": "error", "error_code": exc.code, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


def main() -> None:
    raise SystemExit(cli())


def _validate_artifact_headers(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    for index, artifact in enumerate(artifacts):
        path = f"artifacts[{index}]"
        _require_exact_fields(artifact, ARTIFACT_FIELDS, path)
        if artifact["artifact_version"] != CROSSWALK_ARTIFACT_VERSION:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{path}.artifact_version must be {CROSSWALK_ARTIFACT_VERSION}",
                code="UNSUPPORTED_CROSSWALK_ARTIFACT_VERSION",
            )
        _require_non_empty_string(artifact, "theme_id", path)
        _require_object_list(artifact, "crosswalks", path)
        _require_object_list(artifact, "coverage_gaps", path)
        snapshot = artifact["universe_snapshot"]
        if not isinstance(snapshot, dict):
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{path}.universe_snapshot must be object",
                code="INVALID_CROSSWALK_SNAPSHOT",
            )
        _require_exact_fields(snapshot, SNAPSHOT_FIELDS, f"{path}.universe_snapshot")
        snapshots.append(snapshot)
        _validate_guardrails(artifact["guardrails"], f"{path}.guardrails")
    canonical = snapshots[0]
    if any(snapshot != canonical for snapshot in snapshots[1:]):
        raise ThemeTechBottleneckCrosswalkValidationError(
            "crosswalk artifacts must use the same universe snapshot",
            code="CROSSWALK_SNAPSHOT_MISMATCH",
        )
    return canonical


def _resolve_and_verify_snapshot(
    snapshot: dict[str, Any], repository_root: Path
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path_field, digest_field in (
        ("dataset_path", "dataset_sha256"),
        ("evidence_index_path", "evidence_index_sha256"),
        ("source_index_path", "source_index_sha256"),
    ):
        if snapshot[path_field] != AUTHORITATIVE_INPUT_PATHS[path_field]:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{path_field} must reference the authoritative review-universe input",
                code="NON_AUTHORITATIVE_CROSSWALK_INPUT_PATH",
            )
        relative_path = _safe_relative_path(snapshot[path_field], path_field)
        path = (repository_root / relative_path).resolve()
        repository = repository_root.resolve()
        if not path.is_relative_to(repository):
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{path_field} escapes repository root",
                code="CROSSWALK_INPUT_PATH_ESCAPE",
            )
        if not path.is_file():
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"crosswalk input not found: {path}",
                code="CROSSWALK_INPUT_NOT_FOUND",
            )
        expected_digest = snapshot[digest_field]
        if not isinstance(expected_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_digest
        ):
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{digest_field} must be lowercase SHA-256",
                code="INVALID_SNAPSHOT_DIGEST",
            )
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"snapshot digest mismatch for {relative_path}",
                code="INPUT_SNAPSHOT_DIGEST_MISMATCH",
            )
        result[path_field] = path
    return result


def _build_universe_indexes(
    universe_rows: list[dict[str, str]],
    evidence_rows: list[dict[str, str]],
    source_rows: list[dict[str, str]],
    *,
    expected_count: Any,
) -> dict[str, Any]:
    if isinstance(expected_count, bool) or not isinstance(expected_count, int):
        raise ThemeTechBottleneckCrosswalkValidationError(
            "expected_universe_count must be integer",
            code="INVALID_UNIVERSE_COUNT",
        )
    universe_by_code: dict[str, dict[str, str]] = {}
    universe_by_id: dict[str, dict[str, str]] = {}
    for index, row in enumerate(universe_rows):
        stock_code = normalize_company_code(row.get("stock_code"))
        if not stock_code:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"universe row {index} has no stock code",
                code="INVALID_UNIVERSE_STOCK_CODE",
            )
        if stock_code in universe_by_code:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"duplicate universe stock code: {stock_code}",
                code="DUPLICATE_UNIVERSE_STOCK_CODE",
            )
        row_copy = dict(row)
        row_copy["stock_code"] = stock_code
        universe_id = existing_review_universe_id(stock_code)
        row_copy["existing_review_universe_id"] = universe_id
        universe_by_code[stock_code] = row_copy
        universe_by_id[universe_id] = row_copy
    if len(universe_by_code) != expected_count:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"universe count {len(universe_by_code)} != expected {expected_count}",
            code="UNIVERSE_COUNT_MISMATCH",
        )

    source_by_id: dict[str, dict[str, str]] = {}
    source_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in source_rows:
        row_copy = dict(row)
        row_copy["stock_code"] = normalize_company_code(row.get("stock_code"))
        if row_copy["stock_code"] not in universe_by_code:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"source row references stock outside universe: {row_copy['stock_code']}",
                code="SOURCE_STOCK_OUTSIDE_UNIVERSE",
            )
        source_id = existing_source_id(row_copy)
        if source_id in source_by_id:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"duplicate derived source id: {source_id}",
                code="DUPLICATE_EXISTING_SOURCE_ID",
            )
        row_copy["existing_source_id"] = source_id
        row_copy["source_reference"] = _stable_source_reference(
            row_copy.get("source_file", "")
        )
        source_key = (row_copy["stock_code"], row_copy["source_reference"])
        if source_key in source_by_key:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"duplicate existing source key: {source_key}",
                code="DUPLICATE_EXISTING_SOURCE_KEY",
            )
        source_by_id[source_id] = row_copy
        source_by_key[source_key] = row_copy

    evidence_by_id: dict[str, dict[str, str]] = {}
    for row in evidence_rows:
        row_copy = dict(row)
        row_copy["stock_code"] = normalize_company_code(row.get("stock_code"))
        if row_copy["stock_code"] not in universe_by_code:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"evidence row references stock outside universe: {row_copy['stock_code']}",
                code="EVIDENCE_STOCK_OUTSIDE_UNIVERSE",
            )
        evidence_id = existing_evidence_id(row_copy)
        if evidence_id in evidence_by_id:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"duplicate derived evidence id: {evidence_id}",
                code="DUPLICATE_EXISTING_EVIDENCE_ID",
            )
        row_copy["existing_evidence_id"] = evidence_id
        row_copy["source_reference"] = _stable_source_reference(
            row_copy.get("source_file", "")
        )
        source_key = (row_copy["stock_code"], row_copy["source_reference"])
        if source_key not in source_by_key:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"evidence row has no matching source: {evidence_id}",
                code="EXISTING_EVIDENCE_SOURCE_MISSING",
            )
        evidence_by_id[evidence_id] = row_copy
    universe_codes = set(universe_by_code)
    if {row["stock_code"] for row in source_by_id.values()} != universe_codes:
        raise ThemeTechBottleneckCrosswalkValidationError(
            "source index does not cover the full review universe",
            code="SOURCE_INDEX_STOCK_COVERAGE_MISMATCH",
        )
    if {row["stock_code"] for row in evidence_by_id.values()} != universe_codes:
        raise ThemeTechBottleneckCrosswalkValidationError(
            "evidence index does not cover the full review universe",
            code="EVIDENCE_INDEX_STOCK_COVERAGE_MISMATCH",
        )
    return {
        "universe_by_code": universe_by_code,
        "universe_by_id": universe_by_id,
        "existing_evidence_by_id": evidence_by_id,
        "existing_source_by_id": source_by_id,
        "existing_source_by_key": source_by_key,
    }


def _validate_package(package: dict[str, Any]) -> None:
    indexes = package["indexes"]
    universe_by_code = indexes["universe_by_code"]
    existing_evidence_by_id = indexes["existing_evidence_by_id"]
    existing_source_by_key = indexes["existing_source_by_key"]
    mapping_package = package["theme_mapping_package"]
    mapping_by_id = {
        mapping["mapping_id"]: mapping for mapping in mapping_package["company_mappings"]
    }
    new_evidence_by_id = {
        evidence["evidence_id"]: evidence for evidence in mapping_package["evidence_items"]
    }
    canonical_theme_ids = {theme["theme_id"] for theme in mapping_package["themes"]}
    artifact_theme_ids = {artifact["theme_id"] for artifact in package["artifacts"]}
    if not artifact_theme_ids.issubset(canonical_theme_ids):
        missing = sorted(artifact_theme_ids - canonical_theme_ids)
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"crosswalk artifact references missing themes: {missing}",
            code="CROSSWALK_REFERENCES_MISSING_THEME",
        )

    crosswalk_ids: set[str] = set()
    gap_ids: set[str] = set()
    covered_mapping_ids: set[str] = set()
    for artifact_index, artifact in enumerate(package["artifacts"]):
        theme_id = artifact["theme_id"]
        for row_index, row in enumerate(artifact["crosswalks"]):
            path = f"artifacts[{artifact_index}].crosswalks[{row_index}]"
            _reject_forbidden_fields(row, path)
            _require_exact_fields(row, CROSSWALK_FIELDS, path)
            _validate_crosswalk_row(
                row,
                artifact_theme_id=theme_id,
                universe_by_code=universe_by_code,
                existing_evidence_by_id=existing_evidence_by_id,
                existing_source_by_key=existing_source_by_key,
                mapping_by_id=mapping_by_id,
                new_evidence_by_id=new_evidence_by_id,
                covered_mapping_ids=covered_mapping_ids,
                crosswalk_ids=crosswalk_ids,
                path=path,
            )
        for row_index, row in enumerate(artifact["coverage_gaps"]):
            path = f"artifacts[{artifact_index}].coverage_gaps[{row_index}]"
            _reject_forbidden_fields(row, path)
            _require_exact_fields(row, GAP_FIELDS, path)
            _validate_gap_row(
                row,
                artifact_theme_id=theme_id,
                universe_by_code=universe_by_code,
                mapping_by_id=mapping_by_id,
                new_evidence_by_id=new_evidence_by_id,
                covered_mapping_ids=covered_mapping_ids,
                gap_ids=gap_ids,
                path=path,
            )

    expected_mapping_ids = {
        mapping["mapping_id"]
        for mapping in mapping_package["company_mappings"]
        if mapping["theme_id"] in artifact_theme_ids
    }
    if covered_mapping_ids != expected_mapping_ids:
        missing = sorted(expected_mapping_ids - covered_mapping_ids)
        extra = sorted(covered_mapping_ids - expected_mapping_ids)
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"Phase 4 mapping coverage mismatch; missing={missing}, extra={extra}",
            code="INCOMPLETE_PHASE4_MAPPING_COVERAGE",
        )


def _validate_crosswalk_row(
    row: dict[str, Any],
    *,
    artifact_theme_id: str,
    universe_by_code: dict[str, dict[str, str]],
    existing_evidence_by_id: dict[str, dict[str, str]],
    existing_source_by_key: dict[tuple[str, str], dict[str, str]],
    mapping_by_id: dict[str, dict[str, Any]],
    new_evidence_by_id: dict[str, dict[str, Any]],
    covered_mapping_ids: set[str],
    crosswalk_ids: set[str],
    path: str,
) -> None:
    for field in (
        "crosswalk_id",
        "theme_id",
        "theme_node_id",
        "company_code",
        "company_name",
        "mapping_id",
        "existing_review_universe_id",
        "relationship_type",
    ):
        _require_non_empty_string(row, field, path)
    _require_string(row, "notes", path)
    _check_enum(row, "relationship_type", RELATIONSHIP_TYPES, path)
    _check_enum(row, "review_status", CROSSWALK_REVIEW_STATUSES, path)
    _unique_value(crosswalk_ids, row["crosswalk_id"], f"{path}.crosswalk_id", "DUPLICATE_CROSSWALK_ID")
    _claim_mapping_coverage(covered_mapping_ids, row["mapping_id"], path)
    _validate_mapping_reference(row, artifact_theme_id, mapping_by_id, path)
    company_code = normalize_company_code(row["company_code"])
    if company_code not in universe_by_code:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.company_code is not in existing universe: {company_code}",
            code="CROSSWALK_COMPANY_NOT_IN_UNIVERSE",
        )
    if universe_by_code[company_code].get("stock_name") != row["company_name"]:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.company_name does not match existing universe",
            code="CROSSWALK_COMPANY_NAME_MISMATCH",
        )
    expected_universe_id = existing_review_universe_id(company_code)
    if row["existing_review_universe_id"] != expected_universe_id:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.existing_review_universe_id must be {expected_universe_id}",
            code="CROSSWALK_UNIVERSE_ID_MISMATCH",
        )
    existing_ids = _require_string_list(
        row, "existing_evidence_ids", path, allow_empty=True
    )
    if not existing_ids:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path} requires existing evidence",
            code="CROSSWALK_REQUIRES_EXISTING_EVIDENCE",
        )
    for evidence_id in existing_ids:
        evidence = existing_evidence_by_id.get(evidence_id)
        if evidence is None:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{path} references missing existing evidence: {evidence_id}",
                code="CROSSWALK_REFERENCES_MISSING_EXISTING_EVIDENCE",
            )
        if evidence["stock_code"] != company_code:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{path} existing evidence belongs to another company: {evidence_id}",
                code="CROSSWALK_EXISTING_EVIDENCE_SCOPE_MISMATCH",
            )
        source_key = (company_code, evidence["source_reference"])
        if source_key not in existing_source_by_key:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{path} existing evidence has no source row: {evidence_id}",
                code="CROSSWALK_EXISTING_EVIDENCE_SOURCE_MISSING",
            )
    _validate_new_theme_evidence(row, mapping_by_id, new_evidence_by_id, path)
    confidence = row["confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or confidence < 0
        or confidence > 1
    ):
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.confidence must be number 0-1",
            code="INVALID_CROSSWALK_CONFIDENCE",
        )
    if row["review_status"] == "reviewed" and confidence < REVIEWED_CONFIDENCE_THRESHOLD:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path} reviewed crosswalk requires confidence >= {REVIEWED_CONFIDENCE_THRESHOLD}",
            code="REVIEWED_CROSSWALK_REQUIRES_CONFIDENCE",
        )


def _validate_gap_row(
    row: dict[str, Any],
    *,
    artifact_theme_id: str,
    universe_by_code: dict[str, dict[str, str]],
    mapping_by_id: dict[str, dict[str, Any]],
    new_evidence_by_id: dict[str, dict[str, Any]],
    covered_mapping_ids: set[str],
    gap_ids: set[str],
    path: str,
) -> None:
    for field in (
        "gap_id",
        "theme_id",
        "theme_node_id",
        "company_code",
        "company_name",
        "mapping_id",
    ):
        _require_non_empty_string(row, field, path)
    _require_string(row, "notes", path)
    _check_enum(row, "reason", GAP_REASONS, path)
    _unique_value(gap_ids, row["gap_id"], f"{path}.gap_id", "DUPLICATE_COVERAGE_GAP_ID")
    _claim_mapping_coverage(covered_mapping_ids, row["mapping_id"], path)
    _validate_mapping_reference(row, artifact_theme_id, mapping_by_id, path)
    company_code = normalize_company_code(row["company_code"])
    if company_code in universe_by_code:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.company_code exists in universe: {company_code}",
            code="COVERAGE_GAP_COMPANY_PRESENT",
        )
    _validate_new_theme_evidence(row, mapping_by_id, new_evidence_by_id, path)


def _validate_mapping_reference(
    row: dict[str, Any],
    artifact_theme_id: str,
    mapping_by_id: dict[str, dict[str, Any]],
    path: str,
) -> None:
    mapping = mapping_by_id.get(row["mapping_id"])
    if mapping is None:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.mapping_id references missing Phase 4 mapping: {row['mapping_id']}",
            code="CROSSWALK_REFERENCES_MISSING_MAPPING",
        )
    if row["theme_id"] != artifact_theme_id or mapping["theme_id"] != artifact_theme_id:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path} theme does not match artifact or mapping",
            code="CROSSWALK_THEME_OWNERSHIP_MISMATCH",
        )
    if mapping["mapped_node_id"] != row["theme_node_id"]:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.theme_node_id does not match Phase 4 mapping",
            code="CROSSWALK_NODE_MISMATCH",
        )
    if str(mapping["company_code"]).strip().upper() != str(row["company_code"]).strip().upper():
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.company_code does not match Phase 4 mapping",
            code="CROSSWALK_COMPANY_MISMATCH",
        )
    if mapping["company_name"] != row["company_name"]:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.company_name does not match Phase 4 mapping",
            code="CROSSWALK_COMPANY_NAME_MISMATCH",
        )


def _validate_new_theme_evidence(
    row: dict[str, Any],
    mapping_by_id: dict[str, dict[str, Any]],
    new_evidence_by_id: dict[str, dict[str, Any]],
    path: str,
) -> None:
    evidence_ids = _require_string_list(
        row, "new_theme_evidence_ids", path, allow_empty=True
    )
    if not evidence_ids:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path} requires new theme evidence",
            code="CROSSWALK_REQUIRES_NEW_THEME_EVIDENCE",
        )
    mapping = mapping_by_id[row["mapping_id"]]
    mapping_evidence_ids = set(mapping["evidence_ids"])
    for evidence_id in evidence_ids:
        if evidence_id not in new_evidence_by_id:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{path} references missing new evidence: {evidence_id}",
                code="CROSSWALK_REFERENCES_MISSING_NEW_EVIDENCE",
            )
        if evidence_id not in mapping_evidence_ids:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{path} new evidence is outside Phase 4 mapping: {evidence_id}",
                code="CROSSWALK_NEW_EVIDENCE_SCOPE_MISMATCH",
            )


def _resolve_details(
    package: dict[str, Any], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    indexes = package["indexes"]
    mapping_package = package["theme_mapping_package"]
    mapping_by_id = {
        mapping["mapping_id"]: mapping for mapping in mapping_package["company_mappings"]
    }
    new_evidence_by_id = {
        evidence["evidence_id"]: evidence for evidence in mapping_package["evidence_items"]
    }
    new_source_by_id = {
        source["source_id"]: source for source in mapping_package["sources"]
    }
    crosswalk_ids = {row["crosswalk_id"] for row in package["crosswalks"]}
    details: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: item["mapping_id"]):
        mapping = mapping_by_id[row["mapping_id"]]
        new_evidence = [
            {
                **new_evidence_by_id[evidence_id],
                "source": new_source_by_id[
                    new_evidence_by_id[evidence_id]["source_id"]
                ],
            }
            for evidence_id in row["new_theme_evidence_ids"]
        ]
        mapping_detail = {**mapping, "evidence": new_evidence}
        company_code = normalize_company_code(row["company_code"])
        if row.get("crosswalk_id") in crosswalk_ids:
            public_row = {
                key: value for key, value in row.items() if key != "review_status"
            }
            public_row["crosswalk_review_status"] = row["review_status"]
            existing_evidence = []
            for evidence_id in row["existing_evidence_ids"]:
                evidence = indexes["existing_evidence_by_id"][evidence_id]
                source = indexes["existing_source_by_key"][
                    (company_code, evidence["source_reference"])
                ]
                existing_evidence.append({**evidence, "existing_source": source})
            details.append(
                {
                    **public_row,
                    "status": "linked",
                    "existing_review_universe": indexes["universe_by_code"][
                        company_code
                    ],
                    "existing_evidence": existing_evidence,
                    "new_theme_evidence": new_evidence,
                    "theme_company_mapping": mapping_detail,
                    "manual_review_overlay": package["manual_review_overlay"].get(
                        company_code
                    ),
                }
            )
        else:
            details.append(
                {
                    **row,
                    "status": "coverage_gap",
                    "existing_review_universe": None,
                    "existing_evidence": [],
                    "new_theme_evidence": new_evidence,
                    "theme_company_mapping": mapping_detail,
                    "manual_review_overlay": None,
                }
            )
    return details


def _validate_guardrails(value: Any, path: str) -> None:
    if not isinstance(value, dict):
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path} must be object",
            code="INVALID_CROSSWALK_GUARDRAILS",
        )
    _require_exact_fields(value, GUARDRAIL_FIELDS, path)
    expected = {
        "readonly": True,
        "database_write_enabled": False,
        "csv_writeback_enabled": False,
        "manual_review_write_enabled": False,
        "used_for_signal": False,
        "used_for_admission": False,
        "auto_added_to_quality_pool": False,
    }
    if any(value[field] is not expected[field] for field in expected):
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path} violates read-only guardrails",
            code="CROSSWALK_GUARDRAIL_VIOLATION",
        )


def _reject_forbidden_fields(row: dict[str, Any], path: str) -> None:
    fields = sorted(FORBIDDEN_CROSSWALK_FIELDS.intersection(row))
    if fields:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path} contains forbidden fields: {fields}",
            code="FORBIDDEN_CROSSWALK_FIELD",
        )


def _claim_mapping_coverage(
    covered_mapping_ids: set[str], mapping_id: str, path: str
) -> None:
    if mapping_id in covered_mapping_ids:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path} duplicates Phase 4 mapping coverage: {mapping_id}",
            code="DUPLICATE_MAPPING_COVERAGE",
        )
    covered_mapping_ids.add(mapping_id)


def _safe_relative_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{field} must be non-empty relative path",
            code="INVALID_CROSSWALK_INPUT_PATH",
        )
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{field} must stay inside repository",
            code="CROSSWALK_INPUT_PATH_ESCAPE",
        )
    return path


def _read_csv(
    path: Path, *, required_columns: set[str], label: str
) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(required_columns - fieldnames)
        if missing:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{label} missing required columns: {missing}",
                code="MISSING_CSV_COLUMNS",
            )
        return [dict(row) for row in reader]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path.name}: root must be object",
            code="INVALID_CROSSWALK_ARTIFACT_ROOT",
        )
    return payload


def _load_optional_overlay(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    payload = _load_json(path)
    return {
        normalize_company_code(stock_code): value
        for stock_code, value in payload.items()
        if isinstance(value, dict)
    }


def _stable_row_digest(row: dict[str, Any], fields: tuple[str, ...]) -> str:
    payload = [
        _stable_source_reference(row.get(field))
        if field == "source_file"
        else str(row.get(field) or "").strip()
        for field in fields
    ]
    payload[0] = normalize_company_code(payload[0])
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _stable_source_reference(value: Any) -> str:
    normalized = str(value or "").strip().replace("\\", "/")
    marker = "/outputs/"
    if marker in normalized:
        return f"outputs/{normalized.split(marker, 1)[1]}"
    if normalized.startswith("outputs/"):
        return normalized
    return normalized


def _require_fields(row: dict[str, Any], fields: set[str], path: str) -> None:
    for field in sorted(fields):
        if field not in row:
            raise ThemeTechBottleneckCrosswalkValidationError(
                f"{path}.{field} is required",
                code="MISSING_REQUIRED_FIELD",
            )


def _require_exact_fields(row: dict[str, Any], fields: set[str], path: str) -> None:
    _require_fields(row, fields, path)
    unexpected = sorted(set(row) - fields)
    if unexpected:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path} contains unexpected fields: {unexpected}",
            code="UNEXPECTED_FIELD",
        )


def _require_object_list(
    row: dict[str, Any], field: str, path: str
) -> list[dict[str, Any]]:
    value = row.get(field)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.{field} must be array of objects",
            code="INVALID_LIST_FIELD",
        )
    return value


def _require_string_list(
    row: dict[str, Any], field: str, path: str, *, allow_empty: bool = False
) -> list[str]:
    value = row.get(field)
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or (not allow_empty and not value)
    ):
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.{field} must be array of non-empty strings",
            code="INVALID_LIST_FIELD",
        )
    return value


def _require_non_empty_string(row: dict[str, Any], field: str, path: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.{field} must be non-empty string",
            code="INVALID_STRING_FIELD",
        )
    return value


def _require_string(row: dict[str, Any], field: str, path: str) -> str:
    value = row.get(field)
    if not isinstance(value, str):
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.{field} must be string",
            code="INVALID_STRING_FIELD",
        )
    return value


def _check_enum(
    row: dict[str, Any], field: str, allowed: set[str], path: str
) -> None:
    value = row.get(field)
    if value not in allowed:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path}.{field} invalid: {value}",
            code="INVALID_ENUM_VALUE",
        )


def _unique_value(
    values: set[str], value: str, path: str, error_code: str
) -> None:
    if value in values:
        raise ThemeTechBottleneckCrosswalkValidationError(
            f"{path} duplicated: {value}",
            code=error_code,
        )
    values.add(value)


if __name__ == "__main__":
    main()
