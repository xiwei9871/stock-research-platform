from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from stock_research.theme_company_mapping import (
    THEME_COMPANY_MAPPING_DIR,
    load_theme_company_mapping_package,
)
from stock_research.theme_decomposition import (
    ARTIFACT_DIR as THEME_ARTIFACT_DIR,
    load_theme_package,
)
from stock_research.theme_tech_bottleneck_crosswalk import (
    REPOSITORY_ROOT,
    TECH_BOTTLENECK_CROSSWALK_DIR,
    load_company_crosswalk_details,
    load_theme_tech_bottleneck_crosswalk_package,
    normalize_company_code,
)


THEME_RESEARCH_PRIORITY_POLICY_DIR = (
    REPOSITORY_ROOT / "artifacts" / "theme_decomposition" / "priority_policies"
)
POLICY_VERSION = "theme_research_priority_policy_v1"

POLICY_FIELDS = {
    "policy_version",
    "score_scale",
    "node_deep_research_weights",
    "node_evidence_gap_weights",
    "company_priority_weights",
    "business_materiality_scores",
    "priority_bands",
    "classification_thresholds",
    "allowed_dimensions",
    "forbidden_dimensions",
    "guardrails",
}
SCORE_SCALE_FIELDS = {"component_min", "component_max", "normalized_max"}
NODE_DEEP_DIMENSIONS = {
    "value_capture_score",
    "bottleneck_score",
    "localization_gap_score",
    "supply_tightness_score",
    "evidence_strength",
}
NODE_GAP_DIMENSIONS = {
    "value_capture_score",
    "bottleneck_score",
    "localization_gap_score",
    "supply_tightness_score",
    "evidence_gap_score",
}
COMPANY_DIMENSIONS = {
    "value_capture_score",
    "bottleneck_score",
    "localization_gap_score",
    "supply_tightness_score",
    "evidence_strength",
    "company_relevance_score",
    "business_materiality",
}
ALL_ALLOWED_DIMENSIONS = NODE_DEEP_DIMENSIONS | NODE_GAP_DIMENSIONS | COMPANY_DIMENSIONS
FORBIDDEN_DIMENSIONS = {
    "price",
    "valuation",
    "return",
    "momentum",
    "freshness",
    "low_position",
    "technical_signal",
    "entry_timing",
}
MATERIALITY_LEVELS = {
    "core_business",
    "meaningful_segment",
    "emerging_segment",
    "reserve_only",
    "concept_only",
    "unknown",
}
PRIORITY_BAND_FIELDS = {"high_min", "medium_min"}
THRESHOLD_FIELDS = {
    "evidence_collection_min",
    "deep_research_min",
    "low_evidence_max",
    "strong_evidence_min",
    "company_queue_min",
}
GUARDRAIL_FIELDS = {
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "auto_reviewer_decision",
    "database_write_enabled",
    "price_inputs_allowed",
    "market_position_inputs_allowed",
}


class ThemeResearchPriorityValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


def load_theme_research_priority_package(
    policy_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
    theme_mapping_dir: str | Path | None = None,
    crosswalk_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    policy_root = (
        Path(policy_dir)
        if policy_dir is not None
        else THEME_RESEARCH_PRIORITY_POLICY_DIR
    )
    theme_root = (
        Path(theme_artifact_dir)
        if theme_artifact_dir is not None
        else THEME_ARTIFACT_DIR
    )
    mapping_root = (
        Path(theme_mapping_dir)
        if theme_mapping_dir is not None
        else THEME_COMPANY_MAPPING_DIR
    )
    crosswalk_root = (
        Path(crosswalk_dir)
        if crosswalk_dir is not None
        else TECH_BOTTLENECK_CROSSWALK_DIR
    )
    repository = (
        Path(repository_root) if repository_root is not None else REPOSITORY_ROOT
    )
    policy = _load_policy(policy_root)
    theme_package = load_theme_package(theme_root)
    mapping_package = load_theme_company_mapping_package(mapping_root, theme_root)
    crosswalk_package = load_theme_tech_bottleneck_crosswalk_package(
        artifact_dir=crosswalk_root,
        repository_root=repository,
        theme_mapping_dir=mapping_root,
        theme_artifact_dir=theme_root,
    )
    node_priorities = _build_node_priorities(theme_package["nodes"], policy)
    integration_by_mapping = _integration_by_mapping(crosswalk_package)
    company_priorities = _build_company_priorities(
        mapping_package["company_mappings"],
        node_priorities,
        integration_by_mapping,
        policy,
    )
    evidence_gaps = _build_evidence_gap_priorities(
        node_priorities, company_priorities
    )
    review_queue = _build_review_queue(node_priorities, company_priorities, policy)
    return {
        "policy_dir": str(policy_root),
        "policy": policy,
        "theme_package": theme_package,
        "mapping_package": mapping_package,
        "crosswalk_package": crosswalk_package,
        "node_priorities": node_priorities,
        "company_priorities": company_priorities,
        "evidence_gap_priorities": evidence_gaps,
        "review_queue": review_queue,
    }


def summarize_theme_research_priority_package(
    package: dict[str, Any],
) -> dict[str, Any]:
    node_rows = package["node_priorities"]
    company_rows = package["company_priorities"]
    queue = package["review_queue"]
    return {
        "theme_count": len({row["theme_id"] for row in node_rows}),
        "node_priority_count": len(node_rows),
        "company_priority_count": len(company_rows),
        "unique_company_count": len({row["company_code"] for row in company_rows}),
        "linked_company_count": sum(
            row["integration_status"] == "linked_existing_universe"
            for row in company_rows
        ),
        "coverage_gap_company_count": sum(
            row["integration_status"] == "coverage_gap" for row in company_rows
        ),
        "evidence_gap_priority_count": len(package["evidence_gap_priorities"]),
        "human_review_queue_count": len(queue),
        "node_priorities_by_class": _count_by(node_rows, "priority_class"),
        "company_priorities_by_band": _count_by(company_rows, "priority_band"),
        "review_queue_by_action": _count_by(queue, "recommended_action"),
    }


def list_theme_node_priorities(
    policy_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
    theme_mapping_dir: str | Path | None = None,
    crosswalk_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_research_priority_package(
        policy_dir,
        theme_artifact_dir,
        theme_mapping_dir,
        crosswalk_dir,
        repository_root,
    )
    return package["node_priorities"]


def list_company_research_priorities(
    policy_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
    theme_mapping_dir: str | Path | None = None,
    crosswalk_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_research_priority_package(
        policy_dir,
        theme_artifact_dir,
        theme_mapping_dir,
        crosswalk_dir,
        repository_root,
    )
    return package["company_priorities"]


def list_evidence_gap_priorities(
    policy_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
    theme_mapping_dir: str | Path | None = None,
    crosswalk_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_research_priority_package(
        policy_dir,
        theme_artifact_dir,
        theme_mapping_dir,
        crosswalk_dir,
        repository_root,
    )
    return package["evidence_gap_priorities"]


def build_human_review_queue(
    policy_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
    theme_mapping_dir: str | Path | None = None,
    crosswalk_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_research_priority_package(
        policy_dir,
        theme_artifact_dir,
        theme_mapping_dir,
        crosswalk_dir,
        repository_root,
    )
    return package["review_queue"]


def load_company_priority_details(
    company_code: str,
    policy_dir: str | Path | None = None,
    theme_artifact_dir: str | Path | None = None,
    theme_mapping_dir: str | Path | None = None,
    crosswalk_dir: str | Path | None = None,
    repository_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    package = load_theme_research_priority_package(
        policy_dir,
        theme_artifact_dir,
        theme_mapping_dir,
        crosswalk_dir,
        repository_root,
    )
    query = str(company_code or "").strip().upper()
    has_market_suffix = "." in query
    numeric_query = query.split(".")[0]
    priorities = [
        row
        for row in package["company_priorities"]
        if (
            row["company_code"].upper() == query
            if has_market_suffix
            else row["company_code"].split(".")[0] == numeric_query
        )
    ]
    if not priorities:
        raise ThemeResearchPriorityValidationError(
            f"company priority not found: {company_code}",
            code="COMPANY_PRIORITY_NOT_FOUND",
        )
    mapping_by_id = {
        row["mapping_id"]: row
        for row in package["mapping_package"]["company_mappings"]
    }
    node_by_id = {
        row["node_id"]: row for row in package["theme_package"]["nodes"]
    }
    crosswalk_details = load_company_crosswalk_details(
        company_code,
        artifact_dir=crosswalk_dir,
        repository_root=repository_root,
        theme_mapping_dir=theme_mapping_dir,
        theme_artifact_dir=theme_artifact_dir,
    )
    crosswalk_by_mapping = {row["mapping_id"]: row for row in crosswalk_details}
    return [
        {
            **row,
            "company_mapping": mapping_by_id[row["mapping_id"]],
            "theme_node": node_by_id[row["theme_node_id"]],
            "crosswalk": crosswalk_by_mapping.get(
                row["mapping_id"],
                {
                    "status": "theme_only",
                    "mapping_id": row["mapping_id"],
                    "theme_id": row["theme_id"],
                    "company_code": row["company_code"],
                    "integration_status": row["integration_status"],
                    "existing_review_context": row["existing_review_context"],
                },
            ),
        }
        for row in priorities
    ]


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="theme-research-priority")
    parser.add_argument("--policy-dir", default=str(THEME_RESEARCH_PRIORITY_POLICY_DIR))
    parser.add_argument("--theme-artifact-dir", default=str(THEME_ARTIFACT_DIR))
    parser.add_argument("--theme-mapping-dir", default=str(THEME_COMPANY_MAPPING_DIR))
    parser.add_argument("--crosswalk-dir", default=str(TECH_BOTTLENECK_CROSSWALK_DIR))
    parser.add_argument("--repository-root", default=str(REPOSITORY_ROOT))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("summary")
    subparsers.add_parser("theme-nodes")
    subparsers.add_parser("companies")
    subparsers.add_parser("evidence-gaps")
    subparsers.add_parser("review-queue")
    show_company = subparsers.add_parser("show-company")
    show_company.add_argument("--company-code", required=True)
    args = parser.parse_args(argv)
    common = {
        "policy_dir": args.policy_dir,
        "theme_artifact_dir": args.theme_artifact_dir,
        "theme_mapping_dir": args.theme_mapping_dir,
        "crosswalk_dir": args.crosswalk_dir,
        "repository_root": args.repository_root,
    }
    try:
        if args.command in {"validate", "summary"}:
            package = load_theme_research_priority_package(**common)
            summary = summarize_theme_research_priority_package(package)
            payload = {"status": "ok", **summary} if args.command == "validate" else summary
        elif args.command == "theme-nodes":
            payload = list_theme_node_priorities(**common)
        elif args.command == "companies":
            payload = list_company_research_priorities(**common)
        elif args.command == "evidence-gaps":
            payload = list_evidence_gap_priorities(**common)
        elif args.command == "review-queue":
            payload = build_human_review_queue(**common)
        elif args.command == "show-company":
            payload = load_company_priority_details(args.company_code, **common)
        else:
            raise AssertionError(f"unhandled command: {args.command}")
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except ThemeResearchPriorityValidationError as exc:
        print(
            json.dumps(
                {"status": "error", "error_code": exc.code, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    except (ValueError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_code": getattr(exc, "code", "UPSTREAM_INPUT_ERROR"),
                    "message": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


def main() -> None:
    raise SystemExit(cli())


def _load_policy(policy_dir: Path) -> dict[str, Any]:
    if not policy_dir.exists():
        raise ThemeResearchPriorityValidationError(
            f"priority policy directory not found: {policy_dir}",
            code="PRIORITY_POLICY_DIRECTORY_NOT_FOUND",
        )
    paths = sorted(policy_dir.glob("*.json"))
    if len(paths) != 1:
        raise ThemeResearchPriorityValidationError(
            f"expected exactly one priority policy, found {len(paths)}",
            code="PRIORITY_POLICY_COUNT_MISMATCH",
        )
    with paths[0].open(encoding="utf-8") as handle:
        policy = json.load(handle)
    if not isinstance(policy, dict):
        raise ThemeResearchPriorityValidationError(
            "priority policy root must be object",
            code="INVALID_PRIORITY_POLICY_ROOT",
        )
    _require_exact_fields(policy, POLICY_FIELDS, "policy")
    if policy["policy_version"] != POLICY_VERSION:
        raise ThemeResearchPriorityValidationError(
            f"policy_version must be {POLICY_VERSION}",
            code="UNSUPPORTED_PRIORITY_POLICY_VERSION",
        )
    _validate_policy(policy)
    return policy


def _validate_policy(policy: dict[str, Any]) -> None:
    scale = policy["score_scale"]
    if not isinstance(scale, dict):
        raise ThemeResearchPriorityValidationError(
            "score_scale must be object",
            code="INVALID_SCORE_SCALE",
        )
    _require_exact_fields(scale, SCORE_SCALE_FIELDS, "policy.score_scale")
    expected_scale = {"component_min": 0, "component_max": 5, "normalized_max": 100}
    if (
        any(
            isinstance(scale[field], bool)
            or not isinstance(scale[field], (int, float))
            or not math.isfinite(float(scale[field]))
            for field in SCORE_SCALE_FIELDS
        )
        or scale != expected_scale
    ):
        raise ThemeResearchPriorityValidationError(
            "score_scale must be 0-5 normalized to 100",
            code="INVALID_SCORE_SCALE",
        )
    _validate_weights(
        policy["node_deep_research_weights"],
        NODE_DEEP_DIMENSIONS,
        "policy.node_deep_research_weights",
    )
    _validate_weights(
        policy["node_evidence_gap_weights"],
        NODE_GAP_DIMENSIONS,
        "policy.node_evidence_gap_weights",
    )
    _validate_weights(
        policy["company_priority_weights"],
        COMPANY_DIMENSIONS,
        "policy.company_priority_weights",
    )
    materiality = policy["business_materiality_scores"]
    if not isinstance(materiality, dict) or set(materiality) != MATERIALITY_LEVELS:
        raise ThemeResearchPriorityValidationError(
            "business materiality mapping must cover every Phase 4 level",
            code="INCOMPLETE_MATERIALITY_MAPPING",
        )
    for key, value in materiality.items():
        _validate_component_score(value, f"policy.business_materiality_scores.{key}")
    bands = policy["priority_bands"]
    _require_exact_mapping(bands, PRIORITY_BAND_FIELDS, "policy.priority_bands")
    high_min = _validate_normalized_score(bands["high_min"], "priority_bands.high_min")
    medium_min = _validate_normalized_score(
        bands["medium_min"], "priority_bands.medium_min"
    )
    if high_min <= medium_min:
        raise ThemeResearchPriorityValidationError(
            "high priority band must exceed medium band",
            code="INVALID_PRIORITY_BANDS",
        )
    thresholds = policy["classification_thresholds"]
    _require_exact_mapping(
        thresholds, THRESHOLD_FIELDS, "policy.classification_thresholds"
    )
    for field in ("evidence_collection_min", "deep_research_min", "company_queue_min"):
        _validate_normalized_score(thresholds[field], f"classification_thresholds.{field}")
    for field in ("low_evidence_max", "strong_evidence_min"):
        _validate_component_score(thresholds[field], f"classification_thresholds.{field}")
    if thresholds["low_evidence_max"] >= thresholds["strong_evidence_min"]:
        raise ThemeResearchPriorityValidationError(
            "low and strong evidence thresholds overlap",
            code="INVALID_CLASSIFICATION_THRESHOLDS",
        )
    allowed = policy["allowed_dimensions"]
    if not isinstance(allowed, list) or set(allowed) != ALL_ALLOWED_DIMENSIONS:
        raise ThemeResearchPriorityValidationError(
            "allowed_dimensions must match Phase 6 dimensions",
            code="INVALID_ALLOWED_DIMENSIONS",
        )
    forbidden = policy["forbidden_dimensions"]
    if not isinstance(forbidden, list) or not FORBIDDEN_DIMENSIONS.issubset(forbidden):
        raise ThemeResearchPriorityValidationError(
            "forbidden_dimensions must include all market/trading dimensions",
            code="INCOMPLETE_FORBIDDEN_DIMENSIONS",
        )
    _validate_guardrails(policy["guardrails"])


def _validate_weights(value: Any, expected: set[str], path: str) -> None:
    if not isinstance(value, dict):
        raise ThemeResearchPriorityValidationError(
            f"{path} must be object",
            code="INVALID_WEIGHT_SCHEMA",
        )
    forbidden = set(value).intersection(FORBIDDEN_DIMENSIONS)
    if forbidden:
        raise ThemeResearchPriorityValidationError(
            f"{path} contains forbidden dimensions: {sorted(forbidden)}",
            code="FORBIDDEN_PRIORITY_DIMENSION",
        )
    if set(value) != expected:
        raise ThemeResearchPriorityValidationError(
            f"{path} dimensions do not match policy contract",
            code="INVALID_WEIGHT_SCHEMA",
        )
    total = 0.0
    for field, weight in value.items():
        if (
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or not math.isfinite(float(weight))
            or weight < 0
            or weight > 1
        ):
            raise ThemeResearchPriorityValidationError(
                f"{path}.{field} must be number 0-1",
                code="INVALID_WEIGHT_VALUE",
            )
        total += float(weight)
    if not math.isclose(total, 1.0, abs_tol=1e-9):
        raise ThemeResearchPriorityValidationError(
            f"{path} weights must sum to 1, got {total}",
            code="INVALID_WEIGHT_SUM",
        )


def _validate_guardrails(value: Any) -> None:
    expected = {
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "auto_reviewer_decision": False,
        "database_write_enabled": False,
        "price_inputs_allowed": False,
        "market_position_inputs_allowed": False,
    }
    _require_exact_mapping(value, GUARDRAIL_FIELDS, "policy.guardrails")
    if any(value[field] is not expected[field] for field in expected):
        raise ThemeResearchPriorityValidationError(
            "priority policy violates research-only guardrails",
            code="PRIORITY_GUARDRAIL_VIOLATION",
        )


def _build_node_priorities(
    nodes: list[dict[str, Any]], policy: dict[str, Any]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    thresholds = policy["classification_thresholds"]
    for node in nodes:
        deep_components = {field: node[field] for field in NODE_DEEP_DIMENSIONS}
        gap_components = {
            "value_capture_score": node["value_capture_score"],
            "bottleneck_score": node["bottleneck_score"],
            "localization_gap_score": node["localization_gap_score"],
            "supply_tightness_score": node["supply_tightness_score"],
            "evidence_gap_score": 5 - node["evidence_strength"],
        }
        for field, value in deep_components.items():
            _validate_component_score(value, f"node.{node['node_id']}.{field}")
        deep_score, deep_weighted = _weighted_score(
            deep_components, policy["node_deep_research_weights"]
        )
        gap_score, gap_weighted = _weighted_score(
            gap_components, policy["node_evidence_gap_weights"]
        )
        if (
            node["evidence_strength"] <= thresholds["low_evidence_max"]
            and gap_score >= thresholds["evidence_collection_min"]
        ):
            priority_class = "evidence_collection_priority"
            action = "collect_node_evidence"
            priority_score = gap_score
        elif (
            node["evidence_strength"] >= thresholds["strong_evidence_min"]
            and deep_score >= thresholds["deep_research_min"]
        ):
            priority_class = "deep_research_priority"
            action = "deep_node_research"
            priority_score = deep_score
        else:
            priority_class = "monitor"
            action = "monitor"
            priority_score = max(deep_score, gap_score)
        rows.append(
            {
                "theme_id": node["theme_id"],
                "node_id": node["node_id"],
                "node_name": node["node_name"],
                "node_review_status": node["node_review_status"],
                "value_capture_score": node["value_capture_score"],
                "bottleneck_score": node["bottleneck_score"],
                "localization_gap_score": node["localization_gap_score"],
                "supply_tightness_score": node["supply_tightness_score"],
                "evidence_strength": node["evidence_strength"],
                "evidence_gap_score": gap_components["evidence_gap_score"],
                "deep_research_priority_score": deep_score,
                "evidence_gap_priority_score": gap_score,
                "deep_research_weighted_components": deep_weighted,
                "evidence_gap_weighted_components": gap_weighted,
                "priority_score": priority_score,
                "priority_band": _priority_band(priority_score, policy),
                "priority_class": priority_class,
                "recommended_action": action,
                "rationale_codes": _node_rationale_codes(node),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return sorted(
        rows,
        key=lambda row: (-row["priority_score"], row["theme_id"], row["node_id"]),
    )


def _build_company_priorities(
    mappings: list[dict[str, Any]],
    node_priorities: list[dict[str, Any]],
    integration_by_mapping: dict[str, dict[str, Any]],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    node_by_id = {row["node_id"]: row for row in node_priorities}
    rows: list[dict[str, Any]] = []
    for mapping in mappings:
        node = node_by_id[mapping["mapped_node_id"]]
        materiality = policy["business_materiality_scores"][
            mapping["business_materiality"]
        ]
        relevance = round(mapping["confidence"] * 5, 2)
        components = {
            "value_capture_score": node["value_capture_score"],
            "bottleneck_score": node["bottleneck_score"],
            "localization_gap_score": node["localization_gap_score"],
            "supply_tightness_score": node["supply_tightness_score"],
            "evidence_strength": node["evidence_strength"],
            "company_relevance_score": relevance,
            "business_materiality": materiality,
        }
        score, weighted = _weighted_score(
            components, policy["company_priority_weights"]
        )
        integration = integration_by_mapping.get(mapping["mapping_id"])
        if integration is None:
            integration = {
                "integration_status": "theme_only",
                "integration_ref": "",
                "existing_review_context": {
                    "status": "not_crosswalked",
                    "reviewer_decision": "",
                },
            }
        action = _company_action(node, score, integration["integration_status"], policy)
        rationale = _company_rationale_codes(
            node, relevance, materiality, integration["integration_status"]
        )
        rows.append(
            {
                "theme_id": mapping["theme_id"],
                "theme_node_id": mapping["mapped_node_id"],
                "mapping_id": mapping["mapping_id"],
                "company_code": mapping["company_code"],
                "company_name": mapping["company_name"],
                "mapping_review_status": mapping["review_status"],
                "business_materiality": mapping["business_materiality"],
                "business_materiality_score": materiality,
                "company_relevance_score": relevance,
                "score_components": components,
                "weighted_components": weighted,
                "company_research_priority_score": score,
                "priority_band": _priority_band(score, policy),
                "recommended_action": action,
                "rationale_codes": rationale,
                "integration_status": integration["integration_status"],
                "integration_ref": integration["integration_ref"],
                "existing_review_context": integration["existing_review_context"],
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -row["company_research_priority_score"],
            row["company_code"],
            row["mapping_id"],
        ),
    )


def _build_evidence_gap_priorities(
    node_rows: list[dict[str, Any]],
    company_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mappings_by_node: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in company_rows:
        key = (row["theme_id"], row["theme_node_id"])
        mappings_by_node.setdefault(key, []).append(
            {
                "mapping_id": row["mapping_id"],
                "company_code": row["company_code"],
                "company_name": row["company_name"],
                "integration_status": row["integration_status"],
                "company_research_priority_score": row[
                    "company_research_priority_score"
                ],
                "recommended_action": row["recommended_action"],
            }
        )
    result: list[dict[str, Any]] = []
    for row in node_rows:
        if row["priority_class"] != "evidence_collection_priority":
            continue
        affected = sorted(
            mappings_by_node.get((row["theme_id"], row["node_id"]), []),
            key=lambda mapping: (mapping["company_code"], mapping["mapping_id"]),
        )
        result.append(
            {
                **row,
                "affected_mapping_count": len(affected),
                "affected_company_mappings": affected,
            }
        )
    return result


def _build_review_queue(
    node_rows: list[dict[str, Any]],
    company_rows: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for row in node_rows:
        if row["recommended_action"] == "monitor":
            continue
        queue.append(
            {
                "queue_item_id": f"theme_node_priority:{row['theme_id']}:{row['node_id']}",
                "item_type": "theme_node",
                "theme_id": row["theme_id"],
                "theme_node_id": row["node_id"],
                "company_code": "",
                "priority_score": row["priority_score"],
                "priority_band": row["priority_band"],
                "recommended_action": row["recommended_action"],
                "rationale_codes": row["rationale_codes"],
                "human_review_status": "pending_human_review",
                "integration_status": "not_applicable",
                "source_refs": [f"theme_node:{row['theme_id']}:{row['node_id']}"],
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    for row in company_rows:
        if row["recommended_action"] == "monitor":
            continue
        queue.append(
            {
                "queue_item_id": f"company_priority:{row['mapping_id']}",
                "item_type": "company_mapping",
                "theme_id": row["theme_id"],
                "theme_node_id": row["theme_node_id"],
                "company_code": row["company_code"],
                "priority_score": row["company_research_priority_score"],
                "priority_band": row["priority_band"],
                "recommended_action": row["recommended_action"],
                "rationale_codes": row["rationale_codes"],
                "human_review_status": "pending_human_review",
                "integration_status": row["integration_status"],
                "existing_review_context": row["existing_review_context"],
                "source_refs": [row["mapping_id"], row["integration_ref"]],
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return sorted(
        queue,
        key=lambda row: (-row["priority_score"], row["queue_item_id"]),
    )


def _integration_by_mapping(package: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in package["crosswalks"]:
        company_code = normalize_company_code(row["company_code"])
        universe_row = package["indexes"]["universe_by_code"][company_code]
        overlay = package["manual_review_overlay"].get(company_code)
        if overlay:
            review_context = {
                "status": str(overlay.get("review_status") or "reviewed"),
                "reviewer_decision": str(overlay.get("reviewer_decision") or ""),
            }
        else:
            review_context = {
                "status": str(
                    universe_row.get("frontend_review_status") or "pending_review"
                ),
                "reviewer_decision": str(universe_row.get("reviewer_decision") or ""),
            }
        result[row["mapping_id"]] = {
            "integration_status": "linked_existing_universe",
            "integration_ref": row["crosswalk_id"],
            "existing_review_context": review_context,
        }
    for row in package["coverage_gaps"]:
        result[row["mapping_id"]] = {
            "integration_status": "coverage_gap",
            "integration_ref": row["gap_id"],
            "existing_review_context": {
                "status": "not_in_existing_universe",
                "reviewer_decision": "",
            },
        }
    return result


def _weighted_score(
    components: dict[str, float], weights: dict[str, float]
) -> tuple[float, dict[str, float]]:
    weighted = {
        field: round(float(components[field]) * float(weights[field]) * 20, 2)
        for field in weights
    }
    return round(sum(weighted.values()), 2), weighted


def _priority_band(score: float, policy: dict[str, Any]) -> str:
    bands = policy["priority_bands"]
    if score >= bands["high_min"]:
        return "high"
    if score >= bands["medium_min"]:
        return "medium"
    return "low"


def _company_action(
    node: dict[str, Any],
    score: float,
    integration_status: str,
    policy: dict[str, Any],
) -> str:
    if integration_status == "coverage_gap":
        return "review_crosswalk_coverage_gap"
    if node["evidence_strength"] <= policy["classification_thresholds"][
        "low_evidence_max"
    ]:
        return "strengthen_node_evidence_for_company"
    if score >= policy["classification_thresholds"]["company_queue_min"]:
        return "deep_company_research"
    return "monitor"


def _node_rationale_codes(node: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    if node["value_capture_score"] >= 4:
        codes.append("high_value_capture")
    if node["bottleneck_score"] >= 4:
        codes.append("high_bottleneck")
    if node["localization_gap_score"] >= 3:
        codes.append("localization_gap")
    if node["supply_tightness_score"] >= 4:
        codes.append("supply_tightness")
    if node["evidence_strength"] <= 2:
        codes.append("low_evidence")
    if node["evidence_strength"] >= 3:
        codes.append("strong_evidence")
    return codes


def _company_rationale_codes(
    node: dict[str, Any],
    relevance: float,
    materiality: float,
    integration_status: str,
) -> list[str]:
    codes = _node_rationale_codes(node)
    if relevance >= 4:
        codes.append("high_company_relevance")
    if materiality >= 4:
        codes.append("meaningful_business_materiality")
    if integration_status == "coverage_gap":
        codes.append("crosswalk_coverage_gap")
    return codes


def _validate_component_score(value: Any, path: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
        or value > 5
    ):
        raise ThemeResearchPriorityValidationError(
            f"{path} must be number 0-5",
            code="INVALID_COMPONENT_SCORE",
        )
    return float(value)


def _validate_normalized_score(value: Any, path: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
        or value > 100
    ):
        raise ThemeResearchPriorityValidationError(
            f"{path} must be number 0-100",
            code="INVALID_NORMALIZED_SCORE",
        )
    return float(value)


def _require_exact_mapping(value: Any, fields: set[str], path: str) -> None:
    if not isinstance(value, dict):
        raise ThemeResearchPriorityValidationError(
            f"{path} must be object",
            code="INVALID_POLICY_SCHEMA",
        )
    _require_exact_fields(value, fields, path)


def _require_exact_fields(row: dict[str, Any], fields: set[str], path: str) -> None:
    missing = sorted(fields - set(row))
    if missing:
        raise ThemeResearchPriorityValidationError(
            f"{path} missing fields: {missing}",
            code="MISSING_REQUIRED_FIELD",
        )
    unexpected = sorted(set(row) - fields)
    if unexpected:
        raise ThemeResearchPriorityValidationError(
            f"{path} contains unexpected fields: {unexpected}",
            code="UNEXPECTED_FIELD",
        )


def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(row[field]) for row in rows)
    return {key: counts[key] for key in sorted(counts)}


if __name__ == "__main__":
    main()
