from pathlib import Path

import pandas as pd

from stock_research.serenity_source_backed_evidence_fill import (
    build_pdf_text_industry_chain_evidence_seed,
    build_customer_certification_evidence_seed,
    build_report_index_evidence_seed,
    build_serenity_source_backed_evidence_fill,
)


def test_source_backed_fill_keeps_artifact_only_separate_from_primary_evidence(tmp_path: Path):
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "primary_chain_id": "ai_optical_interconnect",
                "revenue_exposure_bucket": "core_or_high_confidence_product_exposure",
                "customer_certification_stage": "order_or_delivery",
                "supplier_concentration_evidence": "likely_concentrated_supply_chain",
                "evidence_source_provenance": '{"artifact_level":"local_artifact_provenance"}',
            },
            {
                "asset_id": "CN:SH:601939",
                "stock_name": "建设银行",
                "primary_chain_id": "robotics_core_components",
                "revenue_exposure_bucket": "early_ramp_or_inflection_exposure",
                "customer_certification_stage": "customer_validation_or_delivery",
                "supplier_concentration_evidence": "concentration_not_established",
                "evidence_source_provenance": "",
            },
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "field": "revenue_exposure_bucket",
                "source_type": "broker_report",
                "source_path": "data/manual/reports/300308-product-breakdown.pdf",
                "source_date": "2026-05-20",
                "supports_value": "core_or_high_confidence_product_exposure",
                "claim": "高速光模块为核心收入和利润来源。",
                "evidence_tier": "tier1",
                "excerpt": "高速光模块收入占比高。",
            },
            {
                "asset_id": "CN:SZ:300308",
                "field": "customer_certification_stage",
                "source_type": "company_announcement",
                "source_path": "data/manual/announcements/300308-order.pdf",
                "source_date": "2026-04-18",
                "supports_value": "order_or_delivery",
                "claim": "客户订单进入交付。",
                "evidence_tier": "tier1",
                "excerpt": "已取得客户订单并开始交付。",
            },
            {
                "asset_id": "CN:SZ:300308",
                "field": "supplier_concentration_evidence",
                "source_type": "broker_report",
                "source_path": "data/manual/reports/optical-supply.pdf",
                "source_date": "2026-05-21",
                "supports_value": "",
                "claim": "光模块供应链集中度较高。",
                "evidence_tier": "tier2",
                "excerpt": "头部厂商份额集中。",
            },
        ]
    )

    result = build_serenity_source_backed_evidence_fill(
        structured_detail=structured,
        evidence_seed=evidence,
        output_dir=tmp_path,
        run_id="unit",
    )

    long = result["long"].set_index(["asset_id", "field"])
    assert long.loc[("CN:SZ:300308", "revenue_exposure_bucket"), "evidence_grade"] == "primary_strong"
    assert long.loc[("CN:SZ:300308", "revenue_exposure_bucket"), "source_backed_value"] == (
        "core_or_high_confidence_product_exposure"
    )
    assert long.loc[("CN:SZ:300308", "customer_certification_stage"), "evidence_grade"] == "primary_strong"
    assert long.loc[("CN:SZ:300308", "supplier_concentration_evidence"), "evidence_grade"] == "primary_partial"
    assert long.loc[("CN:SH:601939", "revenue_exposure_bucket"), "evidence_grade"] == "missing"

    detail = result["detail"].set_index("asset_id")
    assert detail.loc["CN:SZ:300308", "source_backed_field_count"] == 3
    assert detail.loc["CN:SH:601939", "artifact_only_or_missing_field_count"] == 3
    assert Path(result["paths"]["manual_queue"]).exists()


def test_source_backed_fill_writes_gap_summary_and_manual_queue(tmp_path: Path):
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "stock_name": "生益科技",
                "revenue_exposure_bucket": "meaningful_segment_exposure",
                "customer_certification_stage": "not_identified",
                "supplier_concentration_evidence": "scarce_or_import_substitution_node",
                "evidence_source_provenance": '{"artifact_level":"local_artifact_provenance"}',
            }
        ]
    )

    result = build_serenity_source_backed_evidence_fill(
        structured_detail=structured,
        evidence_seed=pd.DataFrame(),
        output_dir=tmp_path,
        run_id="unit",
    )

    summary = result["summary"].set_index("field")
    assert summary.loc["revenue_exposure_bucket", "artifact_only"] == 1
    assert summary.loc["customer_certification_stage", "artifact_only"] == 1
    assert summary.loc["supplier_concentration_evidence", "artifact_only"] == 1
    assert len(result["manual_queue"]) == 3
    assert set(result["manual_queue"]["needed_source_type"]) == {
        "annual report segment revenue, product revenue split, order backlog, or broker product breakdown",
        "customer validation, design-in, qualification, fixed-point, order, delivery, or mass-production evidence",
        "market share, import dependency, domestic substitute scarcity, supplier count, or single/leading supplier evidence",
    }


def test_source_backed_fill_accepts_akshare_mainbiz_as_primary_revenue_source(tmp_path: Path):
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002169",
                "stock_name": "智光电气",
                "primary_chain_id": "power_grid_energy_infrastructure",
                "revenue_exposure_bucket": "meaningful_segment_exposure",
                "customer_certification_stage": "not_identified",
                "supplier_concentration_evidence": "concentration_not_established",
                "evidence_source_provenance": "",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002169",
                "field": "revenue_exposure_bucket",
                "source_type": "akshare_mainbiz",
                "source_path": (
                    "finance.main_business_composition:CN:SZ:002169:2025-12-31:"
                    "按产品分类:数字能源技术及产品"
                ),
                "source_date": "2025-12-31",
                "supports_value": "meaningful_segment_exposure",
                "claim": "主营构成显示数字能源技术及产品收入占比86.68%。",
                "evidence_tier": "tier1",
                "excerpt": "数字能源技术及产品 revenue_ratio=86.68%",
            }
        ]
    )

    result = build_serenity_source_backed_evidence_fill(
        structured_detail=structured,
        evidence_seed=evidence,
        output_dir=tmp_path,
        run_id="unit",
    )

    long = result["long"].set_index(["asset_id", "field"])
    assert long.loc[("CN:SZ:002169", "revenue_exposure_bucket"), "evidence_grade"] == "primary_strong"
    assert long.loc[("CN:SZ:002169", "revenue_exposure_bucket"), "source_backed_value"] == (
        "meaningful_segment_exposure"
    )
    assert len(result["manual_queue"]) == 2
    assert set(result["manual_queue"]["needed_source_type"]) == {
        "customer validation, design-in, qualification, fixed-point, order, delivery, or mass-production evidence",
        "market share, import dependency, domestic substitute scarcity, supplier count, or single/leading supplier evidence",
    }


def test_cli_dispatches_source_backed_evidence_fill(monkeypatch, capsys, tmp_path: Path):
    import stock_research.cli as cli

    calls = {}

    def fake_run(**kwargs):
        calls.update(kwargs)
        return {
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "long": str(tmp_path / "long.csv"),
                "summary": str(tmp_path / "summary.csv"),
                "manual_queue": str(tmp_path / "queue.csv"),
                "report": str(tmp_path / "report.md"),
            },
            "summary": pd.DataFrame([{"field": "revenue_exposure_bucket"}]),
            "manual_queue": pd.DataFrame([{"asset_id": "CN:SZ:300308"}]),
        }

    monkeypatch.setattr(cli, "run_serenity_source_backed_evidence_fill", fake_run, raising=False)

    cli.main(
        [
            "serenity-source-backed-evidence-fill",
            "--structured-detail-path",
            "/tmp/structured.csv",
            "--evidence-seed-path",
            "/tmp/evidence.csv",
            "--output-dir",
            "/tmp/out",
            "--run-id",
            "unit",
        ]
    )

    assert calls == {
        "structured_detail_path": "/tmp/structured.csv",
        "evidence_seed_path": "/tmp/evidence.csv",
        "output_dir": "/tmp/out",
        "run_id": "unit",
    }
    out = capsys.readouterr().out
    assert "serenity_source_backed_evidence|detail|" in out
    assert "serenity_source_backed_evidence|manual_queue|" in out
    assert "serenity_source_backed_evidence|manual_queue_rows|1" in out


def test_report_index_evidence_seed_extracts_source_backed_claims_from_local_reports():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000400",
                "stock_name": "许继电气",
                "primary_chain_id": "power_delivery",
                "revenue_exposure_bucket": "early_ramp_or_inflection_exposure",
                "customer_certification_stage": "order",
                "supplier_concentration_type": "concentration_not_established",
            }
        ]
    )
    reports = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000400",
                "stock_name": "许继电气",
                "publish_date": "2026-04-17",
                "broker": "光大证券",
                "report_title": "26Q1盈利能力承压 期待特高压订单交付放量",
                "content": "公司特高压订单有望交付放量，电网设备收入为重要业务分部。",
                "pdf_path": "data/manual/reports/000400.pdf",
                "detail_url": "https://example.test/report",
            }
        ]
    )

    seed = build_report_index_evidence_seed(structured_detail=structured, report_index=reports)

    assert set(seed["field"]) == {"revenue_exposure_bucket", "customer_certification_stage"}
    customer = seed[seed["field"].eq("customer_certification_stage")].iloc[0]
    assert customer["supports_value"] == "order"
    assert customer["source_type"] == "broker_report"
    assert "订单" in customer["claim"]


def test_pdf_text_industry_chain_seed_extracts_revenue_customer_and_supplier_evidence():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002222",
                "stock_name": "福晶科技",
                "primary_chain_id": "ai_optical_interconnect",
                "revenue_exposure_bucket": "meaningful_segment_exposure",
                "customer_certification_stage": "order_or_delivery",
                "supplier_concentration_type": "likely_concentrated_supply_chain",
            }
        ]
    )
    reports = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002222",
                "stock_name": "福晶科技",
                "publish_date": "2025-06-03",
                "broker": "中航证券",
                "report_title": "三大业务并驾齐驱 至期光子构筑新增长曲线",
                "pdf_path": "data/manual/reports/002222.pdf",
                "source_type": "annual_report",
            }
        ]
    )

    def fake_fetcher(path: str) -> str:
        assert path == "data/manual/reports/002222.pdf"
        return (
            "公司光通信和激光晶体业务收入持续增长，核心产品进入放量阶段。"
            "公司已向重点客户批量供货并完成多轮验证。"
            "上游高端晶体材料供应稀缺，国产替代空间较大。"
        )

    seed = build_pdf_text_industry_chain_evidence_seed(
        structured_detail=structured,
        report_index=reports,
        fetcher=fake_fetcher,
    )

    assert set(seed["field"]) == {
        "revenue_exposure_bucket",
        "customer_certification_stage",
        "supplier_concentration_type",
    }
    assert seed.set_index("field").loc["revenue_exposure_bucket", "supports_value"] == "meaningful_segment_exposure"
    assert seed.set_index("field").loc["customer_certification_stage", "supports_value"] == "order_or_delivery"
    assert seed.set_index("field").loc["supplier_concentration_type", "supports_value"] == "likely_concentrated_supply_chain"
    assert seed["source_type"].eq("annual_report").all()
    assert seed["source_path"].eq("data/manual/reports/002222.pdf").all()
    assert seed["excerpt"].str.contains("批量供货|国产替代", regex=True).any()


def test_pdf_text_industry_chain_seed_ignores_generic_financial_boilerplate():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600206",
                "stock_name": "有研新材",
                "primary_chain_id": "high_end_sensors",
                "revenue_exposure_bucket": "meaningful_segment_exposure",
                "customer_certification_stage": "",
                "supplier_concentration_type": "likely_concentrated_supply_chain",
            }
        ]
    )
    reports = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600206",
                "publish_date": "2023-04-27",
                "report_title": "2022年年度报告",
                "pdf_path": "data/manual/reports/600206.pdf",
                "source_type": "annual_report",
            }
        ]
    )

    seed = build_pdf_text_industry_chain_evidence_seed(
        structured_detail=structured,
        report_index=reports,
        fetcher=lambda _: "本公司实现净利润，提取法定公积金。少数股东权益影响额。公司不存在其他事项。",
    )

    assert seed.empty


def test_report_index_evidence_seed_does_not_promote_negative_or_unidentified_values():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600388",
                "stock_name": "龙净环保",
                "primary_chain_id": "power_grid_energy_infrastructure",
                "revenue_exposure_bucket": "early_ramp_or_inflection_exposure",
                "customer_certification_stage": "not_identified",
                "supplier_concentration_evidence": "concentration_not_established",
            }
        ]
    )
    reports = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600388",
                "stock_name": "龙净环保",
                "publish_date": "2026-05-10",
                "broker": "样例证券",
                "report_title": "订单交付改善，收入有望放量",
                "content": "公司订单交付改善，收入有望放量，但未说明客户认证或供应集中度。",
                "pdf_path": "data/manual/reports/600388.pdf",
            }
        ]
    )

    seed = build_report_index_evidence_seed(structured_detail=structured, report_index=reports)

    assert set(seed["field"]) == {
        "revenue_exposure_bucket",
        "customer_certification_stage",
        "supplier_concentration_evidence",
    }
    assert seed[seed["field"].eq("customer_certification_stage")].iloc[0]["supports_value"] == ""
    assert seed[seed["field"].eq("supplier_concentration_evidence")].iloc[0]["supports_value"] == ""


def test_report_index_seed_does_not_strongly_support_not_established_values():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000682",
                "stock_name": "东方电子",
                "primary_chain_id": "power_grid_energy_infrastructure",
                "revenue_exposure_bucket": "early_ramp_or_inflection_exposure",
                "customer_certification_stage": "not_identified",
                "supplier_concentration_type": "concentration_not_established",
            }
        ]
    )
    reports = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000682",
                "stock_name": "东方电子",
                "publish_date": "2026-04-28",
                "broker": "光大证券",
                "report_title": "收入稳健增长 中标规模突破",
                "content": "公司客户覆盖较广，行业龙头地位突出。",
                "pdf_path": "data/manual/reports/000682.pdf",
                "detail_url": "",
            }
        ]
    )

    seed = build_report_index_evidence_seed(structured_detail=structured, report_index=reports)

    customer = seed[seed["field"].eq("customer_certification_stage")].iloc[0]
    supplier = seed[seed["field"].eq("supplier_concentration_type")].iloc[0]
    assert customer["supports_value"] == ""
    assert customer["evidence_tier"] == "tier2"
    assert supplier["supports_value"] == ""
    assert supplier["evidence_tier"] == "tier2"


def test_source_backed_fill_accepts_new_supplier_concentration_type_field(tmp_path: Path):
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300567",
                "stock_name": "精测电子",
                "primary_chain_id": "semiconductor_equipment",
                "revenue_exposure_bucket": "meaningful_segment_exposure",
                "customer_certification_stage": "certification",
                "supplier_concentration_type": "import_dependency_or_domestic_substitution_scarcity",
                "source_provenance": "serenity_method_evidence_fields_20260608:candidate_row",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300567",
                "field": "supplier_concentration_type",
                "source_type": "broker_report",
                "source_path": "data/manual/reports/300567.pdf",
                "source_date": "2026-04-30",
                "supports_value": "import_dependency_or_domestic_substitution_scarcity",
                "claim": "半导体检测设备国产替代空间大。",
                "evidence_tier": "tier1",
                "excerpt": "国产替代",
            }
        ]
    )

    result = build_serenity_source_backed_evidence_fill(
        structured_detail=structured,
        evidence_seed=evidence,
        output_dir=tmp_path,
        run_id="unit",
    )

    long = result["long"].set_index(["asset_id", "field"])
    assert long.loc[("CN:SZ:300567", "supplier_concentration_type"), "evidence_grade"] == "primary_strong"
    assert long.loc[("CN:SZ:300567", "revenue_exposure_bucket"), "evidence_grade"] == "artifact_only"


def test_source_backed_fill_maps_legacy_supplier_evidence_alias_to_type_field(tmp_path: Path):
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002222",
                "stock_name": "福晶科技",
                "primary_chain_id": "ai_optical_interconnect",
                "revenue_exposure_bucket": "meaningful_segment_exposure",
                "customer_certification_stage": "",
                "supplier_concentration_type": "likely_concentrated_supply_chain",
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002222",
                "field": "supplier_concentration_evidence",
                "source_type": "broker_report",
                "source_path": "data/manual/reports/002222.pdf",
                "source_date": "2025-06-03",
                "supports_value": "",
                "claim": "研报包含国产替代和稀缺供应链描述。",
                "evidence_tier": "tier2",
                "excerpt": "国产替代 稀缺",
            }
        ]
    )

    result = build_serenity_source_backed_evidence_fill(
        structured_detail=structured,
        evidence_seed=evidence,
        output_dir=tmp_path,
        run_id="unit",
    )

    long = result["long"].set_index(["asset_id", "field"])
    assert long.loc[("CN:SZ:002222", "supplier_concentration_type"), "evidence_grade"] == "primary_partial"


def test_customer_certification_seed_combines_announcements_investor_qa_and_reports():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "stock_name": "中际旭创",
                "customer_certification_stage": "order_or_delivery",
            },
            {
                "asset_id": "CN:SH:600183",
                "stock_name": "生益科技",
                "customer_certification_stage": "not_identified",
            },
        ]
    )
    announcements = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "title": "关于取得海外客户高速光模块订单并开始交付的公告",
                "content": "",
                "published_at": "2026-05-11",
                "url": "https://example.test/notice",
                "source_name": "cninfo_disclosure_announcement",
            }
        ]
    )
    investor_qa = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "summary": "公司已通过重点客户验证，部分产品进入批量交付阶段。",
                "survey_date": "2026-05-12",
                "source": "akshare",
                "source_endpoint": "stock_jgdy_detail_em",
            }
        ]
    )
    reports = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:300308",
                "report_title": "海外客户导入顺利，800G产品量产交付",
                "raw_summary": "公司通过海外大客户认证，800G产品量产交付。",
                "publish_date": "2026-05-13",
                "source_url": "file:///tmp/report.pdf",
                "broker": "样例证券",
            },
            {
                "asset_id": "CN:SH:600183",
                "report_title": "收入稳健增长",
                "raw_summary": "未披露客户认证信息。",
                "publish_date": "2026-05-13",
                "source_url": "file:///tmp/report2.pdf",
                "broker": "样例证券",
            },
        ]
    )

    seed = build_customer_certification_evidence_seed(
        structured_detail=structured,
        announcements=announcements,
        investor_qa=investor_qa,
        reports=reports,
    )

    assert set(seed["source_type"]) == {"company_announcement", "investor_qa", "broker_report"}
    assert seed["field"].eq("customer_certification_stage").all()
    assert seed["supports_value"].eq("order_or_delivery").all()
    assert seed["asset_id"].tolist().count("CN:SZ:300308") == 3
    assert "CN:SH:600183" not in set(seed["asset_id"])


def test_customer_certification_seed_derives_stage_from_source_text_when_structured_value_missing():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "stock_name": "生益科技",
                "customer_certification_stage": "not_identified",
            }
        ]
    )
    announcements = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600183",
                "title": "关于AI服务器材料通过客户认证并开始批量交付的公告",
                "published_at": "2026-04-20",
                "url": "https://example.test/notice-600183",
                "source_name": "cninfo_disclosure_announcement",
            }
        ]
    )

    seed = build_customer_certification_evidence_seed(
        structured_detail=structured,
        announcements=announcements,
    )

    assert len(seed) == 1
    assert seed.iloc[0]["supports_value"] == "order_or_delivery"
    assert seed.iloc[0]["source_type"] == "company_announcement"


def test_customer_certification_seed_keeps_positive_validation_even_when_scale_not_yet_reached():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000049",
                "stock_name": "德赛电池",
                "customer_certification_stage": "not_identified",
            }
        ]
    )
    investor_qa = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000049",
                "answer": "公司已有锂电池产品应用于人形机器人，目前此类业务处于客户验证、样品或小批量阶段，尚未形成规模化销售。",
                "survey_date": "2026-05-26",
                "source": "cninfo_irm",
            }
        ]
    )

    seed = build_customer_certification_evidence_seed(
        structured_detail=structured,
        investor_qa=investor_qa,
    )

    assert len(seed) == 1
    assert seed.iloc[0]["supports_value"] == "customer_validation_or_delivery"


def test_customer_certification_seed_skips_explicit_negative_certification_context():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000049",
                "stock_name": "德赛电池",
                "customer_certification_stage": "not_identified",
            }
        ]
    )
    investor_qa = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000049",
                "answer": "公司相关产品尚未取得客户认证，目前不涉及批量供货。",
                "survey_date": "2026-05-26",
                "source": "cninfo_irm",
            }
        ]
    )

    seed = build_customer_certification_evidence_seed(
        structured_detail=structured,
        investor_qa=investor_qa,
    )

    assert seed.empty


def test_customer_certification_seed_does_not_treat_small_quantity_as_mass_production():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000049",
                "stock_name": "德赛电池",
                "customer_certification_stage": "order_or_delivery",
            }
        ]
    )
    investor_qa = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:000049",
                "answer": "公司主要从事锂电池相关业务，有少量产品应用于数据中心电源。",
                "survey_date": "2026-05-25",
                "source": "cninfo_irm",
            }
        ]
    )

    seed = build_customer_certification_evidence_seed(
        structured_detail=structured,
        investor_qa=investor_qa,
    )

    assert seed.empty


def test_customer_certification_seed_skips_boilerplate_refer_to_announcements():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002222",
                "stock_name": "福晶科技",
                "customer_certification_stage": "order_or_delivery",
            }
        ]
    )
    investor_qa = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002222",
                "answer": "具体经营信息、产能及订单详细情况，以公司定期报告或临时公告披露的信息为准。",
                "survey_date": "2026-05-26",
                "source": "cninfo_irm",
            }
        ]
    )

    seed = build_customer_certification_evidence_seed(
        structured_detail=structured,
        investor_qa=investor_qa,
    )

    assert seed.empty


def test_customer_certification_seed_skips_order_intention_without_confirmed_customer_stage():
    structured = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002222",
                "stock_name": "福晶科技",
                "customer_certification_stage": "order_or_delivery",
            }
        ]
    )
    investor_qa = pd.DataFrame(
        [
            {
                "asset_id": "CN:SZ:002222",
                "answer": "公司将结合实际进行产线建设，积极争取市场订单，具体经营信息以公司定期报告或公告披露的信息为准。",
                "survey_date": "2026-05-26",
                "source": "cninfo_irm",
            }
        ]
    )

    seed = build_customer_certification_evidence_seed(
        structured_detail=structured,
        investor_qa=investor_qa,
    )

    assert seed.empty
