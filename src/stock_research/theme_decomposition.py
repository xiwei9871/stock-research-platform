from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ARTIFACT_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "theme_decomposition"
ARTIFACT_VERSION = "theme_decomposition_v1_5"
SUPPORTED_ARTIFACT_VERSIONS = {
    ARTIFACT_VERSION,
    "theme_decomposition_v1_6",
}
HIGH_PRIORITY_SCORE_THRESHOLD = 4
STRONG_EVIDENCE_THRESHOLD = 3

SOURCE_TYPES = {
    "official_report",
    "official_article",
    "broker_report",
    "media_article",
    "video_claim",
    "social_post",
    "company_filing",
    "unknown",
}
ACCESS_LEVELS = {"public", "gated", "private_claimed", "unknown"}
RELIABILITY_LEVELS = {"S0", "S1", "S2", "S3", "S4"}
SOURCE_REVIEW_STATUSES = {"accepted", "needs_full_text", "lead_only", "rejected", "unknown"}
CLAIM_TYPES = {
    "demand_shock",
    "bottleneck",
    "value_capture",
    "supply_constraint",
    "localization",
    "company_mapping",
    "cost_structure",
    "tech_route",
    "valuation_signal",
    "catalyst",
    "risk",
}
EVIDENCE_STATUSES = {"verified", "partially_verified", "unverified", "contradicted"}
CLAIM_PLATFORM_USE_STATUSES = {"research_lead", "draft", "reviewed", "blocked"}
THEME_TYPES = {
    "ai_power",
    "humanoid_robotics",
    "ai_compute",
    "semiconductor_equipment",
    "industrial_software",
    "new_energy_storage",
    "other",
}
THEME_STATUSES = {"draft", "reviewed", "published"}
CREATED_FROM = {"video", "report", "manual", "mixed"}
NODE_TYPES = {
    "upstream_material",
    "core_component",
    "subsystem",
    "equipment",
    "infrastructure",
    "software",
    "service",
    "downstream_application",
}
NODE_REVIEW_STATUSES = {"draft", "reviewed", "needs_evidence", "blocked"}
VALUE_BASES = {
    "BOM_share",
    "ASP",
    "gross_margin",
    "scarcity",
    "integration_control",
    "customer_certification",
    "capacity_constraint",
    "technology_barrier",
}

THEME_FIELDS = {
    "theme_id",
    "theme_name",
    "theme_type",
    "summary",
    "status",
    "created_from",
    "last_updated",
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
CLAIM_FIELDS = {
    "claim_id",
    "theme_id",
    "source_id",
    "claim_text",
    "claim_type",
    "confidence",
    "evidence_status",
    "platform_use_status",
    "supporting_source_ids",
    "affected_theme_nodes",
}
NODE_FIELDS = {
    "node_id",
    "theme_id",
    "parent_node_id",
    "node_name",
    "node_type",
    "description",
    "value_capture_score",
    "bottleneck_score",
    "localization_gap_score",
    "supply_tightness_score",
    "evidence_strength",
    "node_review_status",
    "key_metrics",
    "overseas_leaders",
    "domestic_players",
    "related_stock_codes",
}
ASSESSMENT_FIELDS = {
    "node_id",
    "value_basis",
    "assessment_text",
    "rank",
    "evidence_ids",
    "uncertainty",
}
TEMPLATE_FIELDS = {
    "template_id",
    "theme_type",
    "steps",
    "required_dimensions",
    "optional_dimensions",
    "output_schema",
}
RESEARCH_KINDS = {"industry_chain_deep_research"}
RESEARCH_PROFILE_FIELDS = {
    "catalog_chain_id",
    "research_kind",
    "industry_stage",
    "central_conflict",
    "investment_summary",
    "value_flow_summary",
    "profit_pool_summary",
    "catalyst_claim_ids",
    "risk_claim_ids",
    "validation_signals",
    "evidence_gap_summary",
}


class ThemeDecompositionValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


def load_theme_package(artifact_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir is not None else ARTIFACT_DIR
    if not root.exists():
        raise ThemeDecompositionValidationError(f"artifact_dir not found: {root}")
    artifacts = [_load_json(path) for path in sorted(root.glob("*.json"))]
    if not artifacts:
        raise ThemeDecompositionValidationError(f"no theme decomposition artifacts found in {root}")
    _validate_artifact_versions(artifacts)
    package = {
        "artifact_dir": str(root),
        "artifact_versions": sorted({artifact["artifact_version"] for artifact in artifacts}),
        "themes": [artifact["theme"] for artifact in artifacts],
        "nodes": [node for artifact in artifacts for node in artifact.get("nodes", [])],
        "sources": [source for artifact in artifacts for source in artifact.get("sources", [])],
        "claims": [claim for artifact in artifacts for claim in artifact.get("claims", [])],
        "value_capture_assessments": [
            assessment
            for artifact in artifacts
            for assessment in artifact.get("value_capture_assessments", [])
        ],
        "decomposition_templates": [
            template
            for artifact in artifacts
            for template in artifact.get("decomposition_templates", [])
        ],
        "research_profiles": [
            {**artifact["research_profile"], "theme_id": artifact["theme"]["theme_id"]}
            for artifact in artifacts
            if artifact.get("research_profile") is not None
        ],
    }
    _validate_package(package)
    return package


def validate_theme_decomposition_artifact(
    artifact: dict[str, Any],
    *,
    expected_theme_id: str | None = None,
) -> set[str]:
    if not isinstance(artifact, dict):
        raise ThemeDecompositionValidationError("theme artifact must be an object")
    _validate_artifact_versions([artifact])
    theme = artifact.get("theme")
    if not isinstance(theme, dict):
        raise ThemeDecompositionValidationError("theme must be an object")
    nodes = artifact.get("nodes")
    if not isinstance(nodes, list):
        raise ThemeDecompositionValidationError("nodes must be a list")
    if any(not isinstance(node, dict) for node in nodes):
        raise ThemeDecompositionValidationError("nodes must contain only objects")
    return _validate_theme_and_nodes(
        [theme],
        nodes,
        expected_theme_id=expected_theme_id,
    )


def summarize_theme_package(package: dict[str, Any]) -> dict[str, Any]:
    nodes = package.get("nodes", [])
    sources = package.get("sources", [])
    claims = package.get("claims", [])
    return {
        "theme_count": len(package.get("themes", [])),
        "node_count": len(nodes),
        "source_count": len(sources),
        "claim_count": len(claims),
        "nodes_by_bottleneck_score": _nodes_by_score(nodes, "bottleneck_score"),
        "nodes_by_value_capture_score": _nodes_by_score(nodes, "value_capture_score"),
        "claims_by_evidence_status": _count_by(claims, "evidence_status"),
        "sources_by_reliability_level": _count_by(sources, "reliability_level"),
        "sources_by_review_status": _count_by(sources, "review_status"),
        "claims_by_platform_use_status": _count_by(claims, "platform_use_status"),
        "nodes_by_review_status": _count_by(nodes, "node_review_status"),
        "high_priority_evidence_gap_count": len(_high_priority_evidence_gap(nodes)),
        "high_priority_evidence_gap": _high_priority_evidence_gap(nodes),
    }


def load_theme(theme_id: str, artifact_dir: str | Path | None = None) -> dict[str, Any]:
    package = load_theme_package(artifact_dir)
    themes = [theme for theme in package["themes"] if theme["theme_id"] == theme_id]
    if not themes:
        raise ThemeDecompositionValidationError(f"theme_id not found: {theme_id}")
    theme_node_ids = {node["node_id"] for node in package["nodes"] if node["theme_id"] == theme_id}
    return {
        "theme": themes[0],
        "nodes": [node for node in package["nodes"] if node["theme_id"] == theme_id],
        "sources": [
            source
            for source in package["sources"]
            if source["source_id"] in _theme_source_ids(package, theme_id, theme_node_ids)
        ],
        "claims": [claim for claim in package["claims"] if claim["theme_id"] == theme_id],
        "value_capture_assessments": [
            assessment
            for assessment in package["value_capture_assessments"]
            if assessment["node_id"] in theme_node_ids
        ],
        "decomposition_templates": [
            template
            for template in package["decomposition_templates"]
            if template["theme_type"] == themes[0]["theme_type"]
        ],
        "research_profile": next(
            (
                {key: value for key, value in profile.items() if key != "theme_id"}
                for profile in package["research_profiles"]
                if profile["theme_id"] == theme_id
            ),
            None,
        ),
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-decomposition")
    parser.add_argument("--artifact-dir", default=str(ARTIFACT_DIR))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("summary")
    show = subparsers.add_parser("show")
    show.add_argument("--theme", required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            package = load_theme_package(args.artifact_dir)
            print(json.dumps({"status": "ok", **summarize_theme_package(package)}, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "summary":
            package = load_theme_package(args.artifact_dir)
            print(json.dumps(summarize_theme_package(package), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "show":
            theme = load_theme(args.theme, args.artifact_dir)
            print(json.dumps(theme, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except ThemeDecompositionValidationError as exc:
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
        raise ThemeDecompositionValidationError(f"{path.name}: root must be object")
    return payload


def _validate_artifact_versions(artifacts: list[dict[str, Any]]) -> None:
    for index, artifact in enumerate(artifacts):
        if "artifact_version" not in artifact:
            raise ThemeDecompositionValidationError(
                f"artifacts[{index}].artifact_version is required",
                code="MISSING_ARTIFACT_VERSION",
            )
        if artifact["artifact_version"] not in SUPPORTED_ARTIFACT_VERSIONS:
            raise ThemeDecompositionValidationError(
                f"artifacts[{index}].artifact_version unsupported: {artifact['artifact_version']}",
                code="UNSUPPORTED_ARTIFACT_VERSION",
            )


def _validate_package(package: dict[str, Any]) -> None:
    source_ids: set[str] = set()
    claim_ids: set[str] = set()
    source_by_id: dict[str, dict[str, Any]] = {}
    claim_by_id: dict[str, dict[str, Any]] = {}
    node_ids = _validate_theme_and_nodes(package["themes"], package["nodes"])
    theme_ids = {theme["theme_id"] for theme in package["themes"]}

    for index, source in enumerate(package["sources"]):
        _require_fields(source, SOURCE_FIELDS, f"sources[{index}]")
        _check_enum(source, "source_type", SOURCE_TYPES, f"sources[{index}]")
        _check_enum(source, "access_level", ACCESS_LEVELS, f"sources[{index}]")
        _check_enum(source, "reliability_level", RELIABILITY_LEVELS, f"sources[{index}]")
        _check_enum(
            source,
            "review_status",
            SOURCE_REVIEW_STATUSES,
            f"sources[{index}]",
            code="INVALID_SOURCE_REVIEW_STATUS",
        )
        if source["reliability_level"] == "S4" and source["review_status"] == "accepted":
            raise ThemeDecompositionValidationError(
                f"sources[{index}] S4 source cannot be accepted",
                code="S4_SOURCE_CANNOT_BE_ACCEPTED",
            )
        _check_unique(source_ids, source["source_id"], f"source.source_id {source['source_id']}")
        source_by_id[source["source_id"]] = source

    for index, claim in enumerate(package["claims"]):
        _require_fields(claim, CLAIM_FIELDS, f"claims[{index}]")
        _check_enum(claim, "claim_type", CLAIM_TYPES, f"claims[{index}]")
        _check_enum(claim, "evidence_status", EVIDENCE_STATUSES, f"claims[{index}]")
        _check_enum(
            claim,
            "platform_use_status",
            CLAIM_PLATFORM_USE_STATUSES,
            f"claims[{index}]",
            code="INVALID_CLAIM_PLATFORM_USE_STATUS",
        )
        _check_unique(claim_ids, claim["claim_id"], f"claim.claim_id {claim['claim_id']}")
        claim_by_id[claim["claim_id"]] = claim
        if claim["theme_id"] not in theme_ids:
            raise ThemeDecompositionValidationError(f"claims[{index}].theme_id references missing theme")
        if claim["source_id"] not in source_ids:
            raise ThemeDecompositionValidationError(f"claims[{index}].source_id references missing source")
        for source_id in claim.get("supporting_source_ids") or []:
            if source_id not in source_ids:
                raise ThemeDecompositionValidationError(f"claims[{index}].supporting_source_ids references missing source")
        for node_id in claim.get("affected_theme_nodes") or []:
            if node_id not in node_ids:
                raise ThemeDecompositionValidationError(f"claims[{index}].affected_theme_nodes references missing node")

    for index, assessment in enumerate(package["value_capture_assessments"]):
        _require_fields(assessment, ASSESSMENT_FIELDS, f"value_capture_assessments[{index}]")
        _check_enum(assessment, "value_basis", VALUE_BASES, f"value_capture_assessments[{index}]")
        if assessment["node_id"] not in node_ids:
            raise ThemeDecompositionValidationError(
                f"value_capture_assessments[{index}].node_id references missing node"
            )
        for evidence_id in assessment.get("evidence_ids") or []:
            if evidence_id not in source_ids and evidence_id not in claim_ids:
                raise ThemeDecompositionValidationError(
                    f"value_capture_assessments[{index}].evidence_ids references missing evidence"
                )

    for index, template in enumerate(package["decomposition_templates"]):
        _require_fields(template, TEMPLATE_FIELDS, f"decomposition_templates[{index}]")
        _check_enum(template, "theme_type", THEME_TYPES, f"decomposition_templates[{index}]")

    for index, profile in enumerate(package["research_profiles"]):
        path = f"research_profiles[{index}]"
        missing = sorted((RESEARCH_PROFILE_FIELDS | {"theme_id"}) - profile.keys())
        if missing:
            raise ThemeDecompositionValidationError(
                f"{path}.{missing[0]} is required",
                code="MISSING_RESEARCH_PROFILE_FIELD",
            )
        if profile["theme_id"] not in theme_ids:
            raise ThemeDecompositionValidationError(
                f"{path}.theme_id references missing theme",
                code="RESEARCH_PROFILE_THEME_NOT_FOUND",
            )
        _check_enum(profile, "research_kind", RESEARCH_KINDS, path)
        for field in (
            "catalog_chain_id",
            "industry_stage",
            "central_conflict",
            "investment_summary",
            "value_flow_summary",
            "profit_pool_summary",
            "evidence_gap_summary",
        ):
            if not isinstance(profile[field], str) or not profile[field].strip():
                raise ThemeDecompositionValidationError(
                    f"{path}.{field} must be a non-empty string",
                    code="INVALID_RESEARCH_PROFILE_FIELD",
                )
        for field in ("catalyst_claim_ids", "risk_claim_ids", "validation_signals"):
            if not isinstance(profile[field], list) or not all(
                isinstance(value, str) and value.strip() for value in profile[field]
            ):
                raise ThemeDecompositionValidationError(
                    f"{path}.{field} must be a list of non-empty strings",
                    code="INVALID_RESEARCH_PROFILE_FIELD",
                )
        for field in ("catalyst_claim_ids", "risk_claim_ids"):
            for claim_id in profile[field]:
                if claim_id not in claim_ids:
                    raise ThemeDecompositionValidationError(
                        f"{path}.{field} references missing claim: {claim_id}",
                        code="RESEARCH_PROFILE_CLAIM_NOT_FOUND",
                    )

    _validate_review_gates(
        package,
        source_by_id=source_by_id,
        claim_by_id=claim_by_id,
    )


def _validate_theme_and_nodes(
    themes: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    *,
    expected_theme_id: str | None = None,
) -> set[str]:
    theme_ids: set[str] = set()
    for index, theme in enumerate(themes):
        path = "theme" if len(themes) == 1 else f"themes[{index}]"
        _require_fields(theme, THEME_FIELDS, path)
        for field in ("theme_id", "theme_name", "summary", "last_updated"):
            _check_non_empty_string(theme, field, path)
        _check_enum(theme, "theme_type", THEME_TYPES, path)
        _check_enum(theme, "status", THEME_STATUSES, path)
        _check_enum(theme, "created_from", CREATED_FROM, path)
        _check_unique(theme_ids, theme["theme_id"], f"theme.theme_id {theme['theme_id']}")
    if expected_theme_id is not None and theme_ids != {expected_theme_id}:
        actual = next(iter(theme_ids), None)
        raise ThemeDecompositionValidationError(
            f"theme.theme_id must equal {expected_theme_id}: {actual}"
        )

    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        path = f"nodes[{index}]"
        _require_fields(node, NODE_FIELDS, path)
        for field in ("node_id", "theme_id", "node_name", "description"):
            _check_non_empty_string(node, field, path)
        if not isinstance(node["parent_node_id"], str):
            raise ThemeDecompositionValidationError(
                f"{path}.parent_node_id must be a string"
            )
        for field in (
            "key_metrics",
            "overseas_leaders",
            "domestic_players",
            "related_stock_codes",
        ):
            _check_string_list(node, field, path)
        _check_enum(node, "node_type", NODE_TYPES, path)
        _check_enum(
            node,
            "node_review_status",
            NODE_REVIEW_STATUSES,
            path,
            code="INVALID_NODE_REVIEW_STATUS",
        )
        if node["theme_id"] not in theme_ids:
            raise ThemeDecompositionValidationError(
                f"{path}.theme_id references missing theme"
            )
        for field in (
            "value_capture_score",
            "bottleneck_score",
            "localization_gap_score",
            "supply_tightness_score",
            "evidence_strength",
        ):
            _check_score(node, field, path)
        _check_unique(node_ids, node["node_id"], f"node.node_id {node['node_id']}")

    for index, node in enumerate(nodes):
        parent_node_id = node["parent_node_id"].strip()
        if parent_node_id and parent_node_id not in node_ids:
            raise ThemeDecompositionValidationError(
                f"nodes[{index}].parent_node_id references missing node"
            )
    return node_ids


def _validate_review_gates(
    package: dict[str, Any],
    *,
    source_by_id: dict[str, dict[str, Any]],
    claim_by_id: dict[str, dict[str, Any]],
) -> None:
    for index, claim in enumerate(package["claims"]):
        if claim["platform_use_status"] != "reviewed":
            continue
        evidence_sources = _claim_sources(claim, source_by_id)
        if any(source["review_status"] == "rejected" for source in evidence_sources):
            raise ThemeDecompositionValidationError(
                f"claims[{index}] reviewed claim uses rejected source",
                code="REVIEWED_CLAIM_USES_REJECTED_SOURCE",
            )
        if evidence_sources and all(source["reliability_level"] == "S4" for source in evidence_sources):
            raise ThemeDecompositionValidationError(
                f"claims[{index}] reviewed claim cannot be supported only by S4 sources",
                code="REVIEWED_CLAIM_S4_ONLY",
            )
        if not any(source["review_status"] == "accepted" for source in evidence_sources):
            raise ThemeDecompositionValidationError(
                f"claims[{index}] reviewed claim requires accepted source",
                code="REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE",
            )

    assessment_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assessment in package["value_capture_assessments"]:
        assessment_by_node[assessment["node_id"]].append(assessment)

    for index, node in enumerate(package["nodes"]):
        if node["node_review_status"] != "reviewed":
            continue
        if node["evidence_strength"] < STRONG_EVIDENCE_THRESHOLD:
            raise ThemeDecompositionValidationError(
                f"nodes[{index}] reviewed node requires evidence_strength >= {STRONG_EVIDENCE_THRESHOLD}",
                code="REVIEWED_NODE_REQUIRES_STRONG_EVIDENCE",
            )
        evidence_sources = _assessment_sources(
            assessment_by_node.get(node["node_id"], []),
            source_by_id=source_by_id,
            claim_by_id=claim_by_id,
        )
        if any(source["review_status"] == "rejected" for source in evidence_sources):
            raise ThemeDecompositionValidationError(
                f"nodes[{index}] reviewed node uses rejected source",
                code="REVIEWED_NODE_USES_REJECTED_SOURCE",
            )


def _claim_sources(
    claim: dict[str, Any],
    source_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    source_ids = {claim["source_id"], *(claim.get("supporting_source_ids") or [])}
    return [source_by_id[source_id] for source_id in sorted(source_ids)]


def _assessment_sources(
    assessments: list[dict[str, Any]],
    *,
    source_by_id: dict[str, dict[str, Any]],
    claim_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    source_ids: set[str] = set()
    for assessment in assessments:
        for evidence_id in assessment.get("evidence_ids") or []:
            if evidence_id in source_by_id:
                source_ids.add(evidence_id)
            elif evidence_id in claim_by_id:
                claim = claim_by_id[evidence_id]
                source_ids.add(claim["source_id"])
                source_ids.update(claim.get("supporting_source_ids") or [])
    return [source_by_id[source_id] for source_id in sorted(source_ids)]


def _theme_source_ids(package: dict[str, Any], theme_id: str, theme_node_ids: set[str]) -> set[str]:
    source_ids: set[str] = set()
    claim_ids: set[str] = set()
    for claim in package["claims"]:
        if claim["theme_id"] != theme_id:
            continue
        claim_ids.add(claim["claim_id"])
        source_ids.add(claim["source_id"])
        source_ids.update(claim.get("supporting_source_ids") or [])
    for assessment in package["value_capture_assessments"]:
        if assessment["node_id"] not in theme_node_ids:
            continue
        for evidence_id in assessment.get("evidence_ids") or []:
            if evidence_id not in claim_ids:
                source_ids.add(evidence_id)
    return source_ids


def _require_fields(row: dict[str, Any], fields: set[str], path: str) -> None:
    for field in sorted(fields):
        if field not in row:
            raise ThemeDecompositionValidationError(f"{path}.{field} is required")


def _check_enum(
    row: dict[str, Any],
    field: str,
    allowed: set[str],
    path: str,
    *,
    code: str = "INVALID_ENUM_VALUE",
) -> None:
    value = row.get(field)
    if value not in allowed:
        raise ThemeDecompositionValidationError(f"{path}.{field} invalid: {value}", code=code)


def _check_non_empty_string(row: dict[str, Any], field: str, path: str) -> None:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ThemeDecompositionValidationError(
            f"{path}.{field} must be a non-empty string"
        )


def _check_string_list(row: dict[str, Any], field: str, path: str) -> None:
    value = row.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ThemeDecompositionValidationError(
            f"{path}.{field} must be a list of strings"
        )


def _check_score(row: dict[str, Any], field: str, path: str) -> None:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 5:
        raise ThemeDecompositionValidationError(f"{path}.{field} must be integer 0-5")


def _check_unique(seen: set[str], value: Any, label: str) -> None:
    text = str(value or "").strip()
    if not text:
        raise ThemeDecompositionValidationError(f"{label} is required")
    if text in seen:
        raise ThemeDecompositionValidationError(f"{label} duplicated")
    seen.add(text)


def _nodes_by_score(nodes: list[dict[str, Any]], field: str) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        grouped[str(node[field])].append(node["node_id"])
    return {score: sorted(grouped[score]) for score in sorted(grouped.keys(), key=int, reverse=True)}


def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counter = Counter(str(row[field]) for row in rows)
    return {key: counter[key] for key in sorted(counter)}


def _high_priority_evidence_gap(nodes: list[dict[str, Any]]) -> list[str]:
    return sorted(
        node["node_id"]
        for node in nodes
        if node["value_capture_score"] >= HIGH_PRIORITY_SCORE_THRESHOLD
        and node["bottleneck_score"] >= HIGH_PRIORITY_SCORE_THRESHOLD
        and node["evidence_strength"] < STRONG_EVIDENCE_THRESHOLD
    )


if __name__ == "__main__":
    main()
