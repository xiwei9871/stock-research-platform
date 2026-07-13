from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_baostock_pe_pb_ps_source_adapter.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_baostock_pe_pb_ps_source_adapter", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _watchlist() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"admission_variant": "standard_research_watchlist", "asset_id": "CN:SH:600000", "symbol": "600000", "name": "浦发银行", "first_admission_date": "2025-01-15"},
            {"admission_variant": "standard_research_watchlist", "asset_id": "CN:SZ:002028", "symbol": "002028", "name": "思源电气", "first_admission_date": "2025-01-15"},
        ]
    )


class FakeQueryResult:
    def __init__(self, fields, rows, error_code="0", error_msg=""):
        self.fields = fields
        self.rows = rows
        self.error_code = error_code
        self.error_msg = error_msg
        self.index = 0

    def next(self):
        if self.index < len(self.rows):
            self.index += 1
            return True
        return False

    def get_row_data(self):
        return self.rows[self.index - 1]


class FakeBaoStockClient:
    __version__ = "test"

    def login(self):
        return type("LoginResult", (), {"error_code": "0", "error_msg": ""})()

    def logout(self):
        return None

    def query_history_k_data_plus(self, code, fields, start_date, end_date, frequency="d", adjustflag="3"):
        field_list = fields.split(",")
        rows = [
            ["2024-01-02", code, "10", "11", "9", "10", "1000", "2000", "1.2", "1", "0.5", "10", "1.3", "2.5", "6.1", "0"],
            ["2025-01-14", code, "10", "11", "9", "12", "1000", "2000", "1.3", "1", "0.5", "-5", "1.4", "2.8", "6.3", "0"],
            ["2025-01-15", code, "10", "11", "9", "13", "1000", "2000", "1.4", "1", "0.5", "15", "1.5", "3.0", "6.5", "0"],
        ]
        return FakeQueryResult(field_list, rows)


def test_package_missing_inventory_does_not_crash() -> None:
    module = _load_module()

    inventory = module.inspect_baostock_source(importer=lambda: (_ for _ in ()).throw(ImportError("missing")))

    assert inventory.loc[0, "package_available"] is False
    assert inventory.loc[0, "login_success"] is False
    assert "package_missing" in inventory.loc[0, "quality_risk"]


def test_asset_id_to_baostock_code_mapping() -> None:
    module = _load_module()

    assert module.asset_id_to_baostock_code("CN:SH:600000") == "sh.600000"
    assert module.asset_id_to_baostock_code("CN:SZ:002028") == "sz.002028"
    assert module.asset_id_to_baostock_code("CN:SH:688190") == "sh.688190"
    assert module.asset_id_to_baostock_code("CN:SZ:300750") == "sz.300750"


def test_structured_output_fields_and_pit(tmp_path: Path) -> None:
    module = _load_module()
    plan = module.build_baostock_fetch_plan(_watchlist(), tmp_path / "out", research_trade_date="2025-01-15", start_date="2024-01-01")
    fetch = module.fetch_baostock_history(plan, tmp_path / "out", client=FakeBaoStockClient())
    raw = module.build_raw_candidate_matches(plan, fetch)
    structured = module.build_structured_outputs(_watchlist(), raw, research_trade_date="2025-01-15")

    assert module.STRUCTURED_COLUMNS == list(structured.columns)
    assert len(structured) == 2
    assert (pd.to_datetime(structured["baostock_date"]) <= pd.to_datetime(structured["research_trade_date"])).all()
    assert int(structured["lookahead_violation"].sum()) == 0


def test_percentiles_use_only_history_not_future_and_negative_pe_not_low(tmp_path: Path) -> None:
    module = _load_module()
    plan = module.build_baostock_fetch_plan(_watchlist().head(1), tmp_path / "out", research_trade_date="2025-01-15", start_date="2024-01-01")
    fetch = module.fetch_baostock_history(plan, tmp_path / "out", client=FakeBaoStockClient())
    raw = module.build_raw_candidate_matches(plan, fetch)
    structured = module.build_structured_outputs(_watchlist().head(1), raw, research_trade_date="2025-01-15")
    percentiles = module.build_percentile_outputs(structured, raw)

    assert module.PERCENTILE_COLUMNS == list(percentiles.columns)
    assert percentiles.loc[0, "history_window_days_available"] == 3
    assert percentiles.loc[0, "pe_ttm_percentile_3y"] != "low_due_to_negative_pe"
    assert "negative_pe_not_low" in percentiles.loc[0, "missing_fields"]


def test_gap_patch_and_audit_have_no_actionable_language(tmp_path: Path) -> None:
    module = _load_module()
    plan = module.build_baostock_fetch_plan(_watchlist(), tmp_path / "out", research_trade_date="2025-01-15", start_date="2024-01-01")
    fetch = module.fetch_baostock_history(plan, tmp_path / "out", client=FakeBaoStockClient())
    raw = module.build_raw_candidate_matches(plan, fetch)
    structured = module.build_structured_outputs(_watchlist(), raw, research_trade_date="2025-01-15")
    percentiles = module.build_percentile_outputs(structured, raw)
    coverage = module.build_asset_coverage(_watchlist(), raw, percentiles)
    patch = module.build_watchlist_gap_patch(_watchlist(), structured, percentiles, coverage, pd.DataFrame())
    audit = module.build_quality_audit(module.inspect_baostock_source(client=FakeBaoStockClient()), plan, fetch, raw, structured, percentiles, coverage)

    joined = patch.to_csv(index=False) + audit.to_csv(index=False)
    assert not module.contains_actionable_trading_language(joined)
    assert int(dict(zip(audit["metric"], audit["value"]))["lookahead_violation_rows"]) == 0
