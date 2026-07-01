from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_fundamental_source_adapter.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_fundamental_source_adapter", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample_watchlist() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"report_date": "2026-06-29", "asset_id": "CN:SZ:000001", "symbol": "000001", "name": "样本A"},
            {"report_date": "2026-06-29", "asset_id": "CN:SZ:000002", "symbol": "000002", "name": "样本B"},
        ]
    )


def _sample_fundamentals() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-06-12",
                "asset_id": "CN:SZ:000001",
                "report_period": "2026-03-31",
                "report_disclosure_date": "2026-04-28",
                "data_available_asof_date": "2026-04-28",
                "source_table": "finance.indicator_quarter|finance.income_statement|finance.balance_sheet|finance.cash_flow",
                "pit_valid_flag": True,
                "lookahead_violation_flag": False,
                "revenue_growth_yoy": 0.20,
                "profit_growth_yoy": 0.35,
                "deduct_profit_growth_yoy": 0.32,
                "gross_margin": 0.42,
                "gross_margin_yoy_change": 0.03,
                "operating_cashflow_to_profit": 1.1,
                "debt_ratio": 0.35,
                "fundamental_quality_score": 0.7,
            }
        ]
    )


def test_source_inventory_includes_fundamental_categories_or_missing(tmp_path: Path) -> None:
    module = _load_module()

    inventory = module.build_fundamental_source_inventory(tmp_path, candidate_paths=[])

    source_types = set(inventory["source_type"])
    assert {"income_statement", "balance_sheet", "cashflow_statement", "financial_indicator"}.issubset(source_types)
    assert set(inventory["existing_in_project"]) == {"source_missing"}


def test_structured_output_contains_required_fields_and_research_scores() -> None:
    module = _load_module()

    structured = module.build_structured_fundamentals(_sample_watchlist(), _sample_fundamentals())

    assert module.STRUCTURED_COLUMNS == list(structured.columns)
    assert len(structured) == 1
    assert structured["source_type"].iloc[0] == "fundamentals"
    assert structured["fundamental_recovery_score"].iloc[0] > 0.5
    assert structured["fundamental_risk_score"].iloc[0] < 0.5
    assert "target_price" not in structured.columns
    assert "entry_signal" not in structured.columns


def test_structured_output_enforces_pit_dates() -> None:
    module = _load_module()

    structured = module.build_structured_fundamentals(_sample_watchlist(), _sample_fundamentals())
    trade = pd.to_datetime(structured["trade_date"])
    financial = pd.to_datetime(structured["financial_as_of_date"])
    announcement = pd.to_datetime(structured["announcement_date"])
    as_of = pd.to_datetime(structured["as_of_date"])

    assert financial.le(trade).all()
    assert announcement.le(trade).all()
    assert as_of.le(trade).all()
    assert int(structured["lookahead_violation"].sum()) == 0


def test_lookahead_violation_is_excluded_from_structured_output() -> None:
    module = _load_module()
    fundamentals = _sample_fundamentals()
    fundamentals.loc[0, "report_disclosure_date"] = "2026-07-01"
    fundamentals.loc[0, "data_available_asof_date"] = "2026-07-01"

    structured = module.build_structured_fundamentals(_sample_watchlist(), fundamentals)

    assert structured.empty


def test_missing_fields_use_neutral_fallback_not_point_six_penalty() -> None:
    module = _load_module()
    fundamentals = _sample_fundamentals().drop(columns=["operating_cashflow_to_profit", "debt_ratio"])

    structured = module.build_structured_fundamentals(_sample_watchlist(), fundamentals)

    assert structured["cashflow_quality_score"].iloc[0] == 0.5
    assert structured["debt_risk_score"].iloc[0] == 0.5
    assert "0.6" not in "|".join(structured["missing_fields"].astype(str))


def test_watchlist_patch_has_no_actionable_language() -> None:
    module = _load_module()
    structured = module.build_structured_fundamentals(_sample_watchlist(), _sample_fundamentals())
    coverage = module.build_fundamental_asset_coverage(_sample_watchlist(), structured)

    patch = module.build_watchlist_fundamental_gap_patch(_sample_watchlist(), coverage)
    joined = patch.to_csv(index=False)

    assert not module.contains_actionable_trading_language(joined)
    assert set(patch["recommended_report_update"]).issubset(module.RECOMMENDED_REPORT_UPDATES)


def test_quality_audit_has_zero_lookahead_and_scores_are_research_only() -> None:
    module = _load_module()
    structured = module.build_structured_fundamentals(_sample_watchlist(), _sample_fundamentals())
    coverage = module.build_fundamental_asset_coverage(_sample_watchlist(), structured)
    inventory = module.build_fundamental_source_inventory(Path("/tmp/nonexistent"), candidate_paths=[])
    raw = module.build_raw_candidate_matches(_sample_watchlist(), _sample_fundamentals(), "sample_source", "sample_path")

    audit = module.build_fundamental_quality_audit(inventory, raw, structured, coverage)
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(float(lookup["lookahead_violation_rows"])) == 0
    assert "position_size" not in structured.columns
    assert "fundamental_quality_score" in structured.columns


def test_report_mentions_untracked_strategy_status_without_actionable_language() -> None:
    module = _load_module()
    text = module.render_main_report(
        inventory=pd.DataFrame(
            {
                "source_name": ["sample"],
                "source_type": ["financial_indicator"],
                "existing_in_project": [True],
                "pit_ready": [True],
                "coverage_estimate": ["sample"],
            }
        ),
        coverage=pd.DataFrame({"asset_id": ["A"], "coverage_status": ["covered"]}),
        field_audit=pd.DataFrame({"field_name": ["revenue_growth_yoy"], "coverage_ratio": [1.0]}),
        patch=pd.DataFrame({"new_fundamental_support": [True], "still_missing_fundamentals": [False]}),
        quality_audit=pd.DataFrame({"metric": ["lookahead_violation_rows"], "value": [0], "note": [""]}),
        git_info={
            "repo_root": "/repo",
            "formal_strategy_status": "?? src/stock_research/tech_bottleneck_v1.py\n?? src/stock_research/tech_bottleneck_candidates.py",
            "formal_strategy_ls_files": "",
            "formal_strategy_stat": "untracked",
        },
        scanned_paths=["outputs/research/midtrend_pit_fundamental_features_20250101_20260612/midtrend_pit_fundamental_features.csv"],
    )

    assert "untracked" in text
    assert not module.contains_actionable_trading_language(text)


def test_report_renders_high_risk_examples_from_coverage() -> None:
    module = _load_module()
    coverage = pd.DataFrame(
        {
            "asset_id": ["A"],
            "symbol": ["000001"],
            "name": ["样本A"],
            "coverage_status": ["covered"],
            "fundamental_risk_score_latest": [0.72],
        }
    )

    text = module.render_main_report(
        inventory=pd.DataFrame(
            {
                "source_name": ["sample"],
                "source_type": ["financial_indicator"],
                "existing_in_project": [True],
                "pit_ready": [True],
                "quality_risk": ["derived"],
            }
        ),
        coverage=coverage,
        field_audit=pd.DataFrame({"field_name": ["revenue_growth_yoy"], "coverage_ratio": [1.0]}),
        patch=pd.DataFrame({"new_fundamental_support": [True], "still_missing_fundamentals": [False]}),
        quality_audit=pd.DataFrame({"metric": ["lookahead_violation_rows"], "value": [0], "note": [""]}),
        git_info={"repo_root": "/repo", "formal_strategy_status": "", "formal_strategy_ls_files": "", "formal_strategy_stat": ""},
        scanned_paths=[],
    )

    assert "risk_score=0.720" in text
    assert not module.contains_actionable_trading_language(text)
