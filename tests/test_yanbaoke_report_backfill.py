import pandas as pd

from stock_research.yanbaoke_report_backfill import build_scored_candidates, load_sector_priority_config


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
