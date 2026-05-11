from stock_research import factor_config


def test_historical_research_defaults_define_window_and_horizons():
    assert factor_config.historical_research_start_date() == "2024-01-01"
    assert factor_config.default_research_horizons() == [5, 10, 20, 60]


def test_candidate_factor_names_include_current_pipeline_outputs():
    names = factor_config.candidate_factor_names()

    assert "ret_20" in names
    assert "volatility_20" in names
    assert "alpha101_delta_close_1_rank" in names
    assert "gtja191_amount_momentum_5_10" in names
    assert "qlib_ret_5" in names
    assert len(names) == len(set(names))


def test_factor_availability_metadata_covers_candidate_factors():
    metadata = factor_config.factor_availability_metadata()

    assert set(metadata) == set(factor_config.candidate_factor_names())
    assert metadata["ret_20"] == {"start_date": None, "reason": "available_full_window"}
