from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from stock_research.industry_chain_theme_research import WAVE_G_CHAIN_THEMES
from stock_research.technology_industry_catalog import load_industry_catalog


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "wave_g_five_industry_chain_themes_v1.json"
)
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location("verify_wave_g_batch", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

WAVE_G_CASES = {
    "mems_intelligent_sensors": "mems_intelligent_sensors_value_chain_v1",
    "wafer_manufacturing_specialty_processes": (
        "wafer_manufacturing_specialty_processes_value_chain_v1"
    ),
    "civil_aircraft_aero_engines": "civil_aircraft_aero_engines_value_chain_v1",
    "nuclear_power_equipment": "nuclear_power_equipment_value_chain_v1",
    "scientific_instruments": "scientific_instruments_value_chain_v1",
}

G1_CHAIN_ID = "mems_intelligent_sensors"
G1_THEME_ID = "mems_intelligent_sensors_value_chain_v1"
G1_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{G1_THEME_ID}.json"
G1_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "mems_intelligent_sensors_company_mapping_v1.json"
)
G1_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "mems_intelligent_sensors_source_pack_v1.json"
)
G1_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "mems_intelligent_sensors_node_evidence_matrix_v1.json"
)
G1_L3 = {
    "mems_sensor_devices",
    "mems_fabrication_packaging",
    "intelligent_sensor_integration",
    "mems_commercial_validation",
}
G1_L4 = {
    "mems_inertial_accelerometer_gyroscope",
    "mems_pressure_flow_environmental_sensors",
    "mems_acoustic_microphones",
    "mems_rf_filters_resonators",
    "mems_optical_micro_mirror_lidar",
    "mems_foundry_wafer_process",
    "mems_packaging_calibration_test",
    "intelligent_sensor_fusion_modules",
    "design_win_mass_production_revenue_validation",
}
G1_INITIAL_UNIVERSE = {
    "002241.SZ", "688396.SH", "600460.SH", "300456.SZ", "688286.SH",
    "688052.SH", "300007.SZ", "300667.SZ", "603662.SH", "688582.SH",
}
G1_EXCLUDED_INITIAL = {"688052.SH", "300667.SZ", "603662.SH"}
G1_MAPPING_CONTRACTS = {
    "002241.SZ": ("mems_acoustic_microphones", "g1_002241_ar2025"),
    "688396.SH": ("mems_foundry_wafer_process", "g1_688396_ar2025"),
    "600460.SH": ("mems_foundry_wafer_process", "g1_600460_ar2025"),
    "300456.SZ": ("mems_foundry_wafer_process", "g1_300456_ar2025"),
    "688286.SH": ("mems_acoustic_microphones", "g1_688286_ar2025"),
    "300007.SZ": ("mems_pressure_flow_environmental_sensors", "g1_300007_ar2025"),
    "688582.SH": ("mems_inertial_accelerometer_gyroscope", "g1_688582_ar2025"),
    "603005.SH": ("mems_packaging_calibration_test", "g1_603005_ar2025"),
}
G1_REVENUE_ROLE_CONTRACTS = {
    "002241.SZ": "revenue_boundary",
    "688396.SH": "revenue_boundary",
    "600460.SH": "revenue_boundary",
    "300456.SZ": "revenue_materiality",
    "688286.SH": "revenue_materiality",
    "300007.SZ": "revenue_boundary",
    "688582.SH": "revenue_materiality",
    "603005.SH": "revenue_boundary",
}

G2_CHAIN_ID = "wafer_manufacturing_specialty_processes"
G2_THEME_ID = "wafer_manufacturing_specialty_processes_value_chain_v1"
G2_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{G2_THEME_ID}.json"
G2_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "wafer_manufacturing_specialty_processes_company_mapping_v1.json"
)
G2_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "wafer_manufacturing_specialty_processes_source_pack_v1.json"
)
G2_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "wafer_manufacturing_specialty_processes_node_evidence_matrix_v1.json"
)
G2_L3 = {
    "wafer_foundry_platforms",
    "specialty_process_platforms",
    "fab_operations_economics",
    "foundry_customer_validation",
}
G2_L4 = {
    "logic_mature_node_foundry",
    "analog_bcd_mixed_signal_process",
    "high_voltage_power_device_process",
    "rf_soi_sige_specialty_process",
    "embedded_nonvolatile_memory_process",
    "cmos_image_sensor_display_driver_process",
    "mems_sensor_specialty_foundry",
    "compound_semiconductor_specialty_foundry",
    "capacity_utilization_yield_cost_control",
    "customer_tapeout_qualification_revenue_validation",
}
G2_INITIAL_UNIVERSE = {
    "688981.SH", "688347.SH", "688249.SH", "688172.SH", "688396.SH",
    "600460.SH", "688469.SH", "300456.SZ", "600745.SH", "300373.SZ",
}
G2_EXCLUDED_INITIAL = {"600745.SH", "300373.SZ"}
G2_MAPPING_CONTRACTS = {
    "688981.SH": ("logic_mature_node_foundry", "g2_688981_ar2025"),
    "688347.SH": ("analog_bcd_mixed_signal_process", "g2_688347_ar2025"),
    "688249.SH": ("cmos_image_sensor_display_driver_process", "g2_688249_ar2025"),
    "688172.SH": ("analog_bcd_mixed_signal_process", "g2_688172_ar2025"),
    "688396.SH": ("high_voltage_power_device_process", "g2_688396_ar2025"),
    "600460.SH": ("compound_semiconductor_specialty_foundry", "g2_600460_ar2025"),
    "688469.SH": ("mems_sensor_specialty_foundry", "g2_688469_ar2025"),
    "300456.SZ": ("mems_sensor_specialty_foundry", "g2_300456_ar2025"),
}
G2_REVENUE_ROLE_CONTRACTS = {
    "688981.SH": "revenue_boundary",
    "688347.SH": "revenue_materiality",
    "688249.SH": "revenue_materiality",
    "688172.SH": "revenue_boundary",
    "688396.SH": "revenue_boundary",
    "600460.SH": "revenue_boundary",
    "688469.SH": "revenue_boundary",
    "300456.SZ": "revenue_materiality",
}
G2_FACT_CONTRACTS = {
    "688981.SH": {
        "locators": (
            "PDF printed p.13 / PDF_PAGE=13 / PDF第13页",
            "PDF printed p.190 / PDF_PAGE=190 / PDF第190页",
            "PDF printed p.17 / PDF_PAGE=17 / PDF第17页",
        ),
        "phrases": ("8英寸和12英寸晶圆代工", "集成电路晶圆代工62,794,043千元", "导入验证到稳定量产"),
    },
    "688347.SH": {
        "locators": (
            "PDF printed p.11 / PDF_PAGE=11 / PDF第11页",
            "PDF printed p.23 / PDF_PAGE=23 / PDF第23页",
            "PDF printed p.14 / PDF_PAGE=14 / PDF第14页",
        ),
        "phrases": ("模拟与电源管理特色晶圆代工", "模拟与电源管理收入4,560,483,268.12元", "90nm BCD稳定量产"),
    },
    "688249.SH": {
        "locators": (
            "PDF printed p.13 / PDF_PAGE=13 / PDF第13页",
            "PDF printed p.16 / PDF_PAGE=16 / PDF第16页",
            "PDF printed p.16 / PDF_PAGE=16 / PDF第16页（批量生产与订单）",
        ),
        "phrases": ("DDIC、CIS晶圆代工", "DDIC 58.06%、CIS 22.64%", "批量生产且订单规模稳步增加"),
    },
    "688172.SH": {
        "locators": (
            "PDF printed p.16 / PDF_PAGE=16 / PDF第16页",
            "PDF printed p.19 / PDF_PAGE=19 / PDF第19页（制造服务收入）",
            "PDF printed p.19 / PDF_PAGE=19 / PDF第19页（BCD稳定量产）",
        ),
        "phrases": ("Foundry与IDM结合且提供BCD代工", "制造服务收入81,220.54万元", "BCD工艺平台稳定量产"),
    },
    "688396.SH": {
        "locators": (
            "PDF printed p.22 / PDF_PAGE=22 / PDF第22页",
            "PDF printed p.30 / PDF_PAGE=30 / PDF第30页",
            "PDF printed p.23 / PDF_PAGE=23 / PDF第23页",
        ),
        "phrases": ("高压BCD覆盖5V-700V", "制造与服务收入4,792,782,896.97元", "建成高可靠BCD工艺线"),
    },
    "600460.SH": {
        "locators": (
            "PDF printed p.13 / PDF_PAGE=13 / PDF第13页（SiC产线）",
            "PDF printed p.14 / PDF_PAGE=14 / PDF第14页",
            "PDF printed p.13 / PDF_PAGE=13 / PDF第13页（量产出货）",
        ),
        "phrases": ("6英寸和8英寸SiC自有产线", "芯片制造子公司宽口径收入", "6英寸出货提升且8英寸通线"),
    },
    "688469.SH": {
        "locators": (
            "PDF printed p.17 / PDF_PAGE=17 / PDF第17页",
            "PDF printed p.65 / PDF_PAGE=65 / PDF第65页",
            "PDF printed p.14 / PDF_PAGE=14 / PDF第14页",
        ),
        "phrases": ("国内MEMS晶圆代工厂", "总营收81.80亿元为宽系统代工口径", "MEMS麦克风与多轴运动传感器量产"),
    },
    "300456.SZ": {
        "locators": (
            "PDF printed p.12 / PDF_PAGE=12 / PDF第12页",
            "PDF printed p.32 / PDF_PAGE=32 / PDF第32页",
            "PDF printed p.13-15 / PDF_PAGE=13-15 / PDF第13-15页",
        ),
        "phrases": ("MEMS纯代工、工艺开发与晶圆制造", "MEMS晶圆制造收入39,373.85万元", "亦庄量产线量产与试产分层"),
    },
}
G2_EXPECTED_EDGES = {
    ("logic_mature_node_foundry", "krf_lithography", "depends_on"),
    ("analog_bcd_mixed_signal_process", "foundry_pdk_design_enablement", "uses"),
    ("mems_foundry_wafer_process", "mems_sensor_specialty_foundry", "depends_on"),
    ("power_mosfet_device", "high_voltage_power_device_process", "depends_on"),
    ("silicon_carbide_power_device", "compound_semiconductor_specialty_foundry", "depends_on"),
}

G3_CHAIN_ID = "civil_aircraft_aero_engines"
G3_THEME_ID = "civil_aircraft_aero_engines_value_chain_v1"
G3_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{G3_THEME_ID}.json"
G3_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "civil_aircraft_aero_engines_company_mapping_v1.json"
)
G3_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "civil_aircraft_aero_engines_source_pack_v1.json"
)
G3_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "civil_aircraft_aero_engines_node_evidence_matrix_v1.json"
)
G3_L3 = {
    "civil_aircraft_platforms",
    "aero_engine_systems",
    "aviation_components_subsystems",
    "aviation_certification_lifecycle",
}
G3_L4 = {
    "civil_aircraft_airframe_final_assembly",
    "aero_engine_complete_machine",
    "engine_hot_section_blades_disks",
    "engine_control_fuel_systems",
    "airborne_avionics_electromechanical_systems",
    "aviation_structures_composites_fasteners",
    "landing_gear_wheels_brakes_systems",
    "airworthiness_certification_production_ramp",
    "mro_spares_installed_base_services",
}
G3_INITIAL_UNIVERSE = {
    "000768.SZ", "600893.SH", "000738.SZ", "600391.SH", "600765.SH",
    "600862.SH", "300696.SZ", "300900.SZ", "688239.SH", "600038.SH",
}
G3_EXCLUDED_INITIAL = {"600038.SH"}
G3_MAPPING_CONTRACTS = {
    "000768.SZ": ("aviation_structures_composites_fasteners", "g3_000768_ar2025"),
    "600893.SH": ("aero_engine_complete_machine", "g3_600893_ar2025"),
    "000738.SZ": ("engine_control_fuel_systems", "g3_000738_ar2025"),
    "600391.SH": ("engine_hot_section_blades_disks", "g3_600391_ar2025"),
    "600765.SH": ("engine_hot_section_blades_disks", "g3_600765_ar2025"),
    "600862.SH": ("aviation_structures_composites_fasteners", "g3_600862_ar2025"),
    "300696.SZ": ("aviation_structures_composites_fasteners", "g3_300696_ar2025"),
    "300900.SZ": ("aviation_structures_composites_fasteners", "g3_300900_ar2025"),
    "688239.SH": ("engine_hot_section_blades_disks", "g3_688239_ar2025"),
    "603308.SH": ("engine_hot_section_blades_disks", "g3_603308_ar2025"),
}
G3_EXPECTED_EDGES = {
    ("engine_hot_section_blades_disks", "metal_cutting_grinding_machine_tools", "uses"),
    (
        "aviation_structures_composites_fasteners",
        "multi_axis_composite_machining_centers",
        "uses",
    ),
}

G4_CHAIN_ID = "nuclear_power_equipment"
G4_THEME_ID = "nuclear_power_equipment_value_chain_v1"
G4_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{G4_THEME_ID}.json"
G4_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "nuclear_power_equipment_company_mapping_v1.json"
)
G4_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "nuclear_power_equipment_source_pack_v1.json"
)
G4_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "nuclear_power_equipment_node_evidence_matrix_v1.json"
)
G4_L3 = {
    "nuclear_island_equipment",
    "conventional_island_balance_plant",
    "nuclear_control_fuel_services",
    "nuclear_project_lifecycle",
}
G4_L4 = {
    "reactor_pressure_vessel_steam_generator",
    "primary_pumps_nuclear_valves_piping",
    "nuclear_grade_materials_forgings_components",
    "turbine_generator_conventional_island",
    "nuclear_instrumentation_control_electrical",
    "nuclear_fuel_cycle_handling_services",
    "engineering_construction_commissioning",
    "maintenance_inspection_life_extension",
    "project_approval_orders_delivery_revenue_validation",
}
G4_INITIAL_UNIVERSE = {
    "600875.SH", "601727.SH", "601106.SH", "603308.SH", "000922.SZ",
    "002438.SZ", "000777.SZ", "002255.SZ", "603169.SH", "002318.SZ",
}
G4_MAPPING_CONTRACTS = {
    "600875.SH": ("reactor_pressure_vessel_steam_generator", "g4_600875_ar2025"),
    "601727.SH": ("reactor_pressure_vessel_steam_generator", "g4_601727_ar2025"),
    "601106.SH": ("reactor_pressure_vessel_steam_generator", "g4_601106_ar2025"),
    "603308.SH": ("nuclear_grade_materials_forgings_components", "g4_603308_ar2025"),
    "000922.SZ": ("nuclear_instrumentation_control_electrical", "g4_000922_ar2025"),
    "002438.SZ": ("primary_pumps_nuclear_valves_piping", "g4_002438_ar2025"),
    "000777.SZ": ("primary_pumps_nuclear_valves_piping", "g4_000777_ar2025"),
    "002255.SZ": ("reactor_pressure_vessel_steam_generator", "g4_002255_ar2025"),
    "603169.SH": ("reactor_pressure_vessel_steam_generator", "g4_603169_ar2025"),
    "002318.SZ": ("nuclear_grade_materials_forgings_components", "g4_002318_ar2025"),
}
G4_BUSINESS_STAGE_CONTRACTS = {
    company_code: "primary_business" for company_code in G4_MAPPING_CONTRACTS
}
G4_BUSINESS_STAGE_CONTRACTS["002318.SZ"] = "reserve_stage"
G4_FACT_LOCATOR_CONTRACTS = {
    "600875.SH": (
        "PDF printed p.10 / PDF_PAGE=10 / PDF第10页（核岛主设备）",
        "PDF printed p.207 / PDF_PAGE=207 / PDF第207页（核能收入边界）",
        "PDF printed p.10 / PDF_PAGE=10 / PDF第10页（研制交付）",
    ),
    "000777.SZ": (
        "PDF printed p.13 / PDF_PAGE=13 / PDF第13页（核级阀门）",
        "PDF printed p.15 / PDF_PAGE=15 / PDF第15页（核工程阀门收入）",
        "PDF printed p.12 / PDF_PAGE=12 / PDF第12页（生产销售与核电站服务）",
    ),
    "002255.SZ": (
        "PDF printed p.16 / PDF_PAGE=16 / PDF第16页（裂变核级组件）",
        "PDF printed p.18 / PDF_PAGE=18 / PDF第18页（核电产品收入）",
        "PDF printed p.16 / PDF_PAGE=16 / PDF第16页（订单与首件制造）",
    ),
    "002318.SZ": (
        "PDF printed p.11 / PDF_PAGE=11 / PDF第11页（核电应用与客户）",
        "PDF printed p.15 / PDF_PAGE=15 / PDF第15页（多用途电力设备收入）",
        "PDF printed p.12 / PDF_PAGE=12 / PDF第12页（报告期核电取证）",
    ),
}
G4_REVENUE_ROLE_CONTRACTS = {
    "600875.SH": "revenue_boundary",
    "601727.SH": "revenue_boundary",
    "601106.SH": "revenue_materiality",
    "603308.SH": "revenue_boundary",
    "000922.SZ": "revenue_materiality",
    "002438.SZ": "revenue_materiality",
    "000777.SZ": "revenue_materiality",
    "002255.SZ": "revenue_materiality",
    "603169.SH": "revenue_boundary",
    "002318.SZ": "revenue_boundary",
}
G4_EXPECTED_EDGES = {
    (
        "reactor_pressure_vessel_steam_generator",
        "metal_cutting_grinding_machine_tools",
        "uses",
    ),
    (
        "nuclear_grade_materials_forgings_components",
        "metal_cutting_grinding_machine_tools",
        "uses",
    ),
}

REQUIRED_READABLE_SECTIONS = [
    {
        "name": "研究结论",
        "non_empty": [
            "theme:research_profile.investment_summary",
            "theme:research_profile.industry_stage",
            "theme:research_profile.central_conflict",
        ],
    },
    {
        "name": "价值链",
        "non_empty": [
            "theme:research_profile.value_flow_summary",
            "theme:nodes",
        ],
    },
    {
        "name": "利润池与竞争壁垒",
        "non_empty": ["theme:research_profile.profit_pool_summary"],
    },
    {
        "name": "催化、验证信号与风险",
        "non_empty": [
            "theme:research_profile.catalyst_claim_ids",
            "theme:research_profile.risk_claim_ids",
            "theme:research_profile.validation_signals",
        ],
    },
    {
        "name": "受益公司",
        "non_empty": ["company_mapping:company_mappings"],
    },
    {
        "name": "来源证据",
        "non_empty": ["source_pack:sources"],
    },
    {
        "name": "证据缺口与更新",
        "non_empty": [
            "theme:research_profile.evidence_gap_summary",
            "node_evidence_matrix:node_evidence_matrix",
        ],
    },
]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def artifact_paths(chain_id: str, theme_id: str) -> dict[str, Path]:
    return {
        "theme": REPOSITORY_ROOT
        / f"artifacts/theme_decomposition/{theme_id}.json",
        "company_mapping": REPOSITORY_ROOT
        / "artifacts/theme_decomposition/company_mappings"
        / f"{chain_id}_company_mapping_v1.json",
        "source_pack": REPOSITORY_ROOT
        / "artifacts/theme_decomposition/source_packs"
        / f"{chain_id}_source_pack_v1.json",
        "node_evidence_matrix": REPOSITORY_ROOT
        / "artifacts/theme_decomposition/source_packs"
        / f"{chain_id}_node_evidence_matrix_v1.json",
    }


def manifest_artifact_paths(chain_id: str, theme_id: str) -> dict[str, str]:
    return {
        key: path.relative_to(REPOSITORY_ROOT).as_posix()
        for key, path in artifact_paths(chain_id, theme_id).items()
    }


def assert_catalog_first_contract(
    chain_id: str,
    theme_id: str,
    expected_l3: set[str],
    expected_l4: set[str],
) -> None:
    catalog = load_industry_catalog()
    chain_nodes = [row for row in catalog["nodes"] if row["chain_id"] == chain_id]
    l3_ids = {row["node_id"] for row in chain_nodes if row["level"] == "L3"}
    l4_ids = {row["node_id"] for row in chain_nodes if row["level"] == "L4"}
    assert l3_ids == expected_l3
    assert l4_ids == expected_l4

    matching_links = [
        row for row in catalog["theme_links"] if row["theme_id"] == theme_id
    ]
    assert len(matching_links) == 1
    link = matching_links[0]
    assert link["chain_id"] == chain_id
    assert link["theme_id"] == theme_id
    assert link["unmapped_theme_node_ids"] == []

    linked_l4_by_theme_node = {
        row["theme_node_id"]: row["catalog_node_id"]
        for row in link["node_links"]
        if row["catalog_node_id"] in l4_ids
    }
    assert set(linked_l4_by_theme_node.values()) == l4_ids

    mapping = load_json(artifact_paths(chain_id, theme_id)["company_mapping"])
    reviewed_mappings = [
        row
        for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    ]
    for reviewed_mapping in reviewed_mappings:
        mapped_node_id = reviewed_mapping["mapped_node_id"]
        assert mapped_node_id in linked_l4_by_theme_node
        assert linked_l4_by_theme_node[mapped_node_id] in l4_ids


def test_wave_g_manifest_freezes_research_scope() -> None:
    manifest = VERIFIER.load_theme_batch_manifest(MANIFEST_PATH)
    expected_completion_gates = {
        "min_accepted_sources": 10,
        "min_primary_sources": 8,
        "min_claims": 12,
        "min_reviewed_mappings": 8,
        "require_node_evidence_matrix_coverage": True,
        "require_bidirectional_evidence_contract": True,
        "require_precise_mapping_locators": True,
        "required_readable_sections": REQUIRED_READABLE_SECTIONS,
    }
    expected_themes = {
        chain_id: {
            "theme_id": theme_id,
            "artifacts": manifest_artifact_paths(chain_id, theme_id),
        }
        for chain_id, theme_id in WAVE_G_CASES.items()
    }

    assert manifest == {
        "schema_version": "industry_chain_theme_batch_v1",
        "batch_id": "wave_g_five_industry_chain_themes_v1",
        "target_theme_count": 5,
        "artifact_base": "../../..",
        "primary_source_types": [
            "company_filing",
            "official_report",
            "official_article",
        ],
        "completion_gates": expected_completion_gates,
        "waves": {"wave_g": list(WAVE_G_CASES)},
        "themes": expected_themes,
    }
    assert list(manifest["themes"]) == list(WAVE_G_CASES)


def test_wave_g_scope_uses_existing_canonical_catalog_chains() -> None:
    catalog = load_industry_catalog()
    chains_by_id = {row["chain_id"]: row for row in catalog["chains"]}

    assert len(catalog["chains"]) == 82
    assert list(WAVE_G_CASES) == [
        "mems_intelligent_sensors",
        "wafer_manufacturing_specialty_processes",
        "civil_aircraft_aero_engines",
        "nuclear_power_equipment",
        "scientific_instruments",
    ]
    assert set(WAVE_G_CASES) <= set(chains_by_id)
    assert {
        chains_by_id[chain_id]["chain_kind"] for chain_id in WAVE_G_CASES
    } == {"canonical_industry_chain"}


def test_wave_g_registry_matches_manifest() -> None:
    manifest = VERIFIER.load_theme_batch_manifest(MANIFEST_PATH)

    assert WAVE_G_CHAIN_THEMES == WAVE_G_CASES
    assert {
        chain_id: metadata["theme_id"]
        for chain_id, metadata in manifest["themes"].items()
    } == WAVE_G_CHAIN_THEMES


def test_mems_g1_catalog_first_exact_tree_and_direct_link_contract() -> None:
    assert_catalog_first_contract(G1_CHAIN_ID, G1_THEME_ID, G1_L3, G1_L4)
    catalog = load_industry_catalog()
    chain_nodes = [row for row in catalog["nodes"] if row["chain_id"] == G1_CHAIN_ID]
    by_id = {row["node_id"]: row for row in chain_nodes}
    assert {row["node_kind"] for row in chain_nodes} == {"canonical"}
    assert all(not row["canonical_key"] for row in chain_nodes if row["level"] == "L3")
    l4_keys = [row["canonical_key"] for row in chain_nodes if row["level"] == "L4"]
    assert len(l4_keys) == len(set(l4_keys)) == 9
    assert all(key.startswith("mems_intelligent_sensors:") for key in l4_keys)
    for row in chain_nodes:
        assert row["primary_path"][1] == G1_CHAIN_ID
        if row["level"] == "L4":
            assert row["parent_node_id"] in G1_L3
            assert by_id[row["parent_node_id"]]["level"] == "L3"

    link = next(
        row for row in catalog["theme_links"] if row["theme_id"] == G1_THEME_ID
    )
    assert len(link["node_links"]) == 9
    assert {
        (row["theme_node_id"], row["catalog_node_id"])
        for row in link["node_links"]
    } == {(node_id, node_id) for node_id in G1_L4}


def test_mems_g1_artifacts_are_reviewed_and_meet_wave_gate() -> None:
    theme = load_json(G1_THEME_PATH)
    mapping = load_json(G1_MAPPING_PATH)
    source_pack = load_json(G1_SOURCE_PACK_PATH)
    matrix = load_json(G1_MATRIX_PATH)
    assert theme["artifact_version"] == "theme_decomposition_v1_6"
    assert mapping["evidence_contract_version"] == "mapping_evidence_roles_v2"
    assert theme["theme"]["status"] == "reviewed"
    assert {row["node_id"] for row in theme["nodes"]} == G1_L4
    assert len(source_pack["sources"]) >= 10
    assert sum(
        row["source_type"] in {"company_filing", "official_report", "official_article"}
        for row in source_pack["sources"]
    ) >= 8
    assert len(theme["claims"]) >= 12
    reviewed = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    assert len(reviewed) >= 8
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == G1_L4

    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_g")
    rows = {row["chain_id"]: row for row in report["theme_results"]}
    assert rows[G1_CHAIN_ID]["ready"] is True
    assert rows[G1_CHAIN_ID]["counts"]["accepted_sources"] >= 10
    assert rows[G1_CHAIN_ID]["counts"]["primary_sources"] >= 8
    assert rows[G1_CHAIN_ID]["counts"]["claims"] >= 12
    assert rows[G1_CHAIN_ID]["counts"]["reviewed_mappings"] >= 8


def test_mems_g1_company_three_role_evidence_and_initial_universe_closure() -> None:
    mapping = load_json(G1_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    reviewed = {
        row["company_code"]: row for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    excluded = {
        row["company_code"]: row for row in mapping["excluded_initial_candidates"]
    }
    assert set(reviewed) == set(G1_MAPPING_CONTRACTS)
    assert set(excluded) == G1_EXCLUDED_INITIAL
    assert (set(reviewed) & G1_INITIAL_UNIVERSE) | set(excluded) == G1_INITIAL_UNIVERSE
    assert not set(reviewed) & set(excluded)
    assert reviewed.keys() - G1_INITIAL_UNIVERSE == {"603005.SH"}
    assert "补充" in reviewed["603005.SH"]["notes"]
    for company_code, (node_id, source_id) in G1_MAPPING_CONTRACTS.items():
        row = reviewed[company_code]
        assert row["mapped_node_id"] == node_id
        items = [evidence[evidence_id] for evidence_id in row["evidence_ids"]]
        assert [item["evidence_type"] for item in items] == [
            "product_relationship",
            G1_REVENUE_ROLE_CONTRACTS[company_code],
            "business_stage",
        ]
        assert len({item["excerpt_locator"] for item in items}) == 3
        assert all(item["source_id"] == source_id for item in items)
        assert all(item["related_node_ids"] == [node_id] for item in items)
    assert mapping["concept_only_candidates"] == []


def test_mems_g1_commercial_validation_company_names_and_codes_are_one_to_one() -> None:
    theme = load_json(G1_THEME_PATH)
    commercial = next(
        row for row in theme["nodes"]
        if row["node_id"] == "design_win_mass_production_revenue_validation"
    )
    expected = {
        "002241.SZ": "歌尔股份",
        "688396.SH": "华润微",
        "600460.SH": "士兰微",
        "300456.SZ": "赛微电子",
        "688286.SH": "敏芯股份",
        "688582.SH": "芯动联科",
        "603005.SH": "晶方科技",
    }
    assert len(commercial["related_stock_codes"]) == len(commercial["domestic_players"])
    assert dict(zip(commercial["related_stock_codes"], commercial["domestic_players"])) == expected


def test_mems_g1_source_identity_claim_union_and_matrix_are_direct() -> None:
    theme = load_json(G1_THEME_PATH)
    mapping = load_json(G1_MAPPING_PATH)
    source_pack = load_json(G1_SOURCE_PACK_PATH)
    matrix = load_json(G1_MATRIX_PATH)
    identity_fields = (
        "source_id", "source_type", "title", "publisher", "author",
        "publish_date", "url_or_ref", "access_level", "reliability_level",
        "review_status", "notes",
    )
    identity = lambda rows: {
        row["source_id"]: tuple(
            row.get(field, row.get("url") if field == "url_or_ref" else None)
            for field in identity_fields
        ) for row in rows
    }
    assert identity(theme["sources"]) == identity(mapping["sources"])
    assert identity(theme["sources"]) == identity(source_pack["sources"])
    assert all(row["author"] == row["publisher"] and row["author"] for row in theme["sources"])

    claims = {row["claim_id"]: row for row in theme["claims"]}
    accepted = {
        row["source_id"] for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    claim_union = {
        source_id for claim in claims.values()
        for source_id in (claim["source_id"], *claim["supporting_source_ids"])
    }
    matrix_union = {
        source_id for row in matrix["node_evidence_matrix"]
        for source_id in row["accepted_source_ids"]
    }
    assert accepted == claim_union == matrix_union
    for row in matrix["node_evidence_matrix"]:
        node_claims = {
            claim_id for claim_id, claim in claims.items()
            if row["node_id"] in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == node_claims
        assert set(row["accepted_source_ids"]) == {
            claims[claim_id]["source_id"] for claim_id in node_claims
        }
    for source in source_pack["sources"]:
        source_claims = {
            claim_id for claim_id, claim in claims.items()
            if source["source_id"] in (claim["source_id"], *claim["supporting_source_ids"])
        }
        assert set(source["supported_claim_ids"]) == source_claims
        assert set(source["supported_node_ids"]) == {
            node_id for claim_id in source_claims
            for node_id in claims[claim_id]["affected_theme_nodes"]
        }
    bichuang = next(
        row for row in source_pack["sources"]
        if row["source_id"] == "g1_300667_ar2025"
    )
    assert bichuang["review_status"] == "rejected"
    assert bichuang["supported_claim_ids"] == []
    assert bichuang["supported_node_ids"] == []


def test_mems_g1_lifecycle_and_neighbor_chain_boundaries_are_explicit() -> None:
    theme = load_json(G1_THEME_PATH)
    mapping = load_json(G1_MAPPING_PATH)
    text = json.dumps({"theme": theme, "policy": mapping["mapping_policy"]}, ensure_ascii=False)
    for stage in ("研究", "样品", "design win", "量产", "订单", "收入"):
        assert stage in text
    for boundary in (
        "专利或实验室原型只作research lead",
        "产线机器视觉与工业检测系统保持工业检测链所有权",
        "人形机器人专用集成保持人形机器人链所有权",
        "纯模拟芯片与非MEMS传感器不得映射",
        "通用封测与generic foundry不得映射",
        "G2拥有晶圆制造特色工艺，G1仅拥有MEMS专用工艺",
        "混合口径公司总营收不作为节点收入",
    ):
        assert boundary in text
    excluded_by_code = {
        row["company_code"]: row["reason"]
        for row in mapping["excluded_initial_candidates"]
    }
    assert "模拟" in excluded_by_code["688052.SH"]
    assert "非MEMS" in excluded_by_code["603662.SH"]
    assert "自有MEMS" in excluded_by_code["300667.SZ"]


def test_mems_g1_has_only_the_reviewed_g2_manufacturing_dependency() -> None:
    catalog = load_industry_catalog()
    nodes = {row["node_id"]: row for row in catalog["nodes"]}
    cross_chain_edges = {
        (row["source_node_id"], row["target_node_id"], row["relationship_type"])
        for row in catalog["edges"]
        if row["source_node_id"] in G1_L4
        and nodes[row["target_node_id"]]["chain_id"] != G1_CHAIN_ID
    }
    assert cross_chain_edges == {
        ("mems_foundry_wafer_process", "mems_sensor_specialty_foundry", "depends_on")
    }


def test_mems_g1_matrix_calibrates_unmapped_nodes_and_evidence_gaps() -> None:
    theme = load_json(G1_THEME_PATH)
    matrix = load_json(G1_MATRIX_PATH)
    nodes = {row["node_id"]: row for row in theme["nodes"]}
    rows = {row["node_id"]: row for row in matrix["node_evidence_matrix"]}
    assert set(rows) == G1_L4
    assert len({row["rationale"] for row in rows.values()}) == 9
    assert all(row["next_evidence_needed"] for row in rows.values())
    for node_id, row in rows.items():
        assert nodes[node_id]["evidence_strength"] == row["evidence_strength_after"]
    for empty_node in ("mems_rf_filters_resonators", "mems_optical_micro_mirror_lidar"):
        assert rows[empty_node]["accepted_source_ids"] == []
        assert rows[empty_node]["supported_claim_ids"] == []
        assert rows[empty_node]["evidence_gap_status"] == "evidence_gap"
        assert rows[empty_node]["node_review_status"] == "needs_evidence"
        assert nodes[empty_node]["related_stock_codes"] == []
        assert nodes[empty_node]["domestic_players"] == []
    fusion = rows["intelligent_sensor_fusion_modules"]
    assert fusion["evidence_strength_after"] <= 2
    assert fusion["node_review_status"] == "needs_evidence"
    assert fusion["evidence_gap_status"] == "evidence_gap"
    assert fusion["accepted_source_ids"] == []
    assert fusion["supported_claim_ids"] == []
    assert "直接MEMS通道+融合模组量产/收入" in fusion["next_evidence_needed"]
    assert nodes["intelligent_sensor_fusion_modules"]["node_review_status"] == "needs_evidence"
    assert nodes["intelligent_sensor_fusion_modules"]["evidence_strength"] <= 2
    assert nodes["intelligent_sensor_fusion_modules"]["related_stock_codes"] == []
    assert nodes["intelligent_sensor_fusion_modules"]["domestic_players"] == []
    claims = {row["claim_id"]: row for row in theme["claims"]}
    assert "g1_claim_09" not in claims
    assert not any(
        "intelligent_sensor_fusion_modules" in row["affected_theme_nodes"]
        for row in claims.values()
    )


def test_wafer_manufacturing_g2_catalog_first_exact_tree_and_links() -> None:
    assert_catalog_first_contract(G2_CHAIN_ID, G2_THEME_ID, G2_L3, G2_L4)
    catalog = load_industry_catalog()
    chain_nodes = [row for row in catalog["nodes"] if row["chain_id"] == G2_CHAIN_ID]
    by_id = {row["node_id"]: row for row in chain_nodes}
    assert {row["node_kind"] for row in chain_nodes} == {"canonical"}
    assert all(not row["canonical_key"] for row in chain_nodes if row["level"] == "L3")
    l4_keys = [row["canonical_key"] for row in chain_nodes if row["level"] == "L4"]
    assert len(l4_keys) == len(set(l4_keys)) == 10
    assert all(
        key.startswith("wafer_manufacturing_specialty_processes:")
        for key in l4_keys
    )
    for row in chain_nodes:
        assert row["primary_path"][1] == G2_CHAIN_ID
        if row["level"] == "L4":
            assert row["parent_node_id"] in G2_L3
            assert by_id[row["parent_node_id"]]["level"] == "L3"

    link = next(
        row for row in catalog["theme_links"] if row["theme_id"] == G2_THEME_ID
    )
    assert len(link["node_links"]) == 10
    assert {
        (row["theme_node_id"], row["catalog_node_id"])
        for row in link["node_links"]
    } == {(node_id, node_id) for node_id in G2_L4}


def test_wafer_manufacturing_g2_artifacts_are_reviewed_and_meet_wave_gate() -> None:
    theme = load_json(G2_THEME_PATH)
    mapping = load_json(G2_MAPPING_PATH)
    source_pack = load_json(G2_SOURCE_PACK_PATH)
    matrix = load_json(G2_MATRIX_PATH)
    assert theme["artifact_version"] == "theme_decomposition_v1_6"
    assert mapping["evidence_contract_version"] == "mapping_evidence_roles_v2"
    assert theme["theme"]["status"] == "reviewed"
    assert {row["node_id"] for row in theme["nodes"]} == G2_L4
    assert len([row for row in source_pack["sources"] if row["review_status"] == "accepted"]) >= 10
    assert sum(
        row["source_type"] in {"company_filing", "official_report", "official_article"}
        and row["review_status"] == "accepted"
        for row in source_pack["sources"]
    ) >= 8
    assert len(theme["claims"]) >= 12
    reviewed = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    assert len(reviewed) >= 8
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == G2_L4

    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_g")
    rows = {row["chain_id"]: row for row in report["theme_results"]}
    assert rows[G2_CHAIN_ID]["ready"] is True
    assert rows[G2_CHAIN_ID]["counts"] == {
        "accepted_sources": 10,
        "primary_sources": 10,
        "claims": len(theme["claims"]),
        "accepted_source_backed_claims": len(theme["claims"]),
        "reviewed_mappings": 8,
    }


def test_wafer_manufacturing_g2_company_evidence_and_initial_universe_close() -> None:
    mapping = load_json(G2_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    reviewed = {
        row["company_code"]: row for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    excluded = {
        row["company_code"]: row for row in mapping["excluded_initial_candidates"]
    }
    assert set(reviewed) == set(G2_MAPPING_CONTRACTS)
    assert set(excluded) == G2_EXCLUDED_INITIAL
    assert set(reviewed) | set(excluded) == G2_INITIAL_UNIVERSE
    assert not set(reviewed) & set(excluded)
    for company_code, (node_id, source_id) in G2_MAPPING_CONTRACTS.items():
        row = reviewed[company_code]
        assert row["mapped_node_id"] == node_id
        items = [evidence[evidence_id] for evidence_id in row["evidence_ids"]]
        assert [item["evidence_type"] for item in items] == [
            "product_relationship",
            G2_REVENUE_ROLE_CONTRACTS[company_code],
            "business_stage",
        ]
        assert len({item["excerpt_locator"] for item in items}) == 3
        assert all(item["source_id"] == source_id for item in items)
        assert all(item["related_node_ids"] == [node_id] for item in items)
        fact = G2_FACT_CONTRACTS[company_code]
        assert tuple(item["excerpt_locator"] for item in items) == fact["locators"]
        assert all(
            phrase in item["evidence_summary"]
            for phrase, item in zip(fact["phrases"], items)
        )
        assert row["business_materiality"]
        assert row["notes"]
    assert mapping["concept_only_candidates"] == []


def test_wafer_manufacturing_g2_rejects_the_two_false_process_assignments() -> None:
    theme = load_json(G2_THEME_PATH)
    mapping = load_json(G2_MAPPING_PATH)
    reviewed = {
        row["company_code"]: row for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    claims = [row for row in theme["claims"]]
    assert reviewed["688469.SH"]["mapped_node_id"] == "mems_sensor_specialty_foundry"
    assert reviewed["688172.SH"]["mapped_node_id"] == "analog_bcd_mixed_signal_process"
    assert "CIS" not in reviewed["688469.SH"]["product_or_service"]
    assert "显示驱动" not in reviewed["688469.SH"]["relationship_summary"]
    assert "非易失" not in reviewed["688172.SH"]["product_or_service"]
    assert "EEPROM" not in reviewed["688172.SH"]["relationship_summary"]
    assert not any(
        claim["source_id"] == "g2_688469_ar2025"
        and "cmos_image_sensor_display_driver_process" in claim["affected_theme_nodes"]
        for claim in claims
    )
    assert not any(
        claim["source_id"] == "g2_688172_ar2025"
        and "embedded_nonvolatile_memory_process" in claim["affected_theme_nodes"]
        for claim in claims
    )


def test_wafer_manufacturing_g2_wide_income_stays_boundary_not_materiality() -> None:
    mapping = load_json(G2_MAPPING_PATH)
    reviewed = {
        row["company_code"]: row for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    for code in ("688981.SH", "688172.SH", "688396.SH", "600460.SH", "688469.SH"):
        row = reviewed[code]
        assert row["revenue_relevance"] in {"limited", "undisclosed"}
        assert G2_REVENUE_ROLE_CONTRACTS[code] == "revenue_boundary"
    silan = reviewed["600460.SH"]
    assert "owned-fab/captive production" in silan["relationship_summary"]
    assert "不构成对外foundry服务" in silan["notes"]


def test_wafer_manufacturing_g2_source_claim_matrix_union_is_direct() -> None:
    theme = load_json(G2_THEME_PATH)
    mapping = load_json(G2_MAPPING_PATH)
    source_pack = load_json(G2_SOURCE_PACK_PATH)
    matrix = load_json(G2_MATRIX_PATH)
    identity_fields = (
        "source_id", "source_type", "title", "publisher", "author",
        "publish_date", "url_or_ref", "access_level", "reliability_level",
        "review_status", "notes",
    )
    identity = lambda rows: {
        row["source_id"]: tuple(
            row.get(field, row.get("url") if field == "url_or_ref" else None)
            for field in identity_fields
        ) for row in rows
    }
    assert identity(theme["sources"]) == identity(mapping["sources"])
    assert identity(theme["sources"]) == identity(source_pack["sources"])
    assert all(row["author"] == row["publisher"] and row["author"] for row in theme["sources"])

    claims = {row["claim_id"]: row for row in theme["claims"]}
    accepted = {
        row["source_id"] for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    claim_union = {
        source_id for claim in claims.values()
        for source_id in (claim["source_id"], *claim["supporting_source_ids"])
    }
    matrix_union = {
        source_id for row in matrix["node_evidence_matrix"]
        for source_id in row["accepted_source_ids"]
    }
    assert accepted == claim_union == matrix_union
    for row in matrix["node_evidence_matrix"]:
        node_claims = {
            claim_id for claim_id, claim in claims.items()
            if row["node_id"] in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == node_claims
        assert set(row["accepted_source_ids"]) == {
            claims[claim_id]["source_id"] for claim_id in node_claims
        }
    for source in source_pack["sources"]:
        source_claims = {
            claim_id for claim_id, claim in claims.items()
            if source["source_id"] in (claim["source_id"], *claim["supporting_source_ids"])
        }
        assert set(source["supported_claim_ids"]) == source_claims
        assert set(source["supported_node_ids"]) == {
            node_id for claim_id in source_claims
            for node_id in claims[claim_id]["affected_theme_nodes"]
        }


def test_wafer_manufacturing_g2_process_lifecycle_and_boundaries_are_explicit() -> None:
    theme = load_json(G2_THEME_PATH)
    mapping = load_json(G2_MAPPING_PATH)
    text = json.dumps({"theme": theme, "policy": mapping["mapping_policy"]}, ensure_ascii=False)
    for stage in ("工艺可用", "tapeout", "qualification", "量产", "产能利用率", "良率", "晶圆收入"):
        assert stage in text
    for boundary in (
        "设备、材料、fabless设计与封装不归G2",
        "IDM器件收入不得冒充foundry或晶圆制造收入",
        "G1拥有MEMS器件与MEMS专用研究，G2拥有制造平台",
        "F4拥有模拟、混合信号和RF芯片产品",
        "功率半导体链拥有MOSFET、IGBT、SiC和GaN器件产品",
        "process availability不等于customer tapeout",
        "customer tapeout不等于qualification",
        "qualification不等于mass production或收入",
    ):
        assert boundary in text
    excluded = {row["company_code"]: row["reason"] for row in mapping["excluded_initial_candidates"]}
    assert "器件" in excluded["600745.SH"] and "foundry" in excluded["600745.SH"]
    assert "自用fab" in excluded["300373.SZ"] and "晶圆制造服务" in excluded["300373.SZ"]
    for row in mapping["company_mappings"]:
        if row["company_code"] in {"688396.SH", "600460.SH"}:
            assert "器件收入不冒充" in row["notes"]


def test_wafer_manufacturing_g2_cross_chain_edges_use_real_l4_owners() -> None:
    catalog = load_industry_catalog()
    nodes = {row["node_id"]: row for row in catalog["nodes"]}
    edges = {
        (row["source_node_id"], row["target_node_id"], row["relationship_type"]): row
        for row in catalog["edges"]
        if row["source_node_id"] in G2_L4 or row["target_node_id"] in G2_L4
    }
    assert set(edges) == G2_EXPECTED_EDGES
    for (source_node_id, target_node_id, relationship_type), row in edges.items():
        assert nodes[source_node_id]["level"] == "L4"
        assert nodes[target_node_id]["level"] == "L4"
        assert (source_node_id in G2_L4) != (target_node_id in G2_L4)
        assert relationship_type in {"uses", "depends_on"}
        assert "所有权" in row["notes"]
    assert nodes["krf_lithography"]["chain_id"] == "semiconductor_manufacturing_equipment"
    assert nodes["foundry_pdk_design_enablement"]["chain_id"] == "semiconductor_eda_ip_design_services"
    assert nodes["mems_foundry_wafer_process"]["chain_id"] == "mems_intelligent_sensors"
    assert nodes["power_mosfet_device"]["chain_id"] == "power_semiconductors"
    assert nodes["silicon_carbide_power_device"]["chain_id"] == "power_semiconductors"


def test_wafer_manufacturing_g2_matrix_calibrates_unmapped_process_gaps() -> None:
    theme = load_json(G2_THEME_PATH)
    matrix = load_json(G2_MATRIX_PATH)
    nodes = {row["node_id"]: row for row in theme["nodes"]}
    rows = {row["node_id"]: row for row in matrix["node_evidence_matrix"]}
    assert set(rows) == G2_L4
    assert len({row["rationale"] for row in rows.values()}) == 10
    assert all(row["next_evidence_needed"] for row in rows.values())
    for node_id, row in rows.items():
        assert nodes[node_id]["evidence_strength"] == row["evidence_strength_after"]
    for empty_node in ("rf_soi_sige_specialty_process", "embedded_nonvolatile_memory_process"):
        assert nodes[empty_node]["related_stock_codes"] == []
        assert nodes[empty_node]["domestic_players"] == []
        assert rows[empty_node]["node_review_status"] == "needs_evidence"
        assert rows[empty_node]["evidence_gap_status"] == "evidence_gap"
        assert rows[empty_node]["evidence_strength_after"] == 3
        assert rows[empty_node]["accepted_source_ids"] == ["g2_688347_ar2025"]
    compound = rows["compound_semiconductor_specialty_foundry"]
    assert compound["node_review_status"] == "reviewed"
    assert compound["evidence_gap_status"] == "covered"
    assert compound["evidence_strength_after"] == 4
    assert nodes["compound_semiconductor_specialty_foundry"]["related_stock_codes"] == ["600460.SH"]
    commercial = rows["customer_tapeout_qualification_revenue_validation"]
    assert commercial["evidence_strength_after"] == 3
    assert commercial["node_review_status"] == "needs_evidence"
    assert commercial["evidence_gap_status"] == "evidence_gap"
    assert commercial["value_capture_score_review_status"] == "provisional"
    assert commercial["bottleneck_score_review_status"] == "provisional"
    assert all(
        phrase in commercial["next_evidence_needed"]
        for phrase in ("qualification", "逐客户订单", "节点专项晶圆收入")
    )
    assert nodes["customer_tapeout_qualification_revenue_validation"]["evidence_strength"] == 3
    assert nodes["customer_tapeout_qualification_revenue_validation"]["node_review_status"] == "needs_evidence"


def test_civil_aircraft_g3_catalog_first_exact_tree_and_links() -> None:
    assert_catalog_first_contract(G3_CHAIN_ID, G3_THEME_ID, G3_L3, G3_L4)
    catalog = load_industry_catalog()
    chain_nodes = [row for row in catalog["nodes"] if row["chain_id"] == G3_CHAIN_ID]
    by_id = {row["node_id"]: row for row in chain_nodes}
    assert {row["node_kind"] for row in chain_nodes} == {"canonical"}
    assert all(not row["canonical_key"] for row in chain_nodes if row["level"] == "L3")
    l4_keys = [row["canonical_key"] for row in chain_nodes if row["level"] == "L4"]
    assert len(l4_keys) == len(set(l4_keys)) == 9
    assert all(key.startswith("civil_aircraft_aero_engines:") for key in l4_keys)
    for row in chain_nodes:
        assert row["primary_path"][1] == G3_CHAIN_ID
        if row["level"] == "L4":
            assert row["parent_node_id"] in G3_L3
            assert by_id[row["parent_node_id"]]["level"] == "L3"

    link = next(
        row for row in catalog["theme_links"] if row["theme_id"] == G3_THEME_ID
    )
    assert len(link["node_links"]) == 9
    assert {
        (row["theme_node_id"], row["catalog_node_id"])
        for row in link["node_links"]
    } == {(node_id, node_id) for node_id in G3_L4}
    assert link["unmapped_theme_node_ids"] == []


def test_civil_aircraft_g3_artifacts_are_reviewed_and_meet_wave_gate() -> None:
    theme = load_json(G3_THEME_PATH)
    mapping = load_json(G3_MAPPING_PATH)
    source_pack = load_json(G3_SOURCE_PACK_PATH)
    matrix = load_json(G3_MATRIX_PATH)
    assert theme["artifact_version"] == "theme_decomposition_v1_6"
    assert mapping["evidence_contract_version"] == "mapping_evidence_roles_v2"
    assert theme["theme"]["status"] == "reviewed"
    assert {row["node_id"] for row in theme["nodes"]} == G3_L4
    assert len([row for row in source_pack["sources"] if row["review_status"] == "accepted"]) >= 10
    assert sum(
        row["source_type"] in {"company_filing", "official_report", "official_article"}
        and row["review_status"] == "accepted"
        for row in source_pack["sources"]
    ) >= 8
    assert len(theme["claims"]) >= 12
    reviewed = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    assert len(reviewed) >= 8
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == G3_L4

    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_g")
    rows = {row["chain_id"]: row for row in report["theme_results"]}
    assert rows[G3_CHAIN_ID]["ready"] is True
    assert rows[G3_CHAIN_ID]["counts"]["accepted_sources"] >= 10
    assert rows[G3_CHAIN_ID]["counts"]["primary_sources"] >= 8
    assert rows[G3_CHAIN_ID]["counts"]["claims"] >= 12
    assert rows[G3_CHAIN_ID]["counts"]["reviewed_mappings"] == 8


def test_civil_aircraft_g3_company_evidence_and_initial_universe_close() -> None:
    mapping = load_json(G3_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    reviewed = {
        row["company_code"]: row for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    excluded = {
        row["company_code"]: row for row in mapping["excluded_initial_candidates"]
    }
    assert set(reviewed) == set(G3_MAPPING_CONTRACTS)
    assert set(excluded) == G3_EXCLUDED_INITIAL
    assert (set(reviewed) & G3_INITIAL_UNIVERSE) | set(excluded) == G3_INITIAL_UNIVERSE
    assert not set(reviewed) & set(excluded)
    assert set(reviewed) - G3_INITIAL_UNIVERSE == {"603308.SH"}
    assert "补充" in reviewed["603308.SH"]["notes"]
    for company_code, (node_id, source_id) in G3_MAPPING_CONTRACTS.items():
        row = reviewed[company_code]
        assert row["mapped_node_id"] == node_id
        items = [evidence[evidence_id] for evidence_id in row["evidence_ids"]]
        assert [item["evidence_type"] for item in items] == [
            "product_relationship",
            "revenue_boundary" if company_code in {"600893.SH", "000738.SZ", "600391.SH", "600765.SH", "600862.SH", "300696.SZ", "300900.SZ", "688239.SH", "603308.SH"} else "revenue_materiality",
            "business_stage",
        ]
        assert len({item["excerpt_locator"] for item in items}) == 3
        assert all(item["source_id"] == source_id for item in items)
        assert all(item["related_node_ids"] == [node_id] for item in items)
        assert row["business_materiality"]
        assert row["notes"]
    assert mapping["concept_only_candidates"] == []


def test_civil_aircraft_g3_rejects_non_civil_and_lifecycle_false_positives() -> None:
    theme = load_json(G3_THEME_PATH)
    mapping = load_json(G3_MAPPING_PATH)
    text = json.dumps({"theme": theme, "policy": mapping["mapping_policy"]}, ensure_ascii=False)
    for stage in (
        "供应商资格",
        "适航认证",
        "批量生产",
        "订单",
        "交付",
        "装机保有量",
        "备件/MRO",
        "确认收入",
    ):
        assert stage in text
    for boundary in (
        "军用-only aircraft不得映射",
        "商业航天保持商业航天链所有权",
        "低空、eVTOL、UAV保持低空链所有权",
        "泛先进材料不得映射",
        "公司总营收与军品收入不得冒充民机节点收入",
        "供应商资格不等于适航认证",
        "适航认证不等于批量生产",
        "批量生产不等于交付或确认收入",
    ):
        assert boundary in text
    excluded = {
        row["company_code"]: row["reason"]
        for row in mapping["excluded_initial_candidates"]
    }
    assert "直升机" in excluded["600038.SH"]
    assert "低空" in excluded["600038.SH"]
    reviewed = {row["company_code"]: row for row in mapping["company_mappings"]}
    assert reviewed["000768.SZ"]["mapped_node_id"] != "civil_aircraft_airframe_final_assembly"
    assert "非总装" in reviewed["000768.SZ"]["notes"]
    assert "军民混合" in reviewed["600893.SH"]["notes"]
    assert "集团" in reviewed["600893.SH"]["notes"]
    assert "军民混合" in reviewed["000738.SZ"]["notes"]
    assert "叶片" in reviewed["600391.SH"]["product_or_service"]
    assert "机匣或环件本身不足以映射hot-section" in reviewed["600391.SH"]["notes"]
    assert "商用航空发动机锻铸" in reviewed["600765.SH"]["product_or_service"]
    assert "热端部件" in reviewed["688239.SH"]["product_or_service"]
    assert "高压涡轮机匣" in reviewed["688239.SH"]["relationship_summary"]
    assert reviewed["688239.SH"]["business_stage"] == "primary_business"
    assert reviewed["688239.SH"]["bottleneck_relevance"] == "core"
    assert reviewed["600391.SH"]["bottleneck_relevance"] == "adjacent"
    assert reviewed["600391.SH"]["confidence"] <= 0.88
    assert "未证明商发交付对应叶片" in reviewed["600391.SH"]["notes"]
    assert reviewed["600765.SH"]["business_stage"] == "reserve_stage"
    assert reviewed["600765.SH"]["business_materiality"] == "reserve_only"
    assert "未定位至叶片、盘或热端" in reviewed["600765.SH"]["notes"]
    assert reviewed["603308.SH"]["bottleneck_relevance"] == "adjacent"
    assert reviewed["603308.SH"]["confidence"] <= 0.9
    assert "不能称为民机热端" in reviewed["603308.SH"]["notes"]


def test_civil_aircraft_g3_visible_stock_pool_excludes_reserve_mappings() -> None:
    theme = load_json(G3_THEME_PATH)
    mapping = load_json(G3_MAPPING_PATH)
    effective = {
        row["company_code"]: row
        for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
        and row["business_stage"] == "primary_business"
        and row["business_materiality"] not in {"reserve_only", "concept_only"}
    }
    assert set(effective) == {
        "000768.SZ", "600893.SH", "000738.SZ", "600391.SH",
        "600862.SH", "300696.SZ", "688239.SH", "603308.SH",
    }
    nodes = {row["node_id"]: row for row in theme["nodes"]}
    visible_codes = {
        code for node in nodes.values() for code in node["related_stock_codes"]
    }
    assert visible_codes == set(effective)
    for node in nodes.values():
        expected = {
            code for code, row in effective.items()
            if row["mapped_node_id"] == node["node_id"]
        }
        assert set(node["related_stock_codes"]) == expected
        assert len(node["domestic_players"]) == len(node["related_stock_codes"])
    assert "300900.SZ" not in visible_codes
    assert "600765.SH" not in visible_codes


def test_civil_aircraft_g3_source_claim_matrix_union_is_direct() -> None:
    theme = load_json(G3_THEME_PATH)
    mapping = load_json(G3_MAPPING_PATH)
    source_pack = load_json(G3_SOURCE_PACK_PATH)
    matrix = load_json(G3_MATRIX_PATH)
    identity_fields = (
        "source_id", "source_type", "title", "publisher", "author",
        "publish_date", "url_or_ref", "access_level", "reliability_level",
        "review_status", "notes",
    )
    identity = lambda rows: {
        row["source_id"]: tuple(
            row.get(field, row.get("url") if field == "url_or_ref" else None)
            for field in identity_fields
        ) for row in rows
    }
    assert identity(theme["sources"]) == identity(mapping["sources"])
    assert identity(theme["sources"]) == identity(source_pack["sources"])
    assert all(row["author"] == row["publisher"] and row["author"] for row in theme["sources"])

    claims = {row["claim_id"]: row for row in theme["claims"]}
    accepted = {
        row["source_id"] for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    claim_union = {
        source_id for claim in claims.values()
        for source_id in (claim["source_id"], *claim["supporting_source_ids"])
    }
    matrix_union = {
        source_id for row in matrix["node_evidence_matrix"]
        for source_id in row["accepted_source_ids"]
    }
    assert accepted == claim_union == matrix_union
    for row in matrix["node_evidence_matrix"]:
        node_claims = {
            claim_id for claim_id, claim in claims.items()
            if row["node_id"] in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == node_claims
        assert set(row["accepted_source_ids"]) == {
            claims[claim_id]["source_id"] for claim_id in node_claims
        }
    for source in source_pack["sources"]:
        source_claims = {
            claim_id for claim_id, claim in claims.items()
            if source["source_id"] in (claim["source_id"], *claim["supporting_source_ids"])
        }
        assert set(source["supported_claim_ids"]) == source_claims
        assert set(source["supported_node_ids"]) == {
            node_id for claim_id in source_claims
            for node_id in claims[claim_id]["affected_theme_nodes"]
        }


def test_civil_aircraft_g3_cross_chain_edges_use_real_l4_owners() -> None:
    catalog = load_industry_catalog()
    nodes = {row["node_id"]: row for row in catalog["nodes"]}
    edges = {
        (row["source_node_id"], row["target_node_id"], row["relationship_type"]): row
        for row in catalog["edges"]
        if row["source_node_id"] in G3_L4 or row["target_node_id"] in G3_L4
    }
    assert set(edges) == G3_EXPECTED_EDGES
    for (source_node_id, target_node_id, relationship_type), row in edges.items():
        assert nodes[source_node_id]["level"] == "L4"
        assert nodes[target_node_id]["level"] == "L4"
        assert (source_node_id in G3_L4) != (target_node_id in G3_L4)
        assert relationship_type in {"uses", "depends_on"}
        assert "所有权" in row["notes"]
    assert nodes["metal_cutting_grinding_machine_tools"]["chain_id"] == "industrial_machine_tools_cnc"
    assert nodes["multi_axis_composite_machining_centers"]["chain_id"] == "industrial_machine_tools_cnc"


def test_civil_aircraft_g3_matrix_calibrates_empty_nodes_and_evidence_gaps() -> None:
    theme = load_json(G3_THEME_PATH)
    matrix = load_json(G3_MATRIX_PATH)
    nodes = {row["node_id"]: row for row in theme["nodes"]}
    rows = {row["node_id"]: row for row in matrix["node_evidence_matrix"]}
    assert set(rows) == G3_L4
    assert len({row["rationale"] for row in rows.values()}) == 9
    assert all(row["next_evidence_needed"] for row in rows.values())
    for node_id, row in rows.items():
        assert nodes[node_id]["evidence_strength"] == row["evidence_strength_after"]
    for empty_node in (
        "civil_aircraft_airframe_final_assembly",
        "airborne_avionics_electromechanical_systems",
        "landing_gear_wheels_brakes_systems",
        "airworthiness_certification_production_ramp",
        "mro_spares_installed_base_services",
    ):
        assert nodes[empty_node]["related_stock_codes"] == []
        assert nodes[empty_node]["domestic_players"] == []
        assert rows[empty_node]["node_review_status"] == "needs_evidence"
        assert rows[empty_node]["evidence_gap_status"] == "evidence_gap"
        assert rows[empty_node]["evidence_strength_after"] <= 3
    assert rows["airworthiness_certification_production_ramp"]["value_capture_score_review_status"] == "provisional"
    assert rows["mro_spares_installed_base_services"]["value_capture_score_review_status"] == "provisional"
    landing = rows["landing_gear_wheels_brakes_systems"]
    assert landing["evidence_strength_after"] <= 2
    assert "零组件" in landing["rationale"]
    hot = rows["engine_hot_section_blades_disks"]
    assert hot["evidence_strength_after"] == 4
    assert hot["node_review_status"] == "needs_evidence"
    assert hot["evidence_gap_status"] == "evidence_gap"
    assert "逐公司" in hot["next_evidence_needed"]


def test_nuclear_power_equipment_g4_catalog_first_exact_tree_and_links() -> None:
    assert_catalog_first_contract(G4_CHAIN_ID, G4_THEME_ID, G4_L3, G4_L4)
    catalog = load_industry_catalog()
    chain_nodes = [row for row in catalog["nodes"] if row["chain_id"] == G4_CHAIN_ID]
    by_id = {row["node_id"]: row for row in chain_nodes}
    assert len(chain_nodes) == 13
    assert all(not row["canonical_key"] for row in chain_nodes if row["level"] == "L3")
    l4_keys = [row["canonical_key"] for row in chain_nodes if row["level"] == "L4"]
    assert len(l4_keys) == len(set(l4_keys)) == 9
    assert all(key.startswith("nuclear_power_equipment:") for key in l4_keys)
    for row in chain_nodes:
        assert row["primary_path"][1] == G4_CHAIN_ID
        if row["level"] == "L4":
            assert row["parent_node_id"] in G4_L3
            assert by_id[row["parent_node_id"]]["level"] == "L3"
    link = next(
        row for row in catalog["theme_links"] if row["theme_id"] == G4_THEME_ID
    )
    assert len(link["node_links"]) == 9
    assert {
        (row["theme_node_id"], row["catalog_node_id"])
        for row in link["node_links"]
    } == {(node_id, node_id) for node_id in G4_L4}
    assert link["unmapped_theme_node_ids"] == []


def test_nuclear_power_equipment_g4_artifacts_are_reviewed_and_meet_wave_gate() -> None:
    theme = load_json(G4_THEME_PATH)
    mapping = load_json(G4_MAPPING_PATH)
    source_pack = load_json(G4_SOURCE_PACK_PATH)
    matrix = load_json(G4_MATRIX_PATH)
    assert theme["artifact_version"] == "theme_decomposition_v1_6"
    assert mapping["evidence_contract_version"] == "mapping_evidence_roles_v2"
    assert theme["theme"]["status"] == "reviewed"
    assert {row["node_id"] for row in theme["nodes"]} == G4_L4
    assert len([row for row in source_pack["sources"] if row["review_status"] == "accepted"]) == 10
    assert all(
        row["source_type"] == "company_filing"
        and row["reliability_level"] == "S0"
        for row in source_pack["sources"]
    )
    assert len(theme["claims"]) >= 12
    reviewed = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    assert len(reviewed) == 10
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == G4_L4
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_g")
    row = next(row for row in report["theme_results"] if row["chain_id"] == G4_CHAIN_ID)
    assert row["ready"] is True
    assert row["counts"] == {
        "accepted_sources": 10,
        "primary_sources": 10,
        "claims": len(theme["claims"]),
        "accepted_source_backed_claims": len(theme["claims"]),
        "reviewed_mappings": 9,
    }


def test_nuclear_power_equipment_g4_company_evidence_and_initial_universe_close() -> None:
    mapping = load_json(G4_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    reviewed = {
        row["company_code"]: row for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    assert set(reviewed) == G4_INITIAL_UNIVERSE == set(G4_MAPPING_CONTRACTS)
    assert mapping["excluded_initial_candidates"] == []
    assert mapping["concept_only_candidates"] == []
    for company_code, (node_id, source_id) in G4_MAPPING_CONTRACTS.items():
        row = reviewed[company_code]
        assert row["mapped_node_id"] == node_id
        assert row["business_stage"] == G4_BUSINESS_STAGE_CONTRACTS[company_code]
        items = [evidence[evidence_id] for evidence_id in row["evidence_ids"]]
        assert [item["evidence_type"] for item in items] == [
            "product_relationship",
            G4_REVENUE_ROLE_CONTRACTS[company_code],
            "business_stage",
        ]
        assert len({item["excerpt_locator"] for item in items}) == 3
        assert all(item["source_id"] == source_id for item in items)
        assert all(item["related_node_ids"] == [node_id] for item in items)
        assert row["notes"]


def test_nuclear_power_equipment_g4_uses_direct_pages_not_generic_or_future_plans() -> None:
    theme = load_json(G4_THEME_PATH)
    mapping = load_json(G4_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    reviewed = {row["company_code"]: row for row in mapping["company_mappings"]}
    for company_code, locators in G4_FACT_LOCATOR_CONTRACTS.items():
        row = reviewed[company_code]
        assert tuple(evidence[evidence_id]["excerpt_locator"] for evidence_id in row["evidence_ids"]) == locators

    dongfang = reviewed["600875.SH"]
    assert dongfang["mapped_node_id"] == "reactor_pressure_vessel_steam_generator"
    assert "蒸汽发生器" in dongfang["product_or_service"]
    assert not any(
        "turbine_generator_conventional_island" in claim["affected_theme_nodes"]
        for claim in theme["claims"]
    )
    assert "p.9-10 / PDF_PAGE=9-10" in evidence["g4_ev_603308_product"]["excerpt_locator"]

    forbidden_locators = {
        "g4_ev_000777_product": ("p.12", "PDF_PAGE=12"),
        "g4_ev_000777_stage": ("p.14", "PDF_PAGE=14"),
        "g4_ev_002255_stage": ("p.33", "PDF_PAGE=33"),
        "g4_ev_002318_product": ("p.9", "PDF_PAGE=9"),
        "g4_ev_002318_stage": ("p.27", "PDF_PAGE=27"),
    }
    for evidence_id, forbidden in forbidden_locators.items():
        locator = evidence[evidence_id]["excerpt_locator"]
        assert all(value not in locator for value in forbidden)


def test_nuclear_power_equipment_g4_visible_pool_excludes_reserve_and_empty_n04() -> None:
    theme = load_json(G4_THEME_PATH)
    mapping = load_json(G4_MAPPING_PATH)
    effective = {
        row["company_code"]: row
        for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
        and row["business_stage"] == "primary_business"
        and row["business_materiality"] not in {"reserve_only", "concept_only"}
    }
    assert len(effective) == 9
    assert "002318.SZ" not in effective
    nodes = {row["node_id"]: row for row in theme["nodes"]}
    visible_codes = {
        code for node in nodes.values() for code in node["related_stock_codes"]
    }
    assert visible_codes == set(effective)
    conventional = nodes["turbine_generator_conventional_island"]
    assert conventional["related_stock_codes"] == []
    assert conventional["domestic_players"] == []
    assert conventional["node_review_status"] == "needs_evidence"
    assert conventional["evidence_strength"] == 1


def test_nuclear_power_equipment_g4_rejects_fusion_generic_nuclear_and_revenue_false_positives() -> None:
    theme = load_json(G4_THEME_PATH)
    mapping = load_json(G4_MAPPING_PATH)
    text = json.dumps(
        {"theme": theme, "mapping_policy": mapping["mapping_policy"]},
        ensure_ascii=False,
    )
    for stage in (
        "项目核准", "采购", "订单", "制造", "交付", "验收", "维护", "确认收入",
    ):
        assert stage in text
    for boundary in (
        "所有聚变claim、项目与订单保持controlled_nuclear_fusion所有权",
        "泛核政策不得映射",
        "无裂变产品或项目关系的材料与通用能力不得映射",
        "普通阀门、电机、钢管、容器和化工设备收入不得冒充核电收入",
        "项目核准不等于采购或订单",
        "订单不等于制造、交付或验收",
        "交付或验收不等于确认收入",
    ):
        assert boundary in text
    reviewed = {row["company_code"]: row for row in mapping["company_mappings"]}
    assert "宽能源收入" in reviewed["601727.SH"]["notes"]
    assert "核岛主设备" in reviewed["601727.SH"]["product_or_service"]
    assert "普通电机" in reviewed["000922.SZ"]["notes"]
    assert "普通阀门" in reviewed["002438.SZ"]["notes"]
    assert "普通阀门" in reviewed["000777.SZ"]["notes"]
    assert "普通容器" in reviewed["002255.SZ"]["notes"]
    assert "炼化设备" in reviewed["603169.SH"]["notes"]
    assert "普通工业钢管" in reviewed["002318.SZ"]["notes"]
    assert "聚变" in reviewed["603308.SH"]["notes"]


def test_nuclear_power_equipment_g4_source_claim_matrix_union_is_direct() -> None:
    theme = load_json(G4_THEME_PATH)
    mapping = load_json(G4_MAPPING_PATH)
    source_pack = load_json(G4_SOURCE_PACK_PATH)
    matrix = load_json(G4_MATRIX_PATH)
    identity_fields = (
        "source_id", "source_type", "title", "publisher", "author",
        "publish_date", "url_or_ref", "access_level", "reliability_level",
        "review_status", "notes",
    )
    identity = lambda rows: {
        row["source_id"]: tuple(
            row.get(field, row.get("url") if field == "url_or_ref" else None)
            for field in identity_fields
        ) for row in rows
    }
    assert identity(theme["sources"]) == identity(mapping["sources"])
    assert identity(theme["sources"]) == identity(source_pack["sources"])
    assert all(row["author"] == row["publisher"] and row["author"] for row in theme["sources"])
    claims = {row["claim_id"]: row for row in theme["claims"]}
    accepted = {
        row["source_id"] for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    claim_union = {
        source_id for claim in claims.values()
        for source_id in (claim["source_id"], *claim["supporting_source_ids"])
    }
    matrix_union = {
        source_id for row in matrix["node_evidence_matrix"]
        for source_id in row["accepted_source_ids"]
    }
    assert accepted == claim_union == matrix_union
    for row in matrix["node_evidence_matrix"]:
        node_claims = {
            claim_id for claim_id, claim in claims.items()
            if row["node_id"] in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == node_claims
        assert set(row["accepted_source_ids"]) == {
            claims[claim_id]["source_id"] for claim_id in node_claims
        }
    for source in source_pack["sources"]:
        source_claims = {
            claim_id for claim_id, claim in claims.items()
            if source["source_id"] in (claim["source_id"], *claim["supporting_source_ids"])
        }
        assert set(source["supported_claim_ids"]) == source_claims
        assert set(source["supported_node_ids"]) == {
            node_id for claim_id in source_claims
            for node_id in claims[claim_id]["affected_theme_nodes"]
        }


def test_nuclear_power_equipment_g4_cross_chain_edges_use_real_l4_owners() -> None:
    catalog = load_industry_catalog()
    nodes = {row["node_id"]: row for row in catalog["nodes"]}
    edges = {
        (row["source_node_id"], row["target_node_id"], row["relationship_type"]): row
        for row in catalog["edges"]
        if row["source_node_id"] in G4_L4 or row["target_node_id"] in G4_L4
    }
    assert set(edges) == G4_EXPECTED_EDGES
    for (source_node_id, target_node_id, relationship_type), row in edges.items():
        assert nodes[source_node_id]["level"] == "L4"
        assert nodes[target_node_id]["level"] == "L4"
        assert (source_node_id in G4_L4) != (target_node_id in G4_L4)
        assert relationship_type == "uses"
        assert "所有权" in row["notes"]
    assert nodes["metal_cutting_grinding_machine_tools"]["chain_id"] == (
        "industrial_machine_tools_cnc"
    )


def test_nuclear_power_equipment_g4_matrix_keeps_empty_service_nodes_readable() -> None:
    theme = load_json(G4_THEME_PATH)
    matrix = load_json(G4_MATRIX_PATH)
    nodes = {row["node_id"]: row for row in theme["nodes"]}
    rows = {row["node_id"]: row for row in matrix["node_evidence_matrix"]}
    assert set(rows) == G4_L4
    assert len({row["rationale"] for row in rows.values()}) == 9
    assert all(row["next_evidence_needed"] for row in rows.values())
    for node_id, row in rows.items():
        assert nodes[node_id]["evidence_strength"] == row["evidence_strength_after"]
    for empty_node in (
        "turbine_generator_conventional_island",
        "nuclear_fuel_cycle_handling_services",
        "engineering_construction_commissioning",
        "maintenance_inspection_life_extension",
    ):
        assert nodes[empty_node]["related_stock_codes"] == []
        assert nodes[empty_node]["domestic_players"] == []
        assert rows[empty_node]["node_review_status"] == "needs_evidence"
        assert rows[empty_node]["evidence_gap_status"] == "evidence_gap"
        assert rows[empty_node]["evidence_strength_after"] <= 2
    validation = rows["project_approval_orders_delivery_revenue_validation"]
    assert validation["accepted_source_ids"]
    assert validation["supported_claim_ids"]
    assert validation["node_review_status"] == "reviewed"
    assert "项目核准" in validation["rationale"]
    assert "确认收入" in validation["next_evidence_needed"]
