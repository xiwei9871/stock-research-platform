import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_research.tech_chain_taxonomy import (
    CHAIN_EVIDENCE_COLUMNS,
    CHAIN_QUALITY_COLUMNS,
    _explicit_true,
    build_chain_evidence_review,
    build_chain_mapping,
    build_chain_quality_review,
    load_taxonomy,
)


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


def test_load_taxonomy_rejects_missing_or_invalid_version(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing_version.json"
    missing_path.write_text(json.dumps({"chains": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="version must be a non-empty string"):
        load_taxonomy(missing_path)

    numeric_path = tmp_path / "numeric_version.json"
    numeric_path.write_text(json.dumps({"version": 1, "chains": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="version must be a non-empty string"):
        load_taxonomy(numeric_path)


def test_load_taxonomy_rejects_invalid_term_entries(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.json"
    payload = {"version": "x", "chains": [_minimal_chain()]}
    payload["chains"][0]["chain_context_terms"] = [None, ""]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="chain_context_terms entries must be non-empty strings",
    ):
        load_taxonomy(path)


def test_load_taxonomy_rejects_invalid_dimension_entries(tmp_path: Path) -> None:
    path = tmp_path / "taxonomy.json"
    payload = {"version": "x", "chains": [_minimal_chain()]}
    payload["chains"][0]["bottleneck_dimensions"]["memory_generation"] = ["HBM3E", None]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="bottleneck_dimensions entries must be non-empty strings",
    ):
        load_taxonomy(path)


def test_build_chain_mapping_identifies_chain_context_and_product_exposure() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "industry_name": "通信设备",
                "product_snippet": "光通信模块、光通信收发模块收入占比高",
            },
            {
                "asset_id": "CN:SH:688256",
                "stock_name": "寒武纪",
                "trade_date": "2025-08-22",
                "industry_name": "半导体",
                "product_snippet": "云端产品线 智能计算芯片 MLU",
            },
            {
                "asset_id": "CN:SZ:300476",
                "stock_name": "胜宏科技",
                "trade_date": "2025-07-04",
                "industry_name": "电子元件",
                "product_snippet": "AI服务器PCB 高阶HDI 高多层板",
            },
        ]
    )

    mapping = build_chain_mapping(candidates=candidates, taxonomy=taxonomy)
    rows = mapping.set_index("asset_id")

    assert rows.loc["CN:SZ:300308", "primary_chain_id"] == "ai_optical_interconnect"
    assert rows.loc["CN:SZ:300308", "product_exposure_quality"] == "strong"
    assert rows.loc["CN:SH:688256", "primary_chain_id"] == "ai_compute_chips"
    assert rows.loc["CN:SZ:300476", "primary_chain_id"] == "ai_server_pcb"


def test_build_chain_mapping_uses_wide_candidate_fields_and_strips_blank_ids() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "  CN:SZ:300308  ",
                "stock_name": "中际旭创",
                "trade_date": 20250620,
                "industry_name": "通信设备",
                "product_snippet": "",
                "technical_snippet": "CPO 光引擎 光通信模块",
            },
            {
                "asset_id": "   ",
                "stock_name": "空白ID",
                "trade_date": "2025-06-20",
                "industry_name": "通信设备",
                "product_snippet": "",
                "technical_snippet": "CPO 光引擎 光通信模块",
            },
        ]
    )

    mapping = build_chain_mapping(candidates=candidates, taxonomy=taxonomy)

    assert mapping["asset_id"].tolist() == ["CN:SZ:300308"]
    assert mapping.loc[0, "trade_date"] == "2025-06-20"
    assert mapping.loc[0, "primary_chain_id"] == "ai_optical_interconnect"


def test_build_chain_mapping_prefers_product_chain_over_overlapping_memory_terms() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:688256",
                "stock_name": "寒武纪",
                "trade_date": "2025-08-22",
                "industry_name": "半导体",
                "product_snippet": "AI芯片 GPU HBM3E 高带宽内存",
            },
        ]
    )

    mapping = build_chain_mapping(candidates=candidates, taxonomy=taxonomy)

    assert mapping.loc[0, "primary_chain_id"] == "ai_compute_chips"
    assert "hbm_high_end_memory" in mapping.loc[0, "matched_chain_ids"].split("|")


def test_build_chain_mapping_preserves_string_asset_ids_with_leading_zeroes() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    candidates = pd.DataFrame(
        [
            {
                "asset_id": "000001",
                "stock_name": "MLCC供应商",
                "trade_date": "2025-06-20",
                "industry_name": "电子元件",
                "product_snippet": "MLCC 多层陶瓷电容器",
            },
        ]
    )

    mapping = build_chain_mapping(candidates=candidates, taxonomy=taxonomy)

    assert mapping.loc[0, "asset_id"] == "000001"


def test_build_chain_evidence_review_maps_dimensions_and_filters_future_rows() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "product_exposure_quality": "strong",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-05-22",
                "evidence_type": "technical_barrier",
                "source_type": "broker_report",
                "source_url": "https://example.com/cpo",
                "matched_keyword": "CPO",
                "evidence_snippet": "持续扩产备料并积极研发布局CPO等",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-09-17",
                "evidence_type": "technical_barrier",
                "matched_keyword": "1.6T",
                "evidence_snippet": "1.6T上量将进一步提升盈利",
                "as_of_safe": False,
            },
        ]
    )

    review = build_chain_evidence_review(
        mapping=mapping, evidence=evidence, taxonomy=taxonomy
    )

    assert len(review) == 1
    assert review.columns.tolist() == [
        "asset_id",
        "stock_name",
        "trade_date",
        "chain_id",
        "chain_name",
        "bottleneck_dimension",
        "matched_evidence_term",
        "evidence_quality",
        "evidence_date",
        "source_type",
        "source_url",
        "snippet",
    ]
    row = review.iloc[0]
    assert row["asset_id"] == "CN:SZ:300308"
    assert row["chain_id"] == "ai_optical_interconnect"
    assert row["bottleneck_dimension"] == "architecture_route"
    assert row["matched_evidence_term"] == "CPO"
    assert row["evidence_quality"] == "strong"
    assert row["source_type"] == "broker_report"
    assert row["source_url"] == "https://example.com/cpo"


def test_build_chain_evidence_review_maps_multiple_dimensions_from_full_text() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "product_exposure_quality": "strong",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-05-22",
                "evidence_type": "technical_barrier",
                "matched_keyword": "CPO",
                "evidence_snippet": "3.2T CPO 客户导入 产能爬坡",
                "as_of_safe": True,
            },
        ]
    )

    review = build_chain_evidence_review(
        mapping=mapping, evidence=evidence, taxonomy=taxonomy
    )

    assert set(review["bottleneck_dimension"]) >= {
        "architecture_route",
        "bandwidth_generation",
        "customer_delivery",
    }


def test_chain_evidence_quality_downgrades_invalidation_context() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "product_exposure_quality": "strong",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-05-22",
                "evidence_type": "invalidation",
                "matched_keyword": "大客户导入",
                "evidence_snippet": "大客户导入不及预期 认证进度延后",
                "as_of_safe": True,
            },
        ]
    )

    review = build_chain_evidence_review(
        mapping=mapping, evidence=evidence, taxonomy=taxonomy
    )

    assert not review.empty
    assert set(review["evidence_quality"]) == {"weak"}


def test_chain_evidence_quality_downgrades_multi_term_invalidation_context() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "product_exposure_quality": "strong",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-05-22",
                "evidence_type": "invalidation",
                "matched_keyword": "800G",
                "evidence_snippet": "800G 1.6T",
                "as_of_safe": True,
            },
        ]
    )

    review = build_chain_evidence_review(
        mapping=mapping, evidence=evidence, taxonomy=taxonomy
    )

    assert set(review["matched_evidence_term"]) == {"800G", "1.6T"}
    assert set(review["evidence_quality"]) == {"weak"}


def test_chain_evidence_quality_downgrades_multi_term_risk_context() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "product_exposure_quality": "strong",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-05-22",
                "evidence_type": "risk",
                "matched_keyword": "800G",
                "evidence_snippet": "800G 1.6T",
                "as_of_safe": True,
            },
        ]
    )

    review = build_chain_evidence_review(
        mapping=mapping, evidence=evidence, taxonomy=taxonomy
    )

    assert set(review["matched_evidence_term"]) == {"800G", "1.6T"}
    assert set(review["evidence_quality"]) == {"weak"}


def test_chain_evidence_review_rejects_malformed_as_of_safe_values() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "product_exposure_quality": "strong",
            }
        ]
    )
    base_evidence = {
        "asset_id": "CN:SZ:300308",
        "candidate_trade_date": "2025-06-20",
        "evidence_date": "2025-05-22",
        "evidence_type": "technical_barrier",
        "matched_keyword": "CPO",
        "evidence_snippet": "CPO",
    }

    for malformed_value in [1, "true", "yes", "y", "1", "TRUE"]:
        evidence = pd.DataFrame([{**base_evidence, "as_of_safe": malformed_value}])

        review = build_chain_evidence_review(
            mapping=mapping, evidence=evidence, taxonomy=taxonomy
        )

        assert review.empty, f"accepted malformed as_of_safe={malformed_value!r}"

    valid_review = build_chain_evidence_review(
        mapping=mapping,
        evidence=pd.DataFrame([{**base_evidence, "as_of_safe": True}]),
        taxonomy=taxonomy,
    )
    assert not valid_review.empty

    pandas_bool_review = build_chain_evidence_review(
        mapping=mapping,
        evidence=pd.DataFrame(
            [
                {
                    **base_evidence,
                    "as_of_safe": pd.Series([True], dtype="boolean").iloc[0],
                }
            ]
        ),
        taxonomy=taxonomy,
    )
    assert not pandas_bool_review.empty

    numpy_bool_review = build_chain_evidence_review(
        mapping=mapping,
        evidence=pd.DataFrame([{**base_evidence, "as_of_safe": np.bool_(True)}]),
        taxonomy=taxonomy,
    )
    assert not numpy_bool_review.empty


def test_explicit_true_accepts_boolean_scalars_but_rejects_numbers_and_strings() -> None:
    assert _explicit_true(True)
    assert _explicit_true(pd.Series([True], dtype="boolean").iloc[0])
    assert _explicit_true(np.bool_(True))

    for malformed_value in [False, np.bool_(False), 1, "true", "yes", "1"]:
        assert not _explicit_true(malformed_value)


def test_build_chain_evidence_review_requires_explicit_as_of_safe_flag() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "product_exposure_quality": "strong",
            }
        ]
    )
    evidence_without_flag = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "evidence_date": "2025-05-22",
                "evidence_type": "technical_barrier",
                "matched_keyword": "CPO",
                "evidence_snippet": "持续扩产备料并积极研发布局CPO",
            },
        ]
    )

    review_without_flag = build_chain_evidence_review(
        mapping=mapping, evidence=evidence_without_flag, taxonomy=taxonomy
    )

    assert review_without_flag.empty
    assert review_without_flag.columns.tolist() == CHAIN_EVIDENCE_COLUMNS

    evidence_with_flag = evidence_without_flag.assign(as_of_safe=True)

    review_with_flag = build_chain_evidence_review(
        mapping=mapping, evidence=evidence_with_flag, taxonomy=taxonomy
    )

    assert len(review_with_flag) == 1


def test_build_chain_evidence_review_filters_raw_evidence_scoped_to_other_chain() -> None:
    taxonomy = load_taxonomy(Path("data/manual/tech_chain_taxonomy_v1.json"))
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "product_exposure_quality": "strong",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "chain_id": "ai_compute_chips",
                "evidence_date": "2025-05-22",
                "evidence_type": "technical_barrier",
                "matched_keyword": "CPO",
                "evidence_snippet": "CPO 1.6T 大客户导入",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300308",
                "candidate_trade_date": "2025-06-20",
                "chain_id": " ",
                "evidence_date": "2025-05-22",
                "evidence_type": "technical_barrier",
                "matched_keyword": "CPO",
                "evidence_snippet": "CPO 1.6T 大客户导入",
                "as_of_safe": True,
            },
        ]
    )

    review = build_chain_evidence_review(
        mapping=mapping, evidence=evidence, taxonomy=taxonomy
    )

    assert not review.empty
    assert len(review) == 3
    assert set(review["matched_evidence_term"]) == {"CPO", "1.6T", "大客户导入"}


def test_build_chain_quality_review_routes_chain_candidates_without_generic_bottleneck_terms() -> None:
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "primary_chain_name": "AI光模块/光通信",
                "product_exposure_quality": "strong",
            },
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "primary_chain_name": "AI光模块/光通信",
                "product_exposure_quality": "missing",
            },
        ]
    )
    evidence_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "chain_id": "ai_optical_interconnect",
                "bottleneck_dimension": "architecture_route",
                "evidence_quality": "strong",
            }
        ]
    )

    review = build_chain_quality_review(mapping=mapping, chain_evidence=evidence_review)
    rows = review.set_index("asset_id")

    assert rows.loc["CN:SZ:300308", "chain_decision"] == "needs_more_evidence"
    assert (
        rows.loc["CN:SZ:300308", "decision_reason"]
        == "chain bottleneck is mapped but support evidence is incomplete"
    )
    assert rows.loc["CN:SZ:300394", "chain_decision"] == "needs_product_family_mapping"


def test_build_chain_quality_review_filters_evidence_scoped_to_other_chain() -> None:
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "primary_chain_name": "AI光模块/光通信",
                "product_exposure_quality": "strong",
            },
        ]
    )
    evidence_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "trade_date": "2025-06-20",
                "chain_id": "ai_compute_chips",
                "bottleneck_dimension": "architecture_route",
                "evidence_quality": "strong",
            }
        ]
    )

    review = build_chain_quality_review(mapping=mapping, chain_evidence=evidence_review)

    assert review.loc[0, "bottleneck_dimension_count"] == 0
    assert review.loc[0, "strong_bottleneck_dimension_count"] == 0
    assert review.loc[0, "chain_decision"] == "needs_more_evidence"
    assert (
        review.loc[0, "decision_reason"]
        == "product exposure is mapped but chain-specific bottleneck evidence is incomplete"
    )


def test_build_chain_quality_review_normalizes_evidence_quality_case_and_blanks() -> None:
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "primary_chain_name": "AI光模块/光通信",
                "product_exposure_quality": "strong",
            },
        ]
    )
    evidence_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "trade_date": "2025-06-20",
                "chain_id": "ai_optical_interconnect",
                "bottleneck_dimension": "architecture_route",
                "evidence_quality": " Strong ",
            },
            {
                "asset_id": "CN:SZ:300308",
                "trade_date": "2025-06-20",
                "chain_id": "ai_optical_interconnect",
                "bottleneck_dimension": "customer_delivery",
                "evidence_quality": "STRONG",
            },
            {
                "asset_id": "CN:SZ:300308",
                "trade_date": "2025-06-20",
                "chain_id": "ai_optical_interconnect",
                "bottleneck_dimension": "architecture_route",
            },
            {
                "asset_id": "CN:SZ:300308",
                "trade_date": "2025-06-20",
                "chain_id": "ai_optical_interconnect",
                "bottleneck_dimension": "customer_delivery",
                "evidence_quality": " ",
            },
        ]
    )

    review = build_chain_quality_review(mapping=mapping, chain_evidence=evidence_review)

    assert review.loc[0, "bottleneck_dimension_count"] == 2
    assert review.loc[0, "strong_bottleneck_dimension_count"] == 2


@pytest.mark.parametrize("product_quality", ["", "MISSING", "Missing", None])
def test_build_chain_quality_review_routes_incomplete_product_quality_to_mapping(
    product_quality: object,
) -> None:
    mapping_item = {
        "asset_id": "CN:SZ:300308",
        "stock_name": "中际旭创",
        "trade_date": "2025-06-20",
        "primary_chain_id": "ai_optical_interconnect",
        "primary_chain_name": "AI光模块/光通信",
    }
    if product_quality is not None:
        mapping_item["product_exposure_quality"] = product_quality
    mapping = pd.DataFrame([mapping_item])
    evidence_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "trade_date": "2025-06-20",
                "chain_id": "ai_optical_interconnect",
                "bottleneck_dimension": "architecture_route",
                "evidence_quality": "strong",
            }
        ]
    )

    review = build_chain_quality_review(mapping=mapping, chain_evidence=evidence_review)

    assert review.loc[0, "chain_decision"] == "needs_product_family_mapping"


def test_build_chain_quality_review_counts_unique_strong_bottleneck_dimensions() -> None:
    mapping = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "trade_date": "2025-06-20",
                "primary_chain_id": "ai_optical_interconnect",
                "primary_chain_name": "AI光模块/光通信",
                "product_exposure_quality": "strong",
            },
        ]
    )
    evidence_review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "trade_date": "2025-06-20",
                "chain_id": "ai_optical_interconnect",
                "bottleneck_dimension": "architecture_route",
                "evidence_quality": "strong",
                "matched_evidence_term": "CPO",
            },
            {
                "asset_id": "CN:SZ:300308",
                "trade_date": "2025-06-20",
                "chain_id": "ai_optical_interconnect",
                "bottleneck_dimension": "architecture_route",
                "evidence_quality": "strong",
                "matched_evidence_term": "LPO",
            },
            {
                "asset_id": "CN:SZ:300308",
                "trade_date": "2025-06-20",
                "chain_id": "ai_optical_interconnect",
                "bottleneck_dimension": "customer_delivery",
                "evidence_quality": "medium",
                "matched_evidence_term": "交付",
            },
        ]
    )

    review = build_chain_quality_review(mapping=mapping, chain_evidence=evidence_review)

    assert review.columns.tolist() == CHAIN_QUALITY_COLUMNS
    assert review.loc[0, "bottleneck_dimension_count"] == 2
    assert review.loc[0, "strong_bottleneck_dimension_count"] == 1
    assert (
        review.loc[0, "matched_bottleneck_dimensions"]
        == "architecture_route|customer_delivery"
    )


def _minimal_chain() -> dict[str, object]:
    return {
        "chain_id": "hbm_high_end_memory",
        "display_name": "HBM High End Memory",
        "chain_context_terms": ["HBM"],
        "product_exposure_terms": ["HBM3E"],
        "bottleneck_dimensions": {"memory_generation": ["HBM3E"]},
        "technical_execution_terms": ["TSV"],
        "commercial_validation_terms": ["qualification"],
        "invalidation_terms": ["commodity DRAM"],
        "global_reference_entities": ["SK hynix"],
    }
