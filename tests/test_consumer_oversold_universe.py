from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from stock_research.consumer_oversold.contracts import ConsumerOversoldConfig
from stock_research.consumer_oversold.universe import build_consumer_universe_from_frames


TRADE_DATE = "2026-07-29"


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
    assert by_code.loc["600001", "exclude_reasons"] == "st_or_delisting_risk"
    assert by_code.loc["600002", "exclude_reasons"] == "listed_less_than_365_days"
    assert by_code.loc["600003", "exclude_reasons"] == "low_liquidity"
    assert by_code.loc["600004", "exclude_reasons"] == "suspended"
    assert by_code.loc["600005", "exclude_reasons"] == "missing_industry"
    assert "not_terminal_consumer" not in by_code.loc["600005", "exclude_reasons"]
    assert not by_code.loc[["600001", "600002", "600003", "600004", "600005"], "included"].any()


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
    assert row["exclude_reasons"] == "listed_less_than_365_days|low_liquidity|st_or_delisting_risk|suspended"


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
