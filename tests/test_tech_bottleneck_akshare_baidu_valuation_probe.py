from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_akshare_baidu_valuation_probe_v1"


def _load_module():
    path = PROJECT_ROOT / "scripts/run_tech_bottleneck_akshare_baidu_valuation_probe.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_akshare_baidu_valuation_probe", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _watchlist() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"asset_id": "CN:SH:600000", "symbol": "600000", "name": "浦发银行"},
            {"asset_id": "CN:SZ:002028", "symbol": "002028", "name": "思源电气"},
        ]
    )


class FakeBaiduAkshare:
    __version__ = "fake"

    @staticmethod
    def stock_zh_valuation_baidu(symbol: str = "600000", indicator: str = "总市值", period: str = "近三年"):
        values = {
            "总市值": 100.0,
            "市盈率(TTM)": 10.0,
            "市盈率(静)": 11.0,
            "市净率": 1.2,
            "市现率": 8.0,
        }
        return pd.DataFrame(
            [
                {"date": "2025-01-14", "value": values[indicator] * 0.9},
                {"date": "2025-01-15", "value": values[indicator]},
            ]
        )


def test_package_missing_does_not_crash() -> None:
    module = _load_module()

    inventory = module.inspect_baidu_source(importer=lambda: (_ for _ in ()).throw(ImportError("missing")))

    assert inventory.loc[0, "package_available"] is False
    assert inventory.loc[0, "function_exists"] is False
    assert "package_missing" in inventory.loc[0, "quality_risk"]


def test_target_function_missing_does_not_crash() -> None:
    module = _load_module()

    class EmptyAk:
        __version__ = "fake"

    inventory = module.inspect_baidu_source(ak_module=EmptyAk)

    assert inventory.loc[0, "package_available"] is True
    assert inventory.loc[0, "function_exists"] is False
    assert "valuation" in inventory.loc[0, "notes"]


def test_probe_plan_generates_102_assets_times_indicators() -> None:
    module = _load_module()
    watchlist = module.load_watchlist_assets()
    plan = module.build_probe_plan(watchlist, OUTPUT_DIR, target_function="stock_zh_valuation_baidu")

    assert len(plan) == 102 * len(module.BAIDU_INDICATORS)
    assert module.PROBE_PLAN_COLUMNS == list(plan.columns)
    assert plan["akshare_symbol"].astype(str).str.len().eq(6).all()


def test_structured_output_fields_and_pit(tmp_path: Path) -> None:
    module = _load_module()
    inventory = module.inspect_baidu_source(ak_module=FakeBaiduAkshare)
    plan = module.build_probe_plan(_watchlist(), tmp_path / "out", target_function="stock_zh_valuation_baidu")
    fetch = module.fetch_baidu_valuation(plan, tmp_path / "out", inventory, ak_module=FakeBaiduAkshare)
    structured = module.build_structured_outputs(_watchlist(), fetch, research_trade_date="2025-01-15")

    assert module.STRUCTURED_COLUMNS == list(structured.columns)
    assert len(structured) == 2
    assert (pd.to_datetime(structured["baidu_trade_date_pe_ttm"]) <= pd.to_datetime(structured["research_trade_date"])).all()
    assert int(structured["lookahead_violation"].sum()) == 0
    assert structured["baidu_ps_ttm_available"].eq(False).all()


def test_cross_validation_does_not_override_baostock_and_marks_material_review(tmp_path: Path) -> None:
    module = _load_module()
    inventory = module.inspect_baidu_source(ak_module=FakeBaiduAkshare)
    plan = module.build_probe_plan(_watchlist().head(1), tmp_path / "out", target_function="stock_zh_valuation_baidu")
    fetch = module.fetch_baidu_valuation(plan, tmp_path / "out", inventory, ak_module=FakeBaiduAkshare)
    structured = module.build_structured_outputs(_watchlist().head(1), fetch, research_trade_date="2025-01-15")
    baostock = pd.DataFrame(
        [
            {"asset_id": "CN:SH:600000", "symbol": "600000", "name": "浦发银行", "research_trade_date": "2025-01-15", "baostock_date": "2025-01-15", "pe_ttm": 100.0, "pb": 8.0, "ps_ttm": 20.0},
        ]
    )

    cross = module.build_cross_validation(structured, baostock)

    assert module.CROSS_VALIDATION_COLUMNS == list(cross.columns)
    assert cross.loc[0, "validation_status"] == "material_difference"
    assert cross.loc[0, "recommended_action"] == "review_discrepancy"
    assert "no_auto_override" in cross.loc[0, "discrepancy_flags"]


def test_outputs_have_no_actionable_language_zero_lookahead_and_no_ps_claim() -> None:
    module = _load_module()
    audit = pd.read_csv(OUTPUT_DIR / "akshare_baidu_quality_audit.csv")
    report = (OUTPUT_DIR / "akshare_baidu_valuation_probe_v1.md").read_text(encoding="utf-8")
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert int(lookup["lookahead violation rows"]) == 0
    assert int(lookup["assets with baidu_ps_ttm"]) == 0
    assert "Baidu does not validate PS/PS-TTM" in report
    assert "无法仅靠 `git diff` 完整证明" in report
    assert not module.contains_actionable_trading_language(report)
