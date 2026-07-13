from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Iterable

from stock_research.theme_company_mapping import load_theme_company_mapping_package
from stock_research.theme_decomposition import load_theme, load_theme_package
from stock_research.theme_research_db_models import ThemeResearchDomainError


_FAMILY_KEYS: dict[str, tuple[str, ...]] = {
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


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _content_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _identity(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    return "|".join(str(row[key]) for key in keys)


def _sorted_rows(rows: Iterable[dict[str, Any]], keys: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    return tuple(sorted((copy.deepcopy(row) for row in rows), key=lambda row: _identity(row, keys)))


@dataclass(frozen=True)
class NormalizedThemeResearchPackage:
    artifact_version: str
    package_sha256: str
    themes: tuple[dict[str, Any], ...]
    nodes: tuple[dict[str, Any], ...]
    sources: tuple[dict[str, Any], ...]
    theme_sources: tuple[dict[str, Any], ...]
    claims: tuple[dict[str, Any], ...]
    claim_sources: tuple[dict[str, Any], ...]
    claim_nodes: tuple[dict[str, Any], ...]
    assessments: tuple[dict[str, Any], ...]
    assessment_evidence: tuple[dict[str, Any], ...]
    company_mappings: tuple[dict[str, Any], ...]
    mapping_evidence_items: tuple[dict[str, Any], ...]
    company_mapping_evidence: tuple[dict[str, Any], ...]

    @classmethod
    def build(
        cls,
        *,
        artifact_version: str,
        themes: Iterable[dict[str, Any]],
        nodes: Iterable[dict[str, Any]],
        sources: Iterable[dict[str, Any]],
        theme_sources: Iterable[dict[str, Any]],
        claims: Iterable[dict[str, Any]],
        claim_sources: Iterable[dict[str, Any]],
        claim_nodes: Iterable[dict[str, Any]],
        assessments: Iterable[dict[str, Any]],
        assessment_evidence: Iterable[dict[str, Any]],
        company_mappings: Iterable[dict[str, Any]],
        mapping_evidence_items: Iterable[dict[str, Any]],
        company_mapping_evidence: Iterable[dict[str, Any]],
    ) -> "NormalizedThemeResearchPackage":
        values = {
            "themes": _sorted_rows(themes, _FAMILY_KEYS["themes"]),
            "nodes": _sorted_rows(nodes, _FAMILY_KEYS["nodes"]),
            "sources": _sorted_rows(sources, _FAMILY_KEYS["sources"]),
            "theme_sources": _sorted_rows(theme_sources, _FAMILY_KEYS["theme_sources"]),
            "claims": _sorted_rows(claims, _FAMILY_KEYS["claims"]),
            "claim_sources": _sorted_rows(claim_sources, _FAMILY_KEYS["claim_sources"]),
            "claim_nodes": _sorted_rows(claim_nodes, _FAMILY_KEYS["claim_nodes"]),
            "assessments": _sorted_rows(assessments, _FAMILY_KEYS["assessments"]),
            "assessment_evidence": _sorted_rows(
                assessment_evidence, _FAMILY_KEYS["assessment_evidence"]
            ),
            "company_mappings": _sorted_rows(company_mappings, _FAMILY_KEYS["company_mappings"]),
            "mapping_evidence_items": _sorted_rows(
                mapping_evidence_items, _FAMILY_KEYS["mapping_evidence_items"]
            ),
            "company_mapping_evidence": _sorted_rows(
                company_mapping_evidence, _FAMILY_KEYS["company_mapping_evidence"]
            ),
        }
        _validate_normalized_rows(values)
        payload = {"artifact_version": artifact_version, **values}
        return cls(
            artifact_version=artifact_version,
            package_sha256=_content_sha256(payload),
            **values,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            field.name: copy.deepcopy(getattr(self, field.name))
            for field in fields(self)
        }


def normalize_artifact_package(
    *,
    theme_artifact_dir: str | Path | None = None,
    company_mapping_dir: str | Path | None = None,
) -> NormalizedThemeResearchPackage:
    theme_package = load_theme_package(theme_artifact_dir)
    mapping_package = load_theme_company_mapping_package(
        company_mapping_dir,
        theme_artifact_dir,
    )
    artifact_version = str(theme_package["artifact_versions"][0])

    themes = []
    artifact_by_theme_id: dict[str, dict[str, Any]] = {}
    for path in sorted(Path(theme_package["artifact_dir"]).glob("*.json")):
        artifact = json.loads(path.read_text(encoding="utf-8"))
        artifact_by_theme_id[artifact["theme"]["theme_id"]] = artifact
    for theme in theme_package["themes"]:
        row = copy.deepcopy(theme)
        row["content_sha256"] = _content_sha256(theme)
        artifact = artifact_by_theme_id[theme["theme_id"]]
        row["artifact_metadata"] = {
            "evidence_policy": copy.deepcopy(artifact.get("evidence_policy", {})),
            "decomposition_templates": copy.deepcopy(
                artifact.get("decomposition_templates", [])
            ),
        }
        themes.append(row)

    sources_by_id: dict[str, dict[str, Any]] = {}
    for source in [*theme_package["sources"], *mapping_package["sources"]]:
        row = copy.deepcopy(source)
        row["publish_date"] = row.get("publish_date") or None
        row.setdefault("content_sha256", _content_sha256(source))
        row.setdefault("provenance", {})
        existing = sources_by_id.get(row["source_id"])
        if existing is not None and existing != row:
            raise ThemeResearchDomainError(
                f"conflicting source rows: {row['source_id']}",
                code="THEME_RESEARCH_CONFLICTING_SOURCE",
            )
        sources_by_id[row["source_id"]] = row

    theme_sources: set[tuple[str, str, str]] = set()
    claims: list[dict[str, Any]] = []
    claim_sources: list[dict[str, Any]] = []
    claim_nodes: list[dict[str, Any]] = []
    assessments: list[dict[str, Any]] = []
    assessment_evidence: list[dict[str, Any]] = []
    source_ids = set(sources_by_id)
    claim_ids = {claim["claim_id"] for claim in theme_package["claims"]}

    for theme in theme_package["themes"]:
        theme_id = theme["theme_id"]
        theme_detail = load_theme(theme_id, theme_artifact_dir)
        for source in theme_detail["sources"]:
            theme_sources.add((theme_id, source["source_id"], "manual"))
        for claim in theme_detail["claims"]:
            row = copy.deepcopy(claim)
            supporting_ids = row.pop("supporting_source_ids", [])
            affected_nodes = row.pop("affected_theme_nodes", [])
            claims.append(row)
            theme_sources.add((theme_id, row["source_id"], "primary_claim"))
            for source_id in supporting_ids:
                claim_sources.append({"claim_id": row["claim_id"], "source_id": source_id})
                theme_sources.add((theme_id, source_id, "supporting_claim"))
            for node_id in affected_nodes:
                claim_nodes.append({"claim_id": row["claim_id"], "node_id": node_id})
        for assessment in theme_detail["value_capture_assessments"]:
            row = copy.deepcopy(assessment)
            evidence_ids = row.pop("evidence_ids", [])
            assessment_id = _assessment_id(theme_id, row)
            row["assessment_id"] = assessment_id
            assessments.append(row)
            for evidence_id in evidence_ids:
                evidence_type = _evidence_type(evidence_id, source_ids, claim_ids)
                assessment_evidence.append(
                    {
                        "assessment_id": assessment_id,
                        "evidence_type": evidence_type,
                        "evidence_id": evidence_id,
                    }
                )
                if evidence_type == "source":
                    theme_sources.add((theme_id, evidence_id, "assessment"))

    mapping_evidence_ids = {
        row["evidence_id"] for row in mapping_package["evidence_items"]
    }
    company_mappings: list[dict[str, Any]] = []
    company_mapping_evidence: list[dict[str, Any]] = []
    for artifact in mapping_package["artifacts"]:
        theme_id = artifact["theme_id"]
        for source in artifact["sources"]:
            theme_sources.add((theme_id, source["source_id"], "company_mapping"))
        for mapping in artifact["company_mappings"]:
            row = copy.deepcopy(mapping)
            evidence_ids = row.pop("evidence_ids", [])
            row["node_id"] = row.pop("mapped_node_id")
            row.setdefault("business_materiality", "")
            row.setdefault("review_status", "draft")
            row.setdefault("metadata", {})
            company_mappings.append(row)
            for evidence_id in evidence_ids:
                evidence_type = (
                    "mapping_evidence_item"
                    if evidence_id in mapping_evidence_ids
                    else _evidence_type(evidence_id, source_ids, claim_ids)
                )
                company_mapping_evidence.append(
                    {
                        "mapping_id": row["mapping_id"],
                        "evidence_type": evidence_type,
                        "evidence_id": evidence_id,
                    }
                )

    return NormalizedThemeResearchPackage.build(
        artifact_version=artifact_version,
        themes=themes,
        nodes=theme_package["nodes"],
        sources=sources_by_id.values(),
        theme_sources=(
            {"theme_id": theme_id, "source_id": source_id, "link_reason": reason}
            for theme_id, source_id, reason in theme_sources
        ),
        claims=claims,
        claim_sources=claim_sources,
        claim_nodes=claim_nodes,
        assessments=assessments,
        assessment_evidence=assessment_evidence,
        company_mappings=company_mappings,
        mapping_evidence_items=mapping_package["evidence_items"],
        company_mapping_evidence=company_mapping_evidence,
    )


def semantic_diff(
    current: NormalizedThemeResearchPackage,
    desired: NormalizedThemeResearchPackage,
) -> dict[str, Any]:
    families: dict[str, dict[str, list[str]]] = {}
    totals = {"insert": 0, "update": 0, "deactivate": 0, "no_change": 0}
    for family, keys in _FAMILY_KEYS.items():
        current_rows = {
            _identity(row, keys): _canonical_json(row) for row in getattr(current, family)
        }
        desired_rows = {
            _identity(row, keys): _canonical_json(row) for row in getattr(desired, family)
        }
        inserted = sorted(desired_rows.keys() - current_rows.keys())
        deactivated = sorted(current_rows.keys() - desired_rows.keys())
        updated = sorted(
            key
            for key in current_rows.keys() & desired_rows.keys()
            if current_rows[key] != desired_rows[key]
        )
        unchanged = sorted(
            key
            for key in current_rows.keys() & desired_rows.keys()
            if current_rows[key] == desired_rows[key]
        )
        families[family] = {
            "insert": inserted,
            "update": updated,
            "deactivate": deactivated,
            "no_change": unchanged,
        }
        totals["insert"] += len(inserted)
        totals["update"] += len(updated)
        totals["deactivate"] += len(deactivated)
        totals["no_change"] += len(unchanged)
    return {
        "has_changes": any(totals[key] for key in ("insert", "update", "deactivate")),
        "summary": totals,
        "families": families,
    }


def validate_package_integrity(
    package: NormalizedThemeResearchPackage,
) -> NormalizedThemeResearchPackage:
    rebuilt = NormalizedThemeResearchPackage.build(
        artifact_version=package.artifact_version,
        themes=package.themes,
        nodes=package.nodes,
        sources=package.sources,
        theme_sources=package.theme_sources,
        claims=package.claims,
        claim_sources=package.claim_sources,
        claim_nodes=package.claim_nodes,
        assessments=package.assessments,
        assessment_evidence=package.assessment_evidence,
        company_mappings=package.company_mappings,
        mapping_evidence_items=package.mapping_evidence_items,
        company_mapping_evidence=package.company_mapping_evidence,
    )
    if rebuilt.package_sha256 != package.package_sha256:
        raise ThemeResearchDomainError(
            "normalized package content does not match its package hash",
            code="THEME_RESEARCH_PACKAGE_HASH_MISMATCH",
            details={
                "declared_package_sha256": package.package_sha256,
                "actual_package_sha256": rebuilt.package_sha256,
            },
        )
    return rebuilt


def _assessment_id(theme_id: str, row: dict[str, Any]) -> str:
    basis = str(row["value_basis"]).lower()
    return f"{theme_id}::{row['node_id']}::{basis}::{row['rank']}"


def _evidence_type(evidence_id: str, source_ids: set[str], claim_ids: set[str]) -> str:
    if evidence_id in source_ids:
        return "source"
    if evidence_id in claim_ids:
        return "claim"
    raise ThemeResearchDomainError(
        f"unknown evidence reference: {evidence_id}",
        code="THEME_RESEARCH_ORPHAN_RELATIONSHIP",
    )


def _validate_normalized_rows(values: dict[str, tuple[dict[str, Any], ...]]) -> None:
    indexed: dict[str, set[str]] = {}
    for family, keys in _FAMILY_KEYS.items():
        identities = [_identity(row, keys) for row in values[family]]
        if len(identities) != len(set(identities)):
            raise ThemeResearchDomainError(
                f"duplicate identity in {family}",
                code="THEME_RESEARCH_DUPLICATE_ID",
                details={"family": family},
            )
        indexed[family] = set(identities)

    theme_ids = indexed["themes"]
    node_by_id = {row["node_id"]: row for row in values["nodes"]}
    source_ids = indexed["sources"]
    claim_by_id = {row["claim_id"]: row for row in values["claims"]}
    assessment_ids = indexed["assessments"]
    mapping_ids = indexed["company_mappings"]
    mapping_evidence_ids = indexed["mapping_evidence_items"]

    def orphan(message: str) -> None:
        raise ThemeResearchDomainError(
            message,
            code="THEME_RESEARCH_ORPHAN_RELATIONSHIP",
        )

    for node in values["nodes"]:
        if node["theme_id"] not in theme_ids:
            orphan(f"node theme missing: {node['node_id']}")
        parent_id = node.get("parent_node_id") or ""
        if parent_id:
            parent = node_by_id.get(parent_id)
            if parent is None or parent["theme_id"] != node["theme_id"]:
                orphan(f"node parent missing or cross-theme: {node['node_id']}")
    for row in values["theme_sources"]:
        if row["theme_id"] not in theme_ids or row["source_id"] not in source_ids:
            orphan(f"theme source missing: {_identity(row, _FAMILY_KEYS['theme_sources'])}")
    for claim in values["claims"]:
        if claim["theme_id"] not in theme_ids or claim["source_id"] not in source_ids:
            orphan(f"claim parent missing: {claim['claim_id']}")
    for row in values["claim_sources"]:
        if row["claim_id"] not in claim_by_id or row["source_id"] not in source_ids:
            orphan(f"claim source missing: {_identity(row, _FAMILY_KEYS['claim_sources'])}")
    for row in values["claim_nodes"]:
        claim = claim_by_id.get(row["claim_id"])
        node = node_by_id.get(row["node_id"])
        if claim is None or node is None or claim["theme_id"] != node["theme_id"]:
            orphan(f"claim node missing or cross-theme: {_identity(row, _FAMILY_KEYS['claim_nodes'])}")
    for assessment in values["assessments"]:
        if assessment["node_id"] not in node_by_id:
            orphan(f"assessment node missing: {assessment['assessment_id']}")
    for row in values["assessment_evidence"]:
        valid_evidence = (
            row["evidence_id"] in source_ids
            if row["evidence_type"] == "source"
            else row["evidence_id"] in claim_by_id
        )
        if row["assessment_id"] not in assessment_ids or not valid_evidence:
            orphan(f"assessment evidence missing: {_identity(row, _FAMILY_KEYS['assessment_evidence'])}")
    for mapping in values["company_mappings"]:
        node = node_by_id.get(mapping["node_id"])
        if mapping["theme_id"] not in theme_ids or node is None or node["theme_id"] != mapping["theme_id"]:
            orphan(f"company mapping parent missing: {mapping['mapping_id']}")
    for evidence in values["mapping_evidence_items"]:
        if evidence["source_id"] not in source_ids:
            orphan(f"mapping evidence source missing: {evidence['evidence_id']}")
    for row in values["company_mapping_evidence"]:
        evidence_exists = {
            "source": row["evidence_id"] in source_ids,
            "claim": row["evidence_id"] in claim_by_id,
            "mapping_evidence_item": row["evidence_id"] in mapping_evidence_ids,
        }.get(row["evidence_type"], False)
        if row["mapping_id"] not in mapping_ids or not evidence_exists:
            orphan(f"company mapping evidence missing: {_identity(row, _FAMILY_KEYS['company_mapping_evidence'])}")
