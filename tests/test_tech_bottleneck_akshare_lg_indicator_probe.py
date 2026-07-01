from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_akshare_lg_indicator_probe_v1"


def _load_module():
    path = PROJECT_ROOT / "scripts/run_tech_bottleneck_akshare_lg_indicator_probe.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_akshare_lg_indicator_probe", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _watchlist() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "CN:SH:600000", "symbol": "600000", "name": "浦发银行", "baostock_code": "sh.600000"},
            {"asset_id": "CN:SZ:002028", "symbol": "002028", "name": "思源电气", "baostock_code": "sz.002028"},
        ]
    )


class FakeAkshareModule:
    __version__ = "fake"

    @staticmethod
    def stock_a_indicator_lg(symbol: str = "600000"):
        return pd.DataFrame(
            [
                {"trade_date": "2025-01-14", "pe": 9, "pe_ttm": 10, "pb": 1.1, "ps": 2.0, "ps_ttm": 2.1, "dv_ratio": 1, "dv_ttm": 1, "total_mv": 100},
                {"trade_date": "2025-01-15", "pe": 10, "pe_ttm": 12, "pb": 1.2, "ps": 2.2, "ps_ttm": 2.4, "dv_ratio": 1, "dv_ttm": 1, "total_mv": 105},
            ]
        )


def test_package_missing_does_not_crash() -> None:
    module = _load_module()

    inventory = module.inspect_akshare_source(importer=lambda: (_ for _ in ()).throw(ImportError("missing")))

    assert inventory.loc[0, "package_available"] is False
    assert inventory.loc[0, "function_exists"] is False
    assert "package_missing" in inventory.loc[0, "quality_risk"]


def test_target_function_missing_does_not_crash() -> None:
    module = _load_module()

    class EmptyAk:
        __version__ = "fake"

    inventory = module.inspect_akshare_source(ak_module=EmptyAk)

    assert inventory.loc[0, "package_available"] is True
    assert inventory.loc[0, "function_exists"] is False
    assert "stock" in inventory.loc[0, "notes"]


def test_probe_plan_maps_102_assets_when_using_real_input() -> None:
    module = _load_module()
    watchlist = module.load_watchlist_assets()
    plan = module.build_probe_plan(watchlist, OUTPUT_DIR, target_function="stock_a_indicator_lg")

    assert len(plan) == 102
    assert module.PROBE_PLAN_COLUMNS == list(plan.columns)
    assert plan["akshare_symbol"].astype(str).str.len().eq(6).all()


def test_structured_output_fields_and_pit(tmp_path: Path) -> None:
    module = _load_module()
    inventory = module.inspect_akshare_source(ak_module=FakeAkshareModule)
    plan = module.build_probe_plan(_watchlist(), tmp_path / "out", target_function="stock_a_indicator_lg")
    fetch = module.fetch_akshare_lg(plan, tmp_path / "out", inventory, ak_module=FakeAkshareModule)
    structured = module.build_structured_outputs(_watchlist(), fetch, research_trade_date="2025-01-15")

    assert module.STRUCTURED_COLUMNS == list(structured.columns)
    assert len(structured) == 2
    assert (pd.to_datetime(structured["akshare_trade_date"]) <= pd.to_datetime(structured["research_trade_date"])).all()
    assert int(structured["lookahead_violation"].sum()) == 0


def test_cross_validation_does_not_override_baostock_and_marks_material_review(tmp_path: Path) -> None:
    module = _load_module()
    inventory = module.inspect_akshare_source(ak_module=FakeAkshareModule)
    plan = module.build_probe_plan(_watchlist().head(1), tmp_path / "out", target_function="stock_a_indicator_lg")
    fetch = module.fetch_akshare_lg(plan, tmp_path / "out", inventory, ak_module=FakeAkshareModule)
    structured = module.build_structured_outputs(_watchlist().head(1), fetch, research_trade_date="2025-01-15")
    baostock = pd.DataFrame(
        [
            {"asset_id": "CN:SH:600000", "symbol": "600000", "name": "浦发银行", "research_trade_date": "2025-01-15", "baostock_date": "2025-01-15", "pe_ttm": 100, "pb": 8, "ps_ttm": 20, "amount": 0},
        ]
    )

    cross = module.build_cross_validation(structured, baostock)

    assert module.CROSS_VALIDATION_COLUMNS == list(cross.columns)
    assert cross.loc[0, "validation_status"] == "material_difference"
    assert cross.loc[0, "recommended_action"] == "review_discrepancy"
    assert "no_auto_override" in cross.loc[0, "discrepancy_flags"]


def test_outputs_have_no_actionable_language_and_zero_lookahead() -> None:
    module = _load_module()
    audit = pd.read_csv(OUTPUT_DIR / "akshare_lg_quality_audit.csv")
    report = (OUTPUT_DIR / "akshare_lg_indicator_probe_v1.md").read_text(encoding="utf-8")
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(lookup["lookahead violation rows"]) == 0
    assert not module.contains_actionable_trading_language(report)
    assert "无法仅靠 `git diff` 完整证明" in report
