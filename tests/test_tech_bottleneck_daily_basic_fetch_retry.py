from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_daily_basic_fetch_retry.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_daily_basic_fetch_retry", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _execution_plan() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fetch_batch_id": "stock_basic_latest",
                "fetch_type": "stock_basic",
                "trade_date": "latest",
                "source_api": "tushare.stock_basic",
                "fields": "ts_code,symbol,name,industry,list_date",
                "cache_target_path": "old/cache/tushare/stock_basic/stock_basic.csv",
                "fetch_required": True,
            },
            {
                "fetch_batch_id": "daily_basic_0001_20250115",
                "fetch_type": "daily_basic",
                "trade_date": "2025-01-15",
                "source_api": "tushare.daily_basic",
                "fields": "ts_code,trade_date,pe,pe_ttm,pb,ps,ps_ttm,total_mv,circ_mv",
                "cache_target_path": "old/cache/tushare/daily_basic/daily_basic_20250115.csv",
                "fetch_required": False,
            },
            {
                "fetch_batch_id": "daily_basic_0002_20250219",
                "fetch_type": "daily_basic",
                "trade_date": "2025-02-19",
                "source_api": "tushare.daily_basic",
                "fields": "ts_code,trade_date,pe,pe_ttm,pb,ps,ps_ttm,total_mv,circ_mv",
                "cache_target_path": "old/cache/tushare/daily_basic/daily_basic_20250219.csv",
                "fetch_required": True,
            },
        ]
    )


def _previous_cache(tmp_path: Path) -> Path:
    previous = tmp_path / "previous"
    daily = previous / "cache/tushare/daily_basic"
    daily.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20250115",
                "pe": 9,
                "pe_ttm": 10,
                "pb": 1.2,
                "ps": 2,
                "ps_ttm": 2.1,
                "total_mv": 100000,
                "circ_mv": 90000,
            }
        ]
    ).to_csv(daily / "daily_basic_20250115.csv", index=False)
    return previous


class FakeRetryClient:
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
                    "close": 10,
                    "turnover_rate": 1,
                    "turnover_rate_f": 1,
                    "volume_ratio": 1,
                    "pe": 9,
                    "pe_ttm": 10,
                    "pb": 1.2,
                    "ps": 2,
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


def test_retry_plan_contains_stock_basic_and_daily_basic_with_cached_row(tmp_path: Path) -> None:
    module = _load_module()
    previous = _previous_cache(tmp_path)

    plan = module.build_retry_plan(_execution_plan(), tmp_path / "out", previous_cache_dir=previous)

    assert {"stock_basic", "daily_basic"}.issubset(set(plan["fetch_type"]))
    assert module.RETRY_PLAN_COLUMNS == list(plan.columns)
    cached = plan[plan["trade_date"].eq("2025-01-15")].iloc[0]
    assert cached["fetch_status"] == "success_cached"
    assert cached["fetch_required"] is False


def test_existing_cache_is_reused_and_manifest_is_complete(tmp_path: Path) -> None:
    module = _load_module()
    previous = _previous_cache(tmp_path)
    context = module.TokenContext(True, "test", "SECRET_TOKEN", False, True, True, "")

    outputs = module.execute_retry(
        _execution_plan(),
        tmp_path / "out",
        previous_cache_dir=previous,
        token_context=context,
        client_factory=lambda _token: FakeRetryClient(),
        min_interval_seconds=0,
        stop_after_attempt_count=1,
    )

    assert module.DAILY_RETRY_MANIFEST_COLUMNS == list(outputs.daily_manifest.columns)
    assert len(outputs.daily_manifest) >= 1
    assert outputs.daily_manifest["content_hash"].astype(str).str.len().gt(0).all()
    assert all(Path(path).exists() for path in outputs.daily_manifest["cache_path"])


def test_token_is_not_written_to_retry_outputs(tmp_path: Path) -> None:
    module = _load_module()
    previous = _previous_cache(tmp_path)
    context = module.TokenContext(True, "test", "SECRET_TOKEN", False, True, True, "")

    output_dir = tmp_path / "out"
    module.write_outputs(
        _execution_plan(),
        output_dir,
        previous_cache_dir=previous,
        token_context=context,
        client_factory=lambda _token: FakeRetryClient(),
        min_interval_seconds=0,
        stop_after_attempt_count=1,
    )
    joined = "\n".join(path.read_text(errors="ignore") for path in output_dir.rglob("*") if path.is_file())

    assert "SECRET_TOKEN" not in joined
    assert not module.contains_actionable_trading_language(joined)


def test_audit_contains_remaining_rate_limit_and_zero_lookahead(tmp_path: Path) -> None:
    module = _load_module()
    previous = _previous_cache(tmp_path)
    context = module.TokenContext(True, "test", "SECRET_TOKEN", False, True, True, "")
    outputs = module.execute_retry(
        _execution_plan(),
        tmp_path / "out",
        previous_cache_dir=previous,
        token_context=context,
        client_factory=lambda _token: FakeRetryClient(),
        min_interval_seconds=0,
        stop_after_attempt_count=1,
    )

    audit = module.build_retry_quality_audit(context, outputs)
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert {"daily_basic_success_count", "daily_basic_success_cached_count", "daily_basic_rate_limited_count", "remaining_unfetched_dates", "lookahead_violation_rows"}.issubset(set(audit["metric"]))
    assert int(lookup["lookahead_violation_rows"]) == 0
    assert int(lookup["daily_basic_success_cached_count"]) >= 1

