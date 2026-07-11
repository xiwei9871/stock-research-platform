from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AI_POWER_SOURCE_PACK_DIR = (
    REPOSITORY_ROOT / "artifacts" / "theme_decomposition" / "source_packs"
)
AI_POWER_THEME_ARTIFACT = (
    REPOSITORY_ROOT / "artifacts" / "theme_decomposition" / "ai_power_value_capture_v1.json"
)

SOURCE_PACK_FILENAME = "ai_power_source_pack_v1.json"
CLAIM_REVIEW_FILENAME = "ai_power_claim_review_v1.json"
NODE_MATRIX_FILENAME = "ai_power_node_evidence_matrix_v1.json"

SOURCE_PACK_VERSION = "ai_power_source_pack_v1"
CLAIM_REVIEW_VERSION = "ai_power_claim_review_v1"
NODE_MATRIX_VERSION = "ai_power_node_evidence_matrix_v1"

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
SOURCE_REVIEW_STATUSES = {"accepted", "needs_full_text", "lead_only", "rejected"}
DOCUMENT_STATUSES = {
    "full_text_reviewed",
    "official_page_reviewed",
    "metadata_only",
    "access_blocked",
    "lead_only",
}
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
}
EVIDENCE_STATUSES = {"verified", "partially_verified", "unverified", "contradicted"}
CLAIM_REVIEW_DECISIONS = {"reviewed", "blocked", "research_lead", "draft"}
SCORE_REVIEW_STATUSES = {"confirmed", "provisional", "unsupported", "conflicted"}
EVIDENCE_GAP_STATUSES = {"supported", "technical_route_only", "evidence_gap"}
NODE_REVIEW_STATUSES = {"reviewed", "needs_evidence", "draft", "blocked"}
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

SOURCE_FIELDS = {
    "source_id",
    "source_type",
    "title",
    "publisher",
    "author",
    "publish_date",
    "url",
    "access_level",
    "reliability_level",
    "review_status",
    "document_status",
    "evidence_locator",
    "evidence_summary",
    "supported_claim_ids",
    "supported_node_ids",
    "limitations",
    "notes",
}
CLAIM_REVIEW_FIELDS = {
    "claim_id",
    "claim_text",
    "claim_type",
    "review_decision",
    "evidence_status",
    "confidence",
    "accepted_source_ids",
    "pending_source_ids",
    "affected_node_ids",
    "rationale",
    "uncertainty",
    "next_evidence_needed",
}
NODE_MATRIX_FIELDS = {
    "node_id",
    "accepted_source_ids",
    "pending_source_ids",
    "supported_claim_ids",
    "evidence_strength_before",
    "evidence_strength_after",
    "value_capture_score_review_status",
    "bottleneck_score_review_status",
    "value_bases",
    "evidence_gap_status",
    "node_review_status",
    "rationale",
    "next_evidence_needed",
}


class AiPowerEvidenceValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


def load_ai_power_evidence_pack(
    artifact_dir: str | Path | None = None,
    theme_artifact_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(artifact_dir) if artifact_dir is not None else AI_POWER_SOURCE_PACK_DIR
    theme_path = (
        Path(theme_artifact_path)
        if theme_artifact_path is not None
        else AI_POWER_THEME_ARTIFACT
    )
    source_pack = _load_json(root / SOURCE_PACK_FILENAME)
    claim_review = _load_json(root / CLAIM_REVIEW_FILENAME)
    node_matrix = _load_json(root / NODE_MATRIX_FILENAME)
    canonical_theme = _load_json(theme_path)
    package = {
        "artifact_dir": str(root),
        "canonical_theme": canonical_theme,
        "source_pack": source_pack,
        "claim_review": claim_review,
        "node_matrix": node_matrix,
        "sources": source_pack.get("sources", []),
        "claim_reviews": claim_review.get("claim_reviews", []),
        "node_evidence_matrix": node_matrix.get("node_evidence_matrix", []),
    }
    validate_ai_power_evidence_pack(package)
    return package


def validate_ai_power_evidence_pack(package: dict[str, Any]) -> None:
    source_pack = package["source_pack"]
    claim_review = package["claim_review"]
    node_matrix = package["node_matrix"]
    canonical_theme = package["canonical_theme"]

    _check_version(source_pack, SOURCE_PACK_VERSION, "source_pack")
    _check_version(claim_review, CLAIM_REVIEW_VERSION, "claim_review")
    _check_version(node_matrix, NODE_MATRIX_VERSION, "node_matrix")

    theme_id = canonical_theme.get("theme", {}).get("theme_id")
    if theme_id != "ai_power_value_capture_v1":
        raise AiPowerEvidenceValidationError(
            f"canonical theme_id invalid: {theme_id}",
            code="INVALID_CANONICAL_THEME",
        )
    for name, artifact in (
        ("source_pack", source_pack),
        ("claim_review", claim_review),
        ("node_matrix", node_matrix),
    ):
        if artifact.get("theme_id") != theme_id:
            raise AiPowerEvidenceValidationError(
                f"{name}.theme_id does not match canonical theme",
                code="THEME_ID_MISMATCH",
            )

    canonical_node_ids = {
        node["node_id"] for node in canonical_theme.get("nodes", []) if node.get("node_id")
    }
    source_by_id = _validate_sources(package["sources"], canonical_node_ids)
    claim_by_id = _validate_claim_reviews(
        package["claim_reviews"],
        source_by_id=source_by_id,
        canonical_node_ids=canonical_node_ids,
    )
    _validate_source_claim_references(package["sources"], claim_by_id)
    _validate_node_matrix(
        package["node_evidence_matrix"],
        source_by_id=source_by_id,
        claim_by_id=claim_by_id,
        canonical_node_ids=canonical_node_ids,
    )


def summarize_ai_power_evidence_pack(package: dict[str, Any]) -> dict[str, Any]:
    sources = package["sources"]
    claim_reviews = package["claim_reviews"]
    node_matrix = package["node_evidence_matrix"]
    return {
        "theme_id": package["source_pack"]["theme_id"],
        "source_count": len(sources),
        "accepted_source_count": sum(
            source["review_status"] == "accepted" for source in sources
        ),
        "needs_full_text_source_count": sum(
            source["review_status"] == "needs_full_text" for source in sources
        ),
        "claim_count": len(claim_reviews),
        "node_count": len(node_matrix),
        "sources_by_reliability_level": _count_by(sources, "reliability_level"),
        "sources_by_review_status": _count_by(sources, "review_status"),
        "claims_by_review_decision": _count_by(claim_reviews, "review_decision"),
        "matrix_nodes_by_evidence_gap_status": _count_by(
            node_matrix, "evidence_gap_status"
        ),
    }


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-power-source-pack")
    parser.add_argument("--artifact-dir", default=str(AI_POWER_SOURCE_PACK_DIR))
    parser.add_argument("--theme-artifact", default=str(AI_POWER_THEME_ARTIFACT))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("summary")
    args = parser.parse_args(argv)

    try:
        package = load_ai_power_evidence_pack(args.artifact_dir, args.theme_artifact)
        summary = summarize_ai_power_evidence_pack(package)
        if args.command == "validate":
            print(json.dumps({"status": "ok", **summary}, ensure_ascii=False, sort_keys=True))
            return 0
        if args.command == "summary":
            print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except AiPowerEvidenceValidationError as exc:
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
    if not path.exists():
        raise AiPowerEvidenceValidationError(
            f"artifact not found: {path}",
            code="ARTIFACT_NOT_FOUND",
        )
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise AiPowerEvidenceValidationError(
            f"artifact root must be object: {path}",
            code="INVALID_ARTIFACT_ROOT",
        )
    return payload


def _check_version(payload: dict[str, Any], expected: str, path: str) -> None:
    if payload.get("artifact_version") != expected:
        raise AiPowerEvidenceValidationError(
            f"{path}.artifact_version must be {expected}",
            code="UNSUPPORTED_ARTIFACT_VERSION",
        )


def _validate_sources(
    sources: list[dict[str, Any]],
    canonical_node_ids: set[str],
) -> dict[str, dict[str, Any]]:
    source_by_id: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        path = f"sources[{index}]"
        _require_fields(source, SOURCE_FIELDS, path)
        _check_enum(source, "source_type", SOURCE_TYPES, path)
        _check_enum(source, "access_level", ACCESS_LEVELS, path)
        _check_enum(source, "reliability_level", RELIABILITY_LEVELS, path)
        _check_enum(source, "review_status", SOURCE_REVIEW_STATUSES, path)
        _check_enum(source, "document_status", DOCUMENT_STATUSES, path)
        source_id = _unique_id(source_by_id, source.get("source_id"), f"{path}.source_id")
        if source["reliability_level"] == "S4" and source["review_status"] == "accepted":
            raise AiPowerEvidenceValidationError(
                f"{path} S4 source cannot be accepted",
                code="S4_SOURCE_CANNOT_BE_ACCEPTED",
            )
        if source["review_status"] == "accepted":
            if source["document_status"] not in {
                "official_page_reviewed",
                "full_text_reviewed",
            }:
                raise AiPowerEvidenceValidationError(
                    f"{path} accepted source requires reviewed document",
                    code="ACCEPTED_SOURCE_REQUIRES_REVIEWED_DOCUMENT",
                )
            if not str(source["url"]).startswith("https://"):
                raise AiPowerEvidenceValidationError(
                    f"{path} accepted source requires public HTTPS URL",
                    code="ACCEPTED_SOURCE_REQUIRES_PUBLIC_URL",
                )
            if not str(source["evidence_locator"]).strip():
                raise AiPowerEvidenceValidationError(
                    f"{path} accepted source requires evidence locator",
                    code="ACCEPTED_SOURCE_REQUIRES_EVIDENCE_LOCATOR",
                )
            if not str(source["evidence_summary"]).strip():
                raise AiPowerEvidenceValidationError(
                    f"{path} accepted source requires evidence summary",
                    code="ACCEPTED_SOURCE_REQUIRES_EVIDENCE_SUMMARY",
                )
            if not str(source["limitations"]).strip():
                raise AiPowerEvidenceValidationError(
                    f"{path} accepted source requires limitations",
                    code="ACCEPTED_SOURCE_REQUIRES_LIMITATIONS",
                )
        for node_id in source["supported_node_ids"]:
            if node_id not in canonical_node_ids:
                raise AiPowerEvidenceValidationError(
                    f"{path}.supported_node_ids references missing node: {node_id}",
                    code="SOURCE_REFERENCES_MISSING_NODE",
                )
        source_by_id[source_id] = source
    return source_by_id


def _validate_claim_reviews(
    claim_reviews: list[dict[str, Any]],
    *,
    source_by_id: dict[str, dict[str, Any]],
    canonical_node_ids: set[str],
) -> dict[str, dict[str, Any]]:
    claim_by_id: dict[str, dict[str, Any]] = {}
    for index, claim in enumerate(claim_reviews):
        path = f"claim_reviews[{index}]"
        _require_fields(claim, CLAIM_REVIEW_FIELDS, path)
        _check_enum(claim, "claim_type", CLAIM_TYPES, path)
        _check_enum(claim, "review_decision", CLAIM_REVIEW_DECISIONS, path)
        _check_enum(claim, "evidence_status", EVIDENCE_STATUSES, path)
        claim_id = _unique_id(claim_by_id, claim.get("claim_id"), f"{path}.claim_id")
        confidence = claim["confidence"]
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            raise AiPowerEvidenceValidationError(
                f"{path}.confidence must be number 0-1",
                code="INVALID_CLAIM_CONFIDENCE",
            )
        for field in ("accepted_source_ids", "pending_source_ids"):
            for source_id in claim[field]:
                if source_id not in source_by_id:
                    raise AiPowerEvidenceValidationError(
                        f"{path}.{field} references missing source: {source_id}",
                        code="CLAIM_REFERENCES_MISSING_SOURCE",
                    )
        for source_id in claim["accepted_source_ids"]:
            if source_by_id[source_id]["review_status"] != "accepted":
                raise AiPowerEvidenceValidationError(
                    f"{path}.accepted_source_ids contains non-accepted source: {source_id}",
                    code="CLAIM_ACCEPTED_SOURCE_STATUS_MISMATCH",
                )
        for source_id in claim["pending_source_ids"]:
            if source_by_id[source_id]["review_status"] == "accepted":
                raise AiPowerEvidenceValidationError(
                    f"{path}.pending_source_ids contains accepted source: {source_id}",
                    code="CLAIM_PENDING_SOURCE_STATUS_MISMATCH",
                )
        if claim["review_decision"] == "reviewed" and not claim["accepted_source_ids"]:
            raise AiPowerEvidenceValidationError(
                f"{path} reviewed claim requires accepted source",
                code="REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE",
            )
        for node_id in claim["affected_node_ids"]:
            if node_id not in canonical_node_ids:
                raise AiPowerEvidenceValidationError(
                    f"{path}.affected_node_ids references missing node: {node_id}",
                    code="CLAIM_REFERENCES_MISSING_NODE",
                )
        claim_by_id[claim_id] = claim
    return claim_by_id


def _validate_source_claim_references(
    sources: list[dict[str, Any]],
    claim_by_id: dict[str, dict[str, Any]],
) -> None:
    for index, source in enumerate(sources):
        for claim_id in source["supported_claim_ids"]:
            if claim_id not in claim_by_id:
                raise AiPowerEvidenceValidationError(
                    f"sources[{index}].supported_claim_ids references missing claim: {claim_id}",
                    code="SOURCE_REFERENCES_MISSING_CLAIM",
                )


def _validate_node_matrix(
    rows: list[dict[str, Any]],
    *,
    source_by_id: dict[str, dict[str, Any]],
    claim_by_id: dict[str, dict[str, Any]],
    canonical_node_ids: set[str],
) -> None:
    row_by_node_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        path = f"node_evidence_matrix[{index}]"
        _require_fields(row, NODE_MATRIX_FIELDS, path)
        node_id = _unique_id(row_by_node_id, row.get("node_id"), f"{path}.node_id")
        for field in ("evidence_strength_before", "evidence_strength_after"):
            _check_score(row, field, path)
        _check_enum(
            row,
            "value_capture_score_review_status",
            SCORE_REVIEW_STATUSES,
            path,
        )
        _check_enum(
            row,
            "bottleneck_score_review_status",
            SCORE_REVIEW_STATUSES,
            path,
        )
        _check_enum(row, "evidence_gap_status", EVIDENCE_GAP_STATUSES, path)
        _check_enum(row, "node_review_status", NODE_REVIEW_STATUSES, path)
        for value_basis in row["value_bases"]:
            if value_basis not in VALUE_BASES:
                raise AiPowerEvidenceValidationError(
                    f"{path}.value_bases invalid: {value_basis}",
                    code="INVALID_VALUE_BASIS",
                )
        for field in ("accepted_source_ids", "pending_source_ids"):
            for source_id in row[field]:
                if source_id not in source_by_id:
                    raise AiPowerEvidenceValidationError(
                        f"{path}.{field} references missing source: {source_id}",
                        code="NODE_MATRIX_REFERENCES_MISSING_SOURCE",
                    )
        for source_id in row["accepted_source_ids"]:
            if source_by_id[source_id]["review_status"] != "accepted":
                raise AiPowerEvidenceValidationError(
                    f"{path}.accepted_source_ids contains non-accepted source: {source_id}",
                    code="NODE_MATRIX_ACCEPTED_SOURCE_STATUS_MISMATCH",
                )
        for claim_id in row["supported_claim_ids"]:
            if claim_id not in claim_by_id:
                raise AiPowerEvidenceValidationError(
                    f"{path}.supported_claim_ids references missing claim: {claim_id}",
                    code="NODE_MATRIX_REFERENCES_MISSING_CLAIM",
                )
        if row["node_review_status"] == "reviewed":
            if row["evidence_strength_after"] < 3 or not row["accepted_source_ids"]:
                raise AiPowerEvidenceValidationError(
                    f"{path} reviewed node requires strength >= 3 and accepted source",
                    code="REVIEWED_NODE_REQUIRES_ACCEPTED_EVIDENCE",
                )
        row_by_node_id[node_id] = row
    if set(row_by_node_id) != canonical_node_ids:
        missing = sorted(canonical_node_ids - set(row_by_node_id))
        extra = sorted(set(row_by_node_id) - canonical_node_ids)
        raise AiPowerEvidenceValidationError(
            f"node matrix coverage mismatch; missing={missing}, extra={extra}",
            code="NODE_MATRIX_COVERAGE_MISMATCH",
        )


def _require_fields(row: dict[str, Any], fields: set[str], path: str) -> None:
    for field in sorted(fields):
        if field not in row:
            raise AiPowerEvidenceValidationError(
                f"{path}.{field} is required",
                code="MISSING_REQUIRED_FIELD",
            )


def _check_enum(
    row: dict[str, Any], field: str, allowed: set[str], path: str
) -> None:
    value = row.get(field)
    if value not in allowed:
        raise AiPowerEvidenceValidationError(
            f"{path}.{field} invalid: {value}",
            code="INVALID_ENUM_VALUE",
        )


def _check_score(row: dict[str, Any], field: str, path: str) -> None:
    value = row.get(field)
    if not isinstance(value, int) or value < 0 or value > 5:
        raise AiPowerEvidenceValidationError(
            f"{path}.{field} must be integer 0-5",
            code="INVALID_SCORE",
        )


def _unique_id(
    rows_by_id: dict[str, dict[str, Any]], value: Any, path: str
) -> str:
    text = str(value or "").strip()
    if not text:
        raise AiPowerEvidenceValidationError(
            f"{path} is required",
            code="MISSING_REQUIRED_FIELD",
        )
    if text in rows_by_id:
        raise AiPowerEvidenceValidationError(
            f"{path} duplicated: {text}",
            code="DUPLICATE_ID",
        )
    return text


def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(row[field]) for row in rows)
    return {key: counts[key] for key in sorted(counts)}


if __name__ == "__main__":
    main()
