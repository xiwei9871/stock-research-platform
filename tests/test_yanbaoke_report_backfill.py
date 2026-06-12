from stock_research.yanbaoke_report_backfill import load_sector_priority_config


def test_load_sector_priority_config_contains_default_quota_buckets():
    config = load_sector_priority_config()

    assert set(config["sector_priority"]) >= {"P0", "P1", "P2", "P3"}
    assert config.loc[config["sector_priority"].eq("P0"), "pilot_quota"].max() == 1200
    assert "AI算力" in set(config["sector_name"])
    assert "半导体" in set(config["sector_name"])
    assert "银行" in set(config["sector_name"])
