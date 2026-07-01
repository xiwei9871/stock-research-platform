from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_valuation_source_adapter.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_valuation_source_adapter", path)
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


def _sample_valuation_source() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "asset_id": "CN:SZ:000001",
                "data_available_asof_date": "2025-01-02",
                "market_cap": 100.0,
                "valuation_percentile": 0.20,
            },
            {
                "trade_date": "2026-06-12",
                "asset_id": "CN:SZ:000001",
                "data_available_asof_date": "2026-06-12",
                "market_cap": 120.0,
                "valuation_percentile": 0.35,
            },
        ]
    )


def test_source_inventory_contains_valuation_categories_or_missing(tmp_path: Path) -> None:
    module = _load_module()

    inventory = module.build_valuation_source_inventory(tmp_path, candidate_paths=[])

    source_types = set(inventory["source_type"])
    assert {"daily_basic", "valuation_factor", "market_cap_factor", "derived_factor"}.issubset(source_types)
    assert set(inventory["existing_in_project"]) == {"source_missing"}


def test_structured_output_contains_required_fields_and_research_scores() -> None:
    module = _load_module()

    structured = module.build_structured_valuations(_sample_watchlist(), _sample_valuation_source())

    assert module.STRUCTURED_COLUMNS == list(structured.columns)
    assert len(structured) == 1
    assert structured["source_type"].iloc[0] == "valuation"
    assert structured["market_cap"].iloc[0] == 120.0
    assert structured["valuation_quality_score"].iloc[0] > 0
    assert "target_price" not in structured.columns
    assert "entry_signal" not in structured.columns


def test_structured_output_enforces_pit_dates() -> None:
    module = _load_module()

    structured = module.build_structured_valuations(_sample_watchlist(), _sample_valuation_source())
    trade = pd.to_datetime(structured["trade_date"])
    as_of = pd.to_datetime(structured["as_of_date"])

    assert as_of.le(trade).all()
    assert int(structured["lookahead_violation"].sum()) == 0


def test_future_valuation_rows_are_excluded() -> None:
    module = _load_module()
    source = _sample_valuation_source()
    source.loc[1, "trade_date"] = "2026-07-01"
    source.loc[1, "data_available_asof_date"] = "2026-07-01"

    structured = module.build_structured_valuations(_sample_watchlist(), source)

    assert structured["trade_date"].iloc[0] == "2026-06-29"
    assert structured["market_cap"].iloc[0] == 100.0


def test_negative_pe_is_not_classified_as_low_valuation() -> None:
    module = _load_module()
    row = pd.Series({"pe_ttm": -8.0, "valuation_position_score": 0.9, "valuation_quality_score": 0.8})

    assert module.classify_valuation_level(row) == "valuation_loss_making_or_not_meaningful"


def test_missing_fields_use_neutral_fallback_not_point_six_penalty() -> None:
    module = _load_module()
    source = _sample_valuation_source().drop(columns=["valuation_percentile"])

    structured = module.build_structured_valuations(_sample_watchlist(), source)

    assert structured["valuation_quality_score"].iloc[0] > 0
    assert "0.6" not in "|".join(structured["missing_fields"].astype(str))


def test_watchlist_patch_has_no_actionable_language() -> None:
    module = _load_module()
    structured = module.build_structured_valuations(_sample_watchlist(), _sample_valuation_source())
    coverage = module.build_valuation_asset_coverage(_sample_watchlist(), structured)

    patch = module.build_watchlist_valuation_gap_patch(_sample_watchlist(), coverage, structured)
    joined = patch.to_csv(index=False)

    assert not module.contains_actionable_trading_language(joined)
    assert set(patch["recommended_report_update"]).issubset(module.RECOMMENDED_REPORT_UPDATES)


def test_quality_audit_zero_lookahead_and_scores_are_research_only() -> None:
    module = _load_module()
    structured = module.build_structured_valuations(_sample_watchlist(), _sample_valuation_source())
    coverage = module.build_valuation_asset_coverage(_sample_watchlist(), structured)
    raw = module.build_raw_candidate_matches(_sample_watchlist(), _sample_valuation_source(), "sample", "sample_path")
    inventory = module.build_valuation_source_inventory(Path("/tmp/nonexistent"), candidate_paths=[])

    audit = module.build_valuation_quality_audit(inventory, raw, structured, coverage)
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(float(lookup["lookahead_violation_rows"])) == 0
    assert "position_size" not in structured.columns
    assert "valuation_position_score" in structured.columns


def test_report_mentions_untracked_strategy_status_without_actionable_language() -> None:
    module = _load_module()
    text = module.render_main_report(
        inventory=pd.DataFrame(
            {
                "source_name": ["sample"],
                "source_type": ["market_cap_factor"],
                "existing_in_project": [True],
                "pit_ready": [True],
                "quality_risk": ["derived"],
            }
        ),
        coverage=pd.DataFrame({"asset_id": ["A"], "coverage_status": ["covered"]}),
        field_audit=pd.DataFrame({"field_name": ["market_cap"], "coverage_ratio": [1.0]}),
        patch=pd.DataFrame({"new_valuation_support": [True], "still_missing_valuation": [False]}),
        quality_audit=pd.DataFrame({"metric": ["lookahead_violation_rows"], "value": [0], "note": [""]}),
        git_info={
            "repo_root": "/repo",
            "formal_strategy_status": "?? src/stock_research/tech_bottleneck_v1.py",
            "formal_strategy_ls_files": "",
            "formal_strategy_stat": "untracked",
        },
        scanned_paths=["outputs/research/midtrend_pit_fundamental_features_20250101_20260612/midtrend_pit_fundamental_features.csv"],
    )

    assert "untracked" in text
    assert not module.contains_actionable_trading_language(text)
