from stock_research import factor_config, factor_registry


def test_factor_registry_returns_metadata_for_manual_factor():
    meta = factor_registry.get_factor_metadata("ret_20")

    assert meta.factor_name == "ret_20"
    assert meta.factor_group == "momentum"
    assert meta.direction == "higher"
    assert meta.status == "validated"
    assert meta.calc_version == "v1"


def test_factor_registry_lists_all_known_factor_names_sorted():
    names = factor_registry.list_factor_names()

    assert "ret_20" in names
    assert "volatility_20" in names
    assert names == sorted(names)


def test_manual_v1_config_is_derived_from_registry_maps():
    config = factor_config.manual_v1_config()

    assert config["factor_groups"]["ret_20"] == "momentum"
    assert config["factor_directions"]["volatility_20"] == "lower"
    assert "ret_20_score" in config["weights"]


def test_factor_registry_availability_metadata_matches_candidates():
    candidates = factor_config.candidate_factor_names()
    availability = factor_config.factor_availability_metadata()

    assert sorted(availability) == candidates
    assert availability["ret_20"]["reason"] == "available_full_window"
