from pathlib import Path

import pandas as pd

from stock_research.yanbaoke_report_backfill import (
    build_scored_candidates,
    build_yanbaoke_inventory_plan,
    load_sector_priority_config,
)


def test_load_sector_priority_config_contains_default_quota_buckets():
    config = load_sector_priority_config()

    assert set(config["sector_priority"]) >= {"P0", "P1", "P2", "P3"}
    assert config.loc[config["sector_priority"].eq("P0"), "pilot_quota"].max() == 1200
    assert "AI算力" in set(config["sector_name"])
    assert "半导体" in set(config["sector_name"])
    assert "银行" in set(config["sector_name"])


def test_build_scored_candidates_prioritizes_deep_p0_missing_coverage():
    candidates = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "report_date": "2026-04-20",
                "title": "公司深度报告：AI算力龙头成长空间打开",
                "broker": "中信证券",
                "stock_code": "000001.SZ",
                "stock_name": "算力龙头",
                "industry_lv1": "计算机",
                "industry_lv2": "AI算力",
                "theme": "AI算力",
            },
            {
                "report_id": "r2",
                "report_date": "2025-03-01",
                "title": "晨会纪要",
                "broker": "普通证券",
                "stock_code": "000002.SZ",
                "stock_name": "普通公司",
                "industry_lv1": "综合",
                "industry_lv2": "普通长尾",
                "theme": "",
            },
        ]
    )
    existing = pd.DataFrame(
        columns=["report_date", "normalized_title", "normalized_broker", "stock_code", "report_type"]
    )

    scored = build_scored_candidates(candidates, existing_coverage=existing)

    top = scored.sort_values("priority_score", ascending=False).iloc[0]
    assert top["report_id"] == "r1"
    assert top["report_type_bucket"] == "P1"
    assert top["sector_priority"] == "P0"
    assert top["sector_quota_bucket"] == "p0_growth_tech_healthcare"
    assert top["coverage_gap_reason"] == "missing_asset_report"
    assert top["priority_score"] > scored.loc[scored["report_id"].eq("r2"), "priority_score"].iloc[0]


def test_build_scored_candidates_empty_candidates_returns_shaped_frame():
    scored = build_scored_candidates(pd.DataFrame(), existing_coverage=pd.DataFrame())

    assert scored.empty
    assert {
        "normalized_title",
        "normalized_broker",
        "report_type_bucket",
        "theme_bucket",
        "sector_priority",
        "sector_quota_bucket",
        "sector_pilot_quota",
        "asset_priority",
        "coverage_gap_reason",
        "priority_score",
    } <= set(scored.columns)


def test_build_yanbaoke_inventory_plan_writes_gap_matrices(tmp_path: Path):
    candidates = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "report_date": "2026-04-20",
                "title": "公司深度报告：AI算力龙头",
                "broker": "中信证券",
                "stock_code": "000001.SZ",
                "stock_name": "算力龙头",
                "industry_lv1": "计算机",
                "industry_lv2": "AI算力",
                "theme": "AI算力",
            },
            {
                "report_id": "r2",
                "report_date": "2025-08-10",
                "title": "行业深度：银行资产质量",
                "broker": "招商证券",
                "stock_code": "",
                "stock_name": "",
                "industry_lv1": "银行",
                "industry_lv2": "银行",
                "theme": "银行",
            },
        ]
    )

    result = build_yanbaoke_inventory_plan(
        candidates=candidates,
        existing_coverage=pd.DataFrame(),
        start_date="2025-01-01",
        end_date="2026-06-12",
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["candidate_reports"]).exists()
    assert Path(result["paths"]["sector_gap_matrix"]).exists()
    assert Path(result["paths"]["asset_gap_matrix"]).exists()
    assert Path(result["paths"]["existing_report_coverage"]).exists()
    assert Path(result["paths"]["gap_matrix"]).exists()
    assert Path(result["paths"]["priority_queue"]).exists()
    assert Path(result["paths"]["report"]).exists()
    assert {"existing_report_coverage", "gap_matrix"} <= set(result["paths"])
    sector_gap = pd.read_csv(result["paths"]["sector_gap_matrix"])
    assert set(sector_gap["sector_priority"]) >= {"P0", "P2"}
    existing_coverage = pd.read_csv(result["paths"]["existing_report_coverage"])
    assert list(existing_coverage.columns) == [
        "report_date",
        "normalized_title",
        "normalized_broker",
        "stock_code",
        "report_type",
    ]
    gap_matrix = pd.read_csv(result["paths"]["gap_matrix"])
    assert {
        "month",
        "normalized_broker",
        "industry_lv1",
        "industry_lv2",
        "stock_code",
        "stock_name",
        "report_type_bucket",
        "coverage_gap_reason",
        "candidate_count",
        "max_priority_score",
    } <= set(gap_matrix.columns)
    assert set(gap_matrix["month"]) == {"2026-04", "2025-08"}
    assert set(gap_matrix["industry_lv1"]) == {"计算机", "银行"}
    assert gap_matrix["candidate_count"].sum() == 2
    assert "Yanbaoke Report Backfill Inventory" in Path(result["paths"]["report"]).read_text(encoding="utf-8")


def test_build_yanbaoke_inventory_plan_allows_missing_existing_coverage(tmp_path: Path):
    candidates = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "report_date": "2026-04-20",
                "title": "公司深度报告：AI算力龙头",
                "broker": "中信证券",
                "stock_code": "000001.SZ",
                "stock_name": "算力龙头",
                "industry_lv1": "计算机",
                "industry_lv2": "AI算力",
                "theme": "AI算力",
            }
        ]
    )

    result = build_yanbaoke_inventory_plan(
        candidates=candidates,
        existing_coverage=None,
        start_date="2025-01-01",
        end_date="2026-06-12",
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["existing_report_coverage"]).exists()
    assert result["existing_report_coverage"].empty
    assert list(result["existing_report_coverage"].columns) == [
        "report_date",
        "normalized_title",
        "normalized_broker",
        "stock_code",
        "report_type",
    ]


def test_build_yanbaoke_inventory_plan_stabilizes_existing_coverage_columns(tmp_path: Path):
    candidates = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "report_date": "2026-04-20",
                "title": "公司深度报告：AI算力龙头",
                "broker": "中信证券",
                "stock_code": "000001.SZ",
                "stock_name": "算力龙头",
                "industry_lv1": "计算机",
                "industry_lv2": "AI算力",
                "theme": "AI算力",
            }
        ]
    )
    existing = pd.DataFrame([{"stock_code": "000001.SZ", "source": "manual"}])

    result = build_yanbaoke_inventory_plan(
        candidates=candidates,
        existing_coverage=existing,
        start_date="2025-01-01",
        end_date="2026-06-12",
        output_dir=tmp_path,
    )

    coverage = pd.read_csv(result["paths"]["existing_report_coverage"])
    assert list(coverage.columns[:5]) == [
        "report_date",
        "normalized_title",
        "normalized_broker",
        "stock_code",
        "report_type",
    ]
    assert "source" in coverage.columns


def test_inventory_report_priority_distribution_includes_report_type_bucket(tmp_path: Path):
    candidates = pd.DataFrame(
        [
            {
                "report_id": "r1",
                "report_date": "2026-04-20",
                "title": "公司深度报告：AI算力龙头",
                "broker": "中信证券",
                "stock_code": "000001.SZ",
                "stock_name": "算力龙头",
                "industry_lv1": "计算机",
                "industry_lv2": "AI算力",
                "theme": "AI算力",
            }
        ]
    )

    result = build_yanbaoke_inventory_plan(
        candidates=candidates,
        existing_coverage=None,
        start_date="2025-01-01",
        end_date="2026-06-12",
        output_dir=tmp_path,
    )

    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")
    assert "report_type_bucket" in report
    assert "| sector_priority | report_type_bucket | candidate_count |" in report


def test_build_yanbaoke_inventory_plan_excludes_candidates_outside_date_window(tmp_path: Path):
    candidates = pd.DataFrame(
        [
            {
                "report_id": "inside",
                "report_date": "2026-04-20",
                "title": "公司深度报告：AI算力龙头",
                "broker": "中信证券",
                "stock_code": "000001.SZ",
                "stock_name": "算力龙头",
                "industry_lv1": "计算机",
                "industry_lv2": "AI算力",
                "theme": "AI算力",
            },
            {
                "report_id": "outside",
                "report_date": "2024-12-31",
                "title": "行业深度：银行资产质量",
                "broker": "招商证券",
                "stock_code": "",
                "stock_name": "",
                "industry_lv1": "银行",
                "industry_lv2": "银行",
                "theme": "银行",
            },
        ]
    )

    result = build_yanbaoke_inventory_plan(
        candidates=candidates,
        existing_coverage=None,
        start_date="2025-01-01",
        end_date="2026-06-12",
        output_dir=tmp_path,
    )

    candidate_reports = pd.read_csv(result["paths"]["candidate_reports"])
    gap_matrix = pd.read_csv(result["paths"]["gap_matrix"])
    assert set(candidate_reports["report_id"]) == {"inside"}
    assert gap_matrix["candidate_count"].sum() == 1
    assert set(gap_matrix["industry_lv1"]) == {"计算机"}
