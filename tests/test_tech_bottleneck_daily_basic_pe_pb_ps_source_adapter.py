from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_daily_basic_pe_pb_ps_source_adapter.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_daily_basic_pe_pb_ps_source_adapter", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _watchlist() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "admission_variant": "standard_research_watchlist",
                "asset_id": "CN:SZ:000001",
                "symbol": "000001",
                "name": "样本A",
                "first_admission_date": "2026-06-29",
            },
            {
                "admission_variant": "standard_research_watchlist",
                "asset_id": "CN:SH:600000",
                "symbol": "600000",
                "name": "样本B",
                "first_admission_date": "2026-06-29",
            },
        ]
    )


def _daily_basic() -> pd.DataFrame:
    rows = []
    for idx, trade_date in enumerate(pd.date_range("2025-01-02", "2026-06-29", freq="30D")):
        rows.append(
            {
                "ts_code": "000001.SZ",
                "trade_date": trade_date.strftime("%Y%m%d"),
                "pe": 9 + idx,
                "pe_ttm": 10 + idx,
                "pb": 0.9 + idx / 20,
                "ps": 1.0 + idx / 10,
                "ps_ttm": 1.1 + idx / 10,
                "total_mv": 100000 + idx * 1000,
                "circ_mv": 90000 + idx * 1000,
            }
        )
        rows.append(
            {
                "ts_code": "600000.SH",
                "trade_date": trade_date.strftime("%Y%m%d"),
                "pe": -2.0 if idx == 0 else 20 + idx,
                "pe_ttm": -3.0 if idx == 0 else 21 + idx,
                "pb": 1.5 + idx / 10,
                "ps": 2.0 + idx / 10,
                "ps_ttm": 2.1 + idx / 10,
                "total_mv": 200000 + idx * 1000,
                "circ_mv": 180000 + idx * 1000,
            }
        )
    rows.append(
        {
            "ts_code": "000001.SZ",
            "trade_date": "20260701",
            "pe": 99,
            "pe_ttm": 99,
            "pb": 99,
            "ps": 99,
            "ps_ttm": 99,
            "total_mv": 999999,
            "circ_mv": 999999,
        }
    )
    return pd.DataFrame(rows)


def _stock_basic() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ts_code": "000001.SZ", "symbol": "000001", "name": "样本A", "industry": "行业A", "list_date": "20100101"},
            {"ts_code": "600000.SH", "symbol": "600000", "name": "样本B", "industry": "行业A", "list_date": "20100101"},
        ]
    )


def test_source_inventory_contains_daily_basic_stock_basic_or_missing(tmp_path: Path) -> None:
    module = _load_module()

    inventory = module.build_daily_basic_source_inventory(tmp_path, daily_basic_paths=[], stock_basic_paths=[])

    source_types = set(inventory["source_type"])
    assert {"tushare_daily_basic", "tushare_stock_basic", "akshare_lg_indicator", "derived_market_cap_only"}.issubset(source_types)
    assert "source_missing" in set(inventory["source_type"]) or "source_missing" in set(inventory["existing_in_project"])


def test_asset_id_to_ts_code_mapping_is_exchange_safe() -> None:
    module = _load_module()

    assert module.asset_id_to_ts_code("CN:SZ:000001") == "000001.SZ"
    assert module.asset_id_to_ts_code("CN:SH:600000") == "600000.SH"
    assert module.ts_code_to_asset_id("688001.SH") == "CN:SH:688001"


def test_structured_output_contains_required_fields_and_enforces_pit() -> None:
    module = _load_module()

    structured = module.build_structured_daily_basic(_watchlist(), _daily_basic())

    assert module.STRUCTURED_COLUMNS == list(structured.columns)
    assert len(structured) == 2
    assert structured["source_type"].eq("tushare_daily_basic").all()
    assert pd.to_datetime(structured["daily_basic_trade_date"]).le(pd.to_datetime(structured["research_trade_date"])).all()
    assert int(structured["lookahead_violation"].sum()) == 0
    assert structured["pe_ttm"].max() < 99
    assert "entry_signal" not in structured.columns


def test_historical_percentiles_use_only_pit_history() -> None:
    module = _load_module()
    watchlist = _watchlist()
    daily_basic = _daily_basic()
    structured = module.build_structured_daily_basic(watchlist, daily_basic)

    percentiles = module.build_daily_basic_percentiles(watchlist, daily_basic, structured)

    assert module.PERCENTILE_COLUMNS == list(percentiles.columns)
    assert len(percentiles) == 2
    assert percentiles["history_window_days_available"].min() > 0
    assert percentiles["pe_ttm_percentile_1y"].dropna().between(0, 1).all()
    assert percentiles["pe_ttm"].max() < 99


def test_industry_outputs_use_stock_basic_mapping_and_peer_counts() -> None:
    module = _load_module()
    watchlist = _watchlist()
    daily_basic = _daily_basic()
    structured = module.build_structured_daily_basic(watchlist, daily_basic)

    industry = module.build_daily_basic_industry_outputs(watchlist, daily_basic, _stock_basic(), structured)

    assert module.INDUSTRY_COLUMNS == list(industry.columns)
    assert industry["industry"].eq("行业A").all()
    assert industry["industry_peer_count"].min() == 2
    assert industry["pb_industry_percentile"].dropna().between(0, 1).all()


def test_negative_or_missing_pe_is_not_interpreted_as_low_context() -> None:
    module = _load_module()

    assert module.classify_pe_context(-3.0, 0.1) == "valuation_loss_making_or_not_meaningful"
    assert module.classify_pe_context(None, 0.1) == "valuation_missing"


def test_missing_fields_do_not_use_point_six_penalty() -> None:
    module = _load_module()
    daily_basic = _daily_basic().drop(columns=["ps_ttm"])

    structured = module.build_structured_daily_basic(_watchlist(), daily_basic)

    assert "ps_ttm" in "|".join(structured["missing_fields"].astype(str))
    assert "0.6" not in structured.to_csv(index=False)


def test_empty_local_source_generates_fetch_plan() -> None:
    module = _load_module()

    plan = module.build_daily_basic_fetch_plan(_watchlist())

    assert not plan.empty
    assert module.FETCH_PLAN_COLUMNS == list(plan.columns)
    assert plan["requires_token"].all()
    assert set(plan["human_action_required"]) == {True}


def test_watchlist_patch_and_report_have_no_actionable_language() -> None:
    module = _load_module()
    watchlist = _watchlist()
    daily_basic = _daily_basic()
    structured = module.build_structured_daily_basic(watchlist, daily_basic)
    percentiles = module.build_daily_basic_percentiles(watchlist, daily_basic, structured)
    industry = module.build_daily_basic_industry_outputs(watchlist, daily_basic, _stock_basic(), structured)
    coverage = module.build_daily_basic_asset_coverage(watchlist, daily_basic, structured, percentiles, industry)

    patch = module.build_watchlist_daily_basic_valuation_gap_patch(watchlist, coverage, structured, percentiles, industry)
    report = module.render_main_report(
        inventory=module.build_daily_basic_source_inventory(Path("/tmp/none"), daily_basic_paths=[], stock_basic_paths=[]),
        fetch_plan=module.build_daily_basic_fetch_plan(watchlist),
        structured=structured,
        percentiles=percentiles,
        industry=industry,
        coverage=coverage,
        field_audit=module.build_daily_basic_field_coverage_audit(structured, percentiles, industry),
        patch=patch,
        quality_audit=module.build_daily_basic_quality_audit(
            module.build_daily_basic_source_inventory(Path("/tmp/none"), daily_basic_paths=[], stock_basic_paths=[]),
            module.build_daily_basic_fetch_plan(watchlist),
            module.build_daily_basic_raw_candidate_matches(watchlist, daily_basic),
            structured,
            percentiles,
            industry,
            coverage,
        ),
        git_info={"repo_root": "/repo", "formal_strategy_status": "untracked", "formal_strategy_stat": "untracked"},
    )

    assert not module.contains_actionable_trading_language(patch.to_csv(index=False))
    assert not module.contains_actionable_trading_language(report)
    assert set(patch["recommended_report_update"]).issubset(module.RECOMMENDED_REPORT_UPDATES)

