from __future__ import annotations

from collections import Counter
from typing import Any


def summarize_evidence_coverage(version: dict[str, Any]) -> dict[str, Any]:
    snapshot = version["snapshot"]
    all_requirements = snapshot.get("evidence_requirements", [])
    requirements = [
        item
        for item in all_requirements
        if item.get("lifecycle_status", "active")
        not in {"superseded", "retired", "removed_from_scope"}
    ]
    candidates = snapshot.get("source_candidates", [])
    assessments = snapshot.get("industry_evidence_assessments", [])

    requirement_by_id = {
        item["requirement_id"]: item for item in requirements
    }
    assessment_counts = Counter(
        item["requirement_id"] for item in assessments
    )
    reviewed_primary = [
        item
        for item in assessments
        if item.get("review_status") == "reviewed"
        and item.get("independence") in {"primary_source", "independent_primary"}
    ]
    acquisition_counts = Counter(
        item.get("acquisition_status", "unknown") for item in candidates
    )
    inaccessible = [
        {
            "candidate_id": item["candidate_id"],
            "acquisition_status": item.get("acquisition_status"),
            "failure_reason": item.get("failure_reason"),
        }
        for item in candidates
        if item.get("acquisition_status")
        in {"unavailable", "paywalled", "inaccessible", "failed"}
    ]
    quality = Counter(item.get("strength", "unknown") for item in assessments)

    bottleneck_coverage: dict[str, dict[str, Any]] = {}
    for bottleneck in snapshot.get("bottleneck_hypotheses", []):
        requirement_ids = bottleneck.get("evidence_requirement_ids", [])
        bottleneck_coverage[bottleneck["bottleneck_hypothesis_id"]] = {
            "requirement_ids": sorted(requirement_ids),
            "assessment_count": sum(
                assessment_counts[requirement_id]
                for requirement_id in requirement_ids
            ),
            "blocked_requirement_ids": sorted(
                requirement_id
                for requirement_id in requirement_ids
                if requirement_by_id.get(requirement_id, {}).get(
                    "collection_status"
                )
                == "blocked"
            ),
        }

    return {
        "project_id": version["project_id"],
        "semantic_version": version["semantic_version"],
        "requirements": {
            "total": len(requirements),
            "total_including_inactive": len(all_requirements),
            "covered": sorted(
                item["requirement_id"]
                for item in requirements
                if item.get("satisfaction_status") == "satisfied"
            ),
            "partial": sorted(
                item["requirement_id"]
                for item in requirements
                if item.get("satisfaction_status") == "partial"
            ),
            "blocked": sorted(
                item["requirement_id"]
                for item in requirements
                if item.get("collection_status") == "blocked"
                or item.get("satisfaction_status") == "blocked"
            ),
        },
        "primary_source_coverage": {
            "requirements_requiring_primary": sum(
                bool(item.get("primary_source_required")) for item in requirements
            ),
            "reviewed_assessment_count": len(reviewed_primary),
            "requirement_ids": sorted(
                {item["requirement_id"] for item in reviewed_primary}
            ),
        },
        "acquisition_status": dict(sorted(acquisition_counts.items())),
        "inaccessible_evidence": sorted(
            inaccessible, key=lambda item: item["candidate_id"]
        ),
        "evidence_stance_distribution": dict(
            sorted(Counter(item.get("evidence_stance", "unknown") for item in assessments).items())
        ),
        "evidence_function_distribution": dict(
            sorted(
                Counter(
                    function
                    for item in assessments
                    for function in item.get("evidence_functions", [])
                ).items()
            )
        ),
        "evidence_quality_distribution": dict(sorted(quality.items())),
        "independent_source_clusters": len(
            snapshot.get("source_relationships", [])
        ),
        "bottleneck_coverage": bottleneck_coverage,
    }
