#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from stock_research.industry_chain_theme_research import list_selected_chain_research
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_research_priority import load_theme_research_priority_package


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACK_SLUGS = {
    "ai_power_value_capture_v1": "ai_power",
    "semiconductor_manufacturing_equipment_value_chain_v1": "semiconductor_manufacturing_equipment",
    "humanoid_robotics_head_to_toe_v1": "humanoid_robotics",
    "ai_compute_infrastructure_value_chain_v1": "ai_compute_infrastructure",
    "new_energy_storage_value_chain_v1": "new_energy_storage",
}


def build_five_theme_report(
    *,
    catalog: dict[str, Any] | None = None,
    theme_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_catalog = catalog if catalog is not None else load_industry_catalog()
    resolved_context = (
        theme_context
        if theme_context is not None
        else load_theme_research_priority_package()
    )
    rows = list_selected_chain_research(
        catalog=resolved_catalog,
        theme_context=resolved_context,
    )
    theme_nodes = resolved_context["theme_package"]["nodes"]
    enriched_rows = []
    for row in rows:
        theme_id = row["theme_id"]
        slug = SOURCE_PACK_SLUGS[theme_id]
        source_pack = _load_json(
            REPOSITORY_ROOT
            / "artifacts/theme_decomposition/source_packs"
            / f"{slug}_source_pack_v1.json"
        )
        matrix = _load_json(
            REPOSITORY_ROOT
            / "artifacts/theme_decomposition/source_packs"
            / f"{slug}_node_evidence_matrix_v1.json"
        )
        expected_node_ids = {
            node["node_id"] for node in theme_nodes if node["theme_id"] == theme_id
        }
        matrix_rows = matrix.get("node_evidence_matrix", []) if matrix else []
        matrix_node_ids = {item.get("node_id") for item in matrix_rows}
        accounted_node_ids = {
            item.get("node_id")
            for item in matrix_rows
            if item.get("accepted_source_ids")
            or item.get("evidence_gap_status") == "evidence_gap"
        }
        source_pack_ready = bool(
            source_pack
            and source_pack.get("theme_id") == theme_id
            and len(
                [
                    item
                    for item in source_pack.get("sources", [])
                    if item.get("review_status") == "accepted"
                ]
            )
            >= 10
        )
        matrix_ready = bool(
            matrix
            and matrix.get("theme_id") == theme_id
            and matrix_node_ids == expected_node_ids
            and accounted_node_ids == expected_node_ids
        )
        enriched_rows.append(
            {
                **row,
                "source_pack_ready": source_pack_ready,
                "node_evidence_matrix_ready": matrix_ready,
                "node_evidence_accounted_count": len(accounted_node_ids),
            }
        )
    rows = enriched_rows
    reviewed_count = sum(row["research_status"] == "reviewed" for row in rows)
    researching_count = sum(row["research_status"] == "researching" for row in rows)
    catalog_link_count = sum(row["coverage"]["checks"]["catalog_link"] for row in rows)
    all_ready = len(rows) == 5 and all(
        row["coverage"]["ready"]
        and row["source_pack_ready"]
        and row["node_evidence_matrix_ready"]
        for row in rows
    )
    return {
        "selected_theme_count": len(rows),
        "catalog_link_count": catalog_link_count,
        "reviewed_theme_count": reviewed_count,
        "researching_theme_count": researching_count,
        "theme_results": rows,
        "all_required_sections_ready": all_ready,
        "completion_status": "ready" if all_ready else "not_ready",
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    report = build_five_theme_report()
    if args.format == "markdown":
        print(f"# Five-theme completion: {report['completion_status']}")
        print()
        for row in report["theme_results"]:
            print(
                f"- {row['chain_name']}: {row['research_status']} "
                f"({row['source_count']} sources, {row['claim_count']} claims, "
                f"{row['reviewed_company_count']} reviewed companies)"
            )
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["completion_status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
