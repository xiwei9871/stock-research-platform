from __future__ import annotations

from typing import Any


def summarize_version(version: dict[str, Any]) -> dict[str, Any]:
    snapshot = version["snapshot"]
    return {
        "project_id": version["project_id"],
        "version_id": version["version_id"],
        "semantic_version": version["semantic_version"],
        "creation_stage": version["creation_stage"],
        "project_stage": snapshot["project_lifecycle_state"],
        "evidence_stage": snapshot["evidence_stage"],
        "conclusion_status": snapshot["conclusion_status"],
        "investment_status": snapshot["investment_status"],
        "question_count": len(snapshot["questions"]),
        "claim_count": len(snapshot["claims"]),
        "requirement_count": len(snapshot["evidence_requirements"]),
        "assessment_count": len(snapshot["evidence_assessments"]),
        "reference_count": len(snapshot["references"]),
        "causal_edge_count": len(snapshot["causal_edges"]),
    }


summary_version = summarize_version


__all__ = ["summarize_version", "summary_version"]
