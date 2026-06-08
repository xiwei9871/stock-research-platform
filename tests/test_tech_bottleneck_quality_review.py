from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_quality_review import (
    build_asset_level_queues,
    build_operational_queues,
    build_quality_review,
    classify_product_family,
    run_quality_review_from_files,
    write_quality_review_artifacts,
)


def test_classify_product_family_links_chrome_product_and_bottleneck_terms() -> None:
    family = classify_product_family("铬的氧化物 铬盐联产产品", "高纯金属铬 高端氧化铬绿 打破境外企业垄断")

    assert family == "chrome_chemicals"


def test_classify_product_family_links_medical_diagnostics_terms() -> None:
    family = classify_product_family("传染病检测产品 体外诊断试剂 POCT", "国产替代 自主可控 上游生物原料 配套检测仪器")

    assert family == "medical_diagnostics"


def test_classify_product_family_links_medical_imaging_terms() -> None:
    family = classify_product_family("超声医学影像设备 探头", "国产超声关键卡脖子技术突破 注册产品实现量产")

    assert family == "medical_imaging"


def test_classify_product_family_links_magnetic_materials_terms() -> None:
    family = classify_product_family("非晶合金薄带及其制品 纳米晶产品 磁性粉末", "加速器高频系统解决卡脖子问题 非晶方案客户认证")

    assert family == "advanced_magnetic_materials"


def test_classify_product_family_links_hydraulics_terms() -> None:
    family = classify_product_family("液压油缸 液压泵阀 液压系统", "液压行业制约装备制造业做强的瓶颈 插装阀年产能")

    assert family == "hydraulics_motion_control"


def test_classify_product_family_links_semiconductor_equipment_terms() -> None:
    family = classify_product_family("半导体设备 薄膜沉积设备 刻蚀设备", "国产替代 核心技术 客户验证 先进制程")

    assert family == "semiconductor_equipment"


def test_classify_product_family_links_semiconductor_testing_metrology_terms() -> None:
    family = classify_product_family("半导体测试设备 晶圆检测设备 量测设备", "国产化 核心技术 客户认证 先进封装")

    assert family == "semiconductor_testing_metrology"


def test_classify_product_family_links_semiconductor_materials_components_terms() -> None:
    family = classify_product_family("半导体材料 靶材 载带 电子级硅微粉", "国产替代 关键材料 客户认证 批量供货")

    assert family == "semiconductor_materials_components"


def test_classify_product_family_links_oled_display_materials_terms() -> None:
    family = classify_product_family("OLED终端材料 OLED有机材料 掩膜版", "国产OLED材料核心技术 客户验证 批量供货")

    assert family == "oled_display_materials"


def test_classify_product_family_links_optical_communication_components_terms() -> None:
    family = classify_product_family("光通信器件 光模块 无源器件 光引擎", "国产替代 高速率 数据中心客户认证")

    assert family == "optical_communication_components"


def test_classify_product_family_links_core_leader_product_aliases() -> None:
    assert (
        classify_product_family(
            "云端产品线 智能计算芯片 MLU",
            "国产AI芯片自主可控 算力芯片核心技术",
        )
        == "ai_compute_chips"
    )
    assert (
        classify_product_family(
            "PCB制造 高阶HDI 高多层板",
            "AI服务器PCB国产替代 数据中心高速PCB批量供货",
        )
        == "ai_server_high_speed_pcb"
    )
    assert (
        classify_product_family(
            "光通信模块 光通信收发模块 4.25G以上",
            "800G光模块 1.6T高速光模块 数据中心客户认证",
        )
        == "optical_communication_components"
    )
    assert (
        classify_product_family(
            "电子工艺装备 半导体工艺装备",
            "半导体设备国产替代 平台型半导体设备核心技术",
        )
        == "semiconductor_equipment"
    )


def test_classify_product_family_links_taxonomy_chain_terms() -> None:
    assert (
        classify_product_family(
            "HBM3E TSV 堆叠 高带宽内存",
            "Nvidia认证 客户验证 后段产能 良率",
        )
        == "hbm_high_end_memory"
    )
    assert (
        classify_product_family(
            "MLCC 高容量 高可靠 小型化",
            "AI server PDN GPU周边 高瞬态电流 满产",
        )
        == "mlcc_high_end_passives"
    )


def test_classify_product_family_links_advanced_medical_devices_terms() -> None:
    family = classify_product_family("数字化X线探测器 骨科植入物 医疗器械", "国产替代 注册证 核心技术 客户认证")

    assert family == "advanced_medical_devices"


def test_build_quality_review_auto_approves_same_product_family_strong_evidence() -> None:
    review = build_quality_review(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:603239",
                    "stock_name": "浙江仙通",
                    "trade_date": "2025-05-16",
                    "product_snippet": "橡胶密封条收入占比80%，塑胶密封条收入占比19%",
                }
            ]
        ),
        product_rows=pd.DataFrame(),
        evidence_hits=pd.DataFrame(
            [
                _hit("CN:SH:603239", "2025-05-16", "bottleneck", "替代进口", "公司以高端密封条替代进口为市场切入点"),
                _hit("CN:SH:603239", "2025-05-16", "technical_barrier", "胶料配方", "胶料配方领域达到国内领先，拥有发明专利"),
                _hit("CN:SH:603239", "2025-05-16", "customer_certification", "合格供应商", "整车厂对合格供应商考核严格"),
                _hit("CN:SH:603239", "2025-05-16", "capacity", "产能", "有序扩展产能，持续引进设备"),
            ]
        ),
    )

    row = review.iloc[0]
    assert row["p3_decision"] == "auto_approve"
    assert row["product_family"] == "auto_sealing"
    assert row["product_linkage_quality"] == "strong"
    assert row["weak_evidence_count"] == 0


def test_build_quality_review_keeps_candidate_for_more_evidence_when_customer_and_capacity_are_weak() -> None:
    review = build_quality_review(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SZ:002028",
                    "stock_name": "思源电气",
                    "trade_date": "2025-01-24",
                    "product_snippet": "开关类及相关产品、线圈类及相关产品、无功补偿类及相关产品",
                }
            ]
        ),
        product_rows=pd.DataFrame(),
        evidence_hits=pd.DataFrame(
            [
                _hit("CN:SZ:002028", "2025-01-24", "bottleneck_or_domestic_substitution", "自主可控", "开展自主可控国产化设备研发，主要产品包括750kV断路器、GIS和无功补偿设备"),
                _hit("CN:SZ:002028", "2025-01-24", "technical_barrier", "核心技术", "参与国家标准制定，拥有多项行业领先核心技术"),
                _hit("CN:SZ:002028", "2025-01-24", "weak_customer_or_catalyst", "定点", "新取得客户定点尚无法在短期形成收入，商誉减值测试"),
                _hit("CN:SZ:002028", "2025-01-24", "weak_capacity", "产能", "产品收入表 OCR 类智 关产能设备 及相 品"),
            ]
        ),
    )

    row = review.iloc[0]
    assert row["p3_decision"] == "needs_more_evidence"
    assert row["product_family"] == "power_grid_equipment"
    assert row["customer_quality"] == "weak"
    assert row["capacity_quality"] == "weak"
    assert row["weak_evidence_count"] == 2


def test_build_quality_review_rejects_unlinked_generic_noise() -> None:
    review = build_quality_review(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:600000",
                    "stock_name": "噪声样本",
                    "trade_date": "2025-01-10",
                    "product_snippet": "其他收入占比0.1%",
                }
            ]
        ),
        product_rows=pd.DataFrame(),
        evidence_hits=pd.DataFrame(
            [
                _hit("CN:SH:600000", "2025-01-10", "technical_barrier", "配方", "利润分配方案及公司章程相关事项"),
                _hit("CN:SH:600000", "2025-01-10", "news_or_announcement_catalyst", "量产", "批量产生不良品的会计描述"),
            ]
        ),
    )

    row = review.iloc[0]
    assert row["p3_decision"] == "reject_or_noise"
    assert row["product_linkage_quality"] == "missing"
    assert row["technical_quality"] == "weak"
    assert row["catalyst_quality"] == "weak"


def test_build_quality_review_handles_candidate_with_no_evidence_hits() -> None:
    review = build_quality_review(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:600897",
                    "stock_name": "空证据样本",
                    "trade_date": "2025-10-24",
                }
            ]
        ),
        product_rows=pd.DataFrame(),
        evidence_hits=pd.DataFrame(),
    )

    row = review.iloc[0]
    assert row["p3_decision"] == "reject_or_noise"
    assert row["product_linkage_quality"] == "missing"
    assert row["evidence_quality_score"] == 0


def test_build_quality_review_marks_unmapped_strong_candidate_for_product_family_mapping() -> None:
    review = build_quality_review(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688999",
                    "stock_name": "映射样本",
                    "trade_date": "2025-03-10",
                    "product_snippet": "高精度机器人减速器收入占比45%",
                }
            ]
        ),
        product_rows=pd.DataFrame(),
        evidence_hits=pd.DataFrame(
            [
                _hit("CN:SH:688999", "2025-03-10", "bottleneck", "国产替代", "机器人核心零部件减速器国产替代加速"),
                _hit("CN:SH:688999", "2025-03-10", "technical_barrier", "核心技术", "掌握齿形设计和精密加工核心技术"),
                _hit("CN:SH:688999", "2025-03-10", "capacity", "产能", "新产线投产后产能提升"),
            ]
        ),
    )

    row = review.iloc[0]
    assert row["p3_decision"] == "needs_product_family_mapping"
    assert row["product_linkage_quality"] == "missing"
    assert row["next_evidence_need"] == "needs_product_family_mapping"


def test_build_quality_review_labels_missing_support_evidence_needs() -> None:
    review = build_quality_review(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688777",
                    "stock_name": "支撑缺口样本",
                    "trade_date": "2025-04-11",
                    "product_snippet": "半导体设备 薄膜沉积设备 刻蚀设备",
                }
            ]
        ),
        product_rows=pd.DataFrame(),
        evidence_hits=pd.DataFrame(
            [
                _hit("CN:SH:688777", "2025-04-11", "bottleneck", "国产替代", "半导体设备国产替代需求明确，薄膜沉积设备打破进口依赖"),
                _hit("CN:SH:688777", "2025-04-11", "technical_barrier", "核心技术", "刻蚀设备等半导体设备具备核心技术和先进制程工艺积累"),
            ]
        ),
    )

    row = review.iloc[0]
    assert row["p3_decision"] == "needs_more_evidence"
    assert row["product_family"] == "semiconductor_equipment"
    assert row["customer_quality"] == "missing"
    assert row["capacity_quality"] == "missing"
    assert row["catalyst_quality"] == "missing"
    assert (
        row["next_evidence_need"]
        == "needs_customer_or_certification_evidence|needs_capacity_evidence|needs_catalyst_evidence"
    )


def test_build_quality_review_rejects_low_tech_consumer_goods_even_when_mapped() -> None:
    review = build_quality_review(
        candidates=pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:603558",
                    "stock_name": "健盛集团",
                    "trade_date": "2025-01-10",
                    "product_snippet": "袜子 无缝服饰 家居服饰",
                }
            ]
        ),
        product_rows=pd.DataFrame(),
        evidence_hits=pd.DataFrame(
            [
                _hit("CN:SH:603558", "2025-01-10", "bottleneck", "瓶颈", "印染项目解决染色瓶颈"),
                _hit("CN:SH:603558", "2025-01-10", "technical_barrier", "发明专利", "拥有发明专利"),
                _hit("CN:SH:603558", "2025-01-10", "capacity", "产能", "全球化产能布局"),
            ]
        ),
    )

    row = review.iloc[0]
    assert row["product_family"] == "low_tech_consumer_goods"
    assert row["p3_decision"] == "reject_or_noise"
    assert "excluded product family" in row["decision_reason"]


def test_write_and_run_quality_review_from_files(tmp_path: Path) -> None:
    candidates_csv = tmp_path / "candidates.csv"
    evidence_csv = tmp_path / "evidence.csv"
    product_csv = tmp_path / "product.csv"
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:603067",
                "stock_name": "振华股份",
                "trade_date": "2025-04-30",
                "product_snippet": "铬的氧化物、铬盐联产产品、重铬酸盐",
            }
        ]
    ).to_csv(candidates_csv, index=False)
    pd.DataFrame(
        [
            _hit("CN:SH:603067", "2025-04-30", "bottleneck", "高端氧化铬绿", "高纯金属铬、高端氧化铬绿国产化，打破境外企业垄断"),
            _hit("CN:SH:603067", "2025-04-30", "technical_barrier", "核心技术", "铬盐工业污染减排集成技术应用核心技术优势"),
            _hit("CN:SH:603067", "2025-04-30", "capacity", "产能", "优势产能延伸，高纯氧化铬绿、金属铬取得批量订单"),
        ]
    ).to_csv(evidence_csv, index=False)
    pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:603067",
                "trade_date": "2025-04-30",
                "item_name": "铬的氧化物",
                "evidence_snippet": "2024年年度报告披露铬的氧化物，收入占比0.42%",
                "as_of_safe": True,
            }
        ]
    ).to_csv(product_csv, index=False)

    paths = run_quality_review_from_files(
        candidates_csv=candidates_csv,
        output_dir=tmp_path / "out",
        evidence_hits_csv=evidence_csv,
        product_rows_csv=product_csv,
    )

    assert paths["csv"].exists()
    assert paths["json"].exists()
    assert paths["summary"].exists()
    rows = pd.read_csv(paths["csv"])
    assert rows.iloc[0]["p3_decision"] == "auto_approve"
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["decision_counts"] == {"auto_approve": 1}
    expected_inputs = {
        "candidates_csv": str(candidates_csv),
        "evidence_hits_csv": str(evidence_csv),
        "product_rows_csv": str(product_csv),
    }
    assert payload["inputs"] == expected_inputs
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["inputs"] == expected_inputs


def test_write_quality_review_artifacts_outputs_decision_summary(tmp_path: Path) -> None:
    review = pd.DataFrame(
        [
            {"asset_id": "CN:SH:603239", "stock_name": "浙江仙通", "trade_date": "2025-05-16", "p3_decision": "auto_approve"},
            {
                "asset_id": "CN:SH:688999",
                "stock_name": "映射样本",
                "trade_date": "2025-03-10",
                "p3_decision": "needs_product_family_mapping",
                "product_family": "",
                "product_linkage_quality": "missing",
                "evidence_quality_score": 8,
            },
        ]
    )

    paths = write_quality_review_artifacts(review=review, output_dir=tmp_path)

    assert "auto_approve" in paths["summary"].read_text(encoding="utf-8")
    assert paths["mapping_backlog"].exists()
    backlog = pd.read_csv(paths["mapping_backlog"])
    assert backlog["asset_id"].tolist() == ["CN:SH:688999"]


def test_build_operational_queues_routes_decisions_and_prioritizes() -> None:
    review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:603067",
                "stock_name": "振华股份",
                "trade_date": "2025-04-30",
                "p3_decision": "auto_approve",
                "product_family": "chrome_chemicals",
                "weak_evidence_count": 0,
                "evidence_quality_score": 12,
            },
            {
                "asset_id": "CN:SH:603239",
                "stock_name": "浙江仙通",
                "trade_date": "2025-05-16",
                "p3_decision": "auto_approve",
                "product_family": "auto_sealing",
                "weak_evidence_count": 1,
                "evidence_quality_score": 9,
            },
            {
                "asset_id": "CN:SZ:002028",
                "stock_name": "思源电气",
                "trade_date": "2025-01-24",
                "p3_decision": "needs_more_evidence",
                "product_family": "power_grid_equipment",
                "weak_evidence_count": 1,
                "evidence_quality_score": 7,
            },
            {
                "asset_id": "CN:SH:603558",
                "stock_name": "健盛集团",
                "trade_date": "2025-01-10",
                "p3_decision": "reject_or_noise",
                "product_family": "low_tech_consumer_goods",
                "weak_evidence_count": 0,
                "evidence_quality_score": 8,
            },
        ]
    )

    queues = build_operational_queues(review)

    promotion = queues["promotion_pool"]
    assert promotion["asset_id"].tolist() == ["CN:SH:603067", "CN:SH:603239"]
    assert promotion["review_priority"].tolist() == ["P1_observe", "P2_observe_after_review"]
    assert promotion["review_action"].tolist() == ["add_to_observation_pool", "add_to_observation_pool"]

    human = queues["human_review_queue"]
    assert human.iloc[0]["asset_id"] == "CN:SZ:002028"
    assert human.iloc[0]["review_action"] == "targeted_evidence_review"

    rejected = queues["rejected_pool"]
    assert rejected.iloc[0]["asset_id"] == "CN:SH:603558"
    assert rejected.iloc[0]["review_action"] == "exclude_from_observation_pool"


def test_write_quality_review_artifacts_outputs_operational_queues(tmp_path: Path) -> None:
    review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:603067",
                "stock_name": "振华股份",
                "trade_date": "2025-04-30",
                "p3_decision": "auto_approve",
                "product_family": "chrome_chemicals",
                "weak_evidence_count": 0,
                "evidence_quality_score": 12,
            },
            {
                "asset_id": "CN:SZ:002028",
                "stock_name": "思源电气",
                "trade_date": "2025-01-24",
                "p3_decision": "needs_more_evidence",
                "product_family": "power_grid_equipment",
                "weak_evidence_count": 1,
                "evidence_quality_score": 7,
            },
        ]
    )

    paths = write_quality_review_artifacts(review=review, output_dir=tmp_path)

    assert paths["promotion_pool"].exists()
    assert paths["human_review_queue"].exists()
    assert paths["rejected_pool"].exists()
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["promotion_pool_count"] == 1
    assert payload["human_review_queue_count"] == 1


def test_build_asset_level_queues_deduplicates_by_asset_best_priority_and_score() -> None:
    queues = {
        "promotion_pool": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SH:688190",
                    "stock_name": "云路股份",
                    "trade_date": "2025-01-03",
                    "review_priority": "P1_observe",
                    "review_action": "add_to_observation_pool",
                    "p3_decision": "auto_approve",
                    "product_family": "advanced_magnetic_materials",
                    "evidence_quality_score": 12,
                    "weak_evidence_count": 0,
                },
                {
                    "asset_id": "CN:SH:688190",
                    "stock_name": "云路股份",
                    "trade_date": "2025-01-10",
                    "review_priority": "P1_observe",
                    "review_action": "add_to_observation_pool",
                    "p3_decision": "auto_approve",
                    "product_family": "advanced_magnetic_materials",
                    "evidence_quality_score": 12,
                    "weak_evidence_count": 0,
                },
            ]
        ),
        "human_review_queue": pd.DataFrame(
            [
                {
                    "asset_id": "CN:SZ:002028",
                    "stock_name": "思源电气",
                    "trade_date": "2025-01-24",
                    "review_priority": "P1_evidence_review",
                    "review_action": "targeted_evidence_review",
                    "p3_decision": "needs_more_evidence",
                    "product_family": "power_grid_equipment",
                    "evidence_quality_score": 10,
                    "weak_evidence_count": 0,
                },
                {
                    "asset_id": "CN:SZ:002028",
                    "stock_name": "思源电气",
                    "trade_date": "2025-01-27",
                    "review_priority": "P1_evidence_review",
                    "review_action": "targeted_evidence_review",
                    "p3_decision": "needs_more_evidence",
                    "product_family": "power_grid_equipment",
                    "evidence_quality_score": 9,
                    "weak_evidence_count": 0,
                },
            ]
        ),
        "rejected_pool": pd.DataFrame(),
    }

    asset_queues = build_asset_level_queues(queues)

    assert asset_queues["promotion_assets"]["trade_date"].tolist() == ["2025-01-03"]
    assert asset_queues["promotion_assets"].iloc[0]["candidate_count_for_asset"] == 2
    assert asset_queues["human_review_assets"]["trade_date"].tolist() == ["2025-01-24"]
    assert asset_queues["human_review_assets"].iloc[0]["candidate_count_for_asset"] == 2


def test_write_quality_review_artifacts_outputs_asset_queues_action_plan_and_manifest(tmp_path: Path) -> None:
    review = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:603067",
                "stock_name": "振华股份",
                "trade_date": "2025-04-30",
                "p3_decision": "auto_approve",
                "product_family": "chrome_chemicals",
                "weak_evidence_count": 0,
                "evidence_quality_score": 12,
            },
            {
                "asset_id": "CN:SH:603067",
                "stock_name": "振华股份",
                "trade_date": "2025-05-09",
                "p3_decision": "auto_approve",
                "product_family": "chrome_chemicals",
                "weak_evidence_count": 0,
                "evidence_quality_score": 11,
            },
        ]
    )

    paths = write_quality_review_artifacts(review=review, output_dir=tmp_path)

    assert paths["promotion_assets"].exists()
    assert paths["human_review_assets"].exists()
    assert paths["rejected_assets"].exists()
    assert paths["action_plan"].exists()
    assert paths["manifest"].exists()
    promotion_assets = pd.read_csv(paths["promotion_assets"])
    assert promotion_assets["asset_id"].tolist() == ["CN:SH:603067"]
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["promotion_assets_count"] == 1
    assert "promotion_assets.csv" in manifest["files"].values()


def _hit(asset_id: str, trade_date: str, bucket: str, term: str, snippet: str) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "stock_name": "",
        "trade_date": trade_date,
        "evidence_bucket": bucket,
        "evidence_type": bucket,
        "term": term,
        "matched_keyword": term,
        "snippet": snippet,
        "evidence_snippet": snippet,
        "quality": "",
    }
