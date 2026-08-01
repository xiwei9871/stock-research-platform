from __future__ import annotations

import ast
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from stock_research.rolling_oversold.contracts import RollingOversoldConfig
from stock_research.rolling_oversold.loaders import RollingInputs, load_rolling_inputs
from stock_research.rolling_oversold import loaders, preflight


def _config() -> RollingOversoldConfig:
    return RollingOversoldConfig(
        anchor_start_date=date(2026, 7, 29),
        index_ids=("IDX",),
        industry_systems=("sw",),
        concept_systems=("theme",),
        forecast_horizons=(1, 3),
    )


def _install_db(monkeypatch):
    calls: list[tuple[str, list[object]]] = []

    @contextmanager
    def fake_connect(service):
        assert service == "research-test"
        yield object()

    def fake_fetch_all(conn, sql, params=None):
        del conn
        normalized = " ".join(sql.split())
        calls.append((normalized, list(params or [])))
        if "FROM market.trading_calendar" in normalized and "DESC" in normalized:
            return [
                {"trade_date": date(2026, 7, 29)},
                {"trade_date": date(2026, 7, 28)},
            ]
        if "FROM market.trading_calendar" in normalized:
            return [{"trade_date": date(2026, 7, 30)}]
        if "market.index_daily_bar" in normalized:
            return [{"index_id": "IDX", "trade_date": date(2026, 7, 29), "close": 1, "preclose": 1, "volume": 1, "amount": 1}]
        if "FROM market_daily_bar" in normalized:
            return [{"asset_id": "A", "trade_date": date(2026, 7, 29), "close": 1, "high": 1, "low": 1, "pct_chg": 0, "volume": 1, "amount": 1}]
        if "core.asset_status_daily" in normalized:
            return [{"asset_id": "A", "trade_date": date(2026, 7, 29), "is_trade": True, "is_st": False, "is_suspended": False, "is_limit_up": False, "is_limit_down": False}]
        if "core.industry_membership" in normalized:
            return [{"asset_id": "A", "industry_system": "sw", "industry_code": "801010", "industry_name": "Agriculture", "level": 1, "start_date": date(2020, 1, 1), "end_date": None}]
        if "core.concept_membership" in normalized:
            return [{"asset_id": "A", "concept_system": "theme", "concept_code": "C1", "concept_name": "Theme", "start_date": date(2020, 1, 1), "end_date": None}]
        if "market.industry_daily_bar" in normalized:
            return [{"industry_system": "sw", "industry_code": "801010", "industry_name": "Agriculture", "trade_date": date(2026, 7, 29), "close": 1, "preclose": 1, "volume": 1, "amount": 1}]
        if "market.concept_daily_bar" in normalized:
            return [{"concept_system": "theme", "concept_code": "C1", "concept_name": "Theme", "trade_date": date(2026, 7, 29), "close": 1, "preclose": 1, "volume": 1, "amount": 1}]
        raise AssertionError(normalized)

    monkeypatch.setattr(loaders, "connect", fake_connect)
    monkeypatch.setattr(loaders, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(
        loaders,
        "load_consumer_finance_history",
        lambda asset_ids, trade_date, *, service: pd.DataFrame(
            {"asset_id": asset_ids, "announcement_date": [trade_date] * len(asset_ids)}
        ),
    )
    monkeypatch.setattr(
        loaders,
        "load_consumer_valuation_history",
        lambda asset_ids, trade_date, *, service: pd.DataFrame(
            {"asset_id": asset_ids, "valuation_date": [trade_date] * len(asset_ids)}
        ),
    )
    return calls


def test_loader_uses_anchor_cutoff_and_point_in_time_membership_predicates(monkeypatch):
    calls = _install_db(monkeypatch)

    inputs = load_rolling_inputs(
        anchor_date=date(2026, 7, 29), config=_config(), service="research-test"
    )

    assert inputs.data_cutoff_date == date(2026, 7, 29)
    assert inputs.stock_bars["trade_date"].tolist() == ["2026-07-29"]
    calendar_sql, calendar_params = calls[0]
    assert "is_open = TRUE" in calendar_sql
    assert "trade_date <= %s" in calendar_sql
    assert calendar_params == ["2026-07-29", 252]
    industry_sql, industry_params = next(
        (sql, params) for sql, params in calls if "core.industry_membership" in sql
    )
    concept_sql, concept_params = next(
        (sql, params) for sql, params in calls if "core.concept_membership" in sql
    )
    assert "start_date <= %s" in industry_sql
    assert "end_date IS NULL OR end_date > %s" in industry_sql
    assert industry_params[:2] == ["2026-07-29", "2026-07-29"]
    assert "start_date <= %s" in concept_sql
    assert "end_date IS NULL OR end_date > %s" in concept_sql
    assert concept_params[:2] == ["2026-07-29", "2026-07-29"]
    stock_sql, stock_params = next(
        (sql, params) for sql, params in calls if "FROM market_daily_bar" in sql
    )
    assert "adjust_type = %s" in stock_sql
    assert stock_params == ["qfq", "2026-07-29"]


def test_loader_uses_original_non_trading_anchor_for_pit_memberships(monkeypatch):
    calls = _install_db(monkeypatch)

    inputs = load_rolling_inputs(
        anchor_date=date(2026, 8, 1), config=_config(), service="research-test"
    )

    assert inputs.data_cutoff_date == date(2026, 7, 29)
    industry_params = next(
        params for sql, params in calls if "core.industry_membership" in sql
    )
    concept_params = next(
        params for sql, params in calls if "core.concept_membership" in sql
    )
    assert industry_params[:2] == ["2026-08-01", "2026-08-01"]
    assert concept_params[:2] == ["2026-08-01", "2026-08-01"]


def test_loader_rejects_anchor_without_an_open_calendar_session(monkeypatch):
    @contextmanager
    def fake_connect(service):
        assert service == "research-test"
        yield object()

    def fake_fetch_all(conn, sql, params=None):
        del conn, sql, params
        return []

    monkeypatch.setattr(loaders, "connect", fake_connect)
    monkeypatch.setattr(loaders, "fetch_all", fake_fetch_all)

    with pytest.raises(ValueError, match="no complete open trading session"):
        load_rolling_inputs(
            anchor_date=date(2026, 7, 29), config=_config(), service="research-test"
        )


def _inputs(*, missing_industry_bar: bool = False) -> RollingInputs:
    cutoff = date(2026, 7, 29)
    dates = pd.bdate_range(end=cutoff, periods=252)
    industry_bars = pd.DataFrame(
        columns=["industry_system", "industry_code", "industry_name", "trade_date", "close", "preclose", "volume", "amount"]
    )
    if not missing_industry_bar:
        industry_bars = pd.DataFrame(
            {"industry_system": ["sw"], "industry_code": ["801010"], "industry_name": ["Agriculture"], "trade_date": [cutoff], "close": [1], "preclose": [1], "volume": [1], "amount": [1]}
        )
    return RollingInputs(
        anchor_date=cutoff,
        data_cutoff_date=cutoff,
        trading_dates=pd.DataFrame({"trade_date": dates}),
        index_bars=pd.DataFrame({"index_id": ["IDX"] * 252, "trade_date": dates, "close": 1, "preclose": 1, "volume": 1, "amount": 1}),
        stock_bars=pd.DataFrame({"asset_id": ["A"], "trade_date": [cutoff], "close": [1], "high": [1], "low": [1], "pct_chg": [0], "volume": [1], "amount": [1]}),
        stock_status=pd.DataFrame({"asset_id": ["A"], "trade_date": [cutoff], "is_trade": [True], "is_st": [False], "is_suspended": [False], "is_limit_up": [False], "is_limit_down": [False]}),
        industry_membership=pd.DataFrame({"asset_id": ["A"], "industry_system": ["sw"], "industry_code": ["801010"], "industry_name": ["Agriculture"], "level": [1], "start_date": [date(2020, 1, 1)], "end_date": [None]}),
        concept_membership=pd.DataFrame({"asset_id": ["A"], "concept_system": ["theme"], "concept_code": ["C1"], "concept_name": ["Theme"], "start_date": [date(2020, 1, 1)], "end_date": [None]}),
        industry_bars=industry_bars,
        concept_bars=pd.DataFrame({"concept_system": ["theme"], "concept_code": ["C1"], "concept_name": ["Theme"], "trade_date": [cutoff], "close": [1], "preclose": [1], "volume": [1], "amount": [1]}),
        finance=pd.DataFrame({"asset_id": ["A"], "announcement_date": [cutoff]}),
        valuation=pd.DataFrame({"asset_id": ["A"], "valuation_date": [cutoff]}),
        index_ids=("IDX",),
        score_version="test-v1",
    )


def test_preflight_blocks_missing_sector_bar_and_writes_backfill(monkeypatch, tmp_path):
    requests = []

    def fake_write(output_dir, **kwargs):
        requests.append((Path(output_dir), kwargs))
        return Path(output_dir) / "policy-backfill.json"

    monkeypatch.setattr(preflight, "write_backfill_request", fake_write)

    result = preflight.run_rolling_preflight(
        _inputs(missing_industry_bar=True),
        anchor_date=date(2026, 7, 29),
        output_dir=tmp_path,
    )

    assert result.blocked is True
    assert any(gap.dataset == "market.industry_daily_bar" for gap in result.gaps)
    assert requests[0][1]["strategy"] == "rolling_sector_oversold"
    assert requests[0][1]["ranking_version"] == "test-v1"
    assert (tmp_path / "rolling_oversold_preflight.json").is_file()


def test_complete_synthetic_inputs_pass_and_report_every_dataset(tmp_path):
    result = preflight.run_rolling_preflight(
        _inputs(), anchor_date=date(2026, 7, 29), output_dir=tmp_path
    )

    assert result.blocked is False
    assert result.gaps == ()
    assert set(result.checked_datasets) == {
        "market.trading_calendar", "market.index_daily_bar", "market_daily_bar",
        "core.asset_status_daily", "core.industry_membership",
        "core.concept_membership", "market.industry_daily_bar",
        "market.concept_daily_bar", "finance_history", "valuation_history",
    }
    assert {row["dataset"] for row in result.coverage_rows} == set(result.checked_datasets)
    assert any(row["sector_code"] == "801010" for row in result.coverage_rows)
    assert (tmp_path / "rolling_oversold_preflight.json").is_file()


def test_loader_module_has_no_external_ingestion_imports():
    source = Path(loaders.__file__).read_text(encoding="utf-8")
    imports = [
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    imports.extend(
        (node.module or "").split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    )
    assert not {"akshare", "baostock"}.intersection(imports)
