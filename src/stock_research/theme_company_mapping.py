from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from stock_research.theme_decomposition import (
    ACCESS_LEVELS,
    ARTIFACT_DIR as THEME_ARTIFACT_DIR,
    RELIABILITY_LEVELS,
    SOURCE_REVIEW_STATUSES,
    SOURCE_TYPES,
    load_theme_package,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
THEME_COMPANY_MAPPING_DIR = (
    REPOSITORY_ROOT / "artifacts" / "theme_decomposition" / "company_mappings"
)
MAPPING_ARTIFACT_VERSION = "theme_company_mapping_v1"
REVIEWED_CONFIDENCE_THRESHOLD = 0.7

MARKETS = {"CN", "HK", "US", "OTHER"}
MAPPING_TYPES = {
    "direct_product",
    "component_supplier",
    "equipment_supplier",
    "material_supplier",
    "system_integrator",
    "downstream_customer",
}
BUSINESS_STAGES = {"primary_business", "concept_exposure", "reserve_stage"}
REVENUE_RELEVANCE = {"material", "meaningful", "limited", "undisclosed", "none"}
BOTTLENECK_RELEVANCE = {"core", "adjacent", "unclear", "not_relevant"}
BUSINESS_MATERIALITY = {
    "core_business",
    "meaningful_segment",
    "emerging_segment",
    "reserve_only",
    "concept_only",
    "unknown",
}
MAPPING_REVIEW_STATUSES = {"reviewed", "draft", "research_lead", "blocked"}
EVIDENCE_TYPES = {
    "product_relationship",
    "service_relationship",
    "customer_relationship",
    "revenue_materiality",
    "customer_validation",
    "capacity_order",
    "business_stage",
    "company_mention",
}
DIRECT_RELATIONSHIP_EVIDENCE_TYPES = {
    "product_relationship",
    "service_relationship",
    "customer_relationship",
}

SOURCE_FIELDS = {
    "source_id",
    "source_type",
    "title",
    "publisher",
    "author",
    "publish_date",
    "url_or_ref",
    "access_level",
    "reliability_level",
    "review_status",
    "notes",
}
EVIDENCE_FIELDS = {
    "evidence_id",
    "source_id",
    "evidence_type",
    "excerpt_locator",
    "evidence_summary",
    "related_company_codes",
    "related_node_ids",
}
MAPPING_FIELDS = {
    "mapping_id",
    "theme_id",
    "company_code",
    "company_name",
    "market",
    "mapped_node_id",
    "mapping_type",
    "business_stage",
    "confidence",
    "evidence_ids",
    "revenue_relevance",
    "bottleneck_relevance",
    "business_materiality",
    "product_or_service",
    "relationship_summary",
    "review_status",
    "notes",
}
ARTIFACT_FIELDS = {
    "artifact_version",
    "theme_id",
    "sources",
    "evidence_items",
    "company_mappings",
}


class ThemeCompanyMappingValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


def load_theme_company_mapping_package(
    artifact_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir is not None else THEME_COMPANY_MAPPING_DIR
    theme_root = (
        Path(theme_artifact_dir) if theme_artifact_dir is not None else THEME_ARTIFACT_DIR
    )
    if not root.exists():
        raise ThemeCompanyMappingValidationError(
            f"company mapping directory not found: {root}",
            code="MAPPING_DIRECTORY_NOT_FOUND",
        )
    artifacts = [_load_json(path) for path in sorted(root.glob("*.json"))]
    if not artifacts:
        raise ThemeCompanyMappingValidationError(
            f"no company mapping artifacts found in {root}",
            code="NO_MAPPING_ARTIFACTS_FOUND",
        )
    theme_package = load_theme_package(theme_root)
    package = {
        "artifact_dir": str(root),
        "theme_artifact_dir": str(theme_root),
        "artifacts": artifacts,
        "themes": theme_package["themes"],
        "theme_nodes": theme_package["nodes"],
        "sources": [source for artifact in artifacts for source in artifact.get("sources", [])],
        "evidence_items": [
            evidence
            for artifact in artifacts
            for evidence in artifact.get("evidence_items", [])
        ],
        "company_mappings": [
            mapping
            for artifact in artifacts
            for mapping in artifact.get("company_mappings", [])
        ],
    }
    _validate_package(package)
    return package


def summarize_theme_company_mapping_package(package: dict[str, Any]) -> dict[str, Any]:
    mappings = package["company_mappings"]
    return {
        "artifact_count": len(package["artifacts"]),
        "theme_count": len({mapping["theme_id"] for mapping in mappings}),
        "company_count": len({mapping["company_code"] for mapping in mappings}),
        "mapping_count": len(mappings),
        "source_count": len(package["sources"]),
        "evidence_count": len(package["evidence_items"]),
        "mappings_by_review_status": _count_by(mappings, "review_status"),
        "mappings_by_business_stage": _count_by(mappings, "business_stage"),
        "mappings_by_revenue_relevance": _count_by(mappings, "revenue_relevance"),
        "mappings_by_node": _count_by(mappings, "mapped_node_id"),
    }


def load_theme_company_mappings(
    theme_id: str,
    artifact_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_company_mapping_package(artifact_dir, theme_artifact_dir)
    rows = [
        mapping
        for mapping in package["company_mappings"]
        if mapping["theme_id"] == theme_id
    ]
    if not rows:
        raise ThemeCompanyMappingValidationError(
            f"theme mapping not found: {theme_id}",
            code="THEME_MAPPING_NOT_FOUND",
        )
    return sorted(rows, key=lambda row: row["mapping_id"])


def load_company_theme_mappings(
    company_code: str,
    artifact_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_company_mapping_package(artifact_dir, theme_artifact_dir)
    rows = [
        mapping
        for mapping in package["company_mappings"]
        if mapping["company_code"] == company_code
    ]
    if not rows:
        raise ThemeCompanyMappingValidationError(
            f"company mapping not found: {company_code}",
            code="COMPANY_MAPPING_NOT_FOUND",
        )
    return sorted(rows, key=lambda row: row["mapping_id"])


def load_theme_company_mapping_details(
    theme_id: str,
    artifact_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_company_mapping_package(artifact_dir, theme_artifact_dir)
    rows = [
        mapping
        for mapping in package["company_mappings"]
        if mapping["theme_id"] == theme_id
    ]
    if not rows:
        raise ThemeCompanyMappingValidationError(
            f"theme mapping not found: {theme_id}",
            code="THEME_MAPPING_NOT_FOUND",
        )
    return _resolve_mapping_details(package, rows)


def load_company_theme_mapping_details(
    company_code: str,
    artifact_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_company_mapping_package(artifact_dir, theme_artifact_dir)
    rows = [
        mapping
        for mapping in package["company_mappings"]
        if mapping["company_code"] == company_code
    ]
    if not rows:
        raise ThemeCompanyMappingValidationError(
            f"company mapping not found: {company_code}",
            code="COMPANY_MAPPING_NOT_FOUND",
        )
    return _resolve_mapping_details(package, rows)


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-company-mapping")
    parser.add_argument("--artifact-dir", default=str(THEME_COMPANY_MAPPING_DIR))
    parser.add_argument("--theme-artifact-dir", default=str(THEME_ARTIFACT_DIR))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("summary")
    show_theme = subparsers.add_parser("show-theme")
    show_theme.add_argument("--theme-id", required=True)
    show_company = subparsers.add_parser("show-company")
    show_company.add_argument("--company-code", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command in {"validate", "summary"}:
            package = load_theme_company_mapping_package(
                args.artifact_dir, args.theme_artifact_dir
            )
            summary = summarize_theme_company_mapping_package(package)
            payload = {"status": "ok", **summary} if args.command == "validate" else summary
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "show-theme":
            rows = load_theme_company_mapping_details(
                args.theme_id, args.artifact_dir, args.theme_artifact_dir
            )
            print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "show-company":
            rows = load_company_theme_mapping_details(
                args.company_code, args.artifact_dir, args.theme_artifact_dir
            )
            print(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except ThemeCompanyMappingValidationError as exc:
        print(
            json.dumps(
                {"status": "error", "error_code": exc.code, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    raise AssertionError(f"unhandled command: {args.command}")


def main() -> None:
    raise SystemExit(cli())


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ThemeCompanyMappingValidationError(
            f"{path.name}: root must be object",
            code="INVALID_ARTIFACT_ROOT",
        )
    return payload


def _validate_package(package: dict[str, Any]) -> None:
    canonical_theme_ids = {theme["theme_id"] for theme in package["themes"]}
    node_theme_by_id = {
        node["node_id"]: node["theme_id"] for node in package["theme_nodes"]
    }
    artifact_theme_ids: set[str] = set()
    for index, artifact in enumerate(package["artifacts"]):
        path = f"artifacts[{index}]"
        _require_fields(artifact, ARTIFACT_FIELDS, path)
        if artifact.get("artifact_version") != MAPPING_ARTIFACT_VERSION:
            raise ThemeCompanyMappingValidationError(
                f"artifacts[{index}].artifact_version must be {MAPPING_ARTIFACT_VERSION}",
                code="UNSUPPORTED_MAPPING_ARTIFACT_VERSION",
            )
        theme_id = str(artifact.get("theme_id") or "").strip()
        if theme_id not in canonical_theme_ids:
            raise ThemeCompanyMappingValidationError(
                f"artifacts[{index}].theme_id references missing theme: {theme_id}",
                code="MAPPING_ARTIFACT_REFERENCES_MISSING_THEME",
            )
        artifact_theme_ids.add(theme_id)
        _validate_artifact_ownership(
            artifact,
            artifact_theme_id=theme_id,
            node_theme_by_id=node_theme_by_id,
            path=path,
        )

    source_by_id = _validate_sources(package["sources"])
    evidence_by_id = _validate_evidence_items(
        package["evidence_items"],
        source_by_id=source_by_id,
        node_theme_by_id=node_theme_by_id,
    )
    _validate_mappings(
        package["company_mappings"],
        artifact_theme_ids=artifact_theme_ids,
        node_theme_by_id=node_theme_by_id,
        source_by_id=source_by_id,
        evidence_by_id=evidence_by_id,
    )


def _validate_sources(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    source_by_id: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        path = f"sources[{index}]"
        _require_fields(source, SOURCE_FIELDS, path)
        _require_non_empty_string(source, "source_id", path)
        for field in ("title", "publisher", "publish_date", "url_or_ref"):
            _require_string(source, field, path)
        _require_string(source, "author", path)
        _require_string(source, "notes", path)
        _check_enum(source, "source_type", SOURCE_TYPES, path)
        _check_enum(source, "access_level", ACCESS_LEVELS, path)
        _check_enum(source, "reliability_level", RELIABILITY_LEVELS, path)
        _check_enum(source, "review_status", SOURCE_REVIEW_STATUSES, path)
        source_id = _unique_id(source_by_id, source["source_id"], f"{path}.source_id")
        if source["review_status"] == "accepted" and source["reliability_level"] in {
            "S0",
            "S1",
        }:
            for field in ("title", "publisher", "publish_date", "url_or_ref"):
                _require_non_empty_string(source, field, path)
        if source["reliability_level"] == "S4" and source["review_status"] == "accepted":
            raise ThemeCompanyMappingValidationError(
                f"{path} S4 source cannot be accepted",
                code="S4_SOURCE_CANNOT_BE_ACCEPTED",
            )
        source_by_id[source_id] = source
    return source_by_id


def _validate_evidence_items(
    evidence_items: list[dict[str, Any]],
    *,
    source_by_id: dict[str, dict[str, Any]],
    node_theme_by_id: dict[str, str],
) -> dict[str, dict[str, Any]]:
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for index, evidence in enumerate(evidence_items):
        path = f"evidence_items[{index}]"
        _require_fields(evidence, EVIDENCE_FIELDS, path)
        _require_non_empty_string(evidence, "evidence_id", path)
        _require_non_empty_string(evidence, "source_id", path)
        evidence_id = _unique_id(
            evidence_by_id, evidence["evidence_id"], f"{path}.evidence_id"
        )
        _check_enum(evidence, "evidence_type", EVIDENCE_TYPES, path)
        _require_string_list(evidence, "related_company_codes", path)
        _require_string_list(evidence, "related_node_ids", path)
        _require_non_empty_string(evidence, "excerpt_locator", path)
        _require_non_empty_string(evidence, "evidence_summary", path)
        if evidence["source_id"] not in source_by_id:
            raise ThemeCompanyMappingValidationError(
                f"{path}.source_id references missing source: {evidence['source_id']}",
                code="EVIDENCE_REFERENCES_MISSING_SOURCE",
            )
        if not evidence["related_company_codes"] or not evidence["related_node_ids"]:
            raise ThemeCompanyMappingValidationError(
                f"{path} requires company and node scope",
                code="EVIDENCE_REQUIRES_SCOPE",
            )
        for node_id in evidence["related_node_ids"]:
            if node_id not in node_theme_by_id:
                raise ThemeCompanyMappingValidationError(
                    f"{path}.related_node_ids references missing node: {node_id}",
                    code="EVIDENCE_REFERENCES_MISSING_NODE",
                )
        evidence_by_id[evidence_id] = evidence
    return evidence_by_id


def _validate_mappings(
    mappings: list[dict[str, Any]],
    *,
    artifact_theme_ids: set[str],
    node_theme_by_id: dict[str, str],
    source_by_id: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
) -> None:
    mapping_by_id: dict[str, dict[str, Any]] = {}
    company_node_pairs: set[tuple[str, str, str]] = set()
    for index, mapping in enumerate(mappings):
        path = f"company_mappings[{index}]"
        _require_fields(mapping, MAPPING_FIELDS, path)
        for field in (
            "mapping_id",
            "theme_id",
            "company_code",
            "company_name",
            "mapped_node_id",
            "product_or_service",
            "relationship_summary",
        ):
            _require_non_empty_string(mapping, field, path)
        _require_string(mapping, "notes", path)
        mapping_id = _unique_id(
            mapping_by_id, mapping["mapping_id"], f"{path}.mapping_id"
        )
        _check_enum(mapping, "market", MARKETS, path)
        _check_enum(mapping, "mapping_type", MAPPING_TYPES, path)
        _check_enum(mapping, "business_stage", BUSINESS_STAGES, path)
        _check_enum(mapping, "revenue_relevance", REVENUE_RELEVANCE, path)
        _check_enum(mapping, "bottleneck_relevance", BOTTLENECK_RELEVANCE, path)
        _check_enum(mapping, "business_materiality", BUSINESS_MATERIALITY, path)
        _check_enum(mapping, "review_status", MAPPING_REVIEW_STATUSES, path)
        _validate_company_code(mapping["company_code"], mapping["market"], path)
        confidence = mapping["confidence"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or confidence < 0
            or confidence > 1
        ):
            raise ThemeCompanyMappingValidationError(
                f"{path}.confidence must be number 0-1",
                code="INVALID_MAPPING_CONFIDENCE",
            )
        theme_id = mapping["theme_id"]
        node_id = mapping["mapped_node_id"]
        if theme_id not in artifact_theme_ids:
            raise ThemeCompanyMappingValidationError(
                f"{path}.theme_id is not declared by an artifact: {theme_id}",
                code="MAPPING_REFERENCES_MISSING_THEME",
            )
        if node_theme_by_id.get(node_id) != theme_id:
            raise ThemeCompanyMappingValidationError(
                f"{path}.mapped_node_id does not belong to theme: {node_id}",
                code="MAPPING_REFERENCES_MISSING_NODE",
            )
        pair = (theme_id, mapping["company_code"], node_id)
        if pair in company_node_pairs:
            raise ThemeCompanyMappingValidationError(
                f"{path} duplicates company-node mapping: {pair}",
                code="DUPLICATE_COMPANY_NODE_MAPPING",
            )
        company_node_pairs.add(pair)
        _require_string_list(mapping, "evidence_ids", path, allow_empty=True)
        if not mapping["evidence_ids"]:
            code = (
                "REVIEWED_MAPPING_REQUIRES_EVIDENCE"
                if mapping["review_status"] == "reviewed"
                else "MAPPING_REQUIRES_EVIDENCE"
            )
            raise ThemeCompanyMappingValidationError(
                f"{path} requires evidence",
                code=code,
            )
        if (
            mapping["business_stage"] == "concept_exposure"
            and mapping["review_status"] == "reviewed"
        ):
            raise ThemeCompanyMappingValidationError(
                f"{path} concept exposure cannot be reviewed",
                code="CONCEPT_EXPOSURE_CANNOT_BE_REVIEWED",
            )
        if mapping["business_stage"] == "concept_exposure" and (
            mapping["business_materiality"] != "concept_only"
            or mapping["revenue_relevance"] != "none"
        ):
            raise ThemeCompanyMappingValidationError(
                f"{path} concept exposure must be concept_only with no current revenue",
                code="CONCEPT_EXPOSURE_MATERIALITY_MISMATCH",
            )
        if mapping["business_stage"] == "reserve_stage" and (
            mapping["business_materiality"] != "reserve_only"
            or mapping["revenue_relevance"] not in {"none", "undisclosed"}
        ):
            raise ThemeCompanyMappingValidationError(
                f"{path} reserve stage must be reserve_only with no material revenue claim",
                code="RESERVE_STAGE_MATERIALITY_MISMATCH",
            )
        if mapping["business_stage"] == "primary_business" and mapping[
            "business_materiality"
        ] in {"reserve_only", "concept_only", "unknown"}:
            raise ThemeCompanyMappingValidationError(
                f"{path} primary business has incompatible materiality",
                code="PRIMARY_BUSINESS_MATERIALITY_MISMATCH",
            )
        mapping_evidence: list[dict[str, Any]] = []
        for evidence_id in mapping["evidence_ids"]:
            if evidence_id not in evidence_by_id:
                raise ThemeCompanyMappingValidationError(
                    f"{path}.evidence_ids references missing evidence: {evidence_id}",
                    code="MAPPING_REFERENCES_MISSING_EVIDENCE",
                )
            evidence = evidence_by_id[evidence_id]
            if (
                mapping["company_code"] not in evidence["related_company_codes"]
                or node_id not in evidence["related_node_ids"]
            ):
                raise ThemeCompanyMappingValidationError(
                    f"{path}.evidence_ids scope mismatch: {evidence_id}",
                    code="MAPPING_EVIDENCE_SCOPE_MISMATCH",
                )
            mapping_evidence.append(evidence)
        if mapping["review_status"] == "reviewed":
            _validate_reviewed_mapping(
                mapping,
                mapping_evidence=mapping_evidence,
                source_by_id=source_by_id,
                path=path,
            )
        mapping_by_id[mapping_id] = mapping


def _validate_reviewed_mapping(
    mapping: dict[str, Any],
    *,
    mapping_evidence: list[dict[str, Any]],
    source_by_id: dict[str, dict[str, Any]],
    path: str,
) -> None:
    if not mapping_evidence:
        raise ThemeCompanyMappingValidationError(
            f"{path} reviewed mapping requires evidence",
            code="REVIEWED_MAPPING_REQUIRES_EVIDENCE",
        )
    if mapping["confidence"] < REVIEWED_CONFIDENCE_THRESHOLD:
        raise ThemeCompanyMappingValidationError(
            f"{path} reviewed mapping requires confidence >= {REVIEWED_CONFIDENCE_THRESHOLD}",
            code="REVIEWED_MAPPING_REQUIRES_CONFIDENCE",
        )
    accepted_evidence = [
        evidence
        for evidence in mapping_evidence
        if source_by_id[evidence["source_id"]]["review_status"] == "accepted"
        and source_by_id[evidence["source_id"]]["reliability_level"] in {"S0", "S1"}
    ]
    if not accepted_evidence:
        raise ThemeCompanyMappingValidationError(
            f"{path} reviewed mapping requires accepted S0/S1 source",
            code="REVIEWED_MAPPING_REQUIRES_ACCEPTED_SOURCE",
        )
    if not any(
        evidence["evidence_type"] in DIRECT_RELATIONSHIP_EVIDENCE_TYPES
        for evidence in accepted_evidence
    ):
        raise ThemeCompanyMappingValidationError(
            f"{path} reviewed mapping requires accepted direct relationship evidence",
            code="REVIEWED_MAPPING_REQUIRES_DIRECT_RELATIONSHIP",
        )
    makes_materiality_claim = mapping["revenue_relevance"] in {
        "material",
        "meaningful",
        "limited",
    } or mapping["business_materiality"] in {
        "core_business",
        "meaningful_segment",
    }
    if makes_materiality_claim and not any(
        evidence["evidence_type"] == "revenue_materiality"
        for evidence in accepted_evidence
    ):
        raise ThemeCompanyMappingValidationError(
            f"{path} materiality claim requires accepted revenue evidence",
            code="REVIEWED_MAPPING_REQUIRES_MATERIALITY_EVIDENCE",
        )


def _validate_artifact_ownership(
    artifact: dict[str, Any],
    *,
    artifact_theme_id: str,
    node_theme_by_id: dict[str, str],
    path: str,
) -> None:
    sources = _require_object_list(artifact, "sources", path)
    evidence_items = _require_object_list(artifact, "evidence_items", path)
    mappings = _require_object_list(artifact, "company_mappings", path)

    source_ids = {str(source.get("source_id") or "").strip() for source in sources}
    evidence_ids = {
        str(evidence.get("evidence_id") or "").strip() for evidence in evidence_items
    }
    for index, mapping in enumerate(mappings):
        mapping_path = f"{path}.company_mappings[{index}]"
        if mapping.get("theme_id") != artifact_theme_id:
            raise ThemeCompanyMappingValidationError(
                f"{mapping_path}.theme_id must match artifact theme {artifact_theme_id}",
                code="MAPPING_THEME_OWNERSHIP_MISMATCH",
            )
        mapping_evidence_ids = mapping.get("evidence_ids")
        if not isinstance(mapping_evidence_ids, list):
            continue
        for evidence_id in mapping_evidence_ids:
            if evidence_id not in evidence_ids:
                raise ThemeCompanyMappingValidationError(
                    f"{mapping_path}.evidence_ids references evidence outside its artifact: {evidence_id}",
                    code="MAPPING_EVIDENCE_OWNERSHIP_MISMATCH",
                )

    for index, evidence in enumerate(evidence_items):
        evidence_path = f"{path}.evidence_items[{index}]"
        if evidence.get("source_id") not in source_ids:
            raise ThemeCompanyMappingValidationError(
                f"{evidence_path}.source_id references source outside its artifact",
                code="EVIDENCE_SOURCE_OWNERSHIP_MISMATCH",
            )
        related_node_ids = evidence.get("related_node_ids")
        if not isinstance(related_node_ids, list):
            continue
        for node_id in related_node_ids:
            if node_theme_by_id.get(node_id) != artifact_theme_id:
                raise ThemeCompanyMappingValidationError(
                    f"{evidence_path}.related_node_ids crosses artifact theme: {node_id}",
                    code="EVIDENCE_THEME_OWNERSHIP_MISMATCH",
                )


def _resolve_mapping_details(
    package: dict[str, Any], mappings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    source_by_id = {source["source_id"]: source for source in package["sources"]}
    evidence_by_id = {
        evidence["evidence_id"]: evidence for evidence in package["evidence_items"]
    }
    details: list[dict[str, Any]] = []
    for mapping in sorted(mappings, key=lambda row: row["mapping_id"]):
        evidence_details = []
        for evidence_id in mapping["evidence_ids"]:
            evidence = evidence_by_id[evidence_id]
            evidence_details.append(
                {**evidence, "source": source_by_id[evidence["source_id"]]}
            )
        details.append({**mapping, "evidence": evidence_details})
    return details


def _validate_company_code(company_code: Any, market: str, path: str) -> None:
    value = str(company_code or "").strip()
    if market == "CN" and not re.fullmatch(r"\d{6}\.(?:SH|SZ|BJ)", value):
        raise ThemeCompanyMappingValidationError(
            f"{path}.company_code invalid for CN market: {value}",
            code="INVALID_COMPANY_CODE",
        )
    if market != "CN" and not value:
        raise ThemeCompanyMappingValidationError(
            f"{path}.company_code is required",
            code="INVALID_COMPANY_CODE",
        )


def _require_fields(row: dict[str, Any], fields: set[str], path: str) -> None:
    for field in sorted(fields):
        if field not in row:
            raise ThemeCompanyMappingValidationError(
                f"{path}.{field} is required",
                code="MISSING_REQUIRED_FIELD",
            )


def _require_object_list(
    row: dict[str, Any], field: str, path: str
) -> list[dict[str, Any]]:
    value = row.get(field)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ThemeCompanyMappingValidationError(
            f"{path}.{field} must be an array of objects",
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
        raise ThemeCompanyMappingValidationError(
            f"{path}.{field} must be an array of non-empty strings",
            code="INVALID_LIST_FIELD",
        )
    return value


def _require_non_empty_string(
    row: dict[str, Any], field: str, path: str
) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ThemeCompanyMappingValidationError(
            f"{path}.{field} must be a non-empty string",
            code="INVALID_STRING_FIELD",
        )
    return value


def _require_string(row: dict[str, Any], field: str, path: str) -> str:
    value = row.get(field)
    if not isinstance(value, str):
        raise ThemeCompanyMappingValidationError(
            f"{path}.{field} must be a string",
            code="INVALID_STRING_FIELD",
        )
    return value


def _check_enum(
    row: dict[str, Any], field: str, allowed: set[str], path: str
) -> None:
    value = row.get(field)
    if value not in allowed:
        raise ThemeCompanyMappingValidationError(
            f"{path}.{field} invalid: {value}",
            code="INVALID_ENUM_VALUE",
        )


def _unique_id(
    rows_by_id: dict[str, dict[str, Any]], value: Any, path: str
) -> str:
    text = str(value or "").strip()
    if not text:
        raise ThemeCompanyMappingValidationError(
            f"{path} is required",
            code="MISSING_REQUIRED_FIELD",
        )
    if text in rows_by_id:
        code = "DUPLICATE_MAPPING_ID" if ".mapping_id" in path else "DUPLICATE_ID"
        raise ThemeCompanyMappingValidationError(
            f"{path} duplicated: {text}",
            code=code,
        )
    return text


def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(row[field]) for row in rows)
    return {key: counts[key] for key in sorted(counts)}


if __name__ == "__main__":
    main()
