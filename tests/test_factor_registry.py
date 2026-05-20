from stock_research import factor_config, factor_registry


def test_factor_registry_returns_metadata_for_manual_factor():
    meta = factor_registry.get_factor_metadata("ret_20")

    assert meta.factor_name == "ret_20"
    assert meta.factor_group == "momentum"
    assert meta.direction == "higher"
    assert meta.status == "validated"
    assert meta.calc_version == "v1"


def test_factor_registry_returns_metadata_for_fundamental_factor():
    meta = factor_registry.get_factor_metadata("roe")

    assert meta.factor_name == "roe"
    assert meta.factor_group == "quality"
    assert meta.direction == "higher"
    assert meta.source == "fundamental"
    assert meta.status == "validated"
    assert meta.calc_version == "v1"


def test_factor_registry_lists_all_known_factor_names_sorted():
    names = factor_registry.list_factor_names()

    assert "ret_20" in names
    assert "volatility_20" in names
    assert names == sorted(names)


def test_factor_registry_lists_fundamental_factor_names():
    names = factor_registry.list_factor_names()

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


def test_manual_v1_config_is_derived_from_registry_maps():
    config = factor_config.manual_v1_config()

    assert config["factor_groups"]["ret_20"] == "momentum"
    assert config["factor_directions"]["volatility_20"] == "lower"
    assert "ret_20_score" in config["weights"]


def test_manual_v1_config_does_not_add_fundamental_weights():
    config = factor_config.manual_v1_config()
    fundamental_factor_names = {
        metadata.factor_name
        for metadata in factor_registry.list_factor_metadata()
        if metadata.source == "fundamental"
    }

    for factor_name in fundamental_factor_names:
        assert factor_name in config["factor_groups"]
        assert factor_name in config["factor_directions"]
        assert f"{factor_name}_score" not in config["weights"]


def test_factor_registry_availability_metadata_matches_candidates():
    candidates = factor_config.candidate_factor_names()
    availability = factor_config.factor_availability_metadata()

    assert sorted(availability) == candidates
    assert availability["ret_20"]["reason"] == "available_full_window"
