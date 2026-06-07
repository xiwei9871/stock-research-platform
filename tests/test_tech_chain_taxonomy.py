from pathlib import Path

import pytest

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
    assert "光通信" in optical.chain_context_terms
    assert "光通信模块" in optical.product_exposure_terms
    assert "光通信收发模块" in optical.product_exposure_terms
    assert "800G" in optical.bottleneck_dimensions["bandwidth_generation"]
    assert "CPO" in optical.bottleneck_dimensions["architecture_route"]
    assert "EML" in optical.bottleneck_dimensions["critical_components"]

    ai_compute = taxonomy.chain_by_id("ai_compute_chips")
    assert "智能计算芯片" in ai_compute.chain_context_terms
    assert "MLU" in ai_compute.product_exposure_terms

    hbm = taxonomy.chain_by_id("hbm_high_end_memory")
    assert "HBM3E" in hbm.bottleneck_dimensions["memory_generation"]
    assert "TSV" in hbm.bottleneck_dimensions["stacking_tsv"]
    assert "良率" in hbm.bottleneck_dimensions["qualification_yield"]
    assert "Samsung" in hbm.global_reference_entities
    assert "SK hynix" in hbm.global_reference_entities

    mlcc = taxonomy.chain_by_id("mlcc_high_end_passives")
    assert "多层陶瓷电容器" in mlcc.chain_context_terms
    assert "片式多层陶瓷电容器" in mlcc.product_exposure_terms
    assert "AI server PDN" in mlcc.bottleneck_dimensions["power_density"]
    assert "陶瓷粉体" in mlcc.bottleneck_dimensions["materials_process"]
    assert "Murata" in mlcc.global_reference_entities


def test_load_taxonomy_rejects_duplicate_chain_id(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.json"
    path.write_text(
        """
        {
          "version": "x",
          "chains": [
            {
              "chain_id": "duplicate",
              "display_name": "First",
              "chain_context_terms": [],
              "product_exposure_terms": [],
              "bottleneck_dimensions": {},
              "technical_execution_terms": [],
              "commercial_validation_terms": [],
              "invalidation_terms": [],
              "global_reference_entities": []
            },
            {
              "chain_id": "duplicate",
              "display_name": "Second",
              "chain_context_terms": [],
              "product_exposure_terms": [],
              "bottleneck_dimensions": {},
              "technical_execution_terms": [],
              "commercial_validation_terms": [],
              "invalidation_terms": [],
              "global_reference_entities": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate chain_id"):
        load_taxonomy(path)


def test_load_taxonomy_rejects_non_list_chains(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.json"
    path.write_text('{"version":"x","chains":{"bad":[]}}', encoding="utf-8")

    with pytest.raises(ValueError, match="chains must be a list"):
        load_taxonomy(path)
