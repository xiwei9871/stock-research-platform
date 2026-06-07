from pathlib import Path

from stock_research.tech_chain_taxonomy import load_taxonomy


def test_load_taxonomy_v1_contains_core_chains() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))

    assert taxonomy.version == "tech_chain_taxonomy_v1"
    assert len(taxonomy.chains) == 20
    chain_ids = {chain.chain_id for chain in taxonomy.chains}
    assert {
        "ai_optical_interconnect",
        "ai_compute_chips",
        "hbm_high_end_memory",
        "mlcc_high_end_passives",
        "semiconductor_equipment",
    }.issubset(chain_ids)

    optical = taxonomy.chain_by_id("ai_optical_interconnect")
    assert "800G" in optical.bottleneck_dimensions["bandwidth_generation"]
    assert "CPO" in optical.bottleneck_dimensions["architecture_route"]
    assert "EML" in optical.bottleneck_dimensions["critical_components"]

    hbm = taxonomy.chain_by_id("hbm_high_end_memory")
    assert "HBM3E" in hbm.bottleneck_dimensions["memory_generation"]
    assert "Samsung" in hbm.global_reference_entities
    assert "SK hynix" in hbm.global_reference_entities

    mlcc = taxonomy.chain_by_id("mlcc_high_end_passives")
    assert "AI server PDN" in mlcc.bottleneck_dimensions["power_density"]
    assert "Murata" in mlcc.global_reference_entities
