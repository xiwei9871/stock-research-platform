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


def test_candidate_factor_names_include_fundamental_factors_without_changing_manual_weights():
    names = factor_config.candidate_factor_names()
    config = factor_config.manual_v1_config()

    for factor_name in (
        "roe",
        "roa",
        "gross_margin",
        "net_margin",
        "debt_ratio",
        "ocf_to_np",
        "pe_ttm",
        "ps_ttm",
        "pb",
    ):
        assert factor_name in names

    assert config["weights"] == {
        "ret_20_score": 0.15,
        "ret_60_score": 0.10,
        "momentum_20_5_score": 0.10,
        "ma20_slope_score": 0.10,
        "ma60_slope_score": 0.05,
        "trend_r2_20_score": 0.05,
        "amount_ratio_5_20_score": 0.08,
        "volume_ratio_5_20_score": 0.05,
        "volatility_20_score": 0.10,
        "max_drawdown_20_score": 0.07,
        "atr_pct_score": 0.05,
        "sector_ret_20_score": 0.05,
        "stock_excess_ret_20_score": 0.05,
    }


def test_factor_availability_metadata_covers_candidate_factors():
    metadata = factor_config.factor_availability_metadata()

    assert set(metadata) == set(factor_config.candidate_factor_names())
    assert metadata["ret_20"] == {"start_date": None, "reason": "available_full_window"}
