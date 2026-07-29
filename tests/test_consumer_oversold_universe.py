from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.contracts import ConsumerOversoldConfig
from stock_research.consumer_oversold.universe import build_consumer_universe_from_frames


TRADE_DATE = "2026-07-29"
INDUSTRY_RULES_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "consumer_oversold_industry_rules_v1.csv"
)
ASSET_OVERRIDES_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "consumer_oversold_asset_overrides_v1.csv"
)


def _assets() -> pd.DataFrame:
    rows = [
        ("a1", "601888", "中国中免", "2019-10-18"),
        ("a2", "000759", "中百集团", "1997-05-19"),
        ("a3", "601127", "赛力斯", "2016-06-15"),
        ("a4", "600418", "江淮汽车", "2001-08-24"),
        ("a5", "000887", "中鼎股份", "1998-12-03"),
        ("a6", "600001", "ST样例", "2000-01-01"),
        ("a7", "600002", "新股样例", "2026-01-01"),
        ("a8", "600003", "低流动性样例", "2000-01-01"),
        ("a9", "600004", "停牌样例", "2000-01-01"),
        ("a10", "600005", "缺行业样例", "2000-01-01"),
    ]
    return pd.DataFrame(rows, columns=["asset_id", "stock_code", "name", "list_date"])


def _statuses() -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "asset_id": [f"a{i}" for i in range(1, 11)],
            "is_st": False,
            "is_delisting_risk": False,
            "is_suspended": False,
        }
    )
    result.loc[result["asset_id"].eq("a6"), "is_st"] = True
    result.loc[result["asset_id"].eq("a9"), "is_suspended"] = True
    return result


def _liquidity() -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "asset_id": [f"a{i}" for i in range(1, 11)],
            "avg_turnover_amount": 100_000_000.0,
        }
    )
    result.loc[result["asset_id"].eq("a8"), "avg_turnover_amount"] = 1_000_000.0
    return result


def _industries() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("a1", "申万", "旅游零售免税"),
            ("a2", "申万", "商超零售"),
            ("a3", "申万", "乘用车"),
            ("a4", "申万", "商用车整车"),
            ("a5", "申万", "汽车零部件"),
            ("a6", "申万", "食品"),
            ("a7", "申万", "家用电器"),
            ("a8", "申万", "百货零售"),
            ("a9", "申万", "酒店餐饮"),
        ],
        columns=["asset_id", "industry_system", "industry_name"],
    )


def _industry_rules() -> pd.DataFrame:
    return pd.DataFrame(
        [
            (10, "*", "汽车零部件|零部件", "", "exclude", "not_terminal_consumer"),
            (100, "*", "食品", "food_beverage", "include", "terminal_consumer_industry"),
            (110, "*", "家用电器", "home_appliance", "include", "terminal_consumer_industry"),
            (120, "*", "商超|百货|零售|免税", "retail_duty_free", "include", "terminal_consumer_industry"),
            (130, "*", "旅游|酒店|餐饮", "tourism_hospitality", "include", "terminal_consumer_industry"),
            (170, "*", "乘用车|商用车|汽车整车|整车", "auto_oem", "include", "terminal_consumer_industry"),
        ],
        columns=[
            "priority",
            "industry_system",
            "industry_name_pattern",
            "consumer_subindustry",
            "action",
            "reason",
        ],
    )


def _overrides(rows=()) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "stock_code",
            "action",
            "consumer_subindustry",
            "reason",
            "effective_from",
            "effective_to",
        ],
    )


def _build(**changes) -> pd.DataFrame:
    frames = {
        "assets": _assets(),
        "statuses": _statuses(),
        "liquidity": _liquidity(),
        "industries": _industries(),
        "industry_rules": _industry_rules(),
        "asset_overrides": _overrides(),
        "config": ConsumerOversoldConfig(trade_date=TRADE_DATE),
    }
    frames.update(changes)
    return build_consumer_universe_from_frames(**frames)


def test_universe_includes_terminal_consumer_examples_and_excludes_auto_parts():
    result = _build()

    included = set(result.loc[result["included"], "stock_code"])
    by_code = result.set_index("stock_code")

    assert {"601888", "000759", "601127", "600418"} <= included
    assert by_code.loc["601888", "consumer_subindustry"] == "retail_duty_free"
    assert by_code.loc["601127", "consumer_subindustry"] == "auto_oem"
    assert by_code.loc["000887", "exclude_reasons"] == "not_terminal_consumer"


def test_universe_applies_all_market_gates_and_keeps_every_asset():
    result = _build()
    by_code = result.set_index("stock_code")

    assert len(result) == len(_assets())
    assert by_code.loc["600001", "exclude_reasons"] == "name_risk_flag|st_or_delisting_risk"
    assert by_code.loc["600002", "exclude_reasons"] == "listed_less_than_365_days"
    assert by_code.loc["600003", "exclude_reasons"] == "low_liquidity"
    assert by_code.loc["600004", "exclude_reasons"] == "suspended"
    assert by_code.loc["600005", "exclude_reasons"] == "missing_industry"
    assert "not_terminal_consumer" not in by_code.loc["600005", "exclude_reasons"]
    assert not by_code.loc[["600001", "600002", "600003", "600004", "600005"], "included"].any()


@pytest.mark.parametrize(
    ("avg_turnover_amount", "included", "exclude_reasons"),
    [
        (691_266_560.0, True, ""),
        (691_266.56, False, "low_liquidity"),
    ],
)
def test_liquidity_gate_compares_turnover_in_yuan(
    avg_turnover_amount, included, exclude_reasons
):
    liquidity = _liquidity()
    liquidity.loc[liquidity["asset_id"].eq("a1"), "avg_turnover_amount"] = avg_turnover_amount

    row = _build(liquidity=liquidity).set_index("stock_code").loc["601888"]

    assert bool(row["included"]) is included
    assert row["exclude_reasons"] == exclude_reasons


@pytest.mark.parametrize(
    ("industry_name", "expected_subindustry"),
    [
        ("酒、饮料和精制茶制造业", "food_beverage"),
        ("食品制造业", "food_beverage"),
        ("农副食品加工业", "food_beverage"),
        ("零售业", "retail_duty_free"),
        ("住宿业", "tourism_hospitality"),
        ("餐饮业", "tourism_hospitality"),
        ("文化艺术业", "tourism_hospitality"),
        ("广播、电视、电影和录音制作业", "tourism_hospitality"),
        ("纺织服装、服饰业", "textile_apparel"),
        ("皮革、毛皮、羽毛及其制品和制鞋业", "textile_apparel"),
        ("家具制造业", "home_leisure"),
        ("文教、工美、体育和娱乐用品制造业", "home_leisure"),
        ("新闻和出版业", "home_leisure"),
    ],
)
def test_real_csrc_terminal_consumer_industries_are_included(
    industry_name, expected_subindustry
):
    industries = _industries()
    industries.loc[industries["asset_id"].eq("a1"), ["industry_system", "industry_name"]] = [
        "csrc",
        industry_name,
    ]
    rules = pd.read_csv(INDUSTRY_RULES_PATH)

    row = _build(industries=industries, industry_rules=rules).set_index("stock_code").loc["601888"]

    assert row["included"]
    assert row["consumer_subindustry"] == expected_subindustry


@pytest.mark.parametrize(
    ("company_name", "industry_name"),
    [
        ("汽车整车样例", "汽车制造业"),
        ("批发样例", "批发业"),
        ("中国中免", "商务服务业"),
        ("公共设施样例", "公共设施管理业"),
        ("纺织B2B样例", "纺织业"),
    ],
)
def test_broad_csrc_industries_default_to_not_terminal_consumer(
    company_name, industry_name
):
    assets = _assets()
    assets.loc[assets["asset_id"].eq("a1"), "name"] = company_name
    industries = _industries()
    industries.loc[industries["asset_id"].eq("a1"), ["industry_system", "industry_name"]] = [
        "csrc",
        industry_name,
    ]
    rules = pd.read_csv(INDUSTRY_RULES_PATH)

    row = _build(assets=assets, industries=industries, industry_rules=rules).set_index("stock_code").loc["601888"]

    assert not row["included"]
    assert row["exclude_reasons"] == "not_terminal_consumer"


def test_delisting_risk_excludes_stock_without_st_flag():
    statuses = _statuses()
    target = statuses["asset_id"].eq("a1")
    statuses.loc[target, "is_st"] = False
    statuses.loc[target, "is_delisting_risk"] = True

    row = _build(statuses=statuses).set_index("stock_code").loc["601888"]

    assert not row["included"]
    assert row["exclude_reasons"] == "st_or_delisting_risk"


@pytest.mark.parametrize(
    "name",
    ["ST样例", " *ST 样例 ", "s*st样例", "SST样例", "退市样例", "样例退"],
)
def test_name_risk_flag_excludes_even_when_status_source_is_false(name):
    assets = _assets()
    assets.loc[assets["asset_id"].eq("a1"), "name"] = name

    row = _build(assets=assets).set_index("stock_code").loc["601888"]

    assert not row["included"]
    assert row["exclude_reasons"] == "name_risk_flag"


@pytest.mark.parametrize("name", ["XD中国中免", "XR 中国中免", "dr中国中免"])
def test_normal_corporate_action_name_prefix_is_not_treated_as_risk(name):
    assets = _assets()
    assets.loc[assets["asset_id"].eq("a1"), "name"] = name

    row = _build(assets=assets).set_index("stock_code").loc["601888"]

    assert row["included"]
    assert row["exclude_reasons"] == ""


@pytest.mark.parametrize("name", ["XD*ST样例", "XR ST样例", "drs*st样例"])
def test_corporate_action_prefix_does_not_hide_st_name(name):
    assets = _assets()
    assets.loc[assets["asset_id"].eq("a1"), "name"] = name

    row = _build(assets=assets).set_index("stock_code").loc["601888"]

    assert not row["included"]
    assert row["exclude_reasons"] == "name_risk_flag"


@pytest.mark.parametrize("false_value", [False, np.bool_(False), 0, "false", " FALSE ", "0"])
def test_status_false_values_do_not_trigger_market_gate(false_value):
    statuses = _statuses().astype(
        {"is_st": "object", "is_delisting_risk": "object", "is_suspended": "object"}
    )
    target = statuses["asset_id"].eq("a1")
    statuses.loc[target, ["is_st", "is_delisting_risk", "is_suspended"]] = false_value

    row = _build(statuses=statuses).set_index("stock_code").loc["601888"]

    assert row["included"]
    assert row["exclude_reasons"] == ""


@pytest.mark.parametrize("true_value", [True, np.bool_(True), 1, "true", " TRUE ", "1"])
def test_status_true_values_trigger_market_gate(true_value):
    statuses = _statuses().astype({"is_suspended": "object"})
    target = statuses["asset_id"].eq("a1")
    statuses.loc[target, "is_suspended"] = true_value

    row = _build(statuses=statuses).set_index("stock_code").loc["601888"]

    assert not row["included"]
    assert row["exclude_reasons"] == "suspended"


@pytest.mark.parametrize("invalid_value", [pd.NA, np.nan, 2, "yes"])
def test_invalid_status_value_raises_with_field_and_asset(invalid_value):
    statuses = _statuses().astype({"is_st": "object"})
    statuses.loc[statuses["asset_id"].eq("a1"), "is_st"] = invalid_value

    with pytest.raises(ValueError, match=r"is_st.*a1"):
        _build(statuses=statuses)


def test_invalid_status_value_is_not_hidden_by_a_later_duplicate_row():
    statuses = _statuses()
    invalid = statuses.loc[statuses["asset_id"].eq("a1")].astype({"is_st": "object"})
    invalid.loc[:, "is_st"] = "unknown"
    statuses = pd.concat([invalid, statuses], ignore_index=True)

    with pytest.raises(ValueError, match=r"is_st.*a1"):
        _build(statuses=statuses)


@pytest.mark.parametrize("list_date", ["", None, "not-a-date"])
def test_unknown_or_invalid_list_date_is_conservatively_excluded(list_date):
    assets = _assets()
    assets.loc[assets["stock_code"].eq("601888"), "list_date"] = list_date

    row = _build(assets=assets).set_index("stock_code").loc["601888"]

    assert not row["included"]
    assert row["exclude_reasons"] == "listed_less_than_365_days"


def test_override_include_and_exclude_take_precedence_when_active():
    overrides = _overrides(
        [
            ("000887", "include", "direct_consumer_brand", "manual_include", "2026-01-01", "2027-01-01"),
            ("601888", "exclude", "", "manual_exclude", "", ""),
        ]
    )

    by_code = _build(asset_overrides=overrides).set_index("stock_code")

    assert by_code.loc["000887", "included"]
    assert by_code.loc["000887", "consumer_subindustry"] == "direct_consumer_brand"
    assert by_code.loc["000887", "include_reasons"] == "manual_include"
    assert not by_code.loc["601888", "included"]
    assert by_code.loc["601888", "exclude_reasons"] == "manual_exclude"


def test_curated_override_file_contains_only_audited_terminal_consumer_decisions():
    overrides = pd.read_csv(ASSET_OVERRIDES_PATH, dtype={"stock_code": "string"})
    expected_auto = {
        "000550", "000572", "000625", "000800", "000868", "000951", "000957",
        "000980", "002594", "600006", "600066", "600104", "600166", "600303",
        "600375", "600418", "600686", "600733", "601127", "601238", "601633",
        "000913", "600099", "603129", "603766",
    }

    audited_consumer = {
        "000501", "000596", "001330", "002187", "002910", "002991", "003016",
        "300673", "301061", "301078", "600702", "600859", "601116", "601595",
        "601888", "603214", "603801", "605089", "605338", "605499", "605567",
    }
    assert set(overrides["stock_code"]) == expected_auto | audited_consumer | {
        "300973",
        "301011",
        "603079",
    }
    assert "601777" not in set(overrides["stock_code"])
    included = overrides.loc[overrides["action"].eq("include")]
    excluded = overrides.loc[overrides["action"].eq("exclude")]
    assert included["reason"].eq("terminal_consumer_brand_audit").all()
    assert set(included.loc[included["stock_code"].isin(expected_auto), "consumer_subindustry"]) == {"auto_oem"}
    assert included.loc[included["stock_code"].eq("601888"), "consumer_subindustry"].item() == "retail_duty_free"
    assert set(map(tuple, excluded[["stock_code", "reason"]].to_numpy())) == {
        ("300973", "b2b_bakery_ingredient_supplier_audit"),
        ("301011", "b2b_amusement_equipment_audit"),
        ("603079", "b2b_ingredient_supplier_audit"),
    }


def test_curated_overrides_include_oems_and_duty_free_but_not_auto_parts():
    overrides = pd.read_csv(ASSET_OVERRIDES_PATH, dtype={"stock_code": "string"})

    by_code = _build(asset_overrides=overrides).set_index("stock_code")

    for code in ("601127", "600418", "601888"):
        assert by_code.loc[code, "included"]
        assert by_code.loc[code, "include_reasons"] == "terminal_consumer_brand_audit"
    assert not by_code.loc["000887", "included"]
    assert by_code.loc["000887", "exclude_reasons"] == "not_terminal_consumer"


def test_curated_override_excludes_shengda_b2b_ingredient_supplier():
    overrides = pd.read_csv(ASSET_OVERRIDES_PATH, dtype={"stock_code": "string"})
    assets = pd.concat(
        [
            _assets(),
            pd.DataFrame(
                [["a11", "603079", "圣达生物", "2019-08-23"]],
                columns=_assets().columns,
            ),
        ],
        ignore_index=True,
    )
    statuses = pd.concat(
        [
            _statuses(),
            pd.DataFrame(
                [["a11", False, False, False]],
                columns=_statuses().columns,
            ),
        ],
        ignore_index=True,
    )
    liquidity = pd.concat(
        [
            _liquidity(),
            pd.DataFrame([["a11", 100_000_000.0]], columns=_liquidity().columns),
        ],
        ignore_index=True,
    )
    industries = pd.concat(
        [
            _industries(),
            pd.DataFrame([["a11", "申万", "食品"]], columns=_industries().columns),
        ],
        ignore_index=True,
    )

    row = _build(
        assets=assets,
        statuses=statuses,
        liquidity=liquidity,
        industries=industries,
        asset_overrides=overrides,
    ).set_index("stock_code").loc["603079"]

    assert not row["included"]
    assert row["exclude_reasons"] == "b2b_ingredient_supplier_audit"


def test_actual_candidate_business_model_audits_are_explicit():
    overrides = pd.read_csv(ASSET_OVERRIDES_PATH, dtype={"stock_code": "string"})
    by_code = overrides.set_index("stock_code")

    assert by_code.loc["300973", ["action", "reason"]].tolist() == [
        "exclude",
        "b2b_bakery_ingredient_supplier_audit",
    ]
    assert by_code.loc["301011", ["action", "reason"]].tolist() == [
        "exclude",
        "b2b_amusement_equipment_audit",
    ]
    for code in {
        "002187",
        "301078",
        "003016",
        "605567",
        "001330",
        "002910",
        "605499",
        "603801",
        "601595",
        "605338",
        "002991",
        "605089",
        "000501",
        "301061",
        "300673",
        "000596",
        "601116",
        "600702",
        "600859",
        "603214",
    }:
        assert by_code.loc[code, "action"] == "include"
        assert by_code.loc[code, "reason"] == "terminal_consumer_brand_audit"


def test_numeric_stock_codes_from_csv_are_zero_padded_for_override_matching(tmp_path):
    override_path = tmp_path / "overrides.csv"
    override_path.write_text(
        "stock_code,action,consumer_subindustry,reason,effective_from,effective_to\n"
        "000887,include,direct_consumer_brand,csv_override,2026-01-01,2027-01-01\n",
        encoding="utf-8",
    )
    overrides = pd.read_csv(override_path)
    assets = _assets().astype({"stock_code": "object"})
    assets.loc[assets["stock_code"].eq("000887"), "stock_code"] = 887

    by_code = _build(assets=assets, asset_overrides=overrides).set_index("stock_code")

    assert "000887" in by_code.index
    assert by_code.loc["000887", "included"]
    assert by_code.loc["000887", "include_reasons"] == "csv_override"


def test_override_csv_with_numeric_and_empty_stock_code_is_rejected(tmp_path):
    override_path = tmp_path / "mixed_overrides.csv"
    override_path.write_text(
        "stock_code,action,consumer_subindustry,reason,effective_from,effective_to\n"
        "000887,include,direct_consumer_brand,valid_row,2026-01-01,2027-01-01\n"
        ",exclude,,missing_code,2026-01-01,2027-01-01\n",
        encoding="utf-8",
    )
    overrides = pd.read_csv(override_path)

    assert overrides["stock_code"].dtype == np.dtype("float64")
    assert overrides.loc[0, "stock_code"] == 887.0
    with pytest.raises(ValueError, match="stock_code"):
        _build(asset_overrides=overrides)


def test_integral_float_stock_code_from_mixed_csv_normalizes_after_invalid_row_removed(tmp_path):
    override_path = tmp_path / "mixed_overrides.csv"
    override_path.write_text(
        "stock_code,action,consumer_subindustry,reason,effective_from,effective_to\n"
        "000887,include,direct_consumer_brand,float_code,2026-01-01,2027-01-01\n"
        ",exclude,,missing_code,2026-01-01,2027-01-01\n",
        encoding="utf-8",
    )
    overrides = pd.read_csv(override_path).dropna(subset=["stock_code"])
    assets = _assets().astype({"stock_code": "object"})
    assets.loc[assets["stock_code"].eq("000887"), "stock_code"] = 887.0

    by_code = _build(assets=assets, asset_overrides=overrides).set_index("stock_code")

    assert by_code.loc["000887", "included"]
    assert by_code.loc["000887", "include_reasons"] == "float_code"


@pytest.mark.parametrize("invalid_code", [887.5, np.inf, -887, "887.0", "ABC887"])
def test_invalid_asset_stock_code_is_rejected_without_truncation(invalid_code):
    assets = _assets().astype({"stock_code": "object"})
    assets.loc[assets.index[0], "stock_code"] = invalid_code

    with pytest.raises(ValueError, match="stock_code"):
        _build(assets=assets)


@pytest.mark.parametrize("invalid_code", ["", np.nan, 887.5, np.inf, -887, "887.0", "ABC887"])
def test_invalid_override_stock_code_is_rejected_without_truncation(invalid_code):
    overrides = _overrides(
        [(invalid_code, "exclude", "", "invalid_code", "2026-01-01", "2027-01-01")]
    )

    with pytest.raises(ValueError, match="stock_code"):
        _build(asset_overrides=overrides)


def test_override_effective_interval_is_left_closed_and_right_open():
    base = ("000887", "include", "direct_consumer_brand", "manual_include")

    before = _overrides([base + ("2026-07-30", "")])
    at_end = _overrides([base + ("2026-01-01", TRADE_DATE)])
    active = _overrides([base + (TRADE_DATE, "2026-07-30")])

    assert _build(asset_overrides=before).set_index("stock_code").loc["000887", "exclude_reasons"] == "not_terminal_consumer"
    assert _build(asset_overrides=at_end).set_index("stock_code").loc["000887", "exclude_reasons"] == "not_terminal_consumer"
    assert _build(asset_overrides=active).set_index("stock_code").loc["000887", "included"]


def test_industry_rules_use_priority_system_and_normalized_regex_search():
    rules = _industry_rules()
    rules = pd.concat(
        [
            pd.DataFrame(
                [(1, "中信", "旅游\\s*零售", "wrong_system", "exclude", "wrong_system_reason")],
                columns=rules.columns,
            ),
            pd.DataFrame(
                [(5, "申万", "旅游\\s*零售", "", "exclude", "priority_exclude")],
                columns=rules.columns,
            ),
            rules,
        ],
        ignore_index=True,
    )
    industries = _industries()
    industries.loc[industries["asset_id"].eq("a1"), "industry_name"] = " 旅 游 零 售 免 税 "

    by_code = _build(industry_rules=rules, industries=industries).set_index("stock_code")

    assert by_code.loc["601888", "exclude_reasons"] == "priority_exclude"


def test_reasons_are_stably_sorted_and_deduplicated():
    statuses = _statuses()
    statuses.loc[statuses["asset_id"].eq("a6"), "is_delisting_risk"] = True
    statuses.loc[statuses["asset_id"].eq("a6"), "is_suspended"] = True
    liquidity = _liquidity()
    liquidity.loc[liquidity["asset_id"].eq("a6"), "avg_turnover_amount"] = 1.0
    config = replace(ConsumerOversoldConfig(trade_date=TRADE_DATE), min_listed_days=20_000)

    row = _build(statuses=statuses, liquidity=liquidity, config=config).set_index("stock_code").loc["600001"]

    assert row["include_reasons"] == "terminal_consumer_industry"
    assert row["exclude_reasons"] == (
        "listed_less_than_365_days|low_liquidity|name_risk_flag|"
        "st_or_delisting_risk|suspended"
    )


@pytest.mark.parametrize(
    ("frame_name", "missing_column"),
    [
        ("assets", "stock_code"),
        ("statuses", "is_suspended"),
        ("liquidity", "avg_turnover_amount"),
        ("industries", "industry_name"),
        ("industry_rules", "priority"),
        ("asset_overrides", "effective_to"),
    ],
)
def test_missing_input_columns_raise_value_error_with_column_name(frame_name, missing_column):
    frames = {
        "assets": _assets(),
        "statuses": _statuses(),
        "liquidity": _liquidity(),
        "industries": _industries(),
        "industry_rules": _industry_rules(),
        "asset_overrides": _overrides(),
    }
    frames[frame_name] = frames[frame_name].drop(columns=[missing_column])

    with pytest.raises(ValueError, match=missing_column):
        _build(**{frame_name: frames[frame_name]})


def test_invalid_override_actions_and_missing_include_subindustry_are_rejected():
    with pytest.raises(ValueError, match="action"):
        _build(asset_overrides=_overrides([("601888", "keep", "retail", "bad", "", "")]))

    with pytest.raises(ValueError, match="consumer_subindustry"):
        _build(asset_overrides=_overrides([("601888", "include", "", "bad", "", "")]))


@pytest.mark.parametrize("action", ["include", "exclude"])
def test_override_reason_must_be_non_empty(action):
    subindustry = "retail_duty_free" if action == "include" else ""

    with pytest.raises(ValueError, match="reason"):
        _build(asset_overrides=_overrides([("601888", action, subindustry, "  ", "", "")]))


@pytest.mark.parametrize(
    ("column", "value", "match"),
    [
        ("priority", np.nan, "priority"),
        ("priority", "high", "priority"),
        ("action", "incldue", "action"),
        ("industry_name_pattern", "", "industry_name_pattern"),
        ("industry_name_pattern", "[", "industry_name_pattern"),
        ("reason", " ", "reason"),
        ("industry_system", "", "industry_system"),
    ],
)
def test_invalid_industry_rule_configuration_is_rejected(column, value, match):
    rules = _industry_rules().astype({column: "object"})
    rules.loc[rules.index[0], column] = value

    with pytest.raises(ValueError, match=match):
        _build(industry_rules=rules)


def test_industry_include_rule_requires_subindustry():
    rules = _industry_rules()
    rules.loc[rules["action"].eq("include"), "consumer_subindustry"] = ""

    with pytest.raises(ValueError, match="consumer_subindustry"):
        _build(industry_rules=rules)


@pytest.mark.parametrize(
    ("effective_from", "effective_to", "match"),
    [
        ("2026-02-30", "", "effective_from"),
        ("", "2026/12/31", "effective_to"),
        ("2026-07-29", "2026-07-29", "effective_to"),
        ("2026-07-30", "2026-07-29", "effective_to"),
    ],
)
def test_invalid_override_date_configuration_is_rejected(effective_from, effective_to, match):
    overrides = _overrides(
        [("601888", "exclude", "", "date_check", effective_from, effective_to)]
    )

    with pytest.raises(ValueError, match=match):
        _build(asset_overrides=overrides)


def test_multiple_active_overrides_for_normalized_stock_code_are_rejected():
    overrides = _overrides(
        [
            ("000887", "include", "direct_consumer_brand", "first", "2026-01-01", ""),
            (887, "exclude", "", "second", "", "2027-01-01"),
        ]
    )

    with pytest.raises(ValueError, match=r"multiple active overrides.*000887"):
        _build(asset_overrides=overrides)


def test_empty_assets_return_stable_columns():
    empty_assets = _assets().iloc[0:0]
    result = _build(assets=empty_assets)

    assert result.empty
    assert result.columns.tolist() == [
        "asset_id",
        "stock_code",
        "name",
        "list_date",
        "industry_system",
        "industry_name",
        "consumer_subindustry",
        "included",
        "include_reasons",
        "exclude_reasons",
    ]
