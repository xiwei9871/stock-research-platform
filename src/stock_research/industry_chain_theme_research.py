from __future__ import annotations

from datetime import date
from typing import Any


COMPLETED_CHAIN_THEMES = {
    "ai_data_center_power": "ai_power_value_capture_v1",
    "semiconductor_manufacturing_equipment": "semiconductor_manufacturing_equipment_value_chain_v1",
    "humanoid_robots_embodied_intelligence": "humanoid_robotics_head_to_toe_v1",
    "ai_compute_infrastructure": "ai_compute_infrastructure_value_chain_v1",
    "new_energy_storage": "new_energy_storage_value_chain_v1",
}

NEXT_FIFTEEN_CHAIN_THEMES = {
    "ai_logic_compute_chips": "ai_logic_compute_chips_value_chain_v1",
    "optical_communications_data_center_interconnect": "optical_communications_data_center_interconnect_value_chain_v1",
    "semiconductor_materials_electronic_chemicals": "semiconductor_materials_electronic_chemicals_value_chain_v1",
    "power_semiconductors": "power_semiconductors_value_chain_v1",
    "industrial_automation_control": "industrial_automation_control_value_chain_v1",
    "semiconductor_packaging_test_advanced_packaging": "semiconductor_packaging_test_advanced_packaging_value_chain_v1",
    "cloud_data_center_infrastructure": "cloud_data_center_infrastructure_value_chain_v1",
    "new_power_system_smart_grid": "new_power_system_smart_grid_value_chain_v1",
    "core_mechanical_components": "core_mechanical_components_value_chain_v1",
    "industrial_inspection_metrology_machine_vision": "industrial_inspection_metrology_machine_vision_value_chain_v1",
    "industrial_robots": "industrial_robots_value_chain_v1",
    "power_batteries_battery_materials": "power_batteries_battery_materials_value_chain_v1",
    "intelligent_driving_smart_cockpit": "intelligent_driving_smart_cockpit_value_chain_v1",
    "automotive_electronics_chip_applications": "automotive_electronics_chip_applications_value_chain_v1",
    "commercial_space_launch": "commercial_space_launch_value_chain_v1",
}

WAVE_D_CHAIN_THEMES = {
    "semiconductor_eda_ip_design_services": "semiconductor_eda_ip_design_services_value_chain_v1",
    "memory_chips_storage_control": "memory_chips_storage_control_value_chain_v1",
    "industrial_machine_tools_cnc": "industrial_machine_tools_cnc_value_chain_v1",
    "satellite_manufacturing_space_infrastructure": "satellite_manufacturing_space_infrastructure_value_chain_v1",
    "high_end_medical_devices": "high_end_medical_devices_value_chain_v1",
}

SELECTED_CHAIN_THEMES = {
    **COMPLETED_CHAIN_THEMES,
    **NEXT_FIFTEEN_CHAIN_THEMES,
    **WAVE_D_CHAIN_THEMES,
}

BENEFICIARY_TIERS = {
    "core_beneficiary",
    "elastic_beneficiary",
    "indirect_beneficiary",
    "concept_association",
}

DIRECT_RELATIONSHIP_EVIDENCE_TYPES = {
    "product_relationship",
    "service_relationship",
    "customer_relationship",
}

PRIMARY_SOURCE_TYPES = {
    "company_filing",
    "official_report",
    "official_article",
}


def classify_beneficiary(
    mapping: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> str:
    if (
        mapping.get("review_status") != "reviewed"
        or mapping.get("business_stage") != "primary_business"
        or mapping.get("business_materiality")
        in {"concept_only", "reserve_only", "unknown"}
        or float(mapping.get("confidence") or 0) < 0.7
        or not _has_accepted_direct_evidence(evidence_items)
    ):
        return "concept_association"
    if (
        mapping.get("bottleneck_relevance") != "core"
        or mapping.get("mapping_type") in {"material_supplier", "downstream_customer"}
    ):
        return "indirect_beneficiary"
    if (
        mapping.get("business_materiality") == "emerging_segment"
        or mapping.get("revenue_relevance") in {"limited", "undisclosed"}
    ):
        return "elastic_beneficiary"
    return "core_beneficiary"


def build_chain_research_summary(
    chain_id: str,
    *,
    catalog: dict[str, Any],
    theme_context: dict[str, Any],
    as_of_date: date | None = None,
) -> dict[str, Any] | None:
    theme_id = SELECTED_CHAIN_THEMES.get(chain_id)
    if theme_id is None:
        return None
    chain = next(
        (row for row in catalog.get("chains", []) if row.get("chain_id") == chain_id),
        {"chain_id": chain_id, "chain_name": chain_id},
    )
    theme = _theme_by_id(theme_context).get(theme_id)
    coverage = verify_deep_theme_coverage(
        theme_id,
        catalog=catalog,
        theme_context=theme_context,
    )
    if theme is None:
        research_status = "not_started"
        freshness_status = "not_available"
    else:
        freshness_status = _freshness_status(
            theme.get("last_updated", ""),
            as_of_date=as_of_date or date.today(),
        )
        research_status = (
            "reviewed"
            if theme.get("status") == "reviewed" and coverage["ready"]
            else "researching"
        )
        if research_status == "reviewed" and freshness_status == "needs_update":
            research_status = "needs_update"
    theme_sources = _theme_sources(theme_id, theme_context)
    theme_claims = _theme_claims(theme_id, theme_context)
    mappings = _theme_mappings(theme_id, theme_context)
    mapping_evidence = _mapping_evidence(theme_context)
    reviewed_companies = [
        mapping
        for mapping in mappings
        if classify_beneficiary(
            mapping,
            mapping_evidence.get(mapping.get("mapping_id", ""), []),
        )
        != "concept_association"
    ]
    return {
        "chain_id": chain_id,
        "chain_name": chain.get("chain_name", chain_id),
        "theme_id": theme_id,
        "theme_title": theme.get("theme_name", "") if theme else "",
        "theme_route": f"/theme-research/{theme_id}",
        "research_status": research_status,
        "freshness_status": freshness_status,
        "source_count": len(theme_sources),
        "claim_count": len(theme_claims),
        "reviewed_company_count": len(reviewed_companies),
        "evidence_gap_count": len(
            [
                row
                for row in theme_context.get("evidence_gap_priorities", [])
                if row.get("theme_id") == theme_id
            ]
        ),
        "last_updated": theme.get("last_updated", "") if theme else "",
        "coverage": coverage,
    }


def build_theme_catalog_context(
    theme_id: str,
    *,
    catalog: dict[str, Any],
) -> dict[str, Any] | None:
    chain_id = next(
        (chain for chain, selected_theme in SELECTED_CHAIN_THEMES.items() if selected_theme == theme_id),
        None,
    )
    if chain_id is None:
        return None
    chain = next(
        (row for row in catalog.get("chains", []) if row.get("chain_id") == chain_id),
        None,
    )
    if chain is None:
        return None
    return {
        "chain_id": chain_id,
        "chain_name": chain.get("chain_name", chain_id),
        "sector_id": chain.get("sector_id", ""),
        "catalog_route": f"/theme-research/catalog/{chain_id}",
    }


def verify_deep_theme_coverage(
    theme_id: str,
    *,
    catalog: dict[str, Any],
    theme_context: dict[str, Any],
) -> dict[str, Any]:
    chain_id = next(
        (chain for chain, selected_theme in SELECTED_CHAIN_THEMES.items() if selected_theme == theme_id),
        "",
    )
    theme = _theme_by_id(theme_context).get(theme_id)
    profiles = {
        row.get("theme_id"): row
        for row in theme_context.get("theme_package", {}).get("research_profiles", [])
    }
    link = next(
        (
            row
            for row in catalog.get("theme_links", [])
            if row.get("theme_id") == theme_id and row.get("chain_id") == chain_id
        ),
        None,
    )
    linked_catalog_nodes = {
        row.get("catalog_node_id")
        for row in (link or {}).get("node_links", [])
    }
    linked_theme_nodes = {
        row.get("theme_node_id")
        for row in (link or {}).get("node_links", [])
    }
    explicitly_unmapped_theme_nodes = set(
        (link or {}).get("unmapped_theme_node_ids", [])
    )
    theme_node_ids = {
        row.get("node_id")
        for row in theme_context.get("theme_package", {}).get("nodes", [])
        if row.get("theme_id") == theme_id
    }
    chain_nodes = [
        row for row in catalog.get("nodes", []) if row.get("chain_id") == chain_id
    ]
    l3_ids = {row.get("node_id") for row in chain_nodes if row.get("level") == "L3"}
    l4_ids = {row.get("node_id") for row in chain_nodes if row.get("level") == "L4"}
    sources = _theme_sources(theme_id, theme_context)
    accepted_source_ids = {
        row.get("source_id")
        for row in sources
        if row.get("review_status") == "accepted"
    }
    claims = _theme_claims(theme_id, theme_context)
    reviewed_claims = [
        row
        for row in claims
        if row.get("platform_use_status") == "reviewed"
    ]
    mappings = _theme_mappings(theme_id, theme_context)
    mapping_evidence = _mapping_evidence(theme_context)
    reviewed_mappings = [
        row
        for row in mappings
        if classify_beneficiary(
            row,
            mapping_evidence.get(row.get("mapping_id", ""), []),
        )
        != "concept_association"
    ]
    checks = {
        "theme_exists": theme is not None,
        "research_profile": profiles.get(theme_id, {}).get("catalog_chain_id") == chain_id,
        "catalog_link": link is not None,
        "all_theme_nodes_accounted_for": bool(theme_node_ids)
        and theme_node_ids <= linked_theme_nodes | explicitly_unmapped_theme_nodes,
        "catalog_l3_linked": not l3_ids or bool(l3_ids & linked_catalog_nodes),
        "catalog_l4_linked": not l4_ids or bool(l4_ids & linked_catalog_nodes),
        "accepted_source_count": len(accepted_source_ids) >= 10,
        "primary_source_count": len(
            [
                row
                for row in sources
                if row.get("source_id") in accepted_source_ids
                and row.get("source_type") in PRIMARY_SOURCE_TYPES
            ]
        )
        >= 4,
        "structured_claim_count": len(claims) >= 10,
        "reviewed_claim_sources_accepted": all(
            row.get("source_id") in accepted_source_ids for row in reviewed_claims
        ),
        "reviewed_company_count": len(reviewed_mappings) >= 8,
    }
    return {
        "theme_id": theme_id,
        "chain_id": chain_id,
        "ready": all(checks.values()),
        "checks": checks,
        "counts": {
            "accepted_sources": len(accepted_source_ids),
            "structured_claims": len(claims),
            "reviewed_claims": len(reviewed_claims),
            "reviewed_companies": len(reviewed_mappings),
            "theme_nodes": len(theme_node_ids),
            "accounted_theme_nodes": len(
                theme_node_ids
                & (linked_theme_nodes | explicitly_unmapped_theme_nodes)
            ),
            "l3_nodes": len(l3_ids),
            "l4_nodes": len(l4_ids),
        },
    }


def list_selected_chain_research(
    *,
    catalog: dict[str, Any],
    theme_context: dict[str, Any],
    as_of_date: date | None = None,
    include_unfinished_targets: bool = False,
) -> list[dict[str, Any]]:
    registry = SELECTED_CHAIN_THEMES if include_unfinished_targets else COMPLETED_CHAIN_THEMES
    return [
        summary
        for chain_id in registry
        if (
            summary := build_chain_research_summary(
                chain_id,
                catalog=catalog,
                theme_context=theme_context,
                as_of_date=as_of_date,
            )
        )
        is not None
    ]


def _theme_by_id(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row.get("theme_id", ""): row
        for row in context.get("theme_package", {}).get("themes", [])
    }


def _theme_claims(theme_id: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in context.get("theme_package", {}).get("claims", [])
        if row.get("theme_id") == theme_id
    ]


def _theme_sources(theme_id: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    claims = _theme_claims(theme_id, context)
    source_ids = {
        source_id
        for claim in claims
        for source_id in {
            claim.get("source_id"),
            *(claim.get("supporting_source_ids") or []),
        }
        if source_id
    }
    if not source_ids and _theme_by_id(context).get(theme_id):
        return list(context.get("theme_package", {}).get("sources", []))
    return [
        row
        for row in context.get("theme_package", {}).get("sources", [])
        if row.get("source_id") in source_ids
    ]


def _theme_mappings(theme_id: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in context.get("mapping_package", {}).get("company_mappings", [])
        if row.get("theme_id") == theme_id
    ]


def _mapping_evidence(context: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    package = context.get("mapping_package", {})
    sources = {row.get("source_id"): row for row in package.get("sources", [])}
    evidence = {
        row.get("evidence_id"): {**row, "source": sources.get(row.get("source_id"), {})}
        for row in package.get("evidence_items", [])
    }
    return {
        mapping.get("mapping_id", ""): [
            evidence[evidence_id]
            for evidence_id in mapping.get("evidence_ids", [])
            if evidence_id in evidence
        ]
        for mapping in package.get("company_mappings", [])
    }


def _has_accepted_direct_evidence(evidence_items: list[dict[str, Any]]) -> bool:
    return any(
        row.get("evidence_type") in DIRECT_RELATIONSHIP_EVIDENCE_TYPES
        and row.get("source", {}).get("review_status") == "accepted"
        and row.get("source", {}).get("reliability_level") in {"S0", "S1"}
        for row in evidence_items
    )


def _freshness_status(value: str, *, as_of_date: date) -> str:
    try:
        updated = date.fromisoformat(str(value))
    except ValueError:
        return "unknown"
    return "needs_update" if (as_of_date - updated).days > 365 else "current"
