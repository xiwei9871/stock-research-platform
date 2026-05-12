import pytest

from stock_research import daily_incremental


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def test_run_daily_incremental_pipeline_dry_run_lists_order_without_runners():
    result = daily_incremental.run_daily_incremental_pipeline(
        trade_date="2026-05-12",
        dry_run=True,
        adjust_type="qfq",
        source_service="stock_qfq",
        industry_system="sw",
    )

    assert result["status"] == "planned"
    assert result["adjust_type"] == "qfq"
    assert result["source_service"] == "stock_qfq"
    assert result["industry_system"] == "sw"
    assert [step["step"] for step in result["steps"]] == [
        "sync_core_assets",
        "load_market_bars",
        "check_market_data_freshness",
        "build_asset_status",
        "sync_index_bars",
        "sync_index_constituents",
        "sync_industry_memberships",
        "build_industry_bars",
        "compute_labels",
        "build_factor_daily",
        "score_approved_factors",
        "run_daily_research_report",
    ]
    assert {step["status"] for step in result["steps"]} == {"planned"}


def test_run_daily_incremental_pipeline_blocks_downstream_after_failure():
    calls = []
    records = []

    def ok_runner(context):
        calls.append(("ok", context["trade_date"]))
        return {"rows": 3}

    def failed_runner(context):
        calls.append(("failed", context["trade_date"]))
        raise RuntimeError("source unavailable")

    result = daily_incremental.run_daily_incremental_pipeline(
        trade_date="2026-05-12",
        step_runners={
            "sync_core_assets": ok_runner,
            "load_market_bars": failed_runner,
            "build_asset_status": ok_runner,
        },
        recorder=records.append,
    )

    assert result["status"] == "failed"
    assert calls == [("ok", "2026-05-12"), ("failed", "2026-05-12")]
    assert [step["status"] for step in result["steps"]] == ["success", "failed"]
    assert result["steps"][1]["error"] == "source unavailable"
    assert [record["step"] for record in records] == ["sync_core_assets", "load_market_bars"]


def test_run_daily_incremental_pipeline_checks_freshness_after_loading_bars():
    calls = []

    result = daily_incremental.run_daily_incremental_pipeline(
        trade_date="2026-05-12",
        step_runners={
            "sync_core_assets": lambda context: calls.append("sync_core_assets") or {},
            "load_market_bars": lambda context: calls.append("load_market_bars") or {"rows": 0},
            "check_market_data_freshness": lambda context: calls.append("check_market_data_freshness")
            or (_ for _ in ()).throw(RuntimeError("market bars missing")),
            "build_asset_status": lambda context: pytest.fail("should not run"),
        },
    )

    assert result["status"] == "failed"
    assert calls == [
        "sync_core_assets",
        "load_market_bars",
        "check_market_data_freshness",
    ]
    assert result["steps"][2]["step"] == "check_market_data_freshness"


def test_run_daily_incremental_pipeline_blocks_on_freshness_check():
    result = daily_incremental.run_daily_incremental_pipeline(
        trade_date="2026-05-12",
        freshness_checker=lambda context: {
            "status": "blocked",
            "reason": "market bars missing",
        },
        step_runners={"sync_core_assets": lambda context: pytest.fail("should not run")},
    )

    assert result == {
        "trade_date": "2026-05-12",
        "status": "blocked",
        "reason": "market bars missing",
        "steps": [],
    }


def test_check_market_data_freshness_blocks_when_market_bars_are_missing(monkeypatch):
    calls = []

    monkeypatch.setattr(
        daily_incremental,
        "connect",
        lambda service: calls.append(service) or _Context(object()),
    )
    monkeypatch.setattr(
        daily_incremental,
        "fetch_all",
        lambda conn, sql, params: [{"bar_count": 0}],
    )

    result = daily_incremental.check_market_data_freshness({"trade_date": "2026-05-12"})

    assert result == {
        "status": "blocked",
        "reason": "market_daily_bar missing for 2026-05-12",
        "bar_count": 0,
    }


def test_check_market_data_freshness_passes_when_market_bars_exist(monkeypatch):
    monkeypatch.setattr(daily_incremental, "connect", lambda service: _Context(object()))
    monkeypatch.setattr(
        daily_incremental,
        "fetch_all",
        lambda conn, sql, params: [{"bar_count": 1234}],
    )

    result = daily_incremental.check_market_data_freshness({"trade_date": "2026-05-12"})

    assert result == {"status": "ok", "bar_count": 1234}


def test_build_default_step_runners_wire_daily_jobs(monkeypatch):
    calls = []

    monkeypatch.setattr(
        daily_incremental,
        "sync_core_asset_master_for_service",
        lambda: calls.append(("sync_core_assets", {})),
    )
    monkeypatch.setattr(
        daily_incremental,
        "load_market_daily_bars",
        lambda **kwargs: calls.append(("load_market_bars", kwargs)) or 11,
    )
    monkeypatch.setattr(
        daily_incremental,
        "check_market_data_freshness",
        lambda context: calls.append(("check_market_data_freshness", context))
        or {"status": "ok", "bar_count": 1234},
    )
    monkeypatch.setattr(
        daily_incremental,
        "build_asset_status_daily_for_service",
        lambda **kwargs: calls.append(("build_asset_status", kwargs)),
    )
    monkeypatch.setattr(
        daily_incremental,
        "sync_index_daily_bars",
        lambda **kwargs: calls.append(("sync_index_bars", kwargs)) or 5,
    )
    monkeypatch.setattr(
        daily_incremental,
        "sync_index_constituents",
        lambda **kwargs: calls.append(("sync_index_constituents", kwargs)) or 3,
    )
    monkeypatch.setattr(
        daily_incremental,
        "sync_industry_memberships",
        lambda trade_date: calls.append(("sync_industry_memberships", {"trade_date": trade_date})) or 7,
    )
    monkeypatch.setattr(
        daily_incremental,
        "build_industry_daily_bars_for_service",
        lambda **kwargs: calls.append(("build_industry_bars", kwargs)),
    )
    monkeypatch.setattr(
        daily_incremental,
        "compute_and_store_labels",
        lambda **kwargs: calls.append(("compute_labels", kwargs)) or 13,
    )
    monkeypatch.setattr(
        daily_incremental,
        "build_and_store_factor_daily",
        lambda **kwargs: calls.append(("build_factor_daily", kwargs)) or 17,
    )
    monkeypatch.setattr(
        daily_incremental,
        "score_stored_factor_daily",
        lambda **kwargs: calls.append(("score_approved_factors", kwargs)) or 19,
    )
    monkeypatch.setattr(
        daily_incremental,
        "run_daily_research_report",
        lambda **kwargs: calls.append(("run_daily_research_report", kwargs)) or {"report_paths": {}},
    )

    runners = daily_incremental.build_default_step_runners()
    context = {
        "trade_date": "2026-05-12",
        "score_version": "manual_v1",
        "top_n": 30,
        "lookback_bars": 130,
        "reports_dir": "reports",
        "adjust_type": "hfq",
        "source_service": "stock_hfq",
        "industry_system": "csrc",
    }

    outputs = [runners[step](context) for step in daily_incremental.DAILY_INCREMENTAL_STEPS]

    assert [call[0] for call in calls] == daily_incremental.DAILY_INCREMENTAL_STEPS
    assert outputs[1] == {"rows": 11}
    assert outputs[2] == {"bar_count": 1234}
    assert calls[1][1]["source_service"] == "stock_hfq"
    assert calls[1][1]["start_date"] == "2026-05-12"
    assert calls[9][1]["lookback_bars"] == 130
    assert calls[10][1]["approved_only"] is True
