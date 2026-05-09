from stock_research import factor_config


def test_manual_v1_config_contains_directions_weights_and_groups():
    config = factor_config.manual_v1_config()

    assert config["score_version"] == "manual_v1"
    assert config["calc_version"] == "v1"
    assert config["source_data_version"] == "market_daily_bar:hfq"
    assert config["factor_groups"]["ret_20"] == "momentum"
    assert config["factor_directions"]["ret_20"] == "higher"
    assert config["factor_directions"]["volatility_20"] == "lower"
    assert config["weights"]["ret_20_score"] > 0
    assert config["weights"]["volatility_20_score"] > 0
