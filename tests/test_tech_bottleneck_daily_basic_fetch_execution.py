from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_daily_basic_fetch_execution.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_daily_basic_fetch_execution", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fetch_plan() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fetch_batch_id": "daily_basic_0001_20260629",
                "trade_date": "2026-06-29",
                "start_date": "20210630",
                "end_date": "20260629",
                "asset_scope": "standard_watchlist_plus_history",
                "target_asset_count": 2,
                "expected_rows": 4,
                "source_api": "tushare.daily_basic",
                "fields": "ts_code,trade_date,pe,pe_ttm,pb,ps,ps_ttm,total_mv,circ_mv",
                "requires_token": True,
                "estimated_calls": 1,
                "rate_limit_note": "test",
            }
        ]
    )


class FakeProClient:
    def stock_basic(self, **kwargs):
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "symbol": "000001",
                    "name": "样本A",
                    "area": "深圳",
                    "industry": "银行",
                    "market": "主板",
                    "exchange": "SZSE",
                    "list_date": "19910403",
                    "delist_date": "",
                    "is_hs": "S",
                }
            ]
        )

    def daily_basic(self, trade_date: str, fields: str | None = None):
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": trade_date,
                    "close": 10.0,
                    "turnover_rate": 1.0,
                    "turnover_rate_f": 1.1,
                    "volume_ratio": 0.9,
                    "pe": 9.0,
                    "pe_ttm": 10.0,
                    "pb": 1.2,
                    "ps": 2.0,
                    "ps_ttm": 2.1,
                    "dv_ratio": 0.5,
                    "dv_ttm": 0.6,
                    "total_share": 100,
                    "float_share": 90,
                    "free_share": 80,
                    "total_mv": 100000,
                    "circ_mv": 90000,
                }
            ]
        )


def test_fetch_execution_plan_contains_daily_basic_and_stock_basic(tmp_path: Path) -> None:
    module = _load_module()

    plan = module.build_fetch_execution_plan(_fetch_plan(), tmp_path)

    assert {"daily_basic", "stock_basic"}.issubset(set(plan["fetch_type"]))
    assert module.EXECUTION_PLAN_COLUMNS == list(plan.columns)
    assert plan["cache_target_path"].astype(str).str.contains(str(tmp_path)).all()


def test_token_unavailable_degrades_without_crashing(tmp_path: Path) -> None:
    module = _load_module()

    context = module.TokenContext(available=False, source="missing", token=None, printed=False, client_initialized=False, test_call_success=False, test_call_error="missing")
    outputs = module.execute_fetch_plan(_fetch_plan(), tmp_path, token_context=context, client_factory=lambda _token: None)

    audit = module.build_fetch_quality_audit(context, outputs.execution_plan, outputs.results, outputs.daily_manifest, outputs.stock_manifest)
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert lookup["token_available"] is False
    assert lookup["token_printed"] is False
    assert set(outputs.results["fetch_status"]) == {"token_missing"}


def test_successful_fetch_writes_cache_and_manifest(tmp_path: Path) -> None:
    module = _load_module()
    context = module.TokenContext(available=True, source="test", token="SECRET_TOKEN", printed=False, client_initialized=True, test_call_success=True, test_call_error="")

    outputs = module.execute_fetch_plan(_fetch_plan(), tmp_path, token_context=context, client_factory=lambda _token: FakeProClient())

    assert module.DAILY_MANIFEST_COLUMNS == list(outputs.daily_manifest.columns)
    assert module.STOCK_MANIFEST_COLUMNS == list(outputs.stock_manifest.columns)
    assert outputs.results["fetch_status"].isin({"success", "success_cached"}).any()
    assert outputs.daily_manifest["content_hash"].astype(str).str.len().gt(0).all()
    assert outputs.stock_manifest["content_hash"].astype(str).str.len().gt(0).all()
    for cache_path in outputs.daily_manifest["cache_path"].dropna():
        assert Path(cache_path).exists()
    for cache_path in outputs.stock_manifest["cache_path"].dropna():
        assert Path(cache_path).exists()


def test_token_value_is_not_written_to_outputs(tmp_path: Path) -> None:
    module = _load_module()
    context = module.TokenContext(available=True, source="test", token="SECRET_TOKEN", printed=False, client_initialized=True, test_call_success=True, test_call_error="")

    output_dir = tmp_path / "out"
    module.write_outputs(_fetch_plan(), output_dir, token_context=context, client_factory=lambda _token: FakeProClient())
    joined = "\n".join(path.read_text(errors="ignore") for path in output_dir.rglob("*") if path.is_file())

    assert "SECRET_TOKEN" not in joined
    assert "token_printed,false" in joined


def test_audit_contains_required_metrics_and_zero_lookahead(tmp_path: Path) -> None:
    module = _load_module()
    context = module.TokenContext(available=True, source="test", token="SECRET_TOKEN", printed=False, client_initialized=True, test_call_success=True, test_call_error="")
    outputs = module.execute_fetch_plan(_fetch_plan(), tmp_path, token_context=context, client_factory=lambda _token: FakeProClient())

    audit = module.build_fetch_quality_audit(context, outputs.execution_plan, outputs.results, outputs.daily_manifest, outputs.stock_manifest)
    metrics = set(audit["metric"])

    assert {"token_available", "token_printed", "daily_basic_success_count", "daily_basic_failed_count", "daily_basic_rate_limited_count", "lookahead_violation_rows"}.issubset(metrics)
    assert int(audit.loc[audit["metric"].eq("lookahead_violation_rows"), "value"].iloc[0]) == 0


def test_outputs_do_not_contain_actionable_language(tmp_path: Path) -> None:
    module = _load_module()
    context = module.TokenContext(available=True, source="test", token="SECRET_TOKEN", printed=False, client_initialized=True, test_call_success=True, test_call_error="")

    output_dir = tmp_path / "out"
    module.write_outputs(_fetch_plan(), output_dir, token_context=context, client_factory=lambda _token: FakeProClient())
    joined = "\n".join(path.read_text(errors="ignore") for path in output_dir.rglob("*") if path.is_file())

    assert not module.contains_actionable_trading_language(joined)

