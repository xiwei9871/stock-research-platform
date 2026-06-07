from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stock_research.tech_bottleneck_evidence_backfill import EVIDENCE_COLUMNS
from stock_research.cli import build_parser, main_for_args
import stock_research.tech_bottleneck_targeted_p2_backfill as targeted_p2_module
from stock_research.tech_bottleneck_targeted_p2_backfill import (
    build_bridge_suggestions,
    build_targeted_bridge_evidence,
    build_targeted_gap_audit,
    combine_evidence,
    normalize_p2_mapping_queue,
    render_promotion_delta,
    run_targeted_p2_backfill_from_files,
    write_targeted_backfill_artifacts,
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


def test_build_targeted_bridge_evidence_marks_derived_proxy_rows() -> None:
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
                "stock_name": "天孚通信",
                "candidate_trade_date": "2025-03-05",
                "as_of_date": "2025-03-05",
                "evidence_date": "2025-03-04",
                "source_type": "news",
                "source_id": "tf-source-1",
                "source_title": "天孚通信光通信器件进展",
                "source_url": "https://example.test/tf",
                "evidence_type": "customer_certification",
                "matched_keyword": "客户导入",
                "evidence_snippet": "公司光通信器件和高速光引擎客户导入推进，受益AI算力需求。",
                "source_confidence": "high",
                "is_proxy": False,
                "as_of_safe": True,
            }
        ]
    )
    suggestions = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "candidate_trade_date": "2025-03-05",
                "bridge_family": "optical_communication_components",
                "matched_product_terms": "高速光引擎|光通信器件",
                "matched_semantic_terms": "AI算力|客户导入",
                "supporting_source_ids": "tf-source-1|tf-source-2",
                "bridge_status": "bridgeable",
            }
        ]
    )

    bridge_evidence = build_targeted_bridge_evidence(
        queue=queue,
        evidence=evidence,
        suggestions=suggestions,
        run_id="targeted-run",
    )

    assert len(bridge_evidence) == 1
    row = bridge_evidence.iloc[0]
    assert row["run_id"] == "targeted-run"
    assert row["asset_id"] == "CN:SZ:300394"
    assert row["stock_name"] == "天孚通信"
    assert row["candidate_trade_date"] == "2025-03-05"
    assert row["as_of_date"] == "2025-03-05"
    assert row["evidence_date"] == "2025-03-04"
    assert row["source_type"] == "derived_product_family_bridge"
    assert row["source_id"] == "CN:SZ:300394:2025-03-05:optical_communication_components:bridge"
    assert row["source_title"] == "天孚通信光通信器件进展"
    assert row["source_url"] == "https://example.test/tf"
    assert row["evidence_type"] == "customer_certification"
    assert row["evidence_snippet"] == "公司光通信器件和高速光引擎客户导入推进，受益AI算力需求。"
    assert row["matched_keyword"].startswith("optical_communication_components:")
    assert row["source_confidence"] == "medium"
    assert row["is_proxy"] is True
    assert row["as_of_safe"] is True
    metadata = json.loads(row["metadata_json"])
    assert metadata["bridge_family"] == "optical_communication_components"
    assert metadata["bridge_reason"] == "product_family_semantic_bridge"
    assert metadata["supporting_source_ids"] == ["tf-source-1", "tf-source-2"]
    assert metadata["source_candidate_trade_date"] == "2025-03-05"


def test_build_targeted_bridge_evidence_ignores_non_bridgeable_suggestions() -> None:
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
                "source_id": "tf-source-1",
                "evidence_snippet": "光通信器件客户导入推进",
                "as_of_safe": True,
            }
        ]
    )
    suggestions = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "candidate_trade_date": "2025-03-05",
                "bridge_family": "optical_communication_components",
                "supporting_source_ids": "tf-source-1",
                "bridge_status": "needs_more_source_evidence",
            }
        ]
    )

    bridge_evidence = build_targeted_bridge_evidence(
        queue=queue,
        evidence=evidence,
        suggestions=suggestions,
        run_id="targeted-run",
    )

    assert bridge_evidence.empty


def test_build_targeted_bridge_evidence_dedupes_duplicate_bridgeable_suggestions() -> None:
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
                "source_id": "tf-source-1",
                "evidence_snippet": "公司光通信器件客户导入推进。",
                "as_of_safe": True,
            }
        ]
    )
    suggestions = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "candidate_trade_date": "2025-03-05",
                "bridge_family": "optical_communication_components",
                "supporting_source_ids": "tf-source-1",
                "bridge_status": "bridgeable",
            },
            {
                "asset_id": "CN:SZ:300394",
                "stock_name": "天孚通信",
                "candidate_trade_date": "2025-03-05",
                "bridge_family": "optical_communication_components",
                "supporting_source_ids": "tf-source-1",
                "bridge_status": "bridgeable",
            },
        ]
    )

    bridge_evidence = build_targeted_bridge_evidence(
        queue=queue,
        evidence=evidence,
        suggestions=suggestions,
        run_id="targeted-run",
    )

    assert len(bridge_evidence) == 1
    assert bridge_evidence["source_id"].tolist() == [
        "CN:SZ:300394:2025-03-05:optical_communication_components:bridge"
    ]


def test_build_targeted_bridge_evidence_rejects_risk_disclosure_sources() -> None:
    queue = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300567",
                "stock_name": "精测电子",
                "trade_date": "2025-12-31",
                "p3_decision": "needs_product_family_mapping",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300567",
                "candidate_trade_date": "2025-12-31",
                "source_id": "risk-row",
                "evidence_type": "invalidation",
                "evidence_snippet": "面板检测行业竞争加剧、半导体业务验证进展不及预期风险。",
                "as_of_safe": True,
            },
            {
                "asset_id": "CN:SZ:300567",
                "candidate_trade_date": "2025-12-31",
                "source_id": "product-only",
                "evidence_type": "product_revenue_exposure",
                "evidence_snippet": "公司面板检测业务收入增长。",
                "as_of_safe": True,
            },
        ]
    )
    suggestions = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300567",
                "stock_name": "精测电子",
                "candidate_trade_date": "2025-12-31",
                "bridge_family": "semiconductor_testing_metrology",
                "matched_product_terms": "面板检测",
                "matched_semantic_terms": "半导体",
                "supporting_source_ids": "risk-row|product-only",
                "bridge_status": "bridgeable",
            }
        ]
    )

    bridge_evidence = build_targeted_bridge_evidence(
        queue=queue,
        evidence=evidence,
        suggestions=suggestions,
        run_id="targeted-run",
    )

    assert bridge_evidence.empty


def test_empty_targeted_bridge_evidence_has_normalized_evidence_schema() -> None:
    bridge_evidence = build_targeted_bridge_evidence(
        queue=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SZ:300394",
                    "stock_name": "天孚通信",
                    "trade_date": "2025-03-05",
                    "p3_decision": "needs_product_family_mapping",
                }
            ]
        ),
        evidence=pd.DataFrame(),
        suggestions=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SZ:300394",
                    "stock_name": "天孚通信",
                    "candidate_trade_date": "2025-03-05",
                    "bridge_family": "optical_communication_components",
                    "bridge_status": "bridgeable",
                }
            ]
        ),
        run_id="targeted-run",
    )

    assert bridge_evidence.empty
    assert list(bridge_evidence.columns) == EVIDENCE_COLUMNS


def test_combine_evidence_preserves_original_then_bridge_row_order_and_count() -> None:
    original_evidence = pd.DataFrame(
        [
            {"source_id": "original-1", "asset_id": "CN:SZ:300394"},
            {"source_id": "original-2", "asset_id": "CN:SZ:002859"},
        ]
    )
    bridge_evidence = pd.DataFrame(
        [
            {"source_id": "bridge-1", "source_type": "derived_product_family_bridge"},
        ]
    )

    combined = combine_evidence(original_evidence=original_evidence, bridge_evidence=bridge_evidence)

    assert len(combined) == 3
    assert combined["source_id"].tolist() == ["original-1", "original-2", "bridge-1"]


def test_render_promotion_delta_lists_promoted_and_blocked_assets() -> None:
    before_review = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "p3_decision": "needs_product_family_mapping",
            },
            {
                "asset_id": "B",
                "stock_name": "Beta",
                "p3_decision": "needs_product_family_mapping",
            },
        ]
    )
    after_review = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "p3_decision": "auto_approve",
            },
            {
                "asset_id": "B",
                "stock_name": "Beta",
                "p3_decision": "needs_product_family_mapping",
            },
        ]
    )
    bridge_evidence = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "source_type": "derived_product_family_bridge",
                "evidence_type": "customer_certification",
                "metadata_json": json.dumps({"bridge_family": "optical_communication_components"}),
            }
        ]
    )

    report = render_promotion_delta(
        before_review=before_review,
        after_review=after_review,
        bridge_evidence=bridge_evidence,
    )

    assert "P2 asset count before: 2" in report
    assert "P2 asset count after: 1" in report
    assert "P1 asset count after: 1" in report
    assert "Alpha (A)" in report
    assert "Beta (B): needs_product_family_mapping" in report
    assert "optical_communication_components" in report
    assert report.endswith("\n")


def test_render_promotion_delta_handles_empty_missing_column_inputs() -> None:
    report = render_promotion_delta(
        before_review=pd.DataFrame(),
        after_review=pd.DataFrame([{"asset_id": "A"}]),
        bridge_evidence=pd.DataFrame([{"metadata_json": None}]),
    )

    assert "P2 asset count before: 0" in report
    assert "P2 asset count after: 0" in report
    assert "P1 asset count before: 0" in report
    assert "P1 asset count after: 0" in report
    assert report.endswith("\n")


def test_render_promotion_delta_dedupes_conflicting_after_decisions_by_asset() -> None:
    before_review = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "p3_decision": "needs_product_family_mapping",
            }
        ]
    )
    after_review = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "p3_decision": "auto_approve",
            },
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "p3_decision": "needs_product_family_mapping",
            },
        ]
    )

    report = render_promotion_delta(
        before_review=before_review,
        after_review=after_review,
        bridge_evidence=pd.DataFrame(),
    )

    assert "P2 asset count after: 0" in report
    assert "P1 asset count after: 1" in report
    assert "- Alpha (A)" in report
    assert "Alpha (A): needs_product_family_mapping" not in report


def test_render_promotion_delta_ignores_malformed_metadata_json() -> None:
    report = render_promotion_delta(
        before_review=pd.DataFrame(),
        after_review=pd.DataFrame(),
        bridge_evidence=pd.DataFrame(
            [
                {
                    "metadata_json": "{malformed",
                    "source_type": "derived_product_family_bridge",
                    "evidence_type": "customer_certification",
                }
            ]
        ),
    )

    assert "## Added Bridge Evidence Families\n- None" in report


def test_write_targeted_backfill_artifacts_writes_required_files(tmp_path: Path) -> None:
    audit = pd.DataFrame([{"asset_id": "CN:SZ:300394", "missing_bridge_side": "missing"}])
    suggestions = pd.DataFrame([{"asset_id": "CN:SZ:300394", "bridge_status": "bridgeable"}])
    bridge_evidence = pd.DataFrame([{"asset_id": "CN:SZ:300394", "source_id": "bridge"}])
    combined_evidence = combine_evidence(
        original_evidence=pd.DataFrame([{"asset_id": "CN:SZ:300394", "source_id": "original"}]),
        bridge_evidence=bridge_evidence,
    )
    review_after = pd.DataFrame([{"asset_id": "CN:SZ:300394", "review_priority": "P3"}])
    manifest = {"run_id": "targeted-run", "bridge_rows": 1}

    paths = write_targeted_backfill_artifacts(
        output_dir=tmp_path,
        audit=audit,
        suggestions=suggestions,
        bridge_evidence=bridge_evidence,
        combined_evidence=combined_evidence,
        review_after=review_after,
        promotion_delta_md="# Promotion Delta\n",
        manifest=manifest,
    )

    expected_keys = {
        "targeted_evidence_gap_audit",
        "product_family_bridge_suggestions",
        "targeted_backfill_evidence",
        "combined_evidence_after_targeted_backfill",
        "quality_review_after_targeted_backfill",
        "promotion_delta",
        "manifest",
    }
    assert set(paths) == expected_keys
    for path in paths.values():
        assert path.exists()
    assert paths["promotion_delta"].read_text(encoding="utf-8") == "# Promotion Delta\n"
    assert json.loads(paths["manifest"].read_text(encoding="utf-8")) == manifest


def test_run_targeted_p2_backfill_from_files_writes_artifacts_and_manifest(tmp_path: Path) -> None:
    human_review_assets_csv = tmp_path / "human_review_assets.csv"
    quality_review_csv = tmp_path / "quality_review.csv"
    evidence_csv = tmp_path / "evidence.csv"
    output_dir = tmp_path / "out"

    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "stock_name": "洁美科技",
                "trade_date": "2025-01-20",
                "review_priority": "P2_mapping_review",
            }
        ]
    ).to_csv(human_review_assets_csv, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "stock_name": "洁美科技",
                "p3_decision": "needs_product_family_mapping",
                "next_evidence_need": "needs_product_family_mapping",
            },
            {
                "asset_id": "CN:SH:600000",
                "stock_name": "浦发银行",
                "p3_decision": "needs_product_family_mapping",
                "next_evidence_need": "needs_product_family_mapping",
            }
        ]
    ).to_csv(quality_review_csv, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002859",
                "candidate_trade_date": "2025-01-20",
                "source_id": "jm-1",
                "evidence_type": "customer_certification",
                "matched_keyword": "载带",
                "evidence_snippet": "载带和MLCC离型膜用于半导体封装客户认证并推进国产替代",
                "as_of_safe": True,
            }
        ]
    ).to_csv(evidence_csv, index=False)

    paths = run_targeted_p2_backfill_from_files(
        human_review_assets_csv=human_review_assets_csv,
        quality_review_csv=quality_review_csv,
        evidence_csv=evidence_csv,
        output_dir=output_dir,
        run_id="targeted-run",
    )

    for path in paths.values():
        assert path.exists()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["run_id"] == "targeted-run"
    assert manifest["p2_asset_count_before"] == 1
    assert manifest["targeted_p2_asset_count_before"] == 1
    assert manifest["quality_review_p2_asset_count_before"] == 2
    assert manifest["bridge_evidence_count"] == 1
    assert manifest["bridgeable_count"] == 1
    assert manifest["quality_review_after_is_temporary_before_copy"] is True
    assert manifest["inputs"] == {
        "human_review_assets_csv": str(human_review_assets_csv),
        "quality_review_csv": str(quality_review_csv),
        "evidence_csv": str(evidence_csv),
    }
    assert "quality_review_after_targeted_backfill.csv is a temporary before-review copy" in paths[
        "promotion_delta"
    ].read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("bad_input_name", "bad_frame", "expected_missing"),
    [
        (
            "human_review_assets_csv",
            pd.DataFrame(columns=["asset_id", "review_priority"]),
            "candidate_trade_date or trade_date",
        ),
        (
            "quality_review_csv",
            pd.DataFrame(columns=["asset_id"]),
            "p3_decision",
        ),
        (
            "evidence_csv",
            pd.DataFrame(columns=["asset_id", "source_id"]),
            "candidate_trade_date or trade_date",
        ),
    ],
)
def test_run_targeted_p2_backfill_from_files_rejects_missing_required_columns(
    tmp_path: Path,
    bad_input_name: str,
    bad_frame: pd.DataFrame,
    expected_missing: str,
) -> None:
    human_review_assets_csv = tmp_path / "human_review_assets.csv"
    quality_review_csv = tmp_path / "quality_review.csv"
    evidence_csv = tmp_path / "evidence.csv"
    output_dir = tmp_path / "out"

    valid_frames = {
        "human_review_assets_csv": pd.DataFrame(columns=["asset_id", "candidate_trade_date"]),
        "quality_review_csv": pd.DataFrame(columns=["asset_id", "p3_decision"]),
        "evidence_csv": pd.DataFrame(columns=["asset_id", "candidate_trade_date"]),
    }
    valid_frames[bad_input_name] = bad_frame
    valid_frames["human_review_assets_csv"].to_csv(human_review_assets_csv, index=False)
    valid_frames["quality_review_csv"].to_csv(quality_review_csv, index=False)
    valid_frames["evidence_csv"].to_csv(evidence_csv, index=False)

    with pytest.raises(ValueError, match=bad_input_name) as exc_info:
        run_targeted_p2_backfill_from_files(
            human_review_assets_csv=human_review_assets_csv,
            quality_review_csv=quality_review_csv,
            evidence_csv=evidence_csv,
            output_dir=output_dir,
        )

    assert expected_missing in str(exc_info.value)


def test_run_targeted_p2_backfill_from_files_accepts_header_only_required_inputs(tmp_path: Path) -> None:
    human_review_assets_csv = tmp_path / "human_review_assets.csv"
    quality_review_csv = tmp_path / "quality_review.csv"
    evidence_csv = tmp_path / "evidence.csv"
    output_dir = tmp_path / "out"

    pd.DataFrame(columns=["asset_id", "trade_date"]).to_csv(human_review_assets_csv, index=False)
    pd.DataFrame(columns=["asset_id", "p3_decision"]).to_csv(quality_review_csv, index=False)
    pd.DataFrame(columns=["asset_id", "candidate_trade_date"]).to_csv(evidence_csv, index=False)

    paths = run_targeted_p2_backfill_from_files(
        human_review_assets_csv=human_review_assets_csv,
        quality_review_csv=quality_review_csv,
        evidence_csv=evidence_csv,
        output_dir=output_dir,
        run_id="header-only-run",
    )

    for path in paths.values():
        assert path.exists()
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["run_id"] == "header-only-run"
    assert manifest["p2_asset_count_before"] == 0
    assert manifest["targeted_p2_asset_count_before"] == 0
    assert manifest["quality_review_p2_asset_count_before"] == 0
    assert manifest["bridge_evidence_count"] == 0
    assert manifest["bridgeable_count"] == 0
    assert manifest["quality_review_after_is_temporary_before_copy"] is True


def test_cli_parser_accepts_targeted_p2_backfill_command() -> None:
    args = build_parser().parse_args(
        [
            "tech-bottleneck-targeted-p2-backfill",
            "--human-review-assets-csv",
            "human_review_assets.csv",
            "--quality-review-csv",
            "quality_review.csv",
            "--evidence-csv",
            "evidence.csv",
            "--output-dir",
            "out",
            "--run-id",
            "custom-run",
        ]
    )

    assert args.command == "tech-bottleneck-targeted-p2-backfill"
    assert args.human_review_assets_csv == "human_review_assets.csv"
    assert args.quality_review_csv == "quality_review.csv"
    assert args.evidence_csv == "evidence.csv"
    assert args.output_dir == "out"
    assert args.run_id == "custom-run"


def test_cli_dispatches_targeted_p2_backfill(monkeypatch, capsys) -> None:
    calls = {}

    def fake_runner(**kwargs):
        calls["runner_kwargs"] = kwargs
        return {"manifest": Path("out/manifest.json")}

    monkeypatch.setattr(targeted_p2_module, "run_targeted_p2_backfill_from_files", fake_runner)

    main_for_args(
        [
            "tech-bottleneck-targeted-p2-backfill",
            "--human-review-assets-csv",
            "human_review_assets.csv",
            "--quality-review-csv",
            "quality_review.csv",
            "--evidence-csv",
            "evidence.csv",
            "--output-dir",
            "out",
            "--run-id",
            "custom-run",
        ]
    )

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"manifest": "out/manifest.json"}
    assert calls["runner_kwargs"] == {
        "human_review_assets_csv": Path("human_review_assets.csv"),
        "quality_review_csv": Path("quality_review.csv"),
        "evidence_csv": Path("evidence.csv"),
        "output_dir": Path("out"),
        "run_id": "custom-run",
    }
