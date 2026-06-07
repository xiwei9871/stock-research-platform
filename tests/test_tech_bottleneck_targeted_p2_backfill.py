from __future__ import annotations

from datetime import date

import pandas as pd

from stock_research.tech_bottleneck_targeted_p2_backfill import (
    build_bridge_suggestions,
    build_targeted_gap_audit,
    normalize_p2_mapping_queue,
)


def test_normalize_p2_mapping_queue_keeps_only_mapping_review_rows() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300567",
                "stock_name": "精测电子",
                "trade_date": "2025-02-10",
                "candidate_trade_date": "2025-02-11",
                "p3_decision": "needs_product_family_mapping",
                "review_priority": "",
                "next_evidence_need": "",
            },
            {
                "asset_id": "CN:SZ:002859",
                "stock_name": "洁美科技",
                "trade_date": "2025-01-20",
                "candidate_trade_date": None,
                "p3_decision": "",
                "review_priority": "P2_mapping_review",
                "next_evidence_need": "",
            },
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "trade_date": "2025-03-05",
                "candidate_trade_date": "",
                "p3_decision": "",
                "review_priority": "",
                "next_evidence_need": "needs_product_family_mapping",
            },
            {
                "asset_id": "CN:SZ:300567",
                "stock_name": "精测电子",
                "trade_date": "2025-02-12",
                "p3_decision": "auto_approve",
                "review_priority": "",
                "next_evidence_need": "",
            },
            {
                "asset_id": "CN:SH:600000",
                "stock_name": "非目标",
                "trade_date": "2025-01-20",
                "p3_decision": "needs_product_family_mapping",
                "review_priority": "",
                "next_evidence_need": "",
            },
        ]
    )

    normalized = normalize_p2_mapping_queue(queue)

    assert normalized["asset_id"].tolist() == [
        "CN:SZ:002859",
        "CN:SZ:300394",
        "CN:SZ:300567",
    ]
    assert normalized["candidate_trade_date"].tolist() == [
        "2025-01-20",
        "2025-03-05",
        "2025-02-11",
    ]
    assert normalized["bridge_family"].tolist() == [
        "semiconductor_materials_components",
        "optical_communication_components",
        "semiconductor_testing_metrology",
    ]


def test_build_targeted_gap_audit_counts_existing_family_evidence() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300567",
                "stock_name": "精测电子",
                "trade_date": "2025-02-10",
                "p3_decision": "needs_product_family_mapping",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300567",
                "candidate_trade_date": "2025-02-10",
                "evidence_type": "product_revenue",
                "matched_keyword": "AOI",
                "evidence_snippet": "AOI测试设备收入快速增长",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300567",
                "candidate_trade_date": "2025-02-10",
                "evidence_type": "technical_barrier",
                "matched_keyword": "专利",
                "evidence_snippet": "机器视觉检测工艺形成技术壁垒",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300567",
                "candidate_trade_date": "2025-02-10",
                "evidence_type": "capacity",
                "matched_keyword": "产能",
                "evidence_snippet": "新基地投产后量产能力提升",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300567",
                "candidate_trade_date": "2025-02-10",
                "evidence_type": "customer_certification",
                "matched_keyword": "客户导入",
                "evidence_snippet": "产品完成客户认证并导入量产线",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300567",
                "candidate_trade_date": "2025-02-10",
                "evidence_type": "product_revenue",
                "matched_keyword": "面板检测",
                "evidence_snippet": "非PIT安全旧证据",
                "as_of_safe": False,
            },
            {
                "asset_id": "CN:SZ:300567",
                "candidate_trade_date": "2025-02-11",
                "evidence_type": "product_revenue",
                "matched_keyword": "量测设备",
                "evidence_snippet": "错误日期证据",
                "as_of_safe": True,
            },
        ]
    )

    audit = build_targeted_gap_audit(queue, evidence)

    row = audit.iloc[0]
    assert row["candidate_bridge_family"] == "semiconductor_testing_metrology"
    assert row["product_evidence_count"] == 2
    assert row["bottleneck_evidence_count"] == 3
    assert row["capacity_evidence_count"] == 2
    assert row["customer_evidence_count"] == 1
    assert row["technical_evidence_count"] == 1
    assert row["missing_bridge_side"] == "missing_product_family_on_semantic_evidence"


def test_build_bridge_suggestions_requires_product_and_semantic_terms() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "stock_name": "洁美科技",
                "trade_date": "2025-01-20",
                "review_priority": "P2_mapping_review",
            },
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "trade_date": "2025-03-05",
                "p3_decision": "needs_product_family_mapping",
            },
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "candidate_trade_date": "2025-01-20",
                "source_id": "jm-1",
                "evidence_snippet": "公司载带和MLCC离型膜用于电子元件材料，半导体封装客户认证推进国产替代",
                "matched_keyword": "载带",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:002859",
                "candidate_trade_date": "2025-01-20",
                "source_id": "jm-2",
                "source_title": "半导体材料产能扩张公告",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300394",
                "candidate_trade_date": "2025-03-05",
                "source_id": "tf-1",
                "product_name": "光模块",
                "evidence_snippet": "光模块业务收入保持增长",
                "as_of_safe": True,
            },
        ]
    )

    suggestions = build_bridge_suggestions(queue, evidence)

    bridgeable = suggestions[suggestions["asset_id"] == "CN:SZ:002859"].iloc[0]
    assert bridgeable["bridge_status"] == "bridgeable"
    assert bridgeable["matched_product_terms"] == "载带|离型膜|MLCC离型膜|半导体材料|电子元件材料"
    assert bridgeable["matched_semantic_terms"] == "国产替代|客户认证|产能|半导体封装"
    assert bridgeable["supporting_source_ids"] == "jm-1|jm-2"

    product_only = suggestions[suggestions["asset_id"] == "CN:SZ:300394"].iloc[0]
    assert product_only["matched_product_terms"] == "光模块"
    assert product_only["matched_semantic_terms"] == ""
    assert product_only["bridge_status"] == "needs_more_source_evidence"


def test_build_bridge_suggestions_limits_supporting_sources_to_matching_evidence() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "stock_name": "洁美科技",
                "trade_date": "2025-01-20",
                "review_priority": "P2_mapping_review",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "candidate_trade_date": "2025-01-20",
                "source_id": "supporting",
                "evidence_snippet": "载带产品推进半导体封装客户认证",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:002859",
                "candidate_trade_date": "2025-01-20",
                "source_id": "irrelevant",
                "evidence_snippet": "办公楼租赁合同续签",
                "as_of_safe": True,
            },
        ]
    )

    suggestions = build_bridge_suggestions(queue, evidence)

    assert suggestions.iloc[0]["supporting_source_ids"] == "supporting"


def test_mixed_date_types_match_candidate_evidence() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "stock_name": "洁美科技",
                "candidate_trade_date": date(2025, 1, 20),
                "review_priority": "P2_mapping_review",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "candidate_trade_date": pd.Timestamp("2025-01-20"),
                "evidence_type": "product_revenue",
                "evidence_snippet": "载带收入增长",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:002859",
                "candidate_trade_date": "2025-01-20",
                "evidence_type": "technical_barrier",
                "evidence_snippet": "客户认证形成技术壁垒",
                "as_of_safe": True,
            },
        ]
    )

    audit = build_targeted_gap_audit(queue, evidence)

    assert audit.iloc[0]["candidate_trade_date"] == "2025-01-20"
    assert audit.iloc[0]["product_evidence_count"] == 1
    assert audit.iloc[0]["technical_evidence_count"] == 1


def test_product_terms_in_text_count_product_evidence_without_product_type() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "trade_date": "2025-03-05",
                "p3_decision": "needs_product_family_mapping",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "candidate_trade_date": "2025-03-05",
                "evidence_type": "news",
                "product_name": "光模块",
                "snippet": "高速光引擎客户导入推进",
                "as_of_safe": True,
            }
        ]
    )

    audit = build_targeted_gap_audit(queue, evidence)

    assert audit.iloc[0]["product_evidence_count"] == 1


def test_product_revenue_type_without_targeted_product_term_does_not_count_product_evidence() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "trade_date": "2025-03-05",
                "p3_decision": "needs_product_family_mapping",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "candidate_trade_date": "2025-03-05",
                "evidence_type": "product_revenue",
                "evidence_snippet": "办公租赁收入保持稳定",
                "matched_keyword": "租赁",
                "as_of_safe": True,
            }
        ]
    )

    audit = build_targeted_gap_audit(queue, evidence)

    assert audit.iloc[0]["product_evidence_count"] == 0


def test_bridge_suggestions_match_common_repo_text_fields() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300567",
                "stock_name": "精测电子",
                "trade_date": "2025-02-10",
                "p3_decision": "needs_product_family_mapping",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300567",
                "candidate_trade_date": "2025-02-10",
                "source_id": "common-fields",
                "product": "半导体检测",
                "business_item": "客户导入",
                "item_name": "量测设备",
                "snippet": "产能进入量产阶段",
                "as_of_safe": True,
            }
        ]
    )

    suggestions = build_bridge_suggestions(queue, evidence)

    row = suggestions.iloc[0]
    assert row["matched_product_terms"] == "半导体检测|量测设备"
    assert row["matched_semantic_terms"] == "客户导入|产能|量产|半导体"
    assert row["supporting_source_ids"] == "common-fields"
    assert row["bridge_status"] == "bridgeable"


def test_bridge_suggestions_match_lowercase_acronym_evidence_with_canonical_output() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "trade_date": "2025-03-05",
                "p3_decision": "needs_product_family_mapping",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "candidate_trade_date": "2025-03-05",
                "source_id": "tf-lowercase",
                "evidence_snippet": "cpo光通信器件客户导入推进",
                "as_of_safe": True,
            }
        ]
    )

    suggestions = build_bridge_suggestions(queue, evidence)

    row = suggestions.iloc[0]
    assert row["matched_product_terms"] == "CPO|光通信器件"
    assert row["matched_semantic_terms"] == "客户导入"
    assert row["supporting_source_ids"] == "tf-lowercase"


def test_string_as_of_safe_values_filter_like_booleans() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002371",
                "stock_name": "北方华创",
                "trade_date": "2025-01-20",
                "review_priority": "P2_mapping_review",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002371",
                "candidate_trade_date": "2025-01-20",
                "evidence_type": "product_revenue",
                "evidence_snippet": "刻蚀设备收入增长",
                "as_of_safe": "true",
            },
            {
                "asset_id": "CN:SZ:002371",
                "candidate_trade_date": "2025-01-20",
                "evidence_type": "technical_barrier",
                "evidence_snippet": "先进制程客户导入",
                "as_of_safe": "1",
            },
            {
                "asset_id": "CN:SZ:002371",
                "candidate_trade_date": "2025-01-20",
                "evidence_type": "product_revenue",
                "evidence_snippet": "清洗设备旧证据",
                "as_of_safe": "False",
            },
            {
                "asset_id": "CN:SZ:002371",
                "candidate_trade_date": "2025-01-20",
                "evidence_type": "product_revenue",
                "evidence_snippet": "PVD旧证据",
                "as_of_safe": "no",
            },
        ]
    )

    audit = build_targeted_gap_audit(queue, evidence)

    assert audit.iloc[0]["product_evidence_count"] == 1
    assert audit.iloc[0]["bottleneck_evidence_count"] == 1
